#!/bin/bash
set -euo pipefail

CALIB_REPO="@@CALIB_REPO@@"
SUBMITTER_HOME="@@SUBMITTER_HOME@@"
MICROMAMBA_BIN_HINT="@@MICROMAMBA_BIN_HINT@@"
BATCH_ID="@@BATCH_ID@@"
INPUT_LIST="@@INPUT_LIST@@"
OUTPUT_ROOTS_DIR="@@OUTPUT_ROOTS_DIR@@"
OUTPUT_PICKLES_DIR="@@OUTPUT_PICKLES_DIR@@"
WORK_DIR="@@WORK_DIR@@"
YEAR="@@YEAR@@"
FILES_NAME="@@FILES_NAME@@"
SKIMMER="@@SKIMMER@@"
CHUNKSIZE="@@CHUNKSIZE@@"
MAXCHUNKS="@@MAXCHUNKS@@"
BATCH_SIZE="@@BATCH_SIZE@@"
MAMBA_ENV="@@MAMBA_ENV@@"
KEEP_INTERMEDIATE="@@KEEP_INTERMEDIATE@@"

if [ ! -d "$CALIB_REPO" ]; then
  echo "ERROR: Calib_ChargeTagger repo not found: $CALIB_REPO" >&2
  exit 1
fi

if [ ! -f "$CALIB_REPO/src/run.py" ]; then
  echo "ERROR: run.py not found under: $CALIB_REPO/src/run.py" >&2
  exit 1
fi

if [ ! -f "$INPUT_LIST" ]; then
  echo "ERROR: input list not found: $INPUT_LIST" >&2
  exit 1
fi

MICROMAMBA_BIN=""
if [ -n "$MICROMAMBA_BIN_HINT" ] && [ -x "$MICROMAMBA_BIN_HINT" ]; then
  MICROMAMBA_BIN="$MICROMAMBA_BIN_HINT"
fi

if [ -z "$MICROMAMBA_BIN" ] && command -v micromamba >/dev/null 2>&1; then
  MICROMAMBA_BIN="$(command -v micromamba)"
fi

if [ -z "$MICROMAMBA_BIN" ]; then
  MICROMAMBA_CANDIDATES=(
    "$HOME/.local/bin/micromamba"
    "$HOME/micromamba/bin/micromamba"
    "$SUBMITTER_HOME/.local/bin/micromamba"
    "$SUBMITTER_HOME/micromamba/bin/micromamba"
  )

  if [[ "$SUBMITTER_HOME" == /home/* ]]; then
    MICROMAMBA_CANDIDATES+=("/isilon/export${SUBMITTER_HOME}/.local/bin/micromamba")
    MICROMAMBA_CANDIDATES+=("/isilon/export${SUBMITTER_HOME}/micromamba/bin/micromamba")
  fi

  for candidate in "${MICROMAMBA_CANDIDATES[@]}"; do
    if [ -x "$candidate" ]; then
      MICROMAMBA_BIN="$candidate"
      break
    fi
  done
fi

if [ -z "$MICROMAMBA_BIN" ]; then
  echo "ERROR: micromamba not found; required for env '$MAMBA_ENV'." >&2
  exit 1
fi

mapfile -t INPUT_FILES < <(grep -v '^[[:space:]]*$' "$INPUT_LIST")
if [ "${#INPUT_FILES[@]}" -eq 0 ]; then
  echo "ERROR: input list is empty: $INPUT_LIST" >&2
  exit 1
fi

for input_file in "${INPUT_FILES[@]}"; do
  if [ ! -f "$input_file" ]; then
    echo "ERROR: input ROOT file not found: $input_file" >&2
    exit 1
  fi
done

# src/run.py always updates outputs/latest relative to the process CWD,
# so the parent outputs/ directory must exist inside the worker work area.
mkdir -p "$OUTPUT_ROOTS_DIR" "$OUTPUT_PICKLES_DIR" "$WORK_DIR" "$WORK_DIR/outputs"
pushd "$WORK_DIR" >/dev/null

export PYTHONPATH="$CALIB_REPO/src:$CALIB_REPO/boostedhh/src${PYTHONPATH:+:$PYTHONPATH}"

# Give each Condor job its own micromamba cache so parallel jobs do not
# race on the shared ~/.cache/mamba/proc lock.
export XDG_CACHE_HOME="$WORK_DIR/.cache"
export CONDA_PKGS_DIRS="$WORK_DIR/.conda/pkgs"
export MAMBA_PKGS_DIRS="$WORK_DIR/.conda/pkgs"
mkdir -p "$XDG_CACHE_HOME" "$CONDA_PKGS_DIRS"

"$MICROMAMBA_BIN" run -n "$MAMBA_ENV" \
  python -u "$CALIB_REPO/src/run.py" \
    --processor skimmer \
    --skimmer "$SKIMMER" \
    --year "$YEAR" \
    --files "${INPUT_FILES[@]}" \
    --files-name "$FILES_NAME" \
    --naming-tag "$BATCH_ID" \
    --save-root \
    --chunksize "$CHUNKSIZE" \
    --maxchunks "$MAXCHUNKS" \
    --batch-size "$BATCH_SIZE" \
    --outdir "$WORK_DIR" \
    --no-write-final-weight

shopt -s nullglob
ROOT_OUTPUTS=("$WORK_DIR"/nano_skim_"$BATCH_ID"_batch_*.root)
PICKLE_OUTPUT="$WORK_DIR/outfiles/$BATCH_ID.pkl"

if [ ! -f "$PICKLE_OUTPUT" ]; then
  echo "ERROR: expected pickle not found: $PICKLE_OUTPUT" >&2
  exit 1
fi

if [ "${#ROOT_OUTPUTS[@]}" -ne 1 ]; then
  echo "ERROR: expected exactly one ROOT output for $BATCH_ID, found ${#ROOT_OUTPUTS[@]}." >&2
  echo "Hint: leave --batch-size at 9999 so one batch folder folds into one ROOT file." >&2
  exit 1
fi

if [ "$KEEP_INTERMEDIATE" -eq 1 ]; then
  cp -f "${ROOT_OUTPUTS[0]}" "$OUTPUT_ROOTS_DIR/$BATCH_ID.root"
  cp -f "$PICKLE_OUTPUT" "$OUTPUT_PICKLES_DIR/$BATCH_ID.pkl"
else
  mv -f "${ROOT_OUTPUTS[0]}" "$OUTPUT_ROOTS_DIR/$BATCH_ID.root"
  mv -f "$PICKLE_OUTPUT" "$OUTPUT_PICKLES_DIR/$BATCH_ID.pkl"
  rm -f "$WORK_DIR"/out_"$BATCH_ID"_batch_*.parquet || true
  rm -f "$WORK_DIR"/num_batches_"$BATCH_ID".txt || true
  rm -rf "$WORK_DIR"/outparquet || true
  rm -rf "$WORK_DIR"/outfiles || true
  rm -rf "$WORK_DIR"/outputs || true
fi

popd >/dev/null

echo "Wrote $OUTPUT_ROOTS_DIR/$BATCH_ID.root"
echo "Wrote $OUTPUT_PICKLES_DIR/$BATCH_ID.pkl"

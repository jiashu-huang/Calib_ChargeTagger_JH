"""
Runs coffea processors locally (iterative/futures) or via dask.

Author: Jiashu Huang
Date: Jan 2026

Usage:
python -m vcb.run \
  --skimmer vcbSkimmer \
  --year 2024 \
  --files /isilon/export/home/jhuan166/Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1/batch_000/<file>.root \
  --save-root \
  --chunksize 100000 \
  --maxchunks 0
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import pickle
from datetime import datetime
from pathlib import Path

import yaml

from boostedhh import run_utils
from boostedhh.hh_vars import DATA_SAMPLES
from boostedhh.processors import SkimmerABC
from boostedhh.xsecs import xsecs
from vcb import vcb_utils

DEFAULT_FILES_NAME = "TTtoLNuCB"


def _parse_skimmer_arg(skimmer: str | None) -> tuple[str, str | None]:
    """
    Docstring for _parse_skimmer_arg

    :param skimmer: Description
    :type skimmer: str | None
    :return: Description
    :rtype: tuple[str, str | None]

    Resolve the "--skimmer" value into a module name and optional class name.
    Examples:
        "vcbSkimmer" -> ("vcbSkimmer", None)
        "vcbSkimmer.py" -> ("vcbSkimmer", None)
    """
    if not skimmer:
        return "vcbSkimmer", None

    class_name = None
    module_part = skimmer

    raw_name = Path(module_part).name
    if raw_name.endswith(".py"):
        raw_name = raw_name[:-3]
    module_name = raw_name.split(".")[-1]

    return module_name, class_name


def _select_skimmer_class(
    skimmer_module, module_name: str, class_name: str | None
) -> type[SkimmerABC]:
    # Given an imported module and an optional class name, find the SkimmerABC subclass.
    # Priority: explicit class name -> class matching module name -> unique subclass in module.

    # If a class name is given, try to get it directly.
    if class_name:
        try:
            return getattr(skimmer_module, class_name)
        except AttributeError as exc:
            raise ValueError(
                f"Skimmer class {class_name} not found in processors.{module_name}"
            ) from exc

    if hasattr(skimmer_module, module_name):
        return getattr(skimmer_module, module_name)

    candidates = []
    for _, obj in vars(skimmer_module).items():
        if (
            inspect.isclass(obj)
            and issubclass(obj, SkimmerABC)
            and obj is not SkimmerABC
            and obj.__module__ == skimmer_module.__name__
        ):
            candidates.append(obj)

    # If the module defines exactly one SkimmerABC subclass, pick it.
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        options = ", ".join(sorted(cls.__name__ for cls in candidates))
        raise ValueError(
            "Multiple skimmer classes found in processors."
            f"{module_name}: {options}. Use --skimmer module:Class to select one."
        )

    raise ValueError(f"No SkimmerABC subclass found in processors.{module_name}")


def get_processor(
    processor: str,
    save_systematics: bool | None = None,
    region: str | None = None,
    nano_version: str | None = None,
    fatjet_pt_cut: float | None = None,
    fatjet_bb_preselection: bool | None = None,
    prescale_factor: int | None = None,
    skimmer: str | None = None,
):
    # Factory for processor instances. Currently only "skimmer" is supported.
    if processor == "skimmer":
        # Resolve module + class, then import and select the skimmer class.
        skimmer_name, class_name = _parse_skimmer_arg(skimmer)
        skimmer_module = importlib.import_module(f"vcb.processors.{skimmer_name}")
        skimmer_cls = _select_skimmer_class(skimmer_module, skimmer_name, class_name)

        # Instantiate the skimmer and pass runtime configuration.
        return skimmer_cls(
            xsecs=xsecs,
            save_systematics=save_systematics,
            region=region,
            nano_version=nano_version,
            fatjet_pt_cut=fatjet_pt_cut,
            fatjet_bb_preselection=fatjet_bb_preselection,
            prescale_factor=prescale_factor,
        )


def _default_naming_tag(args, fileset: dict) -> str:
    # Use first input filename (stripped + stem) as the default tag.
    first_file = None
    if args.files:
        first_file = args.files[0]
    else:
        for files in fileset.values():
            if files:
                first_file = files[0]
                break

    if first_file:
        base = Path(str(first_file)).name.strip()
        stem = base.rsplit(".", 1)[0] if "." in base else base
        return stem[:32] if stem else base[:32]

    return f"{args.starti}-{args.endi}"


def _add_final_weight_outputs(filetag: str, year: str, save_root: bool, outdir: Path) -> None:
    """
    Add a finalWeight column/branch to local batch parquet/root outputs.

    finalWeight is defined as:
      finalWeight = weight / totals["np_nominal"]
    where totals are accumulated over the full processed sample in outfiles/<filetag>.pkl.
    """
    out_pickle = outdir / "outfiles" / f"{filetag}.pkl"
    if not out_pickle.exists():
        print(f"Skipping finalWeight export: missing {out_pickle}")
        return

    with out_pickle.open("rb") as file:
        out_dict = pickle.load(file)

    year_key = str(year)
    if year_key not in out_dict:
        print(
            f"Skipping finalWeight export: year {year_key} not found in {out_pickle}. "
            f"Available: {list(out_dict.keys())}"
        )
        return

    datasets = out_dict[year_key]
    if len(datasets) != 1:
        print(
            "Skipping finalWeight export: expected exactly one dataset in this run, "
            f"found {len(datasets)} ({list(datasets.keys())})."
        )
        return

    dataset_name = next(iter(datasets))
    totals = datasets[dataset_name].get("totals", {})
    np_nominal = totals.get("np_nominal")

    if np_nominal is None:
        print(
            "Skipping finalWeight export: totals['np_nominal'] not found "
            f"for dataset {dataset_name} (likely data)."
        )
        return
    if np_nominal == 0:
        print(f"Skipping finalWeight export: np_nominal is 0 for dataset {dataset_name}.")
        return

    import awkward as ak
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    import uproot

    parquet_paths = sorted(outdir.glob(f"out_{filetag}_batch_*.parquet"))
    if not parquet_paths:
        print(f"Skipping finalWeight export: no parquet files found for filetag {filetag}.")
        return

    for parquet_path in parquet_paths:
        pddf = pd.read_parquet(parquet_path)

        if isinstance(pddf.columns, pd.MultiIndex):
            if "weight" not in pddf.columns.get_level_values(0):
                print(f"Skipping {parquet_path}: missing weight column.")
                continue
            weight_block = pddf["weight"]
            weight_vals = (
                weight_block.iloc[:, 0] if isinstance(weight_block, pd.DataFrame) else weight_block
            )
            # Keep MultiIndex format consistent with existing skim columns.
            subkey = weight_block.columns[0] if isinstance(weight_block, pd.DataFrame) else 0
            pddf[("finalWeight", subkey)] = weight_vals.to_numpy() / np_nominal
        else:
            if "weight" not in pddf.columns:
                print(f"Skipping {parquet_path}: missing weight column.")
                continue
            pddf["finalWeight"] = pddf["weight"].to_numpy() / np_nominal

        table = pa.Table.from_pandas(pddf)
        pq.write_table(table, parquet_path)

        if not save_root:
            continue

        batch_idx = parquet_path.stem.rsplit("_batch_", 1)[-1]
        root_path = outdir / f"nano_skim_{filetag}_batch_{batch_idx}.root"
        if not root_path.exists():
            print(f"Skipping ROOT update for batch {batch_idx}: missing {root_path}")
            continue

        if isinstance(pddf.columns, pd.MultiIndex):
            events_dict = {
                key: np.squeeze(pddf[key].values)
                for key in pddf.columns.get_level_values(0).unique()
            }
        else:
            events_dict = {key: np.squeeze(pddf[key].values) for key in pddf.columns}

        with uproot.recreate(str(root_path), compression=uproot.LZ4(4)) as rfile:
            rfile["Events"] = ak.Array(run_utils.flatten_dict(events_dict))

    print(
        f"Added finalWeight to {len(parquet_paths)} parquet batch(es)"
        + (" and refreshed matching ROOT file(s)." if save_root else ".")
    )


def main(args):
    # Build the processor with all CLI-configured options.
    p = get_processor(
        args.processor,
        args.save_systematics,
        args.region,
        args.nano_version,
        args.fatjet_pt_cut,
        args.fatjet_bb_preselection,
        args.prescale_factor,
        args.skimmer,
    )

    # Select output formats by processor type (skimmer always saves both).
    save_parquet = {"skimmer": True}[args.processor]
    save_root = {"skimmer": True}[args.processor]

    # By default, skip bad files unless we are explicitly running on data.
    skipbadfiles = True

    if len(args.files):
        # Direct file list given on the command line: build a single-entry fileset.
        fileset = {f"{args.year}_{args.files_name}": args.files}
        skipbadfiles = False  # not added functionality for args.files yet
    else:
        if args.yaml:
            # YAML workflow: load list of samples + subsamples for the given year.
            with Path(args.yaml).open() as file:
                samples_to_submit = yaml.safe_load(file)
            try:
                samples_to_submit = samples_to_submit[args.year]
            except Exception as e:
                raise KeyError(f"Year {args.year} not present in yaml dictionary") from e

            samples = samples_to_submit.keys()
            subsamples = []
            for sample in samples:
                subsamples.extend(samples_to_submit[sample].get("subsamples", []))
        else:
            # CLI workflow: use samples + subsamples provided in arguments.
            samples = args.samples
            subsamples = args.subsamples

        # Build fileset from index JSON with start/end slice limits.
        fileset = run_utils.get_fileset(
            f"data/index_{args.year}.json",
            args.year,
            samples,
            subsamples,
            args.starti,
            args.endi,
        )

        # don't skip "bad" files for data - we want it throw an error in that case
        for key in fileset:
            if key in DATA_SAMPLES:
                skipbadfiles = False

    print(f"Running on fileset {fileset}")
    if args.executor == "dask":
        # Distributed execution on a Dask cluster.
        run_utils.run_dask(p, fileset, args)
        if args.write_final_weight:
            print(
                "Skipping finalWeight export for dask executor (only local iterative/futures supported)."
            )
    else:
        if args.naming_tag is not None:
            filetag = args.naming_tag
        elif args.file_tag is not None:
            filetag = args.file_tag
        else:
            filetag = _default_naming_tag(args, fileset)

        # Resolve output directory: use explicit --outdir or auto-generate a timestamped one.
        outputs_root = Path("outputs")
        if args.outdir is not None:
            run_outdir = Path(args.outdir)
        else:
            run_outdir = outputs_root / datetime.now().strftime("%Y%m%d_%H%M")
        run_outdir.mkdir(parents=True, exist_ok=True)
        print(f"Writing outputs to: {run_outdir.resolve()}")

        # Local execution via Coffea's iterative executor.
        run_utils.run(
            p,
            fileset,
            chunksize=args.chunksize,
            maxchunks=args.maxchunks,
            skipbadfiles=skipbadfiles,
            save_parquet=save_parquet,
            save_root=save_root and args.save_root,
            filetag=filetag,
            batch_size=args.batch_size,
            outdir=run_outdir,
        )

        if args.write_final_weight and args.processor == "skimmer":
            _add_final_weight_outputs(
                filetag, str(args.year), save_root and args.save_root, run_outdir
            )

        # Update the "latest" symlink to point to this run's output directory.
        # outputs/ may not exist yet when --outdir points somewhere else.
        outputs_root.mkdir(parents=True, exist_ok=True)
        latest_link = outputs_root / "latest"
        if latest_link.is_symlink():
            latest_link.unlink()
        symlink_target = run_outdir if run_outdir.is_absolute() else run_outdir.name
        latest_link.symlink_to(symlink_target)
        print(f"Updated outputs/latest -> {symlink_target}")


if __name__ == "__main__":
    # Top-level CLI entrypoint: define arguments, validate, then launch main().
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # Common args shared across different workflows.
    run_utils.parse_common_run_args(parser)
    parser.set_defaults(files_name=DEFAULT_FILES_NAME)
    run_utils.parse_common_hh_args(parser)
    vcb_utils.parse_common_run_args(parser)
    parser.add_argument(
        "--skimmer",
        type=str,
        default="vcbSkimmer",
        help=(
            "Skimmer module name in src/processors, optionally with class name "
            "(e.g., vcbSkimmer, vcbSkimmer.py, ttSkimmer)."
        ),
    )
    parser.add_argument(
        "--naming-tag",
        type=str,
        default=None,
        help=(
            "Optional output file tag. Preferred over --file-tag when both are set. "
            "Defaults to the first 32 characters of the input filename (stem)."
        ),
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default=None,
        help=(
            "Output directory for this run. Defaults to outputs/YYYYMMDD_HHMM/ "
            "(auto-generated timestamp). The outputs/latest symlink is always updated."
        ),
    )
    parser.add_argument(
        "--write-final-weight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "For local (iterative/futures) skimmer runs, add finalWeight = weight / np_nominal "
            "to output parquet files and ROOT branches."
        ),
    )
    args = parser.parse_args()

    # Normalize "year" argument to a single value if a one-element list is passed.
    if isinstance(args.year, list):
        if len(args.year) == 1:
            args.year = args.year[0]
        else:
            raise ValueError("Running on multiple years is not supported yet")

    main(args)

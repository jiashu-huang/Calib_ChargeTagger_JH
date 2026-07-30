# Plan: dead-flag cleanup + deferred `finalWeight`

> **Archived 2026-07-27, fully implemented.** This was the git-ignored working
> plan for the `second-pass-finalWeight` branch; everything in it landed and was
> verified. It is kept because it records measurements that exist nowhere else
> (the PyROOT branch-append spike, PyROOT-vs-C++ timings). Links below reflect
> the repo layout at the time of writing: `NORMALIZATION.md` is now
> [`docs/normalization.md`](../normalization.md), `RUNTAG.md` is now
> [`docs/cli.md`](../cli.md).

Working plan, not a design record. The committed companion is
[NORMALIZATION.md](../normalization.md). Written 2026-07-26.

## Context

Two unrelated pieces of work, both prompted by the flag audit in
[RUNTAG.md](../cli.md).

**1. Dead flags.** `--fatjet-pt-cut` and `--fatjet-bb-preselection` are accepted
by the parser, stored on the skimmer, and never read. They are noise in `--help`
and in every worked example. (`--prescale-factor` was initially in this list by
mistake — it is live at
[vcbSkimmer.py:600](../../src/vcb/processors/vcbSkimmer.py#L600) and stays.)

**2. `finalWeight`.** Today the main skimmer run computes `finalWeight` by
default, and condor has to opt out with `--no-write-final-weight` and then run a
second pass (`fix_final_weight.py`) that destructively rewrites all 93 batch
ROOTs. That design fuses a *per-event* quantity with a *global* one at write
time, which is the root of the silent-bias failure mode documented in
[NORMALIZATION.md](../normalization.md) §3. The goal is to make normalization
always a separate, idempotent, cheap second pass — while keeping `finalWeight` a
real column in the same `Events` tree, so downstream reading stays trivial.

---

## Part 1 — Remove the two dead flags

| File | Change |
|---|---|
| [src/vcb/vcb_utils.py](../../src/vcb/vcb_utils.py#L72) | Delete the `--fatjet-pt-cut` argument and the `add_bool_arg(..., "fatjet-bb-preselection", ...)` call. Drop the now-unused `add_bool_arg` import if nothing else uses it. |
| [src/vcb/processors/vcbSkimmer.py](../../src/vcb/processors/vcbSkimmer.py#L181) | Drop `fatjet_pt_cut` / `fatjet_bb_preselection` from `__init__` and the `self._fatjet_pt_cut` / `self._fatjet_bb_preselection` assignments. |
| [src/vcb/run.py](../../src/vcb/run.py#L106) | Drop both from `get_processor`'s signature and from the call site in `main`. |
| [RUNTAG.md](../cli.md) | Remove both rows from the *Inert flags* table; move `--prescale-factor` out of that table into *Processor* with a note that it adds a `prescale` cut to the cutflow. |

Keep `--prescale-factor` untouched.

---

## Part 2 — Make `finalWeight` a second pass

### 2a. Drop it from the main run

| File | Change |
|---|---|
| [src/vcb/run.py](../../src/vcb/run.py) | Delete `_add_final_weight_outputs` (~105 lines), the `--write-final-weight` argument, and the `if args.write_final_weight ...` block in `main`. The `--root-only` special-case printout goes away with it. |
| [condor/templates/calib_batch_exec.sh](../../condor/templates/calib_batch_exec.sh#L112) | Drop `--no-write-final-weight` — no longer a valid flag. |
| [condor/README.md](../../condor/README.md), [README.md](../../README.md), [RUNTAG.md](../cli.md) | Update the flag tables and the step-2 workflow description. |

After this the skimmer writes `weight` and never `finalWeight`. One code path,
no way to bake in a stale denominator.

### 2b. New `condor/scripts/normalize.py`, replacing `fix_final_weight.py`

Reuses the pickle-reading logic already in
`fix_final_weight.py:load_global_norm` (since retired)
and the `make_abs` helper; the only genuinely new part is the branch append.

1. **Pair ROOTs to pickles by filename stem.** Raise on any ROOT without a
   pickle; skip orphan pickles with a warning. This closes the hole in
   NORMALIZATION.md §3 — today the two directories are globbed independently and
   never compared.
2. **Sum `np_nominal`** over exactly the paired pickles.
3. **Write `metadata/normalization.json`**: `global_np_nominal`, `sigma_x_lumi`,
   `total_nevents`, the explicit batch list, the count, and a timestamp. This is
   the provenance record even when the column is also written.
4. **Append the `finalWeight` branch in place with PyROOT** (see below).
5. **Write the provenance next to it**, in the same file: the `global_np_nominal`
   used and a short fingerprint (e.g. sha1) of the sorted batch list it was
   summed over. `finalWeight` is the one branch that is *not* a property of the
   event alone — it depends on which other files were processed — so a batch
   being dropped or reprocessed silently invalidates it in every *other* file,
   which is otherwise untouched and byte-identical. Storing the fingerprint lets
   a reader assert in one line that the column matches the sample in front of
   it, turning silent rot into a loud failure.
6. **Idempotent**: if `finalWeight` already exists, skip unless `--force`.
7. `--target batches|merged` (default `batches`) so it can run before or after
   the hadd.

Delete `fix_final_weight.py`.

### The append, and why it is cheap

`uproot` cannot add a branch to an existing `TTree` — it must read every branch
and rewrite the file. That is what makes the current pass expensive. ROOT
*can* append a branch in place, writing only the new baskets:

```python
f = ROOT.TFile.Open(path, "UPDATE")
tree = f.Get("Events")
val = array("d", [0.0])
br = tree.Branch("finalWeight", val, "finalWeight/D")
for i, w in enumerate(weights):          # weights read once via uproot
    val[0] = w / global_np_nominal
    br.Fill()
tree.Write("", ROOT.TObject.kOverwrite)
f.Close()
```

Measured cost, from the committed baseline (859 B/event, 346 branches,
`weight` = 2.94 compressed B/event) and the measured production size
(18,823,970 readable input events × 30.89% raw acceptance = **5.82 M selected
events**, ~**5.0 GB** of skim):

| Approach | Bytes touched | Destructive? |
|---|---|---|
| Append branch via PyROOT | **~17 MB written** (+0.34% file size) | no |
| Full rewrite via uproot (today) | ~10 GB (read 5 + write 5) | yes |

`finalWeight = weight / scalar` has the same entropy as `weight`, so ~2.94
compressed bytes/event is the right figure. **Roughly 600× less I/O than the
current pass, for the same end result.**

### Spike result — **PASSED 2026-07-26**, risk retired

Appended a branch to a copy of `tests/outfile/test-output.root` with PyROOT
6.32.02 and verified with uproot:

```
branch == weight/denominator      : bit-exact
altered original branches         : NONE (all 346 identical)
entries                           : unchanged
hadd preserves the new branch     : yes
file growth                       : 3.1 B/entry  ->  18 MB for production
```

ROOT updates an uproot-written LZ4 `TTree` cleanly. No fallback needed.

**Timing, PyROOT vs runtime-compiled C++, same machine and files:**

| entries | PyROOT | C++ | peak RSS py / C++ |
|---|---|---|---|
| 64,497 | 10.29 us/ev | — | 581 MB |
| 515,976 | **1.17 us/ev** | 2.28 us/ev | 590 / 574 MB |
| 2,063,904 | **0.85 us/ev** | 2.04 us/ev | 626 / 583 MB |

Per-entry cost *falls* as the tree grows (fixed overhead amortising), so
**~5 s of loop for 5.82 M events, ~1 minute wall** including opening 93 files in
one process. An earlier estimate of 37 s came from the smallest file and was 7x
pessimistic.

**C++ is not worth it, and measurably loses.** Both languages call the identical
compiled ROOT libraries for decompression and basket packing — Python was never
in that path. The time goes into *reading* the `weight` column, where uproot's
one vectorised pass beats 2 M `GetEntry()` calls; the naive C++ loop is 2.4x
slower. (A first C++ attempt was 17x slower still, because `GetEntry` reads all
346 branches unless you `SetBranchStatus` them off — the access pattern, not the
language, is the variable.) Memory is a wash: ~560 MB of that RSS is ROOT's own
libraries before either version does anything.

C++ *would* be the right call for the old 5 GB `RDataFrame::Snapshot` rewrite.
The append shrinks the job to 18 MB, which leaves nothing for the language to
win. If C++ is wanted anyway, use `ROOT.gInterpreter.Declare()` inline — real
compiled C++, no build step, no binary to deploy to the workers.

### 2c. Make each batch ROOT self-describing

Write the batch's own `np_nominal` into its ROOT file at skim time — a
single-entry auxiliary tree or a `TParameter<double>` next to `Events`. Each job
knows its own `np_nominal` (it is already in `totals_dict`), so this is local
with no global dependency: 8 bytes per file.

The second pass then sums denominators by reading the ROOTs directly, and the
ROOT↔pickle pairing stops being load-bearing — the orphan-pickle failure mode
disappears by construction instead of being defended against with a raise in
step 1. This is recommendation #3 in [NORMALIZATION.md](../normalization.md) §6.

Note what is *not* worth storing: a per-event "acceptance" column
`a_i = w^np_i / Σ_all w^np` cannot be written at skim time (the denominator is
global), and written in the second pass it is just `finalWeight / σL` — same
cost, worse to use. The per-event content is already complete, because
`weight_noxsec` **is** `w^np` exactly: the four weights added (`genweight`,
`pileup`, `ISRPartonShower`, `FSRPartonShower`) are precisely
`norm_preserving_weights`, so `weight / weight_noxsec = σL = 42760.5606` holds
to machine precision on every event. `finalWeight` therefore adds exactly one
scalar, replicated per event — which is why appending it later is cheap, and why
no cleverer per-event column can beat it.

### 2d. Also worth doing

Swap the two `mv` lines in
[calib_batch_exec.sh:133-134](../../condor/templates/calib_batch_exec.sh#L133) so the
**pickle moves first**. Then "a ROOT exists" implies "its pickle exists", and
step 1 above can never trip on a job killed between the two moves.

---

## Two properties worth stating, because the design depends on them

**`np_nominal` covers every event read, before any cut.**
[vcbSkimmer.py:419](../../src/vcb/processors/vcbSkimmer.py#L419) computes
`gen_selected` *before* any `add_selection` call (all of which are at lines
582–602), so `selection.names` is empty and `gen_selected` is all-True. This is
what makes `finalWeight` a valid ratio estimator — but it is an accident of
statement ordering, not an assertion. **Add a comment at line 419** saying that
moving any `add_selection` above it silently changes every yield.

**`weight` already contains σ×L.** Step 11 of `add_weights` multiplies every
entry of `weights_dict` by `weight_norm`, so no σL factor is needed in the
second pass — and `single_weight_*` diagnostics carry it too, which is why they
are not bare scale factors.

---

## Verification

```bash
# 1. lint + units
micromamba run -n ttbar ruff check src/vcb tests condor
micromamba run -n ttbar python -m pytest tests/ -q

# 2. removed flags are gone, prescale survives
micromamba run -n ttbar python -m vcb.run --help | grep -E "fatjet|prescale|final-weight"

# 3. regenerate baselines (finalWeight branch disappears; nTrueInt appears)
micromamba run -n ttbar python tests/test_run.py
git diff tests/outfile/
```

Expected baseline diff: `finalWeight` **removed**, `nTrueInt` **added**, and
pile-up-dependent weight values shifted. The `nTrueInt` and weight changes are
still outstanding from the pile-up commit — this run settles both at once.
Anything else in the diff is a bug.

```bash
# 4. spike the append on a copy, then end-to-end on two batches
python condor/submit_batches.py --input-root "$INPUT" --tag norm_test --test --submit
python condor/scripts/normalize.py --processed-dir "$INPUT/processed-nano/norm_test"
```

End-to-end check: `Σ finalWeight` over the merged output should equal
`σL × (weighted acceptance)` = `42760.56 × (Σ_selected weight_np / Σ_all
weight_np)`, independent of how many batches were processed. Verify re-running
`normalize.py` is a no-op without `--force`, and that deleting one pickle makes
it raise rather than silently inflating the yield.

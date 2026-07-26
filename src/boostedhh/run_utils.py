# from distributed.diagnostics.plugin import WorkerPlugin
from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

import numpy as np
import uproot
from coffea import nanoevents, processor

from . import utils


def add_mixins(nanoevents):
    # for running on condor
    nanoevents.PFNanoAODSchema.mixins["SubJet"] = "FatJet"
    nanoevents.PFNanoAODSchema.mixins["PFCands"] = "PFCand"
    nanoevents.PFNanoAODSchema.mixins["SV"] = "PFCand"


def get_fileset(
    fileset_path: str,
    year: int,
    samples: list,
    subsamples: list,
    starti: int = 0,
    endi: int = -1,
    get_num_files: bool = False,
    # coffea_casa: str = False,
):
    with Path(fileset_path).open() as f:
        full_fileset_nano = json.load(f)

    # check if fileset contains multiple years
    if not fileset_path.endswith(f"{year}.json"):
        full_fileset_nano = full_fileset_nano[year]

    fileset = {}

    for sample in samples:
        sample_set = full_fileset_nano[sample]

        set_subsamples = list(sample_set.keys())

        # check if any subsamples for this sample have been specified
        get_subsamples = set(set_subsamples).intersection(subsamples)

        if len(subsamples):
            for subs in subsamples:
                if subs not in get_subsamples:
                    raise ValueError(f"Subsample {subs} not found for sample {sample}!")

        # if so keep only that subset
        if len(get_subsamples):
            sample_set = {subsample: sample_set[subsample] for subsample in get_subsamples}

        if get_num_files:
            # return only the number of files per subsample (for splitting up jobs)
            fileset[sample] = {}
            for subsample, fnames in sample_set.items():
                fileset[sample][subsample] = len(fnames)

        else:
            # return all files per subsample
            sample_fileset = {}

            for subsample, fnames in sample_set.items():
                run_fnames = fnames[starti:] if endi < 0 else fnames[starti:endi]
                sample_fileset[f"{year}_{subsample}"] = run_fnames

            fileset = {**fileset, **sample_fileset}

    return fileset


def parse_common_run_args(parser):
    parser.add_argument("--starti", default=0, help="start index of files", type=int)
    parser.add_argument("--endi", default=-1, help="end index of files", type=int)
    parser.add_argument(
        "--executor",
        type=str,
        default="iterative",
        choices=["futures", "iterative", "dask"],
        help="type of processor executor",
    )
    parser.add_argument(
        "--files", default=[], help="set of files to run on instead of samples", nargs="*"
    )
    parser.add_argument(
        "--files-name",
        type=str,
        default="files",
        help="sample name of files being run on, if --files option used",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="# of outputs to combine into a single output if saving .parquet or .root files",
    )
    parser.add_argument("--yaml", default=None, help="yaml file", type=str)
    parser.add_argument("--file-tag", default=None, help="optional output file tag", type=str)


def parse_common_hh_args(parser):
    parser.add_argument(
        "--year",
        help="year",
        type=str,
        nargs="+",
        required=True,
        choices=["2018", "2022", "2022EE", "2023", "2023BPix", "2024"],
    )

    parser.add_argument(
        "--samples",
        default=[],
        help="which samples to run",  # , default will be all samples",
        nargs="*",
    )

    parser.add_argument(
        "--subsamples",
        default=[],
        help="which subsamples, by default will be all in the specified sample(s)",
        nargs="*",
    )

    parser.add_argument("--maxchunks", default=0, help="max chunks", type=int)
    parser.add_argument("--chunksize", default=10000, help="chunk size", type=int)

    utils.add_bool_arg(parser, "save-systematics", default=False, help="save systematic variations")
    utils.add_bool_arg(parser, "save-root", default=False, help="save root ntuples too")


def flatten_dict(var_dict: dict):
    """
    Flattens dictionary of variables so that each key has a 1d-array
    """
    new_dict = {}
    for key, var in var_dict.items():
        num_objects = var.shape[-1]
        if len(var.shape) >= 2 and num_objects > 1:
            temp_dict = {f"{key}{obj}": var[:, obj] for obj in range(num_objects)}
            new_dict = {**new_dict, **temp_dict}
        else:
            new_dict[key] = np.squeeze(var)

    return new_dict


def run_dask(p: processor, fileset: dict, args):
    """Run processor on using dask via lpcjobqueue"""

    from distributed import Client
    from lpcjobqueue import LPCCondorCluster

    cluster = LPCCondorCluster(
        ship_env=True, shared_temp_directory="/tmp", transfer_input_files="src/HH4b", memory="4GB"
    )
    cluster.adapt(minimum=1, maximum=350)

    local_dir = Path().resolve()
    local_parquet_dir = local_dir / "outparquet_dask"
    local_parquet_dir.mkdir(exist_ok=True)

    with Client(cluster) as client:
        from datetime import datetime

        print(datetime.now())
        print("Waiting for at least one worker...")
        client.wait_for_workers(1)
        print(datetime.now())

        from dask.distributed import performance_report

        with performance_report(filename="dask-report.html"):
            for sample, files in fileset.items():
                outfile = f"{local_parquet_dir}/{args.year}_dask_{sample}.parquet"
                if Path(outfile).is_dir():
                    print("File " + outfile + " already exists. Skipping.")
                    continue

                print("Begin running " + sample)
                print(datetime.now())
                uproot.open.defaults["xrootd_handler"] = (
                    uproot.source.xrootd.MultithreadedXRootDSource
                )

                executor = processor.DaskExecutor(
                    status=True, client=client, retries=2, treereduction=2
                )
                run = processor.Runner(
                    executor=executor,
                    savemetrics=True,
                    schema=processor.NanoAODSchema,
                    chunksize=10000,
                    # chunksize=args.chunksize,
                    skipbadfiles=1,
                )
                out, metrics = run({sample: files}, "Events", processor_instance=p)

                import pandas as pd

                pddf = pd.concat(
                    [pd.DataFrame(v.value) for k, v in out["array"].items()],
                    axis=1,
                    keys=list(out["array"].keys()),
                )

                import pyarrow as pa
                import pyarrow.parquet as pq

                table = pa.Table.from_pandas(pddf)
                pq.write_table(table, outfile)

                with Path(f"{local_parquet_dir}/{args.year}_dask_{sample}.pkl").open("wb") as f:
                    pickle.dump(out["pkl"], f)


def run(
    p: processor,
    fileset: dict,
    chunksize: int,
    maxchunks: int,
    skipbadfiles: bool,
    save_parquet: bool,
    save_root: bool,
    filetag: str,  # should be starti-endi
    executor: str = "iterative",
    batch_size: int = 20,
    outdir: Path | None = None,
    root_dir: Path | None = None,
):
    """
    Run processor without fancy dask (outputs then need to be accumulated manually)

    batch_size (int): used to combine a ``batch_size`` number of outputs into one parquet / root
    outdir (Path | None): directory to write outputs to; defaults to current working directory
    root_dir (Path | None): directory for the skim ROOT files; defaults to ``outdir``
    """
    add_mixins(nanoevents)  # update nanoevents schema

    # resolve output directory
    local_dir = Path(outdir).resolve() if outdir is not None else Path().resolve()
    local_dir.mkdir(parents=True, exist_ok=True)

    # skim ROOT files may be sent elsewhere than the rest of the run's outputs
    root_out_dir = Path(root_dir).resolve() if root_dir is not None else local_dir
    if save_root:
        root_out_dir.mkdir(parents=True, exist_ok=True)

    # outputs are saved here as pickles
    pickles_dir = local_dir / "outfiles"
    pickles_dir.mkdir(exist_ok=True)

    if save_parquet or save_root:
        # these processors store intermediate files in the "outparquet" local directory
        local_parquet_dir = local_dir / "outparquet"

        if local_parquet_dir.is_dir():
            os.system(f"rm -rf {local_parquet_dir}")

        local_parquet_dir.mkdir()

    uproot.open.defaults["xrootd_handler"] = uproot.source.xrootd.MultithreadedXRootDSource

    if executor == "futures":
        executor = processor.FuturesExecutor(status=True)
    else:
        executor = processor.IterativeExecutor(status=True)

    run = processor.Runner(
        executor=executor,
        savemetrics=True,
        schema=nanoevents.NanoAODSchema,
        chunksize=chunksize,
        maxchunks=None if maxchunks == 0 else maxchunks,
        skipbadfiles=skipbadfiles,
    )

    previous_outparquet_dir = os.environ.get("BOOSTEDHH_OUTPARQUET_DIR")
    if save_parquet or save_root:
        os.environ["BOOSTEDHH_OUTPARQUET_DIR"] = str(local_parquet_dir)

    try:
        # try file opening 3 times if it fails
        for i in range(3):
            try:
                out, metrics = run(fileset, "Events", processor_instance=p)
                break
            except FileNotFoundError as e:
                import time

                print("Error!")
                print(e)
                if i < 2:
                    print("Retrying in 1 minute")
                    time.sleep(60)
                else:
                    raise e
    finally:
        if previous_outparquet_dir is None:
            os.environ.pop("BOOSTEDHH_OUTPARQUET_DIR", None)
        else:
            os.environ["BOOSTEDHH_OUTPARQUET_DIR"] = previous_outparquet_dir

    print(out)

    with (pickles_dir / f"{filetag}.pkl").open("wb") as f:
        pickle.dump(out, f)

    if save_parquet or save_root:
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq

        # Get all parquet files
        path = Path(local_parquet_dir)
        parquet_files = list(path.glob("*.parquet"))

        num_batches = int(np.ceil(len(parquet_files) / batch_size))
        if save_parquet:
            with (local_dir / f"num_batches_{filetag}.txt").open("w") as f:
                f.write(f"{num_batches}")

        # need to combine all the files from these processors before transferring to EOS
        # otherwise it will complain about too many small files
        for i in range(num_batches):
            print(i)
            batch = parquet_files[i * batch_size : (i + 1) * batch_size]
            print(batch)
            print([pd.read_parquet(f) for f in batch])
            pddf = pd.concat([pd.read_parquet(f) for f in batch])

            if save_parquet:
                # need to write with pyarrow as pd.to_parquet doesn't support different types in
                # multi-index column names
                table = pa.Table.from_pandas(pddf)
                pq.write_table(table, local_dir / f"out_{filetag}_batch_{i}.parquet")

            if save_root:
                import awkward as ak

                with uproot.recreate(
                    root_out_dir / f"nano_skim_{filetag}_batch_{i}.root", compression=uproot.LZ4(4)
                ) as rfile:
                    rfile["Events"] = ak.Array(
                        # take only top-level column names in multiindex df
                        flatten_dict(
                            {key: np.squeeze(pddf[key].values) for key in pddf.columns.levels[0]}
                        )
                    )

        # the per-chunk parquet scratch only exists to assemble the batched outputs
        # above; drop it when the caller does not want parquet kept
        if not save_parquet:
            os.system(f"rm -rf {local_parquet_dir}")

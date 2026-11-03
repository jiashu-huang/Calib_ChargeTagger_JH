"""Prepare and run a bounded B0 skim for the matched-jet mass comparison.

One immutable, identity-selected set of complete files is used per sample.
The existing C1 sidecar validator and B0 validator own the physics checks.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import traceback
import zlib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parents[1]
PROXY = WORKSPACE / "cmssw-charge-run/x509up_u140430215"
MAMBA = Path('/isilon/export/home/jhuan166/.local/bin/micromamba')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def prepare(args):
    source = args.truth_campaign.resolve()
    config = json.loads((source / 'campaign.json').read_text())
    inventory_path = source / 'inventory.json'
    if sha(inventory_path) != config['inventory_sha256']:
        raise ValueError('Source inventory checksum mismatch')
    validator_path = source / 'code/condor/scripts/c1_truth_campaign.py'
    if sha(validator_path) != config['code_sha256']['condor/scripts/c1_truth_campaign.py']:
        raise ValueError('C1 validator checksum mismatch')
    spec = importlib.util.spec_from_file_location('c1_frozen', validator_path)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    inventory = json.loads(inventory_path.read_text())
    chosen = []
    totals = {}
    for sample in ('TT2Q', 'TTBB'):
        candidates = [r for r in inventory['files'] if r['sample'] == sample]
        candidates.sort(key=lambda r: hashlib.sha256(
            f'{args.seed}:{r["id"]}'.encode()).hexdigest())
        total = 0
        for record in candidates:
            pair = source / 'pairs' / sample / record['id']
            validator.validate_pair(pair, record, config)
            manifest = pair / 'manifest.json'
            chosen.append({**record, 'truth_manifest': str(manifest),
                           'truth_manifest_sha256': sha(manifest)})
            total += record['entries']
            if total >= args.input_events:
                break
        totals[sample] = {'input_events': total,
                          'files': sum(r['sample'] == sample for r in chosen)}
    campaign = args.campaign.resolve()
    campaign.mkdir(parents=True, exist_ok=False)
    for name in ('logs', 'jobs', 'status', 'plots'):
        (campaign / name).mkdir()
    pins = {str(p.relative_to(REPO)): sha(p)
            for p in (REPO / 'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for name in ('run_mass_sanity.py', 'validate_b0_inputs.py', 'validate_ttbb_matching.py'):
        pins['diagnostics/' + name] = sha(REPO / 'diagnostics' / name)
    campaign_data = {
        'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'bounded 2024 TT2Q and TTBB matched-jet mass sanity check; no mass cut',
        'processor_tag': 'b0-processor-20261028-v1',
        'processor_commit': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
        'processor_checkout': str(REPO), 'code_sha256': pins,
        'source_inventory': str(inventory_path), 'source_inventory_sha256': sha(inventory_path),
        'sampling': 'whole files ordered by SHA256(seed:id), stopping at input-event target per source',
        'seed': args.seed, 'input_events_target_per_source': args.input_events,
        'profile': 'b0', 'variation': 'nominal', 'chunk_size': 10000,
        'summary': totals, 'files': chosen,
    }
    write_json(campaign / 'campaign.json', campaign_data)
    wrapper = campaign / 'worker.sh'
    wrapper.write_text('\n'.join([
        '#!/bin/bash', 'set -euo pipefail',
        'export PATH=/usr/local/bin:/usr/bin:/bin',
        f'export X509_USER_PROXY={shlex.quote(str(PROXY))}',
        'export XrdSecPROTOCOL=gsi,unix XRD_NETWORKSTACK=IPv4',
        'export XRD_CONNECTIONWINDOW=30 XRD_REQUESTTIMEOUT=120',
        'export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1',
        'export XDG_CACHE_HOME="${_CONDOR_SCRATCH_DIR:-/tmp}/vcb-mass-$1-cache"',
        'export MPLCONFIGDIR="$XDG_CACHE_HOME/matplotlib"',
        f'export PYTHONPATH={shlex.quote(str(REPO / "src"))}',
        f'exec {shlex.quote(str(MAMBA))} run -p /isilon/export/home/jhuan166/micromamba/envs/ttbar python -u '
        f'{shlex.quote(str(Path(__file__).resolve()))} worker '
        f'--campaign {shlex.quote(str(campaign))} --id "$1"', '',
    ]))
    wrapper.chmod(0o755)
    (campaign / 'worker.sub').write_text('\n'.join([
        'universe = vanilla', 'getenv = false', 'should_transfer_files = NO',
        'use_x509userproxy = true', f'x509userproxy = {PROXY}',
        'request_cpus = 1', 'request_memory = 4G', 'request_disk = 2G',
        '+JobBatchName = "VCB_B0_MASS_SANITY_20261103"',
        f'initialdir = {campaign}', f'executable = {wrapper}',
        'arguments = $(pair)', f'log = {campaign}/logs/jobs.log',
        f'output = {campaign}/logs/$(pair).out', f'error = {campaign}/logs/$(pair).err',
        'queue 1', '',
    ]))
    dag = []
    for record in chosen:
        job = record['id']
        dag += [f'JOB {job} {campaign}/worker.sub', f'VARS {job} pair="{job}"', f'RETRY {job} 1']
    (campaign / 'skim.dag').write_text('\n'.join(dag) + '\n')
    print(json.dumps(totals, indent=2), flush=True)


def worker(args):
    from validate_b0_inputs import validate

    campaign = args.campaign.resolve()
    config = json.loads((campaign / 'campaign.json').read_text())
    for name, digest in config['code_sha256'].items():
        if sha(REPO / name) != digest:
            raise ValueError(f'Pinned code changed: {name}')
    record = next(r for r in config['files'] if r['id'] == args.id)
    manifest = Path(record['truth_manifest'])
    if sha(manifest) != record['truth_manifest_sha256']:
        raise ValueError('Truth manifest changed')
    start = time.monotonic()
    attempt = Path(tempfile.mkdtemp(prefix=args.id + '.', dir=campaign / 'jobs'))
    (attempt / 'outputs').mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix='vcb_mass_', dir=os.environ.get('_CONDOR_SCRATCH_DIR')) as scratch:
            nano = Path(record['nano_file'])
            if record['nano_file'].startswith('root://'):
                nano = Path(scratch) / 'nano.root'
                subprocess.run(['/usr/bin/xrdcp', '--force', '--nopbar', record['nano_file'], str(nano)],
                               check=True, timeout=900)
                checksum = 1
                with nano.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        checksum = zlib.adler32(block, checksum)
                if nano.stat().st_size != record['nano_bytes'] or f'{checksum:08x}' != record['nano_adler32']:
                    raise ValueError('Staged EOS NanoAOD size/checksum mismatch')
            elif (nano.stat().st_size != record['nano_bytes']
                  or nano.stat().st_mtime_ns != record['nano_mtime_ns']):
                raise ValueError('Local NanoAOD changed since inventory')
            command = [sys.executable, '-u', '-m', 'vcb.run', '--year', '2024',
                       '--files', str(nano), '--files-name',
                       'TTBB-TTtoLNu2Q' if record['sample'] == 'TTBB' else 'TTtoLNu2Q',
                       '--input-profile', 'b0', '--kinematic-variation', 'nominal',
                       '--truth-label-manifest', str(manifest), '--truth-label-manifest-sha256',
                       record['truth_manifest_sha256'], '--chunksize', '10000',
                       '--maxchunks', '0', '--batch-size', '9999', '--root-only',
                       '--no-save-systematics', '--naming-tag', record['id'], '--outdir', str(attempt)]
            with (attempt / 'skim.log').open('w') as log:
                subprocess.run(command, cwd=attempt, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=3600)
            roots = list(attempt.glob('nano_skim_*_batch_*.root'))
            if len(roots) != 1:
                raise ValueError(f'Expected one skim ROOT, found {len(roots)}')
            metadata = attempt / 'outfiles' / (record['id'] + '.kinematics.json')
            result = validate(nano, roots[0], metadata, manifest)
            if result['input_events'] != record['entries'] or result['input_uuid'] != record['nano_uuid']:
                raise ValueError('Unexpected input identity or coverage')
            result.update(id=record['id'], sample=record['sample'], state='complete',
                          original_nano=record['nano_file'], metadata=str(metadata),
                          command=command, elapsed_seconds=time.monotonic() - start,
                          completed_utc=datetime.now(timezone.utc).isoformat())
            write_json(campaign / 'status' / (record['id'] + '.json'), result)
            print(json.dumps({k: result[k] for k in ('id', 'state', 'input_events',
                             'selected_events', 'fully_matched', 'elapsed_seconds')}, indent=2))
    except Exception:
        write_json(attempt / 'failure.json', {'error': traceback.format_exc()})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--truth-campaign', required=True, type=Path)
    p.add_argument('--campaign', required=True, type=Path)
    p.add_argument('--input-events', type=int, default=200000)
    p.add_argument('--seed', default='20261103')
    p = sub.add_parser('worker')
    p.add_argument('--campaign', required=True, type=Path)
    p.add_argument('--id', required=True)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else worker)(args)

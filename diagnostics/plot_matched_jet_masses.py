"""Compare TT2Q/TTBB W and top masses from fully matched B0 reconstructed jets.

The four-vector sums follow NanoAOD-calib-studies/studies/hadronic-masses.py.
This reads the B0 slots directly, uses B0AssignmentMask, and applies no mass cut.
Plots are separately normalized shapes; they do not combine sample yields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib as mpl

mpl.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import uproot
import vector

ROLES = ('HadB', 'LepB', 'HadQ1', 'HadQ2')
PARTONS = ('GenHadTopB', 'GenLepTopB', 'GenQ1', 'GenQ2')
COLORS = {'TT2Q': '#2374b5', 'TTBB': '#d65a2e'}
LABELS = {'TT2Q': r'Inclusive $t\bar{t}$ (TT2Q)', 'TTBB': r'Dedicated $t\bar{t}b\bar{b}$'}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cartesian_mass(pt, eta, phi, mass, indices):
    """Independent Cartesian sum, with all components evaluated in float64."""
    rows = np.arange(len(pt))[:, None]
    p, e, f, m = [x[rows, indices] for x in (pt, eta, phi, mass)]
    px, py, pz = p * np.cos(f), p * np.sin(f), p * np.sinh(e)
    energy = np.sqrt((p * np.cosh(e))**2 + m**2)
    m2 = energy.sum(axis=1)**2 - sum(x.sum(axis=1)**2 for x in (px, py, pz))
    if np.any(m2 < -1e-6):
        raise ValueError('Negative invariant mass squared')
    return np.sqrt(np.maximum(m2, 0))


def read_skim(path):
    fields = ['B0AssignmentMask', 'GenWDecayValid', 'GenWDecay', 'GenNExtraBQuarks',
              'GenNExtraBQuarksValid', 'B0SourceEntry', 'weight', 'nJets',
              'run', 'luminosityBlock', 'event', 'GenHadWMass', 'GenHadTopIdx',
              'GenTopMass0', 'GenTopMass1']
    fields += [f'B0SourceUUID{i}' for i in range(4)]
    fields += [f'Gen{role}JetIdx' for role in ROLES]
    fields += [f'ak4Jet{v}{j}' for v in ('Pt', 'Eta', 'Phi', 'Mass') for j in range(10)]
    fields += [f'{p}{v}' for p in PARTONS for v in ('Eta', 'Phi')]
    with uproot.open(path) as source:
        a = source['Events'].arrays(fields, library='np')
    mask = a['B0AssignmentMask'].astype(bool)
    indices = np.column_stack([a[f'Gen{role}JetIdx'] for role in ROLES])
    independent = np.all((indices >= 0) & (indices < np.minimum(a['nJets'], 10)[:, None]), axis=1)
    independent &= np.all(np.diff(np.sort(indices, axis=1), axis=1) != 0, axis=1)
    np.testing.assert_array_equal(mask, independent & a['GenWDecayValid'])
    a = {k: v[mask] for k, v in a.items()}
    idx = indices[mask]
    pt, eta, phi, mass = [np.column_stack([a[f'ak4Jet{v}{i}'] for i in range(10)]).astype(np.float64)
                         for v in ('Pt', 'Eta', 'Phi', 'Mass')]
    rows = np.arange(len(idx))[:, None]
    if not (np.all(pt[rows, idx] > 25) and np.all(np.abs(eta[rows, idx]) < 2.4)):
        raise ValueError('Matched jet outside B0 acceptance')
    if not all(np.isfinite(x[rows, idx]).all() for x in (pt, eta, phi, mass)):
        raise ValueError('Non-finite matched four-vector')
    if np.any(mass[rows, idx] < 0):
        raise ValueError('Negative matched-jet mass')
    parton_eta, parton_phi = [np.column_stack([a[p+v] for p in PARTONS]).astype(np.float64)
                              for v in ('Eta', 'Phi')]
    dphi = (phi[rows, idx] - parton_phi + np.pi) % (2*np.pi) - np.pi
    dr = np.hypot(eta[rows, idx] - parton_eta, dphi)
    if not np.all(dr < 0.4):
        raise ValueError('Matched jet outside DeltaR cone')
    jets = vector.array({'pt': pt[rows, idx], 'eta': eta[rows, idx],
                         'phi': phi[rows, idx], 'mass': mass[rows, idx]})
    w = (jets[:, 2] + jets[:, 3]).mass
    top = (jets[:, 0] + jets[:, 2] + jets[:, 3]).mass
    independent_w = cartesian_mass(pt, eta, phi, mass, idx[:, [2, 3]])
    independent_top = cartesian_mass(pt, eta, phi, mass, idx[:, [0, 2, 3]])
    np.testing.assert_allclose(w, independent_w, rtol=1e-9, atol=1e-6)
    np.testing.assert_allclose(top, independent_top, rtol=1e-9, atol=1e-6)
    np.testing.assert_allclose(w, (jets[:, 3] + jets[:, 2]).mass, rtol=1e-12, atol=1e-9)
    if not np.isfinite(w).all() or not np.isfinite(top).all() or not np.isfinite(a['weight']).all():
        raise ValueError('Non-finite mass or nominal weight')
    gen_top_idx = a['GenHadTopIdx'].astype(int)
    if np.any((gen_top_idx < 0) | (gen_top_idx > 1)):
        raise ValueError('Invalid generator hadronic-top index')
    gen_top = np.column_stack([a['GenTopMass0'], a['GenTopMass1']])[np.arange(len(idx)), gen_top_idx]
    values = {'mW': w, 'mTop': top, 'gen_mW': a['GenHadWMass'], 'gen_mTop': gen_top,
              'nominal_weight': a['weight'].astype(np.float64), 'max_match_delta_r': dr.max(axis=1),
              'extra_b_count': a['GenNExtraBQuarks'], 'extra_b_valid': a['GenNExtraBQuarksValid'],
              'W_decay': a['GenWDecay'], 'source_entry': a['B0SourceEntry'],
              'source_uuid': np.column_stack([a[f'B0SourceUUID{i}'] for i in range(4)]),
              'run': a['run'], 'lumi': a['luminosityBlock'], 'event': a['event']}
    check = {'selected_events': len(mask), 'fully_matched': int(mask.sum()),
             'max_cartesian_difference_GeV': float(max(np.max(np.abs(w-independent_w), initial=0),
                                                      np.max(np.abs(top-independent_top), initial=0))),
             'max_match_delta_r': float(np.max(dr, initial=0)),
             'checks_passed': True}
    return values, check


def statistics(values, edges):
    counts, _ = np.histogram(values, edges)
    peak = int(np.argmax(counts))
    return {'events': len(values), 'mean_GeV': float(np.mean(values)),
            'std_GeV': float(np.std(values)),
            'quantiles_16_50_84_GeV': np.quantile(values, [.16, .5, .84]).tolist(),
            'highest_5GeV_bin': [float(edges[peak]), float(edges[peak+1])],
            'underflow': int(np.sum(values < edges[0])), 'overflow': int(np.sum(values > edges[-1]))}


def draw(samples, output, weighted=False):
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                         'savefig.dpi': 180, 'axes.labelsize': 12})
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.5))
    specs = [('mW', np.arange(0, 205, 5), 80.4, r'$m(j_{q_1}+j_{q_2})$ [GeV]', 'Hadronic W'),
             ('mTop', np.arange(50, 355, 5), 172.5, r'$m(j_{b_{had}}+j_{q_1}+j_{q_2})$ [GeV]', 'Hadronic top')]
    for ax, (key, edges, reference, label, title) in zip(axes, specs, strict=True):
        width = np.diff(edges)
        for sample, data in samples.items():
            weights = data['nominal_weight'] if weighted else np.ones(len(data[key]))
            normalization = weights.sum()
            if normalization <= 0:
                raise ValueError('Nonpositive signed shape normalization')
            counts, _ = np.histogram(data[key], edges, weights=weights)
            variance, _ = np.histogram(data[key], edges, weights=weights**2)
            density = counts / (normalization * width)
            err = np.sqrt(variance) / (normalization * width)
            centers = .5*(edges[1:]+edges[:-1])
            ax.stairs(density, edges, linewidth=1.9, color=COLORS[sample],
                      label=LABELS[sample] + f'  (N={len(weights):,})')
            ax.errorbar(centers, density, yerr=err, fmt='none', elinewidth=.65,
                        alpha=.65, color=COLORS[sample])
        ax.axvline(reference, color='#555555', linestyle='--', linewidth=1,
                   label=f'{reference:g} GeV reference')
        ax.set(xlabel=label, ylabel='Normalized events / GeV', title=title,
               xlim=(edges[0], edges[-1]))
        ax.set_ylim(bottom=0)
        ax.grid(axis='y', alpha=.15)
        ax.legend(frameon=False, fontsize=9, loc='upper right')
    weight_label = 'Nominal MC weights, signed' if weighted else 'Unweighted'
    fig.suptitle('2024 simulation: masses from truth-matched reconstructed jets', fontsize=15, y=.98)
    fig.text(.5, .895, r'B0: $p_T>25$ GeV, $|\eta|<2.4$, up to 10 jets; four distinct matches with $\Delta R<0.4$',
             ha='center', fontsize=10)
    fig.text(.5, .025, weight_label + '; each sample normalized separately; no mass-window cut. Error bars: MC statistical.',
             ha='center', fontsize=10, color='#444444')
    fig.subplots_adjust(left=.075, right=.985, bottom=.16, top=.81, wspace=.25)
    for ext in ('png', 'pdf'):
        fig.savefig(output.with_suffix('.'+ext))
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    config = json.loads((campaign/'campaign.json').read_text())
    parts = {'TT2Q': [], 'TTBB': []}
    reports = []
    schema_hashes, payloads = set(), set()
    for record in config['files']:
        path = campaign/'status'/(record['id']+'.json')
        status = json.loads(path.read_text())
        skim = Path(status['skim'])
        if (status['state'] != 'complete' or not status['passed']
                or sha(skim) != status['matching']['source_sha256']):
            raise ValueError('Missing validation or changed skim')
        metadata = json.loads(Path(status['metadata']).read_text())
        if metadata['input_profile'] != 'b0' or metadata['variation'] != 'nominal':
            raise ValueError('Unexpected selection profile or kinematic variation')
        schema_hashes.add(status['schema_sha256'])
        payloads.add(json.dumps(metadata['jet_payloads'], sort_keys=True))
        arrays, check = read_skim(skim)
        if check['fully_matched'] != status['fully_matched']:
            raise ValueError('Fully matched count changed')
        check.update(id=record['id'], sample=record['sample'], skim=str(skim),
                     input_events=record['entries'], source_lfn=record['source_lfn'])
        reports.append(check)
        parts[record['sample']].append(arrays)
    samples = {s: {k: np.concatenate([a[k] for a in arrays]) for k in arrays[0]}
               for s, arrays in parts.items()}
    if len(schema_hashes) != 1 or len(payloads) != 1:
        raise ValueError('Inconsistent B0 features or jet corrections between files')
    summary = {'processor_commit': config['processor_commit'], 'profile': 'b0',
               'campaign': str(campaign/'campaign.json'), 'campaign_sha256': sha(campaign/'campaign.json'),
               'plotter_sha256': sha(__file__), 'mass_window_selection': False,
               'reconstruction': 'mW = M(jHadQ1 + jHadQ2); mTop = M(jHadB + jHadQ1 + jHadQ2)',
               'selection': 'B0AssignmentMask; all four distinct real matches, including leptonic b',
               'nominal_weights': 'skim weight; separate signed normalization per source; no yields or stitching',
               'b0_schema_sha256': next(iter(schema_hashes)),
               'jet_payloads': json.loads(next(iter(payloads))),
               'source_files': reports, 'samples': {}}
    for sample, data in samples.items():
        identity = np.column_stack([data['source_uuid'].astype(np.uint64), data['source_entry']])
        if len(np.unique(identity, axis=0)) != len(identity):
            raise ValueError('Duplicated source event')
        np.savez_compressed(campaign/'plots'/(sample+'_matched_masses.npz'), **data)
        weights = data['nominal_weight']
        labels, numbers = np.unique(data['W_decay'], return_counts=True)
        summary['samples'][sample] = {
            'input_events': sum(x['input_events'] for x in reports if x['sample'] == sample),
            'selected_events': sum(x['selected_events'] for x in reports if x['sample'] == sample),
            'fully_matched_events': len(weights),
            'negative_weight_events': int(np.sum(weights < 0)),
            'signed_weight_sum': float(weights.sum()),
            'signed_effective_events': float(weights.sum()**2 / (weights**2).sum()),
            'unknown_extra_b_count': int(np.sum(~data['extra_b_valid'])),
            'W_decay_labels': {str(int(x)): int(n) for x, n in zip(labels, numbers, strict=True)},
            'mW': statistics(data['mW'], np.arange(0, 205, 5)),
            'mTop': statistics(data['mTop'], np.arange(50, 355, 5)),
            'gen_W_median_GeV': float(np.median(data['gen_mW'])),
            'gen_top_median_GeV': float(np.median(data['gen_mTop'])),
        }
    summary['integrity_checks_passed'] = True
    draw(samples, campaign/'plots/matched_jet_masses', weighted=False)
    draw(samples, campaign/'plots/matched_jet_masses_weighted', weighted=True)
    (campaign/'plots/summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary['samples'], indent=2))


if __name__ == '__main__':
    main()

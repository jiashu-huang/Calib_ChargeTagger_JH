"""Versioned event-truth definitions; dependency-free for CMSSW/FWLite use.

The extra-quark counter needs the complete b-quark record, including all mother
links. Ordinary NanoAOD GenPart does not meet that requirement. The supported
source is Pythia8 prunedGenParticles, whose MiniAOD pruning keeps all b quarks.
"""

from __future__ import annotations

from enum import IntEnum

TRUTH_LABEL_VERSION = 1
UNKNOWN = -1
FIRST_COPY = 1 << 12
LAST_COPY = 1 << 13
HARD_PROCESS = 1 << 7
FROM_HARD_PROCESS = 1 << 8


class CountStatus(IntEnum):
    VALID = 0
    INCOMPLETE_RECORD = 1
    INVALID_ANCESTRY = 2
    AMBIGUOUS_COPY_CHAIN = 3
    UNRESOLVED_TOP_DECAY = 4
    UNSUPPORTED_STATUS = 5


def count_extra_b_quarks(pdg_ids, statuses, flags, mothers, *, complete_record=False):
    """Return (exact count, CountStatus), with -1 for unknown.

    Count outgoing last-copy b/anti-b lines once, without pT, eta or jet cuts.
    Exclude the primary hard-process top/W b lines, following same-signed b
    copies. A first-copy b starts a new line even if pruning linked it to an
    older b ancestor across a removed gluon. This retains g->bb radiation in
    top decays. Multiple endpoints, broken links and missing primary top b
    lines are unknown, rather than a guessed count.
    """
    if not complete_record:
        return UNKNOWN, CountStatus.INCOMPLETE_RECORD
    n = len(pdg_ids)
    if any(len(values) != n for values in (statuses, flags, mothers)):
        raise ValueError("Generator arrays must have equal lengths")

    class InvalidRecord(Exception):
        def __init__(self, status):
            self.status = status

    def parents(index):
        values = mothers[index]
        if any(p < 0 or p >= n or p == index for p in values):
            raise InvalidRecord(CountStatus.INVALID_ANCESTRY)
        return set(values)

    roots = {}

    def first_copy(index):
        # Pythia status-73 entries can point to multiple earlier copies of the
        # SAME line. Resolve every path; multiplicity of references alone does
        # not make the physical origin ambiguous. Full cycles are checked below.
        pending = [(index, False)]
        while pending:
            current, resolving = pending.pop()
            if current in roots:
                continue
            if flags[current] & FIRST_COPY:
                roots[current] = current
                continue
            copies = [p for p in parents(current) if pdg_ids[p] == pdg_ids[current]]
            if not copies:
                raise InvalidRecord(CountStatus.AMBIGUOUS_COPY_CHAIN)
            if resolving:
                candidates = {roots[p] for p in copies}
                if len(candidates) != 1:
                    raise InvalidRecord(CountStatus.AMBIGUOUS_COPY_CHAIN)
                roots[current] = candidates.pop()
            else:
                pending.append((current, True))
                pending.extend((parent, False) for parent in copies)
        return roots[index]

    def incoming(index):
        # Pythia8 beam/initiator entries, not outgoing shower endpoints.
        return statuses[index] in (4, 11, 12, 13, 14, 21, 31, 34, 41, 42, 45, 46, 53, 54, 61)

    try:
        # Check full ancestry, including across gluons and first-copy boundaries.
        # Stopping this check at a first-copy flag would miss broken origins.
        done, active = set(), set()
        for start in range(n):
            if abs(pdg_ids[start]) not in (5, 6):
                continue
            stack = [(start, False)]
            while stack:
                index, leaving = stack.pop()
                if leaving:
                    active.remove(index)
                    done.add(index)
                elif index not in done:
                    if index in active:
                        raise InvalidRecord(CountStatus.INVALID_ANCESTRY)
                    active.add(index)
                    stack.append((index, True))
                    stack.extend((parent, False) for parent in parents(index))
        tops = [i for i in range(n) if abs(pdg_ids[i]) == 6
                and flags[i] & FROM_HARD_PROCESS and flags[i] & LAST_COPY]
        if len(tops) != 2 or sorted(pdg_ids[i] for i in tops) != [-6, 6]:
            return UNKNOWN, CountStatus.UNRESOLVED_TOP_DECAY
        top_roots = {first_copy(i) for i in tops}
        primary_top_lines = {i: set() for i in top_roots}
        excluded = set()
        endpoints = {}
        outgoing_roots = set()
        for i in range(n):
            if abs(pdg_ids[i]) != 5:
                continue
            root = first_copy(i)
            if not incoming(root):
                outgoing_roots.add(root)
            if flags[root] & HARD_PROCESS and flags[root] & FROM_HARD_PROCESS:
                ps = parents(root)
                if len(ps) == 1:
                    parent = next(iter(ps))
                    if abs(pdg_ids[parent]) == 6 and first_copy(parent) in top_roots:
                        top = first_copy(parent)
                        if pdg_ids[root] * pdg_ids[top] <= 0:
                            return UNKNOWN, CountStatus.UNRESOLVED_TOP_DECAY
                        primary_top_lines[top].add(root)
                        excluded.add(root)
                    elif abs(pdg_ids[parent]) == 24:
                        wp = parents(first_copy(parent))
                        if len(wp) == 1:
                            wt = next(iter(wp))
                            if abs(pdg_ids[wt]) == 6 and first_copy(wt) in top_roots:
                                excluded.add(root)
            if not flags[i] & LAST_COPY or incoming(i):
                continue
            # Supported outgoing Pythia8 partons, through pre-hadronization.
            if not (statuses[i] in (1, 2) or 22 <= statuses[i] <= 79):
                return UNKNOWN, CountStatus.UNSUPPORTED_STATUS
            if root in endpoints:
                return UNKNOWN, CountStatus.AMBIGUOUS_COPY_CHAIN
            endpoints[root] = i

        if any(len(lines) != 1 for lines in primary_top_lines.values()):
            return UNKNOWN, CountStatus.UNRESOLVED_TOP_DECAY
        if not (outgoing_roots | excluded) <= endpoints.keys():
            return UNKNOWN, CountStatus.AMBIGUOUS_COPY_CHAIN
        return len(endpoints.keys() - excluded), CountStatus.VALID
    except InvalidRecord as error:
        return UNKNOWN, error.status

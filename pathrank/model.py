"""Exact probe-count model of directory-major command resolution.

cmd.exe, PowerShell command discovery and Python's shutil.which all search the
same way: for each directory on PATH, in order, try the bare name with each
PATHEXT extension, in order, and stop at the first file that exists.  A
directory that does not hold the command therefore costs len(PATHEXT) failed
filesystem probes, which is why position on PATH dominates resolution latency.
"""

from __future__ import annotations


def resolve(inv, order, stem):
    """Return (dir index, ext rank) that answers `stem`, or None if unresolved."""
    where = inv.commands.get(stem)
    if not where:
        return None
    for d in order:
        if d in where:
            return d, min(where[d])
    return None


def resolved_path(inv, order, stem):
    """Absolute path the search lands on, normalised for comparison."""
    import os

    hit = resolve(inv, order, stem)
    if hit is None:
        return None
    d, rank = hit
    return os.path.normcase(os.path.join(inv.dirs[d].raw, stem + inv.exts[rank]))


def probes(inv, order, stem):
    """Filesystem existence probes performed while resolving `stem`."""
    where = inv.commands.get(stem)
    per_dir = len(inv.exts)
    count = 0
    for d in order:
        if where and d in where:
            return count + min(where[d]) + 1
        count += per_dir
    return count


def expected_probes(inv, order, weights) -> float:
    """Invocation-weighted mean probe count."""
    total = sum(weights.values())
    if total <= 0:
        return 0.0
    return sum(w * probes(inv, order, s) for s, w in weights.items()) / total


def winner_weights(inv, order, weights) -> dict:
    """Share of invocations that each directory answers."""
    out = {d: 0.0 for d in order}
    for stem, w in weights.items():
        hit = resolve(inv, order, stem)
        if hit is not None:
            out[hit[0]] = out.get(hit[0], 0.0) + w
    return out


def smith_bound(inv, order, weights) -> float:
    """Expected probes if directories could be ordered freely by weight.

    Dropping the shadowing constraints but keeping every command's answering
    directory fixed leaves a unit-time weighted-completion-time problem, which
    Smith's rule solves exactly.  The value is a valid lower bound for the
    constrained optimum.
    """
    w = winner_weights(inv, order, weights)
    free = sorted(order, key=lambda d: -w.get(d, 0.0))
    return expected_probes(inv, free, weights)

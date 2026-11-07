"""Check the exact solver against brute force on small random instances.

Sidney decomposition plus per-block dynamic programming is supposed to return a
minimum-cost order, not a good one.  For instances small enough to enumerate,
every feasible permutation is scored directly and compared.
"""

from __future__ import annotations

import itertools
import random
import sys

sys.path.insert(0, ".")

from pathrank import model, solve
from pathrank.inventory import Inventory, PathDir


def synthetic(rng, n_dirs, n_commands, n_exts=3):
    dirs = [PathDir(i, "D%d" % i, True, "key%d" % i, 1) for i in range(n_dirs)]
    exts = [".a", ".b", ".c"][:n_exts]
    commands, files = {}, {}
    for c in range(n_commands):
        stem = "cmd%d" % c
        k = rng.randint(1, min(3, n_dirs))
        where = rng.sample(range(n_dirs), k)
        commands[stem] = {d: frozenset({rng.randrange(n_exts)}) for d in where}
        files[stem + exts[0]] = frozenset(where)
    for d in range(n_dirs):
        files.setdefault("filler%d" % d, frozenset({d}))
    return Inventory(dirs=dirs, exts=exts, commands=commands, files=files)


def brute_force(inv, weights, edges, keep):
    best, best_order = None, None
    for perm in itertools.permutations(keep):
        pos = {d: i for i, d in enumerate(perm)}
        if any(pos[a] > pos[b] for a, b in edges if a in pos and b in pos):
            continue
        cost = model.expected_probes(inv, list(perm), weights)
        if best is None or cost < best - 1e-12:
            best, best_order = cost, perm
    return best, best_order


def run(trials=120, seed=11):
    rng = random.Random(seed)
    worst = 0.0
    for t in range(trials):
        n_dirs = rng.randint(2, 7)
        inv = synthetic(rng, n_dirs, rng.randint(1, 10))
        weights = {s: rng.randint(0, 20) for s in inv.commands}
        result = solve.solve(inv, weights, strict=True)
        reference, _ = brute_force(inv, weights, result.edges, result.reduction.keep)
        if reference is None:
            continue
        gap = result.expected_after - reference
        worst = max(worst, gap)
        assert result.optimal, "trial %d reported a non-exact block" % t
        assert gap < 1e-9, (
            "trial %d: solver %.6f, brute force %.6f" % (t, result.expected_after, reference)
        )
        assert result.expected_after >= result.bound - 1e-9, "bound is not a lower bound"
    print("%d random instances, solver matched brute force exactly "
          "(worst gap %.2e)" % (trials, worst))


if __name__ == "__main__":
    run()

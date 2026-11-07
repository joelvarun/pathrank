"""Exact minimisation of expected PATH probe cost under shadowing constraints.

Expected probes is len(PATHEXT) * sum_D w_D * position(D) plus a term that does
not depend on the order, where w_D is the share of invocations directory D
answers.  Keeping every command resolving to the same file means every
directory that currently wins a name must stay ahead of the other directories
holding that name, so the problem is exactly 1|prec|sum w_j C_j with unit
processing times.

Sidney decomposition splits that into blocks whose relative order is fixed in
some optimal schedule: repeatedly peel off the initial set of maximum density
w(S)/|S|, found exactly by maximum-weight closure (a min-cut) driven by
Dinkelbach iteration.  Each block is then ordered exactly by dynamic
programming over the ideals of its induced order, so the result is optimal, not
merely good.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

INF = float("inf")
DP_STATE_CAP = 400_000


# --------------------------------------------------------------------------- #
# max flow
# --------------------------------------------------------------------------- #
class _Dinic:
    def __init__(self, n):
        self.n = n
        self.to = []
        self.cap = []
        self.head = [[] for _ in range(n)]

    def add(self, u, v, c):
        self.head[u].append(len(self.to))
        self.to.append(v)
        self.cap.append(c)
        self.head[v].append(len(self.to))
        self.to.append(u)
        self.cap.append(0.0)

    def _levels(self, s, t):
        lvl = [-1] * self.n
        lvl[s] = 0
        q = collections.deque([s])
        while q:
            u = q.popleft()
            for e in self.head[u]:
                v = self.to[e]
                if self.cap[e] > 1e-12 and lvl[v] < 0:
                    lvl[v] = lvl[u] + 1
                    q.append(v)
        return lvl if lvl[t] >= 0 else None

    def _augment(self, u, t, lvl, it, limit):
        if u == t:
            return limit
        while it[u] < len(self.head[u]):
            e = self.head[u][it[u]]
            v = self.to[e]
            if self.cap[e] > 1e-12 and lvl[v] == lvl[u] + 1:
                got = self._augment(v, t, lvl, it, min(limit, self.cap[e]))
                if got > 1e-12:
                    self.cap[e] -= got
                    self.cap[e ^ 1] += got
                    return got
            it[u] += 1
        return 0.0

    def maxflow(self, s, t):
        total = 0.0
        while True:
            lvl = self._levels(s, t)
            if lvl is None:
                return total
            it = [0] * self.n
            while True:
                got = self._augment(s, t, lvl, it, INF)
                if got <= 1e-12:
                    break
                total += got

    def source_side(self, s):
        seen = {s}
        q = collections.deque([s])
        while q:
            u = q.popleft()
            for e in self.head[u]:
                v = self.to[e]
                if self.cap[e] > 1e-12 and v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen


def max_weight_closure(nodes, requires, weight):
    """Maximum-weight subset closed under `requires` (node -> nodes it needs)."""
    idx = {v: i for i, v in enumerate(nodes)}
    n = len(nodes)
    g = _Dinic(n + 2)
    s, t = n, n + 1
    positive = 0.0
    for v in nodes:
        p = weight(v)
        if p > 0:
            positive += p
            g.add(s, idx[v], p)
        elif p < 0:
            g.add(idx[v], t, -p)
    for v in nodes:
        for u in requires.get(v, ()):
            if u in idx:
                g.add(idx[v], idx[u], INF)
    value = positive - g.maxflow(s, t)
    side = g.source_side(s)
    chosen = [v for v in nodes if idx[v] in side]
    return value, chosen


def max_density_initial_set(nodes, requires, w):
    """Exact maximum-density initial set, by Dinkelbach on maximum closure."""
    best = None
    for v in nodes:
        closed = _closure_of(v, requires, set(nodes))
        density = sum(w.get(x, 0.0) for x in closed) / len(closed)
        if best is None or density > best[0]:
            best = (density, closed)
    lam, chosen = best
    for _ in range(64):
        value, cand = max_weight_closure(nodes, requires, lambda v: w.get(v, 0.0) - lam)
        if not cand or value <= 1e-9:
            break
        density = sum(w.get(x, 0.0) for x in cand) / len(cand)
        if density <= lam + 1e-12:
            break
        lam, chosen = density, set(cand)
    return lam, set(chosen)


def _closure_of(v, requires, universe):
    out, stack = set(), [v]
    while stack:
        u = stack.pop()
        if u in out or u not in universe:
            continue
        out.add(u)
        stack.extend(requires.get(u, ()))
    return out


# --------------------------------------------------------------------------- #
# exact ordering
# --------------------------------------------------------------------------- #
def order_block(block, requires, w):
    """Exact order for one Sidney block, by dynamic programming over ideals."""
    members = sorted(block)
    need = {v: frozenset(x for x in requires.get(v, ()) if x in block) for v in members}
    if len(members) == 1:
        return members, True
    if max(w.get(v, 0.0) for v in members) - min(w.get(v, 0.0) for v in members) < 1e-12:
        return topological(members, need), True

    memo = {}
    choice = {}
    budget = [DP_STATE_CAP]

    def best(placed):
        if len(placed) == len(members):
            return 0.0
        if placed in memo:
            return memo[placed]
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        position = len(placed) + 1
        top, pick = None, None
        for v in members:
            if v in placed or not need[v] <= placed:
                continue
            rest = best(placed | {v})
            if rest is None:
                return None
            total = w.get(v, 0.0) * position + rest
            if top is None or total < top - 1e-15:
                top, pick = total, v
        memo[placed] = top
        choice[placed] = pick
        return top

    if best(frozenset()) is None:
        return topological(members, need), False

    out, state = [], frozenset()
    while len(out) < len(members):
        v = choice[state]
        out.append(v)
        state = state | {v}
    return out, True


def topological(members, need):
    """Any feasible order: ties broken by descending weight is not needed here."""
    done, out = set(), []
    remaining = list(members)
    while remaining:
        for v in remaining:
            if need.get(v, frozenset()) <= done:
                out.append(v)
                done.add(v)
                remaining.remove(v)
                break
        else:
            out.extend(remaining)
            break
    return out


def sidney(nodes, requires, w):
    """Decompose into blocks of non-increasing density (Sidney 1975)."""
    left = set(nodes)
    blocks = []
    while left:
        sub = {v: set(x for x in requires.get(v, ()) if x in left) for v in left}
        density, chosen = max_density_initial_set(sorted(left), sub, w)
        if not chosen:
            chosen = set(left)
        blocks.append((density, chosen, sub))
        left -= chosen
    return blocks


# --------------------------------------------------------------------------- #
# safe reductions and shadowing constraints
# --------------------------------------------------------------------------- #
@dataclass
class Reduction:
    keep: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    empty: list = field(default_factory=list)
    duplicate: list = field(default_factory=list)

    @property
    def dropped(self):
        return self.missing + self.empty + self.duplicate


def reduce_path(inv) -> Reduction:
    """Drop entries that provably cannot change any resolution.

    An unreadable or file-free directory never answers a name, and a second
    spelling of a directory already earlier on PATH is always beaten by the
    first, so removing either only removes failed probes.
    """
    red = Reduction()
    seen = set()
    for d in range(inv.n):
        entry = inv.dirs[d]
        if not entry.exists:
            red.missing.append(d)
        elif entry.n_entries == 0:
            red.empty.append(d)
        elif entry.key in seen:
            red.duplicate.append(d)
        else:
            seen.add(entry.key)
            red.keep.append(d)
    return red


def precedence(inv, keep, strict=True):
    """Edges (a, b): a must stay ahead of b to preserve today's resolutions."""
    rank = {d: i for i, d in enumerate(keep)}
    edges = set()
    groups = [{d for d in where} for where in inv.commands.values()]
    if strict:
        groups += [set(dirs) for dirs in inv.files.values()]
    for dirs in groups:
        present = sorted((d for d in dirs if d in rank), key=rank.get)
        if len(present) < 2:
            continue
        winner = present[0]
        for d in present[1:]:
            edges.add((winner, d))
    return edges


@dataclass
class Result:
    order: list
    reduction: Reduction
    edges: set
    blocks: list
    optimal: bool
    expected_before: float
    expected_after: float
    bound: float

    @property
    def speedup(self):
        return self.expected_before / self.expected_after if self.expected_after else 0.0


def solve(inv, weights, strict=True):
    """Return a provably optimal PATH order that preserves every resolution."""
    from . import model

    red = reduce_path(inv)
    keep = red.keep
    edges = precedence(inv, keep, strict=strict)
    requires = {}
    for a, b in edges:
        requires.setdefault(b, set()).add(a)

    w = model.winner_weights(inv, keep, weights)
    blocks = sidney(keep, requires, w)

    order, optimal = [], True
    detail = []
    for density, chosen, sub in blocks:
        inner, exact = order_block(chosen, sub, w)
        optimal = optimal and exact
        order.extend(inner)
        detail.append((density, inner, exact))

    return Result(
        order=order,
        reduction=red,
        edges=edges,
        blocks=detail,
        optimal=optimal,
        expected_before=model.expected_probes(inv, inv.order(), weights),
        expected_after=model.expected_probes(inv, order, weights),
        bound=model.smith_bound(inv, keep, weights),
    )

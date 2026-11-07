"""Index every directory on PATH and every file those directories provide.

The index is the ground truth for both the cost model and the verifier: a
command resolves to the first (directory, PATHEXT extension) pair that exists,
scanned directory-major, so knowing which directories hold which names is
enough to predict and to check every resolution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"


@dataclass(frozen=True)
class PathDir:
    """One entry of PATH, as the shell sees it."""

    index: int
    raw: str
    exists: bool
    key: str
    n_entries: int


@dataclass
class Inventory:
    dirs: list
    exts: list
    commands: dict
    files: dict

    @property
    def n(self) -> int:
        return len(self.dirs)

    def order(self) -> list:
        return list(range(self.n))

    def path_value(self, order) -> str:
        return os.pathsep.join(self.dirs[i].raw for i in order)


def _entries(directory: str):
    """Return the file names directly inside `directory`, or None if unreadable."""
    try:
        with os.scandir(directory) as it:
            out = []
            for e in it:
                try:
                    if e.is_file():
                        out.append(e.name)
                except OSError:
                    continue
            return out
    except OSError:
        return None


def build(path_value: str = None, pathext_value: str = None) -> Inventory:
    """Index the given PATH (defaults to this process's environment)."""
    if path_value is None:
        path_value = os.environ.get("PATH", "")
    if pathext_value is None:
        pathext_value = os.environ.get("PATHEXT", DEFAULT_PATHEXT)

    exts = [e.lower() for e in pathext_value.split(";") if e.strip()]
    rank = {e: i for i, e in enumerate(exts)}

    dirs, commands, files = [], {}, {}
    raws = [p for p in path_value.split(os.pathsep) if p.strip()]
    for i, raw in enumerate(raws):
        listing = _entries(raw)
        exists = listing is not None
        listing = listing or []
        try:
            key = os.path.normcase(os.path.realpath(raw))
        except OSError:
            key = os.path.normcase(raw)
        dirs.append(PathDir(i, raw, exists, key, len(listing)))
        for name in listing:
            low = name.lower()
            files.setdefault(low, set()).add(i)
            stem, ext = os.path.splitext(low)
            if ext in rank:
                commands.setdefault(stem, {}).setdefault(i, set()).add(rank[ext])

    return Inventory(
        dirs=dirs,
        exts=exts,
        commands={s: {d: frozenset(r) for d, r in m.items()} for s, m in commands.items()},
        files={f: frozenset(d) for f, d in files.items()},
    )

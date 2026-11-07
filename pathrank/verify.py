"""Exhaustive proof that a reordered PATH resolves identically.

Three independent checks run over the whole name space, not a sample:

1. every command name resolves to the same physical file, extension included;
2. every file name present anywhere on PATH, DLLs and data files included,
   is still answered by the same physical directory;
3. the emitted order really does respect the shadowing constraints it claims.

A fourth check asks the operating system itself, through shutil.which under a
temporarily patched PATH, and compares its answer to the model's prediction.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

from . import model


@dataclass
class Report:
    commands_checked: int = 0
    files_checked: int = 0
    os_checked: int = 0
    mismatches: list = field(default_factory=list)
    constraint_violations: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches and not self.constraint_violations

    def summary(self) -> str:
        state = "PASS" if self.ok else "FAIL"
        return (
            f"{state}: {self.commands_checked} command names, "
            f"{self.files_checked} file names, "
            f"{self.os_checked} operating-system cross-checks, "
            f"{len(self.mismatches)} mismatches, "
            f"{len(self.constraint_violations)} constraint violations"
        )


def _first(order, dirs):
    for d in order:
        if d in dirs:
            return d
    return None


def _identity(inv, stem, hit):
    if hit is None:
        return None
    d, rank = hit
    return (inv.dirs[d].key, stem + inv.exts[rank])


def check(inv, new_order, edges=(), cross_check_os=True):
    """Compare every resolution under the current PATH and under `new_order`."""
    report = Report()
    old_order = inv.order()

    for stem in inv.commands:
        before = _identity(inv, stem, model.resolve(inv, old_order, stem))
        after = _identity(inv, stem, model.resolve(inv, new_order, stem))
        report.commands_checked += 1
        if before != after:
            report.mismatches.append(("command", stem, before, after))

    for name, dirs in inv.files.items():
        a = _first(old_order, dirs)
        b = _first(new_order, dirs)
        report.files_checked += 1
        ka = inv.dirs[a].key if a is not None else None
        kb = inv.dirs[b].key if b is not None else None
        if ka != kb:
            report.mismatches.append(("file", name, ka, kb))

    position = {d: i for i, d in enumerate(new_order)}
    for a, b in edges:
        if a in position and b in position and position[a] > position[b]:
            report.constraint_violations.append((a, b))

    if cross_check_os:
        report.os_checked = _ask_os(inv, new_order, report)
    return report


def _ask_os(inv, new_order, report):
    """Ask shutil.which under the reordered PATH and compare with the model."""
    saved = os.environ.get("PATH", "")
    checked = 0
    try:
        os.environ["PATH"] = inv.path_value(new_order)
        for stem in inv.commands:
            got = shutil.which(stem)
            predicted = model.resolved_path(inv, new_order, stem)
            checked += 1
            if got is None or predicted is None:
                if got is None and predicted is None:
                    continue
                report.mismatches.append(("os", stem, predicted, got))
                continue
            if os.path.normcase(os.path.realpath(got)) != os.path.normcase(
                os.path.realpath(predicted)
            ):
                report.mismatches.append(("os", stem, predicted, got))
    finally:
        os.environ["PATH"] = saved
    return checked

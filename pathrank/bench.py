"""Measure what PATH order costs in wall clock, and draw the comparison.

Timings are taken round-robin across configurations and reported as the minimum
over rounds, because filesystem metadata caching and background load on a
desktop drift over the span of a benchmark and a sequential A-then-B layout
attributes that drift to the configuration.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass

from . import model

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
SERIES = ("#2a78d6", "#eb6834")


def probe_order(inv, order, stem):
    """Resolve exactly as a shell does, touching the filesystem for real."""
    for d in order:
        base = inv.dirs[d].raw
        for ext in inv.exts:
            if os.path.exists(os.path.join(base, stem + ext)):
                return os.path.join(base, stem + ext)
    return None


def sample(weights, n, seed=20261107):
    names = sorted(weights)
    if not names:
        return []
    mass = [weights[k] for k in names]
    return random.Random(seed).choices(names, weights=mass, k=n)


@dataclass
class Timing:
    label: str
    ms_per_1000: float
    rounds: list


def time_orders(inv, orders, weights, n=240, rounds=7):
    """Round-robin timing of several PATH orders over one invocation sample."""
    workload = sample(weights, n)
    acc = {label: [] for label, _ in orders}
    for _ in range(rounds):
        for label, order in orders:
            start = time.perf_counter()
            for stem in workload:
                probe_order(inv, order, stem)
            acc[label].append((time.perf_counter() - start) * 1000.0 / n * 1000.0)
    return [Timing(label, min(acc[label]), acc[label]) for label, _ in orders]


def probe_cost_us(inv, trials=40000):
    """Mean cost of one failed existence probe, used to validate the model."""
    base = inv.dirs[0].raw
    start = time.perf_counter()
    for i in range(trials):
        os.path.exists(os.path.join(base, "pathrank_absent_%d.exe" % i))
    return (time.perf_counter() - start) * 1e6 / trials


def chart(path, expected, timings, bound, caption_values):
    """Write the before/after comparison figure."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["Current PATH", "pathrank order"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4), facecolor=SURFACE)
    fig.subplots_adjust(wspace=0.30, top=0.70, bottom=0.17, left=0.085, right=0.965)

    panels = [
        (axes[0], "Expected filesystem probes per command resolution", expected, "{:.1f}", bound),
        (axes[1], "Measured wall clock, ms per 1000 resolutions",
         [t.ms_per_1000 for t in timings], "{:.0f}", None),
    ]
    for ax, title, values, fmt, line in panels:
        ax.set_facecolor(SURFACE)
        ax.bar([0, 1], values, width=0.38, color=SERIES, zorder=3)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(labels, color=INK, fontsize=10.5)
        ax.set_title(title, color=INK_SOFT, fontsize=10.5, loc="left", pad=12)
        ax.grid(axis="y", color="#e7e6e2", linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#cfcec9")
        ax.tick_params(axis="y", colors=INK_SOFT, labelsize=9, length=0)
        ax.tick_params(axis="x", length=0)
        ax.set_xlim(-0.6, 1.6)
        top = max(values + ([line] if line else []))
        ax.set_ylim(0, top * 1.26)
        for x, value in zip([0, 1], values):
            ax.text(x, value + top * 0.04, fmt.format(value), ha="center",
                    color=INK, fontsize=13, fontweight="bold")
        if line:
            ax.axhline(line, color=INK_SOFT, linestyle=(0, (5, 4)), linewidth=1.3, zorder=4)
            ax.text(-0.56, line + top * 0.035,
                    "unconstrained bound %.1f" % line,
                    color=INK_SOFT, fontsize=9, va="bottom", ha="left")

    fig.text(0.085, 0.925,
             "Reordering PATH cuts Windows command resolution %.1fx"
             % (expected[0] / expected[1]),
             color=INK, fontsize=15, fontweight="bold")
    fig.text(0.085, 0.862,
             "%d PATH entries, %s real invocations read from this machine's shell history."
             % (caption_values["dirs"], caption_values["invocations"]),
             color=INK_SOFT, fontsize=10)
    fig.text(0.085, 0.812,
             "The order is provably optimal and changes nothing: %s command names and %s file "
             "names verified to resolve identically." % (caption_values["commands"],
                                                         caption_values["files"]),
             color=INK_SOFT, fontsize=10)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path

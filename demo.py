"""End to end run: index PATH, solve it exactly, prove it, measure it, chart it.

    python demo.py                 analyse this machine and write docs/before_after.png
    python demo.py --no-bench      skip the wall-clock measurement
    python demo.py --uniform       weight every resolvable command equally
"""

from __future__ import annotations

import argparse
import os
import sys

from pathrank import bench, inventory, model, solve, verify, workload

RULE = "-" * 78


def banner(text):
    print("\n" + RULE)
    print(text)
    print(RULE)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-bench", action="store_true", help="skip wall-clock timing")
    ap.add_argument("--uniform", action="store_true", help="ignore history, weight commands equally")
    ap.add_argument("--out", default=os.path.join("docs", "before_after.png"))
    ap.add_argument("--rounds", type=int, default=7)
    ap.add_argument("--samples", type=int, default=240)
    args = ap.parse_args(argv)

    banner("1. PATH inventory")
    inv = inventory.build()
    print(f"PATH entries          {inv.n}")
    print(f"PATHEXT extensions    {len(inv.exts)}  ({' '.join(inv.exts)})")
    print(f"resolvable commands   {len(inv.commands)}")
    print(f"distinct file names   {len(inv.files)}")
    shadowed = sum(1 for where in inv.commands.values() if len(where) > 1)
    print(f"commands present in more than one directory   {shadowed}")

    banner("2. Invocation workload")
    if args.uniform:
        weights, provenance = workload.uniform(inv), {"uniform": len(inv.commands)}
    else:
        weights, provenance = workload.collect(inv)
        if not weights:
            print("no history found, falling back to a uniform distribution")
            weights, provenance = workload.uniform(inv), {"uniform": len(inv.commands)}
    total = sum(weights.values())
    print(f"invocations           {total:,.0f} over {len(weights)} distinct commands")
    for source, count in sorted(provenance.items(), key=lambda kv: -kv[1]):
        print(f"  {source:22s} {count:,}")
    top = sorted(weights.items(), key=lambda kv: -kv[1])[:10]
    print("  most invoked:        " + ", ".join(f"{k} ({int(v)})" for k, v in top))

    banner("3. Exact solve, preserving every resolution")
    result = solve.solve(inv, weights, strict=True)
    red = result.reduction
    print(f"provably removable entries   missing {len(red.missing)}, "
          f"file free {len(red.empty)}, duplicate {len(red.duplicate)}")
    print(f"shadowing constraints        {len(result.edges)} precedence edges")
    print(f"Sidney blocks                {len(result.blocks)} "
          f"(largest {max(len(b[1]) for b in result.blocks)})")
    print(f"every block solved exactly   {result.optimal}")
    print(f"expected probes  before      {result.expected_before:.2f}")
    print(f"expected probes  after       {result.expected_after:.2f}")
    print(f"unconstrained lower bound    {result.bound:.2f}")
    print(f"reduction                    {result.speedup:.2f}x fewer probes")
    print("\nnew order, first eight entries:")
    for i, d in enumerate(result.order[:8]):
        print(f"  {i + 1:2d}. {inv.dirs[d].raw}")

    banner("4. Verification")
    report = verify.check(inv, result.order, result.edges, cross_check_os=True)
    print(report.summary())
    if not report.ok:
        for row in report.mismatches[:10]:
            print("  mismatch:", row)
        print("\nrefusing to recommend an order that changes a resolution")
        return 1

    banner("5. The unsafe shortcut, for comparison")
    loose = solve.solve(inv, weights, strict=False)
    loose_report = verify.check(inv, loose.order, loose.edges, cross_check_os=False)
    print(f"constraining executables only reaches {loose.expected_after:.2f} expected probes "
          f"({loose.expected_before / loose.expected_after:.2f}x)")
    print("but " + loose_report.summary())
    changed = [m for m in loose_report.mismatches if m[0] == "file"]
    if changed:
        print(f"it moves {len(changed)} non-executable resolutions, including:")
        for kind, name, before, after in changed[:5]:
            print(f"  {name}: {before} -> {after}")
        print("those are DLL and data files that processes load through PATH, so the")
        print("shortcut is rejected and the strict order above is the one reported")

    expected = [result.expected_before, result.expected_after]
    timings = None
    if not args.no_bench:
        banner("6. Measured cost")
        per_probe = bench.probe_cost_us(inv)
        print(f"one failed existence probe   {per_probe:.2f} us")
        predicted = result.expected_before * per_probe / 1000.0
        print(f"model prediction for current PATH   {predicted:.2f} ms per resolution")
        timings = bench.time_orders(
            inv,
            [("Current PATH", inv.order()), ("pathrank order", result.order)],
            weights,
            n=args.samples,
            rounds=args.rounds,
        )
        for t in timings:
            print(f"{t.label:16s} {t.ms_per_1000:9.1f} ms per 1000 resolutions "
                  f"(min of {len(t.rounds)}, worst {max(t.rounds):.1f})")
        measured = timings[0].ms_per_1000 / 1000.0
        print(f"measured current PATH               {measured:.2f} ms per resolution")
        print(f"model error                         {abs(measured - predicted) / measured * 100:.1f}%")
        print(f"wall-clock reduction                "
              f"{timings[0].ms_per_1000 / timings[1].ms_per_1000:.2f}x")

    if timings is None:
        timings = [bench.Timing("Current PATH", 0.0, [0.0]), bench.Timing("pathrank order", 0.0, [0.0])]

    banner("7. Chart")
    out = bench.chart(
        args.out,
        expected,
        timings,
        result.bound,
        {
            "dirs": inv.n,
            "invocations": f"{total:,.0f}",
            "commands": f"{report.commands_checked:,}",
            "files": f"{report.files_checked:,}",
        },
    )
    print(f"wrote {out}")

    banner("8. Recommended PATH")
    print("pathrank does not modify your environment. To try the order in one shell:\n")
    print("  $env:PATH = '" + inv.path_value(result.order) + "'")
    return 0


if __name__ == "__main__":
    sys.exit(main())

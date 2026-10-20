"""Placement experiments for research questions 1 and 3.

Q1: for each slowdown table (one per LLC replacement policy), compare
    cache-oblivious packing (first-fit, random) with cache-aware packing.
Q3 (--noise): the scheduler sees a distorted table (log-normal noise, or the
    coarse per-victim average) while jobs run with the true one.

Every configuration is repeated over several seeds; results.csv has one row per
run and summary.csv has the mean and a 95% confidence interval.

Usage:
  python experiments/run_placement.py --slowdown results/slowdown_lru.csv results/slowdown_ship.csv --out results/q1
  python experiments/run_placement.py --slowdown results/slowdown_lru.csv --noise 0 0.25 0.5 1.0 coarse --out results/q3
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from placement import first_fit, make_cache_aware, make_random, simulate, spread  # noqa: E402
from placement.workload import absolute_table, coarse_table, load_table, noisy_table, poisson_jobs, types_of  # noqa: E402

METRICS = ["mean_slowdown", "p95_slowdown", "max_slowdown", "frac_over_target", "mean_wait", "mean_busy_sockets"]


def schedulers(seed: int, threshold: float):
    return {
        "first_fit": first_fit,
        "random": make_random(seed),
        # same consolidation as first-fit, only the choice of neighbour differs (fair comparison)
        "cache_aware_pack": make_cache_aware(float("inf")),
        # may open an extra socket to avoid a bad neighbour (trades sockets for speed)
        "cache_aware": make_cache_aware(threshold),
        "spread": spread,
    }


def ci95(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    return 1.96 * statistics.stdev(xs) / len(xs) ** 0.5


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slowdown", nargs="+", type=Path, default=[], help="per-policy slowdown tables (relative to each policy's own solo run)")
    ap.add_argument("--absolute", type=Path, help="runs.csv: compare policies in absolute time against LRU's solo speed")
    ap.add_argument("--policies", nargs="+", default=["lru", "ship"], help="policies to use with --absolute")
    ap.add_argument("--loads", nargs="+", type=float, default=[0.5, 0.7, 0.9])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--sockets", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=3000, help="jobs per run")
    ap.add_argument("--threshold", type=float, default=0.10, help="cache_aware opens a new socket above this pair cost")
    ap.add_argument("--target", type=float, default=1.10, help="slowdown target for frac_over_target")
    ap.add_argument("--noise", nargs="*", default=None, help="Q3 mode: noise levels (floats) and/or 'coarse'")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if args.absolute:
        tables = [(p, absolute_table(args.absolute, p)) for p in args.policies]
    elif args.slowdown:
        tables = [(path.stem.replace("slowdown_", ""), load_table(path)) for path in args.slowdown]
    else:
        ap.error("give --slowdown tables or --absolute runs.csv")

    rows = []
    for policy, true in tables:
        types = types_of(true)
        for load in args.loads:
            for seed in range(args.seeds):
                if args.noise is None:
                    variants = [(name, sched, None, "exact") for name, sched in schedulers(seed, args.threshold).items()]
                else:
                    variants = [("first_fit", first_fit, None, "exact")]
                    for lvl in args.noise:
                        est = coarse_table(true) if lvl == "coarse" else noisy_table(true, float(lvl), seed + 1000)
                        variants.append(("cache_aware", make_cache_aware(args.threshold), est, str(lvl)))
                for name, sched, est, info in variants:
                    jobs = poisson_jobs(types, args.jobs, args.sockets, load, seed)
                    res = simulate(jobs, args.sockets, true, sched, est)
                    rows.append({"policy": policy, "load": load, "seed": seed, "scheduler": name,
                                 "estimate": info, **res.summary(args.target)})
        print(f"done {policy}", flush=True)

    with open(args.out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["policy"], r["load"], r["scheduler"], r["estimate"]), []).append(r)
    summary = []
    for (policy, load, sched, est), rs in sorted(groups.items()):
        s = {"policy": policy, "load": load, "scheduler": sched, "estimate": est, "runs": len(rs)}
        for m in METRICS:
            vals = [r[m] for r in rs]
            s[m] = round(statistics.mean(vals), 4)
            s[m + "_ci95"] = round(ci95(vals), 4)
        summary.append(s)
    with open(args.out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)

    print(f"\n{'policy':8} {'load':>4} {'scheduler':12} {'estimate':8} {'mean sd':>8} {'p95 sd':>8} {'>target':>8} {'sockets':>8}")
    for s in summary:
        print(f"{s['policy']:8} {s['load']:>4} {s['scheduler']:12} {s['estimate']:8} {s['mean_slowdown']:8.3f} "
              f"{s['p95_slowdown']:8.3f} {s['frac_over_target']:8.3f} {s['mean_busy_sockets']:8.1f}")
    print(f"\nwrote {args.out / 'results.csv'} and {args.out / 'summary.csv'}")


if __name__ == "__main__":
    main()

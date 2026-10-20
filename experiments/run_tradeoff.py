"""Speed vs servers: sweep cache_aware's threshold finely.

A threshold of t means: open a new socket only if every available neighbour
would add more than t total slowdown. t = inf never opens one (= cache_aware_pack).
Each point is compared with first_fit on the same job stream (paired per seed).

Usage: python experiments/run_tradeoff.py --slowdown results/slowdown_lru.csv results/slowdown_ship.csv --out results/tradeoff
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from placement import first_fit, make_cache_aware, simulate, spread  # noqa: E402
from placement.workload import load_table, poisson_jobs, types_of  # noqa: E402

THRESHOLDS = [0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, math.inf]


def one(task):
    path, policy, load, seed, sockets, n_jobs = task
    table = load_table(Path(path))
    types = types_of(table)
    rows = []
    base = simulate(poisson_jobs(types, n_jobs, sockets, load, seed), sockets, table, first_fit).summary()
    variants = [("first_fit", None, first_fit), ("spread", None, spread)]
    variants += [("cache_aware", t, make_cache_aware(t)) for t in THRESHOLDS]
    for name, t, sched in variants:
        s = base if name == "first_fit" else simulate(poisson_jobs(types, n_jobs, sockets, load, seed), sockets, table, sched).summary()
        rows.append({"policy": policy, "load": load, "seed": seed, "scheduler": name,
                     "threshold": "" if t is None else t, "p95": s["p95_slowdown"], "mean": s["mean_slowdown"],
                     "sockets": s["mean_busy_sockets"], "p95_saved": base["p95_slowdown"] - s["p95_slowdown"],
                     "extra_sockets_pct": 100 * (s["mean_busy_sockets"] / base["mean_busy_sockets"] - 1)})
    return rows


def ci95(xs):
    return 1.96 * statistics.stdev(xs) / len(xs) ** 0.5 if len(xs) > 1 else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slowdown", nargs="+", type=Path, required=True)
    ap.add_argument("--loads", nargs="+", type=float, default=[0.5, 0.6])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--sockets", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    tasks = [(str(p), p.stem.replace("slowdown_", ""), ld, s, args.sockets, args.jobs)
             for p in args.slowdown for ld in args.loads for s in range(args.seeds)]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = [r for chunk in ex.map(one, tasks) for r in chunk]
    with open(args.out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    groups = {}
    for r in rows:
        groups.setdefault((r["policy"], r["load"], r["scheduler"], str(r["threshold"])), []).append(r)
    summary = []
    for (policy, load, sched, t), rs in groups.items():
        row = {"policy": policy, "load": load, "scheduler": sched, "threshold": t}
        for m in ["p95", "mean", "sockets", "p95_saved", "extra_sockets_pct"]:
            xs = [r[m] for r in rs]
            row[m] = round(statistics.mean(xs), 4)
            row[m + "_ci95"] = round(ci95(xs), 4)
        summary.append(row)
    with open(args.out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    print(f"{'policy':6} {'load':>4} {'scheduler':12} {'thr':>5} {'p95':>6} {'saved':>13} {'+sockets':>12}")
    for s in summary:
        print(f"{s['policy']:6} {s['load']:>4} {s['scheduler']:12} {s['threshold']:>5} {s['p95']:6.3f} "
              f"{s['p95_saved']:6.3f}±{s['p95_saved_ci95']:.3f} {s['extra_sockets_pct']:6.1f}±{s['extra_sockets_pct_ci95']:.1f}%")


if __name__ == "__main__":
    main()

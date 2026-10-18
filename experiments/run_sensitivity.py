"""Sensitivity tests: do the main findings depend on arbitrary modelling choices?

Three sweeps, each at 50% and 60% load, for every slowdown table given, with
the baseline settings (threshold 0.10, uniform mix, 50 sockets) except the one
being varied:

  threshold  cache_aware's "open a new socket" threshold: 0.05 0.10 0.20 0.30 0.50
  mix        uniform | cache-heavy (mcf, omnetpp, gcc x3) | streaming-heavy (lbm x3)
  sockets    20 | 50 | 200 (jobs per run scale with the cluster)

Every row compares first_fit, cache_aware_pack and cache_aware on the same job
stream, so differences are paired per seed.

Usage: python experiments/run_sensitivity.py --slowdown results/slowdown_lru.csv results/slowdown_ship.csv --out results/sensitivity
"""
import argparse
import csv
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from placement import first_fit, make_cache_aware, simulate  # noqa: E402
from placement.workload import load_table, poisson_jobs, types_of  # noqa: E402

MIXES = {
    "uniform": None,
    "cache-heavy": {"mcf": 3, "omnetpp": 3, "gcc": 3, "xalancbmk": 1, "lbm": 1, "leela": 1},
    "streaming-heavy": {"mcf": 1, "omnetpp": 1, "gcc": 1, "xalancbmk": 1, "lbm": 3, "leela": 1},
}
BASE = {"threshold": 0.10, "mix": "uniform", "sockets": 50}
SWEEPS = {
    "threshold": [0.05, 0.10, 0.20, 0.30, 0.50],
    "mix": list(MIXES),
    "sockets": [20, 50, 200],
}


def one(task):
    path, policy, sweep, value, load, seed, jobs_per_socket = task
    cfg = dict(BASE, **{sweep: value})
    table = load_table(Path(path))
    n_jobs = jobs_per_socket * cfg["sockets"]
    out = {"policy": policy, "sweep": sweep, "value": value, "load": load, "seed": seed}
    for name, sched in [("first_fit", first_fit), ("cache_aware_pack", make_cache_aware(float("inf"))),
                        ("cache_aware", make_cache_aware(cfg["threshold"]))]:
        jobs = poisson_jobs(types_of(table), n_jobs, cfg["sockets"], load, seed, weights=MIXES[cfg["mix"]])
        s = simulate(jobs, cfg["sockets"], table, sched).summary()
        out[f"{name}_p95"] = s["p95_slowdown"]
        out[f"{name}_sockets"] = s["mean_busy_sockets"]
    return out


def ci95(xs):
    return 1.96 * statistics.stdev(xs) / len(xs) ** 0.5 if len(xs) > 1 else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slowdown", nargs="+", type=Path, required=True)
    ap.add_argument("--loads", nargs="+", type=float, default=[0.5, 0.6])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--jobs-per-socket", type=int, default=60)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    tasks = [(str(p), p.stem.replace("slowdown_", ""), sweep, v, ld, seed, args.jobs_per_socket)
             for p in args.slowdown for sweep, vals in SWEEPS.items() for v in vals
             for ld in args.loads for seed in range(args.seeds)]
    print(f"{len(tasks)} runs", flush=True)
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(one, tasks, chunksize=4))

    with open(args.out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    groups = {}
    for r in rows:
        groups.setdefault((r["sweep"], str(r["value"]), r["policy"], r["load"]), []).append(r)
    summary = []
    for (sweep, value, policy, load), rs in groups.items():
        pack = [r["first_fit_p95"] - r["cache_aware_pack_p95"] for r in rs]
        aware = [r["first_fit_p95"] - r["cache_aware_p95"] for r in rs]
        extra = [r["cache_aware_sockets"] / r["first_fit_sockets"] - 1 for r in rs]
        summary.append({
            "sweep": sweep, "value": value, "policy": policy, "load": load, "runs": len(rs),
            "first_fit_p95": round(statistics.mean(r["first_fit_p95"] for r in rs), 4),
            "pack_benefit": round(statistics.mean(pack), 4), "pack_benefit_ci95": round(ci95(pack), 4),
            "aware_benefit": round(statistics.mean(aware), 4), "aware_benefit_ci95": round(ci95(aware), 4),
            "aware_extra_sockets_pct": round(100 * statistics.mean(extra), 1),
        })
    order = {s: i for i, s in enumerate(SWEEPS)}
    summary.sort(key=lambda s: (order[s["sweep"]], s["policy"], s["load"], SWEEPS[s["sweep"]].index(
        type(SWEEPS[s["sweep"]][0])(s["value"]) if s["sweep"] != "mix" else s["value"])))
    with open(args.out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    print(f"{'sweep':9} {'value':16} {'policy':6} {'load':>4} {'FF p95':>7} {'pack':>13} {'aware':>13} {'+sockets':>8}")
    for s in summary:
        print(f"{s['sweep']:9} {s['value']:16} {s['policy']:6} {s['load']:>4} {s['first_fit_p95']:7.3f} "
              f"{s['pack_benefit']:6.3f}±{s['pack_benefit_ci95']:.3f} {s['aware_benefit']:6.3f}±{s['aware_benefit_ci95']:.3f} "
              f"{s['aware_extra_sockets_pct']:7.1f}%")


if __name__ == "__main__":
    main()

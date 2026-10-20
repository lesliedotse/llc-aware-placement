"""Run every workload alone and every pair together, then build slowdown tables.

For each replacement policy P:
  solo:  champsim_P_1core  <trace A>              -> IPC_solo(A)
  pair:  champsim_P_2core  <trace A> <trace B>    -> IPC_shared(A | B), IPC_shared(B | A)
  slowdown(A | B) = IPC_solo(A) / IPC_shared(A | B)      (1.0 = no interference)

Outputs:
  results/raw/<policy>/<run>.txt          full ChampSim output, kept for checking
  results/runs.csv                        one row per core per run
  results/slowdown_<policy>.csv           columns: victim, neighbor, slowdown

Runs already present in results/raw are reused, so the script can be stopped
and restarted.

Usage: python experiments/run_corun.py [--policies lru ship] [--jobs 4] [--dry-run]
       python experiments/run_corun.py --spec config/workloads_window2.json --results results/window2
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from champsim_output import parse_roi  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def plan_runs(spec: dict, policies: list[str]) -> list[dict]:
    names = [w["name"] for w in spec["workloads"]]
    runs = []
    for p in policies:
        for a in names:
            runs.append({"policy": p, "workloads": [a]})
        for a, b in itertools.combinations_with_replacement(names, 2):
            runs.append({"policy": p, "workloads": [a, b]})
    return runs


def run_one(run: dict, spec: dict, champsim_bin: Path, trace_dir: Path, raw_dir: Path, dry: bool, suffix: str = "") -> Path:
    traces = {w["name"]: w["trace"] for w in spec["workloads"]}
    tag = "__".join(run["workloads"])
    out = raw_dir / run["policy"] / f"{tag}.txt"
    if out.exists() and "Region of Interest Statistics" in out.read_text(errors="ignore"):
        return out
    exe = champsim_bin / f"champsim_{run['policy']}_{len(run['workloads'])}core{suffix}"
    cmd = [str(exe), "--warmup-instructions", str(spec["warmup_instructions"]),
           "--simulation-instructions", str(spec["simulation_instructions"]), "--hide-heartbeat"]
    cmd += [str(trace_dir / traces[w]) for w in run["workloads"]]
    if dry:
        print(" ".join(cmd))
        return out
    missing = [p for p in [exe] + [trace_dir / traces[w] for w in run["workloads"]] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"missing {missing}; run scripts/setup_champsim.sh and scripts/download_traces.sh first")
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"running {run['policy']}: {tag}", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{tag} ({run['policy']}) failed:\n{res.stderr[-2000:]}")
    out.write_text(res.stdout)
    return out


def build_tables(spec: dict, policies: list[str], raw_dir: Path, results: Path) -> None:
    names = [w["name"] for w in spec["workloads"]]
    rows = []
    for p in policies:
        solo = {}
        for a in names:
            core = parse_roi((raw_dir / p / f"{a}.txt").read_text())[0]
            solo[a] = core["ipc"]
            rows.append({"policy": p, "run": a, "core": 0, "workload": a, "neighbor": "", **core})
        table = []
        for a, b in itertools.combinations_with_replacement(names, 2):
            cores = parse_roi((raw_dir / p / f"{a}__{b}.txt").read_text())
            for idx, (me, other) in enumerate(((a, b), (b, a))):
                c = cores[idx]
                rows.append({"policy": p, "run": f"{a}__{b}", "core": idx, "workload": me, "neighbor": other, **c})
                table.append({"victim": me, "neighbor": other, "slowdown": solo[me] / c["ipc"]})
        # a self-pair produces two rows for the same (victim, neighbor); average them
        merged: dict[tuple[str, str], list[float]] = {}
        for r in table:
            merged.setdefault((r["victim"], r["neighbor"]), []).append(r["slowdown"])
        with open(results / f"slowdown_{p}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["victim", "neighbor", "slowdown"])
            for (v, n), vals in sorted(merged.items()):
                w.writerow([v, n, f"{sum(vals) / len(vals):.4f}"])
        print(f"wrote {results / f'slowdown_{p}.csv'}")
    with open(results / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policies", nargs="+", default=["lru", "ship"])
    ap.add_argument("--jobs", type=int, default=4, help="simulations to run in parallel")
    ap.add_argument("--champsim-bin", type=Path, default=ROOT / "champsim" / "bin")
    ap.add_argument("--traces", type=Path, default=ROOT / "traces")
    ap.add_argument("--results", type=Path, default=ROOT / "results")
    ap.add_argument("--spec", type=Path, default=ROOT / "config" / "workloads.json", help="workload list (e.g. config/workloads_window2.json)")
    ap.add_argument("--binary-suffix", default="", help='e.g. "_pf" for the prefetcher-enabled binaries')
    ap.add_argument("--dry-run", action="store_true", help="print the commands only")
    args = ap.parse_args()

    spec = json.loads(args.spec.read_text())
    raw_dir = args.results / "raw"
    runs = plan_runs(spec, args.policies)
    print(f"{len(runs)} runs planned for policies {args.policies}")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(lambda r: run_one(r, spec, args.champsim_bin, args.traces, raw_dir, args.dry_run, args.binary_suffix), runs))
    if not args.dry_run:
        build_tables(spec, args.policies, raw_dir, args.results)


if __name__ == "__main__":
    main()

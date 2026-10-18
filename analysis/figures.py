"""Paper figures from the measured ChampSim tables and the placement experiments.

  fig1_slowdown_tables.png   measured co-run slowdowns, LRU and SHiP
  fig2_benefit_vs_load.png   how much cache-aware placement cuts p95 slowdown, by load
  fig3_tradeoff.png          p95 slowdown vs servers used at 50% load (absolute time)
  fig4_robustness.png        cache-aware placement with wrong slowdown estimates
  key_numbers.csv            the numbers quoted in the write-up

Confidence intervals are 95% intervals over seeds. Benefits are PAIRED: each
seed gives every scheduler the same job stream, so the interval is computed on
the per-seed difference.

Usage: python analysis/figures.py [results_dir]
"""
import csv
import math
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

RES = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "results"
OUT = RES / "figures"
# categorical slots 1-4 of the validated palette; each policy keeps its color in every figure
COLOR = {"lru": "#2a78d6", "ship": "#eb6834", "srrip": "#1baf7a", "drrip": "#eda100"}
POLICY_ORDER = ["lru", "srrip", "drrip", "ship"]
LABEL = {"lru": "LRU", "srrip": "SRRIP", "drrip": "DRRIP", "ship": "SHiP"}
ORDER = ["mcf", "omnetpp", "gcc", "xalancbmk", "lbm", "leela"]  # most to least cache-hungry
INK, MUTED = "#0b0b0b", "#52514e"

plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlesize": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 200})


def read(path: Path) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def ci95(xs: list[float]) -> float:
    return 1.96 * statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0


def paired(rows, policy, load, a, b, metric="p95_slowdown", estimate="exact"):
    """Mean and CI of (scheduler a minus scheduler b) over seeds."""
    by = {}
    for r in rows:
        if r["policy"] == policy and float(r["load"]) == load and r["estimate"] == estimate:
            by.setdefault(int(r["seed"]), {})[r["scheduler"]] = float(r[metric])
    d = [v[a] - v[b] for v in by.values() if a in v and b in v]
    return statistics.mean(d), ci95(d)


def mean_ci(rows, metric, **match):
    xs = [float(r[metric]) for r in rows if all(str(r[k]) == str(v) for k, v in match.items())]
    return statistics.mean(xs), ci95(xs)


def fig1():
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.7), constrained_layout=True)
    norm = LogNorm(vmin=1.0, vmax=3.5)
    for ax, p in zip(axes, ["lru", "ship"]):
        t = {(r["victim"], r["neighbor"]): float(r["slowdown"]) for r in read(RES / f"slowdown_{p}.csv")}
        grid = [[t[(v, n)] for n in ORDER] for v in ORDER]
        im = ax.imshow(grid, cmap="Blues", norm=norm)
        for i, v in enumerate(ORDER):
            for j, n in enumerate(ORDER):
                val = t[(v, n)]
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7.5,
                        color="white" if val > 1.8 else INK)
        ax.set_xticks(range(6), ORDER, rotation=35, ha="right")
        ax.set_yticks(range(6), ORDER)
        ax.set_xlabel("neighbor on the same chip")
        ax.set_title(f"{LABEL[p]} last-level cache", loc="left")
        ax.spines[:].set_visible(False)
    axes[0].set_ylabel("program being slowed down")
    cb = fig.colorbar(im, ax=axes, shrink=0.8, ticks=[1, 1.5, 2, 3])
    cb.ax.set_yticklabels(["1.0×", "1.5×", "2×", "3×"])
    cb.set_label("slowdown vs running alone")
    fig.suptitle("Measured slowdown when two programs share a 2 MB cache (ChampSim)", x=0.02, ha="left", fontsize=10.5)
    fig.savefig(OUT / "fig1_slowdown_tables.png")


def fig2(key):
    rows = read(RES / "q1" / "results.csv")
    loads = sorted({float(r["load"]) for r in rows})
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.4), sharey=True, constrained_layout=True)
    panels = [("cache_aware_pack", "Same number of servers as first-fit"),
              ("cache_aware", "May use extra servers (threshold 0.10)")]
    present = [p for p in POLICY_ORDER if any(r["policy"] == p for r in rows)]
    for ax, (sched, title) in zip(axes, panels):
        for p in present:
            m, c = zip(*[paired(rows, p, ld, "first_fit", sched) for ld in loads])
            ax.plot(loads, m, color=COLOR[p], lw=2, marker="o", ms=4, label=LABEL[p])
            ax.fill_between(loads, [a - b for a, b in zip(m, c)], [a + b for a, b in zip(m, c)],
                            color=COLOR[p], alpha=0.15, lw=0)
            for ld, mm, cc in zip(loads, m, c):
                key.append({"figure": "fig2", "policy": p, "scheduler": sched, "load": ld,
                            "metric": "p95 slowdown reduction vs first_fit", "value": round(mm, 4), "ci95": round(cc, 4)})
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_title(title, loc="left")
        ax.set_xlabel("offered load (share of cores busy)")
        ax.set_xticks(loads, [f"{ld:.0%}" for ld in loads])
        ax.grid(axis="y", color="#e6e5e0", lw=0.6)
    axes[0].set_ylabel("p95 slowdown saved vs first-fit\n(higher = cache-aware helps more)")
    axes[1].legend(title="replacement policy", frameon=False, loc="upper right")
    fig.suptitle(f"Benefit of cache-aware placement, by LLC policy ({len(present)} policies, 95% CI, 10 seeds)", x=0.02, ha="left", fontsize=10.5)
    fig.savefig(OUT / "fig2_benefit_vs_load.png")


def fig3(key, load=0.5):
    rows = read(RES / "q1_absolute" / "results.csv")
    names = {"first_fit": "first-fit", "random": "random", "cache_aware_pack": "cache-aware\n(pack)",
             "cache_aware": "cache-aware", "spread": "spread"}
    fig, ax = plt.subplots(figsize=(6.2, 3.8), constrained_layout=True)
    for p in ["lru", "ship"]:
        for s, nm in names.items():
            x, xc = mean_ci(rows, "mean_busy_sockets", policy=p, load=load, scheduler=s, estimate="exact")
            y, yc = mean_ci(rows, "p95_slowdown", policy=p, load=load, scheduler=s, estimate="exact")
            ax.errorbar(x, y, xerr=xc, yerr=yc, fmt="o", ms=7, color=COLOR[p], mec="white", mew=1.5,
                        label=LABEL[p] if s == "first_fit" else None)
            if p == "lru" and s in ("cache_aware", "spread"):
                ax.annotate(nm, (x, y), xytext=(10, 6), textcoords="offset points", fontsize=8, color=MUTED)
            key.append({"figure": "fig3", "policy": p, "scheduler": s, "load": load,
                        "metric": "p95 job time vs LRU-alone / busy servers", "value": f"{y:.4f} / {x:.2f}", "ci95": f"{yc:.4f} / {xc:.2f}"})
    ax.annotate("first-fit, random and\ncache-aware (pack):\nsame servers, ~3-4% apart", (30.2, 1.62),
                fontsize=8, color=MUTED, va="center")
    ax.set_xlabel("average servers (sockets) in use, of 50")
    ax.set_ylabel("p95 job time\n(1.0 = running alone under LRU)")
    ax.grid(color="#e6e5e0", lw=0.6)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color=COLOR[p], mec="white", ms=8, label=LABEL[p]) for p in ["lru", "ship"]],
              title="replacement policy", frameon=False)
    ax.set_title(f"Speed vs servers used at {load:.0%} load (lower-left is better)", loc="left")
    fig.savefig(OUT / "fig3_tradeoff.png")


def fig4(key, load=0.5):
    rows = read(RES / "q3" / "results.csv")
    levels = [("0", "exact"), ("0.25", "noise σ=0.25"), ("0.5", "noise σ=0.5"), ("1.0", "noise σ=1.0"),
              ("coarse", "average per\nprogram only")]
    ff, ffc = mean_ci(rows, "p95_slowdown", load=load, scheduler="first_fit")
    vals = [mean_ci(rows, "p95_slowdown", load=load, scheduler="cache_aware", estimate=lv) for lv, _ in levels]
    fig, ax = plt.subplots(figsize=(6.2, 3.4), constrained_layout=True)
    xs = range(len(levels))
    ax.bar(xs, [v - 1 for v, _ in vals], bottom=1, yerr=[c for _, c in vals], width=0.6,
           color=COLOR["lru"], capsize=3, error_kw={"ecolor": MUTED, "lw": 1})
    ax.axhline(ff, color=INK, lw=1.2, ls="--")
    ax.text(len(levels) - 0.5, ff, f"first-fit (no estimates): {ff:.2f}", ha="right", va="bottom", fontsize=8, color=INK)
    for x, (v, c) in zip(xs, vals):
        ax.text(x, v + c + 0.015, f"{v:.2f}", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(list(xs), [nm for _, nm in levels])
    ax.set_ylim(1.0, ff + 0.15)
    ax.set_ylabel("p95 job slowdown")
    ax.set_title(f"Cache-aware placement with imperfect slowdown estimates (LRU, {load:.0%} load)", loc="left")
    fig.savefig(OUT / "fig4_robustness.png")
    key.append({"figure": "fig4", "policy": "lru", "scheduler": "first_fit", "load": load,
                "metric": "p95 slowdown", "value": round(ff, 4), "ci95": round(ffc, 4)})
    for (lv, _), (v, c) in zip(levels, vals):
        key.append({"figure": "fig4", "policy": "lru", "scheduler": f"cache_aware[{lv}]", "load": load,
                    "metric": "p95 slowdown", "value": round(v, 4), "ci95": round(c, 4)})


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    key: list[dict] = []
    fig1()
    fig2(key)
    fig3(key)
    fig4(key)
    with open(OUT / "key_numbers.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(key[0].keys()))
        w.writeheader()
        w.writerows(key)
    print(f"wrote 4 figures and key_numbers.csv to {OUT}")

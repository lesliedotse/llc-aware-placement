"""Figures from run_placement.py output.

  benefit_by_policy.png  How much cache-aware packing lowers p95 slowdown
                         versus first-fit at the SAME number of sockets, per
                         replacement policy and load.
                         This is the headline figure for research question 1.
  p95_by_scheduler.png   p95 slowdown of every scheduler, one panel per load.

Usage: python analysis/plots.py results/q1
"""
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ORDER = ["first_fit", "random", "cache_aware_pack", "cache_aware", "spread"]


def load(path: Path) -> list[dict]:
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            try:
                r[k] = float(v)
            except ValueError:
                pass
    return rows


def main(run_dir: Path) -> None:
    rows = [r for r in load(run_dir / "summary.csv") if r["estimate"] == "exact"]
    policies = sorted({r["policy"] for r in rows})
    loads = sorted({r["load"] for r in rows})
    get = {(r["policy"], r["load"], r["scheduler"]): r for r in rows}
    out = run_dir / "figures"
    out.mkdir(exist_ok=True)

    # 1. benefit of cache-aware placement, per policy
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    width = 0.8 / len(policies)
    for i, p in enumerate(policies):
        ben = [get[(p, ld, "first_fit")]["p95_slowdown"] - get[(p, ld, "cache_aware_pack")]["p95_slowdown"] for ld in loads]
        err = [(get[(p, ld, "first_fit")]["p95_slowdown_ci95"] ** 2 + get[(p, ld, "cache_aware_pack")]["p95_slowdown_ci95"] ** 2) ** 0.5
               for ld in loads]
        xs = [j + (i - (len(policies) - 1) / 2) * width for j in range(len(loads))]
        ax.bar(xs, ben, width, yerr=err, capsize=3, label=p.upper())
    ax.set_xticks(range(len(loads)), [f"{ld:.0%} load" for ld in loads])
    ax.set_ylabel("p95 slowdown saved\n(first-fit minus cache-aware packing)")
    ax.axhline(0, color="0.4", lw=0.8)
    ax.legend(title="LLC policy", frameon=False)
    ax.set_title("Benefit of cache-aware placement by replacement policy", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "benefit_by_policy.png", dpi=200)

    # 2. p95 slowdown of every scheduler
    fig, axes = plt.subplots(1, len(loads), figsize=(3.2 * len(loads), 3.6), sharey=True)
    axes = axes if len(loads) > 1 else [axes]
    for ax, ld in zip(axes, loads):
        for i, p in enumerate(policies):
            vals = [get[(p, ld, s)]["p95_slowdown"] for s in ORDER]
            errs = [get[(p, ld, s)]["p95_slowdown_ci95"] for s in ORDER]
            xs = [j + (i - (len(policies) - 1) / 2) * width for j in range(len(ORDER))]
            ax.bar(xs, vals, width, yerr=errs, capsize=2, label=p.upper())
        ax.set_xticks(range(len(ORDER)), [s.replace("_", "\n") for s in ORDER], fontsize=8)
        ax.set_title(f"{ld:.0%} load", fontsize=10)
        ax.set_ylim(bottom=1.0)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("p95 job slowdown (1 = no interference)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, title="LLC policy", frameon=False, fontsize=8,
               loc="upper center", ncol=len(policies), bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(out / "p95_by_scheduler.png", dpi=200)
    print(f"wrote figures to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

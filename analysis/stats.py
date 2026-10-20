"""Paired t-tests with Holm-Bonferroni correction for the policy comparisons.

Question: does a replacement policy change the benefit of cache-aware
placement, compared with LRU? For each (policy, load), the per-seed benefit
(first_fit p95 minus cache_aware p95) under that policy is compared with the
benefit under LRU on the same seed. Every seed uses the same job stream, so
the test is paired. Holm's step-down procedure controls the family-wise error
rate at 5% across all comparisons in one results file.

Usage: python analysis/stats.py results/q1/results.csv [results/window2/q1/results.csv ...]
Writes <dir>/policy_tests.csv next to each input.
"""
from __future__ import annotations

import csv
import math
import statistics
import sys
from pathlib import Path


def _betacf(a, b, x, iters=200, eps=3e-14):
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, iters + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-300 else 1e-300
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def t_two_sided_p(t, df):
    return betainc(df / 2, 0.5, df / (df + t * t))


def paired_test(diffs):
    n = len(diffs)
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    if sd == 0:
        return m, 0.0, (0.0 if m != 0 else 1.0)
    t = m / (sd / math.sqrt(n))
    return m, t, t_two_sided_p(t, n - 1)


def holm(pvals, alpha=0.05):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    adj = [0.0] * len(pvals)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvals) - rank) * pvals[i]))
        adj[i] = running
    return adj, [a < alpha for a in adj]


def analyse(path: Path, scheduler: str = "cache_aware"):
    rows = list(csv.DictReader(open(path)))
    by = {}
    for r in rows:
        if r.get("estimate", "exact") != "exact":
            continue
        by.setdefault((r["policy"], float(r["load"]), int(r["seed"])), {})[r["scheduler"]] = float(r["p95_slowdown"])
    policies = sorted({k[0] for k in by} - {"lru"})
    loads = sorted({k[1] for k in by})
    seeds = sorted({k[2] for k in by})
    tests = []
    for p in policies:
        for ld in loads:
            diffs = []
            for s in seeds:
                a, b = by.get(("lru", ld, s)), by.get((p, ld, s))
                if a and b:
                    diffs.append((b["first_fit"] - b[scheduler]) - (a["first_fit"] - a[scheduler]))
            m, t, pv = paired_test(diffs)
            tests.append({"policy": p, "load": ld, "n": len(diffs), "benefit_minus_lru": round(m, 4),
                          "t": round(t, 3), "p": pv})
    adj, sig = holm([x["p"] for x in tests])
    for x, a, s in zip(tests, adj, sig):
        x["p"] = round(x["p"], 5)
        x["p_holm"] = round(a, 5)
        x["significant_holm"] = s
    out = path.parent / "policy_tests.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(tests[0]))
        w.writeheader()
        w.writerows(tests)
    print(f"\n{path}  ({len(tests)} comparisons, Holm-corrected at 5%)")
    for x in tests:
        flag = "SIGNIFICANT" if x["significant_holm"] else ""
        print(f"  {x['policy']:6} load {x['load']:.1f}: {x['benefit_minus_lru']:+.3f}  p={x['p']:.4f}  p_holm={x['p_holm']:.4f}  {flag}")
    return tests


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        analyse(Path(arg))

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import pytest  # noqa: E402

from placement import Job, first_fit, make_cache_aware, simulate, spread  # noqa: E402
from placement.workload import coarse_table, load_table, noisy_table, poisson_jobs, types_of  # noqa: E402
from champsim_output import parse_roi  # noqa: E402

FLAT = {(a, b): 1.0 for a in "xy" for b in "xy"}
# x hurts y badly, everything else is harmless
SKEWED = {("x", "x"): 1.0, ("x", "y"): 1.0, ("y", "x"): 2.0, ("y", "y"): 1.0}


def test_no_interference_means_no_slowdown():
    jobs = poisson_jobs(["x", "y"], 500, 5, 0.8, seed=1)
    res = simulate(jobs, 5, FLAT, first_fit)
    assert len(res.jobs) == 500
    assert max(res.slowdowns()) == pytest.approx(1.0)


def test_corun_slowdown_is_exact_for_two_jobs():
    # x and y arrive together, same work: y runs at half speed until x leaves
    jobs = [Job(0, "x", 0.0, 10.0), Job(1, "y", 0.0, 10.0)]
    res = simulate(jobs, 1, SKEWED, first_fit)
    by_id = {j.id: j for j in res.jobs}
    assert by_id[0].finish == pytest.approx(10.0)
    # 10 s at speed 0.5 gives 5 units of work, then 5 more units alone
    assert by_id[1].finish == pytest.approx(15.0)


def test_spread_avoids_colocation_when_room():
    jobs = [Job(0, "x", 0.0, 10.0), Job(1, "y", 0.0, 10.0)]
    res = simulate(jobs, 2, SKEWED, spread)
    assert max(res.slowdowns()) == pytest.approx(1.0)


def test_cache_aware_beats_first_fit_on_skewed_table():
    def run(sched):
        jobs = poisson_jobs(["x", "y"], 2000, 20, 0.7, seed=3)
        return simulate(jobs, 20, SKEWED, sched).summary()

    assert run(make_cache_aware(0.1))["mean_slowdown"] < run(first_fit)["mean_slowdown"]


def test_every_job_finishes_after_it_arrives():
    jobs = poisson_jobs(["x", "y"], 300, 3, 0.95, seed=7)
    res = simulate(jobs, 3, SKEWED, first_fit)
    assert all(j.start >= j.arrival and j.finish > j.start for j in res.jobs)


def test_placeholder_table_loads_complete():
    table = load_table(ROOT / "data" / "example_slowdown_PLACEHOLDER.csv")
    assert len(types_of(table)) == 6 and len(table) == 36


def test_noise_and_coarse_tables():
    assert noisy_table(SKEWED, 0.0, 1) == pytest.approx(SKEWED)
    c = coarse_table(SKEWED)
    assert c[("y", "x")] == c[("y", "y")] == pytest.approx(1.5)


SAMPLE = """
=== Simulation ===
CPU 0 runs a.xz
CPU 1 runs b.xz

Region of Interest Statistics

CPU 0 cumulative IPC: 0.8 instructions: 50000000 cycles: 62500000
CPU 0 Branch Prediction Accuracy: 95% MPKI: 3 Average ROB Occupancy at Mispredict: 100

CPU 1 cumulative IPC: 1.5 instructions: 50000000 cycles: 33333333
CPU 1 Branch Prediction Accuracy: 99% MPKI: 1 Average ROB Occupancy at Mispredict: 100

cpu0->cpu0_L2C TOTAL        ACCESS:    1000000 HIT:     800000 MISS:     200000 MISS_MERGE:          0
cpu0->LLC TOTAL        ACCESS:     200000 HIT:     100000 MISS:     100000 MISS_MERGE:          0
cpu1->LLC TOTAL        ACCESS:      50000 HIT:      40000 MISS:      10000 MISS_MERGE:          0

DRAM Statistics
"""


def test_parse_champsim_output():
    cores = parse_roi(SAMPLE)
    assert [c["ipc"] for c in cores] == [0.8, 1.5]
    assert cores[0]["llc_misses"] == 100000
    assert cores[0]["llc_mpki"] == pytest.approx(2.0)
    assert cores[1]["llc_mpki"] == pytest.approx(0.2)


def test_absolute_table_matches_relative_for_reference_policy():
    runs = ROOT / "results" / "runs.csv"
    if not runs.exists():
        return  # measured data not present in this checkout
    rel = load_table(ROOT / "results" / "slowdown_lru.csv")
    from placement.workload import absolute_table
    ab = absolute_table(runs, "lru")
    for key, v in rel.items():
        assert ab[key] == pytest.approx(v, rel=1e-3)
    assert all(ab[(t, "")] == pytest.approx(1.0) for t in types_of(rel))

"""Slowdown tables and job streams."""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

from .sim import SLOTS_PER_SOCKET, Job, Table


def load_table(path: Path) -> Table:
    table: Table = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            table[(row["victim"], row["neighbor"])] = float(row["slowdown"])
    types = sorted({v for v, _ in table})
    missing = [(a, b) for a in types for b in types if (a, b) not in table]
    if missing:
        raise ValueError(f"{path}: slowdown table is missing pairs {missing[:5]}")
    return table


def types_of(table: Table) -> list[str]:
    return sorted({v for v, _ in table})


def noisy_table(table: Table, sigma: float, seed: int) -> Table:
    """Multiplicative log-normal error on the extra slowdown, as a scheduler's
    imperfect estimate would have. sigma=0 returns the table unchanged."""
    rng = random.Random(seed)
    return {k: 1.0 + (v - 1.0) * math.exp(rng.gauss(0.0, sigma)) for k, v in table.items()}


def coarse_table(table: Table) -> Table:
    """What a scheduler that only knows each victim's average sensitivity sees."""
    out: Table = {}
    for v in types_of(table):
        row = [table[(v, n)] for n in types_of(table)]
        avg = sum(row) / len(row)
        for n in types_of(table):
            out[(v, n)] = avg
    return out


def poisson_jobs(types: list[str], n_jobs: int, n_sockets: int, load: float, seed: int,
                 mean_work: float = 100.0, diurnal: bool = True) -> list[Job]:
    """Jobs arriving as a Poisson process, optionally with a day/night rate swing.

    `load` is the offered load as a fraction of all slots (ignoring slowdown).
    Work is exponential with mean `mean_work`; types are drawn uniformly.
    """
    rng = random.Random(seed)
    slots = n_sockets * SLOTS_PER_SOCKET
    base_rate = load * slots / mean_work
    period = 50 * mean_work
    jobs, t = [], 0.0
    peak = base_rate * (1.5 if diurnal else 1.0)
    while len(jobs) < n_jobs:  # thinning keeps the average rate at base_rate
        t += rng.expovariate(peak)
        r = base_rate * (1 + 0.5 * math.sin(2 * math.pi * t / period)) if diurnal else base_rate
        if rng.random() <= r / peak:
            jobs.append(Job(len(jobs), rng.choice(types), t, rng.expovariate(1 / mean_work)))
    return jobs


def jobs_from_csv(path: Path, types: list[str], seed: int, time_scale: float = 1.0) -> list[Job]:
    """Load arrivals from a CSV with columns `arrival,duration[,type]`.

    Use this for real cluster traces (e.g. Azure or Google) converted to that
    format. Rows without a type get one drawn uniformly, with a fixed seed.
    """
    rng = random.Random(seed)
    jobs = []
    with open(path) as f:
        for i, row in enumerate(csv.DictReader(f)):
            ty = row.get("type") or rng.choice(types)
            jobs.append(Job(i, ty, float(row["arrival"]) * time_scale, float(row["duration"]) * time_scale))
    return jobs

"""Placement policies. Each takes (job, cluster, table) and returns a socket index.

All policies except `spread` try to consolidate: they prefer a half-full
socket over opening an empty one, because providers pack jobs to save servers.
That forces co-location, which is where cache interference matters.
"""
from __future__ import annotations

import random as _random

from .sim import SLOTS_PER_SOCKET, Cluster, Job, Table


def _half_full(cluster: Cluster) -> list[int]:
    return [i for i, s in enumerate(cluster.slots) if 0 < len(s) < SLOTS_PER_SOCKET]


def _empty(cluster: Cluster) -> list[int]:
    return [i for i, s in enumerate(cluster.slots) if not s]


def first_fit(job: Job, cluster: Cluster, table: Table) -> int:
    """Cache-oblivious packing: lowest-numbered half-full socket, else lowest empty one."""
    half = _half_full(cluster)
    return half[0] if half else _empty(cluster)[0]


def make_random(seed: int):
    rng = _random.Random(seed)

    def random_pack(job: Job, cluster: Cluster, table: Table) -> int:
        """Cache-oblivious packing: a random half-full socket, else a random empty one."""
        half = _half_full(cluster)
        return rng.choice(half) if half else rng.choice(_empty(cluster))

    return random_pack


def spread(job: Job, cluster: Cluster, table: Table) -> int:
    """Interference-avoiding upper bound: always use an empty socket if one exists."""
    empty = _empty(cluster)
    return empty[0] if empty else _half_full(cluster)[0]


def pair_cost(a: str, b: str, table: Table) -> float:
    """Extra slowdown created when a and b share a socket (0 = no interference)."""
    return (table[(a, b)] - 1.0) + (table[(b, a)] - 1.0)


def make_cache_aware(threshold: float = 0.10):
    """Pack next to the neighbour that hurts least; open an empty socket only if
    every available neighbour would add more than `threshold` total slowdown."""

    def cache_aware(job: Job, cluster: Cluster, table: Table) -> int:
        half = _half_full(cluster)
        empty = _empty(cluster)
        if half:
            best = min(half, key=lambda s: (pair_cost(job.type, cluster.slots[s][0].type, table), s))
            if not empty or pair_cost(job.type, cluster.slots[best][0].type, table) <= threshold:
                return best
        return empty[0]

    cache_aware.__name__ = f"cache_aware_t{threshold:g}"
    return cache_aware

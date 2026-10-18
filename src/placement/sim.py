"""Event-driven simulator of jobs sharing 2-slot sockets.

Model
-----
* The cluster has `n_sockets` sockets. Each socket has 2 slots (cores) that
  share one last-level cache.
* A job has a workload type and an amount of work, measured in seconds when
  running alone.
* While a job shares its socket with a neighbour, it runs at speed
  1 / slowdown[(its type, neighbour type)]. Alone, it runs at speed 1.
* Jobs wait in a FIFO queue when every slot is busy.
* The scheduler only chooses WHERE a job goes; the true slowdown table decides
  how fast it then runs. Giving the scheduler a different (noisy) table than
  the simulator lets us test robustness (research question 3).
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

SLOTS_PER_SOCKET = 2
Table = dict[tuple[str, str], float]


@dataclass
class Job:
    id: int
    type: str
    arrival: float
    work: float
    remaining: float = field(init=False)
    start: float | None = None
    finish: float | None = None
    socket: int | None = None

    def __post_init__(self) -> None:
        self.remaining = self.work


@dataclass
class Cluster:
    n_sockets: int
    slots: list[list[Job]] = field(init=False)

    def __post_init__(self) -> None:
        self.slots = [[] for _ in range(self.n_sockets)]

    def free_sockets(self) -> list[int]:
        return [i for i, s in enumerate(self.slots) if len(s) < SLOTS_PER_SOCKET]

    def neighbour(self, job: Job) -> Job | None:
        others = [j for j in self.slots[job.socket] if j is not job]
        return others[0] if others else None

    def busy_sockets(self) -> int:
        return sum(1 for s in self.slots if s)


def rate(job: Job, cluster: Cluster, table: Table) -> float:
    """Speed of a job right now. A table may also hold (type, "") entries: the
    job's slowdown when running ALONE relative to a common reference, used to
    compare replacement policies in absolute time. Missing means 1.0."""
    nb = cluster.neighbour(job)
    if nb is None:
        return 1.0 / table.get((job.type, ""), 1.0)
    return 1.0 / table[(job.type, nb.type)]


@dataclass
class Result:
    jobs: list[Job]
    busy_socket_time: float  # integral of busy sockets over time
    makespan: float

    def slowdowns(self) -> list[float]:
        return [(j.finish - j.start) / j.work for j in self.jobs]

    def summary(self, target: float = 1.10) -> dict:
        sd = sorted(self.slowdowns())
        waits = [j.start - j.arrival for j in self.jobs]
        n = len(sd)
        return {
            "jobs": n,
            "mean_slowdown": sum(sd) / n,
            "p95_slowdown": sd[min(n - 1, math.ceil(0.95 * n) - 1)],
            "max_slowdown": sd[-1],
            "frac_over_target": sum(1 for s in sd if s > target) / n,
            "mean_wait": sum(waits) / n,
            "mean_busy_sockets": self.busy_socket_time / self.makespan if self.makespan else 0.0,
        }


def simulate(jobs: list[Job], n_sockets: int, true_table: Table, scheduler, est_table: Table | None = None) -> Result:
    """Run all jobs to completion. `scheduler(job, cluster, table)` returns a socket index."""
    est_table = est_table if est_table is not None else true_table
    cluster = Cluster(n_sockets)
    arrivals = sorted(jobs, key=lambda j: (j.arrival, j.id))
    queue: list[Job] = []
    running: list[Job] = []
    t = 0.0
    ai = 0
    busy_time = 0.0
    done: list[Job] = []

    def place_waiting(now: float) -> None:
        while queue and cluster.free_sockets():
            job = queue.pop(0)
            s = scheduler(job, cluster, est_table)
            if s not in cluster.free_sockets():
                raise ValueError(f"scheduler chose full socket {s}")
            job.socket, job.start = s, now
            cluster.slots[s].append(job)
            running.append(job)

    while ai < len(arrivals) or queue or running:
        rates = {j.id: rate(j, cluster, true_table) for j in running}
        next_finish = min((t + j.remaining / rates[j.id] for j in running), default=math.inf)
        next_arrival = arrivals[ai].arrival if ai < len(arrivals) else math.inf
        t_next = min(next_finish, next_arrival)
        if t_next == math.inf:
            raise RuntimeError("deadlock: jobs queued but nothing running")
        dt = t_next - t
        busy_time += dt * cluster.busy_sockets()
        for j in running:
            j.remaining -= dt * rates[j.id]
        t = t_next
        # completions (tolerance for float error)
        for j in [j for j in running if j.remaining <= 1e-9 * j.work]:
            j.remaining, j.finish = 0.0, t
            cluster.slots[j.socket].remove(j)
            running.remove(j)
            done.append(j)
        while ai < len(arrivals) and arrivals[ai].arrival <= t:
            queue.append(arrivals[ai])
            ai += 1
        place_waiting(t)
    return Result(done, busy_time, t)

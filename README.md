# Does smarter cache replacement change how clouds should place workloads?

Independent research project by Leslie Dotse (2026).

Cloud servers run several tenants on one processor, and those tenants share the
last-level cache (LLC). A cache-hungry neighbor slows everyone else down. Two
research communities attack this from different sides:

- **Cloud schedulers** place workloads so that bad neighbors don't share a server
  (e.g. Paragon, ASPLOS 2013; CacheVM, ICNP 2016).
- **Computer architects** design smarter LLC replacement policies so the
  hardware itself shares the cache better (e.g. SHiP, Hawkeye, Mockingjay).

CRUISE (ASPLOS 2012) showed that the two interact: smarter replacement eases the
scheduler's job, and the best co-schedule depends on the replacement policy. It
tested RRIP-era policies on a single chip. **This project revisits that question
with modern PC-based policies and evaluates it at cluster scale.**

## Research questions

1. Does a stronger replacement policy (SHiP / Mockingjay vs LRU) reduce the
   benefit of cache-aware workload placement in a cluster?
2. How fair are these policies when cloud-style workloads share an LLC?
3. How robust is cache-aware placement when its slowdown estimates are wrong?

## How it works

```
 ChampSim traces ──► solo + 2-core co-runs ──► slowdown table ──► cluster placement sim ──► results
 (architecture half: C++ simulator)            (one per policy)   (cloud half: Python)
```

1. **Measure.** For each replacement policy, run every workload alone and every
   pair of workloads together on a 2-core chip with a shared 2 MB LLC
   (ChampSim). Slowdown = solo IPC / co-run IPC.
2. **Place.** A discrete-event cluster simulator assigns arriving jobs to
   2-slot sockets using different schedulers. A job's speed while co-located
   comes from the measured slowdown table.
3. **Compare.** For each policy, how much does cache-aware placement improve
   job slowdown over cache-oblivious placement?

## Repository layout

| Path | What it is |
| --- | --- |
| `config/workloads.json` | The 6 workloads and their trace files |
| `scripts/setup_champsim.sh` | Clones and builds ChampSim, one binary per policy and core count |
| `scripts/download_traces.sh` | Downloads the SPEC CPU 2017 traces (DPC-3 set) |
| `scripts/make_configs.py` | Writes ChampSim JSON configs for each policy |
| `experiments/run_corun.py` | Runs all solo and pair simulations, builds slowdown tables |
| `src/placement/` | Cluster placement simulator and schedulers |
| `experiments/run_placement.py` | Runs the placement experiments (Q1, Q3) |
| `analysis/plots.py` | Makes the figures in `results/figures/` |
| `data/example_slowdown_PLACEHOLDER.csv` | **Made-up numbers** so the pipeline runs before real data exists. Never report results from it. |
| `tests/` | Sanity tests for the simulator |

## Quick start (macOS or Linux)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests                     # simulator sanity checks
python experiments/run_placement.py --slowdown data/example_slowdown_PLACEHOLDER.csv --out results/demo
```

Real experiments, all in one command (needs about 5 GB of free disk and several hours of CPU):

```bash
bash scripts/run_all.sh        # build ChampSim, download traces, start all simulations in the background
tail -f results/run_all.log    # watch progress
```

Or step by step:

```bash
bash scripts/setup_champsim.sh            # builds ChampSim binaries into champsim/bin
bash scripts/download_traces.sh           # downloads the 6 traces (about 3.4 GB) into traces/
python experiments/run_corun.py --jobs 8  # solo + pair runs for every policy
python experiments/run_placement.py --slowdown results/slowdown_lru.csv results/slowdown_ship.csv --out results/q1
python analysis/plots.py results/q1
```

On an Apple Silicon Mac, ChampSim builds natively with Xcode command-line tools
(`xcode-select --install`) plus `brew install cmake pkg-config`. If the native
build fails, use the Docker route in `scripts/setup_champsim.sh --docker`.

## Schedulers compared

| Scheduler | Packs jobs? | Uses slowdown table? |
| --- | --- | --- |
| `first_fit` | yes | no |
| `random` | yes | no |
| `cache_aware_pack` | yes, exactly like first-fit | picks the least harmful neighbour |
| `cache_aware` | yes, unless every neighbour adds > 10% slowdown | yes, may open an extra socket |
| `spread` | no, uses an empty socket whenever one exists | no |

`cache_aware_pack` vs `first_fit` is the fair comparison: same number of busy
sockets, only the neighbour choice differs. `cache_aware` trades extra sockets
for speed, so always report `mean_busy_sockets` next to its slowdown.

## Status

- [x] Repository and simulator (8 sanity tests pass; demo runs end to end on the placeholder table)
- [x] ChampSim config generator and run script (command lines checked with `--dry-run`)
- [ ] ChampSim runs (solo + pairs) for LRU, SRRIP, DRRIP, SHiP
- [ ] Port Mockingjay to current ChampSim (stretch goal)
- [ ] Placement experiments on measured tables
- [ ] Technical report

## Limitations

Results come from simulation: a 2-core model with one shared LLC, short trace
windows, and a simplified cluster model. They show trends under these
assumptions, not production-cloud performance.

## License

MIT (this repository). ChampSim is distributed under its own license.

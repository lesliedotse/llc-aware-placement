"""Write one ChampSim JSON config per (replacement policy, core count).

Every config keeps ChampSim's default core and cache settings and a single
2 MB LLC (2048 sets x 16 ways x 64 B). The LLC is NOT scaled with core count:
in the 2-core configs both programs share the same 2 MB, which is the
contention we want to measure.

Usage: python scripts/make_configs.py <champsim_dir> <out_dir> [--prefetch] [--policies lru ship]

--prefetch turns on hardware prefetchers (IP-stride at L1D, SPP at L2C) and
adds "_pf" to every executable and config name.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


PREFETCHERS = {"L1D": "ip_stride", "L2C": "spp_dev"}


def make_configs(champsim_dir: Path, out_dir: Path, prefetch: bool = False, policies: list[str] | None = None) -> list[Path]:
    base = json.loads((champsim_dir / "champsim_config.json").read_text())
    spec = json.loads((ROOT / "config" / "workloads.json").read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_pf" if prefetch else ""
    written = []
    for policy in policies or spec["policies"]:
        for cores in (1, 2):
            cfg = copy.deepcopy(base)
            cfg["executable_name"] = f"champsim_{policy}_{cores}core{suffix}"
            cfg["num_cores"] = cores
            cpu = base["ooo_cpu"][0]
            cfg["ooo_cpu"] = [copy.deepcopy(cpu) for _ in range(cores)]
            cfg["LLC"]["sets"] = 2048
            cfg["LLC"]["ways"] = 16
            cfg["LLC"]["replacement"] = policy
            for level, pf in PREFETCHERS.items():
                cfg[level]["prefetcher"] = pf if prefetch else base[level].get("prefetcher", "no")
            path = out_dir / f"{policy}_{cores}core{suffix}.json"
            path.write_text(json.dumps(cfg, indent=2))
            written.append(path)
    return written


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("champsim_dir", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--prefetch", action="store_true")
    ap.add_argument("--policies", nargs="+")
    a = ap.parse_args()
    for p in make_configs(a.champsim_dir, a.out_dir, a.prefetch, a.policies):
        print(p)

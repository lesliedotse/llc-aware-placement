"""Write one ChampSim JSON config per (replacement policy, core count).

Every config keeps ChampSim's default core and cache settings and a single
2 MB LLC (2048 sets x 16 ways x 64 B). The LLC is NOT scaled with core count:
in the 2-core configs both programs share the same 2 MB, which is the
contention we want to measure.

Usage: python scripts/make_configs.py <champsim_dir> <out_dir>
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_configs(champsim_dir: Path, out_dir: Path) -> list[Path]:
    base = json.loads((champsim_dir / "champsim_config.json").read_text())
    spec = json.loads((ROOT / "config" / "workloads.json").read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for policy in spec["policies"]:
        for cores in (1, 2):
            cfg = copy.deepcopy(base)
            cfg["executable_name"] = f"champsim_{policy}_{cores}core"
            cfg["num_cores"] = cores
            cpu = base["ooo_cpu"][0]
            cfg["ooo_cpu"] = [copy.deepcopy(cpu) for _ in range(cores)]
            cfg["LLC"]["sets"] = 2048
            cfg["LLC"]["ways"] = 16
            cfg["LLC"]["replacement"] = policy
            path = out_dir / f"{policy}_{cores}core.json"
            path.write_text(json.dumps(cfg, indent=2))
            written.append(path)
    return written


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    for p in make_configs(Path(sys.argv[1]), Path(sys.argv[2])):
        print(p)

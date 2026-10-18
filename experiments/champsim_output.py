"""Parse ChampSim's plain-text output (Region of Interest section)."""
import re

# core names are "CPU 0" in current ChampSim ("cpu0" in some older versions)
_IPC = re.compile(r"^(CPU \d+|cpu\d+) cumulative IPC: (\S+) instructions: (\d+) cycles: (\d+)")
_LLC = re.compile(r"^cpu(\d+)->(\S*LLC)\s+TOTAL\s+ACCESS:\s+(\d+)\s+HIT:\s+(\d+)\s+MISS:\s+(\d+)")


def parse_roi(text: str) -> list[dict]:
    """Return one dict per core: ipc, instructions, cycles, llc_accesses, llc_misses, llc_mpki."""
    marker = "Region of Interest Statistics"
    if marker not in text:
        raise ValueError("no 'Region of Interest Statistics' section; did the run finish?")
    roi = text.rsplit(marker, 1)[1].split("DRAM Statistics", 1)[0]  # last phase = simulation
    cores: list[dict] = []
    llc: dict[int, tuple[int, int]] = {}
    for line in roi.splitlines():
        line = line.strip()
        m = _IPC.match(line)
        if m:
            cores.append({"ipc": float(m.group(2)), "instructions": int(m.group(3)), "cycles": int(m.group(4))})
            continue
        m = _LLC.match(line)
        if m:
            llc[int(m.group(1))] = (int(m.group(3)), int(m.group(5)))
    if not cores:
        raise ValueError("no per-core IPC lines found in ROI section")
    for i, c in enumerate(cores):
        acc, miss = llc.get(i, (0, 0))
        c["llc_accesses"] = acc
        c["llc_misses"] = miss
        c["llc_mpki"] = 1000.0 * miss / c["instructions"] if c["instructions"] else 0.0
    return cores

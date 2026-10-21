#!/usr/bin/env bash
# Robustness test C: SRRIP and DRRIP with prefetchers on, window 2 (54 runs).
# Completes the prefetcher set in results/window2_prefetch/ (LRU and SHiP come
# from test B and are kept). Needs the window-2 traces in traces/.
# Usage (from the repository folder): bash scripts/run_prefetch_rrip.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
mkdir -p results/window2_prefetch

if pgrep -f "run_corun.py" >/dev/null || pgrep -f "bin/champsim_" >/dev/null; then
  echo "Simulations are already running; not starting a second copy."
  echo "Check them with:  bash scripts/progress.sh"
  exit 1
fi

echo "== checking window-2 traces"
python3 - <<'EOF'
import json, os, sys
missing = [w["trace"] for w in json.load(open("config/workloads_window2.json"))["workloads"]
           if not os.path.exists(os.path.join("traces", w["trace"]))]
if missing:
    sys.exit("missing traces: " + ", ".join(missing) + "\nRun: bash scripts/download_traces.sh config/workloads_window2.json")
print("all 6 present")
EOF

echo "== building prefetcher-enabled SRRIP and DRRIP simulators (about 5-10 minutes)"
bash scripts/patch_champsim.sh
SPP_SRC=champsim/prefetcher/spp_dev/spp_dev.cc
python3 scripts/make_configs.py champsim config/champsim --prefetch --policies srrip drrip > /dev/null
for cfg in config/champsim/srrip_*_pf.json config/champsim/drrip_*_pf.json; do
  exe="champsim/bin/champsim_$(basename "$cfg" .json)"
  if [[ -x "$exe" && "$exe" -nt "$SPP_SRC" ]]; then echo "have $(basename "$exe")"; continue; fi
  echo "building $(basename "$exe")"
  (cd champsim && ./config.sh "$REPO/$cfg" > /dev/null && make -j"$(getconf _NPROCESSORS_ONLN)" > /dev/null)
done

KEEP_AWAKE=""
command -v caffeinate >/dev/null && KEEP_AWAKE="caffeinate -i"

echo "== starting in the background (8 simulations at a time)"
# LRU and SHiP runs already exist and are skipped; listing them makes the
# final runs.csv and slowdown tables cover all four policies.
nohup $KEEP_AWAKE python3 experiments/run_corun.py --spec config/workloads_window2.json \
  --results results/window2_prefetch --policies lru srrip drrip ship --binary-suffix _pf --jobs 8 \
  > results/window2_prefetch/run_rrip.log 2>&1 &
echo "C (SRRIP/DRRIP, prefetchers)  started, process $!"
echo
echo "Check progress with:  bash scripts/progress.sh"

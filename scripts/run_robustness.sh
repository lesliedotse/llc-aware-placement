#!/usr/bin/env bash
# Two robustness tests on the second-window traces, run side by side:
#   A. SRRIP and DRRIP on window 2      -> results/window2/          (54 new runs)
#   B. LRU and SHiP with prefetchers on -> results/window2_prefetch/ (54 new runs)
# Needs the window-2 traces in traces/ (from scripts/run_window2.sh).
# Usage (from the repository folder): bash scripts/run_robustness.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
mkdir -p results/window2 results/window2_prefetch

echo "== checking window-2 traces"
python3 - <<'EOF'
import json, os, sys
missing = [w["trace"] for w in json.load(open("config/workloads_window2.json"))["workloads"]
           if not os.path.exists(os.path.join("traces", w["trace"]))]
if missing:
    sys.exit("missing traces: " + ", ".join(missing) + "\nRun: bash scripts/download_traces.sh config/workloads_window2.json")
print("all 6 present")
EOF

echo "== building prefetcher-enabled simulators (about 5-10 minutes the first time)"
python3 scripts/make_configs.py champsim config/champsim --prefetch --policies lru ship > /dev/null
for cfg in config/champsim/*_pf.json; do
  exe="champsim/bin/champsim_$(basename "$cfg" .json)"
  if [[ -x "$exe" ]]; then echo "have $(basename "$exe")"; continue; fi
  echo "building $(basename "$exe")"
  (cd champsim && ./config.sh "$REPO/$cfg" > /dev/null && make -j"$(getconf _NPROCESSORS_ONLN)" > /dev/null)
done

KEEP_AWAKE=""
command -v caffeinate >/dev/null && KEEP_AWAKE="caffeinate -i"

echo "== starting both tests in the background"
nohup $KEEP_AWAKE python3 experiments/run_corun.py --spec config/workloads_window2.json \
  --results results/window2 --policies lru srrip drrip ship --jobs 4 > results/window2/run_more.log 2>&1 &
echo "A (SRRIP/DRRIP)  started, process $!"
nohup $KEEP_AWAKE python3 experiments/run_corun.py --spec config/workloads_window2.json \
  --results results/window2_prefetch --policies lru ship --binary-suffix _pf --jobs 4 > results/window2_prefetch/run.log 2>&1 &
echo "B (prefetchers)  started, process $!"
echo
echo "Check progress with:  bash scripts/progress.sh"

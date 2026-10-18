#!/usr/bin/env bash
# Robustness check: rerun LRU and SHiP on a second trace window of each program.
# Frees the first-window traces (their results are already saved), downloads the
# second-window traces, and starts the 54 simulations in the background.
# Usage (from the repository folder): bash scripts/run_window2.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results/window2

echo "== removing first-window traces (results for them are already in results/)"
python3 - <<'EOF'
import json, os
for w in json.load(open("config/workloads.json"))["workloads"]:
    for f in (os.path.join("traces", w["trace"]), os.path.join("traces", w["trace"] + ".part")):
        if os.path.exists(f):
            os.remove(f)
            print("removed", f)
EOF

echo "== downloading second-window traces"
bash scripts/download_traces.sh config/workloads_window2.json

echo "== starting 54 simulations in the background; progress goes to results/window2/run.log"
KEEP_AWAKE=""
command -v caffeinate >/dev/null && KEEP_AWAKE="caffeinate -i"
nohup $KEEP_AWAKE python3 experiments/run_corun.py --spec config/workloads_window2.json \
  --results results/window2 --policies lru ship --jobs 4 > results/window2/run.log 2>&1 &
echo "started (process $!). Check progress with:  find results/window2/raw -name '*.txt' | wc -l   (done at 54)"

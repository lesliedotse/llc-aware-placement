#!/usr/bin/env bash
# One command for the whole measurement pipeline:
#   1. check tools  2. build ChampSim  3. download traces  4. run all co-run simulations
# Safe to re-run: finished builds, downloads and simulations are skipped.
# Usage (from the repository folder): bash scripts/run_all.sh [--jobs N]
set -euo pipefail
cd "$(dirname "$0")/.."
JOBS="${2:-4}"
LOG="results/run_all.log"
mkdir -p results

echo "== 1/4 checking tools"
for tool in git python3 curl make; do
  command -v "$tool" >/dev/null || { echo "missing $tool. On a Mac run: xcode-select --install"; exit 1; }
done
if [[ "$(uname)" == "Darwin" ]] && ! xcode-select -p >/dev/null 2>&1; then
  echo "Xcode command-line tools are missing. Run: xcode-select --install  then re-run this script."
  exit 1
fi

echo "== 2/4 building ChampSim (first time: 10-30 minutes)"
if ls champsim/bin/champsim_ship_2core >/dev/null 2>&1; then
  echo "already built"
else
  bash scripts/setup_champsim.sh
fi

echo "== 3/4 downloading traces (about 10 GB the first time)"
bash scripts/download_traces.sh

echo "== 4/4 running simulations in the background; progress goes to $LOG"
# caffeinate stops a Mac from sleeping while the runs go (several hours)
KEEP_AWAKE=""
command -v caffeinate >/dev/null && KEEP_AWAKE="caffeinate -i"
nohup $KEEP_AWAKE python3 experiments/run_corun.py --jobs "$JOBS" > "$LOG" 2>&1 &
echo "started (process $!). Check progress with:  tail -f $LOG"
echo "When it finishes, results/slowdown_lru.csv and results/slowdown_ship.csv will exist."

#!/usr/bin/env bash
# Show progress of the robustness runs.
cd "$(dirname "$0")/.."
a=$(find results/window2/raw -name '*.txt' 2>/dev/null | wc -l | tr -d ' ')
b=$(find results/window2_prefetch/raw -name '*.txt' 2>/dev/null | wc -l | tr -d ' ')
echo "A  SRRIP/DRRIP, window 2:    $a of 108 finished (54 were already done)"
echo "B  prefetchers on, window 2: $b of 54 finished"
if pgrep -f "bin/champsim_" >/dev/null; then
  echo "running now (elapsed time, simulator):"
  ps -eo etime,args | grep "[b]in/champsim_" | awk '{n=split($2,p,"/"); print "   " $1 "  " p[n]}'
else
  echo "no simulations running"
fi
ls results/window2/slowdown_*.csv results/window2_prefetch/slowdown_*.csv 2>/dev/null

#!/usr/bin/env bash
# Show progress of the robustness runs.
cd "$(dirname "$0")/.."
count() { find "$@" -name '*.txt' 2>/dev/null | wc -l | tr -d ' '; }
a=$(count results/window2/raw)
b=$(count results/window2_prefetch/raw/lru results/window2_prefetch/raw/ship)
c=$(count results/window2_prefetch/raw/srrip results/window2_prefetch/raw/drrip)
echo "A  SRRIP/DRRIP, window 2:                 $a of 108 finished (54 were already done)"
echo "B  LRU/SHiP, prefetchers on, window 2:    $b of 54 finished"
echo "C  SRRIP/DRRIP, prefetchers on, window 2: $c of 54 finished"
if pgrep -f "bin/champsim_" >/dev/null; then
  echo "running now (elapsed time, simulator):"
  ps -eo etime,args | grep "[b]in/champsim_" | awk '{n=split($2,p,"/"); print "   " $1 "  " p[n]}'
else
  echo "no simulations running"
fi
ls results/window2/slowdown_*.csv results/window2_prefetch/slowdown_*.csv 2>/dev/null

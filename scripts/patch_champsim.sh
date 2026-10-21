#!/usr/bin/env bash
# Local fixes applied on top of the pinned ChampSim commit. Safe to run more than once.
#
# 1. SPP prefetcher (spp_dev) global history register.
#    update_entry() looks for a victim starting from min_conf = 100 with a
#    strict "<". When all 8 entries hold confidence 100 no victim is found and
#    the simulator aborts ("Assertion failed: (0), function update_entry,
#    file spp_dev.cc"). Starting the search above any possible confidence
#    selects exactly the same victim whenever some entry is below 100, so
#    every run that did not abort is bit-for-bit unchanged; the only effect is
#    that the all-100 case now replaces entry 0 instead of crashing.
set -euo pipefail
cd "$(dirname "$0")/../champsim"

f=prefetcher/spp_dev/spp_dev.cc
old='uint32_t min_conf = 100, victim_way = MAX_GHR_ENTRY;'
new='uint32_t min_conf = 0xFFFFFFFFu, victim_way = MAX_GHR_ENTRY; \/\/ patched by scripts\/patch_champsim.sh'
if grep -qF "$old" "$f"; then
  sed -i.orig "s/$old/$new/" "$f"
  rm -f "$f.orig"
  echo "patched $f (SPP GHR victim search)"
elif grep -q "patched by scripts/patch_champsim.sh" "$f"; then
  echo "$f already patched"
else
  echo "warning: $f does not match the expected code; SPP patch not applied" >&2
fi

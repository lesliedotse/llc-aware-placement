#!/usr/bin/env bash
# Download the six traces listed in config/workloads.json into traces/ (about 3.4 GB total).
# Finished files are skipped and interrupted downloads resume where they stopped.
# Usage: bash scripts/download_traces.sh [config/workloads_window2.json]
set -euo pipefail
cd "$(dirname "$0")/.."
export SPEC="${1:-config/workloads.json}"
mkdir -p traces
python3 - <<'EOF' > traces/urls.txt
import json, os
spec = json.load(open(os.environ["SPEC"]))
for w in spec["workloads"]:
    print(spec["trace_base_url"] + w["trace"])
EOF

# Check free space before downloading: need room for the traces still missing, plus 1 GB headroom.
NEED_GB=$(python3 - <<'EOF'
import json, os
sizes_mb = {"605.mcf_s-665B": 976, "620.omnetpp_s-874B": 765, "623.xalancbmk_s-700B": 153,
            "619.lbm_s-4268B": 737, "602.gcc_s-734B": 351, "641.leela_s-800B": 404}
spec = json.load(open(os.environ["SPEC"]))
need = 0
for w in spec["workloads"]:
    f = os.path.join("traces", w["trace"])
    if os.path.exists(f) and os.path.getsize(f) > 0:
        continue
    have = os.path.getsize(f + ".part") if os.path.exists(f + ".part") else 0
    need += sizes_mb.get(w["trace"].split(".champsimtrace")[0], 1000) * 2**20 - have
print(max(0, round(need / 2**30 + 1, 1)) if need > 0 else 0)
EOF
)
FREE_GB=$(python3 -c "import shutil; print(round(shutil.disk_usage('traces').free / 2**30, 1))")
if python3 -c "import sys; sys.exit(0 if $FREE_GB >= $NEED_GB else 1)"; then
  echo "disk space: $FREE_GB GB free, about $NEED_GB GB needed"
else
  echo "NOT ENOUGH DISK SPACE: $FREE_GB GB free, about $NEED_GB GB needed."
  echo "Free up space (e.g. empty the Trash, delete large Downloads), then re-run."
  exit 1
fi

while read -r url; do
  f="traces/$(basename "$url")"
  if [[ -s "$f" ]]; then echo "have $f"; continue; fi
  echo "downloading $f"
  # -C - resumes a partial .part file instead of starting over
  if curl -fL --retry 3 -C - -o "$f.part" "$url"; then
    mv "$f.part" "$f"
  else
    echo "download of $f failed; re-run this script to resume it"
    exit 1
  fi
done < traces/urls.txt
ls -lh traces/*.xz

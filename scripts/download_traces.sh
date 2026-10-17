#!/usr/bin/env bash
# Download the six traces listed in config/workloads.json into traces/.
# Each trace is roughly 1-3 GB. Already-downloaded files are skipped.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p traces
python3 - <<'EOF' > traces/urls.txt
import json
spec = json.load(open("config/workloads.json"))
for w in spec["workloads"]:
    print(spec["trace_base_url"] + w["trace"])
EOF
while read -r url; do
  f="traces/$(basename "$url")"
  if [[ -s "$f" ]]; then echo "have $f"; continue; fi
  echo "downloading $f"
  curl -fL --retry 3 -o "$f.part" "$url" && mv "$f.part" "$f"
done < traces/urls.txt
ls -lh traces/*.xz

#!/usr/bin/env bash
# Clone and build ChampSim: one binary per replacement policy and core count.
# Usage: bash scripts/setup_champsim.sh            (native build, macOS or Linux)
#        bash scripts/setup_champsim.sh --docker   (build inside an Ubuntu container)
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
CHAMPSIM_DIR="$REPO_ROOT/champsim"
# Pin a commit so results are reproducible. Update deliberately, not by accident.
CHAMPSIM_COMMIT="${CHAMPSIM_COMMIT:-develop}"

if [[ "${1:-}" == "--docker" ]]; then
  docker run --rm -v "$REPO_ROOT":/work -w /work ubuntu:24.04 bash -c \
    "apt-get update && apt-get install -y git build-essential cmake curl zip unzip tar pkg-config python3 && bash scripts/setup_champsim.sh"
  exit 0
fi

if [[ ! -d "$CHAMPSIM_DIR" ]]; then
  git clone https://github.com/ChampSim/ChampSim.git "$CHAMPSIM_DIR"
fi
cd "$CHAMPSIM_DIR"
git checkout "$CHAMPSIM_COMMIT"
git submodule update --init
mkdir -p "$REPO_ROOT/results"
git rev-parse HEAD > "$REPO_ROOT/results/champsim_commit.txt"   # record the exact version used

if [[ ! -x vcpkg/vcpkg ]]; then
  vcpkg/bootstrap-vcpkg.sh -disableMetrics
fi

# vcpkg downloads bzip2 from sourceware.org, which is often unreachable.
# macOS already ships bzip2 and zlib, so use those instead (set USE_SYSTEM_COMPRESSION=1
# to do the same on Linux after `sudo apt install libbz2-dev zlib1g-dev`).
if [[ "$(uname)" == "Darwin" || "${USE_SYSTEM_COMPRESSION:-0}" == "1" ]]; then
  python3 - <<'EOF'
import json
j = json.load(open("vcpkg.json"))
j["dependencies"] = [d for d in j["dependencies"] if d not in ("bzip2", "zlib")]
json.dump(j, open("vcpkg.json", "w"), indent=2)
print("using the system's bzip2 and zlib")
EOF
fi

if ! vcpkg/vcpkg install; then
  echo
  echo "vcpkg could not download a library. Scroll up for the 'Downloading ...' line naming the"
  echo "file and the site it tried, check your internet connection or proxy settings, then re-run."
  exit 1
fi

python3 "$REPO_ROOT/scripts/make_configs.py" "$CHAMPSIM_DIR" "$REPO_ROOT/config/champsim"
for cfg in "$REPO_ROOT"/config/champsim/*.json; do
  echo "=== building $(basename "$cfg")"
  ./config.sh "$cfg"
  make -j"$(getconf _NPROCESSORS_ONLN)"
done
echo "Built binaries:"
ls -1 "$CHAMPSIM_DIR/bin"

#!/usr/bin/env bash
# Clone and build ChampSim: one binary per replacement policy and core count.
# Usage: bash scripts/setup_champsim.sh            (native build, macOS or Linux)
#        bash scripts/setup_champsim.sh --docker   (build inside an Ubuntu container)
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
CHAMPSIM_DIR="$REPO_ROOT/champsim"
# Pin a commit so results are reproducible. Update deliberately, not by accident.
CHAMPSIM_COMMIT="${CHAMPSIM_COMMIT:-410cee62d9c429c043ea611325ce00e6c303be2a}"   # ChampSim master as of Sep 2026

if [[ "${1:-}" == "--docker" ]]; then
  docker run --rm -v "$REPO_ROOT":/work -w /work ubuntu:24.04 bash -c \
    "apt-get update && apt-get install -y git build-essential cmake curl zip unzip tar pkg-config python3 && bash scripts/setup_champsim.sh"
  exit 0
fi

if [[ ! -d "$CHAMPSIM_DIR" ]]; then
  git clone https://github.com/ChampSim/ChampSim.git "$CHAMPSIM_DIR"
fi
cd "$CHAMPSIM_DIR"
git checkout -- vcpkg.json 2>/dev/null || true   # undo edits from earlier runs
git checkout "$CHAMPSIM_COMMIT"
git submodule update --init
mkdir -p "$REPO_ROOT/results"
git rev-parse HEAD > "$REPO_ROOT/results/champsim_commit.txt"   # record the exact version used
bash "$REPO_ROOT/scripts/patch_champsim.sh"   # local bug fixes, documented in that script

# ChampSim's Makefile looks for its libraries in the first folder under
# vcpkg_installed/ (headers in include/, libraries in lib/). On a Mac with
# Homebrew we fill that folder from Homebrew instead of building with vcpkg,
# which failed on some Macs. Set USE_VCPKG=1 to force the vcpkg route.
homebrew_deps() {
  local brew_prefix="${BREW_PREFIX:-$(brew --prefix)}"
  if [[ -z "${BREW_PREFIX:-}" ]]; then
    brew install fmt cli11 nlohmann-json xz
  fi
  git checkout -- vcpkg.json 2>/dev/null || true
  rm -rf vcpkg_installed
  local t="vcpkg_installed/homebrew"
  mkdir -p "$t/lib/manual-link"
  ln -s "$brew_prefix/include" "$t/include"
  for lib in fmt lzma; do
    for f in "$brew_prefix"/lib/lib"$lib".*; do ln -sf "$f" "$t/lib/"; done
  done
  # Homebrew's CLI11 is header-only, but ChampSim links -lCLI11: give it an empty library.
  echo 'void champsim_cli11_placeholder(void) {}' > "$t/cli11_placeholder.c"
  cc -c "$t/cli11_placeholder.c" -o "$t/cli11_placeholder.o"
  ar rcs "$t/lib/libCLI11.a" "$t/cli11_placeholder.o"
  # zlib and bzip2 come with macOS itself.
  echo "using Homebrew libraries from $brew_prefix"
}

if [[ "${USE_VCPKG:-0}" != "1" && ( -n "${BREW_PREFIX:-}" || ( "$(uname)" == "Darwin" && -x "$(command -v brew)" ) ) ]]; then
  homebrew_deps
else

if [[ ! -x vcpkg/vcpkg ]]; then
  vcpkg/bootstrap-vcpkg.sh -disableMetrics
fi

# Trim ChampSim's dependency list before vcpkg installs it:
#  - catch2 is only used by ChampSim's own unit tests, not by the simulator,
#    and fails to build on some Macs.
#  - vcpkg downloads bzip2 from sourceware.org, which is often unreachable.
#    macOS already ships bzip2 and zlib, so use those (set USE_SYSTEM_COMPRESSION=1
#    to do the same on Linux after `sudo apt install libbz2-dev zlib1g-dev`).
SYSTEM_COMPRESSION=0
if [[ "$(uname)" == "Darwin" || "${USE_SYSTEM_COMPRESSION:-0}" == "1" ]]; then
  SYSTEM_COMPRESSION=1
fi
SYSTEM_COMPRESSION="$SYSTEM_COMPRESSION" python3 -c '
import json, os
drop = {"catch2"}
if os.environ["SYSTEM_COMPRESSION"] == "1":
    drop |= {"bzip2", "zlib"}
j = json.load(open("vcpkg.json"))
j["dependencies"] = [d for d in j["dependencies"] if d not in drop]
json.dump(j, open("vcpkg.json", "w"), indent=2)
print("vcpkg will install:", ", ".join(j["dependencies"]))
'

if ! vcpkg/vcpkg install; then
  echo
  echo "vcpkg failed to download or build a library. Scroll up for the first 'error:' line,"
  echo "check your internet connection, then re-run. If it repeats, paste that error to Claude."
  exit 1
fi

fi  # end of the vcpkg route

python3 "$REPO_ROOT/scripts/make_configs.py" "$CHAMPSIM_DIR" "$REPO_ROOT/config/champsim"
for cfg in "$REPO_ROOT"/config/champsim/*.json; do
  echo "=== building $(basename "$cfg")"
  ./config.sh "$cfg"
  make -j"$(getconf _NPROCESSORS_ONLN)"
done
echo "Built binaries:"
ls -1 "$CHAMPSIM_DIR/bin"

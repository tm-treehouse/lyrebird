#!/usr/bin/env bash
# Synthesise for GateMate with Yosys, then place and route with nextpnr.
#
#   tools/synth.sh <toplevel> [source.sv ...]
#
# With no sources given, every .sv in hdl/rtl is used.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/hdl/build"
TOP="${1:?usage: tools/synth.sh <toplevel> [sources...]}"
shift || true

# bash 3.2 compatible; macOS ships no mapfile.
SOURCES=()
if [ "$#" -gt 0 ]; then
  for s in "$@"; do SOURCES[${#SOURCES[@]}]="$s"; done
else
  while IFS= read -r s; do SOURCES[${#SOURCES[@]}]="$s"; done \
    < <(find "$ROOT/hdl/rtl" -name '*.sv' | sort)
fi
[ "${#SOURCES[@]}" -gt 0 ] || { echo "no sources found in hdl/rtl" >&2; exit 1; }

mkdir -p "$BUILD"
echo "=== synthesis: $TOP ==="
READ=""
for s in "${SOURCES[@]}"; do READ+="read_verilog -sv $s; "; done
yosys -p "${READ}synth_gatemate -top $TOP -json $BUILD/$TOP.json"

# Place and route needs nextpnr-himbaechel built against Project Peppercorn.
# Synthesis alone is still useful for resource counts and for catching
# anything the simulator accepts but the fabric will not.
if ! command -v nextpnr-himbaechel >/dev/null 2>&1; then
  echo
  echo "nextpnr-himbaechel not on PATH; stopping after synthesis."
  echo "Install the OSS CAD Suite, or build nextpnr with the gatemate"
  echo "himbaechel target against Project Peppercorn."
  exit 0
fi

echo "=== place and route: $TOP ==="
nextpnr-himbaechel --device CCGM1A1 \
  --json "$BUILD/$TOP.json" \
  --vopt out="$BUILD/$TOP.txt" \
  --router router2

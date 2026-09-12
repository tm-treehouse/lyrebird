#!/usr/bin/env bash
# Synthesise, place and route, and pack a bitstream for the GateMate CCGM1A1.
#
#   tools/synth.sh <toplevel> [source.sv ...]
#
# With no sources given, every .sv in hdl/rtl is used. A pin constraints file
# at hdl/constraints/<toplevel>.ccf is used when present; without one, I/O is
# placed automatically and a warning is printed, which is fine for resource
# counts and wrong for hardware. See hdl/constraints/README.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/hdl/build"
DEVICE="CCGM1A1"
TOP="${1:?usage: tools/synth.sh <toplevel> [sources...]}"
shift || true

# The OSS CAD Suite is sourced for this shell only, never added to PATH
# permanently. It ships its own Yosys, and having two on PATH means losing
# track of which one built a given artifact.
OSS_CAD_SUITE="${OSS_CAD_SUITE:-$HOME/tools/oss-cad-suite}"
if [ -f "$OSS_CAD_SUITE/environment" ]; then
  # shellcheck disable=SC1091
  source "$OSS_CAD_SUITE/environment"
else
  echo "OSS CAD Suite not found at $OSS_CAD_SUITE" >&2
  echo "Set OSS_CAD_SUITE, or install from" >&2
  echo "  https://github.com/YosysHQ/oss-cad-suite-build/releases" >&2
  exit 1
fi

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

# -luttree is required, not optional. Without it ABC maps to CC_LUT4, which
# nextpnr-himbaechel rejects outright: the fabric's native element is a LUT
# tree, so synthesis has to target CC_L2T4/CC_L2T5.
echo "=== synthesis: $TOP ==="
READ=""
for s in "${SOURCES[@]}"; do READ+="read_verilog -sv $s; "; done
yosys -q -p "${READ}synth_gatemate -top $TOP -luttree -json $BUILD/$TOP.json"

echo "=== place and route: $DEVICE ==="
PNR_OPTS=(--device "$DEVICE" --json "$BUILD/$TOP.json" --vopt "out=$BUILD/$TOP.txt")
CCF="$ROOT/hdl/constraints/$TOP.ccf"
if [ -f "$CCF" ]; then
  PNR_OPTS+=(--vopt "ccf=$CCF")
else
  echo "  no $CCF; placing I/O automatically (not valid for hardware)"
  PNR_OPTS+=(--vopt allow-unconstrained)
fi
nextpnr-himbaechel "${PNR_OPTS[@]}" > "$BUILD/$TOP.pnr.log" 2>&1 || {
  grep -v "unconstrained in CCF" "$BUILD/$TOP.pnr.log" | tail -20 >&2
  exit 1
}

echo "=== bitstream ==="
gmpack "$BUILD/$TOP.txt" "$BUILD/$TOP.bit"
echo "  $BUILD/$TOP.bit  ($(wc -c < "$BUILD/$TOP.bit" | tr -d ' ') bytes)"

echo "=== utilisation ==="
grep -A16 "Device utilisation" "$BUILD/$TOP.pnr.log" \
  | grep -E "CPE_LT|CPE_FF|GPIO|CLKIN|GLBOUT|PLL|RAM_HALF|SERDES" || true

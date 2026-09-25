#!/usr/bin/env bash
# Regenerate everything derived from the netlist generators, in order, then
# check that nothing is left stale.
#
# This exists because running a netlist generator to verify it makes every
# artifact downstream of it older than its source, and the derived files were
# three times found describing boards that no longer existed. Doing it by hand
# in the right order is exactly the step that got skipped.
#
#   netlist generator  ->  .net  ->  schematic sheets  ->  PDF
#                                ->  bom.csv
#
#   ./hardware/regenerate.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=./.venv/bin/python
CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
export KICAD10_SYMBOL_DIR="/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"

echo "== netlists =="
$PY hardware/netlist/main_board.py    2>&1 | grep -E "errors found" | sed 's/^/   main   /'
$PY hardware/netlist/output_module.py 2>&1 | grep -E "errors found" | sed 's/^/   module /'

echo "== schematics and PDFs =="
for b in main dac; do
  d="hardware/lyrebird-$b-reva"
  rm -f "$d"/sheets/*.kicad_sch
  $PY tools/netlist_to_sheets.py "$d/lyrebird-$b.net" "$d/sheets" >/dev/null
  tmp=$(mktemp -d)
  for f in "$d"/sheets/*.kicad_sch; do
    "$CLI" sch export pdf -o "$tmp/$(basename "${f%.kicad_sch}").pdf" "$f" >/dev/null 2>&1
  done
  $PY - "$tmp" "$d/lyrebird-$b-schematic.pdf" <<'EOF'
import glob, os, sys, pypdf
src, out = sys.argv[1], sys.argv[2]
w = pypdf.PdfWriter()
files = sorted(glob.glob(f"{src}/*.pdf"))
for f in files:
    for page in pypdf.PdfReader(f).pages:
        w.add_page(page)
with open(out, "wb") as fh:
    w.write(fh)
print(f"   {out}: {len(files)} sheets, {os.path.getsize(out)//1024} KB")
EOF
  rm -rf "$tmp"
done

echo "== bills of materials =="
$PY hardware/make_bom.py | sed 's/^/ /'

echo "== checks =="
$PY hardware/verify_power.py | grep "checks pass" | sed "s|^|   power:     |"
$PY hardware/check_freshness.py | grep -E "stale," | sed "s|^|   freshness: |"

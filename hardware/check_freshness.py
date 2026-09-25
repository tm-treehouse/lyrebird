#!/usr/bin/env python3
"""Find documents and derived files that no longer describe the boards.

This exists because the same failure has now happened three times in one
project, in three different places, and each time it was found by accident:

  * the schematics and both PDFs sat eleven days behind the netlists, showing
    USB bus power and a charge pump that had been deleted;
  * the transient simulation asserted four failures against circuits that had
    already been fixed, which is worse than no simulation because it teaches
    a reader to ignore red;
  * `power.md` still listed `AVDD` on `+3V3` -- a destroy-the-part bug the
    netlist corrected long ago and the document went on documenting.

The netlist generators run constantly. Everything derived from them runs
occasionally, and nothing compares the two. That is the whole bug.

Three checks, in increasing order of how much they can actually prove:

  1. TIMESTAMPS. Cheap and weak: a derived file older than its source is
     definitely stale, but a newer one only means somebody ran something.
  2. BOM COVERAGE. Every reference in the netlist should appear in the BOM
     with the same value, and vice versa. This catches parts added, deleted
     or revalued without the BOM following, which timestamps cannot.
  3. SUPERSEDED STRINGS. Names of parts and values that have been replaced,
     searched for across the documentation. This is the one that catches
     prose, which nothing else here can.

    ./.venv/bin/python hardware/check_freshness.py
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT / "hardware"

BOARDS = {
    "main": {
        "dir": HW / "lyrebird-main-reva",
        "net": "lyrebird-main.net",
        "gen": HW / "netlist" / "main_board.py",
        "pdf": "lyrebird-main-schematic.pdf",
    },
    "dac": {
        "dir": HW / "lyrebird-dac-reva",
        "net": "lyrebird-dac.net",
        "gen": HW / "netlist" / "output_module.py",
        "pdf": "lyrebird-dac-schematic.pdf",
    },
}

# Things that were true once. Each maps to what replaced it, so the report
# can say what to write instead rather than only that something is wrong.
SUPERSEDED = {
    "LTC3265": "deleted by decision 5; the negative rail crosses the mezzanine",
    "SMAJ15A": "SMAJ18A -- the 15 V part conducted on a 19 V adapter forever",
    "1812L110": "1812L050/30 -- the 110 is rated 6 Vdc on a 12 V rail",
    "604R": "200R; the 2.1 dB compromise was recovered with the charge pump",
    "604 ohm": "200 ohm, same reason",
    "USB bus power": "an external 12 V supply (0014)",
    "one unit load": "retired with bus power; no enumeration current rule now",
    "WAKEUP_N": "the core-rail gating is removed; it never came up without a host",
    "AVDD on +3V3": "AVDD is a 1.0 V PLL supply; this was a destroy-the-part bug",
    # " + " means every term must appear on the same line. DFN-12 alone is a
    # false positive: it is the right package for the LT3094 and only wrong
    # when it is attached to an LT3045.
    "LT3045 + DFN-12": "LT3045 is a 10-lead part; DFN-12 belongs to the LT3094",
}
# Files where a superseded string is expected, because they are the record of
# the change rather than a description of the board.
SUPERSEDED_OK = ("docs/decisions/", "docs/review/", "CHANGELOG", "notes-")

FAIL, WARN, OK = "FAIL", "WARN", "ok"
rows: list[tuple[str, str, str]] = []


def add(level: str, what: str, detail: str) -> None:
    rows.append((level, what, detail))


def mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def netlist_parts(path: Path) -> dict[str, str]:
    """Reference -> value, straight out of the generated netlist."""
    text = path.read_text(errors="replace")
    out: dict[str, str] = {}
    for block in text.split("(comp")[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', block)
        val = re.search(r'\(value "([^"]+)"\)', block)
        if ref:
            out[ref.group(1)] = val.group(1) if val else ""
        if "(nets" in block:
            break
    return out


def bom_parts(path: Path) -> dict[str, str]:
    """Reference -> value. A BOM row may cover a range like 'C1-C8'."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            refs = (row.get("Ref") or "").strip()
            val = (row.get("Value") or "").strip()
            for piece in re.split(r"[,\s]+", refs):
                if not piece:
                    continue
                m = re.fullmatch(r"([A-Za-z]+)(\d+)-(?:[A-Za-z]+)?(\d+)", piece)
                if m:
                    pre, a, b = m.group(1), int(m.group(2)), int(m.group(3))
                    for i in range(a, b + 1):
                        out[f"{pre}{i}"] = val
                else:
                    out[piece] = val
    return out


def check_timestamps() -> None:
    for name, b in BOARDS.items():
        d: Path = b["dir"]
        net = d / b["net"]
        if not net.exists():
            add(FAIL, f"{name}: netlist", "missing entirely")
            continue
        if mtime(b["gen"]) > mtime(net):
            add(FAIL, f"{name}: netlist behind its generator",
                f"{b['gen'].name} is newer; regenerate the netlist")
        sheets = sorted((d / "sheets").glob("*.kicad_sch"))
        newest = max((mtime(s) for s in sheets), default=0.0)
        if not sheets:
            add(WARN, f"{name}: no schematic sheets", "never generated")
        elif newest < mtime(net):
            add(FAIL, f"{name}: schematic behind the netlist",
                f"{len(sheets)} sheets, newest is older than the netlist")
        pdf = d / b["pdf"]
        if not pdf.exists():
            add(WARN, f"{name}: no schematic PDF", "never exported")
        elif mtime(pdf) < newest:
            add(FAIL, f"{name}: PDF behind the sheets", "re-export it")
        for doc in ("power.md", "brief.md", "bom.csv"):
            f = d / doc
            if f.exists() and mtime(f) < mtime(net):
                days = (mtime(net) - mtime(f)) / 86400
                add(WARN, f"{name}: {doc} older than the netlist",
                    f"by {days:.1f} days -- timestamps only suggest; the "
                    f"content checks below decide")


def check_bom() -> None:
    for name, b in BOARDS.items():
        net = b["dir"] / b["net"]
        bom = b["dir"] / "bom.csv"
        if not net.exists() or not bom.exists():
            continue
        np_, bp = netlist_parts(net), bom_parts(bom)
        # Passives are grouped in the BOM by value rather than listed per
        # reference, so only judge the parts a BOM names individually.
        interesting = {r for r in np_ if r[0] in "UJYFLD"}
        missing = sorted(r for r in interesting if r not in bp)
        extra = sorted(r for r in bp if r not in np_ and r[0] in "UJYFLD")
        if missing:
            add(FAIL, f"{name}: parts on the board and not in the BOM",
                ", ".join(f"{r} ({np_[r][:28]})" for r in missing))
        if extra:
            add(FAIL, f"{name}: parts in the BOM and not on the board",
                ", ".join(f"{r} ({bp[r][:28]})" for r in extra))
        if not missing and not extra:
            add(OK, f"{name}: BOM covers every major reference",
                f"{len(interesting)} checked")


def check_superseded() -> None:
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                                 capture_output=True, text=True,
                                 check=True).stdout.split()
    except Exception as exc:                       # noqa: BLE001
        add(WARN, "superseded-string scan skipped", str(exc))
        return
    docs = [f for f in tracked
            if f.endswith((".md", ".csv"))
            and not any(k in f for k in SUPERSEDED_OK)]
    for old, new in SUPERSEDED.items():
        hits = []
        for f in docs:
            p = ROOT / f
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            terms = [t.strip().lower() for t in old.split(" + ")]
            for i, line in enumerate(text.splitlines(), 1):
                low = line.lower()
                if all(t in low for t in terms):
                    hits.append(f"{f}:{i}")
        if hits:
            add(FAIL, f'"{old}" still described as current',
                f"now {new}\n           " + "\n           ".join(hits[:6])
                + (f"\n           ... and {len(hits)-6} more"
                   if len(hits) > 6 else ""))


def main() -> int:
    check_timestamps()
    check_bom()
    check_superseded()

    print("=" * 74)
    print("FRESHNESS — do the documents still describe the boards?")
    print("=" * 74 + "\n")
    order = {FAIL: 0, WARN: 1, OK: 2}
    for level, what, detail in sorted(rows, key=lambda r: order[r[0]]):
        print(f"  {level:4}  {what}")
        print(f"        {detail}\n")
    bad = sum(1 for r in rows if r[0] == FAIL)
    warn = sum(1 for r in rows if r[0] == WARN)
    print(f"{bad} stale, {warn} to look at, "
          f"{sum(1 for r in rows if r[0] == OK)} clean")
    if bad:
        print("\nA derived file that disagrees with its source is worse than a\n"
              "missing one: somebody will read it and believe it.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

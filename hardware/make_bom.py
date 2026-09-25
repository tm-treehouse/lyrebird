#!/usr/bin/env python3
"""Generate both BOMs from the netlists, so they cannot drift from the boards.

The previous BOMs were written by hand and went twelve days stale. The main
board's listed three integrated circuits for a board that had seven, plus
diodes, a fuse, two inductors and three connectors; the module's still named
`U3a`/`U3b`/`U4a`/`U4b`, references that stopped existing when the register
symbol was replaced. Nothing noticed, because nothing compared them.

So the reference designators, values and footprints come from the netlist
every time this runs. What cannot be derived -- manufacturer, orderable part
number, why this part and not another -- lives in ANNOTATION below, keyed by
reference. A part on the board with no annotation is reported rather than
silently omitted, which is the failure the old files had.

`Status` distinguishes what was verified against a fetched datasheet from
what was not. That column is the point of the file: this project has been
wrong about a part that did not exist at its own rail voltage, and about a
footprint with the wrong lead count, both of which read as confident.

    ./.venv/bin/python hardware/make_bom.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT / "hardware"

V = "VERIFIED"        # read off a fetched datasheet during this project
U = "UNVERIFIED"      # plausible, not confirmed -- order at your own risk
D = "DECIDED"         # a decision record fixes this, datasheet not re-read

ANNOTATION: dict[str, tuple[str, str, str, str, str]] = {
    # ref: (manufacturer, MPN, rail/function, status, note)
    # ---------------------------------------------------------------- main
    "U1": ("Cologne Chip", "CCGM1A1", "+1V0 core, +2V5 banks", V,
           "Interpolation, third-order modulator, DWA rotation. All 324 balls "
           "checked against DS1001. 2.75 V absolute maximum on I/O is the "
           "constraint the whole part chain follows from. 0005, 0008."),
    "U2": ("FTDI", "FT601Q-B-T", "+3V3 VCC33, +2V5 VCCIO", V,
           "USB bridge, 245 Sync FIFO. Chosen because VCCIO can be 2.5 V, "
           "which removes level translation. Runs High Speed, not SuperSpeed, "
           "since isolation has no SuperSpeed option. 0005, 0014."),
    "U3": ("Analog Devices", "LT3045EDD#TRPBF", "+3V3 from +5V", V,
           "C_SET is 100 nF here, not 4.7 uF: PGFB tied to IN disables fast "
           "start, and 4.7 uF then ramps in 359 ms, putting the bridge's "
           "VCCIO 355 ms ahead of its own VCC33. This rail is digital only."),
    "U4": ("Analog Devices", "LTM4622IV#PBF", "+2V5 and +1V0", V,
           "Both RUN pins tied on. The enumeration gating 0009 specified was "
           "removed by 0014: it held the core rail off whenever no USB host "
           "was present, which on a wall-powered board is always."),
    "U5": ("Texas Instruments", "LMR33630ADDAR", "+12V to +5V", V,
           "36 V part on a 12 V rail. Everything downstream of +5V is "
           "unchanged from the bus-powered design, deliberately. 0014."),
    "U6": ("Macronix", "MX25R6435FM2IH0", "+2V5 VDD_WA", U,
           "64 Mbit, runs at 2.5 V where an ordinary 2.7 V part cannot. "
           "Supply range and quad-enable default not re-read. 0006."),
    "U7": ("Texas Instruments", "LMR33630ADDAR", "+12V to -6V", V,
           "Same part as U5, wired as an inverting buck-boost: its GND pin "
           "sits on the negative output and it sees VIN + |VOUT| = 18 V "
           "against a 36 V rating. Feeds the module across the mezzanine so "
           "the analog board needs no switching converter at all."),
    "D1": ("Vishay", "SS34-E3/57T", "reverse polarity", V,
           "Series Schottky. At 12 V its 0.35 V costs 210 mW against a supply "
           "with volts to spare, and buys the absence of a gate to protect. "
           "The FET is the better answer at 5 V and not here."),
    "D2": ("Vishay", "SMAJ18A-E3/61", "transient clamp", V,
           "18 V, not 15 V. The 15 V part conducts on a 19 V adapter at 41 mA "
           "and 117 C indefinitely without tripping the fuse -- a heater, not "
           "a protection. Must stay unidirectional: see D3."),
    "D3": ("Nexperia", "BAT54,215", "negative clamp", U,
           "Holds the reversed rail at -0.233 V against the converter's "
           "-0.3 V minimum. Without it D1's own leakage drags the node to "
           "-0.399 V, held only by D2's forward drop. Forward voltage at "
           "microamps is off the bottom of the datasheet curve."),
    "F1": ("Littelfuse", "1812L050/30MR", "input protection", V,
           "30 Vdc clears the 29.2 V TVS clamp; 100 A Imax clears 27.9 A of "
           "inrush; 0.50 A hold derates to 0.33 A at 70 C, still above the "
           "219 mA drawn. The 0.35 A part derates to 0.20 A and would "
           "nuisance-trip."),
    "L1": ("Wurth", "744314100", "+5V output", U,
           "10 uH, 3 A, shielded. Inductance from the LMR33630 datasheet's "
           "5 V table; the specific part is not confirmed."),
    "L2": ("Wurth", "744314100", "-6V output", U,
           "As L1. In the inverting configuration this returns to system "
           "ground rather than to the output."),
    "Y1": ("Abracon", "ABM8G-30.000MHZ-18-D2Y-T", "FT601Q reference", U,
           "30 MHz for the bridge. The ordering-suffix fields were never "
           "decoded against the datasheet."),
    "J1": ("Connfly", "DS1104-01", "USB", D,
           "USB 3.0 Micro-B. The SuperSpeed pairs go unrouted under 0014 -- "
           "High Speed carries 192/24 stereo at 1.9 % utilisation."),
    "J2": ("generic", "2x40 1.27 mm header", "mezzanine", D,
           "All 80 pins assigned: 28 element lines, clock, five control, two "
           "of -6V, five of +5V, the rest ground. 0007, interface.md."),
    "J3": ("generic", "2x05 1.27 mm header", "JTAG", D,
           "TMS, TCK and TDI carry 1k in series: 0006 specifies an ordinary "
           "FTDI adapter and the common ones drive a fixed 3.3 V into a "
           "2.75 V ball. A 2.5 V adapter is the better answer."),
    "J4": ("CUI Devices", "PJ-002AH", "12 V input", U,
           "2.1 x 5.5 mm, centre positive. Current rating and pin geometry "
           "not confirmed against a datasheet. 0014."),
    # -------------------------------------------------------------- module
    "U2_dac": ("Texas Instruments", "SN74AVC4T245PWR", "2.5 V / 3.3 V", V,
               "Translates the clock and the two oscillator enables across "
               "the domain boundary. 0012."),
    "U3_dac": ("Texas Instruments", "SN74ALVCH16374DGGR", "+3V3_REF", V,
               "VIH is 2.0 V at a 3.3 V supply, against the 2.4 V the FPGA "
               "guarantees -- the only family that clears it with CMOS rather "
               "than BiCMOS outputs, and the supply IS full scale. Bus hold "
               "is settled against UG1003. 0008, 0012."),
    "U1_dac": ("Texas Instruments", "SN74LVC1G74DCUR", "+3V3_CLK", V,
               "Divides the oscillator by two at a 50 % duty cycle by "
               "construction. Its own additive jitter is unpublished; no "
               "74-series datasheet gives one."),
    "U12_dac": ("Texas Instruments", "LMK1C1104PWR", "+3V3_CLK", V,
                "17.5 fs additive jitter, 50 ps output skew -- skew between "
                "register packages behaves like element mismatch. Both clock "
                "inputs of a package hang on one output."),
    "U7_dac": ("Texas Instruments", "OPA1612AID", "+/-5V analog", V,
               "1.1 nV/sqrt(Hz), 40 MHz. The most consequential choice here: "
               "the analog stage is the floor. Six amplifiers, three packages."),
    "U8_dac": ("Analog Devices", "LT3094EDD#TRPBF", "-5V analog", V,
               "Takes the mezzanine's -6 V. 13 pins, so DFN-12 is correct for "
               "this part where it was wrong for every LT3045."),
    "U5_dac": ("Analog Devices", "LT3045EDD#TRPBF", "precision rails", V,
               "10 pins: DFN-10, not the DFN-12 the netlist carried. The "
               "element reference rail IS full scale, so its noise is the "
               "converter's."),
    "Y1_dac": ("Crystek", "CCHD-957X-25-49.152", "+3V3_CLK", V,
               "1024x the element clock. Standby tri-states the output, which "
               "is what makes one shared OSC_RAW net legal. Footprint drawn "
               "here; its pad NUMBERING is still unresolved. 0012."),
    "Y2_dac": ("Crystek", "CCHD-957X-25-45.1584", "+3V3_CLK", V,
               "As Y1, for the 44.1 kHz family."),
    "J1_dac": ("generic", "2x40 1.27 mm header", "mezzanine", D,
               "Mates with the main board's J2. Both halves allocate all 80 "
               "pins and no pin's net differs across the connector."),
    "U9_dac": ("Analog Devices", "LT3045EDD#TRPBF", "+2V5 translator", V,
               "The translator's A port faces the header and must be 2.5 V, "
               "but the header carries only +5V and ground, so the module "
               "regulates its own. Nothing on this rail reaches the signal, "
               "so a cheaper part would do; it is an LT3045 for consistency."),
    "U14_dac": ("Analog Devices", "LT3045EDD#TRPBF", "+5V analog", V,
                "Takes the mezzanine's 5 V straight down to +4.94 V. This is "
                "what deleted the charge pump: the output swings +/-2.83 V "
                "peak and the OPA1612 reaches within 600 mV of its rails, so "
                "the positive supply needs about 3.5 V and the header already "
                "carried it. Only the negative rail ever needed help."),
    "J2_dac": ("Same Sky", "SJ1-3523N", "line out", V,
               "3.5 mm stereo, three conductors, no switch."),
}

BOARDS = {
    "main": (HW / "lyrebird-main-reva", "lyrebird-main.net", ""),
    "dac": (HW / "lyrebird-dac-reva", "lyrebird-dac.net", "_dac"),
}
HEADER = ["Ref", "Qty", "Value", "Manufacturer", "MPN", "Package",
          "Rail/Function", "Status", "Notes"]


def parts(netlist: Path) -> dict[str, tuple[str, str]]:
    text = netlist.read_text(errors="replace")
    out: dict[str, tuple[str, str]] = {}
    for block in text.split("(comp")[1:]:
        if "(nets" in block:
            break
        ref = re.search(r'\(ref "([^"]+)"\)', block)
        val = re.search(r'\(value "([^"]+)"\)', block)
        fp = re.search(r'\(footprint "([^"]+)"\)', block)
        if ref:
            out[ref.group(1)] = (val.group(1) if val else "",
                                 (fp.group(1) if fp else "").split(":")[-1])
    return out


def key(ref: str, suffix: str) -> int:
    return int(re.sub(r"\D", "", ref) or 0)


def main() -> int:
    missing_all = []
    for name, (d, netname, suffix) in BOARDS.items():
        p = parts(d / netname)
        rows = []
        # Majors, one row each, annotated.
        majors = sorted((r for r in p if r[0] in "UJYFLD"),
                        key=lambda r: (r[0], key(r, suffix)))
        for ref in majors:
            val, fp = p[ref]
            ann = ANNOTATION.get(ref + suffix) or ANNOTATION.get(ref)
            if ann is None:
                # Same package and value as an annotated sibling? Reuse it.
                twin = next((o for o in majors
                             if p[o] == p[ref]
                             and (ANNOTATION.get(o + suffix)
                                  or ANNOTATION.get(o))), None)
                ann = (ANNOTATION.get(twin + suffix)
                       or ANNOTATION.get(twin)) if twin else None
            if ann is None:
                missing_all.append(f"{name}:{ref} ({val})")
                ann = ("", "", "", "UNANNOTATED",
                       "On the board and not described here. Add it to "
                       "ANNOTATION in hardware/make_bom.py.")
            mfr, mpn, rail, status, note = ann
            rows.append([ref, 1, val, mfr, mpn, fp, rail, status, note])
        # Passives, grouped by value and package.
        groups: dict[tuple[str, str], list[str]] = {}
        for ref in p:
            if ref[0] in "RC":
                groups.setdefault(p[ref], []).append(ref)
        for (val, fp), refs in sorted(groups.items(),
                                      key=lambda kv: (kv[0][1], kv[0][0])):
            refs.sort(key=lambda r: (r[0], key(r, suffix)))
            kind = "Capacitor" if refs[0][0] == "C" else "Resistor"
            rows.append([" ".join(refs) if len(refs) <= 6
                         else f"{refs[0]}-{refs[-1]}",
                         len(refs), val, "", "", fp, "", "GROUPED",
                         f"{kind}s, grouped by value. "
                         f"{len(refs)} places."])
        out = d / "bom.csv"
        with out.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(HEADER)
            w.writerows(rows)
        counts = Counter(r[7] for r in rows)
        print(f"  {out.relative_to(ROOT)}: {len(rows)} rows, "
              f"{sum(r[1] for r in rows)} parts  "
              + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    if missing_all:
        print("\nParts with no annotation (listed, not hidden):")
        for m in missing_all:
            print(f"  {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

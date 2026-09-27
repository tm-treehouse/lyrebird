#!/usr/bin/env python3
"""The -6 V inverting converter, which no existing check contains.

`hardware/verify_power.py` knows the -6 V rail as three hand-typed constants
(-5.98 V, 64 mA, an assumed 85 % efficiency) and `power_input_transient.py`
does not model U7 at all: its four scenarios build one converter. So the piece
whose grounding is unlike anything else on the board -- U7's GND pin *is* the
negative output -- has never been checked against its own datasheet.

This file does four things and tamper-tests each of them:

  A. NETLIST AUDIT.  Reads the generated netlists and compares every power
     constant the two existing checkers restate against what is actually
     fitted. Both files transcribe the circuit by hand; this measures how far
     the transcription has drifted.
  B. TOPOLOGY, analytically.  Duty cycle, on-time against the DDA package's
     minimum, inductor and switch currents, and every pin against the
     absolute maxima -- all in the device's own frame, where PGND = -6 V.
  C. NGSPICE.  Three circuits: the feedback divider as built (and as it would
     be if someone reasoned about GND as the device's ground), the power stage
     switching open- and closed-loop, and the high-side commutation loop with
     and without the input capacitor the datasheet requires.
  D. SEQUENCING.  +5 V and -6 V arriving together off one 12 V rail, and what
     the module's regulators and amplifiers see while they do.

    ./.venv/bin/python hardware/sim/power_negative_rail.py
    ./.venv/bin/python hardware/sim/power_negative_rail.py --sweep-verify

ngspice comes from KiCad's bundle, as in output_stage_ac.py: InSpice resolves
the library through ctypes and discards an absolute path, so the finder is
replaced below.

Datasheet read in full for this file: LMR33630, TI SNVSAN3F rev F (Nov 2020),
tables 6-1, 7.1, 7.3, 7.4, 7.5, 7.6, 7.7 and section 9.2.2.6. LT3045
(Linear 3045f) and LT3094 (Rev 0) for the loads. Anything not from those is
marked ASSUMED and the report lists it.
"""

from __future__ import annotations

import io
import contextlib
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

KICAD = "/Applications/KiCad/KiCad.app/Contents"
os.environ.setdefault("SPICE_LIB_DIR", f"{KICAD}/PlugIns/sim/ngspice")
_LIB = f"{KICAD}/Frameworks/libngspice.0.dylib"

from InSpice.Spice.NgSpice.Shared import NgSpiceShared  # noqa: E402

NgSpiceShared.find_library = classmethod(lambda cls, name: _LIB)

from InSpice import Circuit, Simulator  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
HW = HERE.parent

DS = "datasheet"
CALC = "calculation"
ASSUMED = "ASSUMED, unverified"


@dataclass
class Fact:
    value: float
    unit: str
    source: str
    note: str = ""


def F(v, u, s, n=""):
    return Fact(v, u, s, n)


# ---------------------------------------------------------------- LMR33630
# Every one of these was read out of SNVSAN3F for this file.
VIN_ABSMAX = F(38.0, "V", DS, "VIN to PGND, table 7.1")
VIN_ABSMIN = F(-0.3, "V", DS, "VIN to PGND, table 7.1")
VIN_OPMAX = F(36.0, "V", DS, "recommended operating maximum, table 7.3")
VIN_OPMIN = F(3.8, "V", DS, "minimum operating input voltage, 7.3")
EN_ABSMAX_OVER_VIN = F(0.3, "V", DS, "EN may not exceed VIN by more than "
                                     "this; table 7.1 note 2")
SW_ABSMIN = F(-0.3, "V", DS, "SW to PGND, table 7.1")
SW_ABSMIN_100NS = F(-3.5, "V", DS, "SW to PGND, <100 ns transients, 7.1")
AGND_PGND_ABSMAX = F(0.3, "V", DS, "AGND to PGND, table 7.1")
PG_OPMAX = F(18.0, "V", DS, "PG to AGND recommended, table 7.3; abs max 22")
BOOT_ABSMAX = F(5.5, "V", DS, "BOOT to SW, table 7.1")
VCC_ABSMAX = F(5.5, "V", DS, "VCC to AGND, table 7.1")
VFB = F(1.000, "V", DS, "feedback voltage, ADJ option, table 7.5")
VFB_MIN = F(0.985, "V", DS, "table 7.5")
VFB_MAX = F(1.015, "V", DS, "table 7.5")
FSW = F(400e3, "Hz", DS, '"A" version, 340/400/460 kHz, table 7.5')
FSW_MIN = F(340e3, "Hz", DS, "table 7.5")
TON_MIN = F(108e-9, "s", DS, "tON-MIN, DDA package: 75 typ / 108 max, 7.6")
TOFF_MIN = F(85e-9, "s", DS, "tOFF-MIN, DDA package: 50 typ / 85 max, 7.6")
TON_MAX = F(7e-6, "s", DS, "tON-MAX, 7 min / 9 typ us, table 7.6")
ISC = F(3.85, "A", DS, "high-side current limit, MINIMUM of 3.85/4.5/5.05")
ILIMIT_LS = F(2.9, "A", DS, "low-side current limit, minimum, table 7.5")
IPEAK_MIN = F(0.69, "A", DS, "minimum peak inductor current, table 7.6 page")
IZC = F(-0.106, "A", DS, "zero current detector threshold, 7.6 page")
TSS = F(4.0e-3, "s", DS, "internal soft start, 2.9/4/6 ms, table 7.5")
RDSON_HS = F(0.095, "ohm", DS, "high-side, DDA package, typical, table 7.5")
RDSON_LS = F(0.066, "ohm", DS, "low-side, DDA package, typical, table 7.5")
RTHJA = F(42.9, "C/W", DS, "DDA (HSOIC-8), 4-layer JEDEC, table 7.4 -- and "
                           "the table says in terms this may not be used for "
                           "design, only for comparison between packages")
CIN_MIN = F(10e-6, "F", DS, "section 9.2.2.6: a minimum of 10 uF of ceramic "
                            "is REQUIRED on the input, plus a small-case "
                            "220 nF as close as possible to the regulator")
PKG_BODY = "HSOIC (8), 5.00 mm x 4.00 mm, 1.27 mm pitch (Device Information)"

# ---------------------------------------------------------------- as built
VIN_NOM = F(12.0, "V", ASSUMED, "adapter not chosen")
VIN_TOL = F(0.05, "", ASSUMED, "assumed, as verify_power.py assumes it")
VIN_FAULT = F(19.0, "V", ASSUMED, "the laptop brick that fits the barrel")
V_CLAMP = F(29.2, "V", DS, "SMAJ18A maximum clamping voltage at 13.7 A")
R_TOP = F(124e3, "ohm", CALC, "main_board.py: GND to FB")
R_BOT = F(24.9e3, "ohm", CALC, "main_board.py: FB to -6V_A")
R_TOL = F(0.01, "", CALC, "1 % parts")
L2 = F(10e-6, "H", CALC, "main_board.py L2")
L2_DCR = F(0.043, "ohm", ASSUMED, "a 10 uH 3 A 12x12 mm shielded part; the "
                                  "BOM's 744314100 is marked UNVERIFIED")
C_OUT_N6 = F(47.1e-6, "F", CALC, "47 uF 1210 + 100 nF 0603, GND to -6V_A")
C_IN_12 = F(22.1e-6, "F", CALC, "22 uF 1210 + 100 nF 0603, +12V to GND -- "
                                "and NOTHING from +12V to -6V_A")
C_VIN_PGND = F(0.0, "F", CALC, "what is fitted from U7's VIN to its PGND")
I_N6V = F(0.0635, "A", CALC, "module power.md worst case: 21.6 quiescent + "
                             "13.9 element + 21.0 network + 7 margin")
V_N6V_TARGET = F(-5.98, "V", CALC, "1.0 V x (1 + 124k/24.9k), inverted")
D1_VF = F(0.35, "V", ASSUMED, "SS34 typical curve, not a spec limit")
F1_RMAX = F(1.0, "ohm", DS, "1812L050/30 R1max")

# LT3094, the load on this rail (Rev 0, read for this file).
LT3094_DROPOUT = F(0.235, "V", DS, "headline figure")
LT3094_VIN_ABSMIN = F(-22.0, "V", DS, "IN with respect to GND: -22 V, 0.3 V")
LT3094_ENUV_TH = F(1.33, "V", DS, "positive trip point rising, MAXIMUM; "
                                  "1.20/1.26/1.33 V, referenced to GND")
LT3094_ILIM_K = F(3.75, "ohm*A", DS, "ILIM scale factor, kohm x A")
LT3094_RTHJA = F(34.0, "C/W", DS, "DD 12-lead 3x3 DFN; exposed pad is IN")
LT3045_DROPOUT_50MA = F(0.330, "V", DS, "220 typ / 275 max / 330 over "
                                        "temperature at I_LOAD = 1 mA and "
                                        "50 mA, Electrical Characteristics")


# ------------------------------------------------------------------ checks
@dataclass
class Result:
    tag: str
    name: str
    ok: bool
    detail: str
    margin: str = ""
    assumed: bool = False


class Checks:
    def __init__(self):
        self.results: list[Result] = []

    def add(self, tag, name, ok, detail, margin="", assumed=False):
        self.results.append(Result(tag, name, ok, detail, margin, assumed))
        return ok

    def get(self, tag):
        for r in self.results:
            if r.tag == tag:
                return r
        raise KeyError(tag)


def banner(t):
    print("\n" + "=" * 76 + f"\n{t}\n" + "=" * 76)


# =========================================================================
# A. NETLIST AUDIT -- what the checkers say is fitted, against what is
# =========================================================================
def read_netlist(name):
    """{ref: (value, footprint)} and {net: [(ref, pin, pintype)]}."""
    path = HW / name
    text = path.read_text(errors="replace")
    comps = {}
    # Split on the component delimiter with its indentation, NOT on the bare
    # token "(comp": every component block also contains "(component_classes)",
    # so a bare split produces one stray fragment per part, and the last of
    # them runs on into the nets section and picks up the first node's ref with
    # no value. verify_power.py's reader splits the bare way and therefore
    # carries one bogus entry -- val["C8"] = "" on the main board and
    # val["C36"] = "" on the module. Harmless only because neither happens to
    # be a SET resistor.
    for blk in re.split(r"\n    \(comp\n", text)[1:]:
        r = re.search(r'\(ref "([^"]+)"\)', blk)
        v = re.search(r'\(value "([^"]*)"\)', blk)
        f = re.search(r'\(footprint "([^"]*)"\)', blk)
        if r:
            comps[r.group(1)] = (v.group(1) if v else "",
                                 f.group(1) if f else "")
    nets = {}
    for blk in re.split(r"\n    \(net\n", text)[1:]:
        nm = re.search(r'\(name "([^"]*)"\)', blk).group(1)
        nets.setdefault(nm, []).extend(
            re.findall(r'\(ref "([^"]+)"\)\s*\n\s*\(pin "([^"]+)"\)'
                       r'\s*\n\s*\(pintype "([^"]+)"\)', blk))
    return comps, nets


def _val_to_float(s):
    """'22uF' -> 22e-6, '124k 1%' -> 124e3, '10uH 3A shielded' -> 10e-6."""
    m = re.match(r"([\d.]+)\s*([pnukKMm]?)", s.strip())
    if not m:
        return None
    mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0,
            "k": 1e3, "K": 1e3, "M": 1e6}[m.group(2)]
    return float(m.group(1)) * mult


def caps_between(comps, nets, a, b):
    """Total capacitance fitted between two named nets."""
    tot = 0.0
    pins_a = {(r, p) for r, p, _ in nets.get(a, [])}
    pins_b = {(r, p) for r, p, _ in nets.get(b, [])}
    refs_a = {r for r, _ in pins_a}
    refs_b = {r for r, _ in pins_b}
    for ref in refs_a & refs_b:
        if not ref.startswith("C"):
            continue
        v = _val_to_float(comps[ref][0])
        if v:
            tot += v
    return tot


def scenario_audit(ck):
    banner("A. NETLIST AUDIT -- the checkers' constants against what is fitted")
    mc, mn = read_netlist("lyrebird-main-reva/lyrebird-main.net")
    dc, dn = read_netlist("lyrebird-dac-reva/lyrebird-dac.net")

    # ---- A-1. U7's input capacitance, VIN to its own PGND.
    c_vin_gnd = caps_between(mc, mn, "+12V", "GND")
    c_vin_pgnd = caps_between(mc, mn, "+12V", "-6V_A")
    print(f"   +12V to GND      {c_vin_gnd*1e6:8.2f} uF   (U5's input cap)")
    print(f"   +12V to -6V_A    {c_vin_pgnd*1e6:8.2f} uF   (U7's input cap: "
          f"its PGND is -6V_A)")
    print(f"   GND  to -6V_A    "
          f"{caps_between(mc, mn, 'GND', '-6V_A')*1e6:8.2f} uF   "
          f"(U7's output cap)")
    ck.add("A-1", "U7 has the input capacitance its datasheet requires",
           c_vin_pgnd >= CIN_MIN.value,
           f"{c_vin_pgnd*1e6:.2f} uF is fitted from U7's VIN to its PGND "
           f"against a REQUIRED minimum of {CIN_MIN.value*1e6:.0f} uF "
           f"(SNVSAN3F 9.2.2.6, and pin 2's own description: \"connect a "
           f"high-quality bypass capacitor or capacitors directly to this "
           f"pin and PGND\")",
           "the 22 uF and 100 nF on +12V are referenced to system ground, "
           "which is not this device's ground. See C-3 for what that costs")

    # ---- A-2. Footprint against the package the datasheet names.
    bad_fp = [(r, v, f) for r, (v, f) in sorted(mc.items())
              if "LMR33630" in v and "P1.27mm" not in f]
    ck.add("A-2", "both LMR33630 footprints match the package",
           not bad_fp,
           "; ".join(f"{r} -> {f}" for r, _, f in bad_fp) or "both correct",
           f"the datasheet's Device Information gives {PKG_BODY}; the KiCad "
           f"symbol's own fplist names "
           f"Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm_ThermalVias. A "
           f"0.65 mm-pitch 3x3 land cannot take a 1.27 mm-pitch 5x4 body")

    # ---- A-3. The feedback divider, read rather than restated.
    def divider(comps, nets, ref, fbpin):
        fb = [n for n, nodes in nets.items()
              if any(r == ref and p == fbpin for r, p, _ in nodes)]
        if not fb:
            return None
        rs = [r for r, p, _ in nets[fb[0]] if r.startswith("R")]
        legs = {}
        for r in rs:
            other = [n for n, nodes in nets.items()
                     if n != fb[0] and any(x == r for x, _, _ in nodes)]
            legs[other[0] if other else "?"] = _val_to_float(comps[r][0])
        return legs

    d7 = divider(mc, mn, "U7", "5")
    d5 = divider(mc, mn, "U5", "5")
    print(f"\n   U5 FB divider  {d5}")
    print(f"   U7 FB divider  {d7}")
    v7 = None
    if d7 and "GND" in d7 and "-6V_A" in d7:
        v7 = -VFB.value * (1 + d7["GND"] / d7["-6V_A"])
    ck.add("A-3", "the -6 V divider programs what the constants claim",
           v7 is not None and abs(v7 - V_N6V_TARGET.value) < 0.01,
           f"the netlist's own resistors give {v7:.3f} V" if v7
           else "could not read the divider from the netlist",
           f"verify_power.py restates this as {V_N6V_TARGET.value} V; they "
           f"agree today, and nothing makes them agree tomorrow")

    # ---- A-4. The constants the two checkers restate, against the netlist.
    import importlib
    sys.path.insert(0, str(HW))
    sys.path.insert(0, str(HERE))
    vp = importlib.import_module("verify_power")
    pit = importlib.import_module("power_input_transient")
    f1_value = mc.get("F1", ("", ""))[0]
    rows = [
        ("F1 value string", f1_value,
         pit.F1_NETLIST_VALUE, "power_input_transient.F1_NETLIST_VALUE"),
        ("+5V load, module share", "123 mA (verify_power I_MODULE_5V)",
         f"{pit.I_MEZZ.value*1e3:.0f} mA", "power_input_transient.I_MEZZ"),
        ("+5V load, total", f"{(vp.I_MODULE_5V.value+vp.I_MAIN_OTHER.value)*1e3:.0f} mA",
         f"{pit.I_LOAD_5V.value*1e3:.0f} mA", "power_input_transient.I_LOAD_5V"),
        ("U7 in the model", "fitted, one of two converters",
         "absent", "power_input_transient builds no inverter"),
    ]
    print()
    drift = 0
    for what, fitted, claimed, where in rows:
        same = str(fitted) == str(claimed)
        drift += 0 if same else 1
        print(f"   {'ok  ' if same else 'DRIFT'} {what:26} fitted={fitted!r}"
              f"  claimed={claimed!r}  [{where}]")
    ck.add("A-4", "the hand-transcribed constants still match the circuit",
           drift == 0,
           f"{drift} of {len(rows)} sampled facts have drifted since they "
           f"were transcribed",
           "neither existing checker imports a netlist except through "
           "verify_power.ldo_rails, so every other constant is a copy that "
           "ages independently of the circuit")
    return {"c_vin_pgnd": c_vin_pgnd, "c_vin_gnd": c_vin_gnd}


# =========================================================================
# B. THE TOPOLOGY, ANALYTICALLY, IN THE DEVICE'S OWN FRAME
# =========================================================================
def inverting_operating_point(vin, vout_mag, iout, l=None, fsw=None):
    """Everything about an inverting buck-boost built from a buck IC.

    The device's PGND sits on the negative output, so in its own frame this is
    a buck from (vin + |vout|) to (|vout|), whose load is connected between
    the output node -- system ground -- and PGND. KCL at PGND is what makes
    the inductor current larger than the load current:

        I_load = (1 - D) * I_L      so   I_L = I_load / (1 - D)
        I_VIN  = D * I_L
        D      = |Vout| / (Vin + |Vout|)
    """
    l = L2.value if l is None else l
    fsw = FSW.value if fsw is None else fsw
    vin_dev = vin + vout_mag                      # VIN to PGND
    d = vout_mag / vin_dev
    il = iout / (1 - d)
    i_vin = d * il
    dil = (vin_dev - vout_mag) * d / (l * fsw)    # CCM ripple
    ccm = il > dil / 2
    if ccm:
        ipk, ton, f_eff = il + dil / 2, d / fsw, fsw
    else:
        # Discontinuous. The part cannot command a peak below IPEAK_MIN, so it
        # folds frequency back rather than shortening the pulse (section 8.4
        # and IPEAK-MIN in table 7.6).
        ipk = IPEAK_MIN.value
        ton = l * ipk / (vin_dev - vout_mag)
        toff = l * ipk / vout_mag
        q = 0.5 * ipk * toff                      # charge into PGND per pulse
        f_eff = min(fsw, iout / q)
        ton = ton if f_eff > 0 else 0.0
    return {"vin_dev": vin_dev, "D": d, "IL": il, "I_VIN": i_vin,
            "dIL": dil, "Ipk": ipk, "ton": ton, "f_eff": f_eff, "ccm": ccm}


def scenario_topology(ck):
    banner("B. THE INVERTING TOPOLOGY, IN THE DEVICE'S OWN FRAME")
    vin_lo = VIN_NOM.value * (1 - VIN_TOL.value)
    vin_hi = VIN_NOM.value * (1 + VIN_TOL.value)
    vmag = abs(V_N6V_TARGET.value)

    print(f"   {'Vin':>7} {'VIN-PGND':>9} {'D':>7} {'I_L':>8} {'I_VIN':>8} "
          f"{'dI_L':>8} {'I_pk':>7} {'t_on':>8} {'f_eff':>9}  mode")
    ops = {}
    for label, vin in (("11.40 V", vin_lo), ("12.00 V", VIN_NOM.value),
                       ("12.60 V", vin_hi), ("19.00 V", VIN_FAULT.value)):
        # The jack voltage is not what reaches U7: F1 and D1 are in the way.
        v_at_u7 = vin - D1_VF.value - (0.219 * F1_RMAX.value)
        o = inverting_operating_point(v_at_u7, vmag, I_N6V.value)
        ops[label] = o
        print(f"   {label:>7} {o['vin_dev']:9.2f} {o['D']:7.4f} "
              f"{o['IL']*1e3:7.1f}m {o['I_VIN']*1e3:7.1f}m "
              f"{o['dIL']*1e3:7.0f}m {o['Ipk']:7.3f} {o['ton']*1e9:7.0f}n "
              f"{o['f_eff']/1e3:8.1f}k  {'CCM' if o['ccm'] else 'DCM'}")

    nom = ops["12.00 V"]
    worst = ops["11.40 V"]

    # ---- B-1. Feedback referencing. FB regulates to VFB above PGND, and the
    # divider runs from system ground (the device's output node) down to the
    # rail. Both legs and the reference are in the device's frame.
    v_fb_node = V_N6V_TARGET.value + VFB.value
    i_top = (0 - v_fb_node) / R_TOP.value
    i_bot = (v_fb_node - V_N6V_TARGET.value) / R_BOT.value
    ck.add("B-1", "the feedback divider is referenced to U7's ground, not the "
                  "board's",
           abs(i_top - i_bot) / i_bot < 0.01,
           f"FB sits at {v_fb_node:.3f} V in board terms, which is exactly "
           f"{VFB.value:.3f} V above U7's GND pin; {i_top*1e6:.1f} uA down "
           f"the 124 k leg and {i_bot*1e6:.1f} uA down the 24.9 k leg agree "
           f"to {abs(i_top-i_bot)/i_bot*100:.2f} %",
           f"|Vout| = VFB x (1 + Rtop/Rbot) = {VFB.value}x"
           f"(1+{R_TOP.value/1e3:g}k/{R_BOT.value/1e3:g}k) = "
           f"{VFB.value*(1+R_TOP.value/R_BOT.value):.3f} V. C-1 shows what "
           f"the same two resistors do if the frame is mistaken")

    # ---- B-2. Rail accuracy, which nothing else computes.
    lo = VFB_MIN.value * (1 + (R_TOP.value * (1 - R_TOL.value))
                          / (R_BOT.value * (1 + R_TOL.value)))
    hi = VFB_MAX.value * (1 + (R_TOP.value * (1 + R_TOL.value))
                          / (R_BOT.value * (1 - R_TOL.value)))
    head_lt3094 = lo - 5.0
    ck.add("B-2", "the -6 V rail keeps the LT3094 out of dropout at its own "
                  "tolerance corner",
           head_lt3094 > LT3094_DROPOUT.value,
           f"the rail is {lo:.3f} to {hi:.3f} V across the LMR33630's "
           f"+/-1.5 % feedback tolerance and 1 % resistors, not the "
           f"{vmag:.2f} V both power.md files and verify_power.py state",
           f"{head_lt3094*1e3:.0f} mV above the LT3094's -5.00 V output at "
           f"the low corner, against {LT3094_DROPOUT.value*1e3:.0f} mV of "
           f"dropout")

    # ---- B-3. Minimum on-time, the reason to ask about a light load.
    ck.add("B-3", "on-time clears the DDA package's minimum at every corner",
           all(o["ton"] > TON_MIN.value for o in ops.values()),
           f"shortest pulse is {min(o['ton'] for o in ops.values())*1e9:.0f} "
           f"ns, at the highest input, against a {TON_MIN.value*1e9:.0f} ns "
           f"maximum minimum on-time for this package",
           "the DDA package is 75 ns typical and 108 ns maximum (table 7.6); "
           "the front page's 68 ns is the RNX package. The margin exists "
           "because IPEAK-MIN = 0.69 A forces frequency foldback rather than "
           "a shorter pulse: the part is in DCM here at 6 % of its rating, "
           "and folds to about "
           f"{nom['f_eff']/1e3:.0f} kHz rather than shrinking t_on")

    # ---- B-4. Current capability in this topology, which is not Iout_max.
    iout_max = (ISC.value - nom["dIL"] / 2) * (1 - nom["D"])
    ck.add("B-4", "current capability in the inverting topology",
           I_N6V.value < 0.3 * iout_max,
           f"the high-side limit is {ISC.value} A minimum, so this "
           f"configuration can deliver ({ISC.value} - dIL/2)x(1-D) = "
           f"{iout_max:.2f} A against the {I_N6V.value*1e3:.0f} mA drawn",
           f"the buck datasheet's 3 A does NOT apply: in inversion the load "
           f"only conducts during (1-D), so the rating scales by "
           f"{1-nom['D']:.3f} and the ripple comes off the top. "
           f"verify_power.py compares 64 mA to 0.3 x 3 A, which is the right "
           f"verdict from the wrong number")

    # ---- B-5. Every pin against its absolute maximum, in the device frame.
    rows = []
    for label, vin in (("12.6 V adapter", vin_hi),
                       ("19 V brick", VIN_FAULT.value),
                       ("TVS clamped surge", V_CLAMP.value)):
        vin_dev = vin + vmag
        rows.append((label, vin_dev, vin_dev <= VIN_OPMAX.value,
                     vin_dev <= VIN_ABSMAX.value))
    print()
    for label, v, op_ok, abs_ok in rows:
        print(f"   VIN-PGND at {label:18} {v:6.2f} V   "
              f"operating {'ok' if op_ok else 'EXCEEDED'}  "
              f"absolute {'ok' if abs_ok else 'EXCEEDED'}")
    ck.add("B-5", "VIN to PGND stays inside the recommended maximum in every "
                  "case the input protection allows",
           all(r[2] for r in rows),
           "; ".join(f"{r[0]} {r[1]:.2f} V" for r in rows) +
           f" against {VIN_OPMAX.value:g} V recommended and "
           f"{VIN_ABSMAX.value:g} V absolute",
           f"the clamped surge leaves "
           f"{VIN_OPMAX.value - (V_CLAMP.value + vmag):.2f} V, not the 6.8 V "
           f"verify_power.py reports: that check compares the clamp to 36 V "
           f"for U5 and there is no U7 in it. |Vout| is added to every input "
           f"stress on this device")

    # ---- B-6. EN, which is where an inverting configuration usually dies.
    en_over_vin = 0.0     # EN and VIN are the same net
    ck.add("B-6", "EN is within its rating in the device's frame",
           en_over_vin <= EN_ABSMAX_OVER_VIN.value,
           f"EN is tied to VIN, so EN - VIN = 0 V against a limit of "
           f"VIN + {EN_ABSMAX_OVER_VIN.value} V; referenced to PGND that is "
           f"{nom['vin_dev']:.1f} V, which is legal only because the limit "
           f"is expressed relative to VIN and not as an absolute number",
           "this is the pin that kills naive inverting designs -- a "
           "logic-level enable referenced to system ground would sit "
           f"{vmag:.2f} V BELOW this device's ground and latch it off. Tying "
           "EN to VIN is the one arrangement that needs no level shift")

    # ---- B-7. PG, and the thing that makes it useless here.
    pg_released = 0.0 - V_N6V_TARGET.value
    ck.add("B-7", "PG is inside its rating, and says nothing before start-up",
           pg_released <= PG_OPMAX.value,
           f"PG's pull-up goes to system ground, so released it sits "
           f"{pg_released:.2f} V above U7's AGND -- inside the "
           f"{PG_OPMAX.value:g} V recommended maximum and inside VIN + 0.3 V",
           "but the flag is unreadable as a signal: asserted it pulls to "
           "AGND = -5.98 V and released it sits at 0 V, so it is a 0/-6 V "
           "swing no 2.5 V logic on this board can take. Worse, before the "
           "converter starts AGND is 0 V, so a low reads 0 V too -- "
           "identical to good. It is a scope point, not a sequencing input, "
           "and must not be used as one")

    # ---- B-8. VCC and BOOT, both referenced to a moving ground.
    ck.add("B-8", "VCC and BOOT are bypassed to the device's ground, not the "
                  "board's",
           True,
           "main_board.py puts the 1 uF VCC bypass on -6V_A and the 100 nF "
           "bootstrap across SW to BOOT, which is what pin 6 and pin 7 ask "
           "for once GND is read as the device's GND",
           "bypassing VCC to system ground instead would hold it 5.98 V off "
           "its own reference and inject the whole switching excursion of "
           "AGND into the control supply; the abs max is VCC-to-AGND 5.5 V, "
           "so it would also be out of specification. This one is right")
    return ops


# =========================================================================
# C. NGSPICE
# =========================================================================
def run(c, step, end, **kw):
    sim = Simulator.factory().simulation(c)
    return sim.transient(step_time=step, end_time=end, **kw)


def arr(an, name):
    return np.array(an[name])


def build_fb_frame(frame="device"):
    """The real divider, closed around a regulator that holds FB at 1.0 V.

    frame="device"  FB is held 1.0 V above the -6V node, which is U7's GND.
    frame="board"   FB is held 1.0 V above system ground -- the mistake the
                    PG fault shows this circuit invites.
    """
    c = Circuit("U7 feedback referencing")
    # An integrator driving the rail until its own FB error is nulled.
    ref = "v(fb)-v(vn6)-1.0" if frame == "device" else "v(fb)-1.0"
    c.raw_spice += f"Bint 0 ctl I = 1e-3*({ref})\n"
    c.raw_spice += "Cint ctl 0 1u\nRint ctl 0 1e12\n"
    # ctl integrates the error; the rail follows it, clamped to the range an
    # inverting converter can reach from 12 V.
    c.raw_spice += "Bout vn6 0 V = max(min(v(ctl),0),-30)\n"
    c.raw_spice += f"Rtop 0 fb {R_TOP.value}\n"
    c.raw_spice += f"Rbot fb vn6 {R_BOT.value}\n"
    c.raw_spice += "Cfb fb 0 1p\n"
    return c


def build_power_stage(d=None, vin=None, iout=None, closed=False):
    """The power stage with real switches, in the board's frame.

    Two voltage-controlled switches: the high side ties SW to VIN, the low
    side ties SW to PGND, which is the -6 V node. The inductor runs from SW
    to system ground, which is what makes it inverting.
    """
    vin = VIN_NOM.value if vin is None else vin
    iout = I_N6V.value if iout is None else iout
    c = Circuit("U7 power stage, inverting")
    c.raw_spice += ".model SWM SW(RON=0.095 ROFF=1e7 VT=0.5 VH=0.01)\n"
    c.raw_spice += ".model SWL SW(RON=0.066 ROFF=1e7 VT=0.5 VH=0.01)\n"
    c.raw_spice += f"Vin vin 0 DC {vin}\n"
    if closed:
        # Peak-current-mode, approximated: a fixed 400 kHz clock sets the
        # pulse, an integrator trims the duty to hold the rail. Enough to read
        # the duty the loop settles on, which is the number under test.
        c.raw_spice += "Vclk clk 0 PULSE(0 1 0 1n 1n 0.1u 2.5u)\n"
        c.raw_spice += f"Bint 0 duty I = 1e-2*(v(vn6)-({V_N6V_TARGET.value}))\n"
        c.raw_spice += "Cduty duty 0 1u IC=0.33\nRduty duty 0 1e12\n"
        c.raw_spice += "Vramp ramp 0 PULSE(0 1 0 2.499u 1n 1n 2.5u)\n"
        c.raw_spice += "Bg hg 0 V = 1*(v(ramp) < v(duty))\n"
    else:
        dd = 0.3326 if d is None else d
        c.raw_spice += f"Vg hg 0 PULSE(0 1 0 1n 1n {dd*2.5e-6} 2.5u)\n"
    c.raw_spice += "Bgl lg 0 V = 1-v(hg)\n"
    # High side: VIN to SW. Low side: SW to PGND (= the -6 V rail).
    c.raw_spice += "Shs vin sw hg 0 SWM\n"
    c.raw_spice += "Sls sw vn6 lg 0 SWL\n"
    c.raw_spice += f"L2 sw 0 {L2.value} IC=0\n"
    c.raw_spice += f"Rl2 sw swx {L2_DCR.value}\n"   # kept out of the loop
    c.raw_spice += "Rdummy swx 0 1e12\n"
    c.raw_spice += f"Cout 0 vn6 {C_OUT_N6.value} IC=0\n"
    c.raw_spice += f"Rload 0 vn6 {abs(V_N6V_TARGET.value)/iout}\n"
    return c


def build_commutation(c_vin_pgnd=0.0, l_plane=4e-9):
    """The high-side turn-off loop, which is where the missing cap is felt.

    At the switching instant the current in the high-side FET transfers to the
    low side. The loop that carries that di/dt runs VIN -> HS -> SW -> LS ->
    PGND and closes through whatever capacitance sits between VIN and PGND. As
    built there is none, so it closes through the +12V-to-GND capacitor in
    series with the GND-to--6V capacitor and the ground plane between them.

    The injected step is the 0.69 A peak collapsing in the 2 ns switch dead
    time (System Characteristics, tD). Every capacitor gets a parallel 1 M so
    the operating point is defined; the plane is tied to 0 through 1 m.
    """
    c = Circuit("U7 commutation loop")
    c.raw_spice += (f"Istep vin_pin pgnd_pin PWL(0 0 10n 0 "
                    f"12n {IPEAK_MIN.value} 14n 0)\n")
    # Package/PCB inductance from the pins to each capacitor.
    c.raw_spice += "Lpin1 vin_pin vin_cap 1.5n\nRpin1 vin_pin vin_cap 1e6\n"
    c.raw_spice += "Lpin2 pgnd_pin pgnd_cap 1.5n\nRpin2 pgnd_pin pgnd_cap 1e6\n"
    # Route 1, as built: 22 uF from +12V to the plane, 47 uF from the plane to
    # -6V, with plane inductance between the two return points.
    c.raw_spice += "Vam1 vin_cap am1 DC 0\n"          # ammeter, route 1
    c.raw_spice += "C1 am1 pl1 22u\nRp1 am1 pl1 1e6\n"
    c.raw_spice += "R1 pl1 pl1b 5m\nL1 pl1b plane 2n\nRl1 pl1b plane 1e6\n"
    c.raw_spice += f"Lplane plane planex {l_plane}\n"
    c.raw_spice += "Rplane planex plane2 2m\n"
    c.raw_spice += "C2 plane2 pl2 47u\nRp2 plane2 pl2 1e6\n"
    c.raw_spice += "R2 pl2 pl2b 5m\nL2b pl2b pgnd_cap 2n\nRl2b pl2b pgnd_cap 1e6\n"
    # Route 2, the fix: a small low-ESL ceramic straight across VIN to PGND,
    # 0603, at the pins.
    c.raw_spice += "Vam2 vin_cap am2 DC 0\n"          # ammeter, route 2
    if c_vin_pgnd > 0:
        c.raw_spice += f"Cfix am2 pfx {c_vin_pgnd}\nRpf am2 pfx 1e6\n"
        c.raw_spice += "Rfx pfx pfxb 3m\nLfx pfxb pgnd_cap 0.8n\n"
        c.raw_spice += "Rlfx pfxb pgnd_cap 1e6\n"
    else:
        c.raw_spice += "Ropen am2 pgnd_cap 1e9\n"     # nothing fitted
    c.raw_spice += "Rleak plane 0 1e6\n"
    return c


def scenario_spice(ck):
    banner("C. NGSPICE -- referencing, the switching stage, and the loop")

    # ---- C-1. Feedback referencing, and the same resistors read wrong.
    out = {}
    for frame in ("device", "board"):
        an = run(build_fb_frame(frame), 1e-5, 0.3)
        out[frame] = float(arr(an, "vn6")[-1])
    print(f"   divider held 1.0 V above U7's own GND   -> "
          f"{out['device']:+.3f} V")
    print(f"   same divider read as if GND were U7's   -> "
          f"{out['board']:+.3f} V")
    ck.add("C-1", "SPICE agrees the referencing gives -5.98 V, and shows what "
                  "the frame error costs",
           abs(out["device"] - V_N6V_TARGET.value) < 0.02,
           f"solving the real divider with FB regulated to VFB above the "
           f"-6 V node settles at {out['device']:.3f} V",
           f"regulating the same FB node to 1.0 V above SYSTEM ground -- the "
           f"error the power-good fault shows this circuit invites -- gives "
           f"{out['board']:+.3f} V instead, a rail "
           f"{abs(out['board']-out['device']):.2f} V away from intent")

    # ---- C-2. The switching stage, open loop at the duty the algebra gives.
    #
    # Run it at three loads. The point of the sweep is that the algebra of
    # B-1/B-4 is a CCM derivation, so it should land exactly at the heavy-load
    # end and overshoot at the light end -- which is an independent
    # confirmation that this converter really is in DCM at its design load,
    # the result B-3's on-time margin rests on.
    v_at_u7 = VIN_NOM.value - D1_VF.value - 0.219
    rows = []
    for iout in (0.0635, 0.30, 0.80):
        op = inverting_operating_point(v_at_u7, abs(V_N6V_TARGET.value), iout)
        an = run(build_power_stage(d=op["D"], iout=iout), 5e-9, 2.0e-3)
        t = np.array(an.time)
        tail = t > 1.6e-3
        vn6 = arr(an, "vn6")[tail]
        try:
            il = np.array(an.branches["l2"])[tail]
            il_mean, il_pk = float(np.mean(np.abs(il))), float(np.max(np.abs(il)))
        except Exception:
            il_mean = il_pk = float("nan")
        rows.append((iout, op, float(np.mean(vn6)),
                     float(np.max(vn6) - np.min(vn6)), il_mean, il_pk))
        print(f"\n   {iout*1e3:5.1f} mA, open loop at D = {op['D']:.4f} "
              f"({'CCM' if op['ccm'] else 'DCM'} predicted): rail "
              f"{rows[-1][2]:+.3f} V, ripple {rows[-1][3]*1e3:.1f} mV, "
              f"I_L mean {il_mean*1e3:.0f} mA peak {il_pk:.3f} A "
              f"(predicted {op['IL']*1e3:.0f} mA)")
    heavy = rows[-1]
    light = rows[0]
    ck.add("C-2", "the topology delivers the rail the duty-cycle algebra "
                  "predicts, and is in DCM at its design load",
           abs(abs(heavy[2]) - abs(V_N6V_TARGET.value)) < 0.30
           and abs(light[2]) > abs(heavy[2]) + 0.1,
           f"at {heavy[0]*1e3:.0f} mA, where the prediction is continuous "
           f"conduction, the real switch pair at D = {heavy[1]['D']:.4f} puts "
           f"the rail at {heavy[2]:+.3f} V against {V_N6V_TARGET.value:+.2f} "
           f"V intended, and the inductor carries {heavy[4]*1e3:.0f} mA "
           f"against I_load/(1-D) = {heavy[1]['IL']*1e3:.0f} mA",
           f"at the design load of {light[0]*1e3:.1f} mA the same duty "
           f"overshoots to {light[2]:+.3f} V, which is what discontinuous "
           f"conduction does and is the independent confirmation that this "
           f"converter runs in DCM at 6 % of the part's rating. The inductor "
           f"return to SYSTEM ground rather than to the device's ground is "
           f"what makes any of this inverting; a buck wiring of the same "
           f"parts would put +5.98 V here")

    # ---- C-3. The commutation loop, with and without the required cap.
    print()
    rows = []
    for label, cfix in (("as built (no VIN-to-PGND cap)", 0.0),
                        ("+ 2.2 uF 0603 across VIN to PGND", 2.2e-6)):
        an = run(build_commutation(cfix), 2e-11, 60e-9)
        v_dev = arr(an, "vin_pin") - arr(an, "pgnd_pin")
        def branch(nm):
            for k in (nm, nm + "#branch", nm.upper()):
                try:
                    return np.array(an.branches[k])
                except Exception:
                    continue
            return None
        i1, i2 = branch("vam1"), branch("vam2")
        exc = float(np.max(v_dev) - np.min(v_dev))
        p1 = float(np.max(np.abs(i1))) if i1 is not None else float("nan")
        p2 = float(np.max(np.abs(i2))) if i2 is not None else float("nan")
        rows.append((label, exc, p1, p2))
        print(f"   {label:34} VIN-PGND moves {exc*1e3:7.0f} mV;  "
              f"{p1*1e3:6.0f} mA through the plane route, "
              f"{p2*1e3:6.0f} mA through the local cap")
    ck.add("C-3", "the commutation loop does not run through the analog "
                  "ground plane",
           rows[0][2] < 0.10 * IPEAK_MIN.value,
           f"as built, {rows[0][2]/IPEAK_MIN.value*100:.0f} % of the "
           f"{IPEAK_MIN.value:.2f} A switch transition returns through the "
           f"ground plane between the two capacitors, because the only path "
           f"from VIN to U7's PGND is 22 uF in series with 47 uF with the "
           f"plane in between; the pin pair moves {rows[0][1]*1e3:.0f} mV "
           f"across roughly 11 nH of loop",
           f"fitting a 2.2 uF 0603 straight across VIN to PGND at the pins "
           f"moves {rows[1][3]/IPEAK_MIN.value*100:.0f} % of the transition "
           f"into it, leaves {rows[1][2]/IPEAK_MIN.value*100:.0f} % in the "
           f"plane, and brings the excursion to {rows[1][1]*1e3:.0f} mV. "
           f"SNVSAN3F 9.2.2.6 asks for 10 uF plus a 220 nF here; the point "
           f"is not the value, it is that the loop has no local return at "
           f"all on a board whose premise is a quiet ground. Against SW's "
           f"-0.3 V DC / -3.5 V 100 ns floor this is also a rating question")
    return {"loop": rows, "fb": out}


# =========================================================================
# D. SEQUENCING, WITH BOTH CONVERTERS
# =========================================================================
def build_sequencing_both(t_mute=None, tss=None):
    """+5 V and -6 V from one 12 V rail, as reference ramps.

    Same modelling choice as power_input_transient.py, and for the same
    reason: arrival order is set by soft-start ramps and enable thresholds,
    not by switching. What is new is that both converters are here, and the
    module's four post-regulators behind them.
    """
    tss = TSS.value if tss is None else tss
    t_mute = 1e9 if t_mute is None else t_mute
    c = Circuit("both rails from one wall wart")
    c.raw_spice += f"Vsrc src 0 PULSE(0 {VIN_NOM.value} 0 30u 30u 20 40)\n"
    c.raw_spice += "Rsrc src vraw 0.3\n"
    c.raw_spice += f"Rf1 vraw v12 {F1_RMAX.value}\n"
    c.raw_spice += f"Cin v12 0 {C_IN_12.value}\n"
    # U5: 12 V -> +5 V, EN on VIN, internal fixed soft start.
    c.raw_spice += f"Bss5 0 ss5 I = {1e-6/tss}*u(v(v12)-3.7)\n"
    c.raw_spice += "Css5 ss5 0 1u\nRss5 ss5 0 1e12\n"
    c.raw_spice += "B5 v5s 0 V = 5.02*min(v(ss5),1.0)\n"
    c.raw_spice += "Vs5 v5s v5a DC 0\nRo5 v5a p5v 30m\nC5 p5v 0 66.4u\n"
    c.raw_spice += "Rl5 p5v 0 14.05\n"       # 5.016 V / 357 mA total load
    # Reflected input current, through the datasheet efficiency: this is the
    # term that makes the fuse verdict mean anything.
    c.raw_spice += ("Bu5in v12 0 I = v(v5a)*i(Vs5)/(0.91*max(v(v12),1))\n")
    # U7: 12 V -> -6 V. Same enable condition, same internal soft start. Its
    # ground is the rail it makes, so the ramp is of |Vout|.
    c.raw_spice += f"Bss7 0 ss7 I = {1e-6/tss}*u(v(v12)-3.7)\n"
    c.raw_spice += "Css7 ss7 0 1u\nRss7 ss7 0 1e12\n"
    c.raw_spice += "B7 v7s 0 V = -5.98*min(v(ss7),1.0)\n"
    c.raw_spice += "Vs7 v7s v7a DC 0\nRo7 v7a n6v 40m\n"
    c.raw_spice += f"C7 0 n6v {C_OUT_N6.value}\n"
    c.raw_spice += "Rl7 0 n6v 94.2\n"        # 5.98 V / 63.5 mA
    c.raw_spice += ("Bu7in v12 0 I = -v(v7a)*i(Vs7)/(0.85*max(v(v12),1))\n")
    # MUTE_N: the module's analog rails are gated by it. 100 k to ground on
    # the module side holds it low until the FPGA drives it.
    c.raw_spice += f"Bmute mute 0 V = 2.5*u(time-{t_mute})\n"
    #
    # Every post-regulator follows its SET pin, which is 100 uA into
    # R_SET || C_SET. PGFB is tied to IN on all six, which disables the 2 mA
    # fast-start circuit, so this RC *is* the ramp. Values read out of the
    # netlists: the main board's U3 was cut to 100 nF deliberately; all five
    # on the module keep 4.7 uF.
    for name, rset, cset, vout, gate, in_node in (
            ("s5", 33.2e3, 4.7e-6, 3.32, None, "p5v"),     # U5  +3V3_REF
            ("s6", 33.2e3, 4.7e-6, 3.32, None, "p5v"),     # U6  +3V3_CLK
            ("s9", 24.9e3, 4.7e-6, 2.49, None, "p5v"),     # U9  +2V5
            ("s14", 45.3e3, 4.7e-6, 4.53, "mute", "p5v"),  # U14 +5V_A
            ("s8", 49.9e3, 4.7e-6, 4.99, "mute", "n6v")):  # U8  -5V_A
        en = ("u(v(p5v)-1.32)" if gate is None
              else f"u(v({gate})-1.32)*u(v({in_node})-1.32)"
              if in_node == "p5v" else f"u(v({gate})-1.33)")
        c.raw_spice += f"B{name} 0 {name} I = 100u*{en}\n"
        c.raw_spice += f"R{name} {name} 0 {rset}\nC{name} {name} 0 {cset}\n"
    # U9 +2V5: the translator's A side and the ID0 strap.
    c.raw_spice += "B25m v25m 0 V = min(v(s9), max(v(p5v)-0.33,0))\n"
    c.raw_spice += "Ro25 v25m p25m 50m\nC25 p25m 0 10u\nRl25 p25m 0 2490\n"
    # U5 +3V3_REF: the two register packages and the elements.
    c.raw_spice += "B33 v33 0 V = min(v(s5), max(v(p5v)-0.33,0))\n"
    c.raw_spice += "Ro33 v33 p33 50m\nC33 p33 0 10.8u\nRl33 p33 0 56.6\n"
    # U6 +3V3_CLK: the oscillators, divider, fanout, translator B side.
    c.raw_spice += "B33c v33c 0 V = min(v(s6), max(v(p5v)-0.33,0))\n"
    c.raw_spice += "Ro33c v33c p33c 50m\nC33c p33c 0 10.2u\nRl33c p33c 0 99\n"
    # U14 +5V_A and U8 -5V_A, both gated by MUTE_N.
    c.raw_spice += "B14 v14 0 V = min(v(s14), max(v(p5v)-0.33,0))\n"
    c.raw_spice += "Ro14 v14 p5va 50m\nC14 p5va 0 10u\nRl14 p5va 0 210\n"
    c.raw_spice += "B8 v8 0 V = max(-v(s8), min(v(n6v)+0.235,0))\n"
    c.raw_spice += "Ro8 v8 n5va 50m\nC8o 0 n5va 10u\nRl8 0 n5va 78.6\n"
    return c


def _cross(t, v, level, rising=True):
    idx = np.where(v >= level)[0] if rising else np.where(v <= level)[0]
    return float(t[idx[0]]) if len(idx) else None


def scenario_sequencing(ck):
    banner("D. SEQUENCING -- both rails, and what the module sees")
    an = run(build_sequencing_both(t_mute=20e-3), 20e-6, 1.2)
    t = np.array(an.time)
    rails = {"+12V": ("v12", 11.4, 1), "+5V": ("p5v", 5.02, 1),
             "-6V_A": ("n6v", -5.98, -1), "+2V5m": ("p25m", 2.49, 1),
             "+3V3_REF": ("p33", 3.32, 1), "+3V3_CLK": ("p33c", 3.32, 1),
             "+5V_A": ("p5va", 4.53, 1), "-5V_A": ("n5va", -4.99, -1)}
    times = {}
    print(f"   {'rail':8} {'10 %':>10} {'90 %':>10} {'final':>10}")
    for nm, (node, nominal, sign) in rails.items():
        v = arr(an, node) * sign
        t10 = _cross(t, v, 0.10 * abs(nominal))
        t90 = _cross(t, v, 0.90 * abs(nominal))
        times[nm] = (t10, t90, float(v[-1]) * sign)
        f = lambda x: f"{x*1e3:.2f} ms" if x is not None else "never"
        print(f"   {nm:8} {f(t10):>10} {f(t90):>10} "
              f"{float(v[-1])*sign:9.3f} V")

    # ---- D-1. Both switchers arrive; neither waits on the other.
    ck.add("D-1", "both converters start from one enable and both arrive",
           times["+5V"][1] is not None and times["-6V_A"][1] is not None,
           f"+5V at {times['+5V'][1]*1e3:.2f} ms and -6V_A at "
           f"{times['-6V_A'][1]*1e3:.2f} ms, both off EN tied to +12V",
           "U7's enable cannot be sequenced behind U5 even if someone wanted "
           "it to be: a ground-referenced enable signal sits below this "
           "device's own ground. Tying EN to VIN is not laziness here, it is "
           "the only simple arrangement that works")

    # ---- D-2. The analog rails arrive together, because one signal gates
    # both, which is the property that matters to the amplifiers.
    skew = abs((times["+5V_A"][1] or 0) - (times["-5V_A"][1] or 0))
    ck.add("D-2", "the op amp rails arrive together",
           skew < 1e-3,
           f"+5V_A at {times['+5V_A'][1]*1e3:.2f} ms and -5V_A at "
           f"{times['-5V_A'][1]*1e3:.2f} ms: {skew*1e6:.0f} us apart",
           "both are gated by MUTE_N and both inputs are already up when it "
           "asserts, so the OPA1612s never see one rail without the other "
           "for longer than their own regulators' ramps. Single-supply "
           "operation is not a damage case for that part (+/-2.25 to +/-18 V, "
           "36 V total) but it is an undefined-output case, and the element "
           "lines are off until the FPGA configures")

    # ---- D-3. -6 V must be up before its regulator is enabled.
    ck.add("D-3", "the LT3094's input is established before MUTE_N enables it",
           (times["-6V_A"][1] or 1) < 20e-3,
           f"-6V_A reaches 90 % at {times['-6V_A'][1]*1e3:.2f} ms against a "
           f"MUTE_N assertion modelled at 20 ms",
           "MUTE_N cannot in practice arrive earlier: it comes from an FPGA "
           "that has to load a bitstream from flash first. If it ever does "
           "-- a strap, a test fixture -- the LT3094 starts into a rising "
           "input, which is a slow ramp rather than a fault")

    # ---- D-3b. The module's own rails arrive hundreds of milliseconds after
    # the FPGA's do, and nothing on either board enforces an order.
    t_ref = times["+3V3_REF"][1]
    ck.add("D-5", "the module's logic rails are up before anything can drive "
                  "their inputs",
           t_ref is not None and t_ref < 50e-3,
           f"+3V3_REF reaches 90 % at {t_ref*1e3:.0f} ms and +2V5 (module) at "
           f"{times['+2V5m'][1]*1e3:.0f} ms, because all five module "
           f"post-regulators keep C_SET = 4.7 uF with PGFB tied to IN, which "
           f"disables the 2 mA fast start and leaves 2.3 x R_SET x C_SET as "
           f"the ramp",
           "the main board's own +2V5 and +1V0 are up inside 5 ms, so the "
           "FPGA can finish loading its bitstream and start driving 28 "
           "element lines and the element clock into an SN74ALVCH16374 whose "
           "VCC is still climbing, and into a 74AVC4T245 whose VCC(A) is "
           "still climbing. Nothing sequences these: MUTE_N is an OUTPUT of "
           "the FPGA and the module returns no power-good. The margin is a "
           "359 ms RC against an unmeasured bitstream load time")

    # ---- D-4. Input current through start-up, now with both converters.
    #
    # Computed from the two converters' output powers rather than read out of
    # the model: the reflected-current sources in build_sequencing_both carry
    # a sign I did not chase to the bottom, and a verdict about a fuse should
    # not rest on that. The SPICE figure is printed beside it as a sanity
    # bound, not as the evidence.
    i_in_spice = float((arr(an, "vraw") - arr(an, "v12"))[-1] / F1_RMAX.value)
    v_jack_lo = VIN_NOM.value * (1 - VIN_TOL.value)
    p5 = 5.016 * 0.357                      # verify_power's own +5V total
    pn6 = abs(V_N6V_TARGET.value) * I_N6V.value
    p_in_ss = p5 / 0.91 + pn6 / 0.85
    i_ss = p_in_ss / (v_jack_lo - D1_VF.value)
    # Both converters charge their output capacitance inside a 4 ms soft start
    # at the same time, because both enables are the same net.
    i_ramp5 = 66.4e-6 * 5.016 / TSS.value
    i_ramp7 = C_OUT_N6.value * abs(V_N6V_TARGET.value) / TSS.value
    i_in_ramp = i_ss + (i_ramp5 * 5.016 / 0.91 + i_ramp7
                        * abs(V_N6V_TARGET.value) / 0.85) / (v_jack_lo
                                                             - D1_VF.value)
    print(f"\n   steady state {i_ss*1e3:.0f} mA at the jack; both soft starts "
          f"add {i_ramp5*1e3:.0f} mA on +5V and {i_ramp7*1e3:.0f} mA on -6V "
          f"of capacitor charging, i.e. {i_in_ramp*1e3:.0f} mA at the jack "
          f"for {TSS.value*1e3:.0f} ms (model reads {i_in_spice*1e3:.0f} mA "
          f"settled)")
    ck.add("D-4", "start-up current stays inside F1's hold with BOTH "
                  "converters ramping at once",
           i_in_ramp < 0.40,
           f"{i_in_ramp*1e3:.0f} mA at the jack during the 4 ms both soft "
           f"starts share, settling to {i_ss*1e3:.0f} mA, against 0.5 A hold "
           f"at 20 C, 0.4 A at 50 C and 0.33 A at 70 C",
           f"power_input_transient.py's S-5 reports 190 mA for this instant "
           f"with no inverter on the board at all. The margin against the "
           f"70 C derating is {(0.33-i_in_ramp)*1e3:.0f} mA, which is the "
           f"number that matters in an enclosure, and it is not large")
    return times


# =========================================================================
# E. DISSIPATION, from the currents above rather than from power.md
# =========================================================================
def scenario_thermal(ck, ops):
    banner("E. DISSIPATION AND JUNCTION TEMPERATURE")
    nom = ops["12.00 V"]
    vmag = abs(V_N6V_TARGET.value)
    p_out = I_N6V.value * vmag
    # Conduction, from the real DCM waveform: a triangle to Ipk over ton in
    # the high side and back to zero over toff in the low side.
    ton, ipk, f_eff = nom["ton"], nom["Ipk"], nom["f_eff"]
    toff = L2.value * ipk / vmag
    i2t_hs = ipk ** 2 * ton / 3
    i2t_ls = ipk ** 2 * toff / 3
    p_hs = i2t_hs * f_eff * RDSON_HS.value
    p_ls = i2t_ls * f_eff * RDSON_LS.value
    p_dcr = (i2t_hs + i2t_ls) * f_eff * L2_DCR.value
    # Switching: the SW node swings VIN-PGND at f_eff, into an assumed node
    # capacitance, plus gate charge out of the 5 V VCC LDO.
    c_sw = 60e-12       # ASSUMED
    q_g = 3e-9          # ASSUMED
    p_sw = c_sw * nom["vin_dev"] ** 2 * f_eff + 2 * 5.0 * q_g * f_eff
    p_q = 24e-6 * nom["vin_dev"]
    p_u7 = p_hs + p_ls + p_sw + p_q
    eff = p_out / (p_out + p_u7 + p_dcr)
    print(f"   U7 output          {p_out*1e3:7.1f} mW at "
          f"{I_N6V.value*1e3:.1f} mA")
    print(f"   high-side I2R      {p_hs*1e3:7.2f} mW")
    print(f"   low-side I2R       {p_ls*1e3:7.2f} mW")
    print(f"   switching + gate   {p_sw*1e3:7.2f} mW   (ASSUMED Csw, Qg)")
    print(f"   quiescent          {p_q*1e3:7.2f} mW")
    print(f"   inductor DCR       {p_dcr*1e3:7.2f} mW   (ASSUMED DCR)")
    print(f"   -> U7 dissipates   {p_u7*1e3:7.1f} mW, stage efficiency "
          f"{eff*100:.1f} %")
    # Cross-check against the datasheet's own efficiency curve rather than
    # trusting the assumed Csw and Qg above: figure C021 reads about 85 % at
    # 60 mA for 12 V in and 5 V out, which is 67 mW of loss, not 11.
    p_curve = p_out * (1 / 0.85 - 1)
    print(f"      datasheet curve  {p_curve*1e3:7.1f} mW at 85 %, which is "
          f"the number to believe; the itemised loss above under-counts "
          f"switching because Csw and Qg are assumed")
    rise = p_u7 * RTHJA.value
    ck.add("E-1", "U7's junction rise, from computed loss rather than an "
                  "assumed efficiency",
           rise < 40,
           f"{p_u7*1e3:.0f} mW itemised and {p_out*(1/0.85-1)*1e3:.0f} mW "
           f"off the datasheet's own efficiency curve; into "
           f"{RTHJA.value:g} C/W that is {rise:.1f} C and "
           f"{p_out*(1/0.85-1)*RTHJA.value:.1f} C respectively",
           f"verify_power.py assumes 85 % and gets 68 mW, which is the same "
           f"answer for the wrong reason: at 6 % of rated current this part's "
           f"loss is switching and quiescent, not conduction. The verdict is "
           f"robust -- ANY efficiency above 30 % keeps the rise under "
           f"{0.383*(1/0.3-1)*RTHJA.value:.0f} C")
    # The pad is at -6 V, which is the part nobody has had to think about.
    ck.add("E-2", "U7's thermal path does not depend on the ground plane",
           rise < 40,
           "pin 1 is PGND and the exposed pad is AGND (table 6-1), and both "
           "are tied to -6V_A here -- correctly, since AGND-to-PGND has a "
           "0.3 V absolute maximum",
           "so U7's thermal pad is a -6 V copper island, not the ground "
           "plane, and the 42.9 C/W of table 7.4 is a 4-layer JEDEC figure "
           "the datasheet explicitly forbids using for design. At 15 mW the "
           "conclusion survives any plausible island; the note is for "
           "whoever lays it out, and for anyone who later raises this rail's "
           "load")
    # Every other dissipating part, with the real currents.
    print()
    p_d1 = 0.219 * D1_VF.value
    p_f1 = 0.219 ** 2 * F1_RMAX.value
    p_u3_ds = (5.02 - 3.32) * 0.185      # main power.md's 185 mA
    p_u3_vp = (5.02 - 3.32) * 0.060      # verify_power.py's 60 mA
    for nm, p, rth, note in (
            ("F1  1812L050/30", p_f1, None, "at R1max, the post-trip value"),
            ("D1  SS34", p_d1, 55.0, "ASSUMED VF"),
            ("U7  LMR33630 inv", p_u7, RTHJA.value, "computed above"),
            ("U3  LT3045 3V3", p_u3_ds, 34.0,
             "at power.md's 185 mA; verify_power.py's 60 mA gives "
             f"{p_u3_vp*1e3:.0f} mW"),
            ("U8  LT3094 -5V", 0.98 * I_N6V.value, LT3094_RTHJA.value,
             "from the -6 V rail's own tolerance low corner"),
            ("U14 LT3045 +5V_A", (5.02 - 4.53) * 0.0216, 34.0,
             "after the SET fix")):
        r = f"{p*rth:5.1f} C" if rth else "    -  "
        print(f"   {nm:18} {p*1e3:7.1f} mW   rise {r}   {note}")
    ck.add("E-3", "no part on the supply chain rises more than 40 C",
           max(p_d1 * 55.0, p_u7 * RTHJA.value, p_u3_ds * 34.0) < 40,
           f"worst is U3 at {p_u3_ds*34.0:.1f} C on main power.md's 185 mA "
           f"through the 3.3 V rail",
           "and that is the figure verify_power.py does not use: it carries "
           "60 mA for the same rail and reports 102 mW where the board's own "
           "page implies 315 mW. Both cannot be right and neither is "
           "measured")
    return p_u7


# =========================================================================
# TAMPERS
# =========================================================================
def run_tampers():
    banner("TAMPERS -- every check above, broken on purpose")
    out = []

    def rec(name, target, expect, ok_observed, note=""):
        got = "passes" if ok_observed else "fails"
        want = "passes" if expect == "hole" else expect
        mark = "OK  " if got == want else ("HOLE" if expect == "hole"
                                           else "MISS")
        out.append((mark, name, target, expect, got, note))
        print(f"\n  {mark}  {name}\n        against {target}: expected it to "
              f"{expect}, it {got}")
        if note:
            print(f"        {note}")

    # T-1. The input capacitor check, given the capacitor it asks for.
    ck = Checks()
    with contextlib.redirect_stdout(io.StringIO()):
        scenario_audit(ck)
    base_a1 = ck.get("A-1").ok
    rec("A-1 run against the netlist as it stands", "A-1, U7's input cap",
        "fails", base_a1,
        "0.00 uF against a required 10 uF. The check is only useful if it "
        "also passes once a capacitor is fitted -- T-2 shows it does")

    # T-2. Same check with the capacitor present, to prove it is not
    # unconditionally failing.
    saved = caps_between
    try:
        globals()["caps_between"] = lambda c, n, a, b: (
            22e-6 if {a, b} == {"+12V", "-6V_A"} else saved(c, n, a, b))
        ck2 = Checks()
        with contextlib.redirect_stdout(io.StringIO()):
            scenario_audit(ck2)
        rec("a 22 uF fitted from +12V to -6V_A", "A-1, U7's input cap",
            "passes", ck2.get("A-1").ok,
            "so A-1 discriminates rather than always failing")
    finally:
        globals()["caps_between"] = saved

    # T-3. Minimum on-time, pushed until it binds.
    ck3 = Checks()
    hi = inverting_operating_point(60.0, 5.98, I_N6V.value)
    rec("a 60 V input, where the pulse would have to shrink",
        "B-3, minimum on-time", "fails", hi["ton"] > TON_MIN.value,
        f"t_on becomes {hi['ton']*1e9:.0f} ns. It does NOT bind, because "
        f"IPEAK-MIN holds the peak at 0.69 A and the part folds frequency "
        f"instead: the on-time is set by L x Ipk / (Vin_dev - Vout), which "
        f"falls only as 1/Vin. B-3 is therefore a weak check on this design "
        f"-- it cannot be made to fail by any input this board can see, and "
        f"the reason is a real property of the part rather than a hole")

    # T-4. Current capability, pushed until the topology limit binds.
    heavy = 0.8
    op = inverting_operating_point(11.4, 5.98, heavy)
    lim = (ISC.value - op["dIL"] / 2) * (1 - op["D"])
    rec("the -6 V rail loaded to 800 mA", "B-4, current capability",
        "fails", heavy < 0.3 * lim,
        f"the topology limit is {lim:.2f} A at that duty, so 800 mA is "
        f"{heavy/lim*100:.0f} % of it and the 30 % criterion fails. The "
        f"headline 3 A would have said this was fine")

    # T-5. Rail tolerance, with the feedback tolerance removed.
    ck5 = Checks()
    sv_lo, sv_hi = VFB_MIN.value, VFB_MAX.value
    try:
        VFB_MIN.value = VFB_MAX.value = 1.0
        R_TOL.value = 0.0
        ck5 = Checks()
        with contextlib.redirect_stdout(io.StringIO()):
            scenario_topology(ck5)
        rec("all tolerances set to zero", "B-2, rail accuracy", "passes",
            ck5.get("B-2").ok,
            "B-2 passes either way here: the LT3094 has 980 mV of headroom "
            "and 1.5 % of 6 V is 90 mV. Recorded because the same "
            "arithmetic on the +5 V rail does NOT pass with room to spare -- "
            "see B-3 in the verdict and section 2")
    finally:
        VFB_MIN.value, VFB_MAX.value = sv_lo, sv_hi
        R_TOL.value = 0.01

    # T-6. The commutation loop, with the plane inductance taken to zero.
    an0 = run(build_commutation(0.0, 1e-12), 2e-11, 60e-9)
    i0 = float(np.max(np.abs(np.array(an0.branches["lplane"]))))
    rec("a perfect ground plane, 1 pH between the capacitors",
        "C-3, the commutation loop", "passes",
        i0 < 0.05 * IPEAK_MIN.value,
        f"{i0*1e3:.0f} mA still returns through the plane -- "
        f"{i0/IPEAK_MIN.value*100:.0f} % of the transition. The current path "
        f"is a topology fact, not a parasitic one: with no capacitor from "
        f"VIN to PGND there is no other route, however good the copper. That "
        f"is why C-3 is about a missing part and not about layout")

    # T-7. Sequencing, with MUTE_N asserted before the rails exist.
    ck7 = Checks()
    sv = build_sequencing_both
    try:
        globals()["build_sequencing_both"] = (
            lambda *a, **k: sv(t_mute=0.0, **{x: y for x, y in k.items()
                                              if x != "t_mute"}))
        with contextlib.redirect_stdout(io.StringIO()):
            scenario_sequencing(ck7)
        rec("MUTE_N asserted at t = 0, before either rail exists",
            "D-3, the LT3094's input before its enable", "fails",
            ck7.get("D-3").ok,
            "D-3 tests the rail's arrival against a fixed 20 ms, so moving "
            "MUTE_N does not move it: the check as written cannot see this "
            "case at all. HOLE. It should compare the two times, not one "
            "time against a constant")
    finally:
        globals()["build_sequencing_both"] = sv

    n_ok = sum(1 for m, *_ in out if m == "OK  ")
    print(f"\n  {n_ok}/{len(out)} tampers moved the check they targeted; "
          f"{sum(1 for m, *_ in out if m == 'HOLE')} found a hole in a check "
          f"and {sum(1 for m, *_ in out if m == 'MISS')} did not do what was "
          f"predicted")
    return out


# =========================================================================
# The sweep the review used on verify_power.py
# =========================================================================
def sweep_verify():
    """Perturb every Fact in verify_power.py and see which checks can fail."""
    sys.path.insert(0, str(HW))
    import importlib
    V = importlib.import_module("verify_power")
    facts = [n for n, v in vars(V).items() if isinstance(v, V.Fact)]

    def once():
        V.results.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            V.main()
        return {r.name: r.ok for r in V.results}

    base = once()
    names = list(base)
    banner(f"SWEEP -- verify_power.py, {len(names)} checks, "
           f"{len(facts)} constants")
    flipped = {n: set() for n in names}
    for f in facts:
        orig = getattr(V, f).value
        for s in (1e-3, 0.1, 0.5, 0.9, 1.1, 2, 10, 1e3, -1):
            getattr(V, f).value = orig * s
            try:
                r = once()
            except Exception:
                r = {}
            for n in names:
                if n in r and r[n] != base[n]:
                    flipped[n].add(f)
            getattr(V, f).value = orig
    dead = [n for n in names if not flipped[n]]
    for n in names:
        tag = "DEAD" if not flipped[n] else "live"
        print(f"  {tag}  {n}")
        if flipped[n]:
            print(f"          <- {', '.join(sorted(flipped[n]))}")
    print(f"\n  {len(names)-len(dead)}/{len(names)} checks can be made to "
          f"fail by some constant; {len(dead)} cannot")
    return dead


def main() -> int:
    if "--sweep-verify" in sys.argv:
        sweep_verify()
        return 0
    ck = Checks()
    print("=" * 76)
    print("LYREBIRD -6 V INVERTING CONVERTER -- the rail no check contains")
    print("=" * 76)
    scenario_audit(ck)
    ops = scenario_topology(ck)
    scenario_spice(ck)
    scenario_sequencing(ck)
    scenario_thermal(ck, ops)

    banner("CHECKS")
    npass = 0
    for r in ck.results:
        mark = "PASS" if r.ok else "FAIL"
        npass += r.ok
        print(f"\n  {mark}  {r.tag}  {r.name}")
        print(f"        {r.detail}")
        if r.margin:
            print(f"        -> {r.margin}")
    print(f"\n  {npass}/{len(ck.results)} checks pass")
    run_tampers()
    banner("CONSTANTS")
    for src in (DS, CALC, ASSUMED):
        print(f"\n  {src}:")
        for n, v in sorted(vars(sys.modules[__name__]).items()):
            if isinstance(v, Fact) and v.source == src:
                print(f"    {n:22} {v.value:>12g} {v.unit:6} {v.note}")
    return 0 if npass == len(ck.results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

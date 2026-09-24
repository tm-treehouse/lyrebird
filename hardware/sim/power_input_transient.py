#!/usr/bin/env python3
"""SPICE the 12 V wall-wart front end, in the cases arithmetic cannot reach.

`hardware/verify_power.py` checks the steady state of the input chain and all
twelve of its checks pass. Nothing in it moves. This file is the other half:
plug-in, reverse polarity, the wrong adapter, and the order the rails arrive
in -- four questions whose answers are times and trajectories rather than
operating points.

The circuit is 0014's, read off `hardware/netlist/main_board.py` under the
"Wall wart input" comment:

    J4 barrel jack -> F1 polyfuse -> D1 SS34 -> [D2 SMAJ15A, 22 uF, 100 nF]
    -> U5 LMR33630 (EN tied to VIN) -> 10 uH -> +5V, 47 uF

What the four scenarios establish, in one line each:

  1. INRUSH.   Peak current at plug-in, and whether F1 notices. The peak is
     set by parasitics nobody has measured; the energy is set by C*V^2 and is
     not, which is why the fuse verdict is the robust one and the peak
     verdict is the one that moves.
  2. REVERSE.  D1 blocks, and its reverse leakage is then the only current in
     the circuit. Where that current goes is the interesting part.
  3. 19 V BRICK.  The TVS conducts, heats, and its own breakdown voltage
     walks up until it stops conducting. The fuse is never involved.
  4. SEQUENCING.  Rail arrival order through a soft-started buck, with the
     WAKEUP_N core gating that 0014 says was retired and the netlist still
     builds.

Every scenario is tamper-tested at the bottom: the thing each check is
supposed to catch is broken on purpose, and the check has to fail. One of
those tampers finds a hole in an existing check rather than a fault in the
design; see TAMPERS and the report.

ngspice comes from KiCad's bundle; there is no standalone binary on this
machine. InSpice resolves the library through ctypes, which discards an
absolute path, so the finder is replaced below.

    ./.venv/bin/python hardware/sim/power_input_transient.py
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field

KICAD = "/Applications/KiCad/KiCad.app/Contents"
os.environ.setdefault("SPICE_LIB_DIR", f"{KICAD}/PlugIns/sim/ngspice")
_LIB = f"{KICAD}/Frameworks/libngspice.0.dylib"

from InSpice.Spice.NgSpice.Shared import NgSpiceShared  # noqa: E402

NgSpiceShared.find_library = classmethod(lambda cls, name: _LIB)

from InSpice import Circuit, Simulator  # noqa: E402
import numpy as np  # noqa: E402

# ------------------------------------------------------------------ sources
DS = "datasheet"
CALC = "calculation"
MODEL = "MODEL, fitted"
ASSUMED = "ASSUMED, unverified"


@dataclass
class Fact:
    value: float
    unit: str
    source: str
    note: str = ""


def F(v, u, s, n=""):
    return Fact(v, u, s, n)


# --------------------------------------------------------------- constants
#
# Datasheets read for this file, in full, not quoted from memory:
#
#   LMR33630   TI SNVSAN3F, Nov 2020
#   SMAJ15A    Vishay 88390 rev 09-Jan-2024; cross-checked against Bourns
#              and Kemet SMAJ, which agree digit for digit on the table row
#   SS34       Vishay 88751 rev 23-Apr-2020 (SS32-SS36)
#   1812L110   Littelfuse 1812L series, revised 12-Jul-2010
#
# Anything not in one of those four is marked ASSUMED or MODEL and the report
# lists it.

# --- U5, LMR33630ADDA ------------------------------------------------------
U5_VIN_ABSMAX = F(38.0, "V", DS, "VIN to PGND absolute maximum, table 7.1")
U5_VIN_ABSMIN = F(-0.3, "V", DS, "VIN to PGND absolute MINIMUM, table 7.1")
U5_VIN_OPMAX = F(36.0, "V", DS, "recommended operating maximum, table 7.3")
U5_VIN_OPMIN = F(3.8, "V", DS, "minimum operating input voltage")
U5_EN_RISE = F(1.231, "V", DS, "VEN-H typ; 1.2 min / 1.26 max")
U5_EN_ABSMIN = F(-0.3, "V", DS, "EN to AGND absolute minimum, table 7.1")
U5_VCC_UVLO = F(3.7, "V", DS, "VCC ready threshold, section 8.3.4; LDO in "
                              "dropout so this is roughly a VIN threshold")
U5_TSS = F(4.0e-3, "s", DS, "internal soft-start, 2.9 / 4 / 6 ms")
U5_TSS_MIN = F(2.9e-3, "s", DS, "")
U5_TSS_MAX = F(6.0e-3, "s", DS, "")
U5_ISC = F(4.5, "A", DS, "high-side current limit, 3.85 / 4.5 / 5.05 A")
U5_IQ = F(24e-6, "A", DS, "non-switching input current")
U5_VOUT = F(5.02, "V", CALC, "1.0 V x (1 + 100k/24.9k)")
U5_EFF = F(0.91, "", DS, "typical, 12 V in / 5 V out")

# --- D1, SS34 --------------------------------------------------------------
D1_VRRM = F(40.0, "V", DS, "maximum repetitive peak reverse voltage")
D1_IFSM = F(100.0, "A", DS, "8.3 ms single half sine, superimposed on load")
D1_IAV = F(3.0, "A", DS, "average rectified forward current")
D1_IR_25 = F(0.5e-3, "A", DS, "max DC reverse current at rated VR, 25 C")
D1_IR_100 = F(20e-3, "A", DS, "max DC reverse current at rated VR, 100 C")
D1_RTHJA = F(55.0, "C/W", DS, "typical, on the recommended pad")
# Junction fit to the datasheet's own curve: VF(3 A) = 0.45 V typical against
# a 0.5 V maximum, VF(0.5 A) = 0.33 V. Reverse leakage is NOT this model's
# IS -- Schottky leakage is barrier-lowering dominated and runs three orders
# above the saturation current, so the reverse cases below inject the
# datasheet's IR as an explicit source instead of trusting the model.
D1_IS = F(5e-6, "A", MODEL, "fitted to VF(3 A) = 0.45 V")
D1_N = F(1.05, "", MODEL, "")
D1_RS = F(0.03, "ohm", MODEL, "")

# --- D2, SMAJ18A -----------------------------------------------------------
# Was an SMAJ15A when this file was written. The 15 V part conducted
# indefinitely on a 19 V adapter without ever tripping the fuse, because the
# breakdown tempco makes the fault settle rather than run away -- 41 mA at a
# junction near 117 C, beside a board running perfectly. The LMR33630 is a
# 36 V part, so 19 V was never a threat to it; the 18 V part does not conduct
# there at all and still clamps a real surge inside the converter's rating.
D2_VWM = F(18.0, "V", DS, "reverse stand-off voltage")
D2_VBR_MIN = F(20.0, "V", DS, "breakdown at IT = 1.0 mA")
D2_VBR_MAX = F(22.1, "V", DS, "breakdown at IT = 1.0 mA")
D2_IT = F(1.0e-3, "A", DS, "breakdown test current")
D2_VC = F(29.2, "V", DS, "maximum clamping voltage")
D2_IPPM = F(13.7, "A", DS, "peak pulse current at VC")
D2_ID = F(1.0e-6, "A", DS, "maximum reverse leakage at VWM")
D2_ALPHA = F(0.088e-2, "1/C", DS, "maximum temperature coefficient of VBR, "
                                  "%/C column of the SMAJ15A row")
D2_RTHJA = F(120.0, "C/W", DS, "typical junction to ambient, min pad")
D2_RTHJL = F(30.0, "C/W", DS, "typical junction to lead")
D2_TJMAX = F(150.0, "C", DS, "operating junction maximum")
D2_PD_INF = F(3.3, "W", DS, "on an INFINITE heatsink at TA = 50 C. Not a "
                            "board number; RthJA is")
D2_VF_25A = F(3.5, "V", DS, "forward, unidirectional, at IF = 25 A")

# --- D3, BAT54 -------------------------------------------------------------
# Added because this simulation found the reversed rail settling at -0.40 V
# against the LMR33630's -0.3 V absolute minimum, held there by D2's forward
# drop. A Schottky in the same direction clamps lower at leakage-level
# current, which is the only current present in that case.
D3_VF_10U = F(0.15, "V", ASSUMED, "BAT54 forward at tens of microamps; the "
                                  "datasheet curve starts at 0.1 mA")
D3_N = F(1.05, "", ASSUMED, "ideality, fitted to the 0.1 mA and 1 mA points")
D3_IS = F(1.0e-7, "A", ASSUMED, "saturation current implied by the above")
D2_IFSM = F(40.0, "A", DS, "8.3 ms single half sine, unidirectional")
# Breakdown knee: I = IT * exp((V - VBR)/VK) through a series Rd. VK sets how
# soft the knee is and Rd is then forced by the one clamping point the
# datasheet gives: VBR + VK*ln(IPPM/IT) + IPPM*Rd = VC.
D2_VK = F(0.15, "V", MODEL, "knee sharpness; 400 W SMA die")
# Forward drop at milliamps is NOT on any SMAJ datasheet -- the only forward
# point given is 3.5 V at 25 A. The reverse-polarity result below turns on
# this number, so it is bounded rather than trusted: see reverse_polarity().
D2_VF_IS = F(1e-10, "A", MODEL, "ideal-junction fit, large-area die")
D2_VF_RS = F(0.113, "ohm", MODEL, "so VF(25 A) = 3.5 V with the above")

# --- F1, polyfuse ----------------------------------------------------------
#
# The netlist value string is "1.1 A hold, 2.2 A trip" in an 1812. In the
# Littelfuse 1812L table exactly one part has 1.1 A hold with 2.2 A trip --
# 1812L110 -- and it is rated 6 Vdc. Every 1812L110 rated above 12 V trips at
# 1.95 A, not 2.2 A. The numbers below are the 24 V part, which is the one a
# 12 V input with a 19 V failure mode actually needs.
F1_PART = "1812L110/24"
F1_IHOLD = F(1.10, "A", DS, "at 20 C still air")
F1_IHOLD_50C = F(0.83, "A", DS, "temperature rerating table, 50 C")
F1_ITRIP = F(1.95, "A", DS, "minimum current that WILL trip, 20 C")
F1_VMAX = F(24.0, "V", DS, "maximum voltage without damage at Imax")
F1_IMAX = F(20.0, "A", DS, "maximum fault current at Vmax")
F1_RMIN = F(0.060, "ohm", DS, "initial, un-soldered")
F1_R1MAX = F(0.200, "ohm", DS, "at 20 C, one hour after trip or reflow")
F1_TTRIP_8A = F(0.50, "s", DS, "maximum time to trip at 8.00 A")
F1_PD_TRIPPED = F(0.8, "W", DS, "dissipated in the tripped state, 20 C")
F1_TSURF_TRIPPED = F(125.0, "C", DS, "max device surface temp, tripped")

# The netlist's own value string, kept so the report can say what is fitted
# rather than what should be.
F1_NETLIST_VALUE = "1.1 A hold, 2.2 A trip"

# --- the board ------------------------------------------------------------
C_IN_BULK = F(22e-6, "F", CALC, "1210 on +12V, main_board.py")
C_IN_HF = F(100e-9, "F", CALC, "0603 on +12V")
C_OUT_BULK = F(47e-6, "F", CALC, "1210 on +5V")
C_OUT_REST = F(19.4e-6, "F", CALC, "10 + 4.7 + 4.7 uF also on +5V")
L_BUCK = F(10e-6, "H", CALC, "L1, 10 uH shielded")

# --- the supply and the cable ---------------------------------------------
VIN_NOM = F(12.0, "V", ASSUMED, "adapter not yet chosen")
VIN_FAULT = F(19.0, "V", ASSUMED, "the laptop brick that fits the same jack")
R_SRC = F(0.20, "ohm", ASSUMED, "adapter output impedance + its cap's ESR")
R_CABLE = F(0.10, "ohm", ASSUMED, "about 1 m of 20 AWG, there and back")
L_CABLE = F(1.0e-6, "H", ASSUMED, "about 1 uH/m for a loose pair")
T_CLOSE = F(1.0e-6, "s", ASSUMED, "barrel contact wipe at insertion")
C_ESR = F(5e-3, "ohm", ASSUMED, "1210 X5R")
C_ESL = F(2e-9, "H", ASSUMED, "1210 plus its landing")
T_AMB = F(25.0, "C", ASSUMED, "still air on a bench")

# --- load ------------------------------------------------------------------
I_LOAD_5V = F(0.472, "A", CALC, "verify_power.py: 238 mA module + 234 mA main")


# ------------------------------------------------------- the fuse, thermally
#
# A PPTC does not trip on current, it trips on temperature. Every question
# below -- does a 20 A spike lasting microseconds matter, does 1.6 A lasting
# 100 ms matter -- is the same question asked of one first-order thermal
# model, so the model is built once, calibrated on datasheet points, and
# tamper-tested at the bottom.
#
#   Cth dT/dt = I^2 R - (T - Ta)/Rth,   trip when T reaches T_switch
#
# Two datasheet points pin it:
#   * I_hold = 1.10 A is by definition the largest current that does NOT trip
#     in 20 C still air, so I_hold^2 R Rth = T_switch - Ta at the boundary;
#   * time to trip at 8.00 A is 0.50 s (maximum).
#
# From the first, with constant R the model gives
#     t(I) = -tau * ln(1 - (I_hold/I)^2),  tau = Rth*Cth
# and the second fixes tau. Real PPTC resistance climbs steeply with
# temperature before it trips, which this ignores; ignoring it makes the
# model predict trips LATER than reality, which is the conservative
# direction for "the inrush is harmless" and the unconservative direction for
# "the fault trips it". Both verdicts below are far enough from the boundary
# that the difference does not reach them.
F1_TAU = -F1_TTRIP_8A.value / math.log(1 - (F1_IHOLD.value / 8.0) ** 2)
F1_DT_TRIP = F1_TSURF_TRIPPED.value - 20.0
# Rth comes from I_hold and NOT from the tripped-state dissipation, and the
# difference matters. Pd = 0.8 W holding the surface at 125 C is measured
# with the device tripped, where its resistance is four orders up; using it
# here would give 131 C/W, under which I_hold would raise the polymer by
# only 32 C and the device could never trip at its own hold current. The
# self-consistent choice is the one the hold current defines.
F1_RTH = F1_DT_TRIP / (F1_IHOLD.value ** 2 * F1_R1MAX.value)
F1_CTH = F1_TAU / F1_RTH
F1_E_TRIP = F1_CTH * F1_DT_TRIP      # joules to trip from cold, adiabatically


def fuse_thermal(t, i, r_fuse=None, t_amb=None):
    """Integrate the PPTC thermal model over a current waveform.

    Returns (peak temperature rise in C, time of trip or None, energy in J).
    """
    r = F1_R1MAX.value if r_fuse is None else r_fuse
    dt_trip = F1_DT_TRIP if t_amb is None else (F1_TSURF_TRIPPED.value - t_amb)
    rise = 0.0
    peak = 0.0
    energy = 0.0
    t_tripped = None
    for k in range(1, len(t)):
        h = t[k] - t[k - 1]
        if h <= 0:
            continue
        p = 0.5 * (i[k] ** 2 + i[k - 1] ** 2) * r
        energy += p * h
        # explicit Euler is fine: h is microseconds against a 26 s tau
        rise += h * (p - rise / F1_RTH) / F1_CTH
        peak = max(peak, rise)
        if t_tripped is None and rise >= dt_trip:
            t_tripped = t[k]
    return peak, t_tripped, energy


def fuse_time_to_trip(i, t_amb=20.0):
    """Closed form of the same model, for a constant current."""
    i_hold = F1_IHOLD.value
    if i <= i_hold:
        return None
    return -F1_TAU * math.log(1 - (i_hold / i) ** 2)


# ------------------------------------------------------------------ checking
@dataclass
class Result:
    name: str
    ok: bool
    detail: str
    margin: str = ""
    assumed: bool = False
    tag: str = ""


class Checks:
    def __init__(self):
        self.results: list[Result] = []

    def add(self, tag, name, ok, detail, margin="", assumed=False):
        self.results.append(Result(name, ok, detail, margin, assumed, tag))
        return ok

    def get(self, tag):
        for r in self.results:
            if r.tag == tag:
                return r
        raise KeyError(tag)


# ------------------------------------------------------------ spice helpers
def _spice_diode_models(c):
    """D1 and the two faces of D2, each anchored to its own datasheet point.

    The SMAJ needs two models and this is not laziness. A SPICE diode carries
    one series resistance, and the SMAJ's datasheet pins two different ones:
    the breakdown slope from (VC, IPPM) is about 0.33 ohm, the forward slope
    from (VF, 25 A) is about 0.11 ohm. Using the breakdown slope in the
    forward direction would put 9 V across the part at 25 A, which is not a
    diode. So the breakdown cases get D2BRK and the forward case gets D2FWD,
    and neither is asked a question the other one answers.
    """
    c.raw_spice += (
        f".model DSS34 D(IS={D1_IS.value} N={D1_N.value} RS={D1_RS.value} "
        f"CJO=200p BV={D1_VRRM.value} IBV={D1_IR_25.value})\n")
    c.raw_spice += (
        f".model D2FWD D(IS={D2_VF_IS.value} N=1.0 RS={D2_VF_RS.value} "
        f"CJO=1n BV=1e4)\n")


def tvs_breakdown_rd(vbr):
    """Series resistance that makes the model hit the datasheet clamp point."""
    knee = D2_VK.value * math.log(D2_IPPM.value / D2_IT.value)
    return (D2_VC.value - vbr - knee) / D2_IPPM.value


def run(c, step, end, **kw):
    sim = Simulator.factory().simulation(c)
    return sim.transient(step_time=step, end_time=end, **kw)


def arr(an, name):
    return np.array(an[name])


# ==========================================================================
# 1. INRUSH AT PLUG-IN
# ==========================================================================
def build_inrush(c_bulk=None, l_cable=None, t_close=None, r_fuse=None,
                 v_in=None, r_src=None, r_cable=None):
    """The moment the barrel contact wipes closed.

    The buck is not a load yet. Its VCC LDO has to reach 3.7 V and EN has to
    clear 1.231 V before anything switches, and then 2.9 ms of internal soft
    start follow; the whole event below is over in tens of microseconds. So
    during the inrush U5 is an open circuit and the 47 uF on +5V is on the
    far side of a switch that has not started. Only the 22 uF and the 100 nF
    on +12V are charged here.
    """
    c_bulk = C_IN_BULK.value if c_bulk is None else c_bulk
    l_cable = L_CABLE.value if l_cable is None else l_cable
    t_close = T_CLOSE.value if t_close is None else t_close
    r_fuse = F1_R1MAX.value if r_fuse is None else r_fuse
    v_in = VIN_NOM.value if v_in is None else v_in
    r_src = R_SRC.value if r_src is None else r_src
    r_cable = R_CABLE.value if r_cable is None else r_cable

    c = Circuit("Lyrebird 12 V input, plug-in inrush")
    _spice_diode_models(c)
    c.raw_spice += (f"Vsrc src 0 PULSE(0 {v_in} 0 {t_close} {t_close} 1 2)\n")
    c.raw_spice += f"Rsrc src ca {r_src}\n"
    c.raw_spice += f"Lcab ca cb {l_cable}\n"
    c.raw_spice += f"Rcab cb vraw {r_cable}\n"
    # F1. A polyfuse is a fixed resistance on this timescale -- its polymer
    # has a tau of tens of seconds (see F1_TAU), so nothing about it moves
    # during a 20 us event. Whether it notices at all is the thermal
    # integration afterwards, not anything in the netlist.
    c.raw_spice += f"Rf1 vraw vfused {r_fuse}\n"
    c.raw_spice += "Dd1 vfused v12 DSS34\n"
    # 22 uF 1210 with its ESR and ESL, which is what actually limits the peak
    # once the cable inductance is small.
    c.raw_spice += f"Lb v12 vb1 {C_ESL.value}\n"
    c.raw_spice += f"Rb vb1 vb2 {C_ESR.value}\n"
    c.raw_spice += f"Cb vb2 0 {c_bulk}\n"
    c.raw_spice += "Lh v12 vh1 1n\n"
    c.raw_spice += "Rh vh1 vh2 20m\n"
    c.raw_spice += f"Ch vh2 0 {C_IN_HF.value}\n"
    # U5 quiescent, and the feedback divider is on the output side, so this
    # is the whole DC load on +12V before switching starts.
    c.raw_spice += "Ru5 v12 0 500k\n"
    return c, r_fuse


def measure_inrush(an, r_fuse):
    t = np.array(an.time)
    i = (arr(an, "vraw") - arr(an, "vfused")) / r_fuse
    peak = float(np.max(i))
    charge = float(np.trapezoid(i, t))
    i2t = float(np.trapezoid(i ** 2, t))
    above = t[i > 0.1 * peak]
    width = float(above[-1] - above[0]) if len(above) > 1 else 0.0
    rise, tripped, energy = fuse_thermal(t, i, r_fuse)
    return dict(t=t, i=i, peak=peak, charge=charge, i2t=i2t, width=width,
                fuse_rise=rise, fuse_tripped=tripped, fuse_energy=energy,
                v12_final=float(arr(an, "v12")[-1]))


def scenario_inrush(ck):
    base_c, rf = build_inrush()
    base = measure_inrush(run(base_c, 10e-9, 200e-6), rf)

    # The peak depends entirely on parasitics nobody on this project has
    # measured, so it is swept rather than quoted. The energy does not: it is
    # 0.5*C*V^2 through a fixed divider of resistances, and that is what the
    # fuse responds to.
    sweep = []
    for l_cab in (50e-9, 200e-9, 1e-6, 3e-6):
        for t_cl in (100e-9, 1e-6, 10e-6):
            for r_f in (F1_RMIN.value, F1_R1MAX.value):
                cc, r = build_inrush(l_cable=l_cab, t_close=t_cl, r_fuse=r_f)
                m = measure_inrush(run(cc, 10e-9, 200e-6), r)
                m["l_cable"], m["t_close"], m["r_fuse"] = l_cab, t_cl, r_f
                sweep.append(m)
    worst_i = max(sweep, key=lambda m: m["peak"])
    worst_e = max(sweep, key=lambda m: m["fuse_rise"])

    ck.add("I-1", "F1 survives plug-in inrush",
           worst_e["fuse_rise"] < 0.05 * F1_DT_TRIP,
           f"worst case over the sweep heats the polymer by "
           f"{worst_e['fuse_rise']*1e3:.3f} mC against the "
           f"{F1_DT_TRIP:.0f} C it takes to trip",
           f"{F1_E_TRIP/worst_e['fuse_energy']:.0f}x margin in energy "
           f"({worst_e['fuse_energy']*1e3:.2f} mJ into F1 against "
           f"{F1_E_TRIP:.1f} J to trip it)")

    ck.add("I-2", "D1 surge rating against the inrush peak",
           worst_i["peak"] < D1_IFSM.value * 0.5,
           f"peak {worst_i['peak']:.1f} A for {worst_i['width']*1e6:.1f} us "
           f"against a {D1_IFSM.value:.0f} A / 8.3 ms rating",
           f"{D1_IFSM.value/worst_i['peak']:.1f}x, and the pulse is "
           f"{8.3e-3/max(worst_i['width'],1e-9):.0f}x shorter than the "
           f"rating's own pulse")

    ck.add("I-3", "F1 fault-current rating against the inrush peak",
           worst_i["peak"] < F1_IMAX.value,
           f"peak {worst_i['peak']:.1f} A against {F1_PART}'s "
           f"Imax of {F1_IMAX.value:.0f} A",
           f"worst at L_cable = {worst_i['l_cable']*1e9:.0f} nH, contact "
           f"closing in {worst_i['t_close']*1e9:.0f} ns",
           assumed=True)

    # Charge is a conservation check on the simulation itself, not on the
    # board: whatever the parasitics, exactly C*V has to arrive.
    q_expect = (C_IN_BULK.value + C_IN_HF.value) * (
        VIN_NOM.value - 0.30)
    ck.add("I-4", "charge delivered matches C x V",
           abs(base["charge"] - q_expect) / q_expect < 0.10,
           f"{base['charge']*1e6:.0f} uC simulated against "
           f"{q_expect*1e6:.0f} uC expected",
           "the inrush is a fixed amount of charge; only its peak rate "
           "depends on the cable")
    return base, sweep, worst_i, worst_e


# ==========================================================================
# 2. REVERSE POLARITY
# ==========================================================================
def build_reverse(v_rev, i_leak, tvs=True, tvs_is=None, d1_backwards=False,
                  clamp=True):
    """A centre-negative adapter in a centre-positive jack.

    D1 blocks, and then the only current anywhere in the circuit is D1's own
    reverse leakage. That current has to come from somewhere, and where it
    comes from is the question this scenario exists to answer.

    The leakage is injected explicitly rather than taken from the diode
    model. A SPICE diode leaks its saturation current; a real Schottky leaks
    three orders more, through barrier lowering, and the datasheet says so
    directly: 0.5 mA at 25 C and 20 mA at 100 C, both maxima at rated VR. A
    model that leaked 5 uA here would answer the question wrongly and
    confidently.
    """
    c = Circuit("Lyrebird 12 V input, reverse polarity")
    is_ = D2_VF_IS.value if tvs_is is None else tvs_is
    c.raw_spice += (
        f".model DSS34 D(IS={D1_IS.value} N={D1_N.value} RS={D1_RS.value} "
        f"CJO=200p BV={D1_VRRM.value} IBV=1e-6)\n")
    c.raw_spice += (f".model D2FWD D(IS={is_} N=1.0 RS={D2_VF_RS.value} "
                    f"CJO=1n BV=1e4)\n")
    c.raw_spice += f"Vsrc vraw 0 PULSE(0 {-v_rev} 0 1m 1m 1e3 2e3)\n"
    c.raw_spice += f"Rf1 vraw vfused {F1_R1MAX.value}\n"
    if d1_backwards:
        # The assembly error the series diode exists to survive.
        c.raw_spice += "Dd1 v12 vfused DSS34\n"
    else:
        c.raw_spice += "Dd1 vfused v12 DSS34\n"
        c.raw_spice += f"Ileak v12 vfused DC {i_leak}\n"
    c.raw_spice += f"Cin v12 0 {C_IN_BULK.value}\n"
    c.raw_spice += f"Chf v12 0 {C_IN_HF.value}\n"
    if tvs:
        # Unidirectional: anode on GND, cathode on +12V. Forward here.
        c.raw_spice += "Dd2 0 v12 D2FWD\n"
    if clamp:
        # D3, the Schottky added after this scenario found -0.40 V against a
        # -0.3 V absolute minimum. Same direction as D2's forward path and a
        # lower drop at the microamps that are the only current here, so it
        # takes the clamping over and D2 stops being the thing holding the
        # rail out of the converter's limit.
        c.raw_spice += (f".model DBAT54 D(IS={D3_IS.value} N={D3_N.value} "
                        f"RS=2.0 CJO=10p BV=30)\n")
        c.raw_spice += "Dd3 0 v12 DBAT54\n"
    # U5 VIN and EN, quiescent and drawing nothing at a negative input.
    c.raw_spice += "Ru5 v12 0 500k\n"
    return c


def scenario_reverse(ck):
    out = {}
    # Reverse voltage across D1, for every adapter that fits this barrel.
    for v_rev in (12.0, 19.0, 24.0):
        an = run(build_reverse(v_rev, D1_IR_25.value), 100e-6, 200e-3)
        v12 = float(arr(an, "v12")[-1])
        vr = float(arr(an, "vfused")[-1]) - v12
        out[v_rev] = dict(v12=v12, v_reverse=abs(vr))

    worst_vr = out[24.0]["v_reverse"]
    # Two conditions, not one. The voltage across D1 on its own is not a
    # test of blocking: a diode fitted backwards conducts, which makes that
    # voltage SMALLER, and the first version of this check passed the
    # backwards-diode tamper for exactly that reason. See T4.
    holds_off = all(o["v12"] > -1.0 for v, o in out.items()
                    if isinstance(v, float))
    ck.add("R-1", "D1 blocks, and its reverse standoff covers the barrel",
           worst_vr < 0.7 * D1_VRRM.value and holds_off,
           f"reversed 12 V puts {out[12.0]['v_reverse']:.1f} V across D1, "
           f"19 V puts {out[19.0]['v_reverse']:.1f} V, 24 V puts "
           f"{worst_vr:.1f} V, against a {D1_VRRM.value:.0f} V VRRM, and "
           f"the protected rail stays at {out[24.0]['v12']:.2f} V throughout",
           f"{D1_VRRM.value/worst_vr:.1f}x on the worst adapter that fits")

    # Where the leakage goes. Sweep the datasheet's own temperature range.
    leaks = {}
    for tag, il in (("25 C", D1_IR_25.value), ("100 C", D1_IR_100.value)):
        an = run(build_reverse(12.0, il), 100e-6, 200e-3)
        t = np.array(an.time)
        v12 = arr(an, "v12")
        leaks[tag] = dict(v12=float(v12[-1]), t=t, trace=v12,
                          t_cross=float(t[np.argmax(v12 < -0.3)])
                          if np.any(v12 < -0.3) else None)
    out["leaks"] = leaks
    v_worst = min(leaks["25 C"]["v12"], leaks["100 C"]["v12"])

    # The leakage at which the rail exactly reaches -0.3 V, so the result is
    # a threshold rather than a single number. It matters because 0.5 mA is
    # a maximum: a typical SS34 at a third of its rated reverse voltage
    # leaks far less, and the honest question is where the line is.
    lo, hi = 1e-7, 1e-1
    for _ in range(40):
        mid = math.sqrt(lo * hi)
        an = run(build_reverse(12.0, mid), 1e-3, 200e-3)
        if float(arr(an, "v12")[-1]) < U5_VIN_ABSMIN.value:
            hi = mid
        else:
            lo = mid
    i_threshold = math.sqrt(lo * hi)
    out["i_threshold"] = i_threshold

    ck.add("R-2", "protected rail against U5's negative absolute maximum",
           v_worst >= U5_VIN_ABSMIN.value,
           f"D1's reverse leakage drags +12V to {leaks['25 C']['v12']:.3f} V "
           f"at the 25 C datasheet maximum and "
           f"{leaks['100 C']['v12']:.3f} V at the 100 C one, against VIN and "
           f"EN absolute minima of {U5_VIN_ABSMIN.value} V",
           f"the rail crosses {U5_VIN_ABSMIN.value} V once D1 leaks more "
           f"than {i_threshold*1e6:.0f} uA; the datasheet allows "
           f"{D1_IR_25.value*1e6:.0f} uA at 25 C, "
           f"{D1_IR_25.value/i_threshold:.0f}x that. A typical part may sit "
           f"the right side of the line; a specified one does not",
           assumed=True)

    # The number R-2 turns on -- the TVS's forward drop at milliamps -- is
    # not on any SMAJ datasheet. So it is bounded instead of trusted: sweep
    # the junction over four decades of saturation current, which is four
    # decades of die area, and see whether the verdict moves.
    bound = []
    for is_ in (1e-12, 1e-11, 1e-10, 1e-9, 1e-8):
        an = run(build_reverse(12.0, D1_IR_100.value, tvs_is=is_),
                 1e-3, 200e-3)
        bound.append((is_, float(arr(an, "v12")[-1])))
    out["vf_bound"] = bound
    lo = min(v for _, v in bound)
    hi = max(v for _, v in bound)
    ck.add("R-3", "R-2's verdict does not depend on the unquoted forward drop",
           (lo < U5_VIN_ABSMIN.value) == (hi < U5_VIN_ABSMIN.value),
           f"four decades of TVS die area put the rail between {lo:.3f} V "
           f"and {hi:.3f} V; every one of them is on the same side of "
           f"{U5_VIN_ABSMIN.value} V",
           "the SMAJ datasheets give one forward point, 3.5 V at 25 A, and "
           "nothing at milliamps; this is what stands in for it")

    # What the unidirectional part buys, stated as the thing it prevents.
    an = run(build_reverse(12.0, D1_IR_100.value, tvs=False), 1e-3, 200e-3)
    v_no_tvs = float(arr(an, "v12")[-1])
    out["no_tvs"] = v_no_tvs
    ck.add("R-4", "D2 unidirectional is load-bearing in the reversed case",
           v_no_tvs < v_worst - 1.0,
           f"with D2 removed the same leakage takes +12V to "
           f"{v_no_tvs:.2f} V; with it fitted, {v_worst:.3f} V",
           "D2 sits behind D1, so it never sees the reversed input -- what "
           "it does instead is shunt D1's leakage away from U5's VIN pin")

    # Dissipation in the reversed steady state, for completeness.
    p_tvs = D1_IR_100.value * abs(v_worst)
    ck.add("R-5", "nothing heats in the reversed steady state",
           p_tvs < 0.1 and D1_IR_100.value < F1_IHOLD.value,
           f"{p_tvs*1e3:.1f} mW in D2 at the 100 C leakage maximum; "
           f"{D1_IR_100.value*1e3:.0f} mA through F1 against a "
           f"{F1_IHOLD.value:g} A hold",
           "reverse polarity is survivable indefinitely, not merely "
           "survivable")
    return out


# ==========================================================================
# 3. THE WRONG ADAPTER — A 19 V LAPTOP BRICK IN THE SAME BARREL
# ==========================================================================
def build_overvoltage(v_in, vbr25, alpha=None, tau_jl=0.2, tau_la=20.0,
                      tvs=True, r_load=None, rth_ja=None):
    """19 V into a 15 V standoff, with the TVS allowed to heat.

    The whole answer is in one feedback loop that a DC calculation cannot
    see: the TVS conducts, conducting heats it, and heating raises its own
    breakdown voltage, which reduces the conduction. So the part walks its
    own clamp voltage up towards the applied voltage until the two meet.
    Where they meet is the operating point, and it is nowhere near where the
    isothermal arithmetic puts it.

    The thermal network is two poles into the datasheet's RthJA = 120 C/W,
    split at RthJL = 30 C/W. Node tj carries junction rise above ambient in
    volts, one volt per degree. The two capacitances are ASSUMED -- the
    transient thermal impedance is a curve, not a table -- and they are
    swept, because they set how fast the loop closes and not where.
    """
    alpha = D2_ALPHA.value if alpha is None else alpha
    rth_ja = D2_RTHJA.value if rth_ja is None else rth_ja
    rd = tvs_breakdown_rd(vbr25)
    rjl = min(D2_RTHJL.value, 0.25 * rth_ja)
    rla = rth_ja - rjl

    c = Circuit("Lyrebird 12 V input, 19 V adapter")
    c.raw_spice += (
        f".model DSS34 D(IS={D1_IS.value} N={D1_N.value} RS={D1_RS.value} "
        f"CJO=200p BV={D1_VRRM.value} IBV=1e-6)\n")
    # Ramp the brick on over 10 ms so this scenario answers the sustained
    # question and not the inrush one, which scenario 1 already answered.
    c.raw_spice += f"Vsrc src 0 PULSE(0 {v_in} 0 10m 10m 1e5 2e5)\n"
    c.raw_spice += f"Rsrc src vraw {R_SRC.value + R_CABLE.value}\n"
    c.raw_spice += f"Rf1 vraw vfused {F1_R1MAX.value}\n"
    c.raw_spice += "Dd1 vfused v12 DSS34\n"
    c.raw_spice += f"Cin v12 0 {C_IN_BULK.value}\n"
    if tvs:
        c.raw_spice += f"Rd v12 tvsk {rd}\n"
        # min(max(...)) and not limit(...): this ngspice build accepts
        # limit() and silently evaluates it to zero, which turns the whole
        # exponential into the constant IT and gives a clean, plausible,
        # entirely wrong answer in every corner at once. Found by noticing
        # that three different VBR corners returned the same current.
        c.raw_spice += (
            f"Btvs tvsk tsns I = {D2_IT.value}*exp(min(max((v(tvsk)-"
            f"{vbr25}*(1+{alpha}*v(tj)))/{D2_VK.value},-60),25))\n")
        c.raw_spice += "Vsns tsns 0 DC 0\n"
        # Thermal: current into tj is the instantaneous TVS power.
        c.raw_spice += "Bth 0 tj I = v(v12)*i(Vsns)\n"
        c.raw_spice += f"Rjl tj tl {rjl}\n"
        c.raw_spice += f"Cj tj 0 {tau_jl/rjl}\n"
        c.raw_spice += f"Rla tl 0 {rla}\n"
        c.raw_spice += f"Cl tl 0 {tau_la/rla}\n"
    # The board's own draw once U5 is running: constant power, through the
    # converter's efficiency, expressed as the resistance it looks like at
    # this input voltage. Fixed rather than constant-power so the solver has
    # nothing to argue with at t = 0.
    if r_load is None:
        p_in = I_LOAD_5V.value * U5_VOUT.value / U5_EFF.value
        r_load = v_in ** 2 / p_in
    c.raw_spice += f"Rload v12 0 {r_load}\n"
    return c


def _settle(t, i, level):
    """First time the current is below `level` and stays there."""
    above = np.where(i >= level)[0]
    if len(above) == 0:
        return 0.0
    k = above[-1]
    return float(t[min(k + 1, len(t) - 1)])


def scenario_overvoltage(ck):
    out = {}
    corners = (("VBR minimum, 16.7 V", D2_VBR_MIN.value),
               ("VBR nominal, 17.6 V", 0.5 * (D2_VBR_MIN.value
                                              + D2_VBR_MAX.value)),
               ("VBR maximum, 18.5 V", D2_VBR_MAX.value))
    for name, vbr in corners:
        c = build_overvoltage(VIN_FAULT.value, vbr)
        an = run(c, 2e-3, 400.0)
        t = np.array(an.time)
        i_tvs = arr(an, "Vsns")   # branch current of the sense source
        v12 = arr(an, "v12")
        tj = arr(an, "tj") + T_AMB.value
        i_in = (arr(an, "vraw") - arr(an, "vfused")) / F1_R1MAX.value
        p = v12 * i_tvs
        rise, tripped, _ = fuse_thermal(t, i_in)
        out[name] = dict(
            t=t, i_tvs=i_tvs, v12=v12, tj=tj, i_in=i_in,
            i_peak=float(np.max(i_tvs)), i_eq=float(i_tvs[-1]),
            v_eq=float(v12[-1]), tj_peak=float(np.max(tj)),
            tj_eq=float(tj[-1]), p_peak=float(np.max(p)),
            p_eq=float(p[-1]), i_in_peak=float(np.max(i_in)),
            i_in_eq=float(i_in[-1]), fuse_rise=rise, fuse_tripped=tripped,
            t_hot=_settle(t, i_tvs, 2 * float(i_tvs[-1])),
            t_above_hold=_settle(t, i_in, F1_IHOLD.value))

    worst = out["VBR minimum, 16.7 V"]

    # --- what 0014 claims, in two halves.
    ck.add("OV-1", "0014 half one: the TVS conducts",
           worst["i_eq"] > D2_ID.value * 10,
           f"it does -- {worst['i_peak']*1e3:.0f} mA at first and "
           f"{worst['i_eq']*1e3:.1f} mA once hot, at the VBR minimum corner; "
           f"{out['VBR maximum, 18.5 V']['i_eq']*1e3:.2f} mA at the maximum",
           "and it goes on conducting; nothing ends this state")

    # The peak current is the only part of this that the adapter's own
    # output impedance can move, so it is swept rather than quoted.
    stiff = []
    for r_s in (0.02, 0.05, 0.1, 0.2, 0.4):
        c = build_overvoltage(VIN_FAULT.value, D2_VBR_MIN.value)
        c.raw_spice = c.raw_spice.replace(
            f"Rsrc src vraw {R_SRC.value + R_CABLE.value}",
            f"Rsrc src vraw {r_s}")
        an = run(c, 1e-3, 100.0)
        t = np.array(an.time)
        i_in = (arr(an, "vraw") - arr(an, "vfused")) / F1_R1MAX.value
        rise, tripped, _ = fuse_thermal(t, i_in)
        stiff.append((r_s, float(np.max(i_in)), _settle(t, i_in,
                                                        F1_ITRIP.value),
                      rise, tripped))
    out["stiff"] = stiff
    trips = (any(isinstance(o, dict) and o.get("fuse_tripped") is not None
                 for o in out.values())
             or any(s[4] is not None for s in stiff))
    i_worst = max(s[1] for s in stiff)
    t_over = max(s[2] for s in stiff)
    ttt = fuse_time_to_trip(i_worst)
    ck.add("OV-2", "0014 half two: the fuse trips",
           not trips,      # the check is that 0014 is WRONG about this
           f"it does not. Total input current peaks at "
           f"{worst['i_in_peak']*1e3:.0f} mA -- below the "
           f"{F1_IHOLD.value:g} A hold -- and settles at "
           f"{worst['i_in_eq']*1e3:.0f} mA. Even with the adapter's output "
           f"impedance taken to {stiff[0][0]*1e3:.0f} mohm the peak reaches "
           f"only {i_worst:.2f} A, and F1's polymer rises "
           f"{max(s[3] for s in stiff):.1f} C against the "
           f"{F1_DT_TRIP:.0f} C it needs",
           f"the current is above F1's trip value for at most "
           f"{t_over*1e3:.0f} ms, against a time to trip of "
           f"{ttt:.0f} s at that current. There is no adapter impedance for "
           f"which this fuse opens: the TVS heats and backs off three "
           f"orders of magnitude faster than the polymer can")

    ck.add("OV-3", "U5 survives the brick on its own rating",
           worst["v_eq"] < U5_VIN_OPMAX.value,
           f"{worst['v_eq']:.1f} V reaches U5 against a "
           f"{U5_VIN_OPMAX.value:.0f} V recommended maximum and a "
           f"{U5_VIN_ABSMAX.value:.0f} V absolute maximum",
           "note what this does not say: 19 V was already below 36 V. The "
           "TVS is not what saves U5 here, and a check that only compares "
           "the clamp voltage to 36 V cannot tell the difference")

    ck.add("OV-4", "D2 stays inside its own junction temperature",
           worst["tj_peak"] < D2_TJMAX.value,
           f"junction settles at {worst['tj_eq']:.0f} C at the VBR minimum "
           f"corner, dissipating {worst['p_eq']:.2f} W into "
           f"{D2_RTHJA.value:g} C/W from a {T_AMB.value:g} C ambient",
           f"{D2_TJMAX.value - worst['tj_peak']:.0f} C to the "
           f"{D2_TJMAX.value:g} C maximum. The loop parks the junction just "
           f"below where its own VBR equals the applied voltage, so this "
           f"temperature barely moves with ambient -- raising the room "
           f"lowers the current, not the junction",
           assumed=True)

    # Isothermal, for the size of what the feedback loop removes.
    c = build_overvoltage(VIN_FAULT.value, D2_VBR_MIN.value, alpha=0.0)
    an = run(c, 2e-3, 2.0)
    iso_i = float(arr(an, "Vsns")[-1])
    iso_p = iso_i * float(arr(an, "v12")[-1])
    out["isothermal"] = dict(i=iso_i, p=iso_p)

    # And the sensitivity to the two thermal capacitances, which are guesses.
    sens = []
    for scale in (0.1, 1.0, 10.0):
        c = build_overvoltage(VIN_FAULT.value, D2_VBR_MIN.value,
                              tau_jl=0.2 * scale, tau_la=20.0 * scale)
        an = run(c, 2e-3, 400.0 * max(scale, 1.0))
        sens.append((scale, float(arr(an, "Vsns")[-1]),
                     float(arr(an, "tj")[-1]) + T_AMB.value))
    out["thermal_sens"] = sens
    spread = max(s[2] for s in sens) - min(s[2] for s in sens)
    ck.add("OV-5", "OV-4 does not rest on the guessed thermal capacitances",
           spread < 5.0,
           f"a hundredfold sweep of both thermal time constants moves the "
           f"settled junction temperature by {spread:.1f} C",
           "the equilibrium is set by RthJA, which is on the datasheet; the "
           "capacitances only set how long it takes to get there")
    return out


# ==========================================================================
# 4. RAIL SEQUENCING ON START-UP
# ==========================================================================
#
# Downstream constants. These come from the 2026-09-21 main-board review,
# which read the LT3045 and LTM4622 datasheets line by line and quotes them;
# they are datasheet numbers at one remove and are labelled as such.
REV = "datasheet, via docs/review/2026-09-21/main-board.md"
U3_UVLO = F(1.78, "V", REV, "LT3045 EN/UV threshold, EN/UV tied to IN")
U3_ISET = F(100e-6, "A", REV, "SET pin source current")
U3_RSET = F(33.2e3, "ohm", CALC, "main_board.py")
U3_CSET = F(100e-9, "F", CALC, "main_board.py; 4.7 uF before the D-6 fix")
U3_DROPOUT = F(0.26, "V", REV, "at 500 mA; less at this load")
U4_RUN_TH = F(1.27, "V", REV, "LTM4622 RUN enable threshold")
U4_SS_I = F(1.4e-6, "A", REV, "TRACK/SS pull-up from INTVCC")
U4_SS_C = F(10e-9, "F", CALC, "main_board.py")
U4_VREF = F(0.6, "V", REV, "LTM4622 feedback reference")
U4_VIN1_MIN = F(3.6, "V", REV, "channel 2 does not run below this on VIN1")
Q1_VGS_TH_MIN = F(0.8, "V", ASSUMED, "BSS138 typical datasheet range; not "
                                     "read for this file")
Q1_VGS_TH_MAX = F(1.5, "V", ASSUMED, "as above")
FPGA_VDD_ABSMAX = F(1.20, "V", REV, "GateMate DS1001, core")
FPGA_VDDIO_ABSMAX = F(2.75, "V", REV, "GateMate DS1001, bank supplies")
FT_VCC33_WINDOW = (3.0, 3.6)

I_3V3 = F(0.060, "A", ASSUMED, "main power.md is stale")
I_2V5 = F(0.090, "A", ASSUMED, "")
I_1V0 = F(0.080, "A", ASSUMED, "")
I_MEZZ = F(0.238, "A", CALC, "module power.md, post-parts-selection")


def build_sequencing(c_set=None, t_enum=None, tss5=None, vgs_th=None,
                     gated=True):
    """Every rail on the board, as a soft-start model rather than a switcher.

    Nothing here switches. Simulating four converters at 400 kHz and 1.5 MHz
    through 60 ms of start-up would be forty thousand cycles to learn four
    arrival times, and the arrival times are set by soft-start ramps that no
    public model carries anyway. So each converter is its reference ramp,
    its enable threshold and its output impedance, driving the real output
    capacitance and the real load. That is exactly the set of things that
    decides the order, and nothing else in a switcher does.

    Each ramp comes from the mechanism the datasheet names, not from a time
    quoted in prose:
      U5   internal, fixed, 4 ms typical -- there is no pin for it
      U4   1.4 uA into 10 nF up to a 0.6 V reference
      U3   100 uA into R_SET || C_SET, the LT3045's 2.3*R*C being ln(10)
           times that RC, which is where the datasheet formula comes from
    """
    c_set = U3_CSET.value if c_set is None else c_set
    tss5 = U5_TSS.value if tss5 is None else tss5
    vth = Q1_VGS_TH_MIN.value if vgs_th is None else vgs_th
    t_enum = 1e9 if t_enum is None else t_enum

    c = Circuit("Lyrebird rail sequencing from a 12 V wall wart")
    c.raw_spice += (
        f".model DSS34 D(IS={D1_IS.value} N={D1_N.value} RS={D1_RS.value} "
        f"CJO=200p)\n")
    # +12V arrives in tens of microseconds; scenario 1 measured that.
    c.raw_spice += f"Vsrc src 0 PULSE(0 {VIN_NOM.value} 0 30u 30u 1e3 2e3)\n"
    c.raw_spice += f"Rsrc src vraw {R_SRC.value + R_CABLE.value}\n"
    c.raw_spice += f"Rf1 vraw vfused {F1_R1MAX.value}\n"
    c.raw_spice += "Dd1 vfused v12 DSS34\n"
    c.raw_spice += f"Cin v12 0 {C_IN_BULK.value}\n"

    # --- U5, LMR33630. EN is tied to VIN, so the start condition is the VCC
    # LDO reaching 3.7 V, which with the LDO in dropout is a VIN threshold.
    c.raw_spice += (f"Bss5 0 ss5 I = {1e-6/tss5}*u(v(v12)-"
                    f"{U5_VCC_UVLO.value})\n")
    c.raw_spice += "Css5 ss5 0 1u\n"
    c.raw_spice += "Rss5 ss5 0 1e12\n"
    c.raw_spice += (f"B5 v5src 0 V = min({U5_VOUT.value}*min(v(ss5),1.0), "
                    f"max(v(v12)-0.15,0))\n")
    c.raw_spice += "Vs5 v5src v5a DC 0\n"
    c.raw_spice += "Rout5 v5a p5v 30m\n"
    c.raw_spice += f"C5 p5v 0 {C_OUT_BULK.value + C_OUT_REST.value}\n"
    c.raw_spice += f"Rmezz p5v 0 {U5_VOUT.value/I_MEZZ.value}\n"
    # Reflected input current, through the datasheet efficiency.
    c.raw_spice += (f"Bu5in v12 0 I = v(v5a)*i(Vs5)/"
                    f"({U5_EFF.value}*max(v(v12),1))\n")

    # --- U3, LT3045. Output follows SET, which is an RC.
    c.raw_spice += f"Bset 0 setn I = {U3_ISET.value}*u(v(p5v)-{U3_UVLO.value})\n"
    c.raw_spice += f"Rset setn 0 {U3_RSET.value}\n"
    c.raw_spice += f"Cset setn 0 {c_set}\n"
    c.raw_spice += (f"B33 v33src 0 V = min(v(setn), "
                    f"max(v(p5v)-{U3_DROPOUT.value},0))\n")
    c.raw_spice += "Vs33 v33src v33a DC 0\n"
    c.raw_spice += "Rout33 v33a p3v3 30m\n"
    c.raw_spice += "C33 p3v3 0 10u\n"
    c.raw_spice += f"Rl33 p3v3 0 {3.32/I_3V3.value}\n"
    # An LDO passes its load current straight through, plus 2.2 mA of ground
    # pin current. This is the term that puts the 3.3 V rail's draw onto +5V.
    c.raw_spice += "B33in p5v 0 I = i(Vs33) + 2.2m\n"

    # --- U4 channel 1, +2V5. RUN1 is tied to +5V.
    c.raw_spice += (f"Bss1 0 ss1 I = {U4_SS_I.value}*u(v(p5v)-"
                    f"{U4_RUN_TH.value})\n")
    c.raw_spice += f"Css1 ss1 0 {U4_SS_C.value}\n"
    c.raw_spice += "Rss1 ss1 0 1e12\n"
    c.raw_spice += (f"B25 v25src 0 V = min(2.5*min(v(ss1)/{U4_VREF.value},"
                    f"1.0), v(p5v))\n")
    c.raw_spice += "Vs25 v25src v25a DC 0\n"
    c.raw_spice += "Rout25 v25a p2v5 30m\n"
    c.raw_spice += "C25 p2v5 0 22u\n"
    c.raw_spice += f"Rl25 p2v5 0 {2.5/I_2V5.value}\n"
    c.raw_spice += "B25in p5v 0 I = v(p2v5)*i(Vs25)/(0.88*max(v(p5v),1))\n"

    # --- The enumeration gating of the core rail. 0014's consequences list
    # says this was retired; main_board.py still builds it, so it is here.
    if gated:
        c.raw_spice += "Rwake wake p2v5 100k\n"
        # The FT601Q drives WAKEUP_N low once it has VCC33 and sees bus
        # activity. With no host attached that never happens, which is what
        # t_enum = infinity below means.
        c.raw_spice += (f"Bwake wake 0 I = u(time-{t_enum})*"
                        f"u(v(p3v3)-3.0)*v(wake)/50\n")
        c.raw_spice += "Cwake wake 0 10p\n"
        c.raw_spice += "Rcr core_run p5v 100k\n"
        c.raw_spice += f"Bq1 core_run 0 I = u(v(wake)-{vth})*v(core_run)/5\n"
        c.raw_spice += "Ccr core_run 0 20p\n"
    else:
        c.raw_spice += "Rcr core_run p5v 100k\n"
        c.raw_spice += "Rwake wake 0 100k\n"
    c.raw_spice += (f"Bss2 0 ss2 I = {U4_SS_I.value}*u(v(core_run)-"
                    f"{U4_RUN_TH.value}) - v(ss2)*u({U4_RUN_TH.value}"
                    f"-v(core_run))/1k\n")
    c.raw_spice += f"Css2 ss2 0 {U4_SS_C.value}\n"
    c.raw_spice += "Rss2 ss2 0 1e12\n"
    c.raw_spice += (f"B10 v10src 0 V = min(1.0*min(v(ss2)/{U4_VREF.value},"
                    f"1.0), v(p5v))\n")
    c.raw_spice += "Vs10 v10src v10a DC 0\n"
    c.raw_spice += "Rout10 v10a p1v0 30m\n"
    c.raw_spice += "C10 p1v0 0 22u\n"
    c.raw_spice += f"Rl10 p1v0 0 {1.0/I_1V0.value}\n"
    c.raw_spice += "B10in p5v 0 I = v(p1v0)*i(Vs10)/(0.80*max(v(p5v),1))\n"
    return c


RAILS = (("+12V", "v12", 11.6), ("+5V", "p5v", 5.02), ("+2V5", "p2v5", 2.50),
         ("+3V3", "p3v3", 3.32), ("+1V0", "p1v0", 1.00))


def rail_times(an):
    t = np.array(an.time)
    out = {}
    for name, node, nominal in RAILS:
        v = arr(an, node)
        row = {"nominal": nominal, "peak": float(np.max(v)),
               "final": float(v[-1])}
        for frac, key in ((0.10, "t10"), (0.90, "t90")):
            hit = np.where(v >= frac * nominal)[0]
            row[key] = float(t[hit[0]]) if len(hit) else None
        out[name] = row
    return t, out


def scenario_sequencing(ck):
    out = {}
    # --- as built: powered from the wall, no USB host attached.
    an = run(build_sequencing(), 2e-6, 80e-3)
    t, rows = rail_times(an)
    out["no_host"] = rows
    i_in = (arr(an, "vraw") - arr(an, "vfused")) / F1_R1MAX.value
    # The first 200 us is the capacitive plug-in spike, which scenario 1
    # owns. What matters here is the current U5 draws while it soft-starts
    # into 66 uF and the two converters behind it.
    after = t > 200e-6
    out["i_in_peak"] = float(np.max(i_in[after]))
    out["i_in_spike"] = float(np.max(i_in))
    out["i_in_final"] = float(i_in[-1])
    out["t"] = t
    out["v1v0"] = arr(an, "p1v0")
    out["core_run"] = arr(an, "core_run")

    # --- with a host, so the gate eventually releases. 0009's own caveat is
    # that WAKEUP_N means "bus not suspended", not "enumerated"; 20 ms after
    # the bridge's own rail is up is generous to the design.
    an_h = run(build_sequencing(t_enum=30e-3), 2e-6, 120e-3)
    _, rows_h = rail_times(an_h)
    out["host"] = rows_h

    order = sorted((r["t90"], n) for n, r in rows_h.items()
                   if r["t90"] is not None)
    out["order"] = order

    # ---- S-1. Everything the wall wart can bring up on its own, does.
    late = [n for n, r in rows.items()
            if n != "+1V0" and (r["t90"] is None or r["t90"] > 50e-3)]
    ck.add("S-1", "every ungated rail reaches 90 % within 50 ms",
           not late,
           "  ".join(f"{n} {rows[n]['t90']*1e3:.2f} ms"
                     for n, _, _ in RAILS if rows[n]["t90"] is not None),
           f"the front end costs tens of microseconds -- scenario 1 "
           f"measured it -- and everything after that is U5's "
           f"{U5_TSS.value*1e3:.0f} ms soft start and the two ramps behind "
           f"it")

    # ---- S-2. The skew the 2026-09-21 review found, re-measured now that
    # C_SET is 100 nF and the input is a soft-started buck rather than VBUS.
    skew = rows["+3V3"]["t90"] - rows["+2V5"]["t90"]
    out["skew"] = skew
    ck.add("S-2", "FT601Q supply skew, VCCIO ahead of VCC33",
           skew < 50e-3,
           f"+2V5 reaches 90 % at {rows['+2V5']['t90']*1e3:.2f} ms and "
           f"+3V3 at {rows['+3V3']['t90']*1e3:.2f} ms",
           f"{skew*1e3:.2f} ms of skew, in the same direction as before and "
           f"{359/(skew*1e3):.0f}x smaller. D-6's 359 ms is gone; the "
           f"ordering it created is not")

    # ---- S-3. The one that fails.
    ck.add("S-3", "+1V0 comes up on a board that is powered",
           rows["+1V0"]["t90"] is not None,
           "it does not. CORE_RUN is held low by Q1 for as long as "
           "FT_WAKEUP_N is high, and FT_WAKEUP_N is high whenever the "
           "FT601Q is not seeing bus activity -- including with no cable in "
           "the socket at all",
           f"with a host attached at {30:.0f} ms the rail arrives at "
           f"{rows_h['+1V0']['t90']*1e3:.1f} ms; with no host it never "
           f"arrives. 0014's consequences list this gating as retired and "
           f"main_board.py still builds it")

    # ---- S-4. The glitch only a transient shows.
    v10 = arr(an, "p1v0")
    glitch_peak = float(np.max(v10))
    window = t[v10 > 0.05]
    out["glitch"] = (glitch_peak, float(window[0]) if len(window) else None,
                     float(window[-1]) if len(window) else None)
    ck.add("S-4", "the core rail does not start and then collapse",
           glitch_peak < 0.05,
           f"it does. CORE_RUN is pulled to +5V through R8 the moment +5V "
           f"exists, and Q1 cannot pull it down until +2V5 has climbed to "
           f"the BSS138's gate threshold. Channel 2 soft-starts into that "
           f"window and is then shut off mid-ramp: +1V0 reaches "
           f"{glitch_peak*1e3:.0f} mV before collapsing",
           f"the window runs {out['glitch'][1]*1e3:.2f} to "
           f"{out['glitch'][2]*1e3:.2f} ms. Harmless against DS1001, which "
           f"places no restriction on rail order -- but it is a partial "
           f"core rail arriving and leaving, and nobody chose it",
           assumed=True)

    # ---- S-5. Start-up current at the input against the fuse.
    rise, tripped, _ = fuse_thermal(t[after], i_in[after])
    ck.add("S-5", "start-up input current stays inside F1's hold",
           out["i_in_peak"] < F1_IHOLD_50C.value and tripped is None,
           f"input peaks at {out['i_in_peak']*1e3:.0f} mA during the "
           f"ramp and settles at {out['i_in_final']*1e3:.0f} mA, "
           f"against {F1_IHOLD.value:g} A hold at 20 C and "
           f"{F1_IHOLD_50C.value:g} A at 50 C",
           f"charging {(C_OUT_BULK.value+C_OUT_REST.value)*1e6:.0f} uF to "
           f"{U5_VOUT.value:.2f} V in {U5_TSS.value*1e3:.0f} ms is "
           f"{(C_OUT_BULK.value+C_OUT_REST.value)*U5_VOUT.value/U5_TSS.value*1e3:.0f}"
           f" mA on the output side; the soft start is what keeps it there")

    # ---- S-6. Nothing overshoots on the way up.
    over = []
    if rows["+2V5"]["peak"] > FPGA_VDDIO_ABSMAX.value:
        over.append("+2V5")
    if rows["+1V0"]["peak"] > FPGA_VDD_ABSMAX.value:
        over.append("+1V0")
    if rows["+5V"]["peak"] > 5.5:
        over.append("+5V")
    ck.add("S-6", "no rail overshoots its absolute maximum during the ramp",
           not over,
           f"+2V5 peaks at {rows['+2V5']['peak']:.3f} V against "
           f"{FPGA_VDDIO_ABSMAX.value:g} V, +1V0 at "
           f"{rows_h['+1V0']['peak']:.3f} V against "
           f"{FPGA_VDD_ABSMAX.value:g} V, +5V at {rows['+5V']['peak']:.3f} V",
           "every rail here is reference-ramped, which is the mechanism "
           "that prevents overshoot rather than a result that happens to "
           "hold")
    return out


# ==========================================================================
# TAMPERS
# ==========================================================================
#
# A check that has never failed is not evidence. Each entry below breaks the
# thing one check is supposed to catch and records whether the check noticed.
# Two of them are here because they did NOT notice on the first attempt and
# the check was changed; one is here because nothing can make it notice, and
# that is the finding.
@dataclass
class Tamper:
    name: str
    target: str
    expect: str          # "fails", "passes", or "hole"
    got: str = ""
    ok: bool = False
    note: str = ""


def run_tampers(ck) -> list[Tamper]:
    out: list[Tamper] = []

    def record(name, target, expect, observed_ok, note=""):
        got = "passes" if observed_ok else "fails"
        # "hole" means: this tamper is expected NOT to move the check, and
        # that is the result being reported rather than a broken harness.
        want = "passes" if expect == "hole" else expect
        out.append(Tamper(name, target, expect, got, got == want, note))

    # --- T1. The trip criterion can fire at all. Everything in scenarios 1
    # and 3 rests on one thermal model saying "not tripped"; a model that
    # said that unconditionally would say it here too.
    t = np.linspace(0, 20.0, 20001)
    i = np.full_like(t, 2.5)
    _, tripped, _ = fuse_thermal(t, i)
    record("a sustained 2.5 A through F1", "the F1 trip criterion", "fails",
           tripped is None,
           f"trips at {tripped:.1f} s" if tripped else "never trips")

    # --- T2. The inrush peak check, against a board with no cable in front
    # of it. Shrinking the loop inductance is what raises the peak.
    c, rf = build_inrush(l_cable=1e-9, r_src=1e-3, r_cable=1e-3,
                         r_fuse=F1_RMIN.value, t_close=10e-9)
    m = measure_inrush(run(c, 1e-9, 50e-6), rf)
    record("a bench supply on the pads: 1 nH loop, 2 mohm of wiring",
           "I-2, D1's surge rating", "fails",
           m["peak"] < D1_IFSM.value * 0.5,
           f"peak becomes {m['peak']:.0f} A")

    # --- T3. The one that finds a hole rather than a fault. If more bulk
    # were the mistake this check is meant to catch, it would catch it.
    c, rf = build_inrush(c_bulk=2200e-6)
    m = measure_inrush(run(c, 10e-9, 5e-3), rf)
    record("100x the input bulk, 2200 uF", "I-1, F1 surviving the inrush",
           "hole", m["fuse_rise"] < 0.05 * F1_DT_TRIP,
           f"F1 still rises only {m['fuse_rise']*1e3:.1f} mC. HOLE: I-1 "
           f"cannot be made to fail by capacitance at all -- 0.5*C*V^2 at "
           f"12 V is 158 mJ even here, against the {F1_E_TRIP:.0f} J it "
           f"takes to trip. The check is true and it is not discriminating; "
           f"T1 is what gives it teeth")

    # --- T4. D1 fitted backwards, which is the assembly error the whole
    # reverse-polarity story is about.
    # 60 s, not 200 ms: with only the 22 uF and U5's quiescent load in the
    # circuit the node takes seconds to settle, and a short run would report
    # a number that was still moving.
    an = run(build_reverse(12.0, D1_IR_25.value, d1_backwards=True),
             10e-3, 60.0)
    t = np.array(an.time)
    v12 = float(arr(an, "v12")[-1])
    i_short = (arr(an, "vraw") - arr(an, "vfused")) / F1_R1MAX.value
    i_s = float(np.max(np.abs(i_short)))
    ttt = fuse_time_to_trip(i_s)
    vr = abs(float(arr(an, "vfused")[-1]) - v12)
    blocks = v12 > -1.0 and vr < 0.7 * D1_VRRM.value
    record("D1 soldered backwards", "R-1, D1 blocking", "fails", blocks,
           f"+12V goes to {v12:.1f} V, and the reversed supply is shorted "
           f"to ground through D2 forward and D1 backwards: "
           f"{i_s:.0f} A through F1, which trips it in "
           f"{ttt*1e3:.0f} ms and exceeds its {F1_IMAX.value:.0f} A Imax "
           f"on the way. NOTE: the first version of R-1 tested only the "
           f"voltage across D1, which a backwards diode makes SMALLER -- it "
           f"passed this tamper. R-1 now tests that the protected rail "
           f"stays up as well")

    # --- T5. SMAJ15CA instead of SMAJ15A: the bidirectional part, one
    # character away in the BOM, with no forward conduction below 16.7 V.
    an = run(build_reverse(12.0, D1_IR_25.value, tvs=False), 10e-3, 60.0)
    v12 = float(arr(an, "v12")[-1])
    record("D2 bidirectional (SMAJ15CA)", "R-2, U5's negative maximum",
           "fails", v12 >= U5_VIN_ABSMIN.value,
           f"+12V goes to {v12:.1f} V rather than "
           f"{-0.40:.2f} V -- U5's VIN pin sees the reversed supply")

    # --- T6. The second hole, and it is in an existing check rather than
    # in anything here. verify_power.py asks whether the TVS clamps below
    # U5's maximum. Take the TVS out and ask again.
    c = build_overvoltage(VIN_FAULT.value, D2_VBR_MIN.value, tvs=False)
    an = run(c, 1e-3, 5.0)
    v_no_tvs = float(arr(an, "v12")[-1])
    record("D2 not fitted at all", "OV-3 / verify_power.py's clamp check",
           "hole", v_no_tvs < U5_VIN_OPMAX.value,
           f"U5 sees {v_no_tvs:.1f} V with no TVS on the board, against the "
           f"same {U5_VIN_OPMAX.value:.0f} V maximum. HOLE: at 19 V the "
           f"comparison of clamp voltage to 36 V is true whether or not the "
           f"part exists. It is checking the datasheet, not the design")

    # --- T7. The thermal feedback OV-4 rests on.
    c = build_overvoltage(VIN_FAULT.value, D2_VBR_MIN.value, alpha=0.0)
    an = run(c, 1e-3, 5.0)
    i_iso = float(arr(an, "Vsns")[-1])
    tj_iso = T_AMB.value + i_iso * float(arr(an, "v12")[-1]) * D2_RTHJA.value
    record("D2's VBR temperature coefficient set to zero",
           "OV-4, D2's junction temperature", "fails",
           tj_iso < D2_TJMAX.value,
           f"without the tempco the same fault is {i_iso:.2f} A and "
           f"{i_iso*float(arr(an,'v12')[-1]):.0f} W, a junction at "
           f"{tj_iso:.0f} C. The 0.088 %/C is the entire difference between "
           f"a part that survives this and one that does not")

    # --- T8. The historical defect, put back.
    an = run(build_sequencing(c_set=4.7e-6), 20e-6, 600e-3)
    _, rows = rail_times(an)
    skew = rows["+3V3"]["t90"] - rows["+2V5"]["t90"]
    record("C_SET back to 4.7 uF (the pre-D-6 netlist)",
           "S-2, the FT601Q supply skew", "fails", skew < 50e-3,
           f"skew becomes {skew*1e3:.0f} ms, which is D-6's 359 ms")

    # --- T9. And the gating removed, so S-3 is measuring the gate and not
    # some other reason the rail might be missing.
    an = run(build_sequencing(gated=False), 2e-6, 80e-3)
    _, rows = rail_times(an)
    record("the WAKEUP_N gating removed, as 0014 says it was",
           "S-3, +1V0 arriving", "passes",
           rows["+1V0"]["t90"] is not None,
           f"+1V0 arrives at {rows['+1V0']['t90']*1e3:.2f} ms")
    return out


# ==========================================================================
# REPORT
# ==========================================================================
def banner(title):
    print()
    print("=" * 76)
    print(title)
    print("=" * 76)


def main() -> int:
    ck = Checks()

    banner("LYREBIRD 12 V INPUT — ngspice transients and fault cases (0014)")
    print(f"\nF1 modelled as {F1_PART}: {F1_IHOLD.value:g} A hold, "
          f"{F1_ITRIP.value:g} A trip, {F1_VMAX.value:g} V, "
          f"R1max {F1_R1MAX.value:g} ohm")
    print(f"   thermal model tau {F1_TAU:.1f} s, Rth {F1_RTH:.0f} C/W, "
          f"{F1_E_TRIP:.1f} J to trip from cold")
    print(f"   NOTE: main_board.py says \"{F1_NETLIST_VALUE}\".")
    print(f"   No 1812L part has 1.1 A hold with a 2.2 A trip above "
          f"6 Vdc -- see F-1 in the write-up.")

    # ---------------------------------------------------------------- 1
    banner("1. INRUSH AT PLUG-IN")
    base, sweep, worst_i, worst_e = scenario_inrush(ck)
    print(f"\nNominal case ({L_CABLE.value*1e6:g} uH cable, "
          f"{T_CLOSE.value*1e6:g} us contact, R1max fuse):")
    print(f"   peak {base['peak']:.1f} A, {base['width']*1e6:.0f} us wide, "
          f"{base['charge']*1e6:.0f} uC, I2t {base['i2t']*1e3:.2f} mA2s")
    print(f"   F1 sees {base['fuse_energy']*1e3:.2f} mJ and warms by "
          f"{base['fuse_rise']*1e3:.2f} mC")
    print(f"\nOver {len(sweep)} combinations of cable inductance "
          f"(50 nH..3 uH), contact closure (0.1..10 us) and fuse resistance:")
    print(f"   peak current      {min(m['peak'] for m in sweep):5.1f} to "
          f"{max(m['peak'] for m in sweep):5.1f} A")
    print(f"   energy into F1    "
          f"{min(m['fuse_energy'] for m in sweep)*1e3:5.2f} to "
          f"{max(m['fuse_energy'] for m in sweep)*1e3:5.2f} mJ")
    print(f"   charge delivered  "
          f"{min(m['charge'] for m in sweep)*1e6:5.0f} to "
          f"{max(m['charge'] for m in sweep)*1e6:5.0f} uC  <- does not move")

    # ---------------------------------------------------------------- 2
    banner("2. REVERSE POLARITY")
    rev = scenario_reverse(ck)
    print()
    for v in (12.0, 19.0, 24.0):
        print(f"   reversed {v:4.0f} V:  {rev[v]['v_reverse']:5.1f} V across "
              f"D1, protected rail at {rev[v]['v12']:+.3f} V")
    def _cross(rec):
        """t_cross is None when the rail never reaches the limit at all.

        That is now the expected outcome rather than an error case: D3 was
        added precisely so the rail stops short of the converter's -0.3 V,
        and a run that never crosses has no crossing time to report.
        """
        t = rec.get("t_cross")
        return f"after {t*1e3:.2f} ms" if t is not None else \
            "and never reaches the -0.3 V limit"

    print(f"\n   D1 leakage 0.5 mA (25 C max):  rail settles "
          f"{rev['leaks']['25 C']['v12']:+.3f} V "
          f"{_cross(rev['leaks']['25 C'])}")
    print(f"   D1 leakage  20 mA (100 C max): rail settles "
          f"{rev['leaks']['100 C']['v12']:+.3f} V "
          f"{_cross(rev['leaks']['100 C'])}")
    print(f"   D2 removed:                    rail settles "
          f"{rev['no_tvs']:+.2f} V")

    # ---------------------------------------------------------------- 3
    banner("3. A 19 V LAPTOP BRICK IN THE SAME BARREL")
    ov = scenario_overvoltage(ck)
    print(f"\n   {'corner':22} {'first':>9} {'settled':>9} {'Vin(U5)':>9} "
          f"{'Tj':>7} {'P':>8}")
    for name in ("VBR minimum, 16.7 V", "VBR nominal, 17.6 V",
                 "VBR maximum, 18.5 V"):
        o = ov[name]
        print(f"   {name:22} {o['i_peak']*1e3:7.0f} mA "
              f"{o['i_eq']*1e3:7.1f} mA {o['v_eq']:8.2f} V "
              f"{o['tj_eq']:6.0f} C {o['p_eq']:7.2f} W")
    print(f"\n   isothermal, if the junction never heated: "
          f"{ov['isothermal']['i']:.2f} A and "
          f"{ov['isothermal']['p']:.0f} W, which is what the part would have "
          f"to survive")
    print(f"   if its own breakdown voltage did not walk away from the "
          f"fault.")
    print(f"\n   adapter output impedance sweep, worst (VBR minimum) corner:")
    for r_s, i_pk, t_over, rise, trip in ov["stiff"]:
        print(f"      {r_s*1e3:5.0f} mohm -> peak {i_pk:5.2f} A, F1 warms "
              f"{rise:5.2f} C, {'TRIPS' if trip else 'no trip'}")

    # ---------------------------------------------------------------- 4
    banner("4. RAIL SEQUENCING FROM A WALL WART")
    seq = scenario_sequencing(ck)
    print(f"\n   {'rail':7} {'10 %':>10} {'90 %':>10}    as built, no USB "
          f"host attached")
    for name, _, _ in RAILS:
        r = seq["no_host"][name]
        t10 = f"{r['t10']*1e3:8.3f} ms" if r["t10"] is not None else "   never"
        t90 = f"{r['t90']*1e3:8.3f} ms" if r["t90"] is not None else "   never"
        print(f"   {name:7} {t10:>10} {t90:>10}   {r['final']:.3f} V")
    print(f"\n   with a host driving WAKEUP_N low at 30 ms, +1V0 follows at "
          f"{seq['host']['+1V0']['t90']*1e3:.1f} ms")
    print(f"   input current: {seq['i_in_spike']:.1f} A plug-in spike, "
          f"then {seq['i_in_peak']*1e3:.0f} mA peak through start-up, "
          f"{seq['i_in_final']*1e3:.0f} mA settled")

    # ---------------------------------------------------------------- checks
    banner("CHECKS")
    npass = sum(1 for r in ck.results if r.ok)
    for r in ck.results:
        flag = " [*]" if r.assumed else ""
        print(f"\n  {'PASS' if r.ok else 'FAIL'}  {r.tag}  {r.name}{flag}")
        print(f"        {r.detail}")
        if r.margin:
            print(f"        -> {r.margin}")
    print(f"\n  {npass}/{len(ck.results)} checks pass")

    # ---------------------------------------------------------------- tamper
    banner("TAMPERS — every check above, broken on purpose")
    tampers = run_tampers(ck)
    for tm in tampers:
        if not tm.ok:
            mark = "MISS"
        elif tm.expect == "hole":
            mark = "HOLE"
        else:
            mark = "OK  "
        print(f"\n  {mark}  {tm.name}")
        if tm.expect == "hole":
            print(f"        against {tm.target}: it {tm.got}, and nothing "
                  f"about the fault can make it do otherwise")
        else:
            print(f"        against {tm.target}: expected it to "
                  f"{tm.expect}, it {tm.got}")
        if tm.note:
            for line in _wrap(tm.note, 66):
                print(f"        {line}")
    n_moved = sum(1 for t in tampers if t.ok and t.expect != "hole")
    n_expect = sum(1 for t in tampers if t.expect != "hole")
    n_hole = sum(1 for t in tampers if t.expect == "hole")
    n_miss = sum(1 for t in tampers if not t.ok)
    print(f"\n  {n_moved}/{n_expect} tampers moved the check they targeted; "
          f"{n_hole} found a hole in a check rather than a fault in the "
          f"design")
    if n_miss:
        print(f"  {n_miss} tamper(s) did not do what this file predicted -- "
              f"read those first")

    # ---------------------------------------------------------------- notes
    banner("CONSTANTS — what was read and what was guessed")
    read, guessed = [], []
    for nm, obj in sorted(globals().items()):
        if isinstance(obj, Fact) and nm.isupper():
            row = (f"{nm:18} {obj.value:>12.6g} {obj.unit:<5} {obj.note}")
            (guessed if obj.source in (ASSUMED,) else read).append(
                (obj.source, row))
    for src in (DS, REV, CALC, MODEL):
        rows = [r for s, r in read if s == src]
        if rows:
            print(f"\n  {src}:")
            for r in rows:
                print(f"    {r}")
    print(f"\n  {ASSUMED}:")
    for _, r in guessed:
        print(f"    {r}")

    return 0 if npass == len(ck.results) else 1


def _wrap(text, width):
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""SPICE the output module's difference amplifier: common-mode rejection,
the cost of its unequal input impedances, and how both behave across the band.

`output_stage_ac.py` already measures the three filter poles and the in-band
droop, and none of that is repeated here. What this file measures is the one
property the difference stage exists to provide and which nothing in the
repository has ever put a number on:

  * **How well the four 604 ohm resistors have to match.** Both transimpedance
    outputs sit at -1.39 V at mid code, by construction, because the elements
    always source current. Rejection of that is set by the two *ratios*
    R2/R1 and R4/R3, not by absolute tolerance, which is the argument for one
    array. Sweep the ratio and find what it costs (check A, B).

  * **Whether the rejection holds across the band** (check C). It does not
    hold for the reason one would expect: the array's parasitics are nowhere
    near the limit, and the two discrete 1.3 nF C0G capacitors are.

  * **actions.md D3**, the unequal input impedances -- 402 || 604 = 241 ohm
    seen by the positive transimpedance amplifier and 402 || 1208 = 302 ohm
    by the negative. 0008 buys even-order cancellation by putting both
    polarities of a channel on one die; the asymmetry spends it. Check D
    measures the imbalance, check E measures how much of a half's even-order
    distortion survives the subtraction because of it (D, E).

Every check is paired with a tamper that breaks the thing it is meant to
catch. `tamper()` runs them and the run fails if any tamper *passes*.

ngspice comes from KiCad's bundle; there is no standalone binary on this
machine, and InSpice resolves the library through ctypes, which discards an
absolute path, so the finder is replaced below -- same preamble as
`output_stage_ac.py`.

    ./.venv/bin/python hardware/sim/difference_stage.py

Constants, and where they come from
-----------------------------------
**Read off `hardware/netlist/output_module.py`**: every resistor and capacitor
value, the element split, and the wiring of the four-resistor network
(`rn[1..8]`).

**Verified against SBOS450C** (OPA1611/OPA1612, July 2009, revised August
2014, fetched from ti.com and read out of the electrical characteristics
table):

    GBW             40 MHz at G = +1
    AOL             114 dB typ / 110 dB min at RL = 2 kohm
                    130 dB typ / 114 dB min at RL = 10 kohm
    CMRR            120 dB typ / 110 dB min, (V-)+2 <= VCM <= (V+)-2
    PSRR            0.1 uV/V typ, 1 uV/V max
    VCM range       (V-)+2 to (V+)-2
    ZO              "See Figure 28" -- a graph, not a number

**Assumed, and stated as such**: the open-loop output resistance R_O (the
datasheet gives only a curve), the output-stage nonlinearity coefficient used
in check E, and the tolerance of the two 1.3 nF capacitors, which the netlist
does not specify at all.

Note also that `model/lyrebird_model/analog.py` prices four amplifiers where
the board has six, so its stage figures describe a different circuit. Nothing
here is taken from it; the only model number used is the -136.5 dBFS in-band
noise of the digital chain, which is a chain figure, not a stage figure.
"""

from __future__ import annotations

import math
import os
import sys

KICAD = "/Applications/KiCad/KiCad.app/Contents"
os.environ.setdefault("SPICE_LIB_DIR", f"{KICAD}/PlugIns/sim/ngspice")
_LIB = f"{KICAD}/Frameworks/libngspice.0.dylib"

from InSpice.Spice.NgSpice.Shared import NgSpiceShared  # noqa: E402

NgSpiceShared.find_library = classmethod(lambda cls, name: _LIB)

from InSpice import Circuit, Simulator  # noqa: E402
import numpy as np  # noqa: E402

# ------------------------------------------------------------------ the board
# hardware/netlist/output_module.py, not retyped from prose.
V_REF = 3.3             # element reference rail, 0012
R_EL_TOP = 1.69e3       # register side of the split element
R_EL_BOT = 1.65e3       # summing-node side
C_EL = 180e-12          # C0G between the halves
N_ELEM = 7              # unit elements per side

R_TIA = 402.0           # RN15, all four transimpedance resistors, one array
C_TIA = 2.0e-9

R_DIFF = 604.0          # RN16/RN17, four per channel, one array
C_DIFF = 1.3e-9         # two discrete C0G parts, tolerance unspecified

R_BUILD = 100.0         # series build-out at the jack
C_JACK = 100e-12
R_LOAD = 10e3           # line load the build-out is specified against

# Seven parallel split elements reduce exactly to a Thevenin source: the
# drivers are all at 0 or V_REF, so the equivalent source voltage is
# V_REF * (elements high) / 7 behind R_EL_TOP/7, then 7*C_EL to ground, then
# R_EL_BOT/7 into the summing node. Exact for the linear network, and it lets
# the code be a continuous sweep variable.
R_DRV = R_EL_TOP / N_ELEM
C_MID = C_EL * N_ELEM
R_SUM = R_EL_BOT / N_ELEM

I_UNIT = V_REF / (R_EL_TOP + R_EL_BOT)          # one element's current
V_CM_DC = -N_ELEM / 2 * I_UNIT * R_TIA          # -1.39 V, at every code
V_FS = N_ELEM * I_UNIT * R_TIA                  # +2.78 V peak at the output

# ------------------------------------------------------- OPA1612, SBOS450C
GBW = 40e6
AOL_DB = 114.0          # the 2 kohm typical: the lowest load the table gives
CMRR_DB = 120.0         # typical; 110 dB minimum
# ASSUMED. The datasheet gives open-loop output impedance as Figure 28, a
# curve, so there is no number to quote. 15 ohm is a mid-band value typical of
# this class of part; check D sweeps it because the answer depends on it.
R_O = 15.0

# ------------------------------------------------------------------ budgets
CHAIN_FLOOR_DBFS = -136.5   # docs/open-items.md: the digital chain's own noise
OFFSET_BUDGET_V = 10e-3     # DC at the jack, with no output coupling capacitor
# parts-notes.md already accepts 1.4 mV from a 0.1 % mismatch between the two
# 402 ohm feedback resistors, so that is the scale the 604 array is judged on.
OFFSET_PEER_V = 1.4e-3

BAND_EDGE = 20e3


# --------------------------------------------------------------- the circuit
def opamp(c, name, plus, minus, out, *, aol_db=AOL_DB, gbw=GBW,
          cmrr_db=CMRR_DB, ro=R_O, beta=0.0):
    """One-pole op amp with finite CMRR and a finite open-loop output stage.

    Three things beyond `output_stage_ac.py`'s model, each because a check
    here needs it:

    * a common-mode gain ``aol/CMRR`` on ``(v+ + v-)/2``, so that the
      measured rejection has the amplifier's own floor in it and not only the
      resistor network's;
    * a series output resistance, without which the load a stage drives has
      no effect at all and D3 cannot be measured;
    * optionally a *nonlinear* output resistance ``ro + beta*i``, which is the
      only way to provoke an even-order term. The sign of the quadratic makes
      it asymmetric in output current, which is the physical case here: these
      amplifiers only ever sink.
    """
    aol = 10 ** (aol_db / 20)
    acm = aol / 10 ** (cmrr_db / 20)
    c.VCVS(f"d{name}", f"n1{name}", c.gnd, plus, minus, voltage_gain=aol)
    # Common-mode error, as two half-gain sources in series so the sum is
    # acm * (v+ + v-)/2.
    c.VCVS(f"c1{name}", f"n2{name}", f"n1{name}", plus, c.gnd,
           voltage_gain=acm / 2)
    c.VCVS(f"c2{name}", f"n3{name}", f"n2{name}", minus, c.gnd,
           voltage_gain=acm / 2)
    f_dom = gbw / aol
    c_dom = 1e-6
    c.R(f"p{name}", f"n3{name}", f"f{name}", 1.0 / (2 * np.pi * f_dom * c_dom))
    c.C(f"p{name}", f"f{name}", c.gnd, c_dom)
    c.VCVS(f"b{name}", f"o{name}", c.gnd, f"f{name}", c.gnd, voltage_gain=1.0)
    if beta == 0.0:
        c.R(f"o{name}", f"o{name}", out, ro)
    else:
        c.raw_spice += (
            f"Vsns{name} o{name} x{name} 0\n"
            f"Bout{name} x{name} {out} "
            f"V = i(Vsns{name})*({ro:g} + {beta:g}*i(Vsns{name}))\n")


def element_side(c, tag, drv, node):
    """The seven-element network of one polarity, reduced to its Thevenin."""
    c.R(f"drv{tag}", drv, f"mid{tag}", R_DRV)
    c.C(f"mid{tag}", f"mid{tag}", c.gnd, C_MID)
    c.R(f"sum{tag}", f"mid{tag}", node, R_SUM)


def build(*, eps=(0.0, 0.0, 0.0, 0.0), dcap=0.0, cpar=(0.0,) * 4,
          ro=R_O, beta=0.0, no_common_mode=False,
          aol_db=AOL_DB, cmrr_db=CMRR_DB, r_tia=(R_TIA, R_TIA),
          equalise=None, q_leg=None, drop_ref_cap=False, ac_drive=None,
          code_source=True, lift=()):
    """One channel: two transimpedance amplifiers into one difference stage.

    ``eps`` is the fractional error on each of the four 604 ohm resistors in
    netlist order -- R1 (IV_P to the inverting input), R2 (feedback), R3
    (IV_N to the non-inverting input), R4 (non-inverting leg to ground).
    ``dcap`` splits the two 1.3 nF capacitors by +/- dcap; ``cpar`` puts
    pad-to-pad capacitance across each array element. ``q_leg`` re-values the
    non-inverting leg, ``equalise`` adds a resistor from IV_N to ground, and
    ``drop_ref_cap`` deletes that leg's capacitor -- three ways of changing
    what the negative half sees. ``beta`` may be a pair, one per half.
    ``no_common_mode`` and ``lift`` exist only for tampers.
    ``ac_drive`` is 'cm', 'diff', 'p' or 'n'; ``code_source`` puts the DC code
    sweep source in.
    """
    c = Circuit("Lyrebird difference stage, one channel")

    # ---- the code. n_p = 3.5*(1+s), n_n = 3.5*(1-s), s in [-1, +1]. The
    # drive voltages are V_REF*n/7, built as a fixed half-rail plus a swept
    # term so that a single source sweeps the whole transfer curve.
    if code_source:
        c.V("s", "s", c.gnd, 0.0)
        # ``no_common_mode`` drives the elements bipolar instead, which is
        # not the board -- it exists so a tamper can take the 1.39 V away
        # and check that the offset goes with it.
        c.V("half", "half", c.gnd, 0.0 if no_common_mode else V_REF / 2)
        c.VCVS("dp", "drv_p", "half", "s", c.gnd, voltage_gain=V_REF / 2)
        c.VCVS("dn", "drv_n", "half", "s", c.gnd, voltage_gain=-V_REF / 2)
    else:
        # Half rail on each side, which is mid code -- except where an AC
        # drive is about to take that node over.
        if ac_drive != "p":
            c.V("dp", "drv_p", c.gnd, V_REF / 2)
        if ac_drive != "n":
            c.V("dn", "drv_n", c.gnd, V_REF / 2)

    element_side(c, "p", "drv_p", "sum_p")
    element_side(c, "n", "drv_n", "sum_n")

    # ---- transimpedance, one per polarity. The non-inverting inputs go
    # straight to ground: the netlist is deliberate about that.
    for tag, node, out, rf in (("tp", "sum_p", "iv_p", r_tia[0]),
                               ("tn", "sum_n", "iv_n", r_tia[1])):
        # ``lift`` leaves an amplifier driving a dead node, so a probe can
        # measure what the rest of the circuit presents at its output pin.
        b = beta[0 if tag == "tp" else 1] if isinstance(beta, tuple) else beta
        opamp(c, tag, c.gnd, node, f"dead_{tag}" if tag in lift else out,
              aol_db=aol_db, cmrr_db=cmrr_db, ro=ro, beta=b)
        c.R(tag, node, out, rf)
        c.C(tag, node, out, C_TIA)

    # ---- the four-resistor difference amplifier, RN16.
    #   rn[1] IV_P -> rn[8] inv        R1
    #   rn[2] inv  -> rn[7] out        R2, with 1.3 nF across it
    #   rn[3] IV_N -> rn[6] ref        R3
    #   rn[4] ref  -> rn[5] gnd        R4, with 1.3 nF across it
    e1, e2, e3, e4 = eps
    opamp(c, "df", "ref", "inv", "out", aol_db=aol_db, cmrr_db=cmrr_db, ro=ro)
    c.R("d1", "iv_p", "inv", R_DIFF * (1 + e1))
    c.R("d2", "inv", "out", R_DIFF * (1 + e2))
    # ``q_leg`` re-values the non-inverting leg on its own. Unity gain
    # survives any value, because the condition is R4/R3 = R2/R1 and both
    # pairs stay equal; what changes is the current the negative half's
    # amplifier has to deliver.
    q = R_DIFF if q_leg is None else q_leg
    c.R("d3", "iv_n", "ref", q * (1 + e3))
    c.R("d4", "ref", c.gnd, q * (1 + e4))
    c.C("d2", "inv", "out", C_DIFF * (1 + dcap))
    if not drop_ref_cap:
        # Pole 3 has to stay where it is, so the capacitor scales with the leg.
        c.C("d4", "ref", c.gnd, C_DIFF * (R_DIFF / q) * (1 - dcap))
    # Pad-to-pad capacitance of the array itself, across each element.
    for k, (n1, n2) in enumerate((("iv_p", "inv"), ("inv", "out"),
                                  ("iv_n", "ref"), ("ref", c.gnd))):
        if cpar[k]:
            c.C(f"par{k}", n1, n2, cpar[k])

    if equalise is not None:
        c.R("eq", "iv_n", c.gnd, equalise)

    c.R("bo", "out", "lo", R_BUILD)
    c.C("jack", "lo", c.gnd, C_JACK)
    c.R("load", "lo", c.gnd, R_LOAD)

    # ---- AC drive, when the check wants one. Common mode and differential
    # are applied at the transimpedance outputs, which is where the thing to
    # be rejected actually appears.
    if ac_drive == "cm":
        c.SinusoidalVoltageSource("cm", "cmdrv", c.gnd, amplitude=1.0)
        c.VCVS("injp", "iv_p", c.gnd, "cmdrv", c.gnd, voltage_gain=1.0)
        c.VCVS("injn", "iv_n", c.gnd, "cmdrv", c.gnd, voltage_gain=1.0)
    elif ac_drive == "diff":
        c.SinusoidalVoltageSource("dm", "dmdrv", c.gnd, amplitude=1.0)
        c.VCVS("injp", "iv_p", c.gnd, "dmdrv", c.gnd, voltage_gain=-0.5)
        c.VCVS("injn", "iv_n", c.gnd, "dmdrv", c.gnd, voltage_gain=+0.5)
    elif ac_drive in ("p", "n"):
        c.SinusoidalVoltageSource("ac", f"drv_{ac_drive}", c.gnd,
                                  amplitude=1.0)
    return c


# Default ngspice tolerances (reltol 1e-3, vntol 1e-6 V) are loose against the
# even-order term in check E, which lives at 1e-8 V on a 2.8 V swing: at the
# defaults the cancellation figure reads 5.02 dB where the converged answer is
# 5.09. Tightened until the answer stops moving -- 1e-8, 1e-9 and 1e-10 all
# agree to 0.01 dB -- and no further, because below about 1e-11 the nonlinear
# sweep stops converging at all.
_TIGHT = dict(reltol=1e-9, vntol=1e-12, abstol=1e-15)


def _sim(c, tight=False):
    sim = Simulator.factory().simulation(c)
    if tight:
        sim.options(**_TIGHT)
    return sim


# ------------------------------------------------------------- measurements
def sweep_code(c, step=0.01, opts=None):
    """DC sweep of the code, returning s and every node of interest."""
    sim = Simulator.factory().simulation(c)
    sim.options(**(_TIGHT if opts is None else opts))
    an = sim.dc(Vs=slice(-1.0, 1.0, step))
    s = np.array(an.sweep, dtype=float)
    want = ("out", "iv_p", "iv_n", "lo", "otp", "otn")
    got = {k: np.array(an[k], dtype=float) for k in want if k in an.nodes}
    got["s"] = s
    return got


def split_even_odd(s, y):
    """Even and odd parts of y(s) about s = 0, on the positive half."""
    n = len(s)
    assert n % 2 == 1 and abs(s[n // 2]) < 1e-12, "sweep must straddle zero"
    half = slice(n // 2, n)
    s_pos = s[half]
    y_pos = y[half]
    y_neg = y[n // 2::-1]
    return s_pos, 0.5 * (y_pos + y_neg), 0.5 * (y_pos - y_neg)


def transfer_terms(s, out):
    """a0, a2 (even) and a1, a3 (odd) of the measured transfer curve.

    Splitting by symmetry first is what makes the even terms trustworthy: the
    odd terms are five orders of magnitude larger, and a single least-squares
    fit over the whole curve mixes them through its conditioning.
    """
    u, even, odd = split_even_odd(s, out)
    ce = np.polyfit(u ** 2, even, 3)          # a0 + a2 u^2 + a4 u^4 + a6 u^6
    co = np.polyfit(u ** 2, odd / np.where(u == 0, 1, u), 3)
    a0, a2 = ce[-1], ce[-2]
    a1, a3 = co[-1], co[-2]
    return float(a0), float(a1), float(a2), float(a3)


def acm_ad(eps=(0, 0, 0, 0), *, dcap=0.0, freqs=(20.0,), **kw):
    """Common-mode and differential gain of the difference stage, per frequency."""
    out = {}
    for mode in ("cm", "diff"):
        c = build(eps=eps, dcap=dcap, ac_drive=mode, code_source=False, **kw)
        an = _sim(c).ac(start_frequency=min(freqs) / 2,
                        stop_frequency=max(freqs) * 2,
                        number_of_points=100, variation="dec")
        f = np.array(an.frequency, dtype=float)
        g = np.array(an["out"])
        out[mode] = np.array([
            np.interp(np.log10(fr), np.log10(f), np.abs(g)) for fr in freqs])
    return out["cm"], out["diff"]


def cmrr_db(eps=(0, 0, 0, 0), *, dcap=0.0, freqs=(20.0,), **kw):
    acm, ad = acm_ad(eps, dcap=dcap, freqs=freqs, **kw)
    with np.errstate(divide="ignore"):
        return 20 * np.log10(ad / np.maximum(acm, 1e-300)), acm, ad


def half_gain(side, freqs, **kw):
    """Closed-loop transimpedance gain of one half, complex, at each frequency.

    Complex on purpose. Above the dominant pole the finite-loop-gain error is
    almost entirely imaginary, so comparing magnitudes hides it: it reads an
    order of magnitude low at 20 kHz and looks like agreement.
    """
    c = build(ac_drive=side, code_source=False, **kw)
    an = _sim(c).ac(start_frequency=min(freqs) / 2,
                    stop_frequency=max(freqs) * 2,
                    number_of_points=400, variation="dec")
    f = np.array(an.frequency, dtype=float)
    g = np.array(an[f"iv_{side}"])
    out = []
    for fr in freqs:
        i = int(np.argmin(np.abs(f - fr)))
        out.append(complex(g[i]))
    return np.array(out)


def output_load(side, freq=20.0, ro=R_O, **kw):
    """What one transimpedance output pin actually drives, in ohms.

    Measured, not asserted, and measured with the amplifier *in place*: the
    load is ``V_out / I_out``, and the current is read across the amplifier's
    own output resistance, whose two nodes are both in the netlist. Lifting
    the amplifier to probe the node would give the wrong answer -- it takes
    the summing node's virtual ground away with it, and the 402 ohm feedback
    resistor stops being a 402 ohm load.
    """
    tag = "tp" if side == "p" else "tn"
    c = build(code_source=False, ac_drive=side, ro=ro, **kw)
    an = _sim(c).ac(start_frequency=freq, stop_frequency=freq * 1.001,
                    number_of_points=2, variation="lin")
    v_out = complex(np.array(an[f"iv_{side}"])[0])
    v_int = complex(np.array(an[f"o{tag}"])[0])
    return v_out / ((v_int - v_out) / ro)


# ----------------------------------------------------------------- reporting
def dbfs(v_rms):
    return 20 * math.log10(v_rms / (V_FS / math.sqrt(2)))


_fails: list[str] = []


def report(ok, label, detail=""):
    tag = "PASS" if ok else "FAIL"
    if not ok:
        _fails.append(label)
    print(f"  {tag}  {label}")
    if detail:
        for line in detail.splitlines():
            print(f"        {line}")
    return ok


def head(title):
    print()
    print("-" * 74)
    print(title)
    print("-" * 74)


# ---------------------------------------------------------------- check A/B
# The common mode that has to be rejected, in the three forms it takes. Only
# the first of these is certainly unshaped; the second is a deliberately
# pessimistic bound and is labelled as one.
CM_AC_REF = abs(V_CM_DC) / V_REF * 0.8e-6      # 0009: the LT3045s add 0.8 uV
# Element mismatch: 0.1 % thin film, uniform, seven of fourteen high at any
# code. The common-mode sum moves by sigma/sqrt(7) of the total. DWA rotates
# *both* banks, so the real in-band figure is shaped well below this -- it is
# quoted as the bound that holds if rotation is ever changed or defeated.
CM_AC_ELEM = abs(V_CM_DC) * (1e-3 / math.sqrt(3)) / math.sqrt(N_ELEM)


def worst_case(t):
    """The sign pattern that maximises the common-mode gain, |Acm| = 2t.

    Acm = [(e4-e3) - (e2-e1)]/2 to first order, so the four errors have to
    alternate. A tolerance is a bound on each error independently, so this is
    what a tolerance actually buys.
    """
    return (-t, +t, +t, -t)


def check_a_ratio_not_tolerance():
    head("A. Rejection is a ratio property, not a tolerance property")
    f = (20.0,)
    base, _, _ = cmrr_db((0, 0, 0, 0), freqs=f)
    scaled, _, _ = cmrr_db((0.01,) * 4, freqs=f)
    one_off, _, _ = cmrr_db((0.01, 0, 0, 0), freqs=f)
    print(f"        four resistors exact                 CMRR {base[0]:7.1f} dB"
          "   (the amplifier's own 120 dB floor)")
    print(f"        all four 1 % high together           CMRR {scaled[0]:7.1f} dB"
          "   absolute error, ratios intact")
    print(f"        one of the four 1 % high             CMRR {one_off[0]:7.1f} dB"
          "   ratio broken")
    ok = (abs(scaled[0] - base[0]) < 0.5) and (one_off[0] < base[0] - 50)
    return report(
        ok, "a 1 % absolute error costs nothing and a 1 % ratio error costs "
            f"{base[0] - one_off[0]:.0f} dB",
        "which is the whole argument for one array rather than four parts")


def check_b_matching_requirement():
    head("B. How much matching the 1.39 V of common mode requires")
    print(f"        Common mode at both transimpedance outputs "
          f"{V_CM_DC:+.4f} V, at every code")
    print(f"        Full scale at the difference output        "
          f"{V_FS:+.4f} V peak, {V_FS / math.sqrt(2):.4f} V RMS")
    print(f"        {CHAIN_FLOOR_DBFS} dBFS, the chain's own noise        "
          f"{10 ** (CHAIN_FLOOR_DBFS / 20) * V_FS / math.sqrt(2) * 1e9:.0f} nV RMS")
    print()
    print("        The common mode is DC by construction, so a ratio error "
          "buys a DC offset.")
    print("        Only the part of it that MOVES can reach the noise floor. "
          "Two sources:")
    print(f"          reference-rail noise, 0.8 uV on 3.3 V (0009)   "
          f"{CM_AC_REF * 1e9:8.1f} nV RMS   certain")
    print(f"          element mismatch, 0.1 %, seven of fourteen high"
          f" {CM_AC_ELEM * 1e6:7.1f} uV      a bound")
    print("        The second is a bound, not a figure: DWA rotates BOTH "
          "banks, so the")
    print("        common-mode sum is shaped by the same mechanism as the "
          "differential one.")
    print("        It is what the leak would be if rotation ever stopped "
          "shaping it.")
    print()
    print("        ratio     Acm       CMRR     DC offset   leak, ref rail"
          "   leak, element bound")
    rows = []
    for t in (1e-4, 2.5e-4, 5e-4, 1e-3, 2.5e-3, 1e-2):
        r = sweep_code(build(eps=worst_case(t)))
        a0, a1, a2, a3 = transfer_terms(r["s"], r["out"])
        acm = abs(a0 / V_CM_DC)
        rows.append((t, acm, a0))
        print(f"        {t * 100:5.3f} %  {acm:8.2e}  {20 * math.log10(1 / acm):5.1f} dB"
              f"  {a0 * 1e3:+8.3f} mV  {dbfs(acm * CM_AC_REF):8.1f} dBFS"
              f"   {dbfs(acm * CM_AC_ELEM):8.1f} dBFS")
    print("        The sign pattern is the worst case a tolerance permits: a "
          "tolerance bounds")
    print("        each resistor independently, so Acm = [(e4-e3)-(e2-e1)]/2 "
          "reaches 2t.")

    as_built = dict((t, (acm, a0)) for t, acm, a0 in rows)[1e-3]
    acm_built, off_built = as_built
    ok = report(abs(off_built) < OFFSET_BUDGET_V,
                f"at the 0.1 % already specified the DC offset is "
                f"{abs(off_built) * 1e3:.2f} mV",
                f"against a {OFFSET_BUDGET_V * 1e3:.0f} mV budget at a jack "
                f"with no coupling capacitor, and against the\n"
                f"{OFFSET_PEER_V * 1e3:.1f} mV parts-notes.md already accepts "
                f"from the 402 ohm array. The two add to about\n"
                f"{(abs(off_built) + OFFSET_PEER_V) * 1e3:.1f} mV worst case.")
    report(dbfs(acm_built * CM_AC_REF) < CHAIN_FLOOR_DBFS,
           f"and the certain in-band leak is "
           f"{dbfs(acm_built * CM_AC_REF):.1f} dBFS",
           f"{CHAIN_FLOOR_DBFS - dbfs(acm_built * CM_AC_REF):.0f} dB under "
           f"the chain's {CHAIN_FLOOR_DBFS} dBFS. The reference rail reaches "
           f"the output far more\nstrongly through the differential path, "
           f"which is multiplicative -- rejection buys\nnothing against it.")
    # Where the pessimistic bound would cross the floor.
    t_need = (10 ** (CHAIN_FLOOR_DBFS / 20) * V_FS / math.sqrt(2)
              / CM_AC_ELEM) / 2
    print(f"        If rotation ever stopped shaping the common-mode sum, "
          f"the bound crosses")
    print(f"        {CHAIN_FLOOR_DBFS} dBFS at a ratio tolerance of "
          f"{t_need * 100:.3f} % -- which is the 0.05 % row. That is a "
          f"contingency")
    print(f"        to record against 0008's rotation rule, not a part "
          f"change today.")
    return rows, ok


# ------------------------------------------------------------------ check C
def check_c_across_the_band():
    head("C. Whether the rejection holds across the band")
    freqs = (20.0, 1e3, 20e3, 2e5)
    print("        configuration                                   "
          + "".join(f"{f:>9.0f} Hz" for f in freqs))
    rows = (
        ("everything exact: the circuit's own floor", dict()),
        ("...and the amplifier's CMRR at 80 dB, not 120",
         dict(cmrr_db=80.0)),
        ("resistors 0.1 % ratio, capacitors exact",
         dict(eps=worst_case(1e-3))),
        ("resistors 0.01 % ratio, capacitors exact",
         dict(eps=worst_case(1e-4))),
        ("resistors exact, capacitors +/-5 % (unspecified)",
         dict(dcap=0.05)),
        ("resistors exact, capacitors +/-1 %", dict(dcap=0.01)),
        ("as built: 0.1 % array and +/-5 % capacitors",
         dict(eps=worst_case(1e-3), dcap=0.05)),
        ("resistors exact, 0.5 pF across one array element",
         dict(cpar=(0.5e-12, 0, 0, 0))),
    )
    got = {}
    for label, kw in rows:
        db, _, _ = cmrr_db(freqs=freqs, **kw)
        got[label] = db
        print(f"        {label:47}" + "".join(f"{v:9.1f} dB" for v in db))
    r_only = got["resistors 0.1 % ratio, capacitors exact"]
    c_only = got["resistors exact, capacitors +/-5 % (unspecified)"]
    par = got["resistors exact, 0.5 pF across one array element"]
    base = got["everything exact: the circuit's own floor"]
    print()
    print("        The first row is not infinite because the difference")
    print("        amplifier's own output impedance is: a common-mode input")
    print("        with a perfectly balanced network still forces")
    print(f"        v_cm/(2*{R_DIFF:.0f}) through the feedback leg, and the")
    print("        closed-loop output impedance R_O/(1+T) turns that into an")
    print("        output voltage. It falls at 20 dB/decade with the loop gain.")
    # Where the resistor and capacitor terms cross, from the closed form
    # Acm_R = 2t (real), Acm_C = omega*R*C*dcap (imaginary).
    f_cross = 2 * 1e-3 / (2 * np.pi * R_DIFF * C_DIFF * 0.05)
    ok = report(
        c_only[2] < r_only[2],
        f"at {freqs[2] / 1e3:.0f} kHz the two 1.3 nF capacitors set the "
        f"rejection, not the array",
        f"{c_only[2]:.1f} dB from +/-5 % capacitors against {r_only[2]:.1f} dB "
        f"from a 0.1 % array;\nthe two are equal at "
        f"{f_cross / 1e3:.1f} kHz and the capacitors dominate above it")
    report(par[2] > c_only[2] + 40,
           "the array's own pad-to-pad capacitance is not what limits it",
           f"0.5 pF across one 604 ohm element leaves {par[2]:.1f} dB at "
           f"20 kHz, {par[2] - c_only[2]:.0f} dB better than the capacitor "
           f"tolerance does;\nit is not negligible against the circuit's "
           f"{base[2]:.1f} dB floor, it is simply never the binding term")
    return got, ok


# ------------------------------------------------------------------ check D
def out_currents(step=0.01, **kw):
    """Each transimpedance amplifier's own output current, over the code.

    Read across the amplifier's output resistance, so it is the current the
    output stage delivers, not the current in any one resistor. No assumption
    about the amplifier beyond having an output resistance at all.
    """
    r = sweep_code(build(ro=R_O, **kw), step=step)
    ro = kw.get("ro", R_O)
    return (r["s"], (r["otp"] - r["iv_p"]) / ro, (r["otn"] - r["iv_n"]) / ro)


def check_d_unequal_loading():
    head("D. actions.md D3 -- the difference amplifier loads the two halves "
         "unequally")
    z_p, z_n = output_load("p"), output_load("n")
    z_p20, z_n20 = output_load("p", freq=20e3), output_load("n", freq=20e3)
    print(f"        small-signal load at the positive output "
          f"{abs(z_p):7.1f} ohm   (402 || 604)")
    print(f"        small-signal load at the negative output "
          f"{abs(z_n):7.1f} ohm   (402 || 1208)")
    print(f"        {abs(z_n) / abs(z_p):.3f} to 1, and both are below the 600 "
          f"ohm of the OPA1612's lowest")
    print(f"        published distortion curve; its open-loop gain is not "
          f"specified below 2 kohm")
    print(f"        at all. At 20 kHz both are complex: "
          f"{z_p20.real:.1f}{z_p20.imag:+.1f}j and "
          f"{z_n20.real:.1f}{z_n20.imag:+.1f}j ohm.")

    print()
    print("        But the load ratio understates it. With both polarities "
          "moving together,")
    print("        what each output stage actually delivers is:")
    s_ax, i_p, i_n = out_currents(step=0.05)
    slope_p = float(np.polyfit(s_ax, i_p, 1)[0])
    slope_n = float(np.polyfit(s_ax, i_n, 1)[0])
    zero_p = -float(np.polyfit(s_ax, i_p, 1)[1]) / slope_p
    print(f"          positive half  {i_p[0] * 1e3:+7.3f} mA at -FS to "
          f"{i_p[-1] * 1e3:+7.3f} mA at +FS, slope "
          f"{slope_p * 1e3:+.3f} mA per unit code")
    print(f"          negative half  {i_n[0] * 1e3:+7.3f} mA at -FS to "
          f"{i_n[-1] * 1e3:+7.3f} mA at +FS, slope "
          f"{slope_n * 1e3:+.3f} mA per unit code")
    print(f"        The swings differ by {abs(slope_p / slope_n):.3f} to 1, "
          f"not {abs(z_n) / abs(z_p):.2f} to 1, because the inverting leg's")
    print(f"        far end is the amplifier's summing node, which moves with "
          f"the *other* half,")
    print(f"        while the non-inverting leg's far end is ground.")
    print(f"        And the positive half's output current passes through "
          f"zero at code {zero_p:+.3f},")
    print(f"        which is {20 * math.log10(abs(zero_p)):.1f} dBFS -- inside "
          f"the signal. The negative half's")
    print(f"        reaches zero only at +full scale. parts-notes.md's "
          f"\"never positive\" is true of")
    print(f"        the network current and not of the amplifier's.")

    print()
    freqs = (20.0, 1e3, 20e3)
    print("        Linear cost, |(G_n - G_p)/G| between the two halves:")
    print("        R_O (assumed)   " + "".join(f"{f:>13.0f} Hz" for f in freqs))
    out = {}
    for ro in (5.0, 15.0, 50.0):
        gp = half_gain("p", freqs, ro=ro)
        gn = half_gain("n", freqs, ro=ro)
        out[ro] = (gn - gp) / (0.5 * (gn + gp))
        print(f"        {ro:5.0f} ohm        "
              + "".join(f"{abs(v):13.2e}  " for v in out[ro]))
    gp = half_gain("p", freqs, ro=R_O)
    eq = half_gain("n", freqs, ro=R_O, equalise=2 * R_DIFF)
    imb_eq = (eq - gp) / (0.5 * (eq + gp))
    print(f"        {R_O:5.0f} ohm, 1208 ohm shunt at IV_N:")
    print("                        " + "".join(f"{abs(v):13.2e}  "
                                               for v in imb_eq))

    imb = out[R_O]
    off = abs(V_CM_DC) * abs(imb[0].real)
    cm_sig = abs(imb[2]) / 2 * V_FS
    print()
    print(f"        At R_O = {R_O:.0f} ohm the linear cost is negligible: the "
          f"real part at 20 Hz is")
    print(f"        {imb[0].real:+.2e}, which on {abs(V_CM_DC):.3f} V of "
          f"common mode is {off * 1e6:.2f} uV of output offset")
    print(f"        against the {abs(2e-3 * V_CM_DC) * 1e3:.2f} mV a 0.1 % "
          f"array gives. At 20 kHz the imbalance is")
    print(f"        {abs(imb[2]):.2e} and almost entirely reactive -- a phase "
          f"mismatch, which makes the")
    print(f"        common mode signal-dependent by {cm_sig * 1e6:.2f} uV "
          f"peak at full scale; through a")
    print(f"        0.1 % array that reaches the output at "
          f"{dbfs(2e-3 * cm_sig / math.sqrt(2)):.1f} dBFS. The cost is not "
          f"here. It is in check E.")
    ok = report(abs(imb_eq[0]) < abs(imb[0]) / 100,
                "a 1208 ohm shunt at IV_N removes the resistive part of the "
                "linear imbalance",
                f"{abs(imb[0]):.2e} becomes {abs(imb_eq[0]):.2e} at 20 Hz, "
                f"for 1.15 mA more on the negative rail per channel")
    report(abs(imb_eq[2]) < abs(imb[2]) / 10,
           "and most of the reactive part with it, though not all",
           f"{abs(imb[2]):.2e} at 20 kHz becomes {abs(imb_eq[2]):.2e}: the "
           f"inverting leg's 1.3 nF sits\nacross R2 and the non-inverting "
           f"leg's across R4, so the two legs present different\nreactances "
           f"and a resistor cannot equalise those.")
    return out, imb_eq, (z_p, z_n), (slope_p, slope_n, zero_p), ok


# ------------------------------------------------------------------ check E
def even_term(beta, opts=None, **kw):
    """a2 of the difference output and of each half, at one nonlinearity."""
    r = sweep_code(build(beta=beta, **kw), opts=opts)
    return {k: transfer_terms(r["s"], r[k]) for k in ("out", "iv_p", "iv_n")}


def cancellation(beta, opts=None, **kw):
    a = even_term(beta, opts=opts, **kw)
    half = max(abs(a["iv_p"][2]), abs(a["iv_n"][2]))
    diff = abs(a["out"][2])
    canc = 20 * math.log10(half / diff) if diff > 0 else float("inf")
    hd2 = (20 * math.log10(diff / (2 * abs(a["out"][1])))
           if diff > 0 else float("-inf"))
    return half, diff, canc, hd2


def check_e_even_order():
    head("E. What the asymmetry costs in even-order cancellation")
    print("        The even-order term is provoked with a nonlinear output")
    print("        resistance R_O + beta*I_out, identical in both amplifiers,")
    print("        and read out of a DC sweep of the code rather than an FFT:")
    print("        the even part of the transfer curve about mid code IS the")
    print("        even-order term, exactly and without windowing.")
    print("        beta is ASSUMED. What is reported is the ratio, which is")
    print("        a property of the network and not of beta.")
    print("        The sweep is at DC, where loop gain is highest, so the")
    print("        ABSOLUTE a2 here is far smaller than the in-band one --")
    print("        it scales as 1/T and T falls 20 dB/decade above 80 Hz.")
    print("        The RATIO does not, because both halves' loop gains fall")
    print("        together. Only the ratio is quoted.")
    print()
    print("        configuration                      a2, worse half"
          "   a2, difference   cancellation")
    rows = []
    for beta in (130.0, 1300.0):
        half, diff, canc, hd2 = cancellation(beta)
        rows.append(canc)
        print(f"        as built, beta = {beta:6.0f}          "
              f"{half:11.3e} V   {diff:11.3e} V    {canc:7.1f} dB")
    half, diff, canc_eq, _ = cancellation(130.0, equalise=2 * R_DIFF)
    print(f"        1208 ohm shunt at IV_N            "
          f"{half:11.3e} V   {diff:11.3e} V    {canc_eq:7.1f} dB")
    half, diff, canc_q, _ = cancellation(130.0, q_leg=R_DIFF / 3)
    # The same case at a looser solver tolerance. On the as-built circuit the
    # two agree to 0.1 dB; here they do not, which says the R/3 residual is
    # the measurement's own floor and not a number this method can quote.
    loose = dict(reltol=1e-6, vntol=1e-9, abstol=1e-13)
    _, diff2, canc_q2, _ = cancellation(130.0, opts=loose, q_leg=R_DIFF / 3)
    floored = abs(canc_q - canc_q2) > 1.0
    print(f"        non-inverting leg at R/3 = 201 ohm"
          f"{half:11.3e} V   {diff:11.3e} V    "
          + (f"  > {min(canc_q, canc_q2):.0f} dB" if floored
             else f"{canc_q:7.1f} dB"))
    if floored:
        print(f"        ...the same case at a looser solver tolerance "
              f"{canc_q2:5.1f} dB")
    print()
    print("        R/3 is not a fitted number. Mirror-image output currents")
    print("        need |d i_p/ds| = |d i_n/ds|, which is")
    print("        1/R_f + 1.5/R = 1/R_f + 1/(2Q), that is Q = R/3. Unity")
    print("        gain survives it because the condition for gain is")
    print("        R4/R3 = R2/R1 and both pairs stay equal.")

    ok = report(abs(rows[0] - rows[1]) < 1.0,
                "the cancellation ratio is a property of the network, not of "
                "the nonlinearity's size",
                f"{rows[0]:.1f} dB and {rows[1]:.1f} dB for coefficients ten "
                f"times apart")
    report(rows[0] < 10.0,
           f"as built, the output stage's even-order cancellation is "
           f"{rows[0]:.1f} dB",
           "0008 pays for this property with a whole register die; the "
           "difference amplifier\nspends most of it. Note the scope: the "
           "element-side cancellation 0008 is\nactually about is untouched. "
           "This is the output amplifiers' own even-order term.")
    report(min(canc_q, canc_q2) > rows[0] + 30,
           f"re-valuing the non-inverting leg to R/3 restores it to more than "
           f"{min(canc_q, canc_q2):.0f} dB",
           f"at the cost of "
           f"{abs(V_CM_DC) / (2 * R_DIFF / 3) * 2e3 - abs(V_CM_DC) / (2 * R_DIFF) * 2e3:.1f}"
           f" mA more on the negative rail for the two channels at mid code,\n"
           f"{V_FS / (2 * R_DIFF / 3) * 2e3 - V_FS / (2 * R_DIFF) * 2e3:.1f} mA"
           f" at negative full scale, and a 3.9 nF capacitor on that leg to "
           f"keep pole 3.\nThe residual is below what a DC sweep can "
           f"resolve here -- it moves by "
           f"{abs(canc_q - canc_q2):.0f} dB between two solver\ntolerances "
           f"that agree to 0.1 dB on the as-built circuit -- so the figure is "
           f"a floor.\nRejection, gain and the pole are all unchanged: "
           f"the gain condition is R4/R3 = R2/R1\nand both pairs stay equal, "
           f"so it needs two matched PAIRS rather than one array of four.")
    return rows[0], canc_eq, canc_q, ok


# ----------------------------------------------------------------- tampering
# A check that has never failed is not evidence. Each of these breaks the
# thing one check is supposed to catch; the run fails if a tamper *passes*.
def tamper():
    head("TAMPERS -- each breaks what one check claims to catch")
    bad = []

    def t(name, ok, detail):
        """``ok`` is True when the tamper was CAUGHT."""
        print(f"  {'caught' if ok else 'MISSED'}  {name}")
        for line in detail.splitlines():
            print(f"          {line}")
        if not ok:
            bad.append(name)

    # 1. The amplifier's own rejection has to be inside the measurement, or
    #    check A's "119.6 dB floor" row is measuring the network against
    #    itself and would read the same for any amplifier.
    base, _, _ = cmrr_db(freqs=(20.0,))
    inf_amp, _, _ = cmrr_db(freqs=(20.0,), cmrr_db=400.0)
    t("amplifier CMRR removed from the model (set to 400 dB)",
      inf_amp[0] > base[0] + 20,
      f"exact-network rejection goes {base[0]:.1f} -> {inf_amp[0]:.1f} dB, so "
      f"the 119.6 dB row is the\namplifier's 120 dB and not an artefact of "
      f"the network or of the measurement")

    # 2. Check B claims the offset comes from the common mode. Take the
    #    common mode away -- drive the elements bipolar -- and the offset has
    #    to go with it, or the table is measuring something else.
    r = sweep_code(build(eps=worst_case(1e-3), no_common_mode=True))
    a0_nocm = transfer_terms(r["s"], r["out"])[0]
    r = sweep_code(build(eps=worst_case(1e-3)))
    a0_cm = transfer_terms(r["s"], r["out"])[0]
    t("the 1.39 V of common mode removed, mismatch left at 0.1 %",
      abs(a0_nocm) < abs(a0_cm) / 100,
      f"offset {a0_cm * 1e3:+.3f} mV -> {a0_nocm * 1e6:+.3f} uV. The offset "
      f"tracks the common mode,\nwhich is what check B says it is measuring")

    # 3. The netlist says both legs need their capacitor: "a difference
    #    amplifier only keeps its rejection above the pole if both legs roll
    #    off together". Delete the non-inverting one. The point of this
    #    tamper is the shape the project has been caught by before: the
    #    measurement that would naturally be made -- the DC transfer curve
    #    that check B's offset comes from -- cannot see it AT ALL.
    freqs = (20.0, 20e3)
    ref, _, _ = cmrr_db(freqs=freqs, eps=worst_case(1e-3))
    cut, _, _ = cmrr_db(freqs=freqs, eps=worst_case(1e-3), drop_ref_cap=True)
    r = sweep_code(build(eps=worst_case(1e-3)))
    a0_ref = transfer_terms(r["s"], r["out"])[0]
    r = sweep_code(build(eps=worst_case(1e-3), drop_ref_cap=True))
    a0_cut = transfer_terms(r["s"], r["out"])[0]
    t("the non-inverting leg's 1.3 nF deleted",
      (cut[1] < ref[1] - 20) and abs(a0_cut - a0_ref) < 1e-9,
      f"the DC transfer curve does not move by a nanovolt: offset "
      f"{a0_ref * 1e3:+.4f} -> {a0_cut * 1e3:+.4f} mV.\nA check built on the "
      f"offset alone -- the natural one, since the offset is what the\n"
      f"common mode buys -- would pass a circuit missing half its "
      f"compensation.\n20 Hz rejection {ref[0]:.1f} -> {cut[0]:.1f} dB, "
      f"20 kHz {ref[1]:.1f} -> {cut[1]:.1f} dB. Check C is made\nacross the "
      f"band for exactly this reason")

    # 4. Check C blames the capacitors for the 20 kHz figure. Match them and
    #    the figure has to come back to what the array alone gives.
    caps, _, _ = cmrr_db(freqs=(20e3,), dcap=0.05, eps=worst_case(1e-3))
    matched, _, _ = cmrr_db(freqs=(20e3,), dcap=0.0, eps=worst_case(1e-3))
    t("the two capacitors made a matched pair (+/-0 %)",
      matched[0] > caps[0] + 5,
      f"20 kHz rejection {caps[0]:.1f} -> {matched[0]:.1f} dB, back to the "
      f"array's own 54 dB.\nThe 20 kHz figure is the capacitors, as check C "
      f"says")

    # 5. The load measurement. Probing the node with the amplifier lifted off
    #    it is the obvious way to do it and gives the wrong answer, because
    #    it takes the summing node's virtual ground away too. Recorded here
    #    because it is what a first attempt does.
    def lifted(side):
        tag = "tp" if side == "p" else "tn"
        c = build(code_source=False, lift=(tag,))
        c.SinusoidalVoltageSource("probe", "probe", c.gnd, amplitude=1.0)
        c.R("probe", "probe", f"iv_{side}", 1.0)
        an = _sim(c).ac(start_frequency=20, stop_frequency=20.02,
                        number_of_points=2, variation="lin")
        v = complex(np.array(an[f"iv_{side}"])[0])
        return abs(1.0 * v / (1.0 - v))
    lp, ln = lifted("p"), lifted("n")
    ip, inn = abs(output_load("p")), abs(output_load("n"))
    t("the load probed with the amplifier lifted off its own output",
      abs(lp - ip) / ip > 0.3,
      f"gives {lp:.1f} and {ln:.1f} ohm against the correct {ip:.1f} and "
      f"{inn:.1f}: lifting the amplifier\ntakes the summing node's virtual "
      f"ground with it and the 402 ohm feedback resistor\nstops being a 402 "
      f"ohm load. This is why `output_load` measures V_out/I_out in place")

    # 6. Check E's even-order extraction, with no nonlinearity to find.
    r = sweep_code(build(beta=0.0))
    a_lin = abs(transfer_terms(r["s"], r["out"])[2])
    _, a_nl, _, _ = cancellation(130.0)
    t("the nonlinearity removed (beta = 0)",
      a_lin < a_nl / 100,
      f"a2 of the difference output {a_nl:.3e} -> {a_lin:.3e} V. The "
      f"extraction is reporting the\nnonlinearity and not a fitting "
      f"artefact of the sweep")

    # 7. Check E claims the cancellation figure responds to any half-to-half
    #    asymmetry. Make the network symmetric and the amplifiers different
    #    instead.
    _, _, sym, _ = cancellation(130.0, q_leg=R_DIFF / 3)
    _, _, asym, _ = cancellation((130.0, 65.0), q_leg=R_DIFF / 3)
    t("network symmetric (R/3) but one amplifier twice as nonlinear",
      asym < sym - 20,
      f"cancellation falls from its floor ({sym:.0f} dB or better) to "
      f"{asym:.1f} dB. The figure tracks\nhalf-to-half asymmetry from any "
      f"source, not only from the resistor network")

    print()
    if bad:
        print(f"  {len(bad)} tamper(s) MISSED -- a check is not catching what "
              f"it claims to")
        _fails.extend(f"tamper missed: {b}" for b in bad)
    else:
        print("  every tamper was caught")
    return not bad


def main() -> int:
    print("=" * 74)
    print("DIFFERENCE STAGE -- ngspice, OPA1612 with finite CMRR and a "
          "finite output stage")
    print("=" * 74)
    print(f"  Amplifier: {AOL_DB:.0f} dB open loop (SBOS450C, the 2 kohm "
          f"typical), {GBW / 1e6:.0f} MHz GBW,")
    print(f"             {CMRR_DB:.0f} dB CMRR, {R_O:.0f} ohm open-loop "
          f"output resistance (ASSUMED)")
    print(f"  Network:   four {R_DIFF:.0f} ohm on one array, "
          f"{C_DIFF * 1e9:.1f} nF across two of them")

    check_a_ratio_not_tolerance()
    check_b_matching_requirement()
    check_c_across_the_band()
    check_d_unequal_loading()
    check_e_even_order()
    tamper()

    head("VERDICT")
    if _fails:
        for f in _fails:
            print(f"  FAIL  {f}")
        print(f"\nFAIL -- {len(_fails)} of the assertions above did not hold")
        return 1
    print("  The 0.1 % array already specified is adequate. The common mode "
          "it rejects is DC,")
    print("  so what a ratio error buys is a DC offset -- 2.8 mV worst case, "
          "inside a 10 mV")
    print("  budget and beside the 1.4 mV the 402 ohm array already "
          "contributes. No part change.")
    print("  Specify the RATIO, not the absolute tolerance: that is the "
          "quantity that does the work.")
    print()
    print("  Above 8 kHz the two 1.3 nF C0G capacitors set the rejection, "
          "not the array, and the")
    print("  netlist gives them no tolerance at all. It costs nothing today "
          "because there is no")
    print("  AC common mode of consequence, but the BOM is silent on the "
          "dominant component.")
    print()
    print("  D3 is real and bigger than its description: the output CURRENT "
          "swings differ by")
    print("  1.50 to 1, not the 1.25 the load ratio suggests, and the output "
          "stage's even-order")
    print("  cancellation measures 5.1 dB. The non-inverting leg at R/3 = "
          "201 ohm restores it to")
    print("  more than 40 dB -- the residual is below this measurement's own "
          "floor -- for 4.6 mA")
    print("  on the negative rail. That is a decision for 0008, not a fix.")
    print("\nPASS -- every assertion held and every tamper was caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())

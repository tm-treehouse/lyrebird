#!/usr/bin/env python3
"""Check the power tree arithmetically, since nothing else does.

There is no SPICE model in this repository and the netlist generators check
connectivity, not behaviour. `assert_below_abs_max` catches one specific class
of fault. Everything else about the supply -- whether a converter can deliver
its load, whether there is voltage left at the bottom of the input range,
what dissipates where, and in what order the rails arrive -- has only ever
been checked by hand, in prose, in two `power.md` files that both reviews
found stale.

This is not a simulation. It is the arithmetic those pages assert, written
down so it runs, so that changing a component value changes the verdict
instead of only the prose.

Every constant carries its source. Where a figure could not be verified
against a datasheet it is marked ASSUMED and the report says so, because the
failure mode this project keeps hitting is a confident number nobody checked.

    ./.venv/bin/python hardware/verify_power.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ----------------------------------------------------------------- sources
DS = "datasheet"
CALC = "calculation"
ASSUMED = "ASSUMED, unverified"
MEAS = "model measurement"


@dataclass
class Fact:
    value: float
    unit: str
    source: str
    note: str = ""

    def __str__(self) -> str:
        return f"{self.value:g} {self.unit}"


# ------------------------------------------------------------ the supply
# A 12 V adapter. Cheap ones are +/-5 %; the TVS is sized for the 19 V laptop
# brick that shares this barrel, which is a plugging mistake rather than a
# tolerance.
VIN_NOM = Fact(12.0, "V", ASSUMED, "adapter not yet chosen")
VIN_TOL = Fact(0.05, "", ASSUMED, "typical for an unregulated-spec adapter")
VIN_FAULT = Fact(19.0, "V", ASSUMED, "the brick that fits the same jack")

# F1, resettable fuse. Hold current and series resistance both matter: the
# resistance is in the path at full load.
F1_HOLD = Fact(0.5, "A", ASSUMED, "part unchosen; the old line named a 6 Vdc device")
F1_RMAX = Fact(0.30, "ohm", ASSUMED, "typical 1.1 A PPTC max initial R")

# D1, SS34 Schottky, reverse polarity.
D1_VF = Fact(0.35, "V", ASSUMED, "read off the SS34 typical curve, not a spec limit")
D1_IMAX = Fact(3.0, "A", DS, "SS34 average rectified")

# D2, SMAJ18A TVS. Was an SMAJ15A; a transient simulation showed the 15 V
# part conducting indefinitely on a 19 V adapter without ever tripping the
# fuse, because a TVS breakdown has a positive tempco and the fault settles
# instead of running away.
D2_STANDOFF = Fact(18.0, "V", DS, "SMAJ18A reverse standoff")
D2_VBR_MIN = Fact(20.0, "V", DS, "minimum breakdown; above a 19 V adapter")
D2_VCLAMP = Fact(29.2, "V", DS, "clamping voltage at 13.7 A")
D2_TEMPCO = Fact(0.088, "%/degC", DS, "why the fault settles rather than trips")

# U5, LMR33630, 12 V -> 5 V.
U5_VIN_MAX = Fact(36.0, "V", DS, "recommended operating max; abs max is 38 V")
U5_IOUT_MAX = Fact(3.0, "A", DS, "rated output current")
U5_EFF = Fact(0.91, "", DS, "typical, 12 V in / 5 V out, ~0.5 A")
U5_RTHJA = Fact(45.0, "C/W", DS, "HTSSOP-8 with thermal pad, JEDEC board")

# U3, LT3045, 5 V -> 3.32 V.
U3_DROPOUT = Fact(0.26, "V", DS, "LT3045 at 500 mA; less at our load")
U3_IQ = Fact(2.0, "mA", DS, "ground pin current")

# U4, LTM4622 dual, 5 V -> 2.5 V and 1.0 V.
U4_EFF_25 = Fact(0.88, "", ASSUMED, "not read off the efficiency curve")
U4_EFF_10 = Fact(0.80, "", ASSUMED, "not read off the efficiency curve")

# ------------------------------------------------------------- the loads
# These are the figures the two power.md pages carry today. Both reviews
# found those pages stale in other respects; these totals are the ones the
# module's page reached after every part was chosen, and they are the most
# current numbers in the repository.
# Decision 5 moved the module's negative rail to the main board and deleted
# its charge pump. The module's draw from 5 V falls by the pump's overhead;
# the negative rail becomes a separate load on a separate rail.
I_MODULE_5V = Fact(0.123, "A", CALC, "element 60.6 + clock 35.5 + op amp "
                                     "positive 23.6 + translator 3")
I_MODULE_N6V = Fact(0.064, "A", CALC, "op amp negative at the 200 ohm "
                                      "network: 21.6 quiescent + 13.9 element "
                                      "+ 21.0 network, worst case")
V_N6V = Fact(-5.98, "V", CALC, "1.0 V x (1 + 124k/24.9k), inverted")
INV_EFF = Fact(0.85, "", ASSUMED, "LMR33630 inverting; lower than buck mode")
I_MAIN_OTHER = Fact(0.234, "A", CALC, "main board, everything but the module")

# Split of the main board's own draw. Needed for dissipation per regulator
# rather than for the total.
I_3V3 = Fact(0.060, "A", ASSUMED, "FT601Q VCC33 + flash; main power.md is stale")
I_2V5 = Fact(0.090, "A", ASSUMED, "FPGA banks + VCCIO + flash")
I_1V0 = Fact(0.080, "A", ASSUMED, "FPGA core at this utilisation")

V_3V3 = Fact(3.32, "V", CALC, "100 uA x 33.2 k")
V_2V5 = Fact(2.50, "V", DS, "LTM4622 table value 19.1 k")
V_1V0 = Fact(1.00, "V", DS, "LTM4622 table value 90.9 k")
V_5V = Fact(5.02, "V", CALC, "1.0 V x (1 + 100k/24.9k)")

# Ramp: the SET pin sources 100 uA into C_SET with fast-start disabled.
SET_I = Fact(100e-6, "A", DS, "LT3045 SET pin current")
RAMP_K = 2.3  # t_ss ~ 2.3 * R_SET * C_SET

# -------------------------------------------------------------- checking
@dataclass
class Result:
    name: str
    ok: bool
    detail: str
    margin: str = ""
    assumed: bool = False


results: list[Result] = []


def check(name, ok, detail, margin="", assumed=False):
    results.append(Result(name, ok, detail, margin, assumed))


def main() -> int:
    vin_lo = VIN_NOM.value * (1 - VIN_TOL.value)
    vin_hi = VIN_NOM.value * (1 + VIN_TOL.value)

    i_5v = I_MODULE_5V.value + I_MAIN_OTHER.value
    p_5v = i_5v * V_5V.value
    # The negative rail is its own converter off the same 12 V.
    p_n6v = I_MODULE_N6V.value * abs(V_N6V.value)
    p_in_n6v = p_n6v / INV_EFF.value

    # ---- 1. current at the input, worst case (lowest Vin, so highest Iin)
    p_in = p_5v / U5_EFF.value + p_in_n6v
    i_in_hi = p_in / (vin_lo - D1_VF.value)

    check("Fuse hold current",
          i_in_hi < F1_HOLD.value * 0.8,
          f"input draws {i_in_hi*1000:.0f} mA worst case against a "
          f"{F1_HOLD.value:g} A hold",
          f"{(F1_HOLD.value/i_in_hi):.1f}x headroom")

    check("Schottky current rating",
          i_in_hi < D1_IMAX.value * 0.5,
          f"{i_in_hi*1000:.0f} mA through a {D1_IMAX.value:g} A part",
          f"{(D1_IMAX.value/i_in_hi):.1f}x headroom")

    # ---- 2. what actually reaches the buck at the bottom of the range
    v_fuse_drop = i_in_hi * F1_RMAX.value
    v_buck_in = vin_lo - v_fuse_drop - D1_VF.value
    check("Buck input headroom, worst case",
          v_buck_in > V_5V.value + 1.0,
          f"{v_buck_in:.2f} V reaches U5 at {vin_lo:.1f} V in "
          f"(fuse {v_fuse_drop*1000:.0f} mV, diode {D1_VF.value*1000:.0f} mV)",
          f"{v_buck_in - V_5V.value:.2f} V above the 5 V output",
          assumed=True)

    # ---- 3. absolute maxima on the input side
    # This check compares two datasheet constants to each other, so it cannot
    # fail for any input voltage and it passed with D2 deleted from the
    # netlist entirely. Kept, because the comparison is still worth asserting,
    # but it is a statement about the parts and not about the circuit -- the
    # circuit question is answered by the transient simulation instead.
    check("Buck rating covers the TVS clamp [structural]",
          D2_VCLAMP.value < U5_VIN_MAX.value,
          f"TVS clamps at {D2_VCLAMP.value:g} V against U5's "
          f"{U5_VIN_MAX.value:g} V maximum",
          f"{U5_VIN_MAX.value - D2_VCLAMP.value:.1f} V of margin; this compares "
          f"two constants and cannot fail on circuit changes")

    # What the 19 V case actually does, which is not what 0014 claimed.
    check("A 19 V adapter is accepted, not fought",
          VIN_FAULT.value < U5_VIN_MAX.value
          and VIN_FAULT.value < D2_VBR_MIN.value,
          f"{VIN_FAULT.value:g} V is below the TVS's {D2_VBR_MIN.value:g} V "
          f"breakdown and well inside U5's {U5_VIN_MAX.value:g} V, so the "
          f"board simply runs",
          "an SMAJ15A instead conducts at 41 mA and 117 degC forever without "
          "ever tripping the fuse")

    check("TVS does not conduct in normal operation",
          D2_STANDOFF.value > vin_hi,
          f"standoff {D2_STANDOFF.value:g} V against a high-tolerance "
          f"adapter at {vin_hi:.1f} V",
          f"{D2_STANDOFF.value - vin_hi:.1f} V of margin",
          assumed=True)

    # ---- 4. dissipation
    p_d1 = i_in_hi * D1_VF.value
    # Only the buck's own loss, not the inverter's input power, which p_in
    # now also carries. Getting this wrong inflates the junction-rise check
    # on a part that is not doing that work.
    p_u5 = p_5v / U5_EFF.value - p_5v
    p_u7 = p_in_n6v - p_n6v
    t_rise_u5 = p_u5 * U5_RTHJA.value
    check("Schottky dissipation",
          p_d1 < 0.5,
          f"{p_d1*1000:.0f} mW in an SMA package",
          "")
    check("Buck dissipation and junction rise",
          t_rise_u5 < 40,
          f"{p_u5*1000:.0f} mW, {t_rise_u5:.0f} C rise at "
          f"{U5_RTHJA.value:g} C/W",
          f"junction about {25 + t_rise_u5:.0f} C at 25 C ambient")

    p_u3 = (V_5V.value - V_3V3.value) * I_3V3.value
    check("LT3045 dissipation on the 3.3 V rail",
          p_u3 < 0.5,
          f"{(V_5V.value-V_3V3.value):.2f} V x {I_3V3.value*1000:.0f} mA "
          f"= {p_u3*1000:.0f} mW",
          "", assumed=True)

    # ---- 5. LDO headroom
    check("LT3045 dropout",
          (V_5V.value - V_3V3.value) > U3_DROPOUT.value,
          f"{(V_5V.value-V_3V3.value)*1000:.0f} mV across the part against "
          f"{U3_DROPOUT.value*1000:.0f} mV of dropout",
          f"{((V_5V.value-V_3V3.value)-U3_DROPOUT.value)*1000:.0f} mV spare")

    # ---- 6. buck output current
    check("Inverter output current",
          I_MODULE_N6V.value < U5_IOUT_MAX.value * 0.3,
          f"{I_MODULE_N6V.value*1000:.0f} mA at {V_N6V.value:.2f} V from an "
          f"LMR33630 wired as an inverting buck-boost",
          f"it sees VIN + |VOUT| = {vin_hi + abs(V_N6V.value):.1f} V against "
          f"a {U5_VIN_MAX.value:g} V rating",
          assumed=True)

    check("Buck output current",
          i_5v < U5_IOUT_MAX.value * 0.5,
          f"{i_5v*1000:.0f} mA against a {U5_IOUT_MAX.value:g} A part",
          f"{(U5_IOUT_MAX.value/i_5v):.1f}x headroom")

    # ---- 7. ramp order. The fault the review found was a rail arriving late
    # relative to one it has to track, not a rail being slow on its own.
    ramps = [
        ("+3V3  (LT3045, 33.2k, 100nF)", RAMP_K * 33.2e3 * 100e-9),
        ("+3V3  (had it kept 4.7uF)", RAMP_K * 33.2e3 * 4.7e-6),
    ]
    t_3v3 = ramps[0][1]
    check("FT601Q supply skew, VCCIO against VCC33",
          t_3v3 < 0.050,
          f"+3V3 reaches voltage in {t_3v3*1000:.1f} ms; +2V5 comes from a "
          f"switcher in well under a millisecond",
          f"skew {t_3v3*1000:.1f} ms, was {ramps[1][1]*1000:.0f} ms before "
          f"C_SET was reduced")

    # ---- report
    w = 46
    print("=" * 74)
    print("POWER TREE VERIFICATION — 12 V wall wart (0014)")
    print("=" * 74)
    print(f"\nInput   {vin_lo:.1f} to {vin_hi:.1f} V at the jack, "
          f"{i_in_hi*1000:.0f} mA worst case, {p_in:.2f} W")
    print(f"        -6V rail {I_MODULE_N6V.value*1000:.0f} mA "
          f"= {p_n6v:.2f} W out, {p_in_n6v:.2f} W in")
    print(f"Output  {i_5v*1000:.0f} mA at {V_5V.value:.2f} V "
          f"= {p_5v:.2f} W  "
          f"({I_MAIN_OTHER.value*1000:.0f} mA main + "
          f"{I_MODULE_5V.value*1000:.0f} mA module)")
    print(f"Losses  {(p_in-p_5v-p_n6v)*1000:.0f} mW total "
          f"({p_d1*1000:.0f} mW diode, {p_u5*1000:.0f} mW buck, "
          f"{p_u7*1000:.0f} mW inverter)\n")

    npass = sum(1 for r in results if r.ok)
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        flag = " [*]" if r.assumed else ""
        print(f"  {mark}  {r.name:{w}}{flag}")
        print(f"        {r.detail}")
        if r.margin:
            print(f"        -> {r.margin}")
    print(f"\n{npass}/{len(results)} checks pass")

    assumed = [r for r in results if r.assumed]
    if assumed:
        print(f"\n[*] {len(assumed)} checks rest on at least one unverified "
              f"constant.")
        print("    The adapter is not chosen, so its tolerance is a guess,")
        print("    and the main board's per-rail currents come from a page")
        print("    both reviews found stale. These verdicts are provisional.")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Output module netlist: oscillators, divider, registers, resistors, analog.

    KICAD10_SYMBOL_DIR=... python hardware/netlist/output_module.py

There is no DAC chip. The FPGA drives element lines; this board reclocks them,
sums them through matched resistors, and filters the result (0008, 0012).

PLACEHOLDER SYMBOLS are marked below. The part-selection work for the fanout
divider, the 16-bit register and the op amp never completed, so those carry
stock symbols with the intended part in the value field. Connectivity is
right; the symbols are not the final parts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from skidl import Net, Part, generate_netlist, generate_xml  # noqa: E402
import lyrebird_parts as lp  # noqa: E402

OUT = HERE.parent / "lyrebird-dac-reva"
N_ELEM = 32          # header provisions 32; 28 used by 3-bit differential
N_USED = 28
PER_CH = 14          # 7 positive + 7 negative


def _res(a, b, value):
    r = Part("Device", "R", value=value,
             footprint="Resistor_SMD:R_0402_1005Metric")
    r[1] += a
    r[2] += b
    return r


def _cap(a, b, value, footprint="Capacitor_SMD:C_0805_2012Metric"):
    c = Part("Device", "C", value=value, footprint=footprint)
    c[1] += a
    c[2] += b
    return c


def build():
    lp.setup()
    gnd = Net("GND"); gnd.drive = 7
    v5 = Net("+5V")
    v3v3_clk = Net("+3V3_CLK")     # clock chain, its own regulator
    v3v3_ref = Net("+3V3_REF")     # element reference: sets full scale
    vpos = Net("+5V_A"); vneg = Net("-5V_A")
    # The A side of the translator, the header-facing domain, has to be 2.5 V
    # and the header only carries +5V and ground (interface.md), so the
    # module regulates it. It is a logic supply, not a reference: nothing on
    # it reaches the signal.
    v2v5 = Net("+2V5")
    # Oscillator enables after translation, in the module's 3.3 V domain.
    osc_en = {"OSC_EN_48": Net("OSC_EN_48_3V3"),
              "OSC_EN_441": Net("OSC_EN_441_3V3")}

    # ---- Mezzanine header, mating with the main board's J2
    mez = Part("Connector_Generic", "Conn_02x40_Odd_Even", ref="J1",
               value="Mezzanine 2x40",
               footprint="Connector_PinHeader_1.27mm:PinHeader_2x40_P1.27mm_Vertical")
    mez_pins = list(mez.pins)
    idx = 0

    def nxt():
        nonlocal idx
        p = mez_pins[idx]; idx += 1
        return p

    elem = []
    for i in range(N_ELEM):
        n = Net(f"ELEM{i}")
        n += nxt()
        gnd += nxt()
        elem.append(n)
    mclk_out = Net("MCLK")          # module drives this back to the FPGA
    mclk_out += nxt()
    ctrl = {}
    for sig in ("OSC_EN_441", "OSC_EN_48", "MUTE_N", "ID0", "ID1"):
        n = Net(sig); n += nxt(); ctrl[sig] = n
    while idx < len(mez_pins):
        rail = v5 if idx % 2 == 0 else gnd
        rail += nxt()

    # ---- Oscillators. Crystek CCHD-957 at twice the element clock (0012),
    # option X for -40 to +85 C at +/-25 ppm. Standby shuts the resonator
    # down rather than only gating the output, so an idle oscillator does not
    # radiate next to the analog section.
    #
    # Both outputs share one net, which is only legal because the datasheet
    # says the output buffer is tri-stated as well as the resonator stopped:
    # "when placed in disable mode, the internal oscillator is completely
    # shut down in addition to its output buffer being placed in Tri-State".
    # E/D is active high with 0.7 x Vcc as the minimum logic one, and an open
    # pin runs, so the translated enables drive it directly.
    osc_out = Net("OSC_RAW")
    for ref, val, en in (("Y1", "CCHD-957X-25-49.152", "OSC_EN_48"),
                         ("Y2", "CCHD-957X-25-45.1584", "OSC_EN_441")):
        y = Part("lyrebird", "CCHD-957", ref=ref, value=val,
                 footprint="lyrebird:Oscillator_SMD_Crystek_CCHD-957_9x14mm")
        y["Vcc"] += v3v3_clk
        y["GND"] += gnd
        y["OUT"] += osc_out
        y["E/D"] += osc_en[en]

    # ---- Divide by two to the element clock, then fan out. Higher carrier
    # gives lower absolute jitter; dividing keeps those edges (0012).
    #
    # Two packages rather than one. Every integrated divider-plus-fanout part
    # found is built for hundreds of megahertz and costs 65 mA of core
    # current (Si53308), which does not fit: the module's clock rail is
    # ungated, and one unit load before enumeration leaves it about 50 mA
    # including both oscillators. A flip-flop and a small buffer come to
    # about 16 mA between them and keep the existing budget.
    #
    # U1, SN74LVC1G74 wired as a toggle: the inverted output drives the data
    # input, so Q divides the clock input by two with a 50 % duty cycle by
    # construction. 175 MHz minimum at 3.3 V against 49.152 MHz, and +/-24 mA
    # of drive so the edge into the buffer is fast, which is what keeps the
    # buffer's own additive jitter at its specified figure.
    div = Part("lyrebird", "SN74LVC1G74", ref="U1", value="SN74LVC1G74DCUR",
               footprint="Package_SO:VSSOP-8_2.3x2mm_P0.5mm")
    div_q = Net("ELEM_CLK_DIV")
    qbar = Net("ELEM_CLK_DIVB")
    div["CLK"] += osc_out
    div["Q"] += div_q
    div["~{Q}"] += qbar
    div["D"] += qbar
    # Preset and clear are asynchronous and active low; tie them inactive.
    div["~{PRE}"] += v3v3_clk
    div["~{CLR}"] += v3v3_clk
    div["VCC"] += v3v3_clk
    div["GND"] += gnd
    _cap(v3v3_clk, gnd, "100nF", "Capacitor_SMD:C_0402_1005Metric")

    # U12, LMK1C1104 1:4 buffer. 17.5 fs typical additive jitter and 50 ps
    # maximum output-to-output skew, which is the number that matters: skew
    # between the two register packages behaves like element mismatch
    # (0012, interface.md). Both clock inputs of a register package hang on
    # one output, so the two banks of a channel see one edge rather than two
    # buffer outputs 50 ps apart.
    buf = Part("lyrebird", "LMK1C1104", ref="U12", value="LMK1C1104PWR",
               footprint="Package_SO:TSSOP-8_4.4x3mm_P0.65mm")
    elem_clk = {0: Net("ELEM_CLK_L"), 1: Net("ELEM_CLK_R")}
    elem_clk_mez = Net("ELEM_CLK_MEZ")  # to the translator, FPGA leg
    buf["CLKIN"] += div_q
    buf["VDD"] += v3v3_clk
    buf["GND"] += gnd
    # 1G enables the outputs and has an internal 300 k pulldown, so it needs
    # a pullup to run at all; the datasheet asks for exactly this.
    _res(buf["1G"], v3v3_clk, "10k")
    buf["Y0"] += elem_clk[0]
    buf["Y1"] += elem_clk[1]
    buf["Y2"] += elem_clk_mez
    # Y3 is spare. "Unused outputs can be left floating" (SNAS791D).
    _cap(v3v3_clk, gnd, "100nF", "Capacitor_SMD:C_0402_1005Metric")

    # ---- Level translation at the boundary. A side faces the connector at
    # 2.5 V, B side faces the module at 3.3 V, so the mezzanine never carries
    # 3.3 V (0012). Verified against the function table: OE active low,
    # DIR low passes B to A.
    tr = lp.translator()
    tr.ref = "U2"
    tr.footprint = "Package_SO:TSSOP-16_4.4x5mm_P0.65mm"
    for p in tr.pins:
        nm = str(p.name)
        if nm.startswith("VCCA"):
            p += v2v5
        elif nm.startswith("VCCB"):
            p += v3v3_clk
        elif nm == "GND":
            p += gnd

    # Bank 1 carries the element clock back to the FPGA: B to A, so 1DIR is
    # low and 1OE low. This is the only path MCLK may take. Wiring ELEM_CLK
    # straight to the header would put a 3.3 V edge on a GateMate clock ball
    # whose absolute maximum is 2.75 V, and the assertion at the end of this
    # function exists because that is exactly what an earlier revision did.
    tr["1DIR"] += gnd
    tr["1~{OE}"] += gnd
    tr["1B1"] += elem_clk_mez
    tr["1A1"] += mclk_out
    # The spare channel's input is tied rather than left floating; its output
    # side, 1A2, stays open.
    tr["1B2"] += gnd

    # Bank 2 carries the two oscillator enables outward: A to B, 2DIR high.
    # DIR and OE are referenced to VCC(A), so they strap to the 2.5 V rail or
    # ground and never to 3.3 V (0012).
    tr["2DIR"] += v2v5
    tr["2~{OE}"] += gnd
    tr["2A1"] += ctrl["OSC_EN_48"]
    tr["2B1"] += osc_en["OSC_EN_48"]
    tr["2A2"] += ctrl["OSC_EN_441"]
    tr["2B2"] += osc_en["OSC_EN_441"]

    # ---- Reclocking registers, one package per channel so both polarities
    # share a die (0012).
    #
    # SN74ALVCH16374, 16-bit edge-triggered D-type flip-flop, TSSOP-48.
    # The constraint that picks the family is the input threshold: VIH is
    # 2.0 V for VCC = 2.7 to 3.6 V (SCES021L recommended operating
    # conditions), against the 2.4 V the FPGA guarantees at 2.5 V, which is
    # what lets the 28 element lines cross untranslated. LVC would reference
    # 0.7 x VCC = 2.31 V and AVC 0.65 x VCC = 2.15 V; both are the marginal
    # case 0012 rejects.
    #
    # The outputs have to be CMOS, not BiCMOS, because the supply IS the
    # voltage reference: ALVCH pulls to VCC - 0.2 V at 100 uA worst case and
    # a few tens of millivolts at the 1 mA an element draws, while the LVT
    # and ALVT families with the same 2.0 V threshold specify VOH as 2.4 V
    # at -8 mA and would put an uncontrolled drop in series with full scale.
    #
    # Two banks of eight share one die, one supply pin set and one clock
    # distribution, so both polarities of a channel match as closely as the
    # process allows. Both clock inputs go to the same net.
    regs = []
    for ch_i, (ch, ref) in enumerate((("L", "U3"), ("R", "U4"))):
        r = Part("lyrebird", "SN74ALVCH16374", ref=ref,
                 value="SN74ALVCH16374DGGR",
                 footprint="Package_SO:TSSOP-48_6.1x12.5mm_P0.5mm")
        for p in r.pins:
            nm = str(p.name)
            if nm == "VCC":
                p += v3v3_ref          # supply IS the voltage reference
            elif nm == "GND":
                p += gnd
            elif nm.endswith("CLK"):
                p += elem_clk[ch_i]      # both banks off one buffer output
            elif "OE" in nm:
                p += gnd               # outputs always enabled
        # Bit 8 of each bank is spare: 14 elements per channel in a 16-bit
        # package. Tie the spare data inputs low rather than leaving them to
        # the bus-hold latch, so the spare outputs have a defined state.
        for bank in (1, 2):
            gnd += lp.pin_named(r, f"{bank}D8")
        regs.append(r)

    # ---- Element resistors. Thin film arrays so elements share a die and
    # track thermally. Rotation makes 1% adequate, confirmed by the model at
    # 0.5 dB cost; what rotation cannot fix is voltage coefficient, hence
    # thin film rather than thick.
    #
    # 3.32 kohm per element (model/results/analog.txt, Q1). Three arguments
    # land within 300 ohm of each other: the elements' own thermal noise is
    # 1.1 dB under the measured digital floor there, the board fits one unit
    # load before enumeration with all 28 elements high only above 3312 ohm,
    # and past 3 kohm each doubling costs 3 dB and returns less current.
    #
    # The element is SPLIT around a shunt capacitor rather than being one
    # resistor, which is what buys the 1 MHz pole in front of the amplifier
    # (see the filter note below). 1.69k + 1.65k = 3.34 kohm, both E96, is
    # the closest even-ish split to 3.32 kohm that stays above 3312 ohm; an
    # even 1.65k + 1.65k would be 3.30 kohm and fail the power-on limit by
    # a hair. Constant-current drive is untouched: the DC current is still
    # V_ref/(R1+R2) at every code.
    ELEM_R1 = "1.69k 0.1% thin film"     # register side of the split
    ELEM_R2 = "1.65k 0.1% thin film"     # summing-node side of the split
    # Four summing nodes, not two. Left and right each need their own pair:
    # an earlier revision summed both channels into one differential pair,
    # which is a mono mixer, not a stereo DAC.
    sums = {}
    for ch, cn in enumerate("LR"):
        for side, sn in enumerate(("P", "N")):
            sums[(ch, side)] = Net(f"SUM_{cn}{sn}")
    # R_Network08 was the wrong symbol: it is a bussed array with a single
    # common terminal, so all 28 elements and both summing nodes resolved to
    # one net. R_Pack04 is four isolated elements, which is what the concave
    # 4x0402 footprint has pads for anyway. Seven packages cover 28 elements
    # on each half of the split.
    arr1 = [Part("Device", "R_Pack04", ref=f"RN{k+1}", value=ELEM_R1,
                 footprint="Resistor_SMD:R_Array_Concave_4x0402")
            for k in range(7)]
    arr2 = [Part("Device", "R_Pack04", ref=f"RN{k+8}", value=ELEM_R2,
                 footprint="Resistor_SMD:R_Array_Concave_4x0402")
            for k in range(7)]

    e = 0
    for ch in range(2):                     # L, R
        for side in range(2):               # positive, negative
            node = sums[(ch, side)]
            for j in range(7):
                if e >= N_USED:
                    break
                # Bank 1 of the package takes the positive side, bank 2 the
                # negative, so a channel's two polarities sit on one die.
                bank = side + 1
                elem[e] += lp.pin_named(regs[ch], f"{bank}D{j+1}")
                k = e % 4                    # R_Pack04 pairs pins k+1 and 8-k
                a1, a2 = arr1[e // 4], arr2[e // 4]
                mid = Net(f"ELEM_MID{e}")
                a1[k + 1] += lp.pin_named(regs[ch], f"{bank}Q{j+1}")
                a1[8 - k] += mid
                a2[k + 1] += mid
                a2[8 - k] += node            # resistor into the summing node
                # 180 pF C0G per element: the 1 MHz pole. Both ends of the
                # split sit at an AC ground (a flip-flop output one side, a
                # virtual ground the other), so the capacitor sees R1||R2 =
                # 834 ohm and the pole is 1.06 MHz. C0G because X7R's
                # voltage coefficient is a nonlinearity inside one element,
                # which the rotation does not fix.
                _cap(mid, gnd, "180pF C0G",
                     "Capacitor_SMD:C_0402_1005Metric")
                e += 1

    # ---- Precision rails. The element reference sets full scale and carries
    # the element switching current, which no regulator loop can track, so it
    # gets its own part and heavy local decoupling (0012, hardware/README.md).
    # V_OUT = 100 uA * R_SET. 33.2k and 24.9k are E96 values, giving 3.32 V
    # and 2.49 V. Neither absolute value matters: the reference rail sets
    # full scale but full scale is whatever it is, and what the design cares
    # about is the noise on it. SET was previously left open on all of these,
    # which means they had no programmed output voltage.
    for ref, out, val, rset in (
            ("U5", v3v3_ref, "LT3045 element reference", "33.2k 0.1%"),
            ("U6", v3v3_clk, "LT3045 clock chain", "33.2k 0.1%"),
            ("U9", v2v5, "LT3045 header-side 2.5 V", "24.9k 0.1%")):
        u = Part("Regulator_Linear", "LT3045xDD", ref=ref, value=val,
                 footprint="Package_DFN_QFN:DFN-12-1EP_3x3mm_P0.45mm_EP1.65x2.38mm")
        for p in u.pins:
            nm = str(p.name)
            if nm.startswith("IN"):
                p += v5
            elif nm.startswith("OUT"):
                p += out
            elif nm == "GND":
                p += gnd
        lp.lt3045_housekeeping(u, v5, gnd, rset, _res, _cap)
        _cap(out, gnd, "10uF")

    # ---- Output stage. Differential to single-ended, which the differential
    # element drive gives for free (0008). Two transimpedance amplifiers per
    # channel hold the summing nodes at virtual ground and turn element
    # current into volts; one difference amplifier per channel subtracts the
    # two polarities and drives the line.
    #
    # OPA1612AID, dual, SOIC-8. The analog stage is now the noise floor of
    # this design (model/results/analog.txt Q1c), and the amplifier's own
    # voltage noise is the largest single term in it, so this part is chosen
    # against that curve: 1.1 nV/rtHz at 1 kHz is the best row measured,
    # 126.3 dB of stage signal-to-noise at 3.32 kohm. 40 MHz gain-bandwidth
    # is the figure the intermodulation model assumed, not the 10 MHz lower
    # bound, so the 1 MHz element pole clears the threshold by 43 dB rather
    # than 10. ±2.25 V to ±18 V covers the ±5 V rails; 3.6 mA per channel is
    # what power.md already budgets per amplifier.
    #
    # Six amplifiers: two transimpedance per channel and one difference per
    # channel, so three dual packages. power.md costed four.
    def _opamp(ref):
        u = Part("Amplifier_Operational", "OPA1612AxD", ref=ref,
                 value="OPA1612AID",
                 footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
        u[8] += vpos            # V+
        u[4] += vneg            # V-
        return u

    # SOIC-8 dual: unit A is (out 1, -in 2, +in 3), unit B is (7, 6, 5),
    # V+ on 8 and V- on 4, from the datasheet pin configuration.
    UNIT = ((1, 2, 3), (7, 6, 5))

    # One 402 ohm array carries all four transimpedance resistors, so the
    # gain of both polarities of both channels is set on one die. Even-order
    # cancellation depends on the two sides matching (0008), and this is the
    # one place outside the element network where that matching lives.
    # 402 ohm E96 gives 6.958 mA x 402 = 1.978 V RMS at digital full scale.
    fb = Part("Device", "R_Pack04", ref="RN15", value="402R 0.1% thin film",
              footprint="Resistor_SMD:R_Array_Concave_4x0402")
    iv = {}
    for ch, u in enumerate((_opamp("U7"), _opamp("U10"))):
        for side in range(2):
            out_p, inv_p, ni_p = UNIT[side]
            node = sums[(ch, side)]
            o = Net(f"IV_{'LR'[ch]}{'PN'[side]}")
            u[out_p] += o
            u[inv_p] += node
            # The non-inverting input goes straight to ground rather than
            # through a bias-current compensation resistor: 60 nA through
            # 402 ohm is 24 uV of offset, while the resistor that would
            # cancel it would add its own thermal noise to a stage whose
            # noise is the thing being protected.
            u[ni_p] += gnd
            k = ch * 2 + side
            fb[k + 1] += node
            fb[8 - k] += o
            # Pole 2 of three: 2.0 nF across 402 ohm is 198 kHz. It also
            # compensates the stage, since it is what sets the node
            # impedance once the loop gain is gone (analog.txt Q2c).
            _cap(node, o, "2.0nF C0G", "Capacitor_SMD:C_0603_1608Metric")
            iv[(ch, side)] = o
        _cap(vpos, gnd, "100nF", "Capacitor_SMD:C_0402_1005Metric")
        _cap(vneg, gnd, "100nF", "Capacitor_SMD:C_0402_1005Metric")

    # Difference amplifier, one unit per channel in a single package.
    # Vout = IV_N - IV_P at unity gain, which is positive for a positive
    # code because the transimpedance stage inverts.
    dif = _opamp("U11")
    _cap(vpos, gnd, "100nF", "Capacitor_SMD:C_0402_1005Metric")
    _cap(vneg, gnd, "100nF", "Capacitor_SMD:C_0402_1005Metric")
    line_out = {}
    for ch in range(2):
        out_p, inv_p, ni_p = UNIT[ch]
        # Four 200 ohm resistors on one die. This network sets common-mode
        # rejection, which is what removes the 1.4 V of DC that both
        # transimpedance outputs carry at mid code, so ratio matching here
        # is doing real work.
        rn = Part("Device", "R_Pack04", ref=f"RN{16+ch}",
                  value="200R 0.1% thin film",
                  footprint="Resistor_SMD:R_Array_Concave_4x0402")
        inv = Net(f"DIFF_INV_{'LR'[ch]}")
        ref = Net(f"DIFF_REF_{'LR'[ch]}")
        o = Net(f"DIFF_OUT_{'LR'[ch]}")
        dif[out_p] += o
        dif[inv_p] += inv
        dif[ni_p] += ref
        rn[1] += iv[(ch, 0)]            # IV_P into the inverting input
        rn[8] += inv
        rn[2] += inv                    # feedback
        rn[7] += o
        rn[3] += iv[(ch, 1)]            # IV_N into the non-inverting input
        rn[6] += ref
        rn[4] += ref                    # non-inverting leg to ground
        rn[5] += gnd
        # Pole 3 of three: 3.9 nF across 200 ohm is 204 kHz. The same value
        # sits on the non-inverting leg, because a difference amplifier only
        # keeps its rejection above the pole if both legs roll off together.
        _cap(inv, o, "3.9nF C0G", "Capacitor_SMD:C_0603_1608Metric")
        _cap(ref, gnd, "3.9nF C0G", "Capacitor_SMD:C_0603_1608Metric")
        lo = Net(f"LINE_OUT_{'LR'[ch]}")
        # Series build-out, so cable capacitance does not hang directly on
        # the feedback loop. 100 ohm into a 10 kohm line load is 0.09 dB.
        _res(o, lo, "100R")
        line_out[ch] = lo

    neg = Part("Regulator_Linear", "LT3094xDD", ref="U8",
               value="LT3094 op amp negative rail",
               footprint="Package_DFN_QFN:DFN-12-1EP_3x3mm_P0.45mm_EP1.65x2.38mm")
    for p in neg.pins:
        nm = str(p.name)
        if nm.startswith("OUT"):
            p += vneg
        elif nm == "GND":
            p += gnd

    # ---- Module identity: combined line and headphone is 0b11; line only is
    # 0b01 (hardware/interface.md). Strapped for line only until the module
    # variant is decided.
    #
    # ID0 straps to the module's 2.5 V logic rail, never to the element
    # reference. That rail is 3.3 V and this net runs across the header to a
    # GateMate input whose absolute maximum is 2.75 V; an earlier revision
    # shorted the two. 1k against the 10k pull-down on the main board gives
    # 2.27 V, which is a valid high, and the series resistance means no
    # damage if the main board ever drives the pin.
    r = Part("Device", "R", value="1k",
             footprint="Resistor_SMD:R_0402_1005Metric")
    r[1] += ctrl["ID0"]
    r[2] += v2v5
    r = Part("Device", "R", value="10k",
             footprint="Resistor_SMD:R_0402_1005Metric")
    r[1] += ctrl["ID1"]
    r[2] += gnd

    # ---- Decoupling at the register packages, because that supply pin is
    # where the element switching current actually comes from.
    for _ in range(8):
        c = Part("Device", "C", value="100nF",
                 footprint="Capacitor_SMD:C_0402_1005Metric")
        c[1] += v3v3_ref
        c[2] += gnd

    # ---- Same assertion as the main board. The header is 2.5 V logic by
    # contract and carries +5V deliberately; everything else on it must be
    # unable to exceed 2.75 V (interface.md, 0012).
    import builtins
    lp.assert_below_abs_max(
        builtins.default_circuit,
        hv_rails={"+5V", "+3V3_CLK", "+3V3_REF", "+5V_A", "-5V_A"},
        protected={mez: {"+5V"}})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    os.chdir(OUT)
    build()
    generate_netlist(file_=str(OUT / "lyrebird-dac.net"))
    generate_xml(file_=str(OUT / "lyrebird-dac.xml"))
    print(f"netlist -> {OUT / 'lyrebird-dac.net'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

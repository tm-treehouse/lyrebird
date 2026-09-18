#!/usr/bin/env python3
"""Output module netlist: oscillators, divider, registers, resistors, analog.

    KICAD10_SYMBOL_DIR=... python hardware/netlist/output_module.py

There is no DAC chip. The FPGA drives element lines; this board reclocks them,
sums them through matched resistors, and filters the result (0008, 0012).

Every part is now a real one. The four that were placeholders - the oscillator,
the divider and fanout, the 16-bit register and the op amp - were selected
against their datasheets, and the parts the stock libraries do not carry have
symbols in ../symbols/lyrebird.kicad_sym with pinouts taken from those
datasheets. See ../lyrebird-dac-reva/parts-notes.md for why each one, and for
what could not be verified.
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
        # Four 604 ohm resistors on one die. This network sets common-mode
        # rejection, which is what removes the 1.4 V of DC that both
        # transimpedance outputs carry at mid code, so ratio matching here
        # is doing real work.
        #
        # 604 ohm rather than the 200 ohm analog.txt names, because this
        # network is also a load on the negative supply and 200 ohm makes it
        # an unaffordable one. The transimpedance outputs sit between 0 and
        # -2.8 V, so the network's current flows out of ground and into their
        # output stages, which sink it to the negative rail: 21 mA at 200 ohm
        # against 7 mA here, on a rail that also carries all 13.9 mA of
        # element current and that a charge pump has to make from 5 V at
        # twice the current. The cost is 2.1 dB of stage noise; the arithmetic
        # is in parts-notes.md.
        rn = Part("Device", "R_Pack04", ref=f"RN{16+ch}",
                  value="604R 0.1% thin film",
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
        # Pole 3 of three: 1.3 nF across 604 ohm is 203 kHz, the same corner
        # analog.txt asks for with its own 3979 pF across 200 ohm. The same
        # value sits on the non-inverting leg, because a difference amplifier
        # only keeps its rejection above the pole if both legs roll off
        # together.
        _cap(inv, o, "1.3nF C0G", "Capacitor_SMD:C_0603_1608Metric")
        _cap(ref, gnd, "1.3nF C0G", "Capacitor_SMD:C_0603_1608Metric")
        lo = Net(f"LINE_OUT_{'LR'[ch]}")
        # Series build-out, so cable capacitance does not hang directly on
        # the feedback loop. 100 ohm into a 10 kohm line load is 0.09 dB.
        _res(o, lo, "100R")
        line_out[ch] = lo

    # ---- The bipolar rail. A 5 V input cannot make +5 V with headroom, so a
    # charge pump makes both polarities and low-dropout regulators drop to
    # the final rails: op amp rejection falls off steeply with frequency, so
    # at a pump's switching frequency the amplifier rejects far less than its
    # headline figure (0009).
    #
    # LTC3265: boost charge pump, inverting charge pump, and a 50 mA LDO on
    # each, in one package. Verified against datasheet 3265fa.
    #
    # VIN_N is tied to VOUT+ rather than to VIN_P, which is the datasheet's
    # own instruction for this case: "If VIN_N is tied to VOUT+, the output at
    # VOUT- will be -VOUT+ or -2 * VIN_P. This configuration is suitable for
    # symmetric outputs at LDO+ and LDO- pins." Tying it to VIN_P instead
    # would cap the negative raw rail at -VIN_P, which cannot support a -5 V
    # output through a regulator that needs its dropout.
    pump_p = Net("PUMP_P")          # 2 x VIN_P, also the inverting pump input
    pump_n = Net("PUMP_N")          # -PUMP_P
    vpos_raw = Net("+5V7_A")        # LDO+, the LT3045's input
    vneg_raw = Net("-5V7_A")        # LDO-, the LT3094's input
    pump = Part("lyrebird", "LTC3265", ref="U13", value="LTC3265EDHC#TRPBF",
                footprint="Package_DFN_QFN:DFN-18-1EP_3x5mm_P0.5mm_EP1.66x4.4mm")
    pump["VIN_P"] += v5
    pump["GND"] += gnd
    pump["VOUT+"] += pump_p
    pump["VIN_N"] += pump_p
    pump["VOUT-"] += pump_n
    pump["LDO+"] += vpos_raw
    pump["LDO-"] += vneg_raw
    _cap(v5, gnd, "10uF")
    _cap(pump_p, gnd, "10uF")
    _cap(pump_n, gnd, "10uF")
    _cap(pump_n, gnd, "10uF")      # VOUT- feeds the LT3094 directly; halve the
                                   # 500 kHz ripple before its rejection sees it
    _cap(pump_p, gnd, "1uF", "Capacitor_SMD:C_0603_1608Metric")  # at VIN_N
    _cap(vpos_raw, gnd, "10uF")
    _cap(vneg_raw, gnd, "10uF")
    # Flying capacitors, one per pump.
    _cap(pump["CBST+"], pump["CBST-"], "1uF 25V X7R")
    _cap(pump["CINV+"], pump["CINV-"], "1uF 25V X7R")
    # MODE low is constant frequency rather than Burst Mode. Burst costs less
    # quiescent current but puts the ripple at a hysteretic rate that moves
    # with load; constant frequency puts it at a known 500 kHz where the
    # LT3045 and LT3094 that follow reject it, which is the whole reason they
    # are there. RT to ground selects the 500 kHz default, the highest
    # available and the furthest from the audio band.
    pump["MODE"] += gnd
    pump["RT"] += gnd
    # Reference bypass on both LDOs: the datasheet's stated purpose is to
    # reduce their output noise, and these two rails reach the signal.
    _cap(pump["BYP+"], gnd, "100nF", "Capacitor_SMD:C_0402_1005Metric")
    _cap(pump["BYP-"], gnd, "100nF", "Capacitor_SMD:C_0402_1005Metric")
    # ADJ servos to +/-1.2 V. 46.4k over 12.4k gives 1.2 x (1 + 46.4/12.4) =
    # 5.69 V, which is 0.69 V of headroom for the LT3045 and LT3094 over
    # their +/-5 V outputs and keeps the pump's own 32 ohm output impedance
    # out of the final rail.
    #
    # The setting is chosen by the arithmetic in parts-notes.md rather than
    # by symmetry with anything. The negative chain is the tight one, because
    # it inverts the already-sagged doubled rail: at the worst-case 4.43 V
    # from the header and four amplifiers' worth of maximum quiescent
    # current, VOUT- reaches only -6.17 V and LDO- needs 5.96 V of it. A
    # 6.0 V setting would drop out there; 5.69 V holds with 0.21 V to spare
    # and still leaves both final regulators more headroom than their
    # dropout needs.
    _res(vpos_raw, pump["ADJ+"], "46.4k 1%")
    _res(pump["ADJ+"], gnd, "12.4k 1%")
    _res(vneg_raw, pump["ADJ-"], "46.4k 1%")
    _res(pump["ADJ-"], gnd, "12.4k 1%")
    # EN+ and EN- must not float, and they are what holds the analog stage
    # off before enumeration. One unit load applies until the device is
    # configured, and this stage does not fit inside it at any element value
    # (analog.txt Q1b), so it is gated on MUTE_N: low or undriven means the
    # pumps and both LDOs are off. The polarity is already right, since
    # MUTE_N is asserted low to mute. The enable thresholds are 2 V rising
    # maximum and 0.4 V falling minimum, so the header's 2.5 V logic clears
    # them, and each pin has a 0.7 uA internal pull-down, so nothing here can
    # drive the mezzanine above its own level.
    pump["EN+"] += ctrl["MUTE_N"]
    pump["EN-"] += ctrl["MUTE_N"]
    # 100 k to ground so the net is defined rather than held by 0.7 uA while
    # the FPGA is unconfigured and its pin is high impedance.
    _res(ctrl["MUTE_N"], gnd, "100k")

    # Final rails. Both regulators are the reason the pump is allowed near an
    # audio stage at all: 0.8 uVRMS of their own and steep rejection of what
    # arrives from the pump.
    pos = Part("Regulator_Linear", "LT3045xDD", ref="U14",
               value="LT3045 op amp positive rail",
               footprint="Package_DFN_QFN:DFN-12-1EP_3x3mm_P0.45mm_EP1.65x2.38mm")
    for p in pos.pins:
        nm = str(p.name)
        if nm.startswith("IN"):
            p += vpos_raw
        elif nm.startswith("OUT"):
            p += vpos
        elif nm == "GND":
            p += gnd
    lp.lt3045_housekeeping(pos, vpos_raw, gnd, "49.9k 0.1%", _res, _cap)
    _cap(vpos, gnd, "10uF")

    # The LT3094 is the negative counterpart and its pins mirror the LT3045's,
    # verified against its own datasheet: 100 uA out of SET through R_SET sets
    # the output, so 49.9k gives -4.99 V and is the value its own Table 1
    # lists for -5 V. "If unused, tie EN/UV to IN. Do not float the EN/UV
    # pin." "If power good and fast start-up functionality are not needed, tie
    # PGFB to IN." EN/UV enables on either polarity beyond +/-1.35 V, so
    # tying it to the negative input is an enable, not a shutdown.
    # The LT3094 takes the inverting pump's output directly, not LDO-. The
    # negative rail carries the quiescent current of six amplifiers, all
    # 13.9 mA of element current, and the difference network's current, which
    # is 42 to 45 mA together and reaches 56 mA with maximum quiescent
    # current over temperature. LDO- is a 50 mA part, and its own dropout
    # would cost another 450 mV of headroom that the doubled-then-inverted
    # rail does not have at the bottom of the USB range. VOUT- has the pump's
    # own current capability behind it instead, and the LT3094's rejection is
    # what the design was relying on anyway.
    neg = Part("Regulator_Linear", "LT3094xDD", ref="U8",
               value="LT3094 op amp negative rail",
               footprint="Package_DFN_QFN:DFN-12-1EP_3x3mm_P0.45mm_EP1.65x2.38mm")
    for p in neg.pins:
        nm = str(p.name)
        if nm.startswith("IN"):
            p += pump_n
        elif nm.startswith("OUT"):
            p += vneg
        elif nm == "GND":
            p += gnd
    _res(neg["SET"], gnd, "49.9k 0.1%")
    _cap(neg["SET"], gnd, "4.7uF")
    pump_n += neg["EN/UV"]
    pump_n += neg["PGFB"]
    # Unlike the LT3045, the LT3094's pin description gives no instruction for
    # an unused ILIM, so the current limit is programmed rather than the pin
    # tied: the scale factor is 3.75 A x kohm, so 24.9k sets about 150 mA,
    # well above the 22 mA this rail carries and below what the pump's LDO
    # can deliver into a fault.
    _res(neg["ILIM"], gnd, "24.9k 1%")
    # VIOC: "If unused, float the VIOC pin." PG is an open-collector flag and
    # is unused, as on the LT3045s.
    _cap(vneg, gnd, "10uF")

    # ---- Analog output. LINE OUT only on this variant, so one 3.5 mm stereo
    # jack: Same Sky (formerly CUI Devices) SJ1-3523N, 3.5 mm, stereo, right
    # angle, through hole, three conductors and no internal switches, which
    # is what the stock footprint's three pads are. A switched jack would
    # earn its place on a combined module, where the switch contact gates the
    # headphone amplifier (0007); here there is nothing to gate.
    #
    # Tip is left, ring is right, sleeve is ground, which is the TRS
    # convention the symbol's pin numbering follows.
    jack = Part("Connector_Audio", "AudioJack3", ref="J2", value="SJ1-3523N",
                footprint="Connector_Audio:Jack_3.5mm_CUI_SJ1-3523N_Horizontal")
    jack["T"] += line_out[0]
    jack["R"] += line_out[1]
    jack["S"] += gnd
    # The jack is the only port on the board and therefore the antenna. 100 pF
    # against the 100 ohm build-out is a 16 MHz corner, which is nothing in
    # band and something against radio frequency arriving from outside.
    for ch in range(2):
        _cap(line_out[ch], gnd, "100pF C0G",
             "Capacitor_SMD:C_0402_1005Metric")

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
        hv_rails={"+5V", "+3V3_CLK", "+3V3_REF", "+5V_A", "-5V_A",
                  "PUMP_P", "PUMP_N", "+5V7_A", "-5V7_A"},
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

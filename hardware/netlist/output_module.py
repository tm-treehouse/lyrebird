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
    # Two pins of -6 V, then the alternating tail. This mirrors the main
    # board's allocation exactly and has to: the two halves of the connector
    # agree pin for pin or nothing works, and the pair is adjacent so a
    # half-inserted connector cannot present one without the other.
    # 100 k to ground so the net is defined rather than floating while the
    # FPGA is unconfigured and its pin is high impedance -- which, with the
    # rails gated off it, means the analog stage stays off until something
    # deliberately turns it on.
    _res(ctrl["MUTE_N"], gnd, "100k")
    mez_neg = Net("-6V_A")
    for _ in range(2):
        mez_neg += nxt()
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
    # 100 k to ground on each enable, for the same reason MUTE_N has one: an
    # open E/D pin runs, and before the FPGA is configured its pins are high
    # impedance and the translator's outputs may be too. Without these, both
    # oscillators start and drive OSC_RAW into each other -- the one net where
    # that is possible, because the shared output is only legal while exactly
    # one part is enabled. Defaulting both off is safe: nothing downstream
    # needs the element clock until the FPGA is running.
    for _en in osc_en.values():
        _res(_en, gnd, "100k")

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
                 footprint="Package_DFN_QFN:DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm")
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
            # Pole 2. Matching between the two halves matters less here than
            # at the difference stage -- this capacitor is inside a feedback
            # loop that the rotation averages across -- but it is the same
            # class of part and the same argument, so it carries a tolerance
            # rather than none.
            _cap(node, o, "2.0nF C0G 2%", "Capacitor_SMD:C_0603_1608Metric")
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
        #
        # 200 ohm, which is what analog.txt names and what the noise
        # arithmetic wants. It was 604 ohm for one round, because the network
        # loads the negative supply -- 21 mA here against 7 at 604 -- and a
        # charge pump on the module made that current cost twice over. That
        # pump is gone (0015): the negative rail now arrives from the
        # main board, where 12 V makes an inverter cheap, and the current is
        # ordinary again. The 2.1 dB the compromise cost is recovered.
        #
        # Pole 3 moves with the resistance and has to be held: 3.9 nF across
        # 200 ohm is 204 kHz, the same corner 1.3 nF across 604 ohm gave.
        rn = Part("Device", "R_Pack04", ref=f"RN{16+ch}",
                  # 0.1 % RATIO, not 0.1 % absolute. An absolute tolerance
                  # permits both legs to sit at opposite ends of it, which is
                  # a 0.2 % ratio error and twice the common-mode leak. The
                  # ratio is the quantity doing the work and the one to order
                  # against; hardware/sim/difference_stage.py measures what it
                  # buys. Absolute value is uncritical here -- it sets gain,
                  # which is calibrated out, not rejection.
                  value="200R, 0.1% RATIO matched, thin film array",
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
        # These two are matched parts, not merely C0G ones, and that is a
        # simulation result rather than caution. Above 8.1 kHz they -- not the
        # resistor array -- set the stage's common-mode rejection, because a
        # mismatch between them unbalances the two legs with frequency where
        # the resistors stay matched. At 20 kHz, 5 % parts give 46.1 dB where
        # the 0.1 % array alone would give 54.0. The netlist specified no
        # tolerance at all on the component that dominates.
        #
        # 2 % is readily stocked in C0G and puts this back under the array.
        # Removing the non-inverting one entirely does not move the DC
        # transfer curve by a nanovolt while 20 kHz rejection falls 28 dB,
        # so an offset check cannot police this: see difference_stage.py.
        _cap(inv, o, "3.9nF C0G 2%", "Capacitor_SMD:C_0603_1608Metric")
        _cap(ref, gnd, "3.9nF C0G 2%", "Capacitor_SMD:C_0603_1608Metric")
        lo = Net(f"LINE_OUT_{'LR'[ch]}")
        # Series build-out, so cable capacitance does not hang directly on
        # the feedback loop. 100 ohm into a 10 kohm line load is 0.09 dB.
        _res(o, lo, "100R")
        line_out[ch] = lo

    # ---- The bipolar rail (0015, superseding 0009's
    # arrangement and the LTC3265 that implemented it).
    #
    # The module used to make both polarities here, doubling the mezzanine's
    # 5 V and inverting the doubled rail. It cost 73 mA of conversion
    # overhead -- a third of the module -- and it put a 500 kHz switcher on
    # the analog board, whose flying-capacitor return was an open layout
    # risk. It also made negative-rail current expensive enough that the
    # difference network went to 604 ohm rather than 200, forfeiting 2.1 dB.
    #
    # Only the negative rail ever needed the pump. The output swings
    # +/-2.83 V peak and the OPA1612 reaches within 600 mV of its rails, so
    # the positive analog supply needs about 3.5 V -- and the mezzanine has
    # carried 5 V all along. The doubler existed because the module made both
    # rails symmetrically from one, not because either rail required it.
    #
    # So the positive rail is now an LT3045 straight off the mezzanine's 5 V,
    # dropping tens of millivolts at 22 mA, and the negative rail arrives
    # from the main board at -6 V where 12 V makes an inverter cheap. Both
    # final regulators stay exactly where they were: their rejection is what
    # the design leans on, and it is wanted at the point of load rather than
    # at the other end of a connector.
    #
    # What this deletes: the LTC3265, two flying capacitors, two ADJ
    # dividers, two reference bypasses and the bulk that fed them. The
    # analog board now contains no switching converter at all.
    vneg_raw = mez_neg                  # -6 V across the mezzanine
    vpos_raw = v5                       # the rail that was always there

    pos = Part("Regulator_Linear", "LT3045xDD", ref="U14",
               value="LT3045 op amp positive rail, +4.53 V from mezzanine 5 V",
               footprint="Package_DFN_QFN:DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm")
    for p in pos.pins:
        nm = str(p.name)
        if nm.startswith("IN"):
            p += vpos_raw
        elif nm.startswith("OUT"):
            p += vpos
        elif nm == "GND":
            p += gnd
    # MUTE_N gates this rail, as it gated the charge pump it replaces. The
    # reason has changed and is worth recording: 0009 needed the analog stage
    # held off to stay inside one unit load before enumeration, and 0014
    # retired that rule entirely. What remains is the audio reason -- the
    # element lines are undefined until the FPGA configures, and the jack has
    # no DC blocking -- so the stage should not be live before there is a
    # code to convert.
    #
    # That makes decision D10 purely an audio question now. Collapsing the
    # supplies is a blunt mute and every assertion is a transient into an
    # unblocked output; with the budget argument gone, a proper output mute
    # or a digital ramp is free to win on merit.
    #
    # 45.3k, not the 49.9k this carried when the charge pump fed it. 100 uA
    # through SET sets the output, so 49.9k programs 4.99 V -- and the input
    # is now the header's 5.02 V rather than the pump's 5.69 V, which leaves
    # 30 mV against a part whose datasheet dropout is 260 mV at 500 mA. The
    # rail would not have come up to its programmed voltage, and nothing in
    # the repository was checking: verify_power.py tests the main board's
    # LT3045, which has 1.7 V of headroom, and none of the module's.
    #
    # 45.3k gives 4.53 V and 490 mV of headroom. That is still far more than
    # the stage needs: the output swings +/-2.83 V peak and the OPA1612
    # reaches within 600 mV of its rails, so 3.43 V would do and this leaves
    # 3.93 V available.
    #
    # The rails are deliberately asymmetric now, +4.53 and -4.99, and it is
    # harmless -- both clear the swing with room, and matching the negative
    # one down would add 30 mW of dissipation in the LT3094 for nothing.
    lp.lt3045_housekeeping(pos, vpos_raw, gnd, "45.3k 0.1%", _res, _cap,
                           en=ctrl["MUTE_N"])
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
            p += vneg_raw
        elif nm.startswith("OUT"):
            p += vneg
        elif nm == "GND":
            p += gnd
    _res(neg["SET"], gnd, "49.9k 0.1%")
    _cap(neg["SET"], gnd, "4.7uF")
    # Same gate on the negative rail. The LT3094's EN/UV enables on either
    # polarity beyond +/-1.35 V, so the header's 2.5 V logic high enables it
    # and a low holds it off, which is the polarity MUTE_N already has.
    ctrl["MUTE_N"] += neg["EN/UV"]
    vneg_raw += neg["PGFB"]
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

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

    # ---- Oscillators. Crystek CCHD-957 at twice the element clock (0012).
    # Standby shuts the resonator down rather than gating the output, so an
    # idle oscillator does not radiate next to the analog section.
    # PLACEHOLDER SYMBOL: stock 4-pin oscillator, correct pinout (EN/GND/OUT/Vdd).
    osc_out = Net("OSC_RAW")
    for ref, val, en in (("Y1", "CCHD-957 49.152MHz", "OSC_EN_48"),
                         ("Y2", "CCHD-957 45.1584MHz", "OSC_EN_441")):
        y = Part("Oscillator", "ASE-xxxMHz", ref=ref, value=val,
                 footprint="Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm")
        y["Vdd"] += v3v3_clk
        y["GND"] += gnd
        y["OUT"] += osc_out
        y["EN"] += osc_en[en]

    # ---- Divide by two to the element clock. Higher carrier gives lower
    # absolute jitter; dividing keeps those edges (0012).
    # PLACEHOLDER SYMBOL: real part is a low-additive-jitter fanout divider.
    div = Part("74xGxx", "74AUP1G74", ref="U1", value="clock divider /2",
               footprint="Package_TO_SOT_SMD:SOT-353_SC-70-5")
    elem_clk = Net("ELEM_CLK")
    for p in div.pins:
        nm = str(p.name)
        if nm in ("CLK", "CP", "C"):
            p += osc_out
        elif nm.startswith("Q") and "~" not in nm:
            p += elem_clk
        elif nm in ("VCC", "Vdd", "VDD"):
            p += v3v3_clk
        elif nm in ("GND", "VSS"):
            p += gnd

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
    tr["1B1"] += elem_clk
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
    # share a die (0012). PLACEHOLDER SYMBOL: stock octal; the real part is a
    # 16-bit register with a 2.0 V input threshold at 3.3 V, which is what
    # lets the element lines cross untranslated. A custom symbol is needed.
    regs = []
    for ch, ref in (("L", "U3"), ("R", "U4")):
        for half in ("a", "b"):
            r = Part("74xx", "74HCT574", ref=f"{ref}{half}",
                     value=f"16-bit register (ch {ch}) PLACEHOLDER",
                     footprint="Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm")
            for p in r.pins:
                nm = str(p.name)
                if nm in ("VCC", "Vdd"):
                    p += v3v3_ref      # supply IS the voltage reference
                elif nm in ("GND", "VSS"):
                    p += gnd
                elif nm in ("CP", "CLK", "C"):
                    p += elem_clk
                elif nm.startswith("OE") or nm.startswith("~{OE}"):
                    p += gnd
            regs.append(r)

    # ---- Element resistors. Thin film arrays so elements share a die and
    # track thermally. Rotation makes 1% adequate, confirmed by the model at
    # 0.5 dB cost; what rotation cannot fix is voltage coefficient, hence
    # thin film rather than thick.
    sum_p, sum_n = Net("SUM_P"), Net("SUM_N")
    reg_d = [[p for p in r.pins if str(p.name).startswith("D")] for r in regs]
    reg_q = [[p for p in r.pins if str(p.name).startswith("Q")] for r in regs]
    # R_Network08 was the wrong symbol: it is a bussed array with a single
    # common terminal, so all 28 elements and both summing nodes resolved to
    # one net. R_Pack04 is four isolated elements, which is what the concave
    # 4x0402 footprint has pads for anyway. Seven packages cover 28 elements.
    arrays = [Part("Device", "R_Pack04", ref=f"RN{k+1}", value="1k thin film",
                   footprint="Resistor_SMD:R_Array_Concave_4x0402")
              for k in range(7)]

    e = 0
    for ch in range(2):                     # L, R
        for side in range(2):               # positive, negative
            node = sum_p if side == 0 else sum_n
            for j in range(7):
                if e >= N_USED:
                    break
                r = regs[ch * 2 + side]
                q = reg_q[ch * 2 + side]
                d = reg_d[ch * 2 + side]
                if j < len(d):
                    elem[e] += d[j]          # FPGA line into the register
                ra = arrays[e // 4]
                k = e % 4                    # R_Pack04 pairs pins k+1 and 8-k
                if j < len(q):
                    q[j] += ra[k + 1]        # register output drives resistor
                ra[8 - k] += node            # resistor into the summing node
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
    # element drive gives for free (0008).
    # PLACEHOLDER SYMBOL: op amp not selected.
    op = Part("Amplifier_Operational", "OPA1612AxD", ref="U7",
              value="output op amp PLACEHOLDER",
              footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
    line_out = Net("LINE_OUT")
    for p in op.pins:
        nm = str(p.name)
        if nm == "V+":
            p += vpos
        elif nm == "V-":
            p += vneg
    # First filter pole for one part: the summing resistors are already in
    # the path, so a shunt capacitor at each node gives it before anything
    # active sees the stepped waveform.
    for node in (sum_p, sum_n):
        c = Part("Device", "C", value="1nF C0G",
                 footprint="Capacitor_SMD:C_0603_1608Metric")
        c[1] += node
        c[2] += gnd

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

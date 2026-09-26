#!/usr/bin/env python3
"""Main board netlist: USB bridge, FPGA, power tree, mezzanine header.

    KICAD10_SYMBOL_DIR=... python hardware/netlist/main_board.py

Emits a KiCad netlist and a BOM into hardware/lyrebird-main-reva/.

Every design choice here traces to a decision record. Bank allocation is
against the real ball map in the stock KiCad GateMate symbol, not invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from skidl import Net, Part, generate_netlist, generate_xml  # noqa: E402
import lyrebird_parts as lp  # noqa: E402

OUT = HERE.parent / "lyrebird-main-reva"
N_ELEM = 32          # provisioned, 28 used (0008/0012)
N_DATA = 32

# Footprints for the passive sizes actually used here.
FP_C = {"0402": "Capacitor_SMD:C_0402_1005Metric",
        "0603": "Capacitor_SMD:C_0603_1608Metric",
        "0805": "Capacitor_SMD:C_0805_2012Metric",
        # Bulk on the 12 V input and the 5 V output. A 22 uF or 47 uF part
        # with usable derating at these voltages does not come in 0805.
        "1210": "Capacitor_SMD:C_1210_3225Metric"}
FP_R = "Resistor_SMD:R_0402_1005Metric"


def rails():
    # +1V0_FT is the FT601Q's own internal LDO output. It is a separate net
    # from the board's +1V0: the datasheet says that rail is "not to be used
    # for external devices", and it feeds only VD10 and AVDD on the bridge.
    n = {k: Net(k) for k in ("GND", "USB_VBUS", "VIN_RAW", "+12V", "+5V",
                             "-6V_A", "+3V3", "+2V5", "+1V0", "+1V0_FT")}
    n["GND"].drive = 7
    return n


def decouple(net_hi, net_gnd, value="100nF", size="0402"):
    c = Part("Device", "C", value=value, footprint=FP_C[size])
    c[1] += net_hi
    c[2] += net_gnd
    return c


def resistor(a, b, value, footprint=FP_R):
    r = Part("Device", "R", value=value, footprint=footprint)
    r[1] += a
    r[2] += b
    return r


def pullup(net, rail, value="10k"):
    return resistor(net, rail, value)


def build():
    lp.setup()
    v = rails()

    fpga = lp.gatemate()
    ftdi = lp.bridge()
    ldo = lp.ldo_3v3()
    buck = lp.buck_dual()
    flash = lp.spi_flash()

    # ---- FPGA power. 0009: economy mode, core at 1.0 V so the SerDes
    # supplies share it rather than forcing a second low-voltage rail.
    for name in ("VDD", "VDD_PLL", "VDD_SER", "VDD_SER_PLL"):
        for p in lp.pins_matching(fpga, rf"^{name}$"):
            p += v["+1V0"]
    # Every GPIO bank supply and the clock supply sit at 2.5 V. Nothing on
    # this board tolerates above 2.75 V (0005).
    for p in lp.pins_matching(fpga, r"^VDD_(NA|NB|EA|EB|SA|SB|WA|WB|WC)$"):
        p += v["+2V5"]
    for p in lp.pins_matching(fpga, r"^VDD_CLK$"):
        p += v["+2V5"]
    for p in lp.pins_matching(fpga, r"^GND$"):
        p += v["GND"]

    # ---- Bridge power. VCC33/VDDA from the regulator; VCCIO at 2.5 V, which
    # is the whole reason this bridge was chosen over the FT2232H (0005).
    #
    # AVDD is NOT a 3.3 V pin. The datasheet pin table gives it as "+1.0V
    # power input for PLL" with an absolute maximum of 1.4 V, and DV10 as the
    # internal LDO output to be tied to VD10 and AVDD. An earlier revision of
    # this file had AVDD on +3V3, which is a destroy-the-part error.
    for nm in ("VCC33", "VDDA"):
        for p in lp.pins_matching(ftdi, rf"^{nm}$"):
            p += v["+3V3"]
    for p in lp.pins_matching(ftdi, r"^VCCIO$"):
        p += v["+2V5"]
    for p in lp.pins_matching(ftdi, r"^GND$"):
        p += v["GND"]
    # VBUS is now a bus-presence sense input rather than the supply. The
    # board is externally powered, so the bridge has to be told when a host
    # is actually attached; wiring this to the board's own +5V would assert
    # bus presence permanently, including with no cable in the socket.
    v["USB_VBUS"] += lp.pin_named(ftdi, "VBUS")

    # Internal 1.0 V LDO: DV10 out, VD10 and AVDD in, 4.7 uF to ground, which
    # is what the datasheet asks for verbatim.
    v["+1V0_FT"] += lp.pin_named(ftdi, "DV10")
    for p in lp.pins_named(ftdi, "VD10"):
        p += v["+1V0_FT"]
    v["+1V0_FT"] += lp.pin_named(ftdi, "AVDD")
    decouple(v["+1V0_FT"], v["GND"], "4.7uF", "0805")
    for _ in lp.pins_named(ftdi, "VD10"):
        decouple(v["+1V0_FT"], v["GND"])

    # ---- USB 3.0 Micro-B receptacle. Both the SuperSpeed pairs and the
    # USB 2.0 pair land here; the bridge falls back to High Speed on a 2.0
    # host, which is also where the 500 mA ceiling applies (0009).
    #
    # Signal naming follows the USB 3.0 connector convention: on a B-type
    # receptacle SSTX is what the device transmits and SSRX is what it
    # receives, because the cable ties StdA_SSTX to the B-side SSRX.
    usb = Part("Connector", "USB3_B_Micro", ref="J1",
               value="Connfly DS1104-01",
               footprint="Connector_USB:USB3_Micro-B_Connfly_DS1104-01")
    usb["VBUS"] += v["USB_VBUS"]
    for nm in ("GND", "DRAIN", "SHIELD"):
        usb[nm] += v["GND"]
    # usb["ID"] is left open on purpose: this is a device port, not OTG.

    Net("USB_DP").connect(usb["D+"], lp.pin_named(ftdi, "DP"))
    Net("USB_DM").connect(usb["D-"], lp.pin_named(ftdi, "DM"))
    # Host transmits into the device receiver: no capacitors on this leg,
    # the host already has them.
    Net("USB_SSRX_P").connect(usb["SSRX+"], lp.pin_named(ftdi, "RIDP"))
    Net("USB_SSRX_N").connect(usb["SSRX-"], lp.pin_named(ftdi, "RIDN"))
    # AC coupling on the transmitter is mandatory, 75 nF to 265 nF per the
    # USB 3.2 specification. 100 nF, matched, as close to the connector as
    # the layout allows.
    for leg, tod in (("SSTX+", "TODP"), ("SSTX-", "TODN")):
        c = Part("Device", "C", value="100nF", footprint=FP_C["0402"])
        c[1] += lp.pin_named(ftdi, tod)
        c[2] += usb[leg]

    # ---- Wall wart input (0014, superseding 0009).
    #
    # The board is externally powered. USB now carries data only, and the
    # connector's VBUS reaches nothing but the bridge's sense pin. Everything
    # the old bus-power budget constrained -- 472 mA against a 500 mA host,
    # the 150 mA one-unit-load rule before enumeration, the 4.43 V worst case
    # -- stops applying here.
    #
    # 12 V rather than 5 V so the negative analog rail can eventually be made
    # by inversion instead of by a doubler. That part is not built yet: the
    # mezzanine still carries +5V and the module still has its charge pump.
    jack = Part("Connector", "Barrel_Jack", ref="J4",
                value="12 V 2.1 x 5.5 mm, centre positive",
                footprint="Connector_BarrelJack:BarrelJack_Horizontal")
    jack[1] += v["VIN_RAW"]
    jack[2] += v["GND"]

    # Resettable fuse first, so a downstream short does not depend on the
    # adapter's own protection being sane.
    #
    # 1812L050/30, chosen against the Littelfuse 1812L table rather than
    # named from memory. The line here used to say "1.1 A hold, 2.2 A trip"
    # in an 1812, which matches exactly one device in that series -- and it
    # is rated 6 Vdc, on a 12 V rail.
    #
    # Three things had to hold together and only this part does all three:
    #
    #   30 Vdc   covers 12 V nominal, the 19 V brick that fits the same
    #            barrel, and the TVS clamping at 29.2 V. The 24 V parts do
    #            not clear that last one.
    #   100 A    against an inrush reaching 27.9 A in the stiffest corner
    #            simulated. The 24 V and 33 V variants drop to 20 A, which
    #            is under it.
    #   0.50 A   hold, against 219 mA drawn. The obvious smaller choice,
    #            1812L035/30, derates to 0.20 A hold at 70 C -- below the
    #            board's own draw -- and would nuisance-trip in a warm
    #            enclosure. This part holds 0.33 A at 70 C and 0.29 A at 85.
    #
    # Trips at 1.00 A, and at 8 A within 0.15 s. R1max is 1.0 ohm, so the
    # worst-case drop at full load is 219 mV out of the volts of headroom
    # the buck has spare.
    fuse = Part("Device", "Polyfuse", ref="F1",
                value="1812L050/30 PPTC 0.5A hold 30V 100A",
                footprint="Fuse:Fuse_1812_4532Metric")
    fuse[1] += v["VIN_RAW"]
    prot = Net("VIN_FUSED")
    fuse[2] += prot

    # Reverse polarity by series Schottky rather than by a P-channel MOSFET.
    # At 12 V the 0.35 V drop costs about 210 mW and buys nothing back, which
    # would be the argument for the FET -- but there is a volt of headroom to
    # spare before the buck cares, and a diode has no gate to protect, no
    # Vgs rating to check against the input, and no body-diode conduction
    # path in the reversed case. The FET is the better answer on a 5 V rail;
    # here the simpler part is the better one.
    # Reverse polarity, and D1 is not doing this alone. With the adapter
    # backwards D1 blocks correctly, but its own reverse leakage is then the
    # only current in the circuit and it flows *out* of the protected node,
    # dragging it negative. What stops it is D2 conducting forward, which
    # pins the rail near one diode drop below ground: about -0.40 V,
    # against the LMR33630's -0.3 V absolute minimum on VIN and EN. Delete
    # D2 and the rail reaches -12.2 V. So the reverse case is held by the
    # TVS, not by the Schottky, and it is held marginally -- see the
    # unresolved -0.40 V against -0.3 V in the review.
    rev = Part("Device", "D_Schottky", ref="D1", value="SS34 3A 40V",
               footprint="Diode_SMD:D_SMA")
    rev["A"] += prot
    rev["K"] += v["+12V"]

    # Unidirectional TVS, 18 V rather than 15 V, and the reason is a
    # simulation result rather than a catalogue preference.
    #
    # 0014 claimed a 19 V laptop brick would make the TVS conduct and the
    # fuse trip. The first half is right and the second is not. A TVS
    # breakdown has a positive tempco -- 0.088 %/degC on this family -- so
    # conducting heats it, heating raises its breakdown, and the current
    # falls. The fault does not run away into a trip; it settles. At 19 V an
    # SMAJ15A lands at about 41 mA and 0.77 W with a junction near 117 degC,
    # indefinitely, while the board runs perfectly well beside it. That is a
    # heater, not a protection.
    #
    # And the protection was never needed for that case: the LMR33630 is a
    # 36 V part, so 19 V is simply an input it accepts. An 18 V standoff does
    # not conduct at 19 V at all, and still clamps a genuine surge at about
    # 29.2 V, inside the converter's rating. The TVS goes back to guarding
    # against transients, which is what a TVS is for.
    #
    # It must stay UNIDIRECTIONAL. See the reverse-polarity note below: the
    # bidirectional SMAJ18CA is one character away in a BOM line and removes
    # the only thing holding the rail out of the converter's negative limit.
    tvs = Part("Device", "D_TVS", ref="D2", value="SMAJ18A unidirectional",
               footprint="Diode_SMD:D_SMA")
    tvs["A1"] += v["GND"]
    tvs["A2"] += v["+12V"]
    # D3 pins the rail out of the converter's negative limit in the reversed
    # case, and it exists because the TVS alone does not quite manage it.
    # With the adapter backwards, D1 blocks and its own reverse leakage --
    # tens of microamps -- is then the only current in the circuit, flowing
    # out of this node and dragging it negative. D2 conducting forward is
    # what stops it, at about -0.40 V, against the LMR33630's -0.3 V absolute
    # minimum on VIN and EN. A hundred millivolts outside an absolute maximum
    # is not a place to leave a protection circuit.
    #
    # A Schottky in the same direction as D2's forward path clamps lower.
    # Simulated: the rail goes from -0.399 V to -0.233 V, inside the limit,
    # and it stays there at 12, 19 and 24 V reversed because the clamp sets
    # the level and the adapter voltage does not.
    #
    # The 100 degC leakage corner still reads -0.371 V, and it is left there
    # deliberately. Reaching it needs the SS34's 20 mA maximum leakage, which
    # is specified at 100 degC at rated reverse voltage -- and in this
    # scenario nothing in the circuit conducts, so nothing dissipates and the
    # junction sits at ambient. A diode can only be at 100 degC here if the
    # room is, which is outside anything this product claims. The applicable
    # figure is the 25 degC one.
    #
    # D3 also makes losing D2 survivable rather than fatal: with the TVS
    # removed the rail now settles at -0.37 V instead of -12.2 V.
    clamp = Part("Device", "D_Schottky", ref="D3", value="BAT54 negative clamp",
                 footprint="Diode_SMD:D_SOD-123")
    clamp["A"] += v["GND"]
    clamp["K"] += v["+12V"]
    decouple(v["+12V"], v["GND"], "22uF", "1210")
    decouple(v["+12V"], v["GND"], "100nF", "0603")

    # ---- 12 V to 5 V. Everything downstream of +5V is unchanged, which is
    # the point: the LTM4622, the LT3045 and the mezzanine all see the rail
    # they were designed against.
    buck5 = Part("Regulator_Switching", "LMR33630ADDA", ref="U5",
                 value="LMR33630 12V->5V 3A",
                 footprint="Package_SO:HTSSOP-8-1EP_3x3mm_P0.65mm_EP1.5x2.1mm")
    for p in lp.pins_named(buck5, "GND"):
        p += v["GND"]
    buck5["VIN"] += v["+12V"]
    # EN to VIN: the part has its own UVLO and nothing here sequences ahead
    # of it.
    buck5["EN"] += v["+12V"]
    # One Net object, reused. Net("PG_5V") called twice creates two nets and
    # SKiDL uniquifies the second name, which is how both power-good pins and
    # both of their pull-ups ended up on four separate single-node nets --
    # resistors placed with a lead floating and flags that read a permanent
    # low. Nothing in the netlist generation complains; KiCad ERC would have,
    # on import, eventually.
    pg_5v = Net("PG_5V")
    buck5["PG"] += pg_5v
    pullup(pg_5v, v["+5V"], "100k")
    # VCC is the internal rail's own bypass, datasheet value.
    decouple(buck5["VCC"], v["GND"], "1uF", "0603")
    sw = Net("SW_5V")
    buck5["SW"] += sw
    # Bootstrap across SW to BOOT, datasheet value.
    cb = Part("Device", "C", value="100nF", footprint=FP_C["0402"])
    cb[1] += sw
    cb[2] += buck5["BOOT"]
    ind = Part("Device", "L", ref="L1", value="10uH 3A shielded",
               footprint="Inductor_SMD:L_12x12mm_H8mm")
    ind[1] += sw
    ind[2] += v["+5V"]
    # FB reference is 1.0 V, so VOUT = 1.0 * (1 + Rtop/Rbot).
    #   100k / 24.9k -> 1 + 4.016 = 5.02 V
    resistor(v["+5V"], buck5["FB"], "100k 1%")
    resistor(buck5["FB"], v["GND"], "24.9k 1%")
    decouple(v["+5V"], v["GND"], "47uF", "1210")

    # ---- -6 V for the module's analog stage (decision 5, option B).
    #
    # The module used to make both analog rails itself, doubling 5 V and then
    # inverting the doubled rail. That cost 73 mA of pure conversion overhead
    # -- a third of the module -- and it is why the difference network sits at
    # 604 ohm instead of 200, forfeiting 2.1 dB: negative-rail current was
    # expensive there in a way it is not anywhere else.
    #
    # Only the NEGATIVE rail ever needed help. The output swings +/-2.83 V
    # peak and the OPA1612 reaches within 600 mV of its rails, so the positive
    # analog supply needs about 3.5 V and the mezzanine's 5 V already carries
    # it. The doubler existed only because the module made both rails
    # symmetrically from one.
    #
    # Same LMR33630 as above, wired as an inverting buck-boost: the device's
    # GND pin sits on the negative output, its SW drives the inductor back to
    # system ground, and it therefore sees VIN + |VOUT| = 18 V against a 36 V
    # rating. Reusing the part means one datasheet, one footprint and one
    # set of verified numbers rather than two.
    #
    # Feedback is referenced to the device's own ground, which is -6 V, so
    # the divider runs from system ground down to that rail and the part
    # regulates the difference: 1.0 V x (1 + 124k/24.9k) = 5.98 V.
    inv = Part("Regulator_Switching", "LMR33630ADDA", ref="U7",
               value="LMR33630 12V->-6V inverting",
               footprint="Package_SO:HTSSOP-8-1EP_3x3mm_P0.65mm_EP1.5x2.1mm")
    for p_ in lp.pins_named(inv, "GND"):
        p_ += v["-6V_A"]            # the device's ground IS the negative rail
    inv["VIN"] += v["+12V"]
    inv["EN"] += v["+12V"]
    # Same idiom, same fault, and this one mattered more: U7's GND pin *is*
    # -6V_A, so 100 k to system ground is a pull-up relative to the device and
    # the only way this flag can be read at all. It was connected to nothing.
    pg_n6v = Net("PG_N6V")
    inv["PG"] += pg_n6v
    resistor(pg_n6v, v["GND"], "100k")
    decouple(inv["VCC"], v["-6V_A"], "1uF", "0603")
    sw_n = Net("SW_N6V")
    inv["SW"] += sw_n
    cbn = Part("Device", "C", value="100nF", footprint=FP_C["0402"])
    cbn[1] += sw_n
    cbn[2] += inv["BOOT"]
    # The inductor returns to system ground, which is what makes this
    # inverting rather than a buck.
    ind_n = Part("Device", "L", ref="L2", value="10uH 3A shielded",
                 footprint="Inductor_SMD:L_12x12mm_H8mm")
    ind_n[1] += sw_n
    ind_n[2] += v["GND"]
    resistor(v["GND"], inv["FB"], "124k 1%")
    resistor(inv["FB"], v["-6V_A"], "24.9k 1%")
    decouple(v["GND"], v["-6V_A"], "47uF", "1210")
    decouple(v["GND"], v["-6V_A"], "100nF", "0603")

    # ---- 3.3 V regulator from bus voltage
    for p in ldo.pins:
        nm = str(p.name)
        if nm.startswith("IN"):
            p += v["+5V"]
        elif nm.startswith("OUT"):
            p += v["+3V3"]
        elif nm == "GND":
            p += v["GND"]
    # SET had no resistor, so the rail had no programmed voltage at all.
    # 33.2k is the E96 value nearest 33.0k and gives 3.32 V, inside the
    # FT601Q's 3.0 to 3.6 V window with room either side.
    #
    # C_SET is 100 nF here, not the 4.7 uF the helper defaults to, and the
    # reason is start-up rather than noise. The SET pin sources 100 uA and
    # PGFB is tied to IN, which disables the 2 mA fast-start circuit, so the
    # ramp is about 2.3 * R_SET * C_SET: 4.7 uF would take 359 ms. This rail
    # reaches nothing but the bridge and the flash, so the 0.8 uVRMS that
    # 4.7 uF buys is spent on two digital parts that cannot use it, while
    # the FT601Q's VCCIO comes up from the LTM4622 in microseconds and would
    # sit 355 ms ahead of its own VCC33. 100 nF brings the ramp to about
    # 7.6 ms and closes that gap. Every rail that does reach the signal keeps
    # the 4.7 uF and the specification it pays for.
    lp.lt3045_housekeeping(
        ldo, v["+5V"], v["GND"], "33.2k 0.1%",
        lambda a, b, val: resistor(a, b, val),
        lambda a, b, val: decouple(a, b, val, "0805"),
        c_set="100nF")
    decouple(v["+5V"], v["GND"], "10uF", "0805")
    decouple(v["+3V3"], v["GND"], "10uF", "0805")

    # ---- LTM4622: one package, both switching rails (0009).
    #
    # Output programming is R_FB from FB to GND against the internal 60.4k
    # from VOUT to FB, R_FB = 0.6 * 60.4k / (VOUT - 0.6):
    #     2.5 V -> 19.07k, datasheet table value 19.1k
    #     1.0 V -> 90.6k,  datasheet table value 90.9k
    # Channel 1 is the 2.5 V rail and channel 2 the 1.0 V rail, matching the
    # table in 0009.
    for p in lp.pins_named(buck, "VIN1") + lp.pins_named(buck, "VIN2"):
        p += v["+5V"]
    for p in lp.pins_named(buck, "GND"):
        p += v["GND"]
    for p in lp.pins_named(buck, "VOUT1"):
        p += v["+2V5"]
    for p in lp.pins_named(buck, "VOUT2"):
        p += v["+1V0"]
    #
    # Failure modes, because these two resistors are the only thing setting
    # either rail and one of them sits in front of a 1.20 V absolute maximum.
    #
    # An OPEN R_FB is safe, and it is worth writing down because the intuition
    # runs the other way. With no path to ground the FB node is pulled to VOUT
    # through the internal 60.4k, the error amplifier sees FB above its 0.6 V
    # reference, and it reduces duty until VOUT is about 0.6 V. A cracked
    # resistor browns the rail out; it does not raise it.
    #
    # What is genuinely dangerous is fitting the WRONG value, and the worst
    # single assembly error on this board is swapping these two: 19.1k on FB2
    # puts 2.5 V onto +1V0, which reaches VDD x28, VDD_PLL, VDD_SER x2 and
    # VDD_SER_PLL against a 1.20 V absolute maximum, and kills the FPGA on
    # first power-up. The reverse swap only browns out +2V5, which is safe.
    #
    # So the core rail's resistor is deliberately a DIFFERENT PACKAGE. A 0603
    # part cannot be placed on an 0402 land, which makes the fatal direction
    # of the swap a physical impossibility rather than a process control.
    resistor(lp.pin_named(buck, "FB1"), v["GND"], "19.1k 1%")
    resistor(lp.pin_named(buck, "FB2"), v["GND"], "90.9k 1%",
             footprint="Resistor_SMD:R_0603_1608Metric")
    #
    # E-4, recorded rather than fixed. DS1001 gives two operating windows on
    # this one net: VDD and VDD_PLL want 0.95-1.05 V, while VDD_SER and
    # VDD_SER_PLL want 1.00-1.15 V. The LTM4622 delivers 0.979/0.999/1.019 V
    # across its own feedback tolerance and a 1 % resistor, so VDD_SER sits
    # below its minimum at nominal. The two windows overlap only between 1.00
    # and 1.05 V, which is narrower than the regulator's own spread, so no
    # resistor value satisfies both parts with margin. VDD is the one with 28
    # balls and a real design depending on it; the SerDes is unused and every
    # one of its signal balls is open. The rail is therefore centred on VDD
    # and VDD_SER is knowingly out of specification on a block that never
    # runs. Revisit if the SerDes is ever used -- it needs its own rail.
    #
    # E-5, recorded. The same arithmetic on channel 1 gives 2.563 V worst
    # case against a 2.75 V absolute maximum and a 2.7 V operating maximum:
    # 187 mV to destruction, 137 mV to out of specification, before any
    # load-step overshoot. Dominated by the LTM4622's own +/-1.33 % feedback
    # tolerance rather than by the resistor, so a tighter resistor buys only
    # about 18 mV and is not fitted. This rail has no room for a second
    # tolerance mistake on top of it.
    # 2.5 V output wants 1.5 MHz rather than the default 1 MHz to keep the
    # inductor ripple sensible; the datasheet gives R_FSET = 649k for that.
    # FREQ is shared, and 1.5 MHz is harmless for the 1.0 V channel: 5 V in
    # to 1.0 V out is a 133 ns on-time against a 20 ns minimum.
    resistor(lp.pin_named(buck, "FREQ"), v["GND"], "649k 1%")
    # Forced continuous mode. Burst Mode is the efficient choice at light
    # load and the wrong one next to an audio board.
    v["GND"] += lp.pin_named(buck, "SYNC/MODE")
    # Soft start. 1.4 uA into 10 nF reaches the 0.6 V reference in about
    # 4.3 ms, which is the datasheet's own tSTART measurement condition.
    for nm in ("TRACK/SS1", "TRACK/SS2"):
        c = Part("Device", "C", value="10nF", footprint=FP_C["0402"])
        c[1] += lp.pin_named(buck, nm)
        c[2] += v["GND"]
    # Open-drain power good, one pull-up each. Test points, not logic.
    for nm in ("PGOOD1", "PGOOD2"):
        n = Net(f"PG_{nm[-1]}")
        n += lp.pin_named(buck, nm)
        pullup(n, v["+2V5"], "100k")
    decouple(v["+5V"], v["GND"], "4.7uF", "0805")
    decouple(v["+5V"], v["GND"], "4.7uF", "0805")
    decouple(v["+2V5"], v["GND"], "22uF", "0805")
    decouple(v["+1V0"], v["GND"], "22uF", "0805")

    # ---- Both rails run unconditionally (0014).
    #
    # 0009 gated the 1.0 V core rail off the bridge's WAKEUP_N through an
    # inverting NMOS, so that the board stayed inside one unit load until USB
    # activity released it. 0014 retired that rule with bus power, and this
    # is where it actually comes out.
    #
    # Leaving it in place was not merely stale, it was fatal. WAKEUP_N is
    # high in suspend and its pull-up holds it high whenever the bridge is
    # not driving it -- which, on an externally powered board with no host
    # attached, is always. Gate high turns the NMOS on, RUN2 is pulled down,
    # and the FPGA core rail never comes up. The board would have been dead
    # without a USB host it no longer needs for power.
    #
    # The transient was worse than the static reading. CORE_RUN reaches its
    # +5V pull-up before Q1's gate crosses threshold, so channel 2 began its
    # soft start into a 1.2 ms window and was killed mid-ramp: +1V0 rose to
    # about 319 mV and collapsed, on every power-up, whether or not a host
    # was present. Found by hardware/sim/power_input_transient.py, which is
    # the class of fault a netlist review cannot see because every net is
    # connected exactly as intended.
    v["+5V"] += lp.pin_named(buck, "RUN1")
    v["+5V"] += lp.pin_named(buck, "RUN2")

    # ---- Bridge housekeeping, all of it from the FT601Q pin table.
    # RREF: "connect 1.6K 1% resistor to ground, provides reference voltage
    # to USB2 PHY". Not a value to round.
    rref = Net("FT_RREF")
    rref += lp.pin_named(ftdi, "RREF")
    resistor(rref, v["GND"], "1.6k 1%")

    # Crystal: 30 MHz +/-20 ppm, 18 pF load, 50 ohm ESR. An oscillator will
    # not do; the datasheet says tying XO to ground does not work.
    # Load capacitors follow C = 2 * (CL - Cstray). Cstray is the 2.0 pF
    # maximum pin capacitance from the datasheet plus roughly 2 pF of pad
    # and track, so C = 2 * (18 - 4) = 28 pF, and 27 pF is the standard
    # value next to it.
    xtal = Part("Device", "Crystal_GND24", ref="Y1",
                value="ABM8G-30.000MHZ-18-D2Y-T",
                footprint="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm")
    xi = Net("FT_XI")
    xo = Net("FT_XO")
    xi += lp.pin_named(ftdi, "XI"), xtal[1]
    xo += lp.pin_named(ftdi, "XO"), xtal[3]
    for p in xtal.pins:
        if str(p.name) == "G":
            p += v["GND"]
    for n in (xi, xo):
        c = Part("Device", "C", value="27pF C0G", footprint=FP_C["0402"])
        c[1] += n
        c[2] += v["GND"]

    # RESET_N: chip reset, active low, held off by a pull-up. It goes to
    # VCCIO and not to the 3.3 V rail, because the I/O absolute maximum is
    # VCCIO + 0.5 V and VCCIO here is 2.5 V.
    ft_reset = Net("FT_RESET_N")
    ft_reset += lp.pin_named(ftdi, "~{RESET}")
    pullup(ft_reset, v["+2V5"])

    # SIWU_N is reserved on this part and the datasheet asks for an external
    # pull-up in normal operation. It is also on the FIFO bus, so the FPGA
    # can drive it; the resistor defines it before the FPGA is configured.
    # GPIO[1:0] are the power-on FIFO mode straps: 00 selects 245
    # synchronous FIFO mode, which is the mode this design uses.
    for nm in ("GPIO0", "GPIO1"):
        n = Net(f"FT_{nm}")
        n += lp.pin_named(ftdi, nm)
        resistor(n, v["GND"], "10k")
    # "Reserved" (pin 19) is left open: the datasheet says do not connect.

    # ---- Bank allocation. Bridge bus and element lines get separate banks:
    # same voltage, but no shared bank supply (hardware/README.md).
    bus_pool = (lp.bank_ios(fpga, "NA") + lp.bank_ios(fpga, "NB")
                + lp.bank_ios(fpga, "EA"))
    elem_pool = lp.bank_ios(fpga, "SA") + lp.bank_ios(fpga, "WB")
    ctrl_pool = lp.bank_ios(fpga, "WC")

    # ---- Bridge FIFO bus: 42 signals plus the clock
    for i in range(N_DATA):
        n = Net(f"FT_DATA{i}")
        n += lp.pin_named(ftdi, f"DATA_{i}")
        n += bus_pool.pop(0)
    for i in range(4):
        n = Net(f"FT_BE{i}")
        n += lp.pin_named(ftdi, f"BE_{i}")
        n += bus_pool.pop(0)
    for sig in ("RXF", "TXE", "RD", "WR", "OE", "SIWU"):
        n = Net(f"FT_{sig}_N")
        n += lp.pin_named(ftdi, "~{%s}" % sig)
        n += bus_pool.pop(0)
        if sig == "SIWU":
            pullup(n, v["+2V5"])

    # Clock-capable pins only. A clock on an ordinary pin is not an error:
    # the packer silently routes it through the fabric and adds the jitter
    # the bypass path exists to avoid (hdl/constraints/README.md).
    ft_clk = Net("FT_CLK")
    ft_clk += lp.pin_named(ftdi, "CLK")
    ft_clk += lp.pin_named(fpga, lp.CLOCK_PINS[0])

    mclk = Net("MCLK")
    mclk += lp.pin_named(fpga, lp.CLOCK_PINS[1])

    # ---- Mezzanine header: 32 element lines each beside a ground, MCLK back
    # from the module, two oscillator enables, mute, two ID straps, and power
    # (hardware/interface.md).
    # 32 element lines each beside a ground is 64 pins before control and
    # power, so the header is 2x40. The 8 spare pins become extra ground and
    # a second supply pin rather than being left open.
    mez = Part("Connector_Generic", "Conn_02x40_Odd_Even",
               ref="J2", value="Mezzanine 2x40",
               footprint="Connector_PinHeader_1.27mm:PinHeader_2x40_P1.27mm_Vertical")
    mez_pins = list(mez.pins)
    idx = 0

    def next_mez():
        nonlocal idx
        p = mez_pins[idx]
        idx += 1
        return p

    elem_nets = []
    for i in range(N_ELEM):
        n = Net(f"ELEM{i}")
        n += elem_pool.pop(0)
        n += next_mez()
        v["GND"] += next_mez()
        elem_nets.append(n)

    mclk += next_mez()
    ctrl_nets = {}
    for sig in ("OSC_EN_441", "OSC_EN_48", "MUTE_N", "ID0", "ID1"):
        n = Net(sig)
        n += ctrl_pool.pop(0)
        n += next_mez()
        ctrl_nets[sig] = n
    # Two pins for the negative analog rail, taken from the ground
    # allocation. 37 returns for 28 switching lines is generous; 35 still is.
    # They are adjacent so the pair can be routed together and so a
    # half-inserted connector cannot present one without the other.
    for _ in range(2):
        v["-6V_A"] += next_mez()
    # Remaining pins: supply and ground, alternating.
    while idx < len(mez_pins):
        rail = v["+5V"] if idx % 2 == 0 else v["GND"]
        rail += next_mez()

    # ID pins pulled low here so "no module fitted" is detectable.
    #
    # OSC_EN_* are pulled low for a different and harder reason. They leave
    # this board, cross the mezzanine and drive the A port of the module's
    # 74AVC4T245, which has no bus hold and whose datasheet requires every
    # unused data input to be held at VCCI or GND. Before the FPGA is
    # configured its pins are high impedance, so without these the translator
    # input floats, its output drives whatever that resolves to, and both
    # CCHD-957 oscillators can turn on into the module's single shared
    # OSC_RAW net. Sharing that net is only legal while exactly one part is
    # enabled -- interface.md states the rule and nothing enforced it.
    #
    # The module also fits 100k pull-downs on the translated side, but those
    # alone are not sufficient: they are downstream of a push-pull output that
    # can source milliamps, so they only decide the case where the translator
    # is itself high impedance. The floating *input* has to be fixed here.
    # MUTE_N needs no pull here because the module grounds it through 100k on
    # its own side, where it is a direct input to the charge pump's enables
    # rather than a translator input.
    for sig in ("ID0", "ID1", "OSC_EN_441", "OSC_EN_48"):
        r = Part("Device", "R", value="10k",
                 footprint="Resistor_SMD:R_0402_1005Metric")
        r[1] += ctrl_nets[sig]
        r[2] += v["GND"]

    # ---- Unused SerDes clock inputs, tied rather than left open.
    #
    # DS1001 section 2.10 lists SER_CLK and SER_CLK_N among the pins VDD_CLK
    # supplies, and VDD_CLK is powered here at 2.5 V. A floating input on a
    # powered receiver settles near mid-rail, where both halves of the input
    # stage conduct, and a differential receiver left open can oscillate as
    # well. Neither current is characterised in the datasheet -- Table 4.5's
    # 158 uA "at GPIO input at transition point" is the GPIO figure, not this
    # receiver's. The SerDes is unused and every one of its signal balls is
    # open, so both clock inputs go to ground: a defined level costs two
    # shorts and removes an unbounded, unmeasured current.
    #
    # This is the class of pin assert_below_abs_max cannot help with. It
    # checks what drives a protected pin, and nothing drives these at all.
    for nm in ("SER_CLK", "SER_CLK_N"):
        ser_clk_pin = lp.pin_named(fpga, nm)
        ser_clk_pin += v["GND"]

    # ---- Configuration. CFG_MD[3:0] = 0b0000 selects SPI Active mode with
    # CPOL=0 CPHA=0, so the FPGA loads itself from flash at reset (0006).
    for p in lp.pins_matching(fpga, r"^CFG_MD"):
        p += v["GND"]

    # ---- Power-on reset network.
    #
    # Datasheet section 3.2.2, "FPGA reset using the POR module":
    #   POR_EN to VDD_WA, RST_N to VDD_CLK, POR_ADJ open in normal operation
    #   with VDD_CLK in 1.8 to 2.7 V. Both rails are the same 2.5 V here.
    #
    # The datasheet also gives the dynamic release time when POR_ADJ carries
    # an R3a to VDD_CLK and a C1 to ground, against the internal 133k/75k
    # divider:
    #
    #   t = (R3a*75k)/(R3a+75k) * C1 * ln( VDD_CLK /
    #         (VDD_CLK - (0.45V/75k) * (75k + (R3a*133k)/(R3a+133k))) )
    #
    # With R3a = 47k, C1 = 2.2 uF, VDD_CLK = 2.5 V:
    #   R3a || 75k                       = 28.89k
    #   R3a || 133k                      = 34.73k
    #   effective threshold              = 6.0 uA * (75k + 34.73k) = 0.658 V
    #   ln(2.5 / (2.5 - 0.658))          = 0.3057
    #   t                                = 19.4 ms
    #
    # That is the number this board wants. 2.5 V comes up on LTM4622 channel
    # 1 in about 4.3 ms of programmed soft start, and the datasheet is
    # explicit that the reset time has to be matched to the VDD_CLK ramp.
    # 19.4 ms clears it by better than four times and is invisible against
    # USB enumeration.
    #
    # R3a stays at or below 100k, which is the datasheet's condition for the
    # static state never being a permanent reset, so the network only sets
    # the release time; it cannot hold the part in reset. C1 also does the
    # noise suppression job the datasheet suggests for this pin.
    v["+2V5"] += lp.pin_named(fpga, "POR_EN/IO_WA_A3")     # VDD_WA
    v["+2V5"] += lp.pin_named(fpga, "~{RESET}")            # RST_N to VDD_CLK
    por_adj = Net("POR_ADJ")
    por_adj += lp.pin_named(fpga, "POR_ADJ")
    resistor(por_adj, v["+2V5"], "47k 1%")                 # R3a
    decouple(por_adj, v["GND"], "2.2uF", "0805")           # C1

    # ---- Configuration flash on the dedicated second functions in bank WA.
    # Quad-I/O wiring, datasheet figure 3.7. VCC comes off VDD_WA, which is
    # 2.5 V: that is why the part has to be a wide-range one. The pull-ups
    # on CS, SIO2 and SIO3 cover the single and dual-I/O cases in figure 3.6
    # as well, where SIO2 and SIO3 are the flash's WP and RESET inputs and
    # have to sit high.
    flash["VCC"] += v["+2V5"]
    flash["GND"] += v["GND"]
    decouple(v["+2V5"], v["GND"])
    spi = [
        ("SPI_CS_N", "IO_WA_A8/~{SPI_CS}", "~{CS}", True),
        ("SPI_CLK",  "IO_WA_B8/SPI_CLK",   "SCLK", False),
        ("SPI_D0",   "IO_WA_B7/SPI_D0",    "SI/SIO0", False),
        ("SPI_D1",   "IO_WA_A7/SPI_D1",    "SO/SIO1", False),
        ("SPI_D2",   "IO_WA_B6/SPI_D2",    "~{WP}/SIO2", True),
        ("SPI_D3",   "IO_WA_A6/SPI_D3",    "~{RESET}/SIO3", True),
    ]
    for name, fpga_pin, flash_pin, needs_pullup in spi:
        n = Net(name)
        n += lp.pin_named(fpga, fpga_pin)
        n += flash[flash_pin]
        if needs_pullup:
            pullup(n, v["+2V5"])
    # SPI_FWD is left open on purpose. It only matters when several FPGAs
    # share one flash in a chain, and this board has one.

    # ---- Programming header. No programming silicon on the board: 0006
    # puts an ordinary external FTDI adapter on a header, driven by
    # openFPGALoader, which can also write the flash through the JTAG-to-SPI
    # bypass the GateMate provides.
    #
    # 2x5 on 1.27 mm, laid out so a stock Cortex-debug cable fits:
    #   1 VREF (2.5 V)   2 TMS
    #   3 GND            4 TCK
    #   5 GND            6 TDO
    #   7 CFG_DONE       8 TDI
    #   9 GND           10 CFG_FAILED_N
    # VREF is brought out so the adapter references the same 2.5 V the WA
    # bank runs at. The two configuration status pins replace the key and
    # reset positions, which a GateMate has no use for.
    jtag = Part("Connector_Generic", "Conn_02x05_Odd_Even", ref="J3",
                value="JTAG 2x5 1.27mm",
                footprint="Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical")
    jtag[1] += v["+2V5"]
    for k in (3, 5, 9):
        jtag[k] += v["GND"]
    # Figure 3.10 puts 10k pull-ups on TMS, TCK and TDI to VDD_WA.
    #
    # The three adapter-driven pins get a series resistor, and this is the one
    # protection on the board that guards against something outside it. 0006
    # specifies an ordinary external FTDI adapter, and the common ones -- the
    # FT2232H mini-module, FT232H breakouts, Cologne Chip's own programmer --
    # are fixed 3.3 V drivers. Pin 1 carries VREF at 2.5 V, but VREF is an
    # output of this board and only an input to adapters that bother to
    # implement it; a fixed 3.3 V adapter ignores it and drives 3.3 V into a
    # ball whose absolute maximum is 2.75 V. assert_below_abs_max cannot see
    # this, because the offending driver is not in the netlist.
    #
    # 1k against the 10k pull-up. UG1003, Cologne Chip's own guide for 3.3 V
    # peripherals, says a series resistor is sufficient because "the input
    # overvoltage security circuitry of the GateMate input pin will limit the
    # input voltage", and recommends 10k to 100k. 10k cannot be used here: in
    # series with the 10k pull-up that Cologne Chip's own figure 3.10 asks for
    # it would divide a driven low to 1.25 V, which is not a low. 1k holds a
    # driven low at 227 mV, bounds the clamp current at about 550 uA, and
    # keeps the RC inside JTAG speeds. That is above the 80 uA UG1003's own
    # example implies, so it is a deliberate compromise rather than vendor
    # compliance, and a 2.5 V adapter or a translator remains the correct
    # answer if this header is ever used at speed.
    #
    # TDO, CFG_DONE and CFG_FAILED_N are driven by the FPGA, not by the
    # adapter, so they are left direct.
    for pin_no, fpga_pin, name, pu in (
            (2, "JTAG_TMS/IO_WA_B4", "JTAG_TMS", True),
            (4, "JTAG_TCK/IO_WA_A5", "JTAG_TCK", True),
            (6, "JTAG_TDO/IO_WA_B3", "JTAG_TDO", False),
            (8, "JTAG_TDI/IO_WA_A4", "JTAG_TDI", True),
            (7, "IO_WA_B2/CFG_DONE", "CFG_DONE", False),
            (10, "IO_WA_A2/~{CFG_FAILED}", "CFG_FAILED_N", True)):
        n = Net(name)
        n += lp.pin_named(fpga, fpga_pin)
        if pu and name == "CFG_FAILED_N":
            # Open drain, and DS1001 3.3.3 says it "requires a pull-up
            # resistor". It is driven by the FPGA rather than by the adapter,
            # so it needs the pull-up but not the series protection.
            pullup(n, v["+2V5"])
            n += jtag[pin_no]
        elif pu:
            # Pull-up on the FPGA side of the series resistor, so the ball is
            # still held high with no adapter plugged in.
            pullup(n, v["+2V5"])
            hdr = Net(name + "_HDR")
            hdr += jtag[pin_no]
            resistor(n, hdr, "1k 1%")
        else:
            n += jtag[pin_no]

    # ---- Decoupling. One per supply ball is the floor, not the design.
    for _ in lp.pins_matching(fpga, r"^VDD_(NA|NB|EA|EB|SA|SB|WA|WB|WC)$"):
        decouple(v["+2V5"], v["GND"])
    for _ in lp.pins_matching(fpga, r"^VDD$"):
        decouple(v["+1V0"], v["GND"])
    for _ in lp.pins_matching(ftdi, r"^VCC33$"):
        decouple(v["+3V3"], v["GND"])
    for _ in lp.pins_matching(ftdi, r"^VCCIO$"):
        decouple(v["+2V5"], v["GND"])

    # ---- The one invariant this board cannot violate. Asserted, not
    # reviewed: nothing reaching an FPGA signal pin or the header may be
    # able to carry more than 2.75 V. The header is allowed +5V because
    # interface.md hands it to the module deliberately.
    import builtins
    lp.assert_below_abs_max(
        builtins.default_circuit,
        # +12V, VIN_RAW and VIN_FUSED are declared because the check is blind
        # to any rail it is not told about: an undeclared rail reaching a
        # protected pin passes silently. That is how a new supply enters a
        # design unguarded.
        # -6V_A is declared for the same reason +12V is: the check is
        # membership-based, so a rail it has not been told about reaches a
        # protected pin silently. A negative rail on a GateMate ball is as
        # fatal as a high one, and this check is the only thing looking.
        hv_rails={"+3V3", "+5V", "USB_VBUS", "VIN_RAW", "VIN_FUSED", "+12V",
                  "-6V_A"},
        protected={fpga: set(), mez: {"+5V", "-6V_A"}})

    return fpga, ftdi, elem_nets


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(OUT)
    build()
    generate_netlist(file_=str(OUT / "lyrebird-main.net"))
    generate_xml(file_=str(OUT / "lyrebird-main.xml"))
    # SKiDL also exposes generate_pcb and generate_schematic. Both were tried
    # on this design and neither completed: they spawned several processes and
    # produced no file after minutes on a 324-ball part. Import the netlist
    # into KiCad instead. See README.md.
    print(f"netlist -> {OUT / 'lyrebird-main.net'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

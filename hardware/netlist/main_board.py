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
        "0805": "Capacitor_SMD:C_0805_2012Metric"}
FP_R = "Resistor_SMD:R_0402_1005Metric"


def rails():
    # +1V0_FT is the FT601Q's own internal LDO output. It is a separate net
    # from the board's +1V0: the datasheet says that rail is "not to be used
    # for external devices", and it feeds only VD10 and AVDD on the bridge.
    n = {k: Net(k) for k in ("GND", "USB_VBUS", "+5V", "+3V3", "+2V5",
                             "+1V0", "+1V0_FT")}
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
    v["+5V"] += lp.pin_named(ftdi, "VBUS")

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

    # ---- Ferrite at the bus input (0009: the 5 V rail is ferrite only).
    # FTDI's bus-powered reference puts one in series with VBUS to keep the
    # board's own noise off the cable. 220 ohm at 100 MHz, 1.4 A, 100 mohm,
    # against the 380 mA the budget in 0009 actually draws.
    fb = Part("Device", "FerriteBead", ref="FB1",
              value="BLM18PG221SN1D 220R@100MHz",
              footprint="Inductor_SMD:L_0603_1608Metric")
    fb[1] += v["USB_VBUS"]
    fb[2] += v["+5V"]

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
    lp.lt3045_housekeeping(
        ldo, v["+5V"], v["GND"], "33.2k 0.1%",
        lambda a, b, val: resistor(a, b, val),
        lambda a, b, val: decouple(a, b, val, "0805"))
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
    resistor(lp.pin_named(buck, "FB1"), v["GND"], "19.1k 1%")
    resistor(lp.pin_named(buck, "FB2"), v["GND"], "90.9k 1%")
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

    # ---- Enumeration gating of the core rail (0009).
    #
    # RUN1 is tied on: channel 1 is the 2.5 V rail and it feeds the bridge's
    # own VCCIO. Gating it would take away the I/O supply for the pin that
    # does the gating, so only the 1.0 V core rail is switched.
    #
    # WAKEUP_N is low while USB is active and high in suspend, so it needs
    # inverting to drive RUN2, which enables above 1.27 V. A logic-level
    # NMOS does that: gate high in suspend pulls RUN2 down, gate low in
    # normal operation lets the pull-up take RUN2 to the bus rail.
    #
    # The honest caveat, and the reason the open item in 0009 stays open:
    # WAKEUP_N tracks "bus not suspended", not "enumeration complete". It
    # releases the core on bus activity, which is earlier than the one unit
    # load rule strictly wants. Verify against silicon before trusting it.
    v["+5V"] += lp.pin_named(buck, "RUN1")
    wake = Net("FT_WAKEUP_N")
    wake += lp.pin_named(ftdi, "~{WAKEUP}")
    pullup(wake, v["+2V5"], "100k")     # holds the core off if VCCIO is absent
    core_run = Net("CORE_RUN")
    core_run += lp.pin_named(buck, "RUN2")
    pullup(core_run, v["+5V"], "100k")
    q = Part("Transistor_FET", "BSS138", ref="Q1", value="BSS138",
             footprint="Package_TO_SOT_SMD:SOT-23")
    q["G"] += wake
    q["D"] += core_run
    q["S"] += v["GND"]

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
    # Remaining pins: supply and ground, alternating.
    while idx < len(mez_pins):
        rail = v["+5V"] if idx % 2 == 0 else v["GND"]
        rail += next_mez()

    # ID pins pulled low here so "no module fitted" is detectable
    for sig in ("ID0", "ID1"):
        r = Part("Device", "R", value="10k",
                 footprint="Resistor_SMD:R_0402_1005Metric")
        r[1] += ctrl_nets[sig]
        r[2] += v["GND"]

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
    for pin_no, fpga_pin, name, pu in (
            (2, "JTAG_TMS/IO_WA_B4", "JTAG_TMS", True),
            (4, "JTAG_TCK/IO_WA_A5", "JTAG_TCK", True),
            (6, "JTAG_TDO/IO_WA_B3", "JTAG_TDO", False),
            (8, "JTAG_TDI/IO_WA_A4", "JTAG_TDI", True),
            (7, "IO_WA_B2/CFG_DONE", "CFG_DONE", False),
            (10, "IO_WA_A2/~{CFG_FAILED}", "CFG_FAILED_N", False)):
        n = Net(name)
        n += lp.pin_named(fpga, fpga_pin)
        n += jtag[pin_no]
        if pu:
            pullup(n, v["+2V5"])

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
        hv_rails={"+3V3", "+5V", "USB_VBUS"},
        protected={fpga: set(), mez: {"+5V"}})

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

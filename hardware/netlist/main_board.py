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


def rails():
    n = {k: Net(k) for k in ("GND", "+5V", "+3V3", "+2V5", "+1V0")}
    n["GND"].drive = 7
    return n


def decouple(net_hi, net_gnd, value="100nF"):
    c = Part("Device", "C", value=value,
             footprint="Capacitor_SMD:C_0402_1005Metric")
    c[1] += net_hi
    c[2] += net_gnd
    return c


def build():
    lp.setup()
    v = rails()

    fpga = lp.gatemate()
    ftdi = lp.bridge()
    ldo = lp.ldo_3v3()

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
    for nm in ("VCC33", "VDDA", "AVDD"):
        for p in lp.pins_matching(ftdi, rf"^{nm}$"):
            p += v["+3V3"]
    for p in lp.pins_matching(ftdi, r"^VCCIO$"):
        p += v["+2V5"]
    for p in lp.pins_matching(ftdi, r"^GND$"):
        p += v["GND"]
    v["+5V"] += lp.pin_named(ftdi, "VBUS")

    # ---- 3.3 V regulator from bus voltage
    for p in ldo.pins:
        nm = str(p.name)
        if nm.startswith("IN"):
            p += v["+5V"]
        elif nm.startswith("OUT"):
            p += v["+3V3"]
        elif nm == "GND":
            p += v["GND"]

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

    # ---- Decoupling. One per supply ball is the floor, not the design.
    for _ in lp.pins_matching(fpga, r"^VDD_(NA|NB|EA|EB|SA|SB|WA|WB|WC)$"):
        decouple(v["+2V5"], v["GND"])
    for _ in lp.pins_matching(fpga, r"^VDD$"):
        decouple(v["+1V0"], v["GND"])
    for _ in lp.pins_matching(ftdi, r"^VCC33$"):
        decouple(v["+3V3"], v["GND"])
    for _ in lp.pins_matching(ftdi, r"^VCCIO$"):
        decouple(v["+2V5"], v["GND"])

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

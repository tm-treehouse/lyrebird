"""Shared part definitions and helpers for the Lyrebird boards.

Schematic as code. SKiDL reads the stock KiCad 10 symbol libraries, which
already carry the GateMate ball map and bank membership, so pin assignment
here is against real ball numbers rather than invented ones.

Nothing in this file chooses a design. The decisions live in docs/decisions
and this only expresses them.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from skidl import KICAD10, Part, TEMPLATE, lib_search_paths, set_default_tool

KICAD_SYMBOLS = Path(os.environ.get(
    "KICAD10_SYMBOL_DIR",
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"))


def setup() -> None:
    set_default_tool(KICAD10)
    p = str(KICAD_SYMBOLS)
    if p not in lib_search_paths[KICAD10]:
        lib_search_paths[KICAD10].append(p)


# ---------------------------------------------------------------- parts
def gatemate() -> Part:
    """CCGM1A1, BGA324. Eight units: SerDes, WA, N, E, S, WB/WC, power, config."""
    return Part("FPGA_CologneChip_GateMate", "CCGM1A1",
                ref="U1", value="CCGM1A1-BGA324")


def bridge() -> Part:
    """FT601Q, QFN-76, USB 3.0 to 32-bit FIFO."""
    return Part("Interface_USB", "FT601Q", ref="U2", value="FT601Q")


def ldo_3v3() -> Part:
    """LT3045, ultralow noise. 0009: the bridge rail uses a regulator rather
    than a switcher because it feeds the USB PHY analog supply."""
    return Part("Regulator_Linear", "LT3045xDD", ref="U3", value="LT3045")


def translator() -> Part:
    """74AVC4T245, dual-supply, two independent 2-bit banks. 0012."""
    return Part("Logic_LevelTranslator", "SN74AVC4T245PW",
                ref="U5", value="74AVC4T245")


# ------------------------------------------------------------- pin lookup
def pins_matching(part: Part, pattern: str) -> list:
    """Every pin whose name matches, in ball order. Names carry the bank,
    e.g. IO_NB_A3 is bank NB, and CLK0/IO_SB_A8 is a clock-capable pin."""
    rx = re.compile(pattern)
    return [p for p in part.pins if rx.search(str(p.name))]


def pin_named(part: Part, name: str):
    """Exactly one pin by full name. Raises if ambiguous, which is the point."""
    hits = [p for p in part.pins if str(p.name) == name]
    if len(hits) != 1:
        raise KeyError(f"{name!r} matched {len(hits)} pins")
    return hits[0]


def bank_ios(part: Part, bank: str) -> list:
    """Free I/O in one GPIO bank, excluding pins with a dedicated second
    function (JTAG, SPI, CLK). Those are claimed explicitly."""
    out = []
    for p in pins_matching(part, rf"IO_{bank}_[AB]\d"):
        n = str(p.name)
        if any(k in n for k in ("JTAG", "SPI", "CLK")):
            continue
        out.append(p)
    return out


CLOCK_PINS = ["CLK0/IO_SB_A8", "CLK1/IO_SB_A7", "CLK2/IO_SB_A6", "CLK3/IO_SB_A5"]

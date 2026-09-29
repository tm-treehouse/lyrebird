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

from skidl import KICAD10, Part, Pin, TEMPLATE, lib_search_paths, set_default_tool

KICAD_SYMBOLS = Path(os.environ.get(
    "KICAD10_SYMBOL_DIR",
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"))

# Project library for parts the stock KiCad 10 libraries do not carry.
PROJECT_SYMBOLS = Path(__file__).resolve().parent.parent / "symbols"


def setup() -> None:
    set_default_tool(KICAD10)
    for d in (KICAD_SYMBOLS, PROJECT_SYMBOLS):
        p = str(d)
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


def buck_dual() -> Part:
    """LTM4622, LGA-25. Dual 2.5 A step-down module, one package for the
    2.5 V I/O rail and the 1.0 V core rail (0009). Not in the stock KiCad
    libraries, so the symbol lives in hardware/symbols/lyrebird.kicad_sym
    with the ball map from the datasheet PIN FUNCTIONS table.

    Orderable: LTM4622IV#PBF (LGA), -40 to 125 C."""
    return Part("lyrebird", "LTM4622", ref="U4", value="LTM4622IV#PBF",
                footprint="lyrebird:Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm")


def spi_flash() -> Part:
    """MX25R6435F, 64 Mbit quad SPI NOR, 1.65-3.6 V. Configuration store for
    SPI Active mode (0006). The wide supply range is what lets it sit on
    VDD_WA at 2.5 V; the common 2.7-3.6 V parts cannot.

    Orderable: MX25R6435FM2IH0 (SOP-8, industrial)."""
    return Part("lyrebird", "MX25R6435F", ref="U6", value="MX25R6435F 64Mb",
                footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")


def lt3045_housekeeping(part, vin, gnd, vset_ohms, make_r, make_c,
                        c_set="4.7uF", en=None) -> None:
    """Wire the LT3045 pins that are not IN, OUT or GND, per its datasheet
    PIN FUNCTIONS section. Without these the part has no programmed output
    voltage and a floating enable.

      SET   100 uA out through R_SET to ground sets VOUT = 100uA * R_SET.
            The 4.7 uF bypass is what buys the 0.8 uVRMS quoted in 0009;
            the datasheet's noise specification is taken with it fitted.

            It also sets the ramp, and that is the trap. The SET pin sources
            100 uA, so the output follows C_SET charging at that current and
            t_ss is about 2.3 * R_SET * C_SET. Tying PGFB to IN below
            disables the 2 mA fast start-up circuit that exists precisely to
            charge this capacitor, so the two choices multiply: 33.2k with
            4.7 uF is 359 ms, and 49.9k with 4.7 uF is 539 ms. Each choice is
            correct on its own and quoted from the datasheet; together they
            are a supply that arrives a third of a second late.

            Pass a smaller c_set on any rail where the noise specification is
            not being bought. A rail that only feeds digital parts gains
            nothing from 4.7 uF and pays the whole ramp for it.
      EN/UV "If unused, tie EN/UV to IN. Do not float the EN/UV pin."
      ILIM  "If the programmable current limit functionality is not needed,
            tie ILIM to GND."
      PGFB  "Tie PGFB to IN if power good and fast start-up functionalities
            are not needed."
      PG    open-collector flag, unused, left open.
    """
    set_pin = pin_named(part, "SET")
    make_r(set_pin, gnd, vset_ohms)
    make_c(set_pin, gnd, c_set)
    # EN/UV goes to IN unless a caller wants to gate the rail, which the
    # analog rails do: MUTE_N holds them off until the element lines carry a
    # defined code. PGFB always goes to IN -- it selects fast start-up, not
    # enable, and the two are separate pins for a reason.
    en_net = vin if en is None else en
    en_net += pin_named(part, "EN/UV")
    vin += pin_named(part, "PGFB")
    gnd += pin_named(part, "ILIM")


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


def pins_named(part: Part, name: str) -> list:
    """Every pin with this exact name. For parts that ship one signal on
    several balls, e.g. LTM4622 VOUT1 on D1 and E1. Raises if none match,
    so a typo is an error rather than a silently open pin."""
    hits = [p for p in part.pins if str(p.name) == name]
    if not hits:
        raise KeyError(f"{name!r} matched no pins")
    return hits


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


# ------------------------------------------------- absolute maximum check
# GateMate GPIO are LVCMOS to 2.5 V with an absolute maximum VDDIO of 2.75 V,
# and the mezzanine carries 2.5 V logic by contract (0005, 0012,
# hardware/interface.md). Both boards have shipped a bug where a 3.3 V module
# signal reached a header pin, so the rule is asserted here rather than
# reviewed.
ABS_MAX_V = 2.75

# The core is a second, much lower, absolute maximum and the check above never
# saw it: it compares against 2.75 V and skips supply pins by construction, so
# +2V5 landing on a VDD ball -- through a resistor or as a short -- passed
# silently. That is not hypothetical. The LTM4622 land pattern was found with
# its two axes transposed, which put +2V5 and +5V directly onto VOUT2, the rail
# that feeds these 32 balls.
CORE_ABS_MAX_V = 1.20

# Pin names on the GateMate that sit on the core rail rather than on I/O.
CORE_SUPPLY_NAMES = ("VDD", "VDD_PLL", "VDD_SER", "VDD_SER_PLL")


def assert_symbol_footprints(circuit, justified=None) -> None:
    """Fail the build if a part overrides a symbol that names its own land.

    Two faults of exactly this shape reached the netlists. An LT3045, an
    11-pin part, was given a 12-pad DFN meant for the LT3094. Both LMR33630s
    were given an HTSSOP-8 at 3 x 3 mm and 0.65 mm pitch when the package is
    HSOP-8 at 3.9 x 4.9 mm and 1.27 mm -- a different part entirely, and
    unbuildable. In both cases the KiCad symbol already carried the right
    answer in its own footprint field and an explicit override replaced it.

    The rule only applies where the symbol names a SPECIFIC footprint.
    Generic symbols -- R, C, D, L, connectors -- name none, because choosing
    the package is the designer's job there, so they are skipped rather than
    flagged. That is what makes this checkable at all: the parts with a
    default are precisely the parts whose package is not a choice.
    """
    # An override may be right, because a symbol can be wrong. It has to say
    # why: justified maps a reference to the reason, and an unexplained
    # override fails the build.
    justified = justified or {}
    cache: dict[tuple, str] = {}
    bad = []
    for part in circuit.parts:
        try:
            lib = str(part.lib.filename).split("/")[-1].replace(".kicad_sym", "")
            name = str(part.name)
        except Exception:                              # noqa: BLE001
            continue
        key = (lib, name)
        if key not in cache:
            try:
                cache[key] = str(getattr(Part(lib, name, dest=None),
                                         "footprint", "") or "")
            except Exception:                          # noqa: BLE001
                cache[key] = ""
        default, mine = cache[key], str(getattr(part, "footprint", "") or "")
        if default and mine and default != mine and part.ref not in justified:
            bad.append(f"  {part.ref} ({part.value}): symbol names\n"
                       f"      {default}\n    but the netlist assigns\n"
                       f"      {mine}")
    if bad:
        raise AssertionError(
            f"{len(bad)} part(s) override a symbol that names its own "
            f"footprint:\n" + "\n".join(sorted(bad))
            + "\n  Either take the symbol's footprint or say in a comment why "
              "it is wrong.")


def assert_core_rail(circuit, protected, core_rails, tolerated=()):
    """Fail the build if anything but a declared core rail reaches a core ball.

    The signal check asks "is this net above 2.75 V". This asks the opposite
    question, because for a supply the interesting fault is not how high the
    rail is but whether it is the *right* rail: a core ball may touch the core
    rail and ground and nothing else. Any other net there, whatever its
    voltage, is a fault -- and every other rail on this board is above the
    1.20 V maximum.
    """
    groups = _net_groups(circuit)
    pin_group = {}
    for i, (_, pins) in enumerate(groups):
        for p in pins:
            pin_group[id(p)] = i
    allowed = set(core_rails) | {"GND"} | set(tolerated)
    bad = []
    core_groups = set()
    for part in protected:
        for p in part.pins:
            if str(p.name) not in CORE_SUPPLY_NAMES:
                continue
            g = pin_group.get(id(p))
            if g is None:
                continue
            core_groups.add(g)
            # ONLY allowed names, not "at least one". A short does not replace
            # the net, it merges it, so the core rail's own name is still
            # there -- asking whether an allowed name is present passes every
            # short there is. The first version of this check did exactly
            # that and caught nothing.
            extra = groups[g][0] - allowed
            if extra:
                bad.append(f"  {part.ref}.{p.num} ({p.name}) on a net that "
                           f"also carries {'/'.join(sorted(extra))}")

    # A resistor from another rail to the core does not merge the nets, so the
    # test above cannot see it. Walk two-terminal parts with one leg on a core
    # net: whatever is on the other leg is tied to a 1.20 V maximum through an
    # impedance, which for a supply pin is not a defence.
    for part in circuit.parts:
        pins = list(part.pins)
        if len(pins) != 2:
            continue
        gs = [pin_group.get(id(x)) for x in pins]
        if None in gs:
            continue
        for a, b in (gs, gs[::-1]):
            if a in core_groups and b not in core_groups:
                other = groups[b][0] - allowed
                if other:
                    bad.append(f"  {part.ref} bridges the core rail to "
                               f"{'/'.join(sorted(other))}")
    if bad:
        raise AssertionError(
            f"nets other than the core rail reach {len(bad)} core supply "
            f"pin(s), whose absolute maximum is {CORE_ABS_MAX_V} V:\n"
            + "\n".join(sorted(bad)))

# Pin types that can drive a net up to their part's supply voltage. An input
# cannot: the 28 element lines legitimately land on 3.3 V register inputs,
# and that is a threshold question, not a damage one. Neither can an
# open-drain pin, which only ever pulls down; whatever it is pulled up to is
# a separate resistor and is caught as one. A regulator output defines a new
# domain rather than propagating its input's, so PWROUT is excluded too and
# the declared rail list is the authority on supply voltages.
_DRIVING = (Pin.types.OUTPUT, Pin.types.BIDIR, Pin.types.TRISTATE)

# Supply pins by name. Large symbols repeat a supply across several balls
# and mark only the first PWRIN, the rest passive, so the func alone does
# not identify them.
_SUPPLY_NAME = re.compile(r"^(V(DD|SS|CC|BUS|DDA|D10)|DV10|AVDD|GND)")


def _net_groups(circuit):
    """One entry per electrically distinct net: (all names, all pins)."""
    out = []
    for rep in circuit.get_nets():
        names = {str(n.name) for n in rep.get_nets()}
        out.append((names, list(rep.get_pins())))
    return out


def assert_below_abs_max(circuit, hv_rails, protected, exempt=("GND",)):
    """Fail the build if a net reaching a protected pin can carry >2.75 V.

    hv_rails   names of the rails this board declares above 2.75 V.
    protected  {part: extra net names that part is allowed to touch}. The
               mezzanine header is allowed +5V because it carries it to the
               module on purpose; the FPGA is allowed nothing but ground.
               Supply pins are skipped: the power tree chooses those rails
               explicitly and they are not signals.
    exempt     never treated as high voltage however it is reached.

    A net is high voltage if it is one of the declared rails, or if it
    carries a driving pin of a part whose every supply sits on such a rail.
    That second clause is what catches a 3.3 V clock or enable arriving at
    the header without passing through the translator.
    """
    exempt = set(exempt)
    hv_rails = set(hv_rails)
    groups = _net_groups(circuit)
    pin_group = {}
    for i, (_, pins) in enumerate(groups):
        for p in pins:
            pin_group[id(p)] = i

    hv = set()
    for i, (names, _) in enumerate(groups):
        if names & hv_rails and not names & exempt:
            hv.add(i)

    # Parts whose only supply is high voltage. A part with any supply pin at
    # or below the limit is a deliberate domain crossing (the FT601Q with
    # VCCIO at 2.5 V, the 74AVC4T245 with VCC(A) at 2.5 V) and is exactly
    # what the design uses to get across the boundary safely.
    def supplies(part):
        return [pin_group.get(id(p)) for p in part.pins
                if p.func is Pin.types.PWRIN and id(p) in pin_group]

    changed = True
    while changed:
        changed = False
        for part in circuit.parts:
            sup = [g for g in supplies(part) if g is not None
                   and not (groups[g][0] & exempt)]
            if not sup or not all(g in hv for g in sup):
                continue
            for p in part.pins:
                g = pin_group.get(id(p))
                if g is None or g in hv or groups[g][0] & exempt:
                    continue
                if p.func in _DRIVING:
                    hv.add(g)
                    changed = True
        # A two-terminal passive with one leg on a high rail pulls the other
        # leg there too, which is how a pull-up to 3.3 V lands on a 2.5 V pin.
        for part in circuit.parts:
            pins = list(part.pins)
            if len(pins) != 2 or any(p.func in (Pin.types.PWRIN,
                                                Pin.types.PWROUT)
                                     for p in pins):
                continue
            gs = [pin_group.get(id(p)) for p in pins]
            if None in gs:
                continue
            for a, b in (gs, gs[::-1]):
                if a in hv and b not in hv and not (groups[b][0] & exempt):
                    hv.add(b)
                    changed = True

    bad = []
    for part, allowed in protected.items():
        ok = exempt | set(allowed)
        for p in part.pins:
            if (p.func in (Pin.types.PWRIN, Pin.types.PWROUT)
                    or _SUPPLY_NAME.match(str(p.name))):
                continue
            g = pin_group.get(id(p))
            if g is None or g not in hv or groups[g][0] & ok:
                continue
            bad.append(f"  {part.ref}.{p.num} ({p.name}) on net "
                       f"{'/'.join(sorted(groups[g][0]))}")
    if bad:
        raise AssertionError(
            f"nets above the {ABS_MAX_V} V absolute maximum reach "
            f"{len(bad)} protected pin(s):\n" + "\n".join(sorted(bad)))

# netlist

Schematic as code. The two boards are described in Python and emit KiCad
netlists, which import into a PCB to start layout.

```
export KICAD10_SYMBOL_DIR="/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
../../.venv/bin/python main_board.py
../../.venv/bin/python output_module.py
```

Outputs land beside each board project, as `.net` for KiCad and `.xml` for
tooling.

Parts the stock libraries do not carry live in `../symbols/lyrebird.kicad_sym`,
which the generator adds to the search path itself. It holds two symbols so
far, both with pinouts taken from the manufacturer datasheet:

| Symbol | Part | Source |
| --- | --- | --- |
| `LTM4622` | LTM4622IV#PBF, LGA-25 | Datasheet Rev J, PIN FUNCTIONS |
| `MX25R6435F` | MX25R6435FM2IH0, SOP-8 | Standard serial NOR pinout |

The LTM4622 still needs a footprint drawn; its `Footprint` field names
`lyrebird:Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm`, which does not exist
yet. It is a 5x5 grid on 1.27 mm, but the pad size is a manufacturer number
and is not worth guessing.

## Why this rather than drawing it

Two reasons specific to this project.

The GateMate is a 324-ball part whose symbol already carries the full ball map
and bank membership. Assigning 42 bus signals and 32 element lines by hand, to
the right banks, is exactly the kind of work that produces a quiet error. Here
the allocation is a loop over pools drawn from the symbol, so a pin cannot be
used twice and a bank cannot be silently overfilled.

More importantly, the constraint that fails silently is checkable. A clock on
an ordinary pin is not an error in the FPGA toolchain: the packer routes it
through the fabric and adds the jitter the bypass path exists to avoid, with no
warning. Because the netlist is generated, that assignment is asserted rather
than hoped for, and the generated netlist confirms both clocks land on
clock-capable balls.

## What is real and what is not

Stock KiCad 10 libraries carry almost everything, including a Cologne Chip
GateMate library, which removed the obstacle I expected to dominate this work.

**Real parts, real pinouts:** GateMate CCGM1A1, FT601Q, LTM4622, LT3045,
LT3094, 74AVC4T245, MX25R6435F, the USB 3.0 receptacle, the crystal, the
ferrite, and the resistor arrays.

**Placeholder symbols**, marked in the source, with the intended part in the
value field:

| Placeholder | Intended part | Why it is a placeholder |
| --- | --- | --- |
| `ASE-xxxMHz` | Crystek CCHD-957 | Same 4-pin enable/ground/output/supply pinout, different footprint |
| `74AUP1G74` | Low-jitter fanout divider | Part never selected |
| `74HCT574` pairs | One 16-bit register per channel | No 16-bit symbol in stock libraries; a custom one is needed |
| `OPA1612AxD` | Output op amp | Part never selected |

The 16-bit register substitution is the one that matters. Decision 0012 calls
for a single package per channel so both polarities share a die, because
even-order cancellation depends on the two sides matching. Two octal parts give
the same connectivity but not that property, so the symbol has to be made
before this is a real schematic.

## The absolute maximum is asserted, not reviewed

GateMate GPIO are LVCMOS to 2.5 V with an absolute maximum VDDIO of 2.75 V,
and the mezzanine carries 2.5 V logic by contract. Both boards had shipped a
netlist where a 3.3 V module signal reached a header pin, so
`lp.assert_below_abs_max` now fails the build instead.

It works out which nets can carry more than 2.75 V, from a declared list of
rails plus anything driven by a part whose every supply sits on one of them,
and then checks that no such net reaches an FPGA signal pin or a header pin.
The header is allowed `+5V`, which `interface.md` hands to the module on
purpose.

Two distinctions make it usable rather than noisy. A part with any supply at
or below the limit is a deliberate domain crossing, not a hazard: that is the
FT601Q with `VCCIO` at 2.5 V and the 74AVC4T245 with `VCC(A)` at 2.5 V, which
are exactly the parts the design uses to get across the boundary. And an
input pin is not a source, which is what lets the 28 element lines land on
3.3 V register inputs legitimately, a threshold question rather than a
damage one.

It catches, as of now: the element clock reaching `MCLK` without passing
through the translator, `ID0` strapped to the 3.3 V reference rail, and a
3.3 V pull-up landing on any header signal.

## Bank allocation

Drawn from the symbol, not invented.

| Purpose | Banks | Count |
| --- | --- | --- |
| Bridge FIFO bus | NA, NB, EA | 42 signals |
| Element lines | SA, WB | 32 provisioned |
| Mezzanine control | WC | 5 |
| Clocks | SB | 2 of 4 clock-capable pins |
| Flash and JTAG | WA | dedicated second functions |

All banks sit at 2.5 V. The bridge interface and the element outputs are kept
in separate banks: same voltage, but no shared bank supply.

Every clock-capable pin on this part lives in bank SB, which is worth knowing
before laying out, since it fixes where both clocks must enter.

## PCB and schematic generation: tried, does not work here

SKiDL exposes `generate_pcb` and `generate_schematic` alongside the netlist
generator. Both were run against the main board and neither completed: they
spawned several processes and produced no file after minutes on the 324-ball
part, and had to be killed.

So the flow stops at the netlist. Import it into a KiCad board to begin
layout, which is the step that actually needs a person: ball escape on a
324-ball package, USB 3.0 differential pairs with controlled impedance, and a
precision analog section are not auto-placeable in any useful sense.

## Why the flash is 64 Mbit

[0013](../../docs/decisions/0013-simulation-and-build-toolchain.md) measured
97,566 bytes at 94 `CPE_LT` and 184,050 bytes at 290, so the bitstream tracks
utilisation rather than being a flat image. A straight line through those two
points is about 441 bytes per `CPE_LT` over a 56 kB fixed part. The real
design adds an interpolator, a modulator, the rotation and the elastic
buffer; at a few thousand CPEs that line predicts megabytes, and 2 Mbit is
not in the conversation.

The decisive argument is not the extrapolation, though. Cologne Chip's own
evaluation board for this die fits 64 Mbit, and the Trenz TEG2000 module fits
128 Mbit. Taking the vendor's own number for the same part is better evidence
than a two-point fit, and 64 Mbit is also about 43 times the largest figure
actually measured here.

**MX25R6435F**, the part on Cologne Chip's board. Its 1.65 to 3.6 V supply
range is what makes it usable: `VDD_WA` is 2.5 V here, and the ordinary 2.7
to 3.6 V flash parts cannot run there.

## Known gaps

The mezzanine header came out at 2x40. Thirty-two element lines each beside a
ground is 64 pins before control and power, and the spare pins become
additional ground and supply rather than being left open.

The element resistor value is still a placeholder, and so are the four
symbols above.

Pins left open on purpose, so they are not mistaken for oversights:

| Pin | Why |
| --- | --- |
| FT601Q `Reserved` | Datasheet says do not connect |
| GateMate SerDes, `NC` | SerDes unused; its supplies share the core rail |
| GateMate `SPI_FWD` | Only used when several FPGAs chain off one flash |
| Unused GateMate bank I/O | EB, and the remainder of EA, SB, WB, WC |
| USB `ID` | Device port, not OTG |
| LTM4622 `COMP1`/`COMP2` | Internally compensated, "do not drive this pin" |
| LTM4622 `INTVCC` | Internally decoupled, no external capacitor needed |
| LT3045 `PG` | Open-collector flag, unused |

Still genuinely open on the module, both waiting on parts nobody has chosen:
the LT3094's input, which needs the charge pump from
[0009](../../docs/decisions/0009-usb-bus-power.md), and the op amp's own
pins. The divider placeholder is also not wired as a divider, because the
real part is a fanout divider with a different pinout entirely.

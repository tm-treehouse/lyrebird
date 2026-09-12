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

**Real parts, real pinouts:** GateMate CCGM1A1, FT601Q, LT3045, LT3094,
74AVC4T245, and the resistor arrays.

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

## Known gaps

The mezzanine header came out at 2x40. Thirty-two element lines each beside a
ground is 64 pins before control and power, and the spare pins become
additional ground and supply rather than being left open.

Passive values other than decoupling are not chosen, and the element resistor
value is a placeholder. Those wait on the part-selection work that has not been
done.

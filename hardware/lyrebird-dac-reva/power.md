# lyrebird-dac-reva — power

The module regulates its own rails from the +5 V the main board hands it
([0009](../../docs/decisions/0009-usb-bus-power.md),
[interface.md](../interface.md)). This page shows the arithmetic behind every
number. The main board's half is
[../lyrebird-main-reva/power.md](../lyrebird-main-reva/power.md) and the two
have to agree; the total below appears there as one line.

**Provenance is marked on every figure**: *datasheet typical*, *calculation*,
or *estimate*. `hardware/datasheets/` is empty, so nothing here was re-read
from a vendor PDF; the two datasheet figures reach this page through decision
records that cite them, and are marked as such.

## Where the boundary sits

**The boundary is the +5 V pins of the mezzanine header**, J1 pins 71, 73, 75,
77 and 79 in `lyrebird-dac.net`, five pins of unregulated bus voltage
downstream of the main board's VBUS ferrite.

**Nothing else crosses.** No 3.3 V, and — the part that bites — **no 2.5 V**.
Everything on this page is generated on this board. Everything upstream of
those five pins is the main board's problem.

That is not a free choice on either side. 2.5 V is the header's logic level,
set by GateMate GPIO with a 2.75 V absolute maximum
([0005](../../docs/decisions/0005-ft601q-bridge-io-voltage.md)), and
[0012](../../docs/decisions/0012-module-clock-architecture.md) requires the
translator's A-side pins — supply, direction and output enable — to be
referenced to that rail and **never to 3.3 V**. The module therefore needs a
2.5 V rail that the interface does not supply. See the last section.

## The rails

| Rail | V | Source | Feeds | At the rail | From 5 V |
| --- | --- | --- | --- | --- | --- |
| `+3V3_REF` | 3.3 | LT3045, U5 | 4 register packages, 8x 100 nF | 54 mA | 56 mA |
| `+3V3_CLK` | 3.3 | LT3045, U6 | Y1, Y2, divider, translator `VCC(B)` | 37.5 mA | 40 mA |
| `+5V_A` | +5 | none | op amp `V+` | 14.4 mA | 51 mA |
| `-5V_A` | −5 | LT3094, U8 | op amp `V−` | 14.4 mA | (both rails) |
| `+2V5` | 2.5 | none | translator `VCC(A)` | <1 mA | — |

## The element reference rail

**This is a voltage reference that happens to power logic.** Each element
contributes the rail voltage divided by its resistor, so rail noise is
multiplicative — sidebands on the signal, not a floor under it. About 10 uV
across the audio band on 3.3 V for a 110 dB dynamic range (0012).

### Element current

Differential thermometer drive holds exactly seven elements high per channel at
every code, so the load is constant by construction and not signal-dependent —
that is the whole reason the drive is differential
([0008](../../docs/decisions/0008-multibit-delta-sigma-with-dwa.md)):

```
N_high = 7 per channel x 2 channels = 14, at every code   (calculation)
I_elem = 14 x 3.3 V / R_elem
```

This assumes the summing node sits at 0 V, a virtual ground at the op amp's
inverting input. If it floated at a DC midpoint instead, the current would be
lower and signal-dependent, which is exactly the compression the differential
drive exists to prevent — so the virtual-ground case is both the one consistent
with 0008 and the worst case.

`R_elem` **has never been chosen**. The netlist's 1 kΩ is a placeholder
([../netlist/README.md](../netlist/README.md),
[open-items.md](../../docs/open-items.md)), and the rail current is inversely
proportional to it:

| `R_elem` | `I_elem` | Rail total | From 5 V |
| --- | --- | --- | --- |
| 1 kΩ, netlist placeholder | 46.2 mA | 54 mA | 56 mA |
| 2 kΩ | 23.1 mA | 31 mA | 33 mA |
| 3.1 kΩ, what 0009's budget implies | 14.9 mA | 23 mA | 25 mA |
| 4.7 kΩ | 9.8 mA | 18 mA | 20 mA |

It cannot be settled on power grounds alone. The same value fixes the
differential current swing into the I/V stage — ±7 x 3.3 V / `R_elem`, so
±23.1 mA at 1 kΩ (*calculation*) — and therefore the output level and the op
amp's feedback network. It is one number decided by two constraints, and
neither has been worked.

### Register current

28 flip-flops plus two package clock trees, `I = C x V x f` (*estimates* on
both capacitances, *calculation* on the rest):

```
flops:  28 x 5 pF x 3.3 V x 12.29 MHz  = 5.7 mA
clock:   2 x 15 pF x 3.3 V x 24.576 MHz = 2.4 mA
                                          -------
                                          8.1 mA
```

Element switching is taken at half the element clock, which is what dynamic
element matching produces on any given line.

### Rail total

```
46.2 mA elements + 8.1 mA registers      = 54.3 mA at the rail
+ 2 mA LT3045 ground pin (estimate)      = 56.3 mA from 5 V
P = (5.00 - 3.30) x 0.0543               = 92 mW dissipated   (calculation)
```

### Decoupling is not a budget question, but it is arithmetic

The DC load is constant, so what the local ceramics actually supply is the
redistribution transient when the rotation swaps which lines are high. A
worst-case swap of seven elements is a 23.1 mA step, lasting as long as the
reclock skew between the flip-flops:

```
dV = dI x t / C = 23.1 mA x 1 ns / 800 nF = 29 uV        (calculation)
```

against 8 x 100 nF fitted. That is above the 10 uV audio-band target, but it
happens at the element clock rate rather than in band and the rotation
scrambles it. It is still the reason 0008 says decouple heavily and keep return
currents tight: at these edge rates the binding term is the loop inductance
from the package pin to the capacitor, which is a layout problem this page
cannot budget.

## The clock chain rail

| Item | mA at 3.3 V | Provenance |
| --- | --- | --- |
| CCHD-957, running | 15.5 | datasheet typical via 0012, see below |
| CCHD-957, standby | 1.5 | datasheet typical via 0012 |
| Fanout divider | 20 | estimate — part never chosen |
| 74AVC4T245, B side | 0.5 | calculation |
| **Total** | **37.5** | |

The oscillator figure is arithmetic on 0012, which gives standby as 1.5 mA and
says both parts fitted cost about 17 mA together:

```
I_running = 17 - 1.5 = 15.5 mA                            (calculation)
```

Exactly one resonator runs; the other is in standby, which shuts the resonator
down rather than gating the output.

**The divider is the largest estimate on the module and 0009 never costed it.**
0009 has a 30 mA line called "Oscillator" against 17 mA of oscillator, which
leaves 13 mA for a part that has to divide by two and drive two register
packages and the header with tight skew. A low-additive-jitter LVCMOS clock
buffer in that class runs 10 to 25 mA at 3.3 V; 20 mA is taken here and it is
an *estimate* until the part exists.

The translator's B side receives `MCLK` and drives nothing, since the direction
is B to A; its cost is internal switching at 24.576 MHz on a 5 pF node
(*estimate*), `5 pF x 3.3 V x 24.576 MHz = 0.41 mA` (*calculation*). The two
enable lines are static.

```
37.5 mA at the rail + 2 mA LT3045 ground = 39.5 mA from 5 V
P = (5.00 - 3.30) x 0.0375               = 64 mW dissipated
```

## The op amp rails

**No part on this path has been chosen** — op amp, charge pump, post-regulators
and reconstruction filter are all open
([open-items.md](../../docs/open-items.md)) — so everything here is an
*estimate* structured by 0009 rather than a measurement.

Four amplifier channels: differential to single-ended for each of L and R, then
a fixed-gain line buffer for each. At 3.6 mA per amplifier, the class implied by
the OPA1612 stand-in in the netlist:

```
4 x 3.6 mA = 14.4 mA on each of +5 V and -5 V             (estimate)
```

Signal current is negligible beside it: 2 V RMS into a 10 kΩ line load is
0.2 mA RMS (*calculation*).

A 5 V input cannot produce +5 V with headroom, so the pump has to make both
polarities and the regulators drop to the final rails — run it hot, because op
amp rejection falls off steeply with frequency and at a pump's switching
frequency it rejects far less than its headline figure (0009). Taking ±7 V into
LDOs at 85 % pump efficiency (*estimate*):

```
P_in  = (7 + 7) V x 14.4 mA = 202 mW
      / 0.85                = 237 mW
I(5V) = 237 mW / 5.0 V      = 47.4 mA
+ pump and two LDO quiescent, 4 mA (estimate)
                            = 51 mA from 5 V              (calculation)
```

The post-regulators drop `2 x (7 - 5) x 14.4 mA = 58 mW` (*calculation*),
which is inside that 237 mW.

## Totals at the mezzanine

| Rail | At the rail | From 5 V | Provenance |
| --- | --- | --- | --- |
| Element reference, at the placeholder 1 kΩ | 54 mA | 56 mA | calculation on an unchosen resistor |
| Clock chain | 37.5 mA | 40 mA | datasheet typical + estimate |
| Op amp stage and charge pump | 14.4 mA each rail | 51 mA | estimate, parts absent |
| Translator A side | <1 mA | 0 today | no source exists |
| **Module total** | | **147 mA** | |

At a 2 kΩ element the total is 124 mA; at 3.1 kΩ, 116 mA.

Headroom is fine at the worst input. USB 3.0 guarantees 4.45 V at the device
(*via 0009*); a ferrite at 50 mΩ drops 19 mV at the full 381 mA and five
parallel header contacts at 20 mΩ drop 0.6 mV at 147 mA (*estimates* on the
resistances), so the module's LT3045s see 4.43 V against a 3.3 V output —
1.13 V of headroom against a dropout of a few hundred millivolts.

## Reflected to the USB input, and margin

The module is one line in the main board's budget:

```
main board  234 mA
module      147 mA
            -------
total       381 mA                                        (calculation)
```

| Against | Limit | Drawn | Spare | Utilisation |
| --- | --- | --- | --- | --- |
| USB 3.0, configured | 900 mA | 381 mA | 519 mA | 42 % |
| USB 2.0 host | 500 mA | 381 mA | 119 mA | 76 % |

This is the line-output module. 0009 puts a hard-driven headphone stage at
roughly 200 mA more, reaching about 580 mA: comfortable on USB 3.0, over the
500 mA of a USB 2.0 host. That module is not this one — `ID0`/`ID1` are
strapped 0b01 — and 0009 deliberately leaves the case unsolved, pointing a
module that needs more than the bus supplies at its own input jack.

**The declared figure is 900 mA regardless**, fixed at enumeration and not
renegotiable when a module is swapped.

## Before enumeration

A device may draw one unit load before it is configured: 150 mA on USB 3.0,
100 mA on USB 2.0. **None of the module's rails are gated.** All three LT3045s
take +5 V straight off the header, and their `EN/UV` pins are unconnected in
the netlist, so 96 mA of clock chain and element reference is live while the
FPGA is still loading its bitstream.

0009 gates the FPGA rails with the LTM4622 run pins, which leaves 72 mA of
bridge and regulator inside the 150 mA. Adding this module's ungated 96 mA
reaches 168 mA and does not fit; the full table, including what other element
values do to it, is in
[../lyrebird-main-reva/power.md](../lyrebird-main-reva/power.md). At power-on
the flip-flop state is undefined and all 28 elements may be high, which doubles
the element term.

## Against 0009's budget

Checked rather than copied. 0009's three module lines sum to 120 mA; this page
gets 147 mA.

| Line | 0009 | Here | Why |
| --- | --- | --- | --- |
| Element reference rail | 25 | 56 | 25 mA implies a 3.1 kΩ element; the netlist says 1 kΩ |
| Oscillator | 30 | 40 | 17 mA of oscillator is right; the fanout divider was never costed |
| Op amp stage and charge pump | 65 | 51 | four amplifiers at 3.6 mA and an 85 % pump |
| **Module subtotal** | **120** | **147** | |

The whole 27 mA difference is two parts nobody has chosen: the element resistor
and the fanout divider. Neither is a budget error in 0009; both are numbers
that could not be computed when it was written.

## What has no source today

**`+2V5`, the translator's A-side supply.** One node in the netlist, `U2.VCCA`,
and no regulator. The header does not carry 2.5 V and 0012 forbids strapping
the A side to 3.3 V, so this rail has to be generated on the module — or the
interface has to gain a pin. Its own consumption is under 1 mA (one 24.576 MHz
clock into about 10 pF of trace, connector and FPGA pad: `10 pF x 2.5 V x
24.576 MHz = 0.61 mA`), so this is a missing rail rather than an expensive one.

**`+5V_A`, the op amp's positive rail.** One node, `U7.V+`, and no regulator.

**The charge pump.** `-5V_A` is regulated by the LT3094 at U8, but U8's `IN`
pins are unconnected and no pump exists to feed them, so neither analog rail
has a source.

**The element reference rail leaves the board.** In `lyrebird-dac.net` it is
merged with the `ID0` strap and appears under that name, which puts 3.3 V on a
header pin that the main board pulls down through 10 kΩ into a GateMate GPIO
with a 2.75 V absolute maximum. The 3.3 V divided clock reaches the header
directly for the same kind of reason. Both are wiring defects rather than power
budget items, but they sit on the rail boundary this page is about, so they are
recorded here too.

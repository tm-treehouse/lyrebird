# Mezzanine interface contract

The boundary between the main board and the output module, per
[0007](../docs/decisions/0007-two-board-split-at-i2s.md) and
[0008](../docs/decisions/0008-multibit-delta-sigma-with-dwa.md). Both boards
must honour this. It is provisional until the first layout fixes a connector.

There is no DAC chip. The FPGA runs the modulator and drives element lines; the
module reclocks them, sums them through matched resistors, and filters the
result.

## Signals

| Signal | Direction | Purpose |
| --- | --- | --- |
| `MCLK` | module to main | Element clock, the enabled oscillator divided by two |
| `ELEM[31:0]` | main to module | Thermometer element lines, see allocation below |
| `OSC_EN_441` | main to module | Enable the 45.1584 MHz oscillator (22.5792 MHz element clock) |
| `OSC_EN_48` | main to module | Enable the 49.152 MHz oscillator (24.576 MHz element clock) |
| `MUTE_N` | main to module | Mute the analog output stage |
| `ID0`, `ID1` | module to main | Module type, strapped on the module |
| `+5V` | main to module | 5.02 V from the main board's buck, for the module's regulators |
| `-6V_A` | main to module | −5.98 V, two pins (73/74), for the module's negative analog rail |
| `GND` | — | Interleaved between signals |

## Element allocation

Thirty-two lines are provisioned; a three-bit differential stereo module uses
28. The rest are reserved so element count can change without touching the main
board or the connector.

| Lines | Use |
| --- | --- |
| `ELEM[6:0]` | Left channel, positive side |
| `ELEM[13:7]` | Left channel, negative side |
| `ELEM[20:14]` | Right channel, positive side |
| `ELEM[27:21]` | Right channel, negative side |
| `ELEM[31:28]` | Reserved. Driven low by the main board |

For code k on a given side, the main board asserts k of the seven positive lines
and seven minus k of the negative lines, so exactly seven lines per channel are
high at any code. Which specific lines carry the code is chosen by the dynamic
element matching rotation and must not be assumed stable.

## Rules

**The negative rail is flanked by ground, deliberately.** `-6V_A` occupies
pins 73 and 74 — one column of a 2×40 odd/even header — with full ground
columns at 71/72 and 75/76 either side. The pair is adjacent to itself so a
half-inserted connector cannot present one pin without the other, and isolated
from the control block because that block has no ground pin inside it: MCLK,
both oscillator enables, `MUTE_N` and both ID straps run from pin 65 to 70 with
returns only at either end. A bridge or a whisker across 1.27 mm from `ID1`
would otherwise put −6 V on a net that reaches a GateMate GPIO through nothing
but a 10 kΩ pull-down, with the input's clamp diode conducting and the current
limited only by the bridge. Four pins out of a ground surplus removes that.

**Logic levels on the header are 2.5 V.** This is set by the GateMate GPIO
banks, which are LVCMOS up to 2.5 V and are not 3.3 V tolerant. See
[0005](../docs/decisions/0005-ft601q-bridge-io-voltage.md). Nothing on the main
board is safe above 2.75 V.

**The module's own domain is 3.3 V**, including the oscillators, the clock
chain and the element reference rail. A translator on the module converts
`MCLK`, `OSC_EN_441` and `OSC_EN_48` at the boundary. It lives on the module
side deliberately, so the mezzanine never carries 3.3 V. The element lines are
not translated; the registers' input threshold accepts 2.5 V directly. See
[0012](../docs/decisions/0012-module-clock-architecture.md).

**Every element line is reclocked on the module** before it reaches a resistor,
by a flip-flop clocked from the module oscillator and powered from the reference
rail. This is what removes the FPGA's clock jitter and supply noise from the
output, and it is the reason the oscillator may stay on the module at all.
Nothing on the main board should be treated as analog-grade.

**Keep reclock skew tight.** Timing mismatch between flip-flop packages behaves
like element mismatch. The rotation scrambles it, but it is cheaper not to
create it.

**Every element line sits adjacent to a ground pin.** Element return currents
are the analog signal.

**Exactly one oscillator runs at a time**, and this is now enforced rather
than merely stated. The main board enables the family it needs; a module fitted
with only one family ignores the other enable and straps its ID accordingly.

The rule matters because a module may share one output net between two
oscillators, which is legal only while exactly one is enabled — the CCHD-957
tri-states its output in standby, so an idle part neither drives nor radiates.
It used to be a rule with nothing behind it: both enables floated before the
FPGA was configured, and an open E/D pin on that part *runs*, so both
oscillators could start and drive the shared net into each other. **Both boards
now pull the enables down** — the main board because the floating input is on
its side of the translator, the module as well because a pull-down there only
decides the case where the translator's output is high impedance.

**The module regulates its own rails** from the +5V and −6V it is handed. Only
the negative rail comes in pre-inverted: the output stage needs about 3.5 V on
the positive side and the header's 5 V covers it, so a module needs no
bipolar converter of its own. A module that wants more than the main board's
inverter delivers should take its own supply input (0009 defers that case for a
headphone stage).

**The element reference rail is the critical one**: it sets full scale, so it
multiplies the signal, and it carries the elements' own switching current.

**A correction to what this document used to promise.** It said the
constant-current property of differential thermometer drive keeps that load
signal-independent, and that heavy local decoupling handles the rest. Both
halves are wrong in a way a module designer would act on:

- 0008 guarantees exactly seven of fourteen elements high at every code, so the
  **DC** load is constant. It guarantees nothing about how often lines
  *change*, and the element filter capacitors and the registers both draw
  current in proportion to that. Because the DWA pointer advances by the code,
  the count of changing lines is a full-wave rectification of it, which puts a
  signal-correlated current on the rail.
- Decoupling does not answer that, because the disturbance is at twice the
  signal frequency and at the programme envelope rather than at the switching
  rate. Eight 100 nF parts are about 100 Ω where it lives; reaching the chain's
  own noise floor would need 170 µΩ at 2 kHz.

Predicted at −101.1 dBFS against a chain held to −136.5. It is the project's
lead open item, it is a prediction from a digital proxy rather than a
measurement, and it wants a bench. See
[docs/open-items.md](../docs/open-items.md).

**There is no declared current budget any more.** This section used to require
the module to stay inside a figure fixed in the USB descriptor at enumeration.
0014 replaced bus power with a 12 V supply, so nothing is negotiated and the
constraint is simply what the main board's converters deliver.

## Module identification

`ID0` and `ID1` are strapped on the module and read by the FPGA.

| ID1 | ID0 | Module |
| --- | --- | --- |
| 0 | 0 | No module fitted, pins pulled low on the main board |
| 0 | 1 | Line output only |
| 1 | 0 | Headphone output only |
| 1 | 1 | Combined line and headphone |

The oscillator complement is not encoded here. A module that lacks a family
never asserts a clock when that enable is driven, and the main board treats the
missing clock as an unsupported rate.

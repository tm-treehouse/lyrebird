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
| `OSC_EN_441` | main to module | Enable the 22.5792 MHz oscillator |
| `OSC_EN_48` | main to module | Enable the 24.576 MHz oscillator |
| `MUTE_N` | main to module | Mute the analog output stage |
| `ID0`, `ID1` | module to main | Module type, strapped on the module |
| `+5V` | main to module | Unregulated, downstream of the VBUS ferrite |
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

**Exactly one oscillator runs at a time.** The main board enables the family it
needs. A module fitted with only one family ignores the other enable and straps
its ID accordingly.

**The module regulates its own rails** from the +5 V it is handed. The element
reference rail is the critical one: it sets full scale, and it carries the
switching current of the elements themselves. The constant-current property of
differential thermometer drive is what keeps that load signal-independent, but
it still needs heavy local decoupling, because a regulator loop cannot hold a
rail at these frequencies.

**The module must stay inside the declared budget.** Current is declared in the
USB descriptor at enumeration and cannot be renegotiated when a module is
swapped, so the descriptor is set for the worst case the design supports.

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

# 0009 — USB bus power, and which rails are precision

**Status:** accepted

## Context

A single cable carrying both power and data was the goal from the start. The
objection was that a DAC's analog supply would then trace back to a bus carrying
the host's switching noise, and that a wall adapter might be cleaner.

Two things since then have answered that. The FPGA is now the DAC, and every
element line is reclocked on the output module by flip-flops on their own
reference rail, so the main board's switching supplies never reach the signal.
See [0008](0008-multibit-delta-sigma-with-dwa.md). And the rails that do reach
the signal are regulated by parts that reject bus noise by roughly 76 dB at
1 MHz while contributing 0.8 uV of their own.

Cologne Chip's own evaluation board is USB-powered and states that a USB supply
is the typical source.

## Decision

**Bus powered. No external power input on the main board.**

### Main board, ordinary regulation

| Rail | Feeds | Part |
| --- | --- | --- |
| 5 V | Passed through to the module | Ferrite only |
| 3.3 V | FT601Q `VCC33`/`VDDA` | LT3045 |
| 2.5 V | FT601Q `VCCIO`, GateMate GPIO banks | LTM4622, channel 1 |
| 1.0 V | GateMate `VDD`, `VDD_PLL`, `VDD_SER`, `VDD_SER_PLL` | LTM4622, channel 2 |

The LTM4622 is a dual, so one package covers both switching rails. Its 3.6 V
minimum input is comfortably below the 4.45 V that USB 3.0 guarantees at the
device, though it is less margin than the modules on Cologne Chip's board.

The 3.3 V rail uses a regulator rather than a switcher because it feeds the USB
PHY's analog supply and because FTDI's own bus-powered reference design does. It
dissipates roughly 400 mW, so tie the exposed pad to plane with thermal vias.

Fit noise filters between every regulator and the FPGA. The GateMate datasheet
asks for this explicitly, and there are no restrictions on rail ordering, so no
sequencer is needed.

### Module, precision regulation

| Rail | Feeds | Part |
| --- | --- | --- |
| Element reference | Reclocking registers | LT3045 |
| Oscillator | Audio oscillator | LT3042 or LT3045 |
| Op amp positive | Output stage | LT3045 |
| Op amp negative | Output stage | LT3094 |

The op amp rails cannot come from bus voltage directly, so a charge pump
generates them and the regulators post-regulate its output.

## The organising principle

The split is not analog versus digital. It is whether a rail's noise reaches
the signal.

| Rail | Reaches the signal |
| --- | --- |
| Element reference | Yes. It sets full scale, multiplicatively |
| Oscillator | Yes, as jitter |
| Op amp rails | Yes, through finite op amp rejection |
| FPGA I/O banks | No. Reclocked away on the module |
| FPGA core | No |
| Bridge 3.3 V | No |

The most critical precision rail powers digital logic. The reclocking registers
are ordinary flip-flops whose output swing happens to be full scale. That is
also what lets the entire main board run on conventional regulation.

## Budget

Estimates, except the bridge figure, which is the datasheet typical.

| Item | mA from 5 V |
| --- | --- |
| Bridge 3.3 V, active SuperSpeed | 185 |
| FPGA core, through buck | 35 |
| Bridge I/O and FPGA banks, through buck | 20 |
| Element reference rail | 25 |
| Oscillator | 30 |
| Op amp stage and charge pump | 65 |
| Regulator quiescent and margin | 20 |
| **Line output total** | **about 380** |

Against 900 mA on USB 3.0 that is 42 percent utilisation.

**Declare 900 mA in the USB descriptor** regardless of the module fitted.
Current is fixed at enumeration and cannot be renegotiated when a module is
swapped, and declaring more than is drawn is legal.

**Gate the FPGA rails with the LTM4622 run pins.** One unit load, 150 mA,
applies before the device is configured, and at power-on the bridge idles near
70 mA while the FPGA loads its bitstream from flash and the oscillator is
already running. Release the rails once enumeration completes. Confirm the run
pin behaviour against the datasheet before relying on exact sequencing.

## What does not fit

A headphone module driven hard adds roughly 200 mA at peaks, reaching about
580 mA. Comfortable on USB 3.0. Over the 500 mA ceiling of a USB 2.0 host. Line
output fits both, since falling back to High Speed also lowers the bridge's own
draw.

This is deliberately not solved here. A module that genuinely needs more than
the bus can supply can carry its own input jack, which is the right place for
it: that is where the current is consumed and where the analog grounds already
are. See [0007](0007-two-board-split-at-i2s.md).

## Rejected: barrel jack on the main board

A second supply means a second ground reference alongside USB ground, which is a
well-known source of hum in audio equipment. A generic wall adapter is also
frequently noisier than a host's bus voltage, so it would trade a characterised
noise source for an uncharacterised one. Both to solve a problem that
regulation already solves, and that no currently specified module has.

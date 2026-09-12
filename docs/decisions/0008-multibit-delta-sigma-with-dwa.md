# 0008 — Multi-bit delta-sigma with dynamic element matching

**Status:** accepted. The 2.5 V element reference rail assumed here, including
in the noise target, is superseded by
[0012](0012-module-clock-architecture.md), which moves it to 3.3 V.

## Context

The FPGA now synthesises the analog waveform directly, so there is no DAC chip.
The quantizer at the end of the modulator drives external elements. One bit is
inherently linear but noisy, stability-limited, and prone to idle tones.
Multi-bit starts from a far smaller quantization error and asks much less of the
reconstruction filter, at the cost of requiring evenly spaced output levels.

## Decision

**Three-bit quantizer, thermometer coded, with data weighted averaging** in the
FPGA. Seven unit elements per side, each driving a matched resistor into a
summing node.

**Differential.** For code k, drive k elements on the positive side and seven
minus k on the negative side.

**External reclocking.** Every element line passes through a flip-flop on the
output module, clocked by the module oscillator and powered from the reference
rail, before it reaches a resistor. See
[0007](0007-two-board-split-at-i2s.md).

## Why differential is not optional here

Thermometer coding draws a signal-dependent current from the reference. At code
one, one element is high; at code seven, seven are. If the reference sags under
that varying load, full scale moves with the signal, which is compression, which
is distortion. No amount of resistor precision fixes it.

Driving k elements positive and seven minus k negative keeps exactly seven
elements high at every code, so the current drawn from the reference is constant
regardless of signal. It also cancels even-order distortion, rejects
common-mode noise on the reference, and gives 6 dB more output. The
differential-to-single-ended conversion falls out of the op amp stage that was
going to exist anyway.

## Why dynamic element matching

Mismatch between elements is not noise-shaped. It lands in the audio band as
distortion, and it is set by resistor tolerance, driver mismatch, and clock skew
between reclocking flip-flops. Rotating which elements represent a given code
makes each one used equally over time, so the average is correct and the
mismatch becomes a high-frequency error the loop shapes out of band.

This is why the coding is thermometer rather than binary. Rotation only works
among elements of equal weight. It also means ordinary one percent resistors are
adequate, and that skew between reclocking flip-flop packages is scrambled along
with everything else.

## Why three bits

Element count grows as two to the power of the bits, minus one, per side, and
differential doubles it.

| | 3-bit | 4-bit |
| --- | --- | --- |
| Output levels | 8 | 16 |
| Elements per side | 7 | 15 |
| Lines, stereo differential | 28 | 60 |
| 16-bit registers per channel | 1 | 2 |

**Three-bit differential fits exactly one register per channel.** Fourteen
elements, seven per polarity, land in a single 16-bit package with two bits
spare. Both polarities of a channel then share one die, one process corner, one
supply pin, and one clock-to-output distribution. Differential cancellation of
even-order distortion depends on the two sides matching, so this is doing real
work, not tidiness.

Four bits needs thirty elements per channel, which is two packages, and the
natural split puts the positive side on one die and the negative on another.
That relies on cross-package matching for precisely the thing differential
drive exists to deliver.

**Provision 32 element lines** in the FPGA pinout and the connector. Element
count is the one parameter baked into both boards at once, so it gets headroom.
Note what the spare lines do not buy: four-bit differential needs 60 and would
require a main board respin regardless. They remain as cheap spares.

## Rejected: four bits

One extra quantizer bit lowers the entire noise transfer curve by about 6 dB,
out-of-band included, which on a single filter pole is roughly a third of a
decade. At an oversampling ratio of 256 the quantization noise already sits far
below what the analog section will produce, so that 6 dB is not the limit and
buying it costs the single-die property above, double the elements, double the
resistors, and a much wider connector.

Four bits would be the right answer at a much lower oversampling ratio, around
32 to 64, where quantization noise genuinely is near the limit. A 24.576 MHz
master clock against a 96 kHz sample rate does not put us there.

## Consequences

**The digital side has large headroom; the analog side sets performance.** At
the oversampling ratios available from a 24.576 MHz master clock, a modest
modulator order already exceeds what the analog section will deliver. Effort
belongs in the reference rail, the reclocker, and the filter, not in chasing
modulator order.

**The reference rail carries the switching current of the elements.** A
low-dropout regulator's loop is far too slow to hold a rail at tens of
megahertz, so decouple heavily at the flip-flops and keep element return
currents tight. The constant-current property above is what makes this
tractable.

**The interface contract changes substantially.** Bit clock, word clock, serial
data, and the I2C pair all disappear, replaced by element lines. See
[hardware/interface.md](../../hardware/interface.md).

**The HDL grows by an interpolation filter chain, the modulator, and the DWA
rotation logic.** Quality can be measured in simulation, by running the
modulator in a testbench and taking an FFT of the element sum, before any board
exists.

## Where the performance actually comes from

Not the quantizer. In rough order of what will set the measured numbers: the
reference regulator's noise, the linearity of the resistor elements, reclock
skew, and the reconstruction filter. Effort spent on modulator order or
quantizer width is effort spent on the one part of this design that already has
margin.

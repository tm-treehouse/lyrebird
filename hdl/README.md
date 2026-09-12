# hdl

FPGA sources for the GateMate CCGM1A1. The FPGA is the DAC: it runs the
interpolator and the delta-sigma modulator and drives element lines directly.
See [0008](../docs/decisions/0008-multibit-delta-sigma-with-dwa.md).

- `rtl/` — synthesizable sources only.
- `constraints/` — pinout and timing. One file per board revision.
- `sim/` — cocotb testbenches.
- `build/` — Yosys and nextpnr output. Git-ignored.

## Signal chain

```
FT601Q words ──> elastic buffer ──> interpolation ──> modulator ──> DWA ──> ELEM[27:0]
  66.67 MHz       hard-block FIFO     Fs to OSR*Fs     3-bit       rotation
                   async, 40K mode                     quantizer
```

## Clock domains

| Domain | Source | Contents |
| --- | --- | --- |
| 66.67 MHz | `CLK` from the FT601Q | FIFO read handshake, word unpacker |
| `MCLK` | Output module oscillator | Interpolator, modulator, DWA, element output |

Only two domains. The sample rate is a divided enable inside the `MCLK` domain
rather than a clock of its own, so the modulator and the sample tick share one
clock tree. At 24.576 MHz the oversampling ratio is 256 at 96 kHz and 512 at
48 kHz, which is ample for a modest modulator order.

`MCLK` arrives from the output module rather than from an oscillator on this
board. That is only safe because every element line is reclocked on the module
before it reaches a resistor, which removes this FPGA's clock jitter from the
output entirely. See
[0007](../docs/decisions/0007-two-board-split-at-i2s.md).

**The master clock changes frequency.** Switching between the 44.1 and 48 kHz
families switches which oscillator the module runs. Treat it as a
reconfiguration event: mute, drive the other enable, wait for settle, re-lock,
prefill, resume.

## Element output

Three-bit quantizer, thermometer coded, differential. For code k the modulator
asserts k of seven positive lines and seven minus k of the negative lines, so
exactly seven lines per channel are high at any code. That keeps the module's
reference loading constant, which is a distortion mechanism rather than a
nicety.

Dynamic element matching rotates which lines carry a given code, so element and
timing mismatch become high-frequency error the loop shapes out of band rather
than in-band distortion. The rotation state is part of the design; do not assume
a stable mapping from code to line.

The full line allocation is in [hardware/interface.md](../hardware/interface.md).

## Bus interface

245 Synchronous FIFO mode, one IN and one OUT channel. Signals are `CLK`,
`DATA[31:0]`, `BE[3:0]`, `RXF_N`, `TXE_N`, `RD_N`, `WR_N`, `OE_N`, `SIWU_N`.
Only the receive direction carries audio; the transmit direction is available
for status or control later.

## Wire format

One padded sample per bus word, with all four byte enables asserted.

```
DATA[31:24]  tag       0xA5 = left, 0x5A = right
DATA[23:0]   sample    24-bit, signed
```

On a 32-bit bus with word-aligned transfers the interface preserves word
boundaries, so the single-dropped-byte failure mode that motivated the tags no
longer really applies. The tags stay because they recover L/R alignment if a
whole word is lost, and because they cost nothing. Require several consecutive
well-formed words before declaring lock, since real audio can contain the tag
values in the sample bits.

## The elastic buffer

Every GateMate block RAM has a hardware FIFO controller that runs in
asynchronous mode, with the write and read ports on separate clocks, full,
empty, almost-full and almost-empty flags, and exposed pointers. That is the
clock-domain crossing and the prefill threshold as a hard block rather than
fabric to write and verify. It requires the 40K configuration.

Sizing, at 96 kHz stereo and 24 bits, storing one sample per 40-bit entry:

| Prefill | Blocks, of 32 available |
| --- | --- |
| 50 ms | 10 |
| 100 ms | 19 |

At 48 kHz both halve. Interpolator delay lines and coefficients are small next
to this; the elastic buffer remains the only resource meaningfully consumed.

## Resources

Logic is not close to binding. Modulator coefficients are shifts and adds rather
than multipliers, and the early interpolation stages run at a few hundred
kilohertz, so one multiplier can be time-shared across many taps.

## Verification

The modulator can be qualified before any board exists. Run it in a testbench,
sum the element lines in the model exactly as the resistors will, take an FFT,
and measure in-band signal-to-noise and distortion. Deliberately mismatch the
element weights in the model to confirm the rotation is actually converting that
mismatch into out-of-band noise. Also drive deliberate word drops on the FT601Q
side to exercise tag resync.

## Clocking caveat

The global mesh is driven from a mux fed by the PLL block, so a clock does not
reach it by an independent route. The mux does include the PLL's bypassed
reference clock, and there is a `PLL_REF_BYPASS` control. Confirm the open
toolchain exposes that bypass before relying on it. The module's reclocking
flip-flops set the final edge timing, so FPGA-side jitter is far less critical
than it would otherwise be, but there is no reason to add it.

## Build

Nothing wired up yet. Scripts land in `tools/`.

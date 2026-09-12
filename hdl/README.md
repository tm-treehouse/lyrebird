# hdl

FPGA sources for the GateMate CCGM1A1. The FPGA is the DAC: it runs the
interpolator and the delta-sigma modulator and drives element lines directly.
See [0008](../docs/decisions/0008-multibit-delta-sigma-with-dwa.md).

- `rtl/` — synthesizable sources only.
- `constraints/` — pinout and timing. One file per board revision.
- `sim/` — cocotb testbenches and the Verilator runner.
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
| `MCLK` | Module oscillator, divided by two | Interpolator, modulator, DWA, element output |

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

One padded sample per bus word, with all four byte enables asserted. Four word
types, distinguished by the tag byte. See
[0010](../docs/decisions/0010-192khz-and-control-word.md).

| Tag | Direction | Payload |
| --- | --- | --- |
| `0xA5` | in | Left sample, 24-bit signed in `DATA[23:0]` |
| `0x5A` | in | Right sample, same |
| `0xC3` | in | Control: opcode in `DATA[23:16]`, payload in `DATA[15:0]` |
| `0x3C` | out | Status, on the transmit direction |

On a 32-bit bus with word-aligned transfers the interface preserves word
boundaries, so the single-dropped-byte failure mode that motivated the tags no
longer really applies. The tags stay because they recover L/R alignment if a
whole word is lost, and because they cost nothing. Require several consecutive
well-formed words before declaring lock, since real audio can contain the tag
values in the sample bits.

Control words are inline, so they take effect in stream order. `SET_RATE`
discards buffered audio, because samples already in the elastic buffer belong
to the old rate: mute, drain, reconfigure, prefill, resume.

## Sample rates

| Rate | Oscillator | Ratio | Half-band stages |
| --- | --- | --- | --- |
| 44.1 / 88.2 / 176.4 kHz | 22.5792 MHz | 512 / 256 / 128 | 9 / 8 / 7 |
| 48 / 96 / 192 kHz | 24.576 MHz | 512 / 256 / 128 | 9 / 8 / 7 |

The modulator always runs at the oscillator rate, so noise shaping is fixed in
absolute frequency and audible-band performance does not vary with sample rate.
Only the interpolator changes, and the stages line up so that a higher rate
simply bypasses stages from the front. Changing rate within a family needs no
oscillator settling; crossing families does.

Volume is digital and lives here, applied inside the interpolation chain at
full internal precision rather than to the incoming PCM, so truncation lands at
the modulator input where it is shaped.

## The elastic buffer

Every GateMate block RAM has a hardware FIFO controller that runs in
asynchronous mode, with the write and read ports on separate clocks, full,
empty, almost-full and almost-empty flags, and exposed pointers. That is the
clock-domain crossing and the prefill threshold as a hard block rather than
fabric to write and verify. It requires the 40K configuration.

Prefill absorbs host scheduling jitter, which is a time-domain problem, so the
buffer is sized in milliseconds and the sample count scales with rate. Size for
the worst case. SDP 40K mode, 80 bits wide, three 24-bit samples per word, per
[0011](../docs/decisions/0011-pack-three-samples-per-fifo-word.md):

| Prefill | 96 kHz | 192 kHz |
| --- | --- | --- |
| 50 ms | 7 blocks | 13 blocks |
| 100 ms | 13 blocks | 25 blocks |

Thirty-two blocks exist, so the specified 100 ms at 192 kHz uses 25 and leaves
7 spare. Committing every block would reach 128 ms at 192 kHz. Interpolator
delay lines and coefficients come to well under one block.

Read granularity is three samples, so the Fs side reads a word every third
sample tick and tracks left/right by counter rather than by word boundary.

## Resources

Logic is not close to binding. Modulator coefficients are shifts and adds rather
than multipliers, and the early interpolation stages run at a few hundred
kilohertz, so one multiplier can be time-shared across many taps.

## Verification

Verilator with cocotb. See
[0013](../docs/decisions/0013-simulation-and-build-toolchain.md).

```
python hdl/sim/run.py              # every suite
python hdl/sim/run.py tag_decode   # one suite
WAVES=1 python hdl/sim/run.py      # dump FST waveforms
```

Sources are SystemVerilog restricted to the subset Yosys accepts: `logic`,
`always_ff`, `always_comb`, `localparam`. No interfaces, no packed structs.
Verilator would take more, but the same files have to synthesise.

**Two tiers, deliberately.** Functional tests live in cocotb: protocol
handshakes, tag resync, control word decoding, underrun behaviour, the lock
state machine. Short, event-driven, and far easier in Python than in an HDL
testbench.

The audio measurement does not use cocotb. Reading 28 element lines from Python
every cycle makes the binding the bottleneck rather than the simulator. Dump
the element lines from the simulation and analyse them in numpy afterwards,
which means you simulate once and analyse many times. Testing the rotation
against a dozen mismatch distributions then costs one simulation rather than
twelve.

The measurement itself: sum the element lines exactly as the resistors will,
take an FFT, and read in-band signal-to-noise and distortion. Deliberately
mismatch the weights to confirm the rotation converts that into out-of-band
noise rather than in-band distortion. Separately, drive word drops on the
bridge side to exercise tag resync.

**Verilator is two-state**, so it will not show X propagation and will happily
simulate a design whose reset is incomplete. Do not rely on it to catch
uninitialised state.

## Build

```
tools/synth.sh <toplevel> [sources...]
```

Yosys with `synth_gatemate`, then nextpnr-himbaechel. The script stops after
synthesis with a message when place-and-route is unavailable, which keeps it
useful for resource counts.

## Clock routing, and the one pinout constraint

The global mesh is driven from a mux fed by the PLL block, so a clock does not
reach it by an independent route. The bypass path exists and the open toolchain
uses it automatically, but not through the port the datasheet suggests.

**The recipe.** Put the clock on one of the four dedicated clock-capable pins,
`CLK0` to `CLK3`, instantiate a `CC_BUFG` driven by that pad, and do not
instantiate a PLL on it. nextpnr sees the pad is clock-capable and wires the
CLKIN reference straight into the GLBOUT mux, so the clock reaches the global
mesh without passing through the VCO.

**The trap.** `CC_PLL` declares a `CLK_REF_OUT` port, matching the datasheet,
but nextpnr rejects it outright: *"Output CLK_REF_OUT cannot be used if PLL is
used."* The bypass belongs to the CLKIN-to-GLBOUT path, not to a configured
PLL. Do not try to reach it that way.

**The constraint this puts on the pinout.** If the clock lands on an ordinary
pin rather than a clock-capable one, the packer silently falls back to routing
it through the fabric as a user global, which adds exactly the jitter the
bypass avoids. It is not an error, so nothing will tell you. Both `MCLK` and
the FT601Q clock must be assigned to dedicated clock pins.

**No PLL is needed anywhere in this design.** Neither clock requires frequency
synthesis, since the sample rate is a divided enable inside the `MCLK` domain
rather than a clock of its own. All four PLLs stay unused and both clocks
bypass straight to the mesh.

Verified against the Yosys GateMate blackbox library and the nextpnr GateMate
clock packer, not just the datasheet.



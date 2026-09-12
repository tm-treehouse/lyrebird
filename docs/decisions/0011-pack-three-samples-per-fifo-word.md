# 0011 — Pack three samples per 80-bit FIFO word

**Status:** accepted. Corrects the buffer sizing in
[0010](0010-192khz-and-control-word.md).

## Context

[0010](0010-192khz-and-control-word.md) concluded that a 100 ms prefill at
192 kHz needed 38 block RAMs against 32 available, and therefore did not fit.
That conclusion followed from a packing choice made earlier without examining
it, not from a limit of the part.

The block RAM FIFO controller offers two usable geometries in the 40K
configuration the FIFO mode requires:

| Mode | Width | Depth | 24-bit samples per block |
| --- | --- | --- | --- |
| TDP 40K | 40 bits | 1,024 | 1,024, one per entry |
| SDP 40K | 80 bits | 512 | 1,536, three per entry |

The original specification used the first, storing one 24-bit sample in a
40-bit entry and wasting 40 percent of every word.

## Decision

Use **SDP 40K mode, 80 bits wide, three samples per word.** Seventy-two of the
80 bits carry audio, so the packing is 90 percent efficient and yields half
again as many samples from the same memory.

| Prefill | 96 kHz | 192 kHz |
| --- | --- | --- |
| 50 ms | 7 blocks | 13 blocks |
| 100 ms | 13 blocks | 25 blocks |

The specified 100 ms at 192 kHz lands on exactly 25 of 32 blocks. Committing
every block would reach 128 ms at 192 kHz.

## Consequences

**A packer and an unpacker.** The write side assembles three samples per word,
the read side distributes them. A small shift register each way.

**Read granularity is three samples.** The Fs-domain side reads a word every
third sample tick rather than every tick. Sample parity, and therefore left
versus right, is tracked by a counter rather than by word boundaries, since
three samples is one and a half frames.

**Only static fill offsets.** SDP mode does not support the dynamic
almost-full and almost-empty offset inputs that TDP does. That is what a fixed
prefill threshold wants anyway.

**Seven blocks stay free**, and nothing else in the design wants meaningful
block RAM. Interpolator delay lines and coefficients together come to well
under one block.

## Rejected: external memory

An external SRAM for headroom was considered and rejected. Prefill is latency,
so a larger buffer is a cost rather than a benefit, and host scheduling jitter
runs one to two orders of magnitude below 100 ms. The requirement is bounded by
tolerable delay, not by available memory.

The costs were also real: roughly 38 signals, about as many as the entire
bridge bus, a memory controller in fabric where the part has no hard one, and
the loss of the block RAM FIFO's hardware dual-clock operation, fill flags and
pointers. That last would mean reimplementing the clock-domain crossing in
fabric, which is the part of this design most likely to hide a subtle bug.

A quad-SPI pseudo-static RAM would need six pins instead of 38 if the
requirement ever changes. Whether to provision an unpopulated footprint is
open.

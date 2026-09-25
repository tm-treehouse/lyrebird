# 0002 — The FPGA owns the audio clock

**Status:** accepted, with two corrections below.

> **Corrections, 2026-09-25.** Two statements in this record no longer match
> the design, and neither was noticed until the documents were audited against
> the netlists.
>
> **The oscillator frequencies named here are the element clock, not the
> parts.** This record says 22.5792 MHz and 24.576 MHz. Those are what reaches
> the registers; [0012](0012-module-clock-architecture.md) fits **45.1584 MHz
> and 49.152 MHz** parts and divides by two on the module, because absolute
> jitter scales inversely with carrier frequency and dividing keeps the edges.
> The principle this record establishes — that the FPGA owns the audio clock
> and the host does not — is untouched.
>
> **The crossing FIFO is sized an order of magnitude low.** "A few thousand
> samples" here against [0011](0011-pack-three-samples-per-fifo-word.md)'s
> **38,400**, which is what a 100 ms buffer at 192 kHz actually needs. 0011 is
> the number; this was written before the buffer was sized.

## Context

USB delivers data in bursts on a 1 ms frame schedule. A DAC needs samples at
exactly Fs, forever, with no gaps. These two facts are in direct conflict and
this is the load-bearing constraint of the whole design.

## Decision

A clean on-board oscillator drives the sample rate, divided down to Fs. The
host is a data source with no say in timing.

- 22.5792 MHz for the 44.1 kHz family
- 24.576 MHz for the 48 kHz family

Between the FTDI interface and the sample-rate domain sits a BRAM FIFO a few
thousand samples deep. The FPGA asserts `RD#` only on its own sample tick.

## Consequences

Backpressure propagates for free and needs no protocol: the BRAM FIFO fills,
the FTDI buffer fills, the host write blocks. No rate negotiation, no feedback
endpoint, no clock recovery from the USB frame timing.

Prefill 50 to 100 ms before starting the output tick, so ordinary host
scheduling jitter cannot cause an underrun.

Deriving Fs from the bridge's FIFO clock was never an option. It is a USB-domain
clock with USB-domain jitter, and audio quality would follow it.

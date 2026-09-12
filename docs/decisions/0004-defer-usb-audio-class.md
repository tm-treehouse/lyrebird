# 0004 — Defer USB Audio Class support

**Status:** accepted, revisit after bring-up

## Context

The FTDI path requires custom host software. A user cannot simply select the
device as an output in their sound settings.

## Decision

Accept custom host software for now. Defer driverless operation.

## If it is wanted later

A USB Audio Class 2.0 bridge providing I2S plus a master clock, driverless on
Linux and macOS: an Amanero Combo384, or an XMOS board.

That path is strictly worse during bring-up. It hides the wire format behind a
compliant device, and the entire point of the current phase is exact control
over the bit pattern reaching the FPGA. Revisit once the FIFO read interface,
the deserializer, and the clock-domain crossing are all proven.

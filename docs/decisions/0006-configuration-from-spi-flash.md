# 0006 — Configure from SPI flash, program over a separate header

**Status:** accepted. Resolves the open question left by
[0005](0005-ft601q-bridge-io-voltage.md).

## Context

Moving to the FT601Q removed the MPSSE engine that was going to serve as the
JTAG cable, so the board needs its own configuration path. Reprogramming is a
development activity, not something normal use requires.

## Decision

Fit an SPI flash and strap `CFG_MD[3:0]` for **SPI Active mode**, where the
FPGA reads its own bitstream from flash at reset with no host involvement.

Bring out a **separate programming header** for development. openFPGALoader
drives GateMate over an ordinary external FTDI adapter, so no programming
silicon needs to live on this board.

## Consequences

Normal operation needs one cable and no programmer. The board comes up
configured whether or not a host is attached.

The bitstream path stays entirely off the audio USB interface, so a stalled or
crashed host cannot affect configuration, and reprogramming cannot disturb a
running stream.

Size the flash with headroom rather than to a measured figure; confirm the
actual bitstream size from a first build before committing the part.

FPGA configuration now draws current at power-on, before any USB enumeration
completes. That interacts with the board's power budget and is treated there.

Rejected: putting a second FTDI part on the board purely for JTAG. It adds
cost, area, and a USB device that exists only for a task performed rarely, when
an external adapter does the same job.

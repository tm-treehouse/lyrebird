# 0005 — FT601Q bridge, forced by GateMate I/O voltage

**Status:** accepted. Supersedes the part selection in
[0001](0001-ftdi-bridge-over-ulpi-phy.md); the reasoning in 0001 for choosing
an FTDI bridge over a ULPI PHY still stands.

## Context

The target FPGA is a Cologne Chip GateMate CCGM1A1. Its single-ended GPIO
support LVCMOS up to 2.5 V, and the absolute maximum on VDDIO is 2.75 V. The
FT2232H has no I/O voltage option at all: VCCIO is specified 2.97 to 3.63 V and
its outputs sit above 3.1 V.

Wiring an FT2232H directly to a GateMate exceeds the absolute maximum rating on
every signal. This is a damage condition, not a noise-margin argument.

| Rail | Spec |
| --- | --- |
| GateMate GPIO, LVCMOS | 1.2 to 2.5 V |
| GateMate VDDIO absolute max | 2.75 V |
| FT2232H VCCIO operating | 2.97 / 3.30 / 3.63 V |
| FT2232H output high, typical | 3.14 to 3.22 V |

## Decision

Use the **FT601Q** and run both its VCCIO and the GateMate GPIO banks from a
single 2.5 V rail. The FT601Q supports 1.8, 2.5, and 3.3 V I/O, so the two
parts connect directly with no level translation.

Run the FIFO bus at **66.67 MHz**, not the available 100 MHz. Bandwidth is not
remotely the constraint here, and the slower clock buys timing margin on a
43-signal bus into a modest FPGA.

## Rejected alternatives

- **Level translators on the FT2232H.** A fast bidirectional part on the eight
  data lines plus unidirectional parts on the control lines. It works, but it
  spends propagation delay out of the tightest budget on the board and adds the
  highest-risk timing path to a first spin, purely to keep a part that is
  already being replaced on its own upgrade path.
- **A 3.3 V-tolerant FPGA.** Lattice ECP5 or iCE40 would take the FT2232H
  directly. Rejected because the FPGA choice is the fixed input here.

## Consequences

**The bus is wider and faster.** 32-bit DATA plus BE[3:0], against 8-bit
before. Roughly 43 signals to the FPGA instead of 15. Still comfortable against
162 available GPIO, but no longer a rounding error, and it argues for a ground
plane rather than trusting the vendor's two-signal-layer claim.

**The framing rationale shifts.** On a 32-bit bus with all byte enables
asserted, a padded sample is exactly one bus word and word boundaries are
preserved by the interface. The single-dropped-byte failure mode from
[0003](0003-self-describing-sample-framing.md) largely disappears. Keep the
tag bytes anyway: they still recover L/R alignment if a whole word is lost, and
they remain a nearly free integrity check.

**The integrated programming cable is lost.** The FT2232H plan used channel B
in MPSSE mode for JTAG, so one part covered both the data path and programming.
The FT601Q has no MPSSE and only two GPIO. The board now needs its own
configuration path. GateMate offers SPI Active, SPI Passive, and JTAG, selected
by strapping CFG_MD[3:0]. The likely answer is an SPI flash for boot plus a
JTAG header for development. Decided in
[0006](0006-configuration-from-spi-flash.md).

**The host driver changes.** D3XX, not D2XX. See
[0001](0001-ftdi-bridge-over-ulpi-phy.md) for what has not changed: the device
still does not enumerate as a sound card.

**The board is harder.** USB 3.0 SuperSpeed differential pairs need controlled
impedance, and the part is QFN-76 rather than LQFP-64.

# 0001 — FTDI bridge instead of a ULPI PHY

**Status:** accepted; part selection superseded by [0005](0005-ft601q-bridge-io-voltage.md)

## Context

The FPGA needs to receive a USB audio stream. The obvious analogy is Ethernet,
where an external PHY handles the analog layer and the MAC lives in the fabric.

## Decision

Use an FT2232H in 245 Synchronous FIFO mode. The FPGA sees an 8-bit FIFO with
a 60 MHz clock and a four-signal handshake, and needs no USB knowledge at all.

## Rejected alternatives

- **ULPI PHY (USB3300, TUSB1210).** The true analog of an Ethernet PHY, but it
  only moves the analog layer off-chip. A USB device controller, endpoint
  management, and enumeration all still have to exist in the fabric. That is
  the expensive part.
- **Cypress FX3.** Requires ARM9 firmware plus a GPIF II state machine. Two
  more toolchains and two more things to debug during bring-up.

## Consequences

The device is not a USB Audio Class device, so it will not enumerate as a sound
card and a custom host program is required. That is accepted for bring-up
because it gives exact control over the bit pattern on the wire. See
[0004](0004-defer-usb-audio-class.md).

Upgrade path if bandwidth ever binds: FT600/FT601, 16 or 32-bit FIFO, same
programming model. Downgrade if JTAG comes from elsewhere: FT232H, single
channel, same FIFO mode.

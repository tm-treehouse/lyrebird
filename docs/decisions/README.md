# Architecture decisions

One file per decision, numbered, never rewritten. If a decision is reversed,
add a new record that supersedes the old one and leave the original in place.
The reasoning is worth more than the conclusion.

What is *not* decided lives in [../open-items.md](../open-items.md).

| # | Decision |
| --- | --- |
| [0001](0001-ftdi-bridge-over-ulpi-phy.md) | FTDI bridge instead of a ULPI PHY. Part selection superseded by 0005 |
| [0002](0002-fpga-owns-the-audio-clock.md) | The FPGA owns the audio clock. Oscillator placement refined by 0007 |
| [0003](0003-self-describing-sample-framing.md) | Self-describing sample framing. Rationale revised by 0005 |
| [0004](0004-defer-usb-audio-class.md) | Defer USB Audio Class support |
| [0005](0005-ft601q-bridge-io-voltage.md) | FT601Q bridge, forced by GateMate I/O voltage |
| [0006](0006-configuration-from-spi-flash.md) | Configure from SPI flash, program over a separate header |
| [0007](0007-two-board-split-at-i2s.md) | Two boards, split at I2S. Reasoning now depends on 0008's reclocker |
| [0008](0008-multibit-delta-sigma-with-dwa.md) | Multi-bit delta-sigma with dynamic element matching. No DAC chip |
| [0009](0009-usb-bus-power.md) | USB bus power, and which rails are precision |
| [0010](0010-192khz-and-control-word.md) | 192 kHz support and an in-band control word. Buffer sizing corrected by 0011 |
| [0011](0011-pack-three-samples-per-fifo-word.md) | Pack three samples per 80-bit FIFO word |
| [0012](0012-module-clock-architecture.md) | Module clock architecture and a 3.3 V element rail. Supersedes 0008's 2.5 V rail |

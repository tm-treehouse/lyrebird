# USB Audio Path — Context Handoff

Context for a Claude Code session. Goal: stream PCM audio from a host PC to an
FPGA over USB, with no USB IP in the fabric.

## Architecture decision

Host PC → FTDI bridge (USB device controller + endpoints in silicon) → 8-bit
synchronous FIFO → FPGA → I2S/parallel → DAC.

A ULPI PHY (USB3300, TUSB1210) was rejected: it is the true analog of an
Ethernet PHY, but still requires a USB device controller in the fabric. The
FTDI bridge presents a dumb FIFO instead, so the FPGA needs no USB knowledge.

## Part selection

- **FT2232H** — primary choice. Channel A in 245 Synchronous FIFO mode,
  channel B in MPSSE mode for JTAG programming. One part covers both the data
  path and the programming cable.
- FT232H — same FIFO mode, single channel, if JTAG comes from elsewhere.
- FT600/FT601 — the USB 3.0 upgrade path, 16/32-bit FIFO, same programming
  model, if bandwidth ever becomes the constraint.
- FX3 — rejected for now. Requires ARM9 firmware plus a GPIF II state machine.

## FIFO interface (245 Sync mode)

- CLKOUT is 60 MHz, driven by the FTDI chip. All FPGA-side logic in this
  domain, or cross into it cleanly.
- Signals: DATA[7:0], RXF#, TXE#, RD#, WR#, OE#, SIWU#.
- Sustained throughput ~35–40 MB/s.

## Clocking — the load-bearing constraint

USB delivers in bursts; the DAC needs samples at exactly Fs. **The FPGA owns
the audio clock, not the host.**

- Clean audio oscillator: 22.5792 MHz (44.1 kHz family) or 24.576 MHz
  (48 kHz family), divided down to Fs.
- BRAM FIFO a few thousand samples deep between the FTDI interface and the
  sample-rate domain.
- The FPGA asserts RD# only on its own sample tick. Backpressure then
  propagates for free: BRAM FIFO fills → FTDI buffer fills → host write blocks.
- Prefill 50–100 ms before starting the output tick, so host scheduling jitter
  cannot cause an underrun.

## Framing

The sync FIFO is a raw byte stream with no packet boundaries. A single dropped
byte permanently swaps L/R, so samples are self-describing:

- Pad each 24-bit sample to 32 bits.
- Tag byte in the MSB position: `0xA5` = left, `0x5A` = right.
- FPGA resyncs by hunting for a valid tag if the expected one does not appear.

Bandwidth check: 2ch / 24-bit / 96 kHz = 576 kB/s raw, 768 kB/s padded, against
~35 MB/s available. The overhead is free.

## Host side

The FTDI chip is **not** a USB Audio Class device — the OS will not enumerate
it as an output. A host program must open a D2XX or libftdi handle and write
raw PCM.

- Bench bring-up: read a WAV file, `FT_Write()` the PCM.
- Real playback: capture a loopback device and forward it. Linux — PipeWire
  null sink plus its monitor source. Windows — WASAPI loopback or VB-Cable.
- Use ~64 kB writes, `FT_SetUSBParameters` with a large transfer size, and
  overlapped/async writes so the pipe never drains.

## Deferred

If the device should later appear as a normal sound card with no custom host
software, that is a USB Audio Class 2.0 bridge (Amanero Combo384, or an XMOS
board) providing I2S plus a master clock, driverless on Linux and macOS. FTDI
remains the better choice during bring-up because it gives exact control over
the bit pattern on the wire.

## Suggested first tasks for the session

1. FPGA-side 245 Sync FIFO read interface (RXF#/RD#/OE# handshake, 60 MHz).
2. Byte-to-sample deserializer with tag hunting and resync.
3. Async FIFO crossing from the 60 MHz FTDI domain to the Fs domain.
4. Host-side WAV pump against the D2XX API.
5. Cocotb testbench driving the FTDI-side signals, including deliberate byte
   drops to exercise resync.

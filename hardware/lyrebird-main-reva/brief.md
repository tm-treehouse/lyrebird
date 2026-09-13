# lyrebird-main-reva — board brief

The digital half of a two-board USB DAC. One USB 3.0 cable in, a 32-bit
thermometer element bus out to a mezzanine header. No analog on this board.

The split is [0007](../../docs/decisions/0007-two-board-split-at-i2s.md); the
contract across the header is [interface.md](../interface.md).

## What it must do

- **Bridge USB to a parallel FIFO.** FT601Q in 245 Synchronous FIFO mode,
  32-bit DATA plus BE[3:0] and six handshake lines, 42 signals plus the clock,
  at 66.67 MHz. Not a USB Audio Class device; a custom D3XX host program drives
  it ([0001](../../docs/decisions/0001-ftdi-bridge-over-ulpi-phy.md),
  [0004](../../docs/decisions/0004-defer-usb-audio-class.md),
  [0005](../../docs/decisions/0005-ft601q-bridge-io-voltage.md)).
- **Run the whole digital interface at 2.5 V.** GateMate GPIO are LVCMOS with
  an absolute maximum VDDIO of 2.75 V and are not 3.3 V tolerant. The FT601Q is
  on this board because its VCCIO can be set to 2.5 V, so the two parts connect
  with no translators. All nine GPIO banks and VDD_CLK sit on that rail.
- **Synthesise the audio.** The CCGM1A1 runs the interpolation chain, the
  three-bit delta-sigma modulator and the dynamic element matching rotation,
  and drives 32 element lines — 28 used, 4 reserved and driven low
  ([0008](../../docs/decisions/0008-multibit-delta-sigma-with-dwa.md),
  [0010](../../docs/decisions/0010-192khz-and-control-word.md),
  [0011](../../docs/decisions/0011-pack-three-samples-per-fifo-word.md)).
- **Take its audio clock back from the module.** MCLK arrives on the header from
  the module's oscillator chain and must land on a clock-capable ball. It does:
  CLK1/IO_SB_A7. The bridge clock lands on CLK0/IO_SB_A8. A clock on an ordinary
  ball is not a toolchain error, it silently routes through the fabric, so the
  assignment is asserted in the generator rather than hoped for.
- **Configure itself.** CFG_MD[3:0] strapped to 0b0000 — SPI Active, CPOL 0,
  CPHA 0 — so the FPGA reads its bitstream from an on-board SPI flash at reset
  with no host involvement. A separate header carries JTAG for development
  ([0006](../../docs/decisions/0006-configuration-from-spi-flash.md),
  [0013](../../docs/decisions/0013-simulation-and-build-toolchain.md)).
- **Power itself and the module from the bus.** 5 V passes through to the
  mezzanine; 3.3 V, 2.5 V and 1.0 V are generated here
  ([0009](../../docs/decisions/0009-usb-bus-power.md)). See
  [power.md](power.md).
- **Detect an absent module.** ID0 and ID1 are pulled to ground through 10 k, so
  0b00 means nothing is fitted.

## What it deliberately does not do

- **No analog, and nothing on it is analog-grade.** Every rail here is reclocked
  away by flip-flops on the module, so main-board switching noise never reaches
  the signal. That is what permits conventional regulation throughout.
- **No DAC chip.** The FPGA is the modulator; the module is the converter.
- **No audio oscillator.** Both oscillators live on the module, next to the
  registers whose edges become the output. Only the FPGA's copy of the clock
  crosses the connector, and jitter on that copy is harmless because it only
  gates FIFO reads.
- **No level translation toward the module.** The translator lives on the
  module so the mezzanine never carries 3.3 V
  ([0012](../../docs/decisions/0012-module-clock-architecture.md)).
- **No analog signal on the connector.** The split is placed in the digital path
  on purpose.
- **No programming silicon.** openFPGALoader over an external FTDI adapter.
- **No external power input.** A second supply means a second ground reference
  next to USB ground.
- **No volume, mute or rate control hardware.** All of it is digital, inside the
  FPGA, commanded by in-band control words.
- **No external memory.** The elastic buffer is 25 of 32 block RAMs.

## Where the board actually is

The netlist generator runs and emits `lyrebird-main.net`. It contains three
active devices (CCGM1A1, FT601Q, LT3045), one 2x40 header, 80 decoupling
capacitors and two pull-downs, and leaves **111 pins unconnected**.

The 1.0 V and 2.5 V rails have no source: the LTM4622 chosen in
[0009](../../docs/decisions/0009-usb-bus-power.md) is not in the netlist. There
is also no USB connector, no crystal, no SPI flash and no programming header.
[missing.md](missing.md) is the full list, including three wiring defects that
are worse than omissions.

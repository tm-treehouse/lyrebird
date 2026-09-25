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
- **Power itself and the module from a 12 V supply.** A barrel jack feeds a
  fuse, reverse-polarity and transient protection, then two LMR33630s: one
  makes 5 V for everything, the other inverts to −6 V for the module's analog
  stage. 3.3 V, 2.5 V and 1.0 V are generated from the 5 V here, and the
  mezzanine carries +5V and −6V
  ([0014](../../docs/decisions/0014-wall-wart-power.md), superseding 0009).
  See [power.md](power.md).
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
- **No second power input.** The board takes one 12 V supply. A *further*
  supply on the module is 0009's deferred answer for a headphone stage needing
  real power, and it stays deferred — two bricks means two grounds and a loop
  between them.
- **No volume, mute or rate control hardware.** All of it is digital, inside the
  FPGA, commanded by in-band control words.
- **No external memory.** The elastic buffer is 25 of 32 block RAMs.

## Where the board actually is

The netlist generator runs clean and emits `lyrebird-main.net`: **159
components, 142 nets**. Seven active devices (CCGM1A1, FT601Q, LT3045,
LTM4622, two LMR33630s, MX25R6435F), three connectors, three diodes, a fuse,
two inductors, a crystal and the passives.

Everything the first pass listed as missing is fitted. The 1.0 V and 2.5 V
rails come from the LTM4622; the USB receptacle, the crystal, the SPI flash and
the JTAG header are all in. Both the schematic and the BOM are generated from
the netlist now, so neither can drift again without
`hardware/check_freshness.py` saying so.

Verified rather than asserted: a build-time assertion fails if any net above
2.75 V can reach an FPGA pin, tamper-tested; `hardware/verify_power.py` runs
the power arithmetic in 13 checks; `hardware/sim/power_input_transient.py`
covers inrush, reverse polarity, the wrong adapter and rail sequencing in 20
checks with 7 tampers.

[missing.md](missing.md) records the original gap list and the three wiring
defects found while closing it, all fixed: `AVDD` on a 3.3 V rail when it is a
1.0 V PLL supply with a 1.4 V maximum, every LT3045 `SET` pin left open so no
rail had a programmed voltage, and the bridge's FIFO mode straps unstrapped.

**What is not done: layout.** The `.kicad_pcb` holds placed footprints from the
netlist import and zero tracks. That is the largest remaining block of work on
this board and none of it has begun.

# lyrebird-dac-reva — board brief

The analog half of a two-board USB DAC. A 32-bit thermometer element bus in on
a mezzanine header, a line-level signal out. No USB, no FPGA, and no DAC chip:
the FPGA runs the modulator, and this board is the converter.

The split is [0007](../../docs/decisions/0007-two-board-split-at-i2s.md); the
contract across the header is [interface.md](../interface.md).

## What it must do

- **Own the audio clock.** Two Crystek CCHD-957 oscillators, 49.152 MHz for the
  48 kHz family and 45.1584 MHz for the 44.1 kHz family, exactly one running.
  Two parts are required because the families sit at 147 to 160, which no
  divider bridges. Standby shuts the resonator down rather than gating the
  output, at 1.5 mA, so an idle part does not radiate next to the analog
  section ([0012](../../docs/decisions/0012-module-clock-architecture.md)).
- **Divide by two and fan out.** The element clock is 24.576 or 22.5792 MHz.
  The 1024 multiple is bought for jitter — time jitter scales inversely with
  carrier — and for margin: 16 ns of round trip through the translator leaves
  about 24 ns against the divided period and about 4 ns against the undivided
  one. The buffer has to reach two register packages and the header with tight
  skew, so the divider lives in it.
- **Reclock every element line.** This is the architecture. The flip-flop
  replaces the FPGA's clock mesh, its output drivers and its I/O rail all at
  once: the clock becomes the oscillator's, the swing becomes full scale, and
  the drivers become one type on one die
  ([0008](../../docs/decisions/0008-multibit-delta-sigma-with-dwa.md)).
  One 16-bit package per channel, 14 elements, both polarities on one die,
  decoupled at the package because that supply pin is where the element
  switching current comes from.
- **Be the voltage reference.** The register supply *is* full scale, so its
  noise is multiplicative rather than additive. About 10 uV across the audio
  band on 3.3 V for a 110 dB dynamic range. The regulator sets DC and
  low-frequency noise; local ceramics carry the rest, because no regulator loop
  reaches the modulator rate. Neither substitutes for the other.
- **Sum 28 elements through matched resistors.** Seven per polarity per
  channel, thin film. Rotation makes 1 % adequate — measured at 0.5 dB against
  70 dB without it ([model](../../model/README.md)) — but it does not fix
  voltage coefficient within one resistor, which is why thin film is specified
  and must not be substituted away.
- **Filter passively before the op amp.** Shaped noise is still there, above
  the band. An op amp asked to slew on it intermodulates it back down. The
  summing resistors are already in the path, so a shunt capacitor at each node
  buys the first pole for one part.
- **Translate only the FPGA's leg of the clock.** 74AVC4T245, `VCC(A)` at
  2.5 V toward the connector and `VCC(B)` at 3.3 V toward the module, carrying
  `MCLK` out and the two oscillator enables in. Its partial power-down
  behaviour earns its place on a mezzanine where a module may be absent.
- **Regulate its own rails from the +5 V it is handed.** The header carries
  unregulated bus voltage and nothing else. See [power.md](power.md).
- **Identify itself.** `ID0`/`ID1` strapped 0b01, line output only.

## What it deliberately does not do

- **No DAC chip, no oversampling filter, no I2S.** Element lines instead.
- **No translators on the element lines.** Twenty-eight of them would be seven
  more packages injecting skew into exactly the signals where skew behaves like
  element mismatch. The register's 2.0 V input threshold at 3.3 V does the work,
  which is what constrains the logic family.
- **No 3.3 V toward the main board.** Nothing there tolerates above 2.75 V.
  The translator sits on this side of the boundary for that reason alone.
- **No PLL and no clock synthesis.** A loop in the master clock path would undo
  the reason for buying a good oscillator. MEMS and programmable parts were
  rejected for the same reason.
- **No volume, mute or rate hardware.** All digital, in the FPGA, commanded by
  in-band control words ([0010](../../docs/decisions/0010-192khz-and-control-word.md)).
  `MUTE_N` arrives as a signal for the output stage, not as a control panel.
- **No analog on the connector.** The split is in the digital path on purpose.
- **No headphone amplifier on this variant.** A headphone stage driven hard
  adds roughly 200 mA and does not fit a USB 2.0 host
  ([0009](../../docs/decisions/0009-usb-bus-power.md)).
- **No external power input.** Deferred to a module that genuinely needs one,
  which is the right place for a second ground reference.

## Where the board actually is

The netlist generator runs and emits `lyrebird-dac.net`. As generated on
2026-09-12 it contains 28 components — 4 register stand-ins, 2 oscillators, 4
resistor arrays, 3 LT3045/LT3094 regulators, the translator, a divider
stand-in, an op amp stand-in, one 2x40 header, 10 capacitors and one
pull-down — and leaves **57 of 293 pins unconnected**.

Four things are worth knowing before reading it. Two put 3.3 V on the 2.5 V
mezzanine: the element reference rail is tied straight to the `ID0` strap, and
the divided clock reaches the header from the 3.3 V divider rather than through
the translator's 2.5 V side, which has no signal connections at all. The
summing nodes `SUM_P` and `SUM_N` are one net, because the stock
`R_Network08` is a bussed array rather than eight isolated resistors. And the
registers' clock inputs are open, so the element clock leaves the board without
ever reaching a flip-flop.

Three of the four placeholder symbols named in
[../netlist/README.md](../netlist/README.md) are on this board, and the fanout
divider, the 16-bit register, the op amp, the charge pump and the element
resistor value have never been chosen at all
([open-items.md](../../docs/open-items.md)). [missing.md](missing.md) is the
full list, generated from a fresh netlist run rather than from this page.

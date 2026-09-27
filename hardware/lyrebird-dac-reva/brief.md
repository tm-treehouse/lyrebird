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
- **Regulate its own rails from what the header hands it.** The mezzanine
  carries **+5V and −6V** and nothing else. Four LT3045s make the reference,
  clock, translator and positive analog rails from the 5 V; an LT3094 makes
  −5 V from the −6 V. There is no switching converter on this board
  ([0014](../../docs/decisions/0014-wall-wart-power.md)). See
  [power.md](power.md).
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

The netlist generator runs clean and emits `lyrebird-dac.net`: **112
components, 133 nets**, with 12 pins deliberately open and each of them
tabulated with a reason in [parts-notes.md](parts-notes.md).

Every part is chosen, and every one against a datasheet rather than by
resemblance: OPA1612AID amplifiers, SN74ALVCH16374DGGR registers, an
SN74LVC1G74 divider with an LMK1C1104 fanout, Crystek CCHD-957 oscillators,
LT3045 and LT3094 regulators, an SJ1-3523N jack, and 3.34 kΩ elements as
1.69 k + 1.65 k split around 180 pF. What could not be verified says so.

The four wiring defects the first pass found are fixed, and they are worth
listing because they are the class of error a netlist review exists for: the
element reference rail was tied to the `ID0` strap and the divided clock
reached the header without passing through the translator, both putting 3.3 V
on 2.5 V pins; the two summing nodes were one net, because the stock
`R_Network08` is a bussed array rather than isolated resistors, which made the
whole thing a mono mixer; and the registers' clock inputs were open, so the
element clock left the board without ever reaching a flip-flop. A build-time
assertion now fails on the overvoltage class of that list, and it is
tamper-tested.

**The charge pump is gone.** It was chosen, verified and wired, and [0015](../../docs/decisions/0015-negative-rail-across-the-mezzanine.md)
deleted it before it was ever built — the negative rail now crosses the
mezzanine from the main board, where 12 V makes an inverter cheap. That took
16 parts off this board and recovered the 2.1 dB the 604 Ω difference network
had cost.

Two things remain open on this board specifically. The **Crystek footprint's
pad numbering is rotated 90°** against the datasheet's bottom view, which is
the one defect here that would stop a board working; the pad geometry is
confirmed correct and only the numbering is wrong, and the two candidate fixes
differ by a mirror, so it wants the drawing in front of a person. And the
**difference amplifier loads the two halves unequally**, measured at 1.499 : 1
in output current with the positive half crossing zero inside the signal —
open item D3, a decision for 0008 rather than a fix.

**What is not done: layout.** Zero tracks. [missing.md](missing.md) records the
original gap list and how it closed.

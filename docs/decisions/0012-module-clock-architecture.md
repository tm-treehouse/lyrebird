# 0012 — Module clock architecture and a 3.3 V element rail

**Status:** accepted. Supersedes the 2.5 V element rail assumed in
[0008](0008-multibit-delta-sigma-with-dwa.md).

## Context

The reclocking registers strike the edges that become analog output
transitions, so the clock reaching them is the single most jitter-sensitive
signal in the design. The reclock does not reduce jitter, it substitutes the
oscillator's timing for the FPGA's, so the oscillator's quality is what ends up
audible.

Two candidate oscillators were rejected for the same reason: a MEMS part and a
programmable part, both of which synthesise their output through an internal
fractional-N loop rather than resonating at the output frequency. Neither
reaches the sub-picosecond range that fixed quartz does.

Separately, [0008](0008-multibit-delta-sigma-with-dwa.md) assumed the element
reference rail was 2.5 V to match the header logic level, without examining
whether it had to be.

## Decision

### Oscillators at the 1024 multiple, divided by two

| Oscillator | Family | Divided element clock |
| --- | --- | --- |
| 49.152 MHz | 48 kHz | 24.576 MHz |
| 45.1584 MHz | 44.1 kHz | 22.5792 MHz |

Two parts are required because the families sit at a ratio of 147 to 160, which
no divider bridges. A single clock at a common multiple of 7.056 MHz would
divide to both by integer division, but the divisors are not powers of two and
that destroys the half-band cascade, replacing it with a rational resampler.

**Part: Crystek CCHD-957**, ±25 ppm, −40 to +85 °C. Its phase noise plots are
taken at exactly 45.1584 and 49.152 MHz, which are the manufacturer's own
characterisation points. Integrating the −169 dBc/Hz floor across 12 kHz to
20 MHz against a 49.152 MHz carrier gives roughly 73 fs, so real performance
lands in the low hundreds of femtoseconds against a 1 ps target.

Its standby mode shuts the resonator down rather than only tri-stating the
output, which is what the one-oscillator-at-a-time rule actually needs: an idle
oscillator next to the analog section radiates a spur regardless of whether its
output is connected. Standby draws 1.5 mA, so both parts fitted cost about
17 mA together.

### Why the 1024 multiple rather than 512

**Availability.** 45.1584 and 49.152 MHz are the most widely stocked audio
clock frequencies.

**Lower absolute jitter.** For a given phase noise profile, jitter expressed in
time scales inversely with carrier frequency. The Epson datasheet showed this
on one part: roughly 31 ps in the 10 to 20 MHz band against roughly 3 ps at 125
to 170 MHz. Dividing retains every other edge with its timing intact, so the
divided clock inherits the higher carrier's lower jitter plus a small additive
contribution.

**Round-trip timing.** With a translator in the clock path to the FPGA, the
delay from launching edge to data arriving at the module register is about
16 ns. Against 40.7 ns at 24.576 MHz that leaves roughly 24 ns of setup margin.
At 49.152 MHz the period is 20.3 ns and the margin would be about 4 ns, which is
not a basis for a first board.

### The 3.3 V element reference rail

Good audio oscillators are 3.3 V parts, so the module clock domain is 3.3 V and
the element reference rail moves with it. Full scale rises from 2.5 to 3.3 V,
worth about 2.4 dB of output, and the noise target for a 110 dB dynamic range
relaxes from roughly 8 uV to roughly 10 uV.

**This constrains the register logic family.** The registers sit on the 3.3 V
rail but their data inputs are driven at 2.5 V by the FPGA. Choose a family
whose input threshold is 2.0 V at a 3.3 V supply, which accepts the 2.4 V the
FPGA guarantees with margin. A family referencing its threshold to 0.7 times
the supply would sit at 2.31 V and be marginal.

**The element lines are not translated.** Twenty-eight translators would be
seven more packages injecting skew into exactly the signals where skew behaves
like element mismatch. The register's input threshold does the work instead.

### The jitter rule

**Never translate the register leg. Translate the FPGA leg freely.**

The registers take the short, clean, untranslated path: oscillator, divider,
fanout, registers, all on one rail. The FPGA's copy is retimed downstream by
those same registers, so jitter on it never reaches the output and only has to
meet setup and hold against a 40.7 ns period.

A fanout buffer is required regardless, because the clock must reach two
register packages and the FPGA with tight skew. Put the divider in it.

### Translator: 74AVC4T245

One package, configured as two independent 2-bit transceivers. `VCC(A)` at
2.5 V faces the connector, `VCC(B)` at 3.3 V faces the module.

| Signal | Bank | Direction | Strap |
| --- | --- | --- | --- |
| Element clock to FPGA | 1 | B to A | `1DIR` low, `1OE` low |
| `OSC_EN_48` | 2 | A to B | `2DIR` high, `2OE` low |
| `OSC_EN_441` | 2 | A to B | same |
| spare | 1 | — | — |

Verified against the datasheet function table: output enable is active low, and
direction low passes B to A while direction high passes A to B. The A pins,
direction and output enable are all referenced to `VCC(A)`, so strap them to the
2.5 V rail or ground, never to 3.3 V. Both supplies accept 0.8 to 3.6 V with no
ordering constraint. Rated 380 Mbit/s for this translation class, against about
13 percent utilisation here.

**It lives on the module**, so the A side faces the connector and the mezzanine
stays at 2.5 V per
[interface.md](../../hardware/interface.md). Reversing it would put 3.3 V on the
main board.

Its partial power-down behaviour earns its place: with either supply at ground
both ports go high impedance and internal circuitry prevents backflow. On a
mezzanine where a module may be absent or unpowered while the main board runs,
that protects the FPGA, which is the one part here that cannot tolerate
overvoltage.

## Consequences

**The FPGA side does not change.** The element clock is still 24.576 MHz, so
interpolation ratios, stage counts and buffer sizing all stand.

**Two open items close.** Oscillator supply voltage and element rail voltage
were both listed in [open-items.md](../open-items.md) and are settled here.

**Two open.** The fanout and divider part, and the register part within the
constrained family.

## Rejected

- **MEMS oscillators**, for example the Abracon ASEMB series. Synthesised
  output, 5 ps period jitter, no integrated phase jitter published.
- **Programmable oscillators**, for example the Epson SG-8101CA. Publishes
  phase jitter over the right band, which is to its credit, but about 18 ps
  maximum at 2.5 V in the 20 to 40 MHz band, roughly twenty times the target.
- **A single oscillator plus synthesis.** A phase-locked loop in the master
  clock path would undo the reason for buying a good oscillator.
- **Dropping the 44.1 kHz family.** Most music is 44.1 kHz derived, so the host
  would resample the majority of material, discarding the bit-exactness this
  project exists to preserve.

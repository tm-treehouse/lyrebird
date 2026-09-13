# hardware

Two boards, split at the I2S boundary per
[0007](../docs/decisions/0007-two-board-split-at-i2s.md). The contract between
them is [interface.md](interface.md).

**The boards are described as code, not drawn.** `netlist/` holds SKiDL
generators that emit KiCad netlists; see [netlist/README.md](netlist/README.md)
for why, and for what is a real part versus a placeholder. Unconnected pins in
the generated netlist are the honest measure of how finished a board is, which
is why a missing part shows up as an open pin rather than as something nobody
wrote down.

- `netlist/` — the generators, and the authority on connectivity.
- `lyrebird-main-reva/` — USB connector, FT601Q, GateMate, power tree, SPI
  flash, programming header, mezzanine header. Generated netlist lands here.
- `lyrebird-dac-reva/` — audio oscillators, clock chain, reclocking registers,
  resistor elements and the analog output stage. There is no DAC chip: the FPGA
  is the converter, per
  [0008](../docs/decisions/0008-multibit-delta-sigma-with-dwa.md).
- `datasheets/` — vendor PDFs for parts on either board. Committed
  deliberately, because vendor links rot faster than the boards do.
- `fab/` — gerbers, drill files, BOM, and pick-and-place. Git-ignored by
  default since it is regenerated from source. When a board is actually
  fabricated, force-add a dated zip so the artifact that was built is
  recoverable.

One directory per board revision, so an old revision stays buildable after a
respin. The two boards revise independently, which is the point of the split.

## Main board

| Part | Role |
| --- | --- |
| FT601Q | USB 3.0 bridge, QFN-76, 32-bit FIFO. VCCIO on the 2.5 V rail |
| GateMate CCGM1A1 | FPGA, BGA324 15x15 mm. GPIO banks on the same 2.5 V rail |
| MX25R6435F | 64 Mbit quad SPI flash, FPGA configuration, SPI Active mode |
| LTM4622 | Dual switching module, the 2.5 V and 1.0 V rails |
| USB 3.0 Micro-B | Bus power and data, one cable |
| 30 MHz crystal | The bridge's only clock source; an oscillator will not do |

Roughly 43 pins face the bridge and 32 are provisioned for element lines to the
mezzanine, against 162 single-ended GPIO. Put the element outputs in their own
GPIO bank. The part has nine independently supplied banks, and while the module
reclocks everything anyway, there is no reason to share a rail between the
element drivers and the bridge interface.

Bus powered, with the core in economy mode. See
[0009](../docs/decisions/0009-usb-bus-power.md).

| Rail | Feeds | Part |
| --- | --- | --- |
| 5 V | Passed through to the module | Ferrite only |
| 3.3 V | FT601Q `VCC33`/`VDDA` | LT3045 |
| 2.5 V | FT601Q `VCCIO`, GateMate GPIO banks, mezzanine logic | LTM4622, ch 1 |
| 1.0 V | GateMate `VDD`, `VDD_PLL`, `VDD_SER`, `VDD_SER_PLL` | LTM4622, ch 2 |

Run the core at 1.0 V in economy mode rather than 0.9 V in low power mode. The
SerDes supplies have a 1.0 V minimum, so the lower setting would force a second
low-voltage rail for pins this design does not even use.

Nothing on this board is precision regulation. Every rail here is reclocked away
on the module, so none of it reaches the audio signal. The 3.3 V rail uses a
regulator rather than a switcher only because it feeds the USB PHY's analog
supply and FTDI's reference design does the same.

**Fit a noise filter between every regulator and the FPGA.** The GateMate
datasheet asks for this explicitly. There are no restrictions on the order rails
come up, so no sequencer is needed; the on-chip power-on reset handles it.

**Gate the FPGA rails with the LTM4622 run pins**, releasing them after the
bridge enumerates, so the board respects the one-unit-load limit that applies
before configuration.

## The 2.5 V rail is load-bearing

GateMate GPIO are LVCMOS up to 2.5 V with an absolute maximum VDDIO of 2.75 V.
They are not 3.3 V tolerant. The FT601Q is on this board specifically because
its VCCIO can be set to 2.5 V, which lets the two parts connect with no level
translation. Do not substitute a 3.3 V-only bridge without adding translators,
and do not hand 3.3 V logic to the mezzanine header. See
[0005](../docs/decisions/0005-ft601q-bridge-io-voltage.md).

Note that 100 MHz FIFO operation requires 2.5 V or 3.3 V on the FT601Q, so the
2.5 V choice does not close off the faster clock. The design uses 66.67 MHz
anyway, for timing margin rather than necessity.

## Output module

There is no DAC chip. The FPGA runs the modulator; this board turns element
lines into an analog waveform. See
[0008](../docs/decisions/0008-multibit-delta-sigma-with-dwa.md).

| Section | Part or role |
| --- | --- |
| Audio oscillators | Crystek CCHD-957 at 49.152 and 45.1584 MHz. One runs, the other in standby |
| Divider and fanout | Divide by two to the element clock, distribute with tight skew |
| Level translator | 74AVC4T245, 2.5 V toward the connector, 3.3 V toward the module |
| Reclocking registers | One 16-bit package per channel, on the element reference rail |
| Matched resistors | Summing network, 28 elements for three-bit differential stereo |
| Reconstruction filter | Passive, before the op amp |
| Output stage | Differential to single-ended, then line and/or headphone |

**The module domain is 3.3 V**, the header stays at 2.5 V, and the translator
sits on this side of the boundary so the mezzanine never carries 3.3 V. Full
scale is therefore 3.3 V rather than 2.5 V, worth about 2.4 dB. See
[0012](../docs/decisions/0012-module-clock-architecture.md).

Two oscillators are required because the sample rate families sit at a ratio of
147 to 160, which no divider bridges. They run at twice the element clock
because jitter expressed in time improves with carrier frequency, and because a
16 ns round trip through the translator would leave only about 4 ns of setup
margin at the undivided rate. The standby pin shuts the resonator down rather
than only gating the output, which is what keeps an idle oscillator from
radiating next to the analog section.

### Reclocking

The flip-flops are what make this architecture work. Without them the analog
output would be generated by the FPGA's output drivers, timed by the FPGA's
global clock mesh, and referenced to the FPGA's I/O bank supply. All three are
poor analog references: the mesh carries tens of picoseconds of jitter, driver
on-resistance shifts with process, voltage and temperature and differs between
the high and low states, and the I/O rail is a switching-regulator-fed digital
supply.

The flip-flop replaces all three at once. Its output swing becomes full scale,
its clock comes from the oscillator, and its drivers are one consistent type on
one die.

**Use one 16-bit register per channel, not two octal parts.** Three-bit
differential is fourteen elements per channel, which fits a single package with
two bits spare, putting both polarities on the same die with one supply pin and
one clock-to-output distribution. Even-order cancellation depends on the two
sides matching, so this is worth protecting. Decouple at the package, because
that supply pin is where the element switching current actually comes from.

**Choose a logic family whose input threshold is 2.0 V at a 3.3 V supply.** The
registers sit on the 3.3 V rail but their data inputs are driven at 2.5 V by
the FPGA, which guarantees 2.4 V. A family referencing its threshold to 0.7
times the supply would sit at 2.31 V and be marginal. This is why the element
lines need no translators, which would otherwise mean seven more packages
injecting skew into the signals least able to tolerate it.

### The element reference rail

**This is a voltage reference, not a logic supply.** Each element contributes
the rail voltage divided by its resistor, so the output is directly
proportional to the rail. Noise there is multiplicative rather than additive:
it rides on the signal as modulation sidebands instead of sitting under it as a
floor.

For a dynamic range near 110 dB, rail noise wants to be about 110 dB below the
rail, which on 3.3 V is roughly 10 uV across the audio band. Good low-noise
regulators reach that and generic ones do not. This is the one place in the
design where the specific regulator part matters.

Separate its two jobs. The regulator sets the DC value and the low-frequency
noise; it cannot hold the rail at the modulator rate, because its loop
bandwidth is orders of magnitude too low. Local ceramics supply the
high-frequency current. Neither substitutes for the other.

Give this rail to the flip-flops alone. Regulate the oscillator and the op amp
stage separately from a common upstream rail.

Differential thermometer drive keeps exactly seven elements high per channel at
every code, which is what stops the load itself from varying with the signal.

### The resistor elements

Dynamic element matching rotates mismatch into out-of-band noise, so absolute
tolerance matters much less than intuition suggests. One percent parts work,
and slow temperature drift is handled for free because it is slow compared to
the rotation.

**But it is not free, and an earlier version of this note overstated it.** The
model measured the cost of one percent mismatch at order 2, where the
modulator's own floor hides the rotation residual. At the recommended order 3
it costs 33 dB, not the fraction of a decibel first reported. The result still
lands around 135 dB, comfortably past the 110 dB target, so one percent parts
remain adequate. What changes is which component sets the floor: above order 2
it is element matching, not the modulator. See
[model/README.md](../model/README.md).

What the rotation does not fix is nonlinearity within a single resistor.
Voltage coefficient is real in thick film and small in thin film, so specify
thin film and do not let a purchasing substitution quietly change it. Prefer
thin film arrays over discretes for the same die-sharing reason as the
registers.

The summing resistors are already in the signal path, so a shunt capacitor at
the summing node buys the first filter pole for one part, before anything
active sees the stepped waveform.

**Filter the out-of-band noise passively before the op amp.** Noise shaping
works by moving quantization noise above the audio band, and it is still there.
An op amp asked to slew on it will intermodulate it back down.

A combined module shares the differential-to-single-ended stage, then splits to
a fixed-gain line buffer that bypasses volume control and a volume-controlled
headphone amplifier gated by the jack switch contact.

If the output stage needs a bipolar supply, generate it on the module and
post-regulate it. Op amp power supply rejection falls off steeply with
frequency, so at a charge pump's switching frequency the op amp rejects far
less than its headline figure. Run the pump a little hot and drop to the final
rail through low-dropout regulators.

## Layer stack

Roughly 43 FIFO signals run between the bridge and the FPGA on the main board,
plus USB 3.0 SuperSpeed differential pairs needing controlled impedance.
Cologne Chip advertises that the BGA324 escapes in two signal layers. Do not
take that as permission to build a two-layer board; budget for a solid ground
plane.

## Configuration

GateMate selects its configuration mode by strapping `CFG_MD[3:0]` to GND or
VDD_WA at reset. This design uses SPI Active, so the FPGA loads itself from
flash with no host involvement. A separate header carries the programming
interface. See [0006](../docs/decisions/0006-configuration-from-spi-flash.md).

**The flash is an MX25R6435F, 64 Mbit.** Two things fix that. The bitstream
scales with utilisation rather than being a fixed image
([0013](../docs/decisions/0013-simulation-and-build-toolchain.md)), so the
2 Mbit an earlier revision called ample is not; and Cologne Chip's own
evaluation board for this die fits exactly this part at exactly this size.
Its 1.65 to 3.6 V supply range is the other half of the choice: `VDD_WA` is
2.5 V and an ordinary 2.7 to 3.6 V flash cannot run there.

**Power-on reset is deliberate rather than default.** `POR_EN` goes to
`VDD_WA` and `RST_N` to `VDD_CLK`, as the datasheet's figure 3.4 has it, and
`POR_ADJ` carries a 47 k to `VDD_CLK` with 2.2 uF to ground. Against the
internal 133 k / 75 k divider the datasheet's formula gives about 19.4 ms of
release delay, which clears the 4.3 ms programmed soft start on the 2.5 V
rail by better than four times. Keeping R3a at or below 100 k is the
datasheet's own condition for the network never latching the part in reset,
so it only sets the release time.

## Committing KiCad

Commit `.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, local symbol and footprint
libraries. Local state (`.kicad_prl`), autosave, lock files, and the footprint
cache are ignored. Never commit a `-backups/` directory.

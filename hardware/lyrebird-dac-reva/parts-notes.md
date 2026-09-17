# lyrebird-dac-reva — part selections

Every part the module was missing, why it was chosen, and what was verified
against a datasheet rather than assumed. The netlist that carries these is
[../netlist/output_module.py](../netlist/output_module.py); the numbers they
are chosen against are [model/results/analog.txt](../../model/results/analog.txt)
and the decisions in [docs/decisions](../../docs/decisions).

**Where a specification could not be verified it says so.** Nothing here is a
manufacturer part number that was not read off a datasheet.

## Output op amp — OPA1612AID (U7, U10, U11)

Texas Instruments OPA1612, dual, SOIC-8 (D). Verified against SBOS450C.

| Parameter | Datasheet | Why it matters |
| --- | --- | --- |
| Input voltage noise density | **1.1 nV/√Hz typ at 1 kHz** (1.5 max), 1.5 at 100 Hz, 2 at 10 Hz | The largest single term in the stage's noise |
| Gain-bandwidth | **40 MHz** at G = +1, unity-gain stable | Sets the intermodulation margin |
| Input current noise | 1.7 pA/√Hz at 1 kHz | 0.2 % of noise power; irrelevant here |
| Supply range | ±2.25 V to ±18 V | ±5 V rails are inside it with room |
| Quiescent current | 3.6 mA per channel typ, 4.5 max | What power.md already budgets per amplifier |
| Output | rail to rail within 600 mV at 2 kΩ, ±30 mA | ±2.83 V peak on ±5 V, and a 400 Ω load |
| Common-mode range | (V−) + 2 to (V+) − 2 | ±3 V on ±5 V rails; the difference stage sits inside it |
| Slew rate | 27 V/µs | The figure analog.txt's output threshold is argued against |
| THD+N | 0.000015 % at 1 kHz, 3 V RMS | Below anything this design measures |

**This is the most consequential choice on the board**, because the analog
stage is now the floor: 125.8 dB against the digital chain's 133.5
([analog.txt](../../model/results/analog.txt) Q1c). The measured sensitivity to
amplifier voltage noise at the chosen 3.32 kΩ element is

| e_n | Stage SNR |
| --- | --- |
| 1.1 nV/√Hz | **126.3 dB** |
| 1.3 | 125.8 |
| 2.5 | 122.8 |
| 5.0 | 117.9 |

so the OPA1612 buys the best row on that table, half a decibel above the part
the model assumed and 3.5 dB above an ordinary 2.5 nV/√Hz audio dual. Paying
for a quieter part than this is not possible without leaving the class: the
sub-1 nV parts (ADA4898, LT1128) cost 8 mA per amplifier or more against a
budget that is already 76 % of a USB 2.0 host's, and buy at most 2 dB.

The gain-bandwidth is the other half. The filter was designed to clear its
intermodulation threshold **with a 10 MHz part** — the loosest case, leaving
9.8 dB of margin. At the OPA1612's 40 MHz the same filter measures −190.3 dBFS
in band, 43 dB inside the threshold, so the whole intermodulation argument
stops being close.

**Six amplifiers, three packages.** Two transimpedance stages per channel hold
the summing nodes at virtual ground, then one difference amplifier per channel
converts to single ended. power.md costed four amplifiers at 3.6 mA; six is
21.6 mA on each rail rather than 14.4, which is 15 mA more from the 5 V input
than that page's op amp line. It is still inside 0009's 65 mA for the op amp
stage and charge pump.

Two details of the wiring are deliberate and worth not undoing:

- **The non-inverting inputs of the transimpedance stages go straight to
  ground**, not through a bias-current compensation resistor. 60 nA through
  402 Ω is 24 µV of offset, while the 218 Ω that would cancel it would add
  1.9 nV/√Hz to the one stage whose noise this whole selection is about.
- **The difference amplifier's four 200 Ω resistors are one array.** They set
  common-mode rejection, and what they have to reject is the 1.4 V of DC that
  both transimpedance outputs carry at mid code. Their own thermal noise
  (about 3.4 nV/√Hz at the output) does not appear in analog.txt's noise
  breakdown, which accounts for the element resistors, the transimpedance
  resistors and the amplifiers only; it costs roughly 0.9 dB and is the reason
  not to scale that network up.

## Reclocking registers — SN74ALVCH16374DGGR (U3, U4)

Texas Instruments, 16-bit edge-triggered D-type flip-flop with 3-state
outputs, TSSOP-48 (DGG). Verified against SCES021L; the part is listed ACTIVE
in DL, DGG and DGV. A custom symbol was needed, and the pinout in
[../symbols/lyrebird.kicad_sym](../symbols/lyrebird.kicad_sym) is the
datasheet's own terminal assignment (1OE on 1, 1CLK on 48, VCC on 7/18/31/42,
GND on 4/10/15/21/28/34/39/45).

**The input threshold is what picks the family.** VIH is **2.0 V for VCC =
2.7 V to 3.6 V**, against the 2.4 V the FPGA guarantees at 2.5 V. That is the
rule 0012 states, and it is the reason the 28 element lines cross the
mezzanine untranslated:

| Family | VIH at 3.3 V | Verdict |
| --- | --- | --- |
| ALVCH | **2.0 V** | 400 mV of margin |
| LVC / LVCH | 0.7 × VCC = 2.31 V | The marginal case 0012 rejects |
| AVC | 0.65 × VCC = 2.15 V | Still referenced to the supply |
| LVTH, ALVTH | 2.0 V | Threshold passes, output fails — see below |

**The output has to be CMOS, not BiCMOS.** The register supply *is* full
scale, so the output high level is the reference the whole converter is
measured against. ALVCH specifies VOH as VCC − 0.2 V at −100 µA and 2.4 V at
−12 mA, so at the 1 mA an element draws it sits a few tens of millivolts under
the rail through an output impedance around 20 Ω — which is the figure
analog.txt already assumes, 0.6 % of a 3.32 kΩ element, and identical on every
element, so gain error rather than distortion. The LVT and ALVT families have
the same 2.0 V threshold but a bipolar output stage whose VOH is specified as
2.4 V at −8 mA; that is an uncontrolled drop in series with full scale.

Other specifications read off the datasheet: tpd CLK→Q 4.2 ns max at 3.3 V,
fmax 150 MHz against 24.576 MHz, ICC 40 µA static, Cpd 30 pF, data input
capacitance 6 pF. **Output-to-output skew is not specified in SCES021L** —
the minimum and typical columns of the switching table are marked "not
available at the time of publication" — so the one-package-per-channel
argument rests on both banks sharing a die and a supply, not on a published
skew number. Nothing was found to substitute for it.

**Bus hold is the one thing to know about this part.** The data inputs carry
an active bus-hold latch, which the datasheet offers as the reason no external
pull resistors are needed, and which explicitly warns against combining with
pull-ups or pull-downs. It sources up to **75 µA at VI = 2 V** toward its own
3.3 V rail. While the FPGA drives an element line, the line sits at the FPGA's
level and the hold current is absorbed by its driver. While the FPGA does
**not** drive — before configuration, or on a board whose flash has never been
programmed — bus hold pulls that line toward 3.3 V, and the line runs across
the mezzanine to a GateMate ball with a 2.75 V absolute maximum.

This is not caught by `lp.assert_below_abs_max`, because a data input is not a
driving pin and the check is right about that in general.

**It is settled against Cologne Chip's UG1003**, the GateMate interface guide
for 3.3 V peripherals. UG1003 states plainly that VDDIO may not exceed 2.7 V
and that "any voltage above VDDIO supply voltage should be avoided on the
GateMate pins", so the hazard is real rather than theoretical. But for a 3.3 V
source driving a GateMate input at low speed its recommended circuit is a bare
**10 kΩ to 100 kΩ series resistor and nothing else**, because "the input
overvoltage security circuitry of the GateMate input pin will limit the input
voltage". A 10 kΩ resistor from 3.3 V into a 2.5 V pin delivers about **80 µA**
into that clamp, and Cologne Chip endorses it. Bus hold is specified as a
**75 µA maximum current**, not a resistance, so it sits just inside the
envelope the vendor sanctions, and it stays inside it at any line voltage
because it is a current limit by construction.

**So no pull-down is needed, on either board**, and the element lines stay as
they are: straight from the header to the register inputs, which is what 0012
wants them to be.

One gap remains and is stated rather than papered over: **whether GateMate
GPIO are high impedance before configuration completes is not spelled out in
the datasheet**, so whether the bus hold ever gets to pull a line up is
unconfirmed. It does not change the conclusion, because the clamp covers the
worst case either way.

No ALVC-family 16-bit flip-flop without bus hold exists; the alternatives are
the threshold and output-stage failures in the tables above.

Spare bits: 14 elements in a 16-bit package leaves bit 8 of each bank unused.
Its data inputs are tied low rather than left to the hold latch, so the spare
outputs have a defined state; the spare outputs themselves are left open.

## Clock divider and fanout — SN74LVC1G74DCUR (U1) + LMK1C1104PWR (U12)

Two packages, not one, and the reason is current rather than preference.

**What was rejected.** Skyworks Si53308-B-GM is the closest single-chip
answer: dual 1:3 universal buffer, pin-strapped ÷2 per bank (DIVx low),
LVCMOS output format, 120–130 fs additive jitter from a single-ended input,
50 ps output skew. Its core supply current is **65 mA typical, 100 mA
maximum** (Si5330x data sheet rev 1.0, DC common characteristics), because it
is built for 725 MHz. The module's rails are not gated, and one unit load
before enumeration leaves roughly 50 mA for the whole clock rail including
17 mA of oscillator (analog.txt Q1b). It does not fit. Renesas 870S208, the
other divider-plus-fanout part found, takes only differential inputs and is
listed obsolete.

**U1, SN74LVC1G74** wired as a toggle: `~Q` drives `D`, so `Q` is the input
divided by two at a 50 % duty cycle by construction. Verified against SCES794G:
fmax 175 MHz minimum at 3.3 V against 49.152 MHz in, tpd 2.2 ns typical,
±24 mA of output drive, ICC 10 µA static, Cpd 37 pF — about 6 mA at
49.152 MHz. VSSOP-8 (DCU); the pinout in the project symbol is figure 5-1.
Preset and clear are tied to the rail.

**U12, LMK1C1104** 1:4 LVCMOS fanout. Verified against SNAS791D: **additive
jitter 17.5 fs typical, 50 fs maximum** (12 kHz to 20 MHz) and
**output-to-output skew 50 ps maximum**, which is the number that matters,
because skew between the register packages behaves like element mismatch.
fmax 250 MHz at 3.3 V, propagation delay 1.5 ns typical, output impedance
60 Ω, and about 10 mA at 24.576 MHz read off the current-against-frequency
curve (the tabulated 33 mA is at 100 MHz with four outputs into 5 pF). `1G`
has a 300 kΩ internal pull-down and needs the external pull-up the datasheet
asks for. Y0 goes to U3, Y1 to U4, Y2 to the translator, Y3 spare and
floating, which the datasheet permits.

Both clock inputs of a register package hang on **one** buffer output, so the
two banks of a channel see the same edge rather than two outputs 50 ps apart.

**The divider's own additive jitter is not specified.** No 74-series datasheet
publishes one. This is the weakest number in the clock chain and it is stated
rather than estimated: what the datasheet does give — 175 MHz fmax, ±24 mA of
drive into a 5 pF buffer input, and a dedicated LT3045-regulated rail — is
the argument that its contribution is small, not a measurement. The
alternative that would have removed the question costs 65 mA.

Clock rail total: 17 mA of oscillator (one running, one in standby) + 6 mA
divider + 10 mA buffer + 0.5 mA translator ≈ 33.5 mA, against power.md's
37.5 mA estimate, which had allowed 20 mA for an unchosen divider.

## Oscillators — CCHD-957X-25-49.152 and CCHD-957X-25-45.1584 (Y1, Y2)

The part was already chosen in 0012; what was missing was a correct symbol.
The netlist carried an Abracon ASE stand-in with a 3.2 × 2.5 mm footprint.
Verified against the Crystek spec sheet rev N:

- **The package is 9 × 14 mm**, not a 7050. No stock KiCad footprint matches.
- Pad connection: **1 = E/D, 2 = GND, 3 = OUT, 4 = Vcc**. E/D is active high,
  with "1" at 0.7 × Vcc minimum, and an **open pin runs**.
- 3.3 V ±0.3 V, 15 mA typical and 25 mA maximum running, **1.5 mA maximum
  disabled** — the two figures 0012 costs the pair at.
- Phase noise floor −169 dBc/Hz typical, −100 dBc/Hz at 10 Hz offset.
- Option X is −40 to +85 °C at ±25 ppm, which is what 0012 specifies, and the
  part number example in the datasheet is exactly `CCHD-957X-25-49.152`.

**Both outputs share one net, and the datasheet is what makes that legal**:
"when placed in disable mode, the internal oscillator is completely shut down
in addition to its output buffer being placed in Tri-State". The idle part
neither drives the net nor radiates.

**The footprint still has to be drawn.** `Footprint` names
`lyrebird:Oscillator_SMD_Crystek_CCHD-957_9x14mm`, which does not exist yet,
the same situation as the LTM4622 on the main board. The datasheet's suggested
pad layout is four pads of 0.090 × 0.070 in (2.28 × 1.77 mm) on a 0.280 in
(7.11 mm) by 0.200 in (5.08 mm) centre grid, so the numbers are available to
whoever draws it.

## Element resistors and the reconstruction filter

3.32 kΩ was already decided in [notes-analog.md](../../model/notes-analog.md).
What the netlist carried was a 1 kΩ placeholder, a single resistor per element
and a 1 nF capacitor at each summing node. All three changed.

**Value.** 1.69 kΩ + 1.65 kΩ = 3.34 kΩ per element, both E96, seven
four-element arrays of each. The split is the filter pole, below. The total is
0.6 % above the decided 3.32 kΩ, which is gain and nothing else, and it stays
above the 3312 Ω that the one-unit-load-at-power-on argument requires; an even
1.65 + 1.65 split would be 3.30 kΩ and fail that by a hair.

**The first filter pole is not a capacitor at the summing node.** This is the
one place where this work departs from the wording it was given, and it
follows analog.txt Q2b, which measured it:

> A shunt capacitor at the summing node is therefore not the first filter
> pole. Against a true virtual ground it sees no resistance and forms no pole
> at all; buy it a resistance by floating the node and the rail modulation
> arrives before the pole does. The netlist's 1 nF is not a filter.

What does work, and what the same file recommends, is splitting each element
resistor around a shunt capacitor: both ends stay at an AC ground — a
flip-flop output on one side, the virtual ground on the other — so the
capacitor sees R1‖R2 = 834 Ω while the DC current stays V_ref/(R1+R2) at
every code, and the constant-current property that 0008 depends on is
untouched. **180 pF C0G per element, 28 places**, gives 1.06 MHz.

The cost is the seven extra arrays and it is worth paying: with no real pole
in front of the first amplifier, analog.txt Q2c measures its in-band
intermodulation at −131.3 dBFS against a −147.2 dBFS threshold. That is a
failure by 15.9 dB. With the 1 MHz pole it is −190.3 dBFS. C0G rather than X7R
because a voltage coefficient inside one element is a nonlinearity the
rotation does not fix, and Q2e measured that 10 % capacitor tolerance costs
only 2 dB, so ordinary parts are fine.

**Poles two and three** are in the amplifier feedback: 2.0 nF across each
402 Ω transimpedance resistor (198 kHz) and 3.9 nF across each 200 Ω
difference-stage feedback (204 kHz), against the 200 kHz analog.txt asks for
and the 0.1 dB droop budget it is set by.

**Four summing nodes, not two.** The netlist summed left and right into one
differential pair, which is a mono mixer. Each channel now has its own pair
and its own amplifiers.

## Status

| Item | State |
| --- | --- |
| Output op amp | **done** — OPA1612AID, U7/U10/U11 |
| 16-bit registers | **done** — SN74ALVCH16374DGGR, U3/U4, new symbol |
| Clock divider and fanout | **done** — SN74LVC1G74DCUR U1 + LMK1C1104PWR U12, new symbols |
| Oscillator symbols | **done** — CCHD-957, Y1/Y2, new symbol; footprint still to draw |
| Element resistor and filter | **done** — 3.34 kΩ split, 180 pF per element, 402 Ω feedback |
| Charge pump | not yet wired |
| Positive rail post-regulator | not yet wired |
| Analog output connector | not yet wired |

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
- **The difference amplifier's four resistors are one array, and they are
  604 Ω rather than the 200 Ω analog.txt names.** They set common-mode
  rejection, and what they have to reject is the 1.4 V of DC that both
  transimpedance outputs carry at mid code, so the array matters. The value
  is set by a supply-current argument, below.

### The negative rail carries the signal, and that set two values

This is the one thing found here that analog.txt's model does not contain, and
it changed two component values, so it is written out.

**Every milliampere of element current ends up in the negative supply.** The
elements push current into a node held at 0 V; it leaves through the
transimpedance resistor into the amplifier's output pin, and the output stage
sinks it to `V−`. That is 13.9 mA, constant at every code by construction
(0008) — a third of what the whole analog stage draws, and it is not
quiescent current, it is the signal.

**The difference network is a second such load, and its size is a choice.**
The transimpedance outputs sit between 0 and −2.8 V, never positive, so the
network's current flows out of ground into those outputs and is sunk to `V−`
as well. It scales as 1/R while the network's own noise scales as √R:

| Network | Its current, both channels | Negative rail, typical IQ | Stage SNR |
| --- | --- | --- | --- |
| 200 Ω | 21.0 mA mid code, 28.0 worst | 56.5–63.5 mA | 125.6 dB |
| 402 Ω | 10.4 / 14.0 | 46.0–49.4 | 124.3 |
| **604 Ω** | **7.0 / 9.3** | **42.5–44.8** | **123.5** |
| 1 kΩ | 4.2 / 5.6 | 39.7–41.1 | 122.4 |

At 200 Ω the negative rail asks for 56 mA at idle and 63 mA at full scale.
That is past the LTC3265's 50 mA LDO rating, and — because a charge pump that
doubles costs about twice its output current at the input, and the negative
rail is inverted from the already-doubled one — it is 161 mA of USB current
for the analog stage alone, which does not fit the budget at all.

**604 Ω is where the two arguments balance.** It costs 2.1 dB against the
200 Ω case, taking the stage from 125.6 dB to 123.5 and the system to about
123.3 dB, which is still 13 dB above 0012's 110 dB target and still leaves the
digital chain's 133.5 dB well clear. It saves 14 mA on the negative rail and
28 mA at the USB input. Pole 3 moves with it: 1.3 nF across 604 Ω is 203 kHz,
the same corner analog.txt sets, so the filter is unchanged.

**This is the number to revisit if the supply ever gets easier.** A module with
its own power input — the one 0007 points a headphone design at — should go
back to 200 Ω and take the 2.1 dB.

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

**The footprint is drawn**, at
`../footprints/lyrebird.pretty/Oscillator_SMD_Crystek_CCHD-957_9x14mm.kicad_mod`,
from the datasheet's SUGGESTED PAD LAYOUT: four pads of 0.050 × 0.090 in
(1.27 × 2.28 mm) on a 0.280 in (7.11 mm) by 0.200 in (5.08 mm) centre grid,
against package pad metal of 0.040 × 0.070 in (1.01 × 1.77 mm) in the bottom
view. Two things about it are read rather than stated, and both should be
checked against the vendor drawing before a board is fabricated:

- **Which axis the 0.090 in dimension lies along.** The text carries the four
  numbers without saying which belongs to which axis. It is drawn with the
  longer land along the 7.11 mm axis. If that is backwards the joint still
  forms — the land is larger than the pad metal either way, 2.28 against 1.77
  and 1.27 against 1.01 — but the fillet is smaller than intended.
- **Which corner is pad 1.** The pad *functions* are the datasheet's own Pad
  Connection table. Their geometric arrangement follows the universal four-pad
  oscillator convention, the same one KiCad's SG-8002CA footprint uses: pad 1
  lower left in top view, then 2, 3, 4 anticlockwise.

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

## Charge pump — LTC3265EDHC#TRPBF (U13)

Analog Devices LTC3265: a boost charge pump, an inverting charge pump and a
50 mA LDO on each, in one 18-lead 5 × 3 mm DFN. Verified against datasheet
3265fa. A custom symbol was needed; its pinout is the datasheet's own
PIN FUNCTIONS list, and the DHC package's 1.65 × 4.40 mm exposed pad matches
the stock `DFN-18-1EP_3x5mm_P0.5mm_EP1.66x4.4mm` footprint exactly.

**Why a doubler is unavoidable.** A 5 V input cannot produce a regulated +5 V:
the module sees 4.43 V worst case at the header (power.md), and an LT3045 needs
its dropout above that. So the positive rail has to come from a pump that
doubles, and the negative one has to come from a pump that inverts something
bigger than 5 V.

**VIN_N is tied to VOUT+, not to VIN_P**, which is the datasheet's own
instruction for this case:

> If VIN_N is tied to VOUT+, the output at VOUT– will be –VOUT+ or –2 • VIN_P.
> This configuration is suitable for symmetric outputs at LDO+ and LDO– pins.
> If VIN_N is tied to VIN_P, the output at VOUT– will be –VIN_P.

Tying it to VIN_P would cap the negative raw rail at −4.43 V worst case, which
cannot feed a −5 V regulator at all.

### The 4.43 V question, worked out

The LTC3265's `VIN_P` range is given as **4.5 V to 16 V**, and power.md's worst
case at the module is **4.43 V** — 70 mV below it. **It resolves, and this
section is here so nobody has to re-open it.**

The part does not stop at 4.5 V: its undervoltage lockout is 3.6 V typical and
**3.8 V maximum rising**, so 4.43 V is 0.6 V above the voltage at which it
switches off, not near it. What is at stake is not the pump's own regulation
accuracy, which nothing downstream depends on, but whether what comes out of
it still lets the LT3045 and LT3094 regulate ±5 V. That is arithmetic, with
these datasheet numbers in it:

- **32 Ω**, the boost and inverting pumps' output impedance, specified at
  MODE = 0 and RT = GND, which is how they are wired: constant frequency,
  500 kHz.
- **LDO+ dropout 800 mV maximum at 50 mA**, scaled to the current drawn.
- **`VOUT+` carries both chains** — the positive LDO's load *and* the
  inverting pump's input current — because `VIN_N` is tied to it.
- **The rails are asymmetric**: 21.6 mA positive against 42–45 mA negative,
  for the reason set out under the op amp above.

| Bus | Load +/− | VOUT+ | VOUT− | LDO+ | LT3045 margin | LT3094 margin | USB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4.43 V | 21.6 / 42.5 mA, mid code | 6.71 V | −5.35 V | regulating | +0.64 V | +0.30 V | 134 mA |
| 4.43 V | 21.6 / 44.8 mA, full scale | 6.64 V | −5.21 V | regulating | +0.64 V | +0.16 V | 139 mA |
| 4.43 V | 33 / 56 mA, max IQ over temperature | 5.92 V | −4.12 V | dropout | +0.34 V | −0.93 V | 184 mA |
| 5.00 V | 21.6 / 42.5 mA | 7.85 V | −6.49 V | regulating | +0.64 V | +1.44 V | 134 mA |
| 5.00 V | 33 / 56 mA | 7.06 V | −5.26 V | regulating | +0.64 V | +0.21 V | 184 mA |

Margins are against the 5.05 V each final regulator needs to hold 5 V,
including its own dropout at these currents.

**So: it resolves.** At the realistic load the ±5 V rails hold at the bottom of
the USB range with 0.6 V and 0.16 V to spare, and at the nominal 5 V with a
volt or more. The 70 mV of input-range excursion is not what constrains
anything; the pump's 32 Ω under an asymmetric load is.

**The one case that does not hold is worth naming.** Stack the minimum bus
voltage, the maximum quiescent current of six amplifiers *over the full
temperature range* rather than at 25 °C, and a full-scale signal, and the
negative rail stops regulating and follows the pump down to about −4.1 V. The
output stage still has 1.3 V of headroom over the 2.83 V peak it has to
produce, and full scale is set by the element reference rail, not by this one,
so what is lost in that corner is headroom and supply rejection, not level or
accuracy. It should be measured rather than assumed, and 4.43 V is itself
built from a guaranteed USB minimum plus *estimated* ferrite and contact
drops, so a real board may never go there.

**The LT3094 is fed from `VOUT−` directly, not through LDO−.** The negative
rail's 42–56 mA is at or past that LDO's 50 mA rating, and putting it in the
chain would cost another 450 mV of dropout out of a rail that has 0.16 V of
margin at the bottom of the range. `VOUT−` has the pump's own capability
behind it — 100 mA of short-circuit current minimum — and the LT3094's
rejection is the stage the design was relying on in any case. LDO− stays
enabled with its capacitor and divider, unused, because `EN−` enables the
inverting pump and that LDO together.

**What it injects, and at what frequency.** This is the part of the choice that
matters, not efficiency.

- **MODE is tied low: constant frequency, not Burst Mode.** This is the
  decisive setting. In Burst Mode the part regulates hysteretically and the
  **burst repetition rate moves with load** — it is not a fixed frequency at
  all, and a load-dependent repetition rate is exactly the kind of thing that
  can land in the audio band or wander through it. Constant-frequency mode
  puts everything at one known line. The cost is quiescent current, 3 mA
  typical on each input pin against 135 µA in Burst Mode, and it is worth
  paying.
- **RT is tied to ground, which selects the 500 kHz default** — the highest
  frequency the part offers and the furthest from the band. 500 kHz is 4.6
  octaves above 20 kHz, and its harmonics only climb away from the band. No
  subharmonic of it lands in band, because a charge pump has no subharmonics
  to give: the switching is a fixed divide of one oscillator with no feedback
  loop that could period-double.
- **Three stages sit between that ripple and the signal.** The pump's own
  ripple is roughly I/(f·C) = 22 mA / (500 kHz × 10 µF) = 4.4 mV at VOUT; the
  internal LDO takes a first bite, the LT3045 or LT3094 rejects around 76 dB
  more at these frequencies, and the OPA1612's own supply rejection follows.
  What reaches the output as a 500 kHz tone is far below anything this design
  measures.
- **The residual risk is not the tone, it is the ground return.** The flying
  capacitors dump their charge through GND at 500 kHz, and that current shares
  a plane with the summing nodes, whose signal *is* a return current (0008).
  This is a layout constraint rather than a part choice: keep the pump's
  flying-capacitor loops tight and their return away from the element and
  summing-node ground. It is recorded here because a netlist cannot express
  it.

**Enable: the pump is gated on MUTE_N.** `EN+` and `EN−` both go to the
header's `MUTE_N`, with a 100 kΩ pull-down on the module so the net is defined
while the FPGA is unconfigured and its pin is high impedance. Three things make
this right rather than clever:

- analog.txt Q1b says in as many words that the op amp stage and charge pump
  "does not fit inside one unit load at any element value and has to be held
  off". Something had to gate it, and this is the only signal that crosses the
  header for the purpose.
- The polarity already matches: `MUTE_N` is asserted low to mute, and low or
  undriven means both pumps and both LDOs are off. The thresholds are 2 V
  rising maximum and 0.4 V falling minimum, so the header's 2.5 V logic clears
  them.
- Each enable pin has a 0.7 µA internal **pull-down**, so this part can never
  push the mezzanine net above its own level — it is an input in the checker's
  eyes and a pull-down in the physics.

The consequence to know: **a board whose FPGA never asserts `MUTE_N` has no
analog rails and makes no sound.** That is the failure mode this buys, against
drawing 90 mA before the host has allowed it.

**What it costs.** A doubler moves charge, so its input current is about twice
its output current whatever the voltage; the negative side is inverted from the
already-doubled rail, so it costs twice again. At 21.6 mA on each of ±5 V:

```
VOUT+ load  = 21.6 mA (positive chain) + 21.6 mA (into VIN_N) = 43 mA
input       = 2 x 43 mA                                       = 86 mA
+ quiescent, constant frequency mode, both pumps               ~ 4 mA
                                                              = 90 mA from 5 V
```

against power.md's 51 mA, which assumed four amplifiers and an 85 % pump.
Six amplifiers and the physics of doubling account for the difference. The
module lands near 182 mA and the board near 416 mA: inside the 900 mA declared
at enumeration, and inside a USB 2.0 host's 500 mA, which is the case 0009
says the line module has to fit. It is no longer comfortable there, and a
headphone module — already excluded by 0009 — is further out of reach than
that page's arithmetic suggests.

## Positive and negative post-regulators — LT3045 (U14) and LT3094 (U8)

The LT3045 was already the part on this board; U14 is a fourth one, sitting on
the pump's +5.69 V LDO output and programmed to +4.99 V by 49.9 kΩ on SET. Its
housekeeping is the same shared helper the other three use.

The **LT3094** at U8 was in the netlist with only OUT and GND connected — the
netlist README lists its input as one of two genuinely open things on the
module. It is now wired against its own datasheet rather than by analogy:

- `SET`: 49.9 kΩ to ground. "The regulator's output voltage is determined by
  VSET = ISET • RSET" with a precision 100 µA reference, and 49.9 kΩ is the
  value its own Table 1 lists for −5 V. 4.7 µF of SET bypass, which is what
  the quoted noise figure is measured with.
- `EN/UV`: tied to IN. "If unused, tie EN/UV to IN. Do not float the EN/UV
  pin." The enable thresholds are ±1.2 V nominal **of either polarity**, so on
  a negative regulator tying the pin to the negative input is an enable, not a
  shutdown — worth stating, because it reads like a shutdown.
- `PGFB`: tied to IN. "If power good and fast start-up functionality are not
  needed, tie PGFB to IN."
- `ILIM`: **programmed, not tied.** The LT3045's datasheet says to tie ILIM to
  ground when the feature is unused; the LT3094's pin description gives no such
  sentence, and its scale factor is 3.75 A·kΩ, so grounding the pin is not
  obviously the same instruction. 24.9 kΩ programs about 150 mA, comfortably
  above the 22 mA this rail carries and below what the pump's LDO can deliver
  into a fault.
- `VIOC`: left open. "If unused, float the VIOC pin."
- `PG`: left open, an open-collector flag, as on the LT3045s.

## Analog output connector — SJ1-3523N (J2)

Same Sky (formerly CUI Devices) SJ1-3523N: 3.5 mm, stereo, right angle,
through hole, **three conductors and no internal switches**, rated 12 VDC.
Stock KiCad symbol and footprint both exist and agree with it — the footprint
has exactly three pads, T, R and S, which is what a switchless jack has.

Tip is left, ring is right, sleeve is ground.

**No switch, because this variant has nothing to switch.** A switched jack
earns its place on a combined module, where 0007 gates the headphone amplifier
from the jack's switch contact.

**No output coupling capacitor.** The differential arrangement puts both
transimpedance outputs at the same DC, so the difference amplifier's output
sits at zero by construction and what is left is offset: a 0.1 % mismatch
between the two 402 Ω feedback resistors on 1.4 V of common mode is about
1.4 mV. A series capacitor large enough not to intrude in band would be an
electrolytic or a film part in the signal path, which is a worse trade than
1.4 mV.

**100 pF C0G from each output to ground**, at the jack. The jack is the only
port on the board and therefore its antenna; against the 100 Ω build-out
resistor this is a 16 MHz corner, which is nothing in band and something
against radio frequency arriving from outside.

## `MUTE_N` is now an HDL requirement

Gating the charge pump on `MUTE_N` moved a line from the hardware's column to
the FPGA's. **Nothing on this module makes an analog rail until the FPGA
asserts `MUTE_N`**, so an HDL that never drives that pin leaves a board that
powers up, enumerates, clocks, converts, and is silent. It is the right failure
direction — silence rather than 90 mA the host has not granted, or a thump into
somebody's amplifier — but only if something eventually asserts it.

**What the pin does now.** It drives `EN+` and `EN−` on the LTC3265 through a
100 kΩ pull-down on the module. Low or undriven means both charge pumps and
both of the pump's LDOs are off, so `+5V_A` and `−5V_A` do not exist and the
six OPA1612 channels are unpowered. High means the whole analog stage comes up.
The thresholds are 2 V rising maximum and 0.4 V falling minimum, which the
header's 2.5 V logic clears at both ends.

**When to assert it.** Two conditions, and the order matters:

1. **After the host has configured the device.** One unit load applies until
   then — 150 mA on USB 3.0 — and the analog stage does not fit inside it at
   any element value (analog.txt Q1b). This is the same event 0009 already uses
   to release the FPGA rails through the LTM4622 run pins, so the FPGA knows
   it.
2. **After the element lines are being driven with a defined code.** The
   oscillator has to be enabled, the element clock running, and the registers
   clocked at least once, or the analog stage powers up onto whatever state
   the flip-flops came up in — which can be all 28 elements high, a
   full-scale DC step into the output. Assert `MUTE_N` after the modulator is
   running and settled at mid-scale, not before.

It does **not** wait on the module's own rails, because they do not exist until
it asserts. It is the cause, not the effect.

**Allow for the ramp.** Asserting `MUTE_N` starts the charge pumps, then the
pump's LDOs, then the LT3045 and LT3094, whose start-up is set by the 4.7 µF
bypass on each SET pin. That is milliseconds, not microseconds. Hold the
digital output at zero across it.

**Do not use it as a mute.** 0010 puts volume and mute in the FPGA, and that is
where a rate change should mute: 0007's "mute, switch, re-lock, prefill,
resume" must use the digital path, because toggling `MUTE_N` now power-cycles
the analog stage and costs milliseconds each way. `MUTE_N` is a power-sequencing
signal that happens to have the right polarity and the right name.

**De-assert it on the way down** if the FPGA can see it coming — loss of
configuration, a rate family change that stops the clock, a commanded shutdown
— so the output stage loses its rails before the element reference rail sags
and the elements drift.

## What is left open on purpose

| Pin | Why |
| --- | --- |
| U3, U4 `1Q8`, `2Q8` | Spare bit of each register bank; 14 elements in a 16-bit package |
| U12 `Y3` | Spare buffer output. "Unused outputs can be left floating" |
| U8 `VIOC` | "If unused, float the VIOC pin" |
| U5, U6, U8, U9, U14 `PG` | Open-collector flag, unused |
| U2 `1A2` | Output side of the translator's spare channel; its input is tied |
| `ELEM28`–`ELEM31` | Reserved element lines, driven low by the main board (interface.md) |

## What changes for a headphone module

This is the **line-only** variant: `ID0`/`ID1` strapped 0b01, one 3.5 mm jack,
no volume and no headphone amplifier (brief.md). What a headphone or combined
module would have to change, in the order the changes bite:

**The output stage splits after the difference amplifier.** 0007 shares the
current-to-voltage and filter stage and then splits to a fixed-gain line buffer
and a volume-controlled headphone amplifier. Everything up to and including
U11 is that shared stage, and all three filter poles are already behind it, so
a headphone path inherits the filtered signal rather than needing its own.

**The OPA1612 cannot be the headphone driver.** It is specified into 2 kΩ and
600 Ω and its output current is ±30 mA; 2 V RMS into 32 Ω is 88 mA peak. A
headphone module needs a dedicated driver with the current to match. No part
is named here because none was evaluated for it.

**The charge pump does not scale.** The LTC3265's LDOs are 50 mA each, and its
input current is about twice its output current on the positive side and twice
again through the inverting pump. A stage drawing tens of milliamps more per
rail leaves this architecture behind entirely, which is the concrete form of
0009's conclusion that a headphone module exceeds a USB 2.0 host's budget:
this board already reaches about 416 mA at the USB input, and 0009 puts a
hard-driven headphone stage at roughly 200 mA more. That is comfortable on
USB 3.0's 900 mA and over a USB 2.0 host's 500 mA, so such a module should
carry its own input jack (0007).

**The jack gains a switch contact.** 0007 gates the headphone amplifier from
the jack's switch so an unplugged module costs line-out current. The SJ1-3523N
fitted here has no switch, and the switched members of the same family have
more than three pads, so both the footprint and the symbol change. No specific
switched part number is given here because none was checked against a
datasheet.

**The identity straps change.** `ID0`/`ID1` are 0b10 for headphone only and
0b11 for combined (interface.md). They are two resistors: 1 kΩ to the module's
2.5 V rail for a one, 10 kΩ to ground for a zero. Never to the 3.3 V reference
rail — that mistake has already been made once on this board.

**`MUTE_N` earns its keep.** On a line module, gating the analog rails from it
is mostly a power-budget device. With headphones on the end of the cable, the
same gate is what keeps a power-up or power-down transient out of somebody's
ears.

## The build

As generated, the module is 125 components and 635 pins with **12 unconnected
pins**, all of them in the table above. Before this work it was 42 components,
344 pins and 35 unconnected, of which the op amp's six signal pins, the
LT3094's nine and the registers' clocks were the parts that had no part.

`lp.assert_below_abs_max` passes, and it was checked by tampering rather than
by assumption: putting `+3V3_REF` on a header pin still fails the build.

## Status

| Item | State |
| --- | --- |
| Output op amp | **done** — OPA1612AID, U7/U10/U11 |
| 16-bit registers | **done** — SN74ALVCH16374DGGR, U3/U4, new symbol |
| Clock divider and fanout | **done** — SN74LVC1G74DCUR U1 + LMK1C1104PWR U12, new symbols |
| Oscillator symbols | **done** — CCHD-957, Y1/Y2, new symbol and new footprint |
| Element resistor and filter | **done** — 3.34 kΩ split, 180 pF per element, 402 Ω feedback |
| Charge pump | **done** — LTC3265EDHC#TRPBF, U13, new symbol |
| Positive rail post-regulator | **done** — LT3045, U14; LT3094 at U8 now fully wired |
| Analog output connector | **done** — SJ1-3523N, J2 |

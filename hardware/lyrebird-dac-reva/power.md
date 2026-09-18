# lyrebird-dac-reva — power

The module regulates its own rails from the +5 V the main board hands it
([0009](../../docs/decisions/0009-usb-bus-power.md),
[interface.md](../interface.md)). This page shows the arithmetic behind every
number. The main board's half is
[../lyrebird-main-reva/power.md](../lyrebird-main-reva/power.md) and the two
have to agree; the total below appears there as one line.

**Provenance is marked on every figure**: *datasheet*, *calculation*, or
*estimate*. Every part on the module has now been chosen and its datasheet
read, so most of what was estimated here is measured from a vendor document;
[parts-notes.md](parts-notes.md) says which document and what could not be
verified. `hardware/datasheets/` is still empty, so the PDFs were read rather
than committed.

## Where the boundary sits

**The boundary is the +5 V pins of the mezzanine header**, J1 pins 71, 73, 75,
77 and 79 in `lyrebird-dac.net`, five pins of unregulated bus voltage
downstream of the main board's VBUS ferrite.

**Nothing else crosses.** No 3.3 V, and — the part that bites — **no 2.5 V**.
Everything on this page is generated on this board. Everything upstream of
those five pins is the main board's problem.

That is not a free choice on either side. 2.5 V is the header's logic level,
set by GateMate GPIO with a 2.75 V absolute maximum
([0005](../../docs/decisions/0005-ft601q-bridge-io-voltage.md)), and
[0012](../../docs/decisions/0012-module-clock-architecture.md) requires the
translator's A-side pins — supply, direction and output enable — to be
referenced to that rail and **never to 3.3 V**. The module therefore needs a
2.5 V rail that the interface does not supply. See the last section.

## The rails

| Rail | V | Source | Feeds | At the rail | From 5 V |
| --- | --- | --- | --- | --- | --- |
| `+3V3_REF` | 3.32 | LT3045, U5 | 2 register packages, 28 elements, 8x 100 nF | 58 mA | 60 mA |
| `+3V3_CLK` | 3.3 | LT3045, U6 | Y1, Y2, U1 divider, U12 buffer, translator `VCC(B)` | 33.5 mA | 35.5 mA |
| `+5V_A` | +5 | LT3045, U14, from the pump's LDO+ | op amp `V+` | 21.6 mA | (see pump) |
| `-5V_A` | −5 | LT3094, U8, from the pump's `VOUT−` | op amp `V−`, **and all the signal current** | 42.5–44.8 mA | (see pump) |
| pump | +5.69 V from LDO+, −5.2 to −7.8 V raw from `VOUT−` | LTC3265, U13 | both analog rails | — | 134–139 mA |
| `+2V5` | 2.5 | LT3045, U9 | translator `VCC(A)` | <1 mA | 3 mA |

**The two analog rails are not symmetric, and that is the single biggest
change to this page.** The negative one carries the op amps' quiescent
current *and* every milliampere of element current, because the summing nodes
are virtual grounds and what flows into them leaves through the amplifier's
output pin into `V−`. See the op amp section.

## The element reference rail

**This is a voltage reference that happens to power logic.** Each element
contributes the rail voltage divided by its resistor, so rail noise is
multiplicative — sidebands on the signal, not a floor under it. About 10 uV
across the audio band on 3.3 V for a 110 dB dynamic range (0012).

### Element current

Differential thermometer drive holds exactly seven elements high per channel at
every code, so the load is constant by construction and not signal-dependent —
that is the whole reason the drive is differential
([0008](../../docs/decisions/0008-multibit-delta-sigma-with-dwa.md)):

```
N_high = 7 per channel x 2 channels = 14, at every code   (calculation)
I_elem = 14 x 3.3 V / R_elem
```

This assumes the summing node sits at 0 V, a virtual ground at the op amp's
inverting input. If it floated at a DC midpoint instead, the current would be
lower and signal-dependent, which is exactly the compression the differential
drive exists to prevent — so the virtual-ground case is both the one consistent
with 0008 and the worst case.

`R_elem` **is chosen**: 3.32 kΩ ([model/notes-analog.md](../../model/notes-analog.md)),
fitted as 1.69 k + 1.65 k = 3.34 kΩ around the filter capacitor that buys the
1 MHz pole ([parts-notes.md](parts-notes.md)). The rail is 3.32 V, set by the
LT3045's 33.2 k:

```
I_elem = 14 x 3.32 V / 3340 ohm = 13.92 mA, constant       (calculation)
```

against 46.2 mA at the 1 kΩ placeholder this page used to carry. That is a
32 mA saving and it is the largest single improvement to the module's budget.

**The filter capacitors add a term the old page could not have.** Each 180 pF
is charged through the register-side half of its element on every rising edge
and discharged on every falling one. At the rotation's assumed transition rate
— half the element clock, this page's own figure — that is about 0.37 mA per
element averaged over a cycle:

```
28 x 0.37 mA = 10.4 mA                                     (estimate)
```

**and unlike the 13.9 mA it is not constant with code**, because it scales with
how often lines change and the rotation ties that to the signal. The constant
current property 0008 guarantees covers the DC term only. parts-notes.md
records this as something to measure with the modulator running rather than to
settle here.

### Register current

The register is now a part — SN74ALVCH16374 — so this is a *datasheet* figure
rather than a guess at a capacitance. Its power dissipation capacitance is
**30 pF with outputs enabled at 3.3 V** (SCES021L, operating characteristics),
and `I = Cpd x V x f` per flip-flop:

```
28 x 30 pF x 3.32 V x 12.29 MHz = 34.3 mA                  (calculation)
```

Element switching is taken at half the element clock, which is what dynamic
element matching produces on any given line.

**Read `Cpd` as per flip-flop, not per package.** The datasheet does not say
which, but the same family's single-gate parts quote 37 pF for one flip-flop
(SN74LVC1G74), and a sixteen-bit register cannot dissipate less than one of
those. If it were per package the figure would be sixteen times smaller and
this rail would be 26 mA rather than 58. It is the largest remaining
uncertainty on this page and it is worth a bench measurement.

### Rail total

```
13.9 mA elements (calculation)
10.4 mA element filter capacitors (estimate)
34.3 mA registers (datasheet Cpd)
                                         = 58.6 mA at the rail
+ 2 mA LT3045 ground pin (estimate)      = 60.6 mA from 5 V
P = (5.00 - 3.32) x 0.0586               = 98 mW dissipated   (calculation)
```

Almost the same total as the old page's 56 mA, arrived at completely
differently: the elements cost a third of what a 1 kΩ placeholder implied, and
the registers cost four times what a 5 pF estimate implied.

### Decoupling is not a budget question, but it is arithmetic

The DC load is constant, so what the local ceramics actually supply is the
redistribution transient when the rotation swaps which lines are high. A
worst-case swap of seven elements is a 6.96 mA step at 3.34 kΩ, lasting as long
as the reclock skew between the flip-flops:

```
dV = dI x t / C = 6.96 mA x 1 ns / 800 nF = 8.7 uV       (calculation)
```

against 8 x 100 nF fitted. At the 1 kΩ this page used to carry the same
arithmetic gave 29 uV, three times the 10 uV audio-band target; at the chosen
element it is under it. It happens at the element clock rate rather than in
band and the rotation scrambles it in any case. It is still the reason 0008 says decouple heavily and keep return
currents tight: at these edge rates the binding term is the loop inductance
from the package pin to the capacitor, which is a layout problem this page
cannot budget.

## The clock chain rail

| Item | mA at 3.3 V | Provenance |
| --- | --- | --- |
| CCHD-957, running | 15.5 | datasheet, 15 mA typical and 25 mA maximum |
| CCHD-957, standby | 1.5 | datasheet maximum |
| SN74LVC1G74 divider | 6.0 | datasheet Cpd 37 pF x 3.3 V x 49.152 MHz |
| LMK1C1104 fanout buffer | 10 | datasheet, current against frequency at 24.576 MHz |
| 74AVC4T245, B side | 0.5 | calculation |
| **Total** | **33.5** | |

The oscillator figure is arithmetic on 0012, which gives standby as 1.5 mA and
says both parts fitted cost about 17 mA together:

```
I_running = 17 - 1.5 = 15.5 mA                            (calculation)
```

Exactly one resonator runs; the other is in standby, which shuts the resonator
down rather than gating the output.

**The divider is no longer an estimate, and it came in under budget.** 0009 has
a 30 mA line called "Oscillator" against 17 mA of oscillator, leaving 13 mA for
a part that has to divide by two and drive two register packages and the header
with tight skew. A flip-flop and a small fanout buffer do it for 16 mA together.
The integrated divider-plus-fanout parts that would have done it in one package
cost 65 mA of core current, which is why there are two
([parts-notes.md](parts-notes.md)).

The translator's B side receives `MCLK` and drives nothing, since the direction
is B to A; its cost is internal switching at 24.576 MHz on a 5 pF node
(*estimate*), `5 pF x 3.3 V x 24.576 MHz = 0.41 mA` (*calculation*). The two
enable lines are static.

```
33.5 mA at the rail + 2 mA LT3045 ground = 35.5 mA from 5 V
P = (5.00 - 3.30) x 0.0335               = 57 mW dissipated
```

## The op amp rails

**Every part on this path is now chosen**: OPA1612AID amplifiers, an LTC3265
charge pump, an LT3045 on the positive rail and the LT3094 that was already
here on the negative one ([parts-notes.md](parts-notes.md)). The figures below
are *datasheet* and *calculation*; only the pump quiescent current is an
estimate.

**Six amplifier channels, not four.** Two transimpedance stages per channel
hold the summing nodes at virtual ground, then one difference amplifier per
channel converts to single ended. The old four-channel figure assumed a
difference stage plus a line buffer; the line buffer turned out to be the
difference stage.

```
6 x 3.6 mA = 21.6 mA of quiescent current on each rail     (datasheet typical)
```

### The negative rail carries the signal

This is the term no quiescent figure accounts for, and it is bigger than the
quiescent one.

The elements push current into nodes held at 0 V. It leaves through the
transimpedance resistors into the amplifiers' output pins, and the output
stages sink it to `V−`. **All 13.9 mA of element current lands on the negative
rail**, constant at every code — the same constant-current property 0008 buys,
arriving somewhere the earlier arithmetic did not look.

The difference network is a second such load. Both transimpedance outputs sit
between 0 and −2.8 V and never go positive, so the network's current flows out
of ground into those outputs and is sunk to `V−` as well. It scales as 1/R, and
its own thermal noise as √R, which is what fixed the value at 604 Ω rather than
the 200 Ω the model names:

```
604 ohm network: 7.0 mA at mid code, 9.3 mA worst case     (calculation)
```

```
negative rail = 21.6 quiescent + 13.9 elements + 7.0 network = 42.5 mA
                at full scale                               = 44.8 mA
positive rail = 21.6 mA                                                (datasheet + calculation)
```

Signal current into the load is negligible beside both: 2 V RMS into a 10 kΩ
line load is 0.2 mA RMS (*calculation*).

### What the pump costs

A 5 V input cannot produce +5 V with headroom, so the LTC3265 doubles for the
positive rail and inverts the doubled rail for the negative one, and the two
low-dropout regulators drop to the final rails — op amp rejection falls off
steeply with frequency, so at a pump's switching frequency it rejects far less
than its headline figure (0009).

**A charge pump that doubles costs about twice its output current at its
input**, because it moves charge rather than transforming voltage. Both rails
are drawn from `VOUT+`, since the inverting pump's input is tied there:

```
VOUT+ load = 21.6 mA positive chain
           + 44.8 mA negative chain
           +  3   mA inverting pump quiescent (datasheet, constant frequency)
                                     = 69.4 mA
USB input  = 2 x 69.4 mA             = 139 mA from 5 V       (calculation)
                                       134 mA at mid code
```

That is the price of the asymmetry: the 13.9 mA of element current is paid for
once on the reference rail and twice again here. It is also why the difference
network is 604 Ω — at the 200 Ω the model names, the negative rail would be
56 mA and this line would read 161 mA.

The pump's own headroom at the bottom of the USB range, including its 32 Ω
output impedance and the regulators' dropout, is worked out in
[parts-notes.md](parts-notes.md). The ±5 V rails hold with 0.6 V and 0.16 V of
margin at 4.43 V in.

## Totals at the mezzanine

| Rail | At the rail | From 5 V | Provenance |
| --- | --- | --- | --- |
| Element reference, 3.34 kΩ elements | 58.6 mA | 60.6 mA | calculation + datasheet Cpd |
| Clock chain | 33.5 mA | 35.5 mA | datasheet |
| Op amp stage and charge pump | 21.6 / 44.8 mA | 139 mA | datasheet + calculation |
| Translator A side | <1 mA | 3 mA | calculation, LT3045 ground pin |
| **Module total** | | **238 mA** | |

At mid code rather than full scale the module draws 233 mA. The op amp line is
where the module's current now lives, and two thirds of it is the doubling: the
stage itself takes 66 mA across both rails.

Headroom is fine at the worst input. USB 3.0 guarantees 4.45 V at the device
(*via 0009*); a ferrite at 50 mΩ drops 24 mV at the full 472 mA and five
parallel header contacts at 20 mΩ drop 1 mV at 238 mA (*estimates* on the
resistances), so the module's LT3045s see 4.43 V against a 3.3 V output —
1.13 V of headroom against a dropout of a few hundred millivolts. The part
that has to be checked at 4.43 V is the charge pump, whose input range starts
at 4.5 V; [parts-notes.md](parts-notes.md) works that out and it resolves.

## Reflected to the USB input, and margin

The module is one line in the main board's budget:

```
main board  234 mA
module      238 mA
            -------
total       472 mA                                        (calculation)
```

| Against | Limit | Drawn | Spare | Utilisation |
| --- | --- | --- | --- | --- |
| USB 3.0, configured | 900 mA | 472 mA | 428 mA | 52 % |
| USB 2.0 host | 500 mA | 472 mA | 28 mA | 94 % |

**The USB 2.0 line is no longer comfortable**, and it is the one number on this
page that should worry a reader. Two things soften it and neither is an
argument for ignoring it. The 234 mA of main board includes 185 mA of bridge
in *active SuperSpeed*; a host that only offers 500 mA is a High Speed host,
where the FT601Q draws substantially less, so the real USB 2.0 figure is lower
than 472 mA — by how much is not computed here. And 472 mA is full scale on
both channels at once with maximum quiescent current assumed nowhere; at mid
code it is 467 mA. If it has to come down, the difference network is the lever:
every milliampere saved on the negative rail is two at the input.

This is the line-output module. 0009 puts a hard-driven headphone stage at
roughly 200 mA more, reaching about 580 mA: comfortable on USB 3.0, over the
500 mA of a USB 2.0 host. That module is not this one — `ID0`/`ID1` are
strapped 0b01 — and 0009 deliberately leaves the case unsolved, pointing a
module that needs more than the bus supplies at its own input jack.

**The declared figure is 900 mA regardless**, fixed at enumeration and not
renegotiable when a module is swapped.

## Before enumeration

A device may draw one unit load before it is configured: 150 mA on USB 3.0,
100 mA on USB 2.0. **The analog stage is now gated and the digital rails are
not**, which is what makes this fit.

`MUTE_N` drives the LTC3265's two enable pins through a 100 kΩ pull-down on the
module, so until the FPGA asserts it there is no charge pump, no ±5 V and no
139 mA. That is deliberate: analog.txt says in as many words that the op amp
stage and charge pump do not fit inside one unit load at any element value and
have to be held off. It is also an HDL requirement now — see
[parts-notes.md](parts-notes.md).

What is live before configuration is the clock chain and the element reference,
and neither is switching yet, because the oscillators are disabled until the
FPGA enables them:

```
72 mA bridge and regulator, with the FPGA rails gated by the LTM4622 run pins
35.5 mA clock chain (oscillator in standby until enabled: less)
27.8 mA element reference, worst case: no clock, so no dynamic current, but
       the flip-flop state is undefined and all 28 elements may be high
                                       --------
                                       135 mA against a 150 mA unit load
```

That fits, and it only fits because the element is 3.32 kΩ: at the 1 kΩ this
page used to carry, 28 elements high is 92 mA and the total is 199 mA. The
margin is the reason analog.txt would not take any element value below
3312 Ω.

## Against 0009's budget

Checked rather than copied. 0009's three module lines sum to 120 mA; this page
now gets 238 mA.

| Line | 0009 | Here | Why |
| --- | --- | --- | --- |
| Element reference rail | 25 | 61 | 3.32 kΩ costs 14 mA of elements, but the registers cost 34 mA and the filter capacitors 10 |
| Oscillator | 30 | 35.5 | 17 mA of oscillator, 16 mA of divider and buffer |
| Op amp stage and charge pump | 65 | 139 | six amplifiers, 14 mA of element current on `V−`, and a doubler that pays for all of it twice |
| **Module subtotal** | **120** | **238** | |

**The op amp line is where 0009 was wrong, and not by a little.** Its 65 mA
assumed an amplifier stage that costs what its quiescent current costs. This
one sinks the whole element current into its negative rail and buys that rail
from a charge pump at two-for-one, which no estimate written before the
topology existed could have contained. The element line moved the other way —
the resistor 0009 implied was about right — but the registers turned out to be
four times their estimate.

## What had no source, and what does now

Every item this section used to list is closed.

**`+2V5`, the translator's A-side supply** — LT3045 at U9, off the header's
5 V. Its own consumption is under 1 mA (one 24.576 MHz clock into about 10 pF
of trace, connector and FPGA pad: `10 pF x 2.5 V x 24.576 MHz = 0.61 mA`), so
the 3 mA in the table above is almost entirely the regulator's ground pin.

**`+5V_A`, the op amp's positive rail** — LT3045 at U14, from the charge pump's
positive LDO at 5.69 V.

**The charge pump** — LTC3265 at U13, boost and inverting pumps with `VIN_N`
tied to `VOUT+` for symmetric rails. `-5V_A` comes from the LT3094 at U8, whose
input is now the pump's `VOUT−` rather than nothing.

**The element reference rail no longer leaves the board.** `ID0` straps to the
2.5 V rail through 1 kΩ, and the divided clock reaches the header only through
the translator's 2.5 V side. `lp.assert_below_abs_max` fails the build if
either regresses, and it was tamper-tested rather than assumed.

## What is still uncertain here

| Figure | Why it is not settled |
| --- | --- |
| 34.3 mA of register current | `Cpd` read as per flip-flop rather than per package; a bench measurement settles it, and the rail is 26 mA if the other reading is right |
| 10.4 mA of element filter capacitors | Depends on the rotation's transition rate, which is a model question, and it is the one term on this rail that is not constant with code |
| 10 mA of fanout buffer | Read off a curve rather than a table; the tabulated figure is 33 mA at 100 MHz with four outputs loaded |
| 3 mA of pump quiescent | Datasheet gives 3 mA typical and 6 mA maximum on each input pin in constant frequency mode |
| 4.43 V at the header | Guaranteed USB minimum plus *estimated* ferrite and contact drops; it decides whether the charge pump is inside its input range |

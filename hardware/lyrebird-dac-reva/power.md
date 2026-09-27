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

| Rail | V | Source | Feeds | At the rail | From the header |
| --- | --- | --- | --- | --- | --- |
| `+3V3_REF` | 3.32 | LT3045, U5 | 2 register packages, 28 elements, 8× 100 nF | 58 mA | 60 mA of +5V |
| `+3V3_CLK` | 3.3 | LT3045, U6 | Y1, Y2, U1 divider, U12 buffer, translator `VCC(B)` | 33.5 mA | 35.5 mA of +5V |
| `+5V_A` | +4.53 | LT3045, U14, **straight off the header's +5V** | op amp `V+` | 21.6 mA | 23.6 mA of +5V |
| `-5V_A` | −5 | LT3094, U8, from the mezzanine's **−6V** | op amp `V−`, **and all the signal current** | 56.5–63.5 mA | 64 mA of −6V |
| `+2V5` | 2.5 | LT3045, U9 | translator `VCC(A)` | <1 mA | 3 mA of +5V |

**There is no charge pump.** 0015 moved the negative rail to the main
board, where 12 V makes an inverter cheap, so this board now contains no
switching converter of any kind — which was the point of choosing that
arrangement over three alternatives that each relocated a switcher instead of
removing one.

**Only the negative rail ever needed help from outside.** The pump existed
because the module made both polarities symmetrically from one 5 V input. The
output swings ±2.83 V peak and the OPA1612 reaches within 600 mV of its rails,
so the positive analog supply wants about 3.5 V — and the header had carried
5 V all along. U14 is programmed to **+4.53 V**, which leaves 3.93 V of swing
available against the 2.83 V needed — and 490 mV of headroom over its input,
which matters more than the swing does. It was 4.99 V until a review caught
that: the SET resistor still held the value that suited the charge pump's
5.69 V, leaving 30 mV against a part whose published dropout is 260 mV.

**The two analog rails are not symmetric**, and that is the most consequential
fact on this page. The negative one carries the op amps' quiescent current
*and* every milliampere of element current, because the summing nodes are
virtual grounds and what flows into them leaves through the amplifier's output
pin into `V−`. See the op amp section.

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

**Every part on this path is chosen**: OPA1612AID amplifiers (U7, U10, U11),
an LT3045 at U14 for the positive rail and an LT3094 at U8 for the negative.
The charge pump that used to sit in front of them is deleted.

Six amplifiers, not four. Two transimpedance stages per channel hold the
summing nodes at virtual ground, then one difference amplifier per channel
converts to single ended. At the datasheet's 3.6 mA per channel that is
21.6 mA on each rail.

    positive rail = 21.6 mA quiescent                       (datasheet typical)
    negative rail = 21.6 quiescent
                  + 13.9 elements      constant at every code, by 0008
                  + 21.0 network       200 ohm difference array, mid code
                  = 56.5 mA mid code, 63.5 mA worst case    (calculation)

**The asymmetry is the whole story of this rail.** The positive side carries
quiescent current and nothing else. The negative side carries that plus every
milliampere the elements push into the summing nodes, because a virtual ground
sources nothing — the current arrives through the element, leaves through the
transimpedance resistor, and is sunk by the amplifier's output stage to `V−`.
It is signal current, not quiescent, and it is a third of the analog stage.

That is why the 200 Ω difference network was once 604 Ω. While the module made
its own negative rail by inverting an already-doubled 5 V, 63.5 mA cost about
four times that at the input; 604 Ω brought it to 44.8 mA and cost 2.1 dB of
stage noise. 0015 made the current ordinary and the 2.1 dB came back.

One measured caveat on the asymmetry, from `hardware/sim/difference_stage.py`:
the two halves do not merely draw different currents, they *swing* differently
— 1.499 : 1 rather than the 1.25 the load ratio suggests — and the positive
half's output current crosses zero at −3.5 dBFS, inside the signal. That is a
distortion question rather than a supply one, and it is open item D3.

## Totals at the mezzanine

| Rail | At the rail | From the header | Provenance |
| --- | --- | --- | --- |
| Element reference, 3.34 kΩ elements | 58.6 mA | 60.6 mA of +5V | calculation + datasheet Cpd |
| Clock chain | 33.5 mA | 35.5 mA of +5V | datasheet |
| Op amp positive | 21.6 mA | 23.6 mA of +5V | datasheet + LT3045 ground pin |
| Translator A side | <1 mA | 3 mA of +5V | calculation, LT3045 ground pin |
| **From +5V** | | **123 mA** | |
| Op amp negative, incl. element and network current | 56.5–63.5 mA | **64 mA of −6V** | datasheet + calculation |

**123 mA of +5V and 64 mA of −6V**, against 238 mA of +5V alone before
0015. The difference is not the rail that was added — it is the 73 mA of
conversion overhead that went away with the pump. A doubler costs about twice
its output at the input, and the negative rail was inverted from the
already-doubled one, so it was paid for twice over.

That overhead is also what forced the difference network to 604 Ω and cost
2.1 dB. At 200 Ω the negative rail wants 63.5 mA rather than 44.8, which is
now an ordinary number on a rail a main-board inverter makes directly. Both the
2.1 dB and the current are accounted for above.

Headroom at the worst input. The main board's buck holds +5V at 5.02 V, and
five parallel header contacts at 20 mΩ drop 2 mV at 123 mA (*estimate* on the
contact resistance), so the module's LT3045s see about 5.0 V against a 3.32 V
output — 1.7 V against a dropout of a few hundred millivolts. The part that
used to need checking here was the charge pump, whose 4.5 V minimum sat above
the 4.43 V a bus-powered board could deliver. It is gone, and so is the
question.

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

## Before enumeration — retired

This section used to size everything against a device drawing one unit load
until the host configures it: 150 mA on USB 3.0, 100 mA on USB 2.0. **That rule
no longer applies.** 0014 replaced bus power with a 12 V supply, so nothing on
either board waits on enumeration for current, and the mezzanine's rails come
up when the adapter is plugged in.

Three things were shaped by the retired rule and are worth naming, because each
one now stands or falls on its own merits rather than on a budget:

- **`MUTE_N` gating the analog rails.** Kept, but for the audio reason only —
  the element lines are undefined until the FPGA configures and the jack has no
  DC blocking. That makes it open item D10 rather than a requirement.
- **The element resistor at 3.32 kΩ.** One of its three justifications is now
  retired: it had to fit one unit load at power-on with the flip-flops in an
  undefined state. With that gone the value can be revisited, and moving to
  2585 Ω buys about **0.67 dB** of stage SNR for roughly 4 mA. Note that
  2585 Ω is **not** an optimum — it is where the element resistors' own thermal
  noise equals the digital floor, and that noise falls monotonically as R does,
  so lower is always quieter and always costs more current. An earlier version
  of this page called it a noise optimum worth 1.1 dB; both were wrong. Open
  item, and still blocked on `analog.py` pricing six amplifiers rather than
  four.
- **Rejecting the single-chip divider.** The Si53308 was rejected for drawing
  65 mA. It is still the wrong choice, but now because 65 mA to replace two
  parts drawing 16 mA is a poor trade on a board built around a quiet clock.

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

Every rail on this board is sourced, and the arrangement changed twice since
this section was first written — once when the parts were chosen, once when
0015 moved the negative rail off the board.

| Rail | Source | Note |
| --- | --- | --- |
| `+3V3_REF` | LT3045, U5 | The rail **is** full scale, so its noise is the converter's |
| `+3V3_CLK` | LT3045, U6 | Separate from the reference so element switching cannot reach the oscillators |
| `+2V5` | LT3045, U9 | The translator's A port faces the header; nothing here reaches the signal |
| `+5V_A` | LT3045, U14 | Straight off the header's +5V. No doubler: the stage needs 3.5 V and the header carries 5 |
| `-5V_A` | LT3094, U8 | From the mezzanine's −6V, made by an inverter on the main board |

**The charge pump is deleted**, with its two flying capacitors, two ADJ
dividers and two reference bypasses. This board has no switching converter on
it at all, which is the property 0015 was chosen for — the three
alternatives each relocated a switcher rather than removing one.

Both final regulators stay where they always were, and deliberately: their
rejection is what the design leans on, and it is wanted at the point of load
rather than at the far end of a connector.

## What is still uncertain here

| Figure | Why it is not settled |
| --- | --- |
| 34.3 mA of register current | `Cpd` read as per flip-flop rather than per package; a bench measurement settles it, and the rail is 26 mA if the other reading is right |
| 10.4 mA of element filter capacitors | Depends on the rotation's transition rate, which is a model question, and it is the one term on this rail that is not constant with code |
| 10 mA of fanout buffer | Read off a curve rather than a table; the tabulated figure is 33 mA at 100 MHz with four outputs loaded |
| 3 mA of pump quiescent | Datasheet gives 3 mA typical and 6 mA maximum on each input pin in constant frequency mode |
| 4.43 V at the header | Guaranteed USB minimum plus *estimated* ferrite and contact drops; it decides whether the charge pump is inside its input range |

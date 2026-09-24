# The output difference amplifier, in SPICE

Simulation: [`hardware/sim/difference_stage.py`](../../../hardware/sim/difference_stage.py).
Run it with `./.venv/bin/python hardware/sim/difference_stage.py`; it exits
non-zero if any assertion fails or any tamper is missed. Every number below is
printed by that script.

It answers three things the repository had asked and never costed: how well the
four 604 Ω resistors have to match, whether that rejection survives to the top
of the band, and what `actions.md` **D3** — the unequal input impedances —
actually costs.

`output_stage_ac.py` already measures the three filter poles and the in-band
droop. None of that is repeated.

---

## The three answers, first

1. **The 0.1 % array already specified is adequate, with margin — and it is
   adequate for a reason worth writing down: the common mode it rejects is
   DC.** A ratio mismatch on a DC common mode buys a DC offset, not in-band
   error. At 0.1 % worst case the offset is **2.78 mV**, beside the 1.4 mV
   `parts-notes.md` already accepts from the 402 Ω array and inside a 10 mV
   budget at a jack with no coupling capacitor. The certain in-band leak is
   **−189.3 dBFS**, 53 dB under the chain's −136.5. **No part change.** One
   wording change: the BOM says `604R 0.1% thin film`, which is an *absolute*
   tolerance and permits a 0.2 % ratio error; the quantity that does the work
   is the ratio.

2. **Above 8.1 kHz the rejection is set by the two 1.3 nF C0G capacitors, not
   by the array** — and the netlist gives them no tolerance at all. At 20 kHz
   an exact array with ±5 % capacitors gives 46.1 dB where a 0.1 % array with
   exact capacitors gives 54.0 dB. It costs nothing today, because there is no
   AC common mode of consequence, but the BOM is silent on the component that
   dominates the figure. The array's own parasitics are never the binding term.

3. **D3 is real, and larger than its own description.** The 241 Ω / 302 Ω load
   ratio is 1.25 to 1, but the quantity that governs even-order cancellation is
   the *output current swing*, and that differs by **1.499 to 1**. Measured,
   the output stage's even-order cancellation is **5.1 dB**. The positive
   half's output current also **changes sign at −3.5 dBFS**, inside the signal,
   where the negative half's never does. The fix is a value change, not a part
   change: the non-inverting leg at **R/3 = 201 Ω** restores the cancellation
   to **more than 40 dB** — the residual falls below what this measurement can
   resolve — keeps gain, rejection and pole 3 exactly where they are, and costs
   4.6 mA on the negative rail at mid code.

---

## What was verified against a datasheet, and what was assumed

The OPA1612 datasheet was fetched from ti.com and read out of the electrical
characteristics table: **SBOS450C, July 2009, revised August 2014**.

| Constant | Value | Source |
| --- | --- | --- |
| Gain-bandwidth | 40 MHz at G = +1 | **Verified**, SBOS450C §6.4 |
| Open-loop gain | 114 dB typ / 110 min at R_L = 2 kΩ; 130 typ / 114 min at 10 kΩ | **Verified** |
| CMRR | 120 dB typ, 110 min, (V−)+2 ≤ V_CM ≤ (V+)−2 | **Verified** |
| PSRR | 0.1 µV/V typ, 1 µV/V max | **Verified** |
| Common-mode range | (V−)+2 to (V+)−2 | **Verified** |
| Lowest published THD+N load | 600 Ω | **Verified**, Figures 7–11 |
| Open-loop output impedance Z_O | *"See Figure 28"* — a curve, no number | **Unavailable. Assumed 15 Ω**, swept 5–50 |
| CMRR vs frequency | *"Figure 14"* — a curve, no number | **Unavailable.** Held flat; bounded below |
| Output-stage nonlinearity | nothing published | **Assumed**; the result is a ratio, which does not depend on it |
| 1.3 nF capacitor tolerance | the netlist says `1.3nF C0G` and no more | **Assumed ±5 %**, with ±1 % shown alongside |
| Element resistor tolerance | `0.1% thin film` | Read off the netlist |
| Reference-rail noise | 0.8 µV | `0009`, quoting the LT3045 |

Every resistor and capacitor value, and the wiring of the four-resistor
network, was read off `hardware/netlist/output_module.py` — including the
`rn[1..8]` pin assignment, which is what fixes *which* resistor is in *which*
leg and therefore which impedance each half sees.

**Two model figures deliberately not used.** `model/lyrebird_model/analog.py`
prices four amplifiers where the board has six (`actions.md` B1), so its stage
figures describe a circuit that was not built; nothing here comes from it. The
only model number used is the **−136.5 dBFS** in-band noise of the digital
chain, which is a chain figure and not a stage figure.

**A small correction in passing.** `output_stage_ac.py` uses `AOL_DB = 120.0`.
SBOS450C gives 114 dB typ at 2 kΩ and 130 dB typ at 10 kΩ; 120 is neither.
This file uses 114 dB, the typical at the lowest load the datasheet specifies.
`output_stage_ac.py` was not modified — its results do not turn on the figure.

### The operating point everything is measured against

| | |
| --- | --- |
| Unit element current | 3.3 V / 3.34 kΩ = 0.988 mA |
| Common mode at **both** transimpedance outputs | **−1.3901 V, at every code** |
| Full scale at the difference output | +2.7803 V peak, **1.9660 V RMS** |
| 0 dBFS, for every dBFS figure below | 1.9660 V RMS |
| −136.5 dBFS | 294 nV RMS |

---

## 1. How much matching the 1.39 V of common mode requires

### Rejection is a ratio property, and the simulation shows it rather than asserting it

| the four 604 Ω resistors | CMRR at 20 Hz |
| --- | --- |
| exact | 119.6 dB — the amplifier's own 120 dB |
| **all four 1 % high together** | **119.6 dB** — absolute error, ratios intact |
| **one of the four 1 % high** | **46.0 dB** — ratio broken |

To first order `A_cm = [(e4 − e3) − (e2 − e1)] / 2`, so absolute error cancels
out entirely and only the two *ratios* R2/R1 and R4/R3 matter. That is the
whole argument for one array rather than four parts, and it is why the BOM's
`0.1%` — an absolute tolerance, which bounds each resistor independently and
therefore permits `A_cm = 2t` — understates what is actually being bought.

### What a tolerance costs

Worst-case sign pattern, which is what a tolerance permits:

| ratio | A_cm | CMRR | DC offset | leak, reference rail | leak, element bound |
| --- | --- | --- | --- | --- | --- |
| 0.010 % | 1.99e−04 | 74.0 dB | +0.277 mV | −209.3 dBFS | −150.3 dBFS |
| 0.025 % | 4.99e−04 | 66.0 dB | +0.694 mV | −201.4 dBFS | −142.3 dBFS |
| 0.050 % | 9.99e−04 | 60.0 dB | +1.389 mV | −195.3 dBFS | −136.2 dBFS |
| **0.100 %** | **2.00e−03** | **54.0 dB** | **+2.782 mV** | **−189.3 dBFS** | −130.2 dBFS |
| 0.250 % | 5.01e−03 | 46.0 dB | +6.967 mV | −181.3 dBFS | −122.2 dBFS |
| 1.000 % | 2.02e−02 | 33.9 dB | +28.08 mV | −169.2 dBFS | −110.1 dBFS |

**The offset column is the real answer, and it is not a noise-floor question.**
The common mode is DC at every code by construction (0008), so what imperfect
rejection buys is a DC offset. A DC offset does not compete with an in-band
noise floor. 2.78 mV at 0.1 %, adding to the 1.4 mV the 402 Ω array already
contributes, is about **4.2 mV worst case** at a jack with no coupling
capacitor — which is what `parts-notes.md` already decided to live with, at a
scale it already named.

**Only the part of the common mode that moves can reach −136.5 dBFS**, and
there is very little of it:

- **Reference-rail noise**, the one certain term: 0.8 µV on 3.3 V appears at
  the transimpedance outputs scaled by 1.3901/3.3, i.e. **337 nV RMS**.
  Through a 0.1 % array that is **−189.3 dBFS**. It is also the wrong thing to
  spend rejection on: reference-rail noise reaches the output far more strongly
  through the *differential* path, because it multiplies the signal rather than
  adding to it. Rejection buys nothing against it.
- **Element mismatch**, as a bound rather than a figure: 0.1 % elements with
  seven of fourteen high put **303 µV** of code-dependent error on the
  common-mode sum. Through a 0.1 % array that would be −130.2 dBFS, 6 dB above
  the chain floor. **This is a bound, not a prediction**: DWA rotates *both*
  banks, so the common-mode sum is shaped by the same mechanism as the
  differential one, and the real in-band figure is far below. It is quoted
  because it is what the leak becomes if rotation ever stops shaping the
  common-mode sum — the bound crosses −136.5 dBFS at **0.048 %**.

### The answer, as a part

**0.1 % is adequate. Order the array you already specified.** The one change is
to the words on the BOM line: ask for **ratio tolerance 0.1 %** (or better,
whatever the chosen array's ratio spec is — matched thin-film arrays commonly
specify 0.05 % ratio inside a 0.1 % absolute), because that is the parameter
that sets rejection and the current line specifies only the absolute value.

Tightening to 0.05 % or 0.01 % buys 6 dB and 20 dB of rejection respectively,
and there is nothing in the circuit that needs it. The single case where 0.05 %
would be required is the contingency above: a change to 0008's rotation rule
that stops shaping the common-mode element sum. Worth a sentence in 0008 rather
than a part change.

---

## 2. D3 — the unequal input impedances, costed

### The impedances themselves, measured

| | |
| --- | --- |
| Small-signal load at the **positive** output | **241.4 Ω** (402 ‖ 604) |
| Small-signal load at the **negative** output | **301.6 Ω** (402 ‖ 1208) |
| Ratio | 1.250 to 1 |
| At 20 kHz | 240.5 − 14.6j and 299.1 − 26.5j Ω |

`actions.md` D3's arithmetic is confirmed exactly. Its accompanying point is
confirmed too and is worth restating more strongly: **both loads are below the
600 Ω of the OPA1612's lowest published distortion curve, and its open-loop
gain is not specified below 2 kΩ at all** — 114 dB typ at 2 kΩ, 130 dB typ at
10 kΩ. The part is being run at an eighth of the lowest load it is
characterised at, on both halves. The asymmetry genuinely cannot be costed from
the datasheet.

### The load ratio understates the asymmetry

With both polarities moving together — which is how the circuit runs, and not
how a one-port impedance measurement drives it — the amplifiers deliver:

| | at −FS | at +FS | slope |
| --- | --- | --- | --- |
| positive half | **+2.302 mA** | −11.519 mA | −6.910 mA per unit code |
| negative half | −9.218 mA | 0.000 mA | +4.609 mA per unit code |

**The swings differ by 1.499 to 1, not 1.250 to 1.** The reason is topological:
the inverting leg's far end is the amplifier's summing node, which moves with
the *other* half, so the positive amplifier sees `1/R_f + 1.5/R`; the
non-inverting leg's far end is ground, so the negative amplifier sees
`1/R_f + 1/(2R)`. The extra half comes from the summing node following v_n.

**And the positive half's output current changes sign at code −0.667, which is
−3.5 dBFS.** Its output stage traverses zero current — the crossover region —
for any signal reaching that level, which is most of them. The negative half's
current reaches zero only at exact positive full scale. `parts-notes.md`'s
"the transimpedance outputs sit between 0 and −2.8 V, never positive, so the
network's current flows out of ground into those outputs and is sunk to V−" is
true of the *network* current and not of the *amplifier's*. That sentence is
load-bearing for the supply-current argument, which survives; it is not a
statement about what the output stage does.

### What the imbalance costs, in two parts

**Linear: essentially nothing.** The gain imbalance between the halves,
|(G_n − G_p)/G|:

| R_O (assumed) | 20 Hz | 1 kHz | 20 kHz |
| --- | --- | --- | --- |
| 5 Ω | 1.57e−08 | 1.92e−07 | 3.80e−06 |
| **15 Ω** | **4.71e−08** | **5.75e−07** | **1.14e−05** |
| 50 Ω | 1.57e−07 | 1.92e−06 | 3.80e−05 |

At 20 Hz the real part is 4.57e−08, which on 1.390 V of common mode is 0.06 µV
of output offset — four orders below the 2.78 mV the array itself gives. At
20 kHz the imbalance is almost entirely *reactive*: a phase mismatch between
the halves, which makes the common mode signal-dependent by 15.9 µV peak at
full scale and reaches the output through a 0.1 % array at **−158.9 dBFS**.

*(This had to be measured with complex gains. Comparing magnitudes reads an
order of magnitude low at 20 kHz, because above the dominant pole the
finite-loop-gain error is nearly all imaginary. The first version of this
measurement did exactly that and reported 1.05e−06 where the answer is
1.14e−05, which also happens to be what the closed form predicts.)*

**Even-order: most of it.** Provoked with a nonlinear output resistance
`R_O + β·I_out`, identical in both amplifiers, and read out of a DC sweep of
the code — the even part of the transfer curve about mid code *is* the
even-order term, exactly and without windowing:

| configuration | a2, worse half | a2, difference | cancellation |
| --- | --- | --- | --- |
| **as built**, β = 130 | 2.282e−08 V | 1.270e−08 V | **5.1 dB** |
| as built, β = 1300 | 2.282e−07 V | 1.267e−07 V | **5.1 dB** |
| 1208 Ω shunt at IV_N | 2.282e−08 V | 7.060e−09 V | 10.2 dB |
| **non-inverting leg at R/3 = 201 Ω** | 2.282e−08 V | 1.682e−10 V | **> 43 dB**, floor-limited |

β is assumed and the absolute values mean nothing on their own. The
**cancellation ratio** does, and it is a property of the network: two
coefficients ten times apart give 5.1 and 5.1 dB.

**Scope, which matters.** This is the *output amplifiers'* own even-order term.
The element-side cancellation 0008 is actually about — the reference rail, the
element resistors, the drivers — is upstream of the transimpedance stage and is
untouched by any of this. What the difference amplifier spends is the
even-order cancellation of the two output amplifiers themselves.

**Caveat.** The sweep is at DC, where loop gain is highest, so the absolute a2
here is far below the in-band value; it scales as 1/T and T falls 20 dB/decade
above 80 Hz. The ratio does not, because both halves' loop gains fall together.
Only the ratio is quoted.

### The fix, and what it costs

Mirror-image output currents need `|di_p/ds| = |di_n/ds|`, that is
`1/R_f + 1.5/R = 1/R_f + 1/(2Q)`, that is **Q = R/3 = 201.3 Ω** for the
non-inverting leg. Not a fitted number. Verified in the simulation:

- full scale **unchanged** at 2.7803 V — the gain condition is R4/R3 = R2/R1
  and both pairs stay equal;
- rejection **unchanged** at every frequency, exact or at 0.1 % ratio;
- pole 3 **unchanged**, with the non-inverting leg's capacitor scaled to
  3.9 nF (201.3 × 3.9 n = 604 × 1.3 n);
- cancellation 5.1 dB → **better than 43 dB**. The residual there is at
  this measurement's own floor: it moves by 2 dB between two solver tolerances
  that agree to 0.1 dB on the as-built circuit, and it does not scale with β
  the way a real residual would. The honest claim is a bound, not a value.

It costs **+4.6 mA on the negative rail at mid code** for both channels
(2.30 → 6.90 mA), and +9.2 mA at negative full scale (4.60 → 13.81 mA). On
`parts-notes.md`'s own table that lands between its 604 Ω and 402 Ω rows, and
by that page's doubling argument it is roughly 9–18 mA at the USB input — which
is not free against a board already at 472 mA. **This is a decision for 0008,
not a fix to apply.**

It also stops being one array of four equal resistors and becomes two matched
*pairs* (604/604 and 201/201). That is not a loss: rejection depends on
`(e4 − e3) − (e2 − e1)`, so only *within-pair* matching matters and cross-pair
matching does not enter at all. Two two-resistor matched pairs give the same
CMRR as one four-resistor array.

The cheaper half-measure — a 1208 Ω shunt from IV_N to ground, one extra part,
+1.15 mA per channel — equalises the small-signal loads exactly (it takes the
linear imbalance from 4.71e−08 to 2.37e−12 at 20 Hz) but only reaches 10.1 dB
of even-order cancellation, because equal *loads* are not the same condition as
mirror-image *currents*.

---

## 3. Whether the rejection holds across the band

CMRR, in dB:

| configuration | 20 Hz | 1 kHz | 20 kHz | 200 kHz |
| --- | --- | --- | --- | --- |
| everything exact: the circuit's own floor | 119.6 | 118.3 | 98.1 | 75.2 |
| …with the amplifier's CMRR at 80 dB, not 120 | 80.0 | 80.0 | 80.0 | 78.0 |
| resistors 0.1 % ratio, capacitors exact | 54.0 | 54.0 | 54.0 | 53.5 |
| resistors 0.01 % ratio, capacitors exact | 74.0 | 74.0 | 74.0 | 69.3 |
| **resistors exact, capacitors ±5 %** (unspecified) | 105.9 | 72.1 | **46.1** | 27.1 |
| resistors exact, capacitors ±1 % | 116.8 | 86.0 | 60.0 | 41.0 |
| **as built: 0.1 % array and ±5 % capacitors** | **54.0** | **53.9** | **45.6** | **27.2** |
| resistors exact, 0.5 pF across one array element | 119.6 | 119.2 | 103.6 | 79.0 |

Three findings.

**The two 1.3 nF capacitors dominate above 8.1 kHz.** The resistor term is real
and flat (`A_cm = 2t`); the capacitor term is imaginary and rises with
frequency (`A_cm ≈ jωRC·δ`), so they add in quadrature and cross where
`2t = ωRC·δ` — 8.1 kHz for 0.1 % resistors and ±5 % capacitors. At 20 kHz the
capacitors cost 8 dB more than the array does. **The netlist specifies no
tolerance for them at all** (`"1.3nF C0G"`), while it specifies 0.1 % for every
resistor that matters. ±1 % C0G in 0603 is an ordinary stocked part and would
put the capacitor term 14 dB below the resistor term everywhere in band. Given
that there is no AC common mode of consequence, this is a consistency
observation rather than a defect — but it is the component that sets the
figure, and it is the one the BOM does not constrain.

**The array's own parasitics are never the binding term.** 0.5 pF across one
604 Ω element leaves 103.6 dB at 20 kHz, 57 dB better than the capacitor
tolerance does. It is not *negligible* against the circuit's own 98.1 dB floor —
it moves it — but nothing in band is ever decided by it.

**The floor in the first row is the difference amplifier's own output
impedance**, not its CMRR. With a perfectly balanced network a common-mode
input still forces `v_cm/(2·604)` through the feedback leg, and the closed-loop
output impedance `R_O/(1 + T)` turns that current into an output voltage. It
falls at 20 dB/decade with the loop gain, which is the 119.6 → 98.1 → 75.2 dB
progression. This depends on the assumed R_O. It is also never the binding
term, so the assumption does not propagate into any conclusion.

The second row bounds the one datasheet figure that is a curve rather than a
number: the model holds the amplifier's CMRR flat with frequency, where
Figure 14 shows it falling. Forcing it to 80 dB at all frequencies — far worse
than the curve — leaves the as-built row unchanged at 20 kHz, because the
network terms are 34 dB worse than that anyway.

---

## 4. The tampers

Seven, all caught. Each breaks the thing one check claims to catch.

| tamper | what it proves |
| --- | --- |
| amplifier CMRR set to 400 dB | exact-network rejection goes 119.6 → 145.8 dB, so the 119.6 dB row is the amplifier's 120 dB and not an artefact of the network or the measurement |
| the 1.39 V of common mode removed (elements driven bipolar), mismatch left at 0.1 % | offset +2.782 mV → −0.000 µV. The offset tracks the common mode, which is what §1 says it measures |
| **the non-inverting leg's 1.3 nF deleted** | **the DC transfer curve does not move by a nanovolt** (+2.7816 → +2.7816 mV), so a check built on the offset alone — the natural one, since the offset is what the common mode buys — would pass a circuit missing half its compensation. 20 Hz rejection 54.0 → 54.0 dB, 20 kHz 54.0 → 26.1 dB |
| the two capacitors made a matched pair | 20 kHz rejection 45.6 → 54.0 dB, back to the array's own figure. The 20 kHz figure is the capacitors, as §3 says |
| **the load probed with the amplifier lifted off its own output** | gives 358.0 and 508.8 Ω against the correct 241.4 and 301.6 — lifting the amplifier takes the summing node's virtual ground with it and the 402 Ω feedback resistor stops being a 402 Ω load. This is a wrong answer the obvious method gives |
| the nonlinearity removed (β = 0) | a2 of the difference output 1.270e−08 → 1.469e−11 V. The extraction reports the nonlinearity, not a fitting artefact |
| network symmetric (R/3) but one amplifier twice as nonlinear | cancellation falls from its floor (43 dB or better) → 6.0 dB. The figure tracks half-to-half asymmetry from any source, not only from the resistor network |

Two of these found faults in the *checks* rather than in the design, which is
the point of running them:

- The **lifted-probe** tamper is the one that matters most, because lifting the
  amplifier to probe its output node is the first thing anyone would do. It
  reports 358 Ω and 509 Ω — plausible numbers, both wrong, and wrong in a
  direction that makes the asymmetry look *smaller* than it is (1.42 to 1
  rather than 1.25 to 1, and it hides the current-slope story entirely). `output_load` measures `V_out / I_out` with the amplifier in
  place instead.
- The **deleted capacitor** tamper is this file's version of the lesson the
  filter-topology check taught: a DC-only measurement of this circuit is
  completely blind to it. The offset does not move by a nanovolt while 20 kHz
  rejection falls 28 dB. §3 is made across the band for that reason.

A third check was wrong and the tamper discipline caught it before it reached
this document: the half-to-half gain imbalance in §2 was first measured on gain
*magnitudes* and reported 1.05e−06 at 20 kHz. The closed form says 1.14e−05.
Above the dominant pole the finite-loop-gain error is almost entirely
imaginary, so magnitudes hide it by an order of magnitude and look like
agreement.

---

## What to do with this

| | |
| --- | --- |
| **RN16/RN17, the 604 Ω arrays** | No change. Amend the BOM/netlist value string to specify **ratio** tolerance rather than the absolute 0.1 %. |
| **The two 1.3 nF C0G capacitors** | Consider ±1 %. They set the rejection above 8.1 kHz and are the only components in the network with no tolerance specified. Not required by any budget. |
| **`actions.md` D3** | Now costed. 5.1 dB of even-order cancellation as built, from a 1.499-to-1 current-swing asymmetry, with the positive half crossing zero output current at −3.5 dBFS. `Q = R/3` restores it to better than 43 dB for 4.6–9.2 mA on the negative rail and two matched pairs instead of one array. A decision for 0008. |
| **`parts-notes.md`** | The clause "the transimpedance outputs sit between 0 and −2.8 V, never positive, so the network's current flows out of ground into those outputs" is true of the network current and false of the amplifier's own output current on the positive half. The supply-current conclusion it supports is unaffected. |
| **`output_stage_ac.py`** | `AOL_DB = 120.0` is not a SBOS450C figure (114 typ at 2 kΩ, 130 typ at 10 kΩ). Cosmetic — none of its results turn on it. Not modified. |
| **0008** | Two sentences: that the even-order cancellation it buys does not survive the output stage as wired, and that its rotation rule is what keeps the common-mode element sum shaped — without which the array would need 0.05 % ratio rather than 0.1 %. |

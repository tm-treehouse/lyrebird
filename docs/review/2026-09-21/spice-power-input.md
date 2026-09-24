# SPICE — the 12 V wall-wart input, in transient and in fault

Scope: the input chain 0014 introduced, as `hardware/netlist/main_board.py`
builds it under the "Wall wart input" comment — J4, F1, D1, D2, the 22 µF and
100 nF bulk, U5, and the rails behind it.

    ./.venv/bin/python hardware/sim/power_input_transient.py     # ~23 s

`hardware/verify_power.py` already checks the steady state and all twelve of
its checks pass. Nothing here repeats it. Every scenario below is a
trajectory: what happens when the plug goes in, when it goes in backwards,
when it is the wrong plug, and in what order the rails arrive.

**20 checks, 16 pass.** Four fail: one marginal rating, one absolute-maximum
violation, and two consequences of a gating circuit that decision 0014 says
was retired and the netlist still builds. **Nine tampers, all nine did what
the simulation predicted** — seven moved the check they targeted, and two
were run because they were expected *not* to and that is the finding.

---

## 0. Method, and what is a datasheet number

`hardware/datasheets/` still contains only `.gitkeep`. Four vendor PDFs were
fetched and read in full for this pass, and every constant in
`power_input_transient.py` carries the source it came from. The file prints
the whole list at the end of its run, split four ways.

| Part | Document | What came out of it |
| --- | --- | --- |
| U5 LMR33630ADDA | TI **SNVSAN3F**, Nov 2020 | `tSS` 2.9/4/6 ms, `VEN-H` 1.231 V, VCC UVLO 3.7 V, `ISC` 4.5 A, VIN abs max **−0.3 to 38 V**, op max 36 V, `TSD` 165 °C |
| D2 SMAJ15A | Vishay **88390** rev 09-Jan-2024, cross-checked against Bourns and Kemet | `VBR` 16.7–18.5 V at 1.0 mA, `VC` 24.4 V at `IPPM` **16.4 A**, `αVBR` **0.088 %/°C**, `RθJA` 120 °C/W, `TJ` max 150 °C, SMA (DO-214AC) |
| D1 SS34 | Vishay **88751** rev 23-Apr-2020 | `VRRM` 40 V, `IFSM` 100 A, `VF` 0.5 V max at 3 A, `IR` **0.5 mA at 25 °C and 20 mA at 100 °C**, `RθJA` 55 °C/W |
| F1 polyfuse | Littelfuse **1812L series**, rev 12-Jul-2010 | the whole 1812L110 family table — see F-1 below |

Downstream (LT3045, LTM4622, GateMate DS1001) the constants are taken from
`docs/review/2026-09-21/main-board.md`, which quotes those datasheets
verbatim. They are marked as datasheet-at-one-remove, not as read here.

Guessed, and marked so in the run: the adapter (12 V nominal, 19 V fault),
its output impedance, the cable's resistance and inductance, the barrel
contact's closure time, the ceramics' ESR and ESL, ambient, the BSS138 gate
threshold, and the main board's per-rail currents (which come from a page
both reviews found stale). **Every conclusion below that depends on one of
those was swept over it**, and the report says how far it moved.

Three models are fitted rather than quoted, and each is anchored to a
datasheet point the report names: the SS34 junction (to `VF` = 0.45 V at
3 A), the SMAJ breakdown knee (to `VC` = 24.4 V at 16.4 A), and the SMAJ
forward junction (to `VF` = 3.5 V at 25 A).

### One trap, recorded because it produced a confident wrong answer

This ngspice build **accepts `limit(x, lo, hi)` in a `B`-source expression
and silently evaluates it to zero.** The TVS model used it to clamp an
exponent; the whole exponential collapsed to the constant `IT`, and the
simulation returned a clean, plausible operating point for every corner. It
was caught only because three different `VBR` corners returned *identical*
currents, which is not a thing three different parts do. `min(max(...))`
works. Nothing warns.

---

## 1. Inrush at plug-in

The buck is not a load yet — its VCC LDO has to reach 3.7 V, `EN` has to
clear 1.231 V, and 2.9 ms of internal soft start follow — so the plug-in
event charges the 22 µF and the 100 nF on `+12V` and nothing else.

Nominal case (1 µH of cable, 1 µs contact wipe, `R1max` fuse):

```
peak 17.1 A, 29 µs wide, 261 µC delivered, I²t = 2.78 mA²s
F1 absorbs 0.56 mJ and warms its polymer by 9.2 milli-°C
```

Over 24 combinations of cable inductance (50 nH to 3 µH), contact closure
(0.1 to 10 µs) and fuse resistance (`Rmin` to `R1max`):

| | range |
| --- | --- |
| peak current | **13.3 to 27.9 A** |
| energy into F1 | 0.16 to 0.56 mJ |
| charge delivered | 261 to 292 µC — *does not move* |

**The fuse verdict is the robust one and the peak is the one that moves.**
Peak current is set entirely by parasitics nobody on this project has
measured. Energy is not: it is ½CV² through a fixed divider of resistances,
and at 12 V that is 1.6 mJ for the whole loop no matter what the cable does.
Against the 6.3 J it takes to trip a 1.1 A PPTC from cold, the margin is
**~11 000×**.

**This is not a nuisance-trip risk and it cannot be made into one by
capacitance.** Tamper T3 fits 2200 µF — a hundred times the bulk, the change
someone would make if they thought more decoupling was free — and F1 still
warms by less than a degree. That is a hole in the check rather than a
comfort: see §6.

**I-3 fails.** At the short-cable end the peak reaches 27.9 A against the
1812L110/24's **`Imax` = 20 A**. `Imax` is defined in the datasheet as "the
maximum fault current the device can withstand without damage at rated
voltage", which is about interrupting a fault rather than about a 20 µs
capacitive spike, so this is a letter-of-the-spec failure and not obviously
a physical one. It is reported as a failure because nothing in the datasheet
says a capacitive spike is exempt, and it is one question to a vendor. Note
that the 6 V `1812L110` and the 16 V `1812L110/16` are both rated `Imax` =
100 A; only the 24 V and 33 V parts drop to 20 A, so this interacts directly
with F-1.

D1 is comfortable: 27.9 A for 21 µs against a 100 A / 8.3 ms `IFSM`.

---

## 2. Reverse polarity

A centre-negative adapter in a centre-positive jack. D1 blocks, and then
**the only current anywhere in the circuit is D1's own reverse leakage** —
and where that current goes is the whole story.

| reversed adapter | across D1 | protected rail settles at |
| --- | --- | --- |
| 12 V | 11.6 V | −0.399 V |
| 19 V | 18.6 V | −0.399 V |
| 24 V | 23.6 V | −0.399 V |

Against a 40 V `VRRM`, the worst adapter that fits this barrel leaves 1.7×.
**D1 blocks, with margin, and the reverse-voltage half of the question is
closed.**

### R-2 fails: the protected rail goes negative, and it is not supposed to

D1's reverse leakage flows *out of* the `+12V` node. Nothing on the board
sources current into that node — so it falls until something conducts, and
the only thing that does is **D2, forward**.

```
D1 leaking 0.5 mA (the 25 °C datasheet maximum):  rail settles −0.399 V, 7.8 ms in
D1 leaking  20 mA (the 100 °C datasheet maximum): rail settles −0.497 V, 0.13 ms in
```

The LMR33630's absolute minimum on both `VIN` and `EN` is **−0.3 V**
(SNVSAN3F table 7.1). The rail crosses that line once D1 leaks more than
**25 µA**, and the datasheet allows twenty times that at room temperature.

Two honest qualifications, and the check carries both:

* **0.5 mA is a maximum at rated `VR`.** A typical SS34 at 12 V — under a
  third of its rated reverse voltage — leaks far less, and a real part may
  well sit on the right side of the line. A specified one does not. The
  threshold, 25 µA, is the number to argue about.
* **The forward drop this turns on is not on any SMAJ datasheet.** The only
  forward point Vishay, Bourns and Kemet give is 3.5 V at 25 A. Check R-3
  sweeps the junction over four decades of saturation current — four decades
  of die area — and the rail lands between −0.378 V and −0.616 V. **Every
  one of those is on the same side of −0.3 V**, so the verdict does not
  depend on the guess.

What is actually at risk is unspecified: TI does not document an internal
clamp from PGND to VIN. If there is one it will carry this current instead,
and if there is not, the pin sits 100–200 mV outside its rating for as long
as the adapter is in. Either way this is a question for TI, not a
calculation.

### R-4, which is the part 0014 does not say

0014 justifies the series Schottky at length and never mentions the TVS in
the reverse case. **The TVS is load-bearing there.** With D2 removed the same
leakage takes the protected rail to **−12.2 V** — U5's `VIN` pin at the full
reversed supply. D2 sits *behind* D1, so it never sees the reversed input and
never breaks down; what it does is shunt D1's leakage away from U5.

Tamper T5 makes this concrete: substituting an **SMAJ15CA** for the
SMAJ15A — one character in a BOM line, the bidirectional part, no forward
conduction below 16.7 V — takes the rail to **−12.1 V**. The unidirectional
suffix is not a preference here; it is the reverse-polarity protection.

Nothing heats: 10 mW in D2 at the 100 °C leakage maximum, 20 mA through a
1.1 A fuse. Reverse polarity is survivable indefinitely, not merely
survivable.

---

## 3. The wrong adapter — a 19 V laptop brick

0014: *"the TVS conducts and the fuse trips"*. `verify_power.py`'s check
"A 19 V brick is clamped, not passed" asserts the same thing.

**The first half is right. The second half is wrong, and it is the half that
matters.**

| corner | first current | settled | at U5's VIN | junction | power |
| --- | --- | --- | --- | --- | --- |
| `VBR` minimum, 16.7 V | 934 mA | **41.1 mA** | 18.62 V | **117 °C** | 0.77 W |
| `VBR` nominal, 17.6 V | 235 mA | 17.5 mA | 18.64 V | 64 °C | 0.33 W |
| `VBR` maximum, 18.5 V | 3 mA | 1.8 mA | 18.65 V | 29 °C | 0.03 W |

### What actually happens

A feedback loop no DC calculation contains: the TVS conducts, conducting
heats it, and heating raises **its own breakdown voltage** at 0.088 %/°C —
which reduces the conduction. The part walks its clamp voltage up until it
meets the applied voltage and parks there.

* **Isothermally — if the junction never heated — the fault is 0.95 A and
  17 W.** That is the number the arithmetic gives, and it would destroy an
  SMA part.
* **With the tempco, it settles at 41 mA and 0.77 W**, junction at 117 °C.
  Tamper T7 sets α to zero and the same fault computes a 2095 °C junction.
  **The 0.088 %/°C is the entire difference between a part that survives this
  and one that does not.**

The equilibrium is set by `RθJA` = 120 °C/W, which is a datasheet number. The
two thermal capacitances are guesses; check OV-5 sweeps both over a hundredfold
range and the settled junction temperature moves by **0.0 °C**. They set how
long the loop takes to close (about 100 ms), not where it closes.

### The fuse is never involved

Total input current peaks at **1076 mA — below the 1.1 A hold** — and settles
at 175 mA. Taking the adapter's output impedance down to 20 mΩ raises the
peak only to 1.46 A, still under the 1.95 A trip, and F1's polymer rises
0.8 °C against the 105 °C it needs. At 1.46 A this fuse's own time to trip is
**22 seconds**, and the TVS has backed off within 100 ms.

**There is no adapter impedance for which this fuse opens.** The TVS heats
and retreats three orders of magnitude faster than the polymer can respond.

### So what is the actual failure mode

Not destruction. **The board runs.** 18.6 V reaches U5, which is a 36 V part,
and everything downstream is unchanged. What is left is a TVS dissipating
0.3–0.8 W forever, with its junction pinned near 117 °C at the `VBR`-minimum
corner — 33 °C from its rating.

And that temperature **barely moves with ambient**, which is the
counter-intuitive part: the loop regulates junction temperature, not current.
Raising the room lowers the current until `VBR(Tj)` matches the brick again.
At a 40 °C ambient the part still sits near 117 °C, just passing less. The
margin to `TJ` max is not a thermal-design margin that improves with a better
layout; it is set by the ratio of the brick voltage to `VBR` at the minimum
corner.

### OV-3 is true and it is not evidence

18.6 V is below 36 V. So is 19 V. **The TVS is not what saves U5 from a 19 V
brick** — U5's own input range is. Tamper T6 removes D2 from the netlist
entirely and U5 still sees 18.7 V, and `verify_power.py`'s check still
passes. See §6.

---

## 4. Rail sequencing on start-up

Every converter modelled as its enable threshold, its reference ramp and its
output impedance, driving the real output capacitance and the real load.
Nothing switches: forty thousand switching cycles to learn four arrival times
would be forty thousand cycles spent on the one thing that does not decide
them. Each ramp comes from the mechanism the datasheet names — U5's fixed
internal 4 ms, U4's 1.4 µA into 10 nF to a 0.6 V reference, U3's 100 µA into
`R_SET ∥ C_SET` (the LT3045's `2.3·R·C` being ln 10 times that RC, which is
where the formula comes from).

**As built, powered from the wall, no USB host attached:**

| rail | 10 % | 90 % | settles at |
| --- | --- | --- | --- |
| `+12V` | 11 µs | 46 µs | 11.63 V |
| `+5V` | 0.42 ms | **3.63 ms** | 5.009 V |
| `+2V5` | 1.47 ms | **4.90 ms** | 2.497 V |
| `+3V3` | 1.79 ms | **9.10 ms** | 3.318 V |
| `+1V0` | 1.47 ms | **never** | 0.000 V |

Input current: an 8.1 A plug-in spike (§1), then **184 mA peak** through
start-up and 166 mA settled. The soft start is what keeps it there —
charging 66 µF to 5.02 V in 4 ms is only 83 mA on the output side. No rail
overshoots: `+2V5` peaks at 2.497 V against a 2.75 V absolute maximum,
`+1V0` at 0.998 V against 1.20 V.

### S-2: D-6's 359 ms is gone; the ordering it created is not

The FT601Q sees `VCCIO` before `VCC33` by **4.21 ms**, where the
2026-09-21 review measured 355 ms. Reducing `C_SET` to 100 nF closed the gap
by 85×. The skew is in the same direction as before and is now short enough
that nobody would design around it — but it has not been *removed*, and
FTDI's datasheet still states no ordering requirement either way. Tamper T8
puts 4.7 µF back and the skew returns to 357 ms, which reproduces D-6 to
within half a percent.

### S-3 fails: the FPGA core rail never comes up on a powered board

`CORE_RUN` is pulled to `+5V` through R8 and pulled down by Q1 whenever
`FT_WAKEUP_N` is high. `FT_WAKEUP_N` is pulled up to `+2V5` through 100 k and
is driven low only by the FT601Q, only when it sees bus activity. **With no
cable in the socket, that never happens**, so `+1V0` never arrives. With a
host driving `WAKEUP_N` low at 30 ms the rail follows at 33.9 ms, which is
the LTM4622's 4.3 ms soft start and nothing else. Tamper T9 removes the
gating and `+1V0` arrives at 4.90 ms alongside `+2V5`.

This is not a new circuit. It is 0009's enumeration gating, and **0014's own
consequences list says it was retired**:

> **Retired.** … `MUTE_N`'s pre-enumeration role; the LTM4622 run-pin gating
> and its `WAKEUP_N` NMOS.

`main_board.py:341-367` still builds it — R8, R7, Q1 and the comment
explaining the one-unit-load rule that 0014 deleted. A board powered from the
wall with no host attached has its FPGA core rail held off by a bus-presence
signal from a bus that is now data-only. Nothing downstream is damaged
(DS1001 §3.2.1: "no restrictions concerning order of voltage switch-on"), but
the behaviour is not the one the decision record describes.

### S-4 fails: the core rail starts and then collapses

Only a transient shows this. `CORE_RUN` is pulled to `+5V` the moment `+5V`
exists, and Q1 cannot pull it down until `+2V5` has climbed to the BSS138's
gate threshold. Between those two instants `RUN2` is above its 1.27 V
threshold, and **channel 2 soft-starts into that window and is shut off
mid-ramp**:

```
+1V0 rises to 319 mV between 1.25 ms and 2.43 ms, then collapses to zero
```

The 2026-09-21 review read this statically — "`WAKEUP_N`'s 100 k pull-up goes
high → Q1 on → `+1V0` stays off" — which is right about the end state and
misses the 1.2 ms in between. Harmless against DS1001. But it is a partial
core rail arriving and leaving on every power-up, and nobody chose it. The
window is bounded by the BSS138's gate threshold, which is an **assumed**
0.8–1.5 V here and was not read from a datasheet for this pass; a higher
threshold widens the window.

---

## 5. Findings

Ordered by what it costs to get wrong.

### F-1 (high) — the polyfuse in the netlist does not exist at this voltage

`main_board.py:167` specifies `"1.1 A hold, 2.2 A trip"` in an 1812
footprint, with no voltage rating. In the Littelfuse 1812L table **exactly
one part has 1.1 A hold with 2.2 A trip — the `1812L110` — and it is rated
6 Vdc.** Every 1812L110 rated above 12 V trips at **1.95 A**:

| part | `Ihold` | `Itrip` | `Vmax` | `Imax` | `Rmin` | `R1max` |
| --- | --- | --- | --- | --- | --- | --- |
| 1812L110 | 1.10 A | **2.20 A** | **6 V** | 100 A | 0.040 Ω | 0.210 Ω |
| 1812L110/16 | 1.10 A | 1.95 A | 16 V | 100 A | 0.060 Ω | 0.180 Ω |
| 1812L110/24 | 1.10 A | 1.95 A | 24 V | **20 A** | 0.060 Ω | 0.200 Ω |
| 1812L110/33 | 1.10 A | 1.95 A | 33 V | 20 A | 0.060 Ω | 0.200 Ω |

The board runs at 12 V nominal and 0014 explicitly designs for a 19 V brick
in the same barrel, so a 6 V or 16 V part is out of its rating in a case the
decision record names. **The part this board needs is the `/24` or the
`/33`**, and with either of them the trip current is 1.95 A rather than the
2.2 A the netlist and `verify_power.py` both carry.

Everything in this file is simulated against the `/24`. None of the verdicts
change at 2.2 A — the 19 V fault never reaches 1.5 A — but the netlist value
string is a part number nobody can order for this rail, and the `/24`'s
`Imax` = 20 A is what I-3 fails against.

### F-2 (medium) — reverse polarity puts U5's VIN below its absolute minimum

§2. The protected rail settles at −0.40 V at the 25 °C leakage maximum
against a −0.3 V limit, held there only by D2 conducting forward. Threshold
is 25 µA of D1 leakage; the datasheet allows 500 µA. Ask TI whether the
LMR33630 has an internal PGND-to-VIN clamp and what it is rated to carry; if
it does not, a second small Schottky from GND to `+12V` — anode on GND — is
one part and moves the clamp to 0.25 V.

### F-3 (medium) — 0014 and `verify_power.py` both claim the fuse trips on a 19 V brick, and it does not

§3. `verify_power.py`'s check "A 19 V brick is clamped, not passed" says *"so
the TVS conducts and the fuse trips"* and `0014` says the same. The TVS
conducts; the fuse never trips at any adapter impedance; and the steady state
is a 0.77 W heater at 117 °C junction, permanently, on a board that otherwise
works fine. **This is not a fault that announces itself.** It is a warm
component and a slightly hot barrel jack, for the life of the product.

Worth noting what the alternative looks like: an **SMAJ18A** (`VWM` 18 V,
`VBR` 20.0–22.1 V, `VC` 29.2 V at 13.7 A) does not conduct on a 19 V brick at
all, still stands off 12 V + tolerance with more margin than the 15 V part,
and still clamps a surge at 29.2 V — below U5's 36 V operating maximum and
well below its 38 V absolute maximum. That is a one-line BOM change that
converts F-3 from "runs hot forever" to "runs". It does mean a 19 V brick is
silently accepted rather than flagged, which is a product decision, not an
electrical one.

### F-4 (medium) — 0014 says the core-rail gating was retired; the netlist still builds it

§4, S-3 and S-4. The decision record's consequences list retires the LTM4622
run-pin gating and its `WAKEUP_N` NMOS. `main_board.py:341-367` still
instantiates R7, R8 and Q1, and the code comment there still argues from the
one-unit-load rule that 0014 deleted. Consequence: `+1V0` never arrives on a
wall-powered board with no host, and on every power-up it briefly rises to
319 mV and collapses.

### F-5 (low) — I-3, the inrush peak against the fuse's `Imax`

§1. 27.9 A worst case against 20 A. One question to Littelfuse.

### F-6 (low) — three constants in `verify_power.py`

None of them change a verdict. All three are the kind of number this project
keeps getting bitten by.

| constant | file says | datasheet says |
| --- | --- | --- |
| `D2_VCLAMP` | "24.4 V at **21.7 A**", tagged `DS` | 24.4 V at **16.4 A** (Vishay, Bourns and Kemet all agree) |
| `U5_VIN_MAX` | 36.0 V, "LMR33630 **absolute maximum** VIN" | 36 V is the *recommended operating* maximum; the absolute maximum is **38 V** |
| `F1_HOLD` | "Polyfuse 1.1 A hold / **2.2 A trip**", tagged `DS` | see F-1 — no such part above 6 V |
| `D1_VF` | 0.35 V, tagged `DS`, "SS34 at a few hundred mA" | the only `VF` *specified* is 0.5 V max at 3 A; 0.35 V is a reading off the typical curve, which is a different kind of number |
| `F1_RMAX` | 0.30 Ω, tagged `ASSUMED` | `R1max` is **0.200 Ω** for the `/24`; the assumption was conservative and can now be replaced |

### F-7 (informational) — the SS34 footprint constrains the vendor

The netlist gives D1 `Diode_SMD:D_SMA` (DO-214AC). Vishay's SS34 is **SMC
(DO-214AB)** and will not fit it; ON Semiconductor's is SMA and will. Both
are real SS34s. The electrical constants above are Vishay's, and the SMA
parts from other vendors carry the same headline numbers, but the BOM should
name a vendor or the footprint should be widened. D2's footprint is correct —
Vishay's SMAJ series is SMA (DO-214AC).

---

## 6. Tampers, and the two holes they found

Every check was broken on purpose. Nine tampers, all nine behaved as
predicted.

| | tamper | target | result |
| --- | --- | --- | --- |
| T1 | a sustained 2.5 A through F1 | the F1 trip criterion | trips at **5.6 s** ✔ |
| T2 | a bench supply on the pads: 1 nH loop, 2 mΩ of wiring | I-2, D1's surge rating | peak becomes **121 A**, check fails ✔ |
| T3 | 100× the input bulk, 2200 µF | I-1, F1 surviving the inrush | **HOLE** |
| T4 | D1 soldered backwards | R-1, D1 blocking | becomes a **32 A short**, check fails ✔ |
| T5 | D2 bidirectional (SMAJ15CA) | R-2, U5's negative maximum | rail goes to **−12.1 V**, check fails ✔ |
| T6 | D2 not fitted at all | OV-3 / `verify_power.py`'s clamp check | **HOLE** |
| T7 | D2's `VBR` tempco set to zero | OV-4, D2's junction temperature | junction computes **2095 °C**, check fails ✔ |
| T8 | `C_SET` back to 4.7 µF | S-2, the FT601Q supply skew | skew becomes **357 ms**, check fails ✔ |
| T9 | the `WAKEUP_N` gating removed | S-3, `+1V0` arriving | `+1V0` arrives at **4.90 ms** ✔ |

### T4 found a hole in this file, and it was fixed

The first version of R-1 tested only the voltage across D1 against its 40 V
`VRRM`. **A diode fitted backwards makes that voltage smaller**, so R-1
passed the tamper cleanly. A check for "D1 blocks" that a conducting D1
passes is not a check. R-1 now tests two things: the standoff *and* that the
protected rail stays up. This is exactly the failure mode the passband-filter
tamper found earlier in this review — a measurement that cannot distinguish
the right answer from the wrong one.

The corrected tamper is also worth reading for its own sake. With D1
backwards **and** the adapter reversed, D2 forward and D1 backwards form a
complete loop from ground to the reversed supply: **32 A through F1**, which
trips it in about 31 ms and passes straight through the `/24` part's 20 A
`Imax` on the way. With D1 backwards and the adapter the right way round the
board simply does not power up. So a backwards D1 announces itself in both
directions — which is a good property of the topology and not one anyone
wrote down.

### T3 — the inrush check is true and not discriminating

Fitting 2200 µF instead of 22 µF still warms F1 by less than a degree. ½CV²
at 12 V is 158 mJ even at a hundred times the bulk, against 6.3 J to trip.
**I-1 cannot be made to fail by any plausible input capacitance**, which
means it is not really testing the design — it is testing an inequality that
12 V guarantees. T1 is what gives the trip criterion teeth: it shows the same
model *does* fire, at 5.6 s under a sustained 2.5 A. Read I-1 and T1
together, or read neither.

### T6 — the hole is in `verify_power.py`, not here

`verify_power.py` check 4 asks whether the TVS clamps below U5's maximum:

```
TVS clamps at 24.4 V against U5's 36 V maximum   ->   11.6 V of margin
```

Remove D2 from the netlist entirely and the fault still puts 18.7 V on U5,
and the check still passes — because 19 V was already below 36 V and 24.4 V
is a datasheet constant that does not know whether the part is fitted. **That
check compares two datasheet numbers to each other.** It cannot fail for any
19 V input, with or without a TVS, and it would go on passing if D2 were
deleted from the BOM. What it should be asking is what §3 asks: how much
current flows, for how long, and where the heat goes.

---

## 7. What this does not cover

* **No switching.** Every converter is a soft-start ramp with an output
  impedance. Switching ripple, loop stability, load-step response and EMI are
  all out of scope; nothing here would see a compensation error.
* **Surge, in the sense the TVS is actually for.** The 10/1000 µs and
  IEC 61000-4-5 cases are not simulated. §3 is the *sustained* overvoltage,
  which is a different question and the one 0014 raised.
* **The adapter is not chosen**, so its output impedance, its bulk, its own
  soft start and its inrush behaviour on the mains side are all guesses. The
  peak-current results move with them; the energy results do not.
* **D1's reverse leakage versus reverse voltage.** The datasheet gives `IR`
  at *rated* `VR` only. At 12 V — under a third of rated — a real part leaks
  much less. F-2's threshold (25 µA) is the number that matters and the
  curve is a figure, not a table.
* **Supply ground to chassis** is still undecided (0014's own open item) and
  nothing here touches it.
* **The 100 °C leakage case in §2 needs a 100 °C ambient**, since nothing is
  dissipating during a reverse-polarity fault. The 25 °C column is the
  operative one, and it already fails.

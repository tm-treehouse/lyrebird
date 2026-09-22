# Review: analog output module (lyrebird-dac-reva)

Reviewer: output-module agent. Date 2026-09-21/22.
Scope: `hardware/netlist/output_module.py`, `hardware/lyrebird-dac-reva/`,
`hardware/symbols/lyrebird.kicad_sym`, `hardware/footprints/lyrebird.pretty/`,
decisions 0007/0008/0012, `model/results/analog.txt`, `model/notes-analog.md`.

The netlist was regenerated before judging it:

```
export KICAD10_SYMBOL_DIR="/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
./.venv/bin/python hardware/netlist/output_module.py
```

It runs clean: 0 errors, 258 warnings all of which are SKiDL "missing tag"
noise from anonymous `Part(...)` calls in `_res`/`_cap`. The
`assert_below_abs_max` check at the end of `build()` passes. 126 parts,
144 electrically distinct nets, matching the count open-items.md quotes.

Two things are treated as known and are not reported as defects: the 12 V
wall-wart redesign (agreed, deliberately not implemented, deletes the
LTC3265) and the reference-rail transition-current risk.

## 1. The Crystek CCHD-957 footprint: open question settled, and a new defect

**Source checked:** the real datasheet, fetched from
`https://www.crystek.com/specification/clock/CCHD-957.pdf`, "CCHD-957 FEMTO
Clock Ultra-Low Phase Noise Oscillator with Standby Mode", **Rev N, dated
25-Aug-2026** — the same revision `parts-notes.md` and the footprint's own
`descr` cite. The drawings are vector, so rather than eyeball them I extracted
the path geometry and the text placement matrices from the PDF content stream.
Everything below is measured off those coordinates, not inferred from prose.

### 1.1 Which axis the long pad dimension lies along — ANSWERED, and the footprint is right

The SUGGESTED PAD LAYOUT figure carries four callouts: `0.280 (7.11)`,
`0.050 (1.27)`, `0.090 (2.28)`, `0.200 (5.08)`. In device coordinates the
figure's four pads occupy x ∈ [220.92, 265.92], y ∈ [115.92, 182.88] pt, and
the callout text sits at:

| callout | position (pt) | relative to figure | therefore |
| --- | --- | --- | --- |
| `0.280 (7.11)` | x=269.8, y=151.1 | right of it, mid-height | **vertical** dimension |
| `0.090 (2.28)` | x=202.1, y=176.2 | left of it | **vertical** dimension |
| `0.200 (5.08)` | x=235.9, y=106.1 | below it | **horizontal** dimension |
| `0.050 (1.27)` | x=240.2, y=195.4 | above it | **horizontal** dimension |

The drawn pads confirm it independently. Their centres are 36.00 pt apart in x
and 50.40 pt apart in y, and each pad is 9.00 pt in x by 16.56 pt in y.
Calibrating on 36.00 pt = 0.200 in gives 180 pt/in, and then 50.40 pt = 0.280 in
exactly and 9.00 pt = 0.050 in exactly.

**So the 0.090 in / 2.28 mm pad dimension lies along the same axis as the
0.280 in / 7.11 mm pad spacing, which is the package's 14.2 mm axis.**

`hardware/footprints/lyrebird.pretty/Oscillator_SMD_Crystek_CCHD-957_9x14mm.kicad_mod`
has pads `(size 2.28 1.27)` — 2.28 along X — at `(±3.556, ±2.54)`, with the
body drawn `-7.1 -4.57` to `7.1 4.57`. X is therefore the 14.2 mm axis, the
7.112 mm spacing is on X, and 2.28 is on X. **This is correct.** The 90-degree
error the open question feared is not present, and the datasheet's own outline
(`0.560 ±0.005 (14.2 ±0.127)` by `0.360 ±0.005 (9.14 ±0.127)`) matches the
drawn body exactly. This question can be closed.

### 1.2 DEFECT (blocking, part-killing): the pad *numbering* is rotated 90 degrees

The same extraction settles something the open question did not ask about.
The datasheet's Bottom View draws its four terminals at centres
(97.2, 115.0), (133.2, 115.0), (97.2, 167.5), (133.2, 167.5) pt — so **36.00 pt
= 0.200 in between the two columns and 52.56 pt ≈ 0.29 in between the two
rows**, i.e. the long axis is vertical in that figure, exactly as in the pad
layout figure. The pad-number glyphs land at:

```
'1' (94.56, 152.65)   '2' (130.56, 152.65)     <- upper row, y centre 167.5
'4' (94.56, 123.85)   '3' (130.56, 123.85)     <- lower row, y centre 115.0
```

(labels are placed inboard, symmetrically about the figure's mid-height, 12 pt
inside each pad centre.) Reading that off:

> **Pin 1 and pin 2 sit at the same end of the 14.2 mm axis, 0.200 in /
> 5.08 mm apart. Pin 1 and pin 4 are 0.280 in / 7.11 mm apart.**

The repo footprint has it the other way round:

```
(pad "1" ... (at -3.556  2.54) ...)   pad 1 <-> pad 2 : 7.112 mm apart   WRONG
(pad "2" ... (at  3.556  2.54) ...)   pad 1 <-> pad 4 : 5.08  mm apart   WRONG
(pad "3" ... (at  3.556 -2.54) ...)
(pad "4" ... (at -3.556 -2.54) ...)
```

The diagonals survive (1 opposite 3, 2 opposite 4, which is why this reads
plausible), and the pad shapes and positions are right, but the *numbers* are
rotated one quarter turn against the pads. Because the pad grid is 7.112 ×
5.08 mm and not square, the part physically fits only one way up to a 180 degree
flip, so this cannot be recovered by rotating the component in layout. Both
possible placements give:

| footprint pad (and its net) | reaches physical pin |
| --- | --- |
| 1 — `OSC_EN_*_3V3` | Vcc (or E/D after a 180 degree flip) |
| 2 — `GND` | E/D (or OUT) |
| 3 — `OSC_RAW` | GND (or Vcc) |
| 4 — `+3V3_CLK` | OUT (or GND) |

In every orientation the oscillator ends up with its supply or its ground on a
signal pin. Both oscillators are dead on the first board and probably damaged.

The fix is to renumber, not to redraw: pads 1 and 2 must share an x, e.g.
1 = (3.556, 2.54), 2 = (3.556, −2.54), 3 = (−3.556, −2.54), 4 = (−3.556, 2.54),
and the pin-1 silkscreen dot at `(-6.3, 3.8)` must move with pad 1. The
`descr` line "Pad 1 = E/D, 2 = GND, 3 = OUT, 4 = Vcc" stays true — that is the
function table, and it is correct; it is the *placement* of those numbers that
is wrong.

The symbol `CCHD-957` in `hardware/symbols/lyrebird.kicad_sym` is correct:
1 = E/D (input), 2 = GND (power_in), 3 = OUT (output), 4 = Vcc (power_in),
matching the datasheet's Pad Connection table verbatim.

## 2. Does the board match what the model assumes?

`model/results/analog.txt` computes every noise and distortion figure from a
specific set of values. Each is checked against the regenerated netlist below.
Component values were read out of the built circuit, not out of the comments.

### 2.1 Values that agree

| Quantity | analog.txt assumes | netlist carries | verdict |
| --- | --- | --- | --- |
| Reference rail | `V_REF = 3.3` (analog.py) | LT3045 U5, 33.2 k → 3.32 V | agrees to 0.6 %; and the rail current is unchanged, because 14×3.3/3320 and 14×3.32/3340 are both 13.916 mA |
| Elements per node / per channel | 7 / 14 | 7 / 14, four nodes | agrees (§5) |
| Transimpedance `R_f` | 406.5 → "402 Ω E96" | 402 Ω, one `R_Pack04` (RN15) | agrees |
| Element pole | 1 MHz, even split, 192 pF | 1.69 k + 1.65 k, 180 pF C0G, R1‖R2 = 834.9 Ω → **1.059 MHz** | agrees; 180 pF is E-series and 1.06 MHz sits on the same row of Q2c |
| Which half is shunted | `split_element` returns R1 = driver side | `ELEM_R1` = 1.69 k on the register side | agrees with `ElementSource`'s `z = r2 + (r1 ‖ 1/jwC)` |
| Feedback pole | 1.96 nF across 407 Ω = 200 kHz | 2.0 nF C0G across 402 Ω = **198 kHz** | agrees |
| Third pole | 3979 pF across 200 Ω = 200 kHz | 1.3 nF C0G across 604 Ω = **203 kHz** | corner agrees (the 604 Ω itself is the known divergence) |
| No shunt at the summing node | Q2b: "a shunt capacitor at the summing node is not the first filter pole… the netlist's 1 nF is not a filter" | no capacitor from `SUM_*` to ground; the 2.0 nF runs node→output, i.e. feedback | **the model's complaint has been acted on correctly** |
| Rail source impedance | 10 mΩ = regulator + 8 × 100 nF | exactly 8 × 100 nF on `+3V3_REF` | agrees |
| Gain-bandwidth | 40 MHz (`Amp.gbw`) | OPA1612, **40 MHz at G = +1** (SBOS450C §6.4) | agrees |
| Full-scale output | 2.0 V RMS (`LINE_RMS`) | 6.916 mA × 402 Ω = 2.780 V peak = **1.966 V RMS** | agrees to 0.15 dB |
| Stray at the node | `c_node = 15 pF` | nothing deliberate; array + 0603 + op amp input | plausible, unverifiable until layout |
| Capacitor dielectric | Q2e: C0G required, X7R's voltage coefficient is in-element nonlinearity | all three filter capacitors specified C0G | agrees |

### 2.2 Element resistance — the netlist is right, the model's headline is stale

analog.txt recommends **3.32 kΩ**; the netlist fits **1.69 k + 1.65 k =
3.34 kΩ**. **The netlist is right.** The binding constraint in Q1b is
`Minimum R for 28 elements high : 3312 ohm`, and an even 1.65 k + 1.65 k =
3.30 kΩ fails it. 3.34 kΩ clears it and is the closest near-even E96 split
that does. The constant-current property is untouched, since the DC current is
`V_ref/(R1+R2)` either way. This divergence is deliberate, documented in the
netlist and in parts-notes.md, and correct.

What is *not* right is the arithmetic Q1a and Q1b use to get there. Q1a states
its assumption explicitly:

> `'module' and 'board' follow power.md's other lines unchanged: 8.1 mA of
> registers, 2 mA of LT3045 ground pin, 40 mA of clock chain, 51 mA of op amp
> stage and charge pump, and 234 mA of main board.`

`hardware/lyrebird-dac-reva/power.md` now carries **34.3 mA of registers**
(datasheet Cpd, not 8.1), **35.5 mA of clock chain** (not 40), and **139 mA
for the op amp stage and charge pump** (not 51) — the last because the stage
turned out to need six amplifiers and a doubling charge pump. So the `module`
and `board` columns of Q1a are wrong by more than 120 mA: Q1a's 3320 Ω row
says module 115 mA / board 349 mA, and power.md's own total for the same board
is **238 mA module / 472 mA total**.

**The recommendation survives the correction and the margin improves.**
Reconstructing Q1b's threshold: 3312 Ω is 28 × 3.3 V / 27.9 mA, and 27.9 mA is
150 − 72 (bridge) − 40 (clock) − 8.1 (registers) − 2 (LT3045 ground). With
power.md's current clock figure of 35.5 mA and with the registers drawing only
their 40 µA static ICC before a clock exists, the pre-enumeration allowance is
about 40 mA rather than 27.9, and the minimum element falls to roughly 2.3 kΩ.
3.34 kΩ is inside either number, so nothing has to move — but **the 3312 Ω that
picked the value is not a live number**, and anyone who reruns `run_analog.py`
will get the stale one back, because `run_analog.py` hard-codes the old
power.md lines.

### 2.3 DIVERGENCE: the output stage is not the topology the model costed

This is the largest mismatch and it is not recorded as one anywhere in
`model/`.

`analog.py`'s `noise_budget` docstring states the circuit it is pricing:

> `n_stages` is how many amplifiers the differential-to-single-ended path
> uses. Two is the arrangement that keeps both summing nodes at a true virtual
> ground with the four amplifiers power.md budgets for stereo: a transimpedance
> amplifier on the negative node, then a second amplifier that is
> simultaneously the transimpedance for the positive node and the inverting
> summer for the first one's output.

and it prices exactly that: `n_fb = 3` resistors, noise gains `ng1 = 1.857` and
`ng2 = 1 + R_f/(R_elem/7 ‖ R_f) = 2.858`, four amplifiers for stereo.

The netlist builds something else: **two independent transimpedance amplifiers
per channel (U7, U10) plus a four-resistor difference amplifier per channel
(U11), six amplifiers in three packages.** That is a different noise sum, a
different resistor count and a different amplifier count:

| | model's topology | netlist's topology |
| --- | --- | --- |
| amplifiers, stereo | 4 | **6** |
| gain-setting resistors per channel | 3 × 406.5 Ω | 2 × 402 Ω **+ 4 × 604 Ω** |
| amplifier noise gains summed | √(1.857² + 2.858²) = 3.41 | √(1.843² + 1.843² + 2²) = 3.29 |

Working the netlist's own sum at 300 K over a 19.98 kHz band, with the
OPA1612's typical 1.1 nV/√Hz and 1.7 pA/√Hz:

```
element resistors (14)    402 * sqrt(14*4kT/3340)      = 3.35 nV/rtHz
transimpedance (2 x 402)  sqrt(2*4kT*402)              = 3.65
difference net (4 x 604)  sqrt(4*4kT*604)              = 6.33   <- the largest term
amplifiers (3 per ch)     3.29 * 1.1n                  = 3.62
amplifier current noise                                 ~1.1
                                            total       = 8.88 nV/rtHz
1.966 V RMS / (8.88n * sqrt(19980))  ->  stage SNR      = 123.9 dB
```

against **analog.txt's 126.3 dB** for the same amplifier at 3.32 kΩ. The gap
is 2.4 dB and it is almost entirely the 604 Ω difference network, which is the
single loudest thing in the stage. parts-notes.md independently reaches
**123.5 dB** by the same route and states the disagreement openly ("the two
numbers in this file disagree by design and this is which is which"), so the
board's designer knows. **The model does not.** `run_analog.py` still prints
125.8 dB / 126.3 dB and `notes-analog.md` still says "System noise at 3.32 kohm
is 125.2 dB". Those figures describe a circuit that is not on this board.

**Verdict on which is right: the netlist.** The model's two-amplifier
arrangement asks one amplifier to be simultaneously a transimpedance stage for
the positive node and an inverting summer for the negative one's output; its
summing node then sees `R_elem/7 ‖ R_f` and its noise gain rises to 2.86, and
its two inputs no longer see matched impedances, which is exactly the symmetry
0008's even-order cancellation depends on. The netlist's arrangement is the
conventional one and costs 2 mA per channel more. But the model's *numbers*
should be regenerated against it, because three published figures — stage SNR,
system SNR, and "the output stage is the noise floor of this design" — are
quoted throughout the repo from a topology that was not built.

### 2.4 Smaller model-vs-board divergences

- **Amplifier current noise.** Model assumes `i_n = 1.5 pA/√Hz`; the OPA1612
  is **1.7 pA/√Hz at 1 kHz** (SBOS450C §6.4). Immaterial — 0.2 % of noise
  power — but the model's value is not the part's.
- **Amplifier voltage noise is a typical, not a guarantee.** SBOS450C gives
  `en` at 1 kHz as **1.1 nV/√Hz typ, 1.5 nV/√Hz max**. Every stage-SNR figure
  in the repo uses the typical. At the 1.5 nV max the netlist's stage falls to
  about 122.9 dB. parts-notes.md records the max in its table but does not
  carry it into any conclusion.
- **The difference amplifier's own intermodulation is not modelled.** Q2c's
  `Amp` is a transimpedance stage with `z_src` = seven split elements, which is
  exactly the netlist's TIA, so Q2c applies to U7/U10. U11 sees −54.5 dBFS of
  residual (Q2d) into a bipolar input pair that the model never runs. The level
  is 25 dB below what Q2c analyses, so this is almost certainly fine, but it is
  outside what was measured.
- **The model has no output network.** The netlist adds a 100 Ω build-out and
  100 pF to ground per channel (16 MHz), which is below every corner the model
  cares about and changes nothing, and a 0.09 dB insertion loss into 10 kΩ that
  no level figure accounts for.

## 3. Symbols and footprints, checked pin by pin against each datasheet

Every custom symbol's pin numbering was compared with the terminal assignment
in the part's own datasheet. Four of the five custom symbols are correct. The
error is not in a hand-drawn symbol at all — it is in a footprint assignment to
a *stock* symbol.

### 3.1 Custom symbols — all correct

| Symbol | Datasheet checked | Result |
| --- | --- | --- |
| `SN74ALVCH16374` | **SCES021L**, Jul 1995 rev Sep 2004, DGG/DGV/DL top view | **correct.** 1 = 1OE, 48 = 1CLK, 47…37 = 1D1…1D8 with GND at 45/39 and VCC at 42, 36…26 = 2D1…2D8, 25 = 2CLK, 24 = 2OE, 2…12 = 1Q1…1Q8, 13…23 = 2Q1…2Q8, VCC 7/18/31/42, GND 4/10/15/21/28/34/39/45. All 48 match. |
| `SN74LVC1G74` | **SCES794G**, rev Sep 2021, Figure 5-1 DCU top view | **correct.** 1 CLK, 2 D, 3 Q̄, 4 GND, 5 Q, 6 CLR̄, 7 PRE̅, 8 VCC. DCU is the 2.30 × 2.00 mm US8/VSSOP body, so `Package_SO:VSSOP-8_2.3x2mm_P0.5mm` is right. |
| `LMK1C1104` | **SNAS791D**, rev Feb 2022, Figure 6-4 PW top view + Table 6-1 | **correct.** 1 CLKIN, 2 1G, 3 Y0, 4 GND, 5 Y2, 6 VDD, 7 Y3, 8 Y1. Table 6-1 also confirms the netlist's two claims: 1G has "internal 300-kΩ (typical) pulldown resistor to GND. Typically connected to VDD with external pullup resistor", and "Unused outputs can be left floating". |
| `LTC3265` | **3265fa** PIN FUNCTIONS (DFN/TSSOP), read from the ADI PDF | **correct.** 1 CBST−, 2 CBST+, 3 VIN_P, 4 EN−, 5 BYP−, 6 ADJ−, 7 LDO−, 8 VOUT−, 9 CINV−, 10 CINV+, 11 VIN_N, 12 RT, 13 EN+, 14 MODE, 15 BYP+, 16 ADJ+, 17 LDO+, 18 VOUT+, EP 19 GND. All 19 match. |
| `CCHD-957` | **Crystek rev N**, 25-Aug-2026, Pad Connection table | **correct.** 1 E/D, 2 GND, 3 OUT, 4 Vcc. (Its *footprint* is not — see §1.2.) |

### 3.2 Stock symbols used by the module

| Symbol | Result |
| --- | --- |
| `Regulator_Linear:LT3094xDD` | **correct.** LT3094 Rev. B PIN FUNCTIONS: "IN (Pins 1, 2, Exposed Pad Pin 13)", EN/UV 3, PG 4, PGFB 5, ILIM 6, VIOC 7, SET 8, GND 9, OUTS 10, OUT 11/12. Symbol and netlist match, including tying the exposed pad to IN. |
| `Logic_LevelTranslator:SN74AVC4T245PW` | **correct.** SCES576I, Figure 4-1 / Table 4-1: VCCA 1, 1DIR 2, 2DIR 3, 1A1 4, 1A2 5, 2A1 6, 2A2 7, GND 8/9, 2B2 10, 2B1 11, 1B2 12, 1B1 13, 2OE 14, 1OE 15, VCCB 16. Function table confirms the netlist comment: OE = L with DIR = L is "B data to A bus", DIR = H is "A data to B bus". VCCA and VCCB both accept 1.2 V–3.6 V. |
| `Amplifier_Operational:OPA1612AxD` | **correct.** SBOS450C Pin Functions, D (OPA1612): OUT A 1, −IN A 2, +IN A 3, V− 4, +IN B 5, −IN B 6, OUT B 7, V+ 8 — which is exactly the netlist's `UNIT = ((1,2,3),(7,6,5))` with V+ on 8 and V− on 4. |
| `Device:R_Pack04` | four isolated elements, pins paired k+1 with 8−k. The netlist's indexing matches, and the choice over `R_Network08` (a bussed array) is correct: a bussed part would short every element of a package together. |
| `Connector_Audio:AudioJack3` | three pads T/R/S, which is what a switchless SJ1-3523N has. |

### 3.3 DEFECT (blocking): all four LT3045s carry a 12-lead footprint for a 10-lead part

The netlist gives U5, U6, U9 and U14 the footprint

```
Package_DFN_QFN:DFN-12-1EP_3x3mm_P0.45mm_EP1.65x2.38mm
```

**The LT3045's DD package is a 10-lead DFN on 0.5 mm pitch, not a 12-lead on
0.45 mm.** From the LT3045 datasheet (Rev. C, read from the PDF):

> `LT3045 is available in thermally enhanced 12-Lead MSOP and 10-Lead 3mm ×
> 3mm DFN packages.`
>
> `DD PACKAGE / 10-LEAD (3mm × 3mm) PLASTIC DFN / … EXPOSED PAD (PIN 11) IS
> GND, MUST BE SOLDERED TO PCB`

and the ORDER INFORMATION table lists `LT3045EDD#TRPBF … 10-Lead (3mm × 3mm)
Plastic DFN`. The 12-lead variant is the **MSE** (MSOP) package, which is a
different body entirely.

Three independent confirmations that the assignment is wrong:

1. KiCad's own `LT3045xDD` symbol carries
   `Footprint = Package_DFN_QFN:DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm` and
   `Description = "…Linear Regulator, DFN-10"`. Its `ki_fp_filters` is
   `DFN*1EP*3x3mm*P0.5mm*` — which **excludes** the P0.45mm footprint the
   netlist assigns.
2. The symbol has only 11 pins (1 IN, 2 IN, 3 EN/UV, 4 PG, 5 ILIM, 6 PGFB,
   7 SET, 8 GND, 9 OUTS, 10 OUT, 11 GND = the exposed pad), against a
   footprint with 13 pads. Pads 11, 12 and the exposed pad land on no net.
3. Contrast the LT3094 at U8, which really *is* a 12-lead DFN and whose
   KiCad symbol's own default footprint is
   `DFN-12-1EP_3x3mm_P0.45mm_EP1.65x2.38mm_ThermalVias` — the netlist's
   footprint string for U8 is right for the same reason it is wrong for the
   LT3045s. The two parts were given the same footprint because they are
   pin-mirrors in function, but they are not the same package.

The consequence is not cosmetic: a 10-lead 0.5 mm part cannot be placed on a
12-lead 0.45 mm land pattern, and the exposed pad, which the datasheet says
"MUST BE SOLDERED TO PCB", has no net. `bom.csv` records the same wrong package
("DFN-12-1EP 3x3mm P0.45mm") for U5, U6 and U8, so the error would survive into
purchasing. The fix is one string:
`Package_DFN_QFN:DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm` (it exists in the stock
library), for U5, U6, U9 and U14 only.

### 3.4 The regulator housekeeping is right, but one quoted reason is false

`lp.lt3045_housekeeping` was checked against the LT3045 PIN FUNCTIONS section
and every quotation in it is verbatim and correctly applied: `SET` sources a
precision 100 µA so `VOUT = ISET · RSET` (33.2 k → 3.32 V, 24.9 k → 2.49 V,
49.9 k → 4.99 V, all right); "If unused, tie EN/UV to IN. Do not float the EN/UV
pin."; "If the programmable current limit functionality is not needed, tie ILIM
to GND."; "Tie PGFB to IN if power good and fast start-up functionalities are
not needed"; "If the power good functionality is not needed, float the PG pin."
The 4.7 µF SET bypass and the 10 µF output capacitor are both what the
datasheet asks for (output ESR < 20 mΩ, which a ceramic meets).

The LT3094 at U8 is equally correct in what it does — `SET` 49.9 k for −4.99 V
with the 100 µA sink, `EN/UV` and `PGFB` to IN, `VIOC` floated, `PG` floated,
`ILIM` programmed with 24.9 k, and the scale factor **is** "nominally
3.75 A • kΩ" so that is about 150 mA.

**But the stated reason for programming ILIM rather than grounding it is wrong.**
The netlist says "the LT3094's pin description gives no instruction for an
unused ILIM", and parts-notes.md says "the LT3094's pin description gives no
such sentence". It does. The LT3094 Rev. B PIN FUNCTIONS entry for ILIM ends
with **"If not used, tie ILIM to GND."** — the same instruction as the LT3045's.
Programming 150 mA is still a defensible choice and the value is fine; only the
justification is false, and it is stated in two places as a datasheet fact.

There is a second, more dangerous staleness in the same sentence: it says
150 mA is "well above the **22 mA** this rail carries". Eleven lines earlier the
same comment block says the negative rail carries "42 to 45 mA … and reaches
56 mA with maximum quiescent current over temperature", and power.md agrees at
42.5–44.8 mA. parts-notes.md repeats the 22 mA. 150 mA still clears 56 mA, so
nothing is broken — but if anyone ever re-picks ILIM against "22 mA" they will
choose a limit that clips the rail.

### 3.5 LTC3265 configuration — every claim verified

Checked against 3265fa PIN FUNCTIONS and the electrical table:

- `VIN_N` to `VOUT+`: the netlist quotes the datasheet verbatim and correctly.
  Confirmed: "If VIN_N is tied to VOUT+, the output at VOUT– will be –VOUT+ or
  –2 • VIN_P. This configuration is suitable for symmetric outputs at LDO+ and
  LDO– pins."
- `MODE` low: **correct.** "A logic 'low' on the MODE pin forces the charge
  pumps to operate in open-loop mode with a constant switching frequency."
- `RT` to ground: **correct**, and this one was worth checking because RT
  servos to 1.2 V and a direct short looks wrong. The datasheet settles it:
  "If the RT pin is tied to GND, the switching frequency defaults to a fixed
  500kHz."
- `EN+` / `EN−` thresholds: **correct.** `VEN+(H)` rising 1.1 min / 2 V max,
  `VEN+(L)` falling 0.4 min / 1.0 V max, and `IEN+` internal pull-down 0.7 µA.
  So 2.5 V header logic clears the rising threshold and the pin can never push
  the mezzanine net above its own level. "Do not float this pin" — the 100 k
  pull-down on `MUTE_N` satisfies that.
- `BYP+` / `BYP−`: "Connect a capacitor from BYP to GND to reduce LDO output
  noise. Leave floating if unused." 100 nF fitted on each — correct.
- Charge-pump output impedance **32 Ω** at MODE = 0, RT = GND: confirmed
  (`ROUTINV … MODE = 0V, RT = GND … 32 Ω`), which is the number parts-notes.md
  builds its 4.43 V headroom table on.
- LDO+ / LDO− rated 50 mA: confirmed ("Low Noise Positive LDO Post Regulator Up
  to 50mA").

One internal inconsistency, harmless in itself. The netlist explains the
`ADJ−` divider as giving "0.69 V of headroom for the LT3045 **and LT3094** over
their ±5 V outputs", and works the value against LDO− dropping out. But the
LT3094 is fed from `VOUT−`, not `LDO−`, and `LDO−` drives nothing at all — the
`-5V7_A` net has exactly three connections: `U13.7 (LDO−)`, `R9` and `C57`,
i.e. the pin, its own feedback divider and its own capacitor. parts-notes.md
states this deliberately ("LDO− stays enabled with its capacitor and divider,
unused"), so the *circuit* is intended; it is the netlist comment that explains
`ADJ−`'s value by an argument that no longer applies to anything.

## 4. Unconnected pins, enumerated

Taken from the regenerated circuit, not from a document. Twelve pins on the
module are open, plus four single-pin nets.

| Part | Pin | Name | Verdict |
| --- | --- | --- | --- |
| U5, U6, U9, U14 (LT3045) | 4 | `PG` | **deliberate and correct.** "If the power good functionality is not needed, float the PG pin." Open-collector, nothing reads it. |
| U8 (LT3094) | 4 | `PG` | **deliberate and correct**, same sentence in the LT3094 datasheet. |
| U8 (LT3094) | 7 | `VIOC` | **deliberate and correct.** "If unused, float the VIOC pin." |
| U12 (LMK1C1104) | 7 | `Y3` | **deliberate and correct.** Table 6-1: "Unused outputs can be left floating." Three of four outputs are used (U3, U4, translator). |
| U2 (74AVC4T245) | 5 | `1A2` | **deliberate and correct.** Bank 1 runs B→A, so 1A2 is an *output* of the spare channel and an open output is fine. Its input side, 1B2, is tied to GND rather than floated, which is what SCES576I requires: "All unused data inputs of the device must be held at VCCI or GND for proper device operation." |
| U3, U4 | 12, 23 | `1Q8`, `2Q8` | **deliberate and correct.** 14 elements in a 16-bit package. Their data inputs (1D8/2D8, pins 37/26) are tied to GND, so the outputs have a defined state and simply drive nothing. |
| J1 | 57, 59, 61, 63 | `ELEM28…ELEM31` | **deliberate and correct.** 32 lines provisioned, 28 used (0008/0012). interface.md says `ELEM[31:28]` are "Reserved. Driven low by the main board", so the module is right to leave them at the header. Whether the main board actually drives them low is an HDL question — flagged below. |

Two things that are *not* in this list but should be treated as the same class
of problem, because an input held by nothing is worse than an output driving
nothing:

### 4.1 DEFECT: `OSC_EN_48` and `OSC_EN_441` float before the FPGA is configured

`MUTE_N` gets a 100 kΩ pull-down on the module, for a reason the netlist states
plainly: "so the net is defined rather than held by 0.7 uA while the FPGA is
unconfigured and its pin is high impedance." **The identical argument applies to
the two oscillator enables and was not applied to them.** Neither board fits a
resistor: the module has none, and `main_board.py` pulls down `ID0` and `ID1`
only.

Those two nets land on `U2.6 (2A1)` and `U2.7 (2A2)` — A-port *inputs* of the
translator, bank 2 running A→B. The SN74AVC4T245 has no bus hold, and SCES576I
says "All unused data inputs of the device must be held at VCCI or GND for
proper device operation." Three consequences, in increasing severity:

1. Crossover current in the translator's input stage on two floating pins, on a
   rail whose pre-enumeration budget is what Q1b's element-resistor minimum is
   computed from.
2. **If both enables resolve high, both oscillators run and drive `OSC_RAW`
   simultaneously.** Two CCHD-957s at 49.152 and 45.1584 MHz, each specified at
   "Output Current: ±24mA Max", in push-pull contention. interface.md's rule
   "Exactly one oscillator runs at a time" is a software convention with no
   hardware interlock behind it, and the one net both outputs share
   (`OSC_RAW`, 3 pins: `Y1.3`, `Y2.3`, `U1.1`) is only legal while that
   convention holds.
3. **If both resolve low, `OSC_RAW` is high-impedance** — the datasheet is
   explicit that disable tri-states the output buffer — and it drives
   `U1.1 (CLK)` on an SN74LVC1G74, which has no input pull-down and no
   fail-safe input. A floating CMOS clock input sits near the trip point and
   burns supply current unpredictably. (U12's `CLKIN` does have a 300 kΩ
   pull-down and a documented fail-safe input, so the buffer is protected and
   the flip-flop is not.)

The fix is two resistors: 100 kΩ from each of `OSC_EN_48_3V3`/`OSC_EN_441_3V3`
to ground on the module's 3.3 V side, or from the header nets to ground in the
style of `MUTE_N`. A pull-down on the module's B side is the better of the two
because it also defines the state if the translator is unpowered.

### 4.2 DEFECT: the register's bus hold can put 3.3 V on a 2.5 V GateMate pin

This one is *already known and argued through* in parts-notes.md, so it is
flagged here only to say the argument was checked and to record where it is
thin — not to re-raise it.

SCES021L confirms the mechanism: "Active bus-hold circuitry holds unused or
undriven inputs at a valid logic state", the hold current is 75 µA at
VI = 2 V with VCC = 3 V, and footnote 2 defines the ±500 µA figure as "the
bus-hold maximum dynamic current … the minimum overdrive current required to
switch the input from one state to another". So while the FPGA is
unconfigured, each of the 28 element lines is actively pulled toward
`+3V3_REF` by its register input, and those lines run untranslated to GateMate
balls whose VDDIO may not exceed 2.7 V.

parts-notes.md settles it against Cologne Chip **UG1003**, and I confirmed the
two sentences it relies on are in that document: "GateMate's GPIO supply
voltage VDDIO is not allowed to exceed 2.7 V… Any voltage above VDDIO supply
voltage should be avoided on the GateMate pins", and, for a 3.3 V source, that
a 10 kΩ–100 kΩ series resistor suffices because "the input overvoltage
security circuitry of the GateMate input pin will limit the input voltage". The
argument — 75 µA is inside the ~80 µA a vendor-sanctioned 10 kΩ would deliver —
holds.

What is worth recording is that `lp.assert_below_abs_max` cannot see this, and
its own comment states the assumption that makes it blind:

> An input cannot [drive a net]: the 28 element lines legitimately land on
> 3.3 V register inputs, and that is a threshold question, not a damage one.

With an ALVC**H** part it is both. The check is silent on the one class of
overvoltage the module actually has, and 28 lines × 75 µA = 2.1 mA is being
injected into the GateMate's clamp structure for the whole pre-configuration
interval. The residual unknown parts-notes.md names — whether GateMate GPIO are
high-impedance before configuration — I could not resolve either: the GateMate
datasheet (DS1001) has no statement about the I/O state during configuration
that I could find.

## 5. 0008's differential / constant-current property: the topology delivers it

This is checked from the built circuit, by reading every pin on every summing
node out of the regenerated netlist.

### 5.1 Four summing nodes, seven elements each, left and right genuinely separate

0008 asks for "Seven unit elements per side, each driving a matched resistor
into a summing node", and "for code k, drive k elements on the positive side and
seven minus k on the negative side", so "exactly seven elements high at every
code". The netlist builds exactly that, per channel:

```
SUM_LP  7 element resistors  (RN8 x4, RN9 x3)   + U7.2  (-in)  + RN15.1 + C37
SUM_LN  7 element resistors  (RN9 x1, RN10 x4, RN11 x2) + U7.6  + RN15.2 + C38
SUM_RP  7 element resistors  (RN11 x2, RN12 x4, RN13 x1) + U10.2 + RN15.3 + C41
SUM_RN  7 element resistors  (RN13 x3, RN14 x4) + U10.6 (-in)  + RN15.4 + C42
```

Four nodes, seven elements each, 28 in total. **Left and right are separate all
the way to the jack** — `SUM_L*` reach only U7 and `SUM_R*` only U10, the two
difference amplifiers are separate units of U11 with separate 604 Ω arrays
(RN16 for L, RN17 for R), and `DIFF_OUT_L` and `DIFF_OUT_R` reach `J2.T` and
`J2.R` through their own build-out resistors. The mono-mixer failure mode the
netlist comment records ("an earlier revision summed both channels into one
differential pair") is gone, and no net carries pins from both channels except
GND and the supplies.

The element-to-node mapping matches interface.md exactly:

| interface.md | netlist nets | register pins |
| --- | --- | --- |
| `ELEM[6:0]` left positive | → `SUM_LP` | U3 bank 1, `1D1…1D7` (pins 47,46,44,43,41,40,38) |
| `ELEM[13:7]` left negative | → `SUM_LN` | U3 bank 2, `2D1…2D7` (36,35,33,32,30,29,27) |
| `ELEM[20:14]` right positive | → `SUM_RP` | U4 bank 1, `1D1…1D7` |
| `ELEM[27:21]` right negative | → `SUM_RN` | U4 bank 2, `2D1…2D7` |

and 0008's "one 16-bit package per channel so both polarities share a die" is
honoured: U3 carries all fourteen of the left channel, U4 all fourteen of the
right, and both banks of each package are clocked from a single net
(`ELEM_CLK_L` reaches `U3.48 (1CLK)` and `U3.25 (2CLK)`; `ELEM_CLK_R` likewise
on U4), off one LMK1C1104 output each, which is the skew argument 0012 makes.

### 5.2 The constant-current property survives the split element

The element is two resistors around a shunt capacitor. That is the one thing
that could have broken the property, and it does not: both ends of the split
sit at an AC ground — a flip-flop output on the reference rail one side, a
virtual ground the other — so the DC current is `V_ref/(R1+R2)` at every code,
independent of the capacitor. 14 × 3.32 V / 3.34 kΩ = 13.92 mA, constant. The
netlist, power.md and analog.txt all agree on that number.

A second property falls out of the same arithmetic and is worth recording
because nothing in the repo states it: **the common-mode voltage at the
difference amplifier's inputs is constant at every code, not just at mid code.**
`IV_P + IV_N = −R_f · (k + (7−k)) · V_ref/R_elem = −2.780 V` exactly, for every
k. So the 604 Ω network's common-mode rejection only ever has to reject a DC
offset — it never sees a signal-dependent common mode, and therefore contributes
no distortion, only a fixed output offset. parts-notes.md's justification for
omitting an output coupling capacitor ("the differential arrangement puts both
transimpedance outputs at the same DC") is loosely worded — the two outputs are
at the same DC only at mid code — but the conclusion is right, and for a
stronger reason than the one given.

That said, the offset estimate in parts-notes.md counts only one of the two
mechanisms. It computes 1.4 mV from a 0.1 % mismatch between the two 402 Ω
transimpedance resistors (correct: 3.48 mA × 402 Ω × 0.001 = 1.4 mV), but the
604 Ω difference network's own ratio mismatch acting on the −1.39 V common mode
contributes separately, and at 0.1 % ratio matching that is of the same order
again. Both are arrays, so real matching will be better than 0.1 %; the
conclusion (no coupling capacitor) stands, but the figure is optimistic by
roughly a factor of two.

### 5.3 What the netlist cannot deliver, and correctly does not claim to

0008's own correction — that the constant-current property "covers the DC term
only", and the transition current carries the signal — is the documented lead
open item and is out of scope here. Two observations that bear on it and are
*new*:

- The netlist puts the **larger** half of the split (1.69 k) on the register
  side and the smaller (1.65 k) on the summing-node side. That is the right way
  round for the transition-current problem, because the 180 pF charge and
  discharge current flows through the register-side resistor. It is a 1 %
  effect, not a fix, and the netlist does not claim otherwise.
- The eight 100 nF parts on `+3V3_REF` are all present and all at the register
  packages, which is where power.md says the current comes from. open-items.md
  is right that they are not the mitigation.

## 6. Other findings

### 6.1 DEFECT (documentation, but it would be bought from): `bom.csv` describes a netlist that no longer exists

`hardware/lyrebird-dac-reva/bom.csv` is the only file in the module directory
that was not updated when the parts were selected. It still describes the
pre-selection netlist, and every one of these lines is false of the circuit
that regenerates today:

| bom.csv says | The netlist actually has |
| --- | --- |
| U1 "Never chosen… 74AUP1G74 stand-in… Its D input is unconnected, so it does not divide" | SN74LVC1G74DCUR wired as a toggle, `~Q`→`D` |
| U3a/U3b/U4a/U4b "two 74HCT574 octals per channel… the Cp clock inputs of all four packages are unconnected, so no flip-flop is clocked" | two SN74ALVCH16374DGGR, one per channel, both banks clocked |
| U7 "Never chosen… OPA1612AxD stand-in with only V+ and V− wired; both inputs and the outputs are open" | three OPA1612AID, six amplifiers, fully wired |
| Y1/Y2 "Abracon ASE stand-in… wrong footprint"; "both EN pins are driven straight from the 2.5 V header" | CCHD-957 with a drawn 9×14 mm footprint, enables through the translator |
| RN1–RN4 "1k thin film… placeholder… R_Network08 … shorts each package's elements together" | RN1–RN14, 1.69 k + 1.65 k, `R_Pack04` isolated elements |
| C1–C2 "1nF C0G summing node shunt" | no shunt at the summing node at all — the model rejected it (Q2b) |
| U5/U6 "EN/UV unconnected, so the rail is not gated at power-on" | `EN/UV` tied to IN via `lt3045_housekeeping` |
| U8 "Its IN pins are unconnected and no charge pump exists to feed them" | IN on `PUMP_N` from the LTC3265 |
| R1 "ID0 has no resistor: it is tied directly to the 3.3 V element reference rail" | 1 k to `+2V5`; the 3.3 V short was fixed and the build now asserts against it |
| "Charge pump — never chosen and absent from the netlist" | LTC3265EDHC#TRPBF at U13 |
| "Positive rail post-regulator — never chosen and absent" | LT3045 at U14 |
| "2.5 V regulator — never chosen and absent" | LT3045 at U9 |
| "Analog output connector — never chosen. LINE_OUT… attached to nothing" | SJ1-3523N at J2 |

It also omits every part that was actually chosen (no OPA1612, no LTC3265, no
SN74ALVCH16374, no element resistor values, no jack), and it records the wrong
LT3045 package (§3.3). `missing.md` is right that the netlist is the authority,
but a file called `bom.csv` is not read as a historical note. Either regenerate
it from `lyrebird-dac.xml` or delete it; leaving it is worse than either.

### 6.2 DEFECT: the audit command `missing.md` tells you to run does not work

`missing.md` documents the one procedure it says should replace trusting a
written list:

```sh
./.venv/bin/python - <<'PY'
...
for part in b.build():
PY
```

`build()` in `hardware/netlist/output_module.py` has no `return`, so this fails
with `TypeError: 'NoneType' object is not iterable`. I ran it. The fix is one
line — return `builtins.default_circuit.parts` from `build()`, or iterate the
default circuit in the snippet.

### 6.3 The three amplifiers all run below the load their specifications are given at

Working the loads out of the netlist, per channel:

```
TIA on the positive node (U7.1 / U10.1):  402 || 604       = 241 ohm
TIA on the negative node (U7.7 / U10.7):  402 || (604+604) = 301 ohm
difference amplifier      (U11.1/U11.7):  604 || 10.1k     = 570 ohm
```

SBOS450C specifies `VOUT` and `AOL` at `RL = 10 kΩ` and `RL = 2 kΩ`, and its
lowest published THD+N curve is at `RL = 600 Ω`. All three stages sit below
that, and two of them well below. Nothing here breaks: peak output current is
about 11.5 mA against a ±30 mA rating and `ISC` of +55/−62 mA, and the swing
needed (−2.78 V on a −5 V rail) is nowhere near the `(V−) + 0.6 V` limit even
at 2 kΩ. But the distortion of this stage at 241 Ω is outside what the
datasheet characterises, and the whole design rests on that distortion being
negligible.

**The asymmetry is the part worth acting on.** The two transimpedance
amplifiers of a channel see *different* loads — 241 Ω and 301 Ω — because the
classic four-resistor difference amplifier has unequal input impedances (`R1`
on the inverting side against `R3 + R4` on the non-inverting side). 0008's
even-order cancellation is bought by the two sides matching, and 0008 goes as
far as putting both polarities on one register die to protect it. The output
stage then loads those two polarities 25 % differently. That is not something I
can quantify without the OPA1612's distortion-versus-load data, and I could not
find it published, so it is flagged rather than costed.

### 6.4 `MUTE_N` gates the supplies, not the signal, and there is nothing at the jack

`MUTE_N` drives the LTC3265's `EN+`/`EN−`, so muting collapses both analog
rails. There is no output mute device, no relay, no series FET, and no DC
blocking capacitor — the difference amplifier's output reaches the jack through
a 100 Ω resistor and nothing else. Every rail-collapse and rail-restore
therefore appears at the jack as whatever the OPA1612 outputs do while its
supplies slew through zero. parts-notes.md names the benefit ("silence rather
than… a thump into somebody's amplifier") but that is the argument for muting
at all, not for muting this way; a supply-gated stage is the one arrangement
that *cannot* mute quietly, because the mute action is itself a supply
transient. Worth a bench measurement before the first listening test, and worth
recording as a known property of the line variant.

### 6.5 Smaller items, none blocking

- **`power.md` was updated to six amplifiers; the netlist comment was not.**
  The netlist says "power.md costed four"; power.md now says "**Six amplifier
  channels, not four**". Harmless, but it reads as a live discrepancy.
- **The register's `VOH` claim is not a datasheet number.** The netlist and
  parts-notes say ALVCH "sits a few tens of millivolts under the rail" at the
  ~1 mA an element draws. SCES021L guarantees `VOH ≥ VCC − 0.2 V` at
  `IOH = −100 µA` and `≥ 2.4 V` at −12 mA with VCC = 3 V; it publishes nothing
  at 1 mA. The ~20 Ω output impedance the claim rests on is a typical for the
  family, not a specification. Since it is common to every element it really is
  gain error, so this changes nothing — but it is stated as datasheet-derived
  and is not.
- **The bias-compensation-resistor argument understates itself.** parts-notes
  says a 218 Ω resistor at the non-inverting input "would add 1.9 nV/√Hz".
  218 Ω is 1.90 nV/√Hz of its own, but at that node it is multiplied by the
  stage's noise gain of 1.84, so the real cost is about 3.5 nV/√Hz. The
  decision (omit it) is more strongly supported than the number given.
- **A dropped `√2`.** The netlist comment "6.958 mA x 402 = 1.978 V RMS at
  digital full scale" — that product is 2.797 V *peak*; 1.978 V RMS is the
  result after dividing by √2, as `analog.txt` writes it. The number is right
  and the expression is not.
- **`interface.md` names the oscillators by their divided frequency.** It says
  `OSC_EN_441` enables "the 22.5792 MHz oscillator" and `OSC_EN_48` "the
  24.576 MHz oscillator". 0012 and the netlist fit **45.1584 MHz** and
  **49.152 MHz** parts, at twice the element clock, precisely because 0012
  chose the 1024 multiple. The contract document names the wrong parts.
- **`parts-notes.md` and `power.md` disagree on the module total by 56 mA.**
  parts-notes' "What it costs" block computes the pump input from a *symmetric*
  21.6 / 21.6 mA load — "VOUT+ load = 21.6 mA (positive chain) + 21.6 mA (into
  VIN_N) = 43 mA … = 90 mA from 5 V" — and concludes "the module lands near
  182 mA and the board near 416 mA". power.md uses the asymmetric load that the
  same parts-notes section argues for (21.6 positive, 44.8 negative) and gets
  139 mA for the pump, 238 mA module, 472 mA board. **power.md is right** and
  open-items.md quotes power.md's 472 mA. The parts-notes block contradicts its
  own preceding section.

## 7. The 604 Ω divergence: deliberate, but recorded for the wrong reason

The brief names this as known and deliberate, so this is not a finding against
the board. It is a finding against the record, because the reason written down
is not the reason that holds.

`parts-notes.md`: "At 200 Ω the negative rail asks for 56 mA at idle and 63 mA
at full scale. **That is past the LTC3265's 50 mA LDO rating**…"

`open-items.md`: "The 604 Ω difference network was chosen **only because** the
charge pump's internal LDO is rated 50 mA and 200 Ω wanted 63."

**The negative rail does not go through that LDO.** The netlist takes the
LT3094's input from `VOUT−` directly, `LDO−` drives nothing, and
`parts-notes.md` says so itself thirty lines later: "The LT3094 is fed from
`VOUT−` directly, not through LDO−." The 50 mA rating binds nothing. The
datasheet's own limit on `VOUT−` is `IVOUT–(SC) … 100 / 160 / 250 mA`, which
63 mA is comfortably inside.

**The reason that does hold is the USB budget**, and it holds tightly. Redoing
power.md's arithmetic at 200 Ω:

```
negative rail    21.6 IQ + 13.9 elements + 28.0 network      = 63.5 mA
VOUT+ load       21.6 + 63.5 + 3 (inverting pump quiescent)  = 88.1 mA
USB input        2 x 88.1                                    = 176 mA
module           60.6 + 35.5 + 176 + 3                       = 275 mA
board            275 + 234 (main board)                      = 509 mA
```

against a USB 2.0 host's 500 mA, which 0009 says the line module must fit. So
200 Ω really is unaffordable on this board — by 9 mA, not by an LDO rating.
open-items.md's conclusion ("what it recovers: 2.1 dB" under the 12 V wall
wart) survives, because the wall wart removes the USB budget too. Only the
"only because" clause is wrong, and it is the clause someone would act on if
they went looking for the 2.1 dB before the redesign lands.

## 8. What I could not verify

- **The OPA1612's distortion below 600 Ω of load.** SBOS450C's THD+N curves
  stop at `RL = 600 Ω` and its `AOL`/`VOUT` specifications at 2 kΩ. Two of the
  three stages run at 241 Ω and 301 Ω (§6.3). No data was found.
- **Whether GateMate GPIO are high-impedance before configuration completes.**
  parts-notes.md names this gap; I read DS1001 and UG1003 and found no
  statement either way. It bounds how long the register bus-hold pull-up sits
  on the header (§4.2), not whether the clamp handles it.
- **Whether the module's `J1` and the main board's `J2` mate pin-1 to pin-1.**
  Both boards instantiate the same `PinHeader_2x40_P1.27mm_Vertical` footprint
  and consume header pins in the same order, so the two netlists agree on
  *numbering*; whether that survives a real mated pair (one part has to be the
  socket, and a mated 2×40 mirrors columns) is a layout question.
  open-items.md already lists connector pin assignment as waiting on layout.
- **The SN74ALVCH16374's output-to-output skew**, which parts-notes.md already
  records as absent from SCES021L. I confirmed the switching table's MIN and
  TYP columns are unpopulated. The one-package-per-channel argument rests on
  die and supply sharing, not on a number.
- **The LT3045's and LT3094's exposed-pad thermal path**, because no layout
  exists. The LT3094 dissipates (10 V − 5 V) × 45 mA ≈ 225 mW in a 3 × 3 DFN if
  `VOUT−` runs near its unloaded −2·VIN_P; parts-notes.md's headroom table has
  `VOUT−` sagging to −5.2 V under load instead, which would make it 10 mW. The
  truth depends on the pump's 32 Ω under the real load and should be measured.

## 9. Two more, found after the sections above were written

### 9.1 The generated netlist contradicts itself on the LT3045 package, in adjacent lines

`lyrebird-dac.net` carries, for each of U5, U6, U9 and U14:

```
(ref "U5")
(value "LT3045 element reference")
(description "500mA, Adjustable, Ultralow Noise, Ultrahigh PSRR Linear Regulator, DFN-10")
(footprint "Package_DFN_QFN:DFN-12-1EP_3x3mm_P0.45mm_EP1.65x2.38mm")
```

The description comes from the KiCad symbol and says DFN-10; the footprint
string is the module's own override and says DFN-12. They sit one line apart.
The main board does **not** override it — `lyrebird-main.net` gives its LT3045
`Package_DFN_QFN:DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm`, which is right. So the
two boards in this repository disagree about the package of the same part, and
the module is the one that is wrong.

### 9.2 `brief.md` is stale in the same way `bom.csv` is, and repeats a rejected design

The "Where the board actually is" section describes the netlist "As generated
on 2026-09-12": 28 components, "**57 of 293 pins unconnected**", ID0 tied to
the 3.3 V reference rail, the divided clock reaching the header without the
translator, `SUM_P`/`SUM_N` merged into one net by `R_Network08`, and the
registers' clock inputs open. None of that is true now: 126 components, twelve
open pins, and all four faults fixed.

More consequentially, its requirements list still states the filter topology
the model rejected:

> **Filter passively before the op amp.** … The summing resistors are already
> in the path, so **a shunt capacitor at each node buys the first pole for one
> part.**

analog.txt Q2b is explicit that this does not work — "Against a true virtual
ground it sees no resistance and forms no pole at all… the rail modulation
arrives before the pole does" — and the board correctly does something else
(split the element around the capacitor). `brief.md` is the page someone reads
first, and it currently asks for the thing the board deliberately does not do.

## Summary

Blocking, in the order I would fix them:

1. **CCHD-957 footprint pad numbering is rotated 90°** (§1.2). Both oscillators
   get supply or ground on a signal pin in every possible placement.
2. **All four LT3045s carry a DFN-12 0.45 mm footprint for a DFN-10 0.5 mm
   part** (§3.3). The part cannot be placed, and its exposed pad has no net.
3. **`OSC_EN_48` and `OSC_EN_441` float before configuration** (§4.1), which
   permits two oscillators to drive one net into each other.

Not blocking but load-bearing:

4. **The model's output-stage topology is not the board's** (§2.3). Three
   published figures — stage SNR, system SNR, and "the output stage is the noise
   floor of this design" — come from a four-amplifier circuit that was not
   built. The real number is about 123.5–123.9 dB, not 125.8/126.3.
5. **analog.txt's Q1a/Q1b current columns are stale** (§2.2), by more than
   120 mA, because `run_analog.py` hard-codes power.md lines that have since
   changed. The element-resistor recommendation survives; the arithmetic behind
   it does not reproduce.
6. **`bom.csv` and `brief.md` describe a netlist that no longer exists**
   (§6.1, §9.2), and `brief.md` still asks for the summing-node shunt capacitor
   that analog.txt Q2b rejected.
7. **The audit command in `missing.md` does not run** (§6.2) — `build()`
   returns `None`. One line, and it is the procedure the repo nominates as the
   authority on completeness.

Everything else on this board checks out against its datasheet. The five custom
symbols are right, the LTC3265's configuration is right in every detail I could
test, the regulator housekeeping is right, the filter corners land where
analog.txt asks, and 0008's seven-of-fourteen constant-current property is
genuinely implemented with left and right fully separate.

## Cross-section flags

Every inconsistency between this module and something outside its scope. Each
is tagged with the section of this review that argues it.

- **[§2.3 — model]** `model/lyrebird_model/analog.py`'s `noise_budget` prices a
  topology the board does not build. Its docstring states "the four amplifiers
  power.md budgets for stereo: a transimpedance amplifier on the negative node,
  then a second amplifier that is simultaneously the transimpedance for the
  positive node and the inverting summer for the first one's output", with
  `n_fb = 3` and noise gains 1.857 / 2.858. The netlist has **six** amplifiers:
  two independent transimpedance stages per channel plus a four-resistor
  difference amplifier, with 2 × 402 Ω and 4 × 604 Ω of gain-setting resistance.
  Consequence: `analog.txt`'s Q1c stage-SNR column, its "125.2 dB" system
  figure, `notes-analog.md`'s repetition of it, and the claim "**the output
  stage is the noise floor of this design**" are all computed for a circuit
  that was not built. The board's real stage SNR is about 123.5–123.9 dB.
  `parts-notes.md` already recomputes this by hand and says so; the model was
  never updated. **The netlist is right and the model should be regenerated
  against it.**

- **[§2.2 — model]** `model/run_analog.py` hard-codes power.md lines that have
  changed: `PRE_ENUM_OTHER = 0.072 + 0.040`, `REG_RAIL_OTHER = 0.0081 + 0.002`,
  `module = i_rail + REG_RAIL_OTHER + 0.040 + 0.051`, and `+ 0.234` for the main
  board. `power.md` now carries 34.3 mA of registers (not 8.1), 35.5 mA of clock
  chain (not 40) and 139 mA for the op amp stage and charge pump (not 51).
  Q1a's `module`/`board` columns are wrong by >120 mA (115/349 printed against
  power.md's 238/472), and Q1b's `Minimum R for 28 elements high : 3312 ohm`
  falls out of the stale 27.9 mA allowance; with current figures it would be
  about 2.3 kΩ. The 3.34 kΩ element clears both, so no value moves — but the
  numbers do not reproduce.

- **[§2.1, §2.4 — model]** `run_analog.py`'s stated part parameters are not the
  part's: `E_N = 1.3e-9` against the OPA1612's 1.1 nV/√Hz typical (and 1.5 max,
  which nothing in the repo carries into a conclusion), and `I_N = 1.5e-12`
  against 1.7 pA/√Hz. `GBW = 40e6` is correct. `R_DIFF = 200.0` is the known
  604 Ω divergence.

- **[§2.4 — model]** `analog.txt` Q2c models intermodulation in the
  transimpedance stage only. The board has a third amplifier per channel — the
  difference stage — seeing −54.5 dBFS of residual into a bipolar input pair
  that the model never runs. Almost certainly immaterial; outside what was
  measured.

- **[§7 — `docs/open-items.md`]** "The 604 Ω difference network was chosen
  **only because** the charge pump's internal LDO is rated 50 mA and 200 Ω
  wanted 63" is false. The LT3094 is fed from `VOUT−` directly and `LDO−`
  drives nothing on this board — `parts-notes.md` says so itself. The reason
  that actually binds is the USB 2.0 budget: at 200 Ω the board totals about
  509 mA against 500 mA. The "what it recovers: 2.1 dB" conclusion survives
  (the wall wart removes the USB constraint too), but the stated cause does not,
  and it is the clause someone would act on if they went after the 2.1 dB
  before the redesign lands. `parts-notes.md` carries the same false reason.

- **[§1.2 — `docs/open-items.md`]** open-items.md's "Chosen since" table records
  the CCHD-957 footprint as drawn and closed. `parts-notes.md` leaves two things
  about it explicitly unverified. One is now settled — the long land dimension
  does lie along the 7.11 mm axis, the footprint is right — and the other is a
  **blocking defect**: the pad *numbering* is rotated 90° against the
  datasheet's bottom view, which puts supply or ground on an oscillator signal
  pin in every possible placement. open-items.md should reopen this.

- **[§4.1 — main board, `hardware/netlist/main_board.py`]** `OSC_EN_48` and
  `OSC_EN_441` have no pull resistor on **either** board. `main_board.py` pulls
  down `ID0` and `ID1` only; the module pulls down `MUTE_N` with 100 kΩ for
  exactly the reason that applies here too. The nets land on SN74AVC4T245
  A-port inputs, which have no bus hold and whose datasheet requires all unused
  data inputs to be held at VCCI or GND. Before FPGA configuration this leaves
  the two oscillator enables undefined, which can put two CCHD-957 outputs into
  contention on the shared `OSC_RAW` net, or leave `U1.CLK` floating on a part
  with no input pull-down. Fix belongs on one board or the other; the module's
  3.3 V side is the better place.

- **[§3.3, §9.1 — main board]** The two boards disagree about the LT3045's
  package. `lyrebird-main.net` uses
  `DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm` (correct — the LT3045's DD package is
  a 10-lead 3 × 3 mm DFN, exposed pad pin 11 = GND). The module overrides it to
  `DFN-12-1EP_3x3mm_P0.45mm_EP1.65x2.38mm` for all four of U5, U6, U9 and U14,
  on a symbol whose own description in the same netlist file says "DFN-10".
  **The main board is right.** `bom.csv` records the wrong package too.

- **[§6.5 — `hardware/interface.md`]** The contract names the oscillators by
  their divided frequency: "`OSC_EN_441` — Enable the 22.5792 MHz oscillator"
  and "`OSC_EN_48` — Enable the 24.576 MHz oscillator". 0012 and the netlist fit
  **45.1584 MHz** and **49.152 MHz** parts, at twice the element clock, which is
  the whole point of 0012's "1024 multiple" section. The netlist is right;
  interface.md names parts that are not fitted.

- **[§4.1 — `hardware/interface.md`]** "Exactly one oscillator runs at a time"
  is a rule with no hardware behind it. The netlist's single shared `OSC_RAW`
  net is legal only while it holds, and nothing enforces it before the FPGA is
  configured. interface.md should either state that the main board must hold
  both enables low until configured, or the module must fit the pull-downs.

- **[§4, §5.1 — HDL]** interface.md requires `ELEM[31:28]` to be "Reserved.
  Driven low by the main board". The module correctly leaves them at the header
  (four single-pin nets, J1 pins 57/59/61/63). There is no synthesizable
  top-level in `hdl/rtl/` that drives them — `lyrebird_sim_stub_ft601q.sv` has a
  28-bit `elem_o`. The element ordering it does produce matches interface.md and
  the netlist exactly (`{right negative, right positive, left negative, left
  positive}` = `ELEM[27:21], [20:14], [13:7], [6:0]`), so only the reserved four
  are unaccounted for.

- **[§6.4 — HDL]** `MUTE_N` now gates both analog rails through the LTC3265's
  `EN+`/`EN−`. An HDL that never asserts it leaves a board that enumerates,
  clocks and converts in silence. `parts-notes.md` records this as an HDL
  requirement; nothing in `hdl/` implements it yet. Separately, because the mute
  acts by collapsing the supplies rather than by muting the signal, and there is
  no DC blocking or output mute device at the jack, every assertion and release
  of `MUTE_N` is a supply transient straight into the output.

- **[§6.3 — decision 0008]** 0008 protects even-order cancellation by putting
  both polarities of a channel on one register die, calling it "real work, not
  tidiness". The output stage then loads the two polarities unequally: the
  positive transimpedance amplifier sees 402 ‖ 604 = 241 Ω and the negative one
  402 ‖ 1208 = 301 Ω, because the four-resistor difference amplifier has unequal
  input impedances. Both are below the 600 Ω of the OPA1612's lowest published
  distortion curve, so the asymmetry cannot be costed from the datasheet. Worth
  0008's attention because it works against the property 0008 exists to buy.

- **[§2.2 — `model/run_analog.py` and `power.md`]** These two are the only
  places the pre-enumeration budget is computed, and they no longer agree.
  Whoever reconciles the model's constants should also note that `power.md` and
  `parts-notes.md` disagree with each other by 56 mA on the module total
  (238 mA against 182 mA) because parts-notes' charge-pump block assumes a
  symmetric ±21.6 mA load that its own preceding section disproves. `power.md`
  is right, and `open-items.md`'s "472 mA against 500 mA USB 2.0 margin" follows
  power.md, so only parts-notes.md is the outlier.

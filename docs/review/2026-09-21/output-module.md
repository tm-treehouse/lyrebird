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


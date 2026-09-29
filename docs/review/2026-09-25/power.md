# Power design review — 12 V wall wart, two boards

Reviewed 2026-09-25 to 29 against `hardware/netlist/main_board.py`,
`hardware/netlist/output_module.py` and the generated
`lyrebird-main.net` / `lyrebird-dac.net`, which are the authority used
throughout: where a Python comment and the generated netlist disagree, the
netlist wins and the disagreement is a flag. Four faults were fixed while the
review was open — U7's missing input bypass, U14's SET resistor, the −6 V pins'
position on the connector, and the two power-good nets — and the entries for
those are marked CLOSED rather than deleted, so the record shows what was real.

Two things are out of scope by instruction and are not reported as faults: the
adapter is unchosen so its tolerance is assumed, and the reference-rail
transition-current item is signal integrity rather than supply.

## Verdict

The architecture is sound and the inverting converter is, against expectation,
wired correctly — the feedback referencing, the enable, the bootstrap, the
inductor return and the exposed-pad assignment are all right, and I verified
each against the LMR33630 datasheet rather than against the comment beside it.
Four things are worth acting on; one stops a build and one was closed while
this review was running.

| | |
| --- | --- |
| **B-1** | **Open.** Both LMR33630s carry a footprint for the wrong package: `HTSSOP-8 3x3 P0.65mm` against an HSOIC-8, 5.00 × 4.00 mm body on 1.27 mm pitch. The KiCad symbol's own `fplist` names the right land. Nothing in either check suite looks at footprints, and this is now the second footprint fault in the power tree after the LTM4622's transposed axes. |
| **B-2** | **Closed during this review.** U7 had no input capacitor: its PGND *is* −6V_A, so the datasheet's required 10 µF "directly to this pin and PGND" means +12 V to −6V_A, and only +12 V-to-ground parts were fitted. I measured 100 % of the 0.69 A switch transition returning through the analog ground plane, 7.6 V across the pin pair. 10 µF + 100 nF is now fitted and the same measurement gives 91 % local, 9 % plane, 2.6 V. Retained here because it was the third fault in U7 and all three were the same mistake. |
| **B-3** | **Narrowed, still open.** `verify_power.py` now tests the stacked tolerance corner and U14 is 40.2 k / 4.02 V, which clears both bounds. What is still unaccounted for anywhere is the **+5 V rail's own spread**: 4.86 V to 5.17 V from the LMR33630's ±1.5 % feedback tolerance (datasheet 7.5) and 1 % divider parts, against the 5.02 V every document states as exact. Every other rail has volts of headroom, so U14 was the only casualty — but the number is still absent from both `power.md` files. |
| **B-4** | **New.** The translator's supply ordering, relied on in place of the pull-up SCES576I asks for, is sound arithmetic (2.3× of margin, verified below) and **covers only one of the two banks.** Bank 1's outputs are on the A side and are protected by making VCC(A) last; bank 2's outputs are on the B side, powered by the rail that arrives *first*, and they carry both oscillator enables onto a shared net that is only legal with one part enabled. |

---

# Part 1 — Are the existing checks worth anything?

Answer: `power_input_transient.py` is worth a great deal and `verify_power.py`
is worth less than its 18/18 suggests, for one structural reason and three
mechanical ones. Method: for every check, perturb what it depends on and see
whether the verdict moves. Where the dependency is a netlist fact I tampered
with a **copy** of the generated netlist in a scratchpad; nothing in the repo
was modified.

## 1.1 The one check that reads the circuit, and the five ways it stops

`ldo_rails()` is the only path in either file that reads a netlist. It is a
real improvement and it has teeth — but it fails *open* in every direction,
and each of the following restores an 18-check suite to "all pass" with one
fewer subject.

I exercised it against copies of both `.net` files:

| Tamper | Result |
| --- | --- |
| **T1** U14's SET resistor back to `49.9k 0.1%` — the exact fault this check was written for | **FAIL**, correctly: `module U14: dropout on a 4.99 V rail`. The check works. |
| **T2** the same 45.3 kΩ spelled `45300R 0.1%` instead of `45.3k` | U14 vanishes from the list. Report: **"17/17 checks pass"** |
| **T3** U14 fed from a `+5V_PRE` net instead of `+5V` | U14 vanishes. **"17/17 checks pass"** |
| **T4** U14's value string changed to `ADM7150 op amp positive rail` | U14 vanishes. **"17/17 checks pass"** |

T2 is the regex: `re.match(r"([\d.]+)k", …)` only understands a value written
in kilohms. T3 is `if rail not in known: continue`, where `known` is the
two-entry dict `{"+5V", "-6V_A"}`. T4 is the family match against the
component's free-text `value`. All three are the failure mode already recorded
in the file's own comment — *"a check that finds no subjects passes"* — and
the lesson was written down without being closed.

**The fix is one line and it is the only thing that makes this check
trustworthy: assert the subject count.** The design has exactly six
post-regulators; if the reader returns five, that is a failure, not a smaller
suite. Nothing else in this review is as cheap.

Two further scope limits on the same check, neither a silent skip:

- **The input voltage is still a restated constant.** `known` maps `+5V` to
  `V_5V = 5.02`, a `Fact` typed in by hand. The divider that actually sets it
  (100 k / 24.9 k on U5's FB) is in the netlist and is not read, so changing it
  moves every module dropout verdict by nothing at all. The check reads the
  *output* side of all six regulators from the circuit and the *input* side of
  none of them.
- **No tolerance is applied to either side.** See B-3 in the verdict and
  §2.1: 5.02 V is the nominal of a rail whose real range is 4.86–5.17 V, and
  U14's fixed 4.53 V has 330 mV at the low corner against a 330 mV dropout
  maximum. The check passes with +230 mV because it is comparing two
  typicals.
- **The dropout constant is the wrong one, in the unconservative direction.**
  `U3_DROPOUT = 0.26 V, "LT3045 at 500 mA; less at our load"` and the margin
  line repeats *"the low-current dropout is smaller and is not published in
  anything fetched here."* Both halves are wrong. The LT3045 datasheet
  (3045f, Electrical Characteristics) publishes dropout at **I_LOAD = 1 mA and
  50 mA as 220 mV typical, 275 mV maximum, 330 mV over temperature** — larger
  in the max column, not smaller, and published. 260 mV is the front-page
  headline at 500 mA. The same 260 mV is also applied to U8, which is an
  **LT3094** with its own 235 mV figure.

## 1.2 Every other check in the file, swept exhaustively

Rather than guess which checks are narrow, I perturbed *every* `Fact` in the
module by ×10⁻³, 0.1, 0.5, 0.9, 1.1, 2, 10, 10³ and −1, re-ran `main()` after
each, and recorded which checks ever changed verdict. Harness:
`hardware/sim/power_negative_rail.py --sweep-verify`.

Result: **17 of 18 checks can be made to fail by some constant. One cannot.**

- **`FT601Q supply skew, VCCIO against VCC33` is dead.** It asserts
  `2.3·R_SET·C_SET < 50 ms` from `33.2e3` and `100e-9` — both written as bare
  literals inside the `ramps` list rather than as `Fact`s, so they are not
  even reachable by the sweep, and the threshold is 6.6× the value. Nothing in
  the netlist is consulted; C_SET returning to 4.7 µF (the fault this check
  commemorates) would not move it, because the literal here would still say
  100 nF. The transient file's S-2 tests the same property properly and *does*
  fail on that tamper.

That leaves a subtler problem the sweep exposes, which is not about any single
check: **`I_MAIN_OTHER` is an independent 234 mA total that no per-rail figure
adds up to.** The file also carries `I_3V3 = 60 mA`, `I_2V5 = 90 mA`,
`I_1V0 = 80 mA`; reflected to +5 V through the stated efficiencies those come
to about 136 mA, not 234 mA — a 72 % disagreement inside one file. The
per-rail numbers are used only for U3's dissipation, so the visible
consequence is that `LT3045 dissipation on the 3.3 V rail` reports 102 mW
where the main board's own `power.md` says the rail carries 185 mA, i.e.
**315 mW**. Three of the four figures cannot all be right, and no check
compares them.

Two checks are true statements about parts rather than about this circuit, and
one is labelled as such:

- `Buck rating covers the TVS clamp [structural]` — honestly flagged; it
  compares 29.2 V to 36 V and passed with D2 deleted. It also compares the
  wrong pair for U7: see §3.6, where the clamp leaves **0.8 V** rather than
  6.8 V.
- `A 19 V adapter is accepted, not fought` and `TVS does not conduct in
  normal operation` compare three constants among themselves. Correct, and no
  circuit change reaches them.

## 1.3 `power_input_transient.py`: the tampers are real, and two gaps remain

This file is the better of the two and its self-assessment is honest: it
reports 20/20 checks with **2 MISS and 2 HOLE** among its 9 tampers, which is
already not the "7 tampers, all passing" the brief describes. I re-ran it and
reproduced that exactly. Its conclusions on inrush, reverse polarity and the
19 V brick I accept; the modelling is careful and the D3 clamp result
(−0.399 V → −0.233 V) is a genuine design improvement found by simulation.

Three things it does not cover, all consequences of the same structural fact
— **it models a circuit transcribed by hand, so the circuit it models is the
one that existed when each constant was typed**:

1. **U7 is not in it at all.** There is no inverting converter in any of the
   four scenarios. Every input-side verdict — I-1 through I-4 inrush, S-5
   start-up current against the fuse hold — is computed for a board with one
   converter on it. The −6 V rail's own inrush, its start-up current and its
   sequencing relative to +5 V are unmodelled. §3 does that work.
2. **Its load constants are two generations stale.**
   `I_LOAD_5V = 0.472 A, "verify_power.py: 238 mA module + 234 mA main"` —
   `verify_power.py` now says 357 mA, 123 mA of it module, and 472 mA was the
   pre-decision-5 figure including the deleted charge pump.
   `I_MEZZ = 0.238 A, "module power.md, post-parts-selection"` is the same
   stale number, and it sets `Rmezz`, the load the sequencing model actually
   drives.
3. **`F1_NETLIST_VALUE = "1.1 A hold, 2.2 A trip"`**, printed at the top of
   every run as *"NOTE: main_board.py says …"* followed by a warning that no
   1812L part matches it. `main_board.py` says
   `1812L050/30 PPTC 0.5A hold 30V 100A`. The discrepancy was fixed in the
   netlist and the file still reports it, so a passing run emits a false
   warning about a resolved fault. This is the cleanest available proof that
   the coupling between checks and circuit is manual, because here the drift
   is visible in the output.

Two mechanical defects in its own checks, found by tampering:

- **S-4 cannot see a rail that collapses after it arrives.** The predicate is
  `glitch_peak < 0.05 or rows["+1V0"]["t90"] is not None`. It caught the
  historical fault because that one died at 319 mV, below 90 %. A rail that
  reaches 998 mV at 4.9 ms and collapses at 40 ms satisfies the second clause
  and passes S-4, S-3 and S-1 together. The check's name — "the core rail does
  not start and then collapse" — describes something it does not test.
- **S-6 reports a number it did not check.** The `over` list is built from
  `rows` (no host) while the detail string prints
  `rows_h['+1V0']['peak']` (host). Harmless today because the gate is gone and
  the two runs agree; it is a latent mismatch between verdict and evidence.
- **F1's thermal model has a 128 s time constant**, from fitting
  `t(I) = −τ·ln(1 − (I_hold/I)²)` at 8 A with R held at R1max. That implies
  C_th = 0.30 J/K for an 1812 body of roughly 14 mm³, which is an order of
  magnitude high, and E_trip = 31.9 J correspondingly. The file states the
  direction of the error and it is the conservative one for "the inrush is
  harmless"; I checked whether it reaches any verdict and it does not — every
  trip verdict in the file is decided by current being *below the hold
  current*, where τ is irrelevant. Worth recording rather than fixing.
  (Separately: `F1_TTRIP_8A` is assigned twice, 0.15 s then 0.50 s, both
  marked `datasheet`; the second wins and the first is dead. And the comment
  block above the model still derives τ from "I_hold = 1.10 A", the superseded
  part.)

## 1.4 The class of fault no power check can reach

Two faults found this round came from outside the power checks and both were in
the power tree: the LTM4622's land pattern with its axes transposed, putting
+2V5 and +5V onto VOUT2 — the FPGA core rail, 1.20 V absolute maximum — and
both LMR33630 power-good pins on single-node nets from `Net("PG_5V")` being
called twice.

Neither was reachable from `verify_power.py` or `power_input_transient.py`, and
the reason is worth stating once: **both files reason about rails by name.** A
rail is a string, its voltage is a constant, and the question "does this rail
arrive at the right ball of the right package" is not expressible. That
assumption — the footprint is right — has now failed twice in the power tree:
once on the LTM4622's land, and it is still failing on both LMR33630s (B-1).
`hardware/sim/power_negative_rail.py` check A-2 closes the LMR33630 half by
comparing the assigned footprint against the pitch the datasheet's package
demands; the general form would compare every footprint's pin count and pitch
against its symbol's own `fplist`, which is cheap and which nothing does.

The PG fault has a second lesson that belongs in §3: the first two defects
found in U7 were both **somebody treating its GND pin as system ground.** The
pull-up value was right for a ground-referenced flag and wrong for this one.
That is the error this circuit invites, and §3 is written to look for it
everywhere else.

One more silent-subject trap, in the new reader and in mine: both split the
netlist on the bare token `(comp`, which also matches `(component_classes)`
inside every component block. The last such fragment runs on into the nets
section and takes the first node's ref with no value, so
`verify_power.py`'s value table carries one bogus entry — `val["C8"] = ""` on
the main board, `val["C36"] = ""` on the module. Harmless only because neither
happens to be a SET resistor. I hit the same bug writing A-1 and it cost the
input-capacitance audit its 22 µF until I split on `\n    (comp\n` instead.

---

# Part 2 — Every rail, jack to load

Recomputed rather than read. Where a figure is a load estimate I say so; the
converters' own behaviour is computed from the datasheets named in Part 7.

## 2.1 The chain, at the worst input

At 11.4 V in (the assumed −5 % corner), drawing 219 mA:

| Node | V | How |
| --- | --- | --- |
| J4 barrel jack | 11.40 | assumed adapter tolerance |
| after F1 | 11.18 | 219 mA × 1.00 Ω R1max — the *post-trip* resistance, which is the right one to use |
| after D1 (+12V) | 10.83 | 0.35 V assumed off the SS34 curve, not a spec limit |
| U5 input | 10.83 | 7.0 V above the 3.8 V minimum operating input |
| **+5V** | **4.86 – 5.17** | 5.016 V nominal; ±1.5 % on VFB (0.985/1.000/1.015 V, table 7.5) and 1 % on 100 k / 24.9 k |
| **−6V_A** | **−5.79 – −6.17** | same arithmetic on 124 k / 24.9 k |
| at the mezzanine | −0.6 mV | 4 contacts × 20 mΩ in parallel at 123 mA |

**The ±1.5 % is the finding.** Every document in the repository treats
+5V as 5.02 V exactly, and the checks compare typical against typical. The
consequences run downhill:

- **U14 (+5V_A), now 40.2 k / 4.02 V.** I checked the whole stack
  independently and it clears, on both bounds. Dropout side: the rail's low
  corner 4.863 V against U14's high corner (40.2 k × the LT3045's 102 µA SET
  maximum) = 4.100 V leaves **763 mV, i.e. +433 mV over the 330 mV
  over-temperature dropout** at this load (3045f, I_LOAD = 1 mA and 50 mA
  rows — note that the published low-current figure is *larger* than the
  260 mV headline at 500 mA, not smaller). Swing side: U14's low corner
  40.2 k × 98 µA = 3.940 V against the 3.43 V the ±2.83 V output needs
  through an OPA1612 that reaches within 600 mV of its rails, leaving
  **+510 mV**. An intermediate 45.3 k / 4.53 V, which this review saw
  briefly, had only 3 mV on the dropout bound. 40.2 k is right.
- **U9 (+2V5), U5/U6 (3.32 V), U3 (3.32 V)** all have 1.5 V or more and are
  unaffected.
- **U8 (LT3094, −4.99 V from −5.79 V worst case)** has 793 mV against a
  235 mV dropout. Comfortable.

## 2.2 Current, rail by rail

| Rail | V | Source | At the rail | Reflected to +5 V | From 12 V |
| --- | --- | --- | --- | --- | --- |
| +3V3 | 3.32 | U3 LT3045 | **60 or 185 mA — unresolved** | 62 or 187 mA | |
| +2V5 | 2.49 | U4 ch 1 | 15–90 mA, unresolved | 9–51 mA | |
| +1V0 | 1.00 | U4 ch 2 | 80–149 mA, unresolved | 20–35 mA | |
| mezzanine +5V | 5.02 | U5 | 123 mA | 123 mA | |
| **+5V total** | | U5 | **357 mA** | | 166 mA at 11.4 V |
| **−6V_A** | −5.98 | U7 | **63.5 mA** | — | 38 mA at 11.4 V |
| **At the jack** | | | | | **219 mA, 2.42 W** |

The 219 mA reproduces exactly in my own model, from the two converters' output
powers and their efficiencies, so the *total* is agreed by three independent
routes. What is not agreed is how it divides:

**The per-rail currents are unresolved in a way no document admits.** The main
board's `power.md` says +3V3 carries 185 mA, +2V5 15 mA and +1V0 149 mA.
`verify_power.py` says 60 mA, 90 mA and 80 mA, all marked ASSUMED. Reflected
to +5 V, `power.md`'s three lines come to 231 mA and `verify_power.py`'s to
about 136 mA, yet both files put the main board's subtotal at 234 mA. The
234 mA total and the 60/90/80 split cannot both be right, and the only visible
consequence today is U3's dissipation (§6). **I did not resolve it**: it needs
the FT601Q's VCC33 current from its datasheet, which I did not fetch, and a
GateMate core figure that depends on a bitstream that does not exist.

## 2.3 What is comfortable and what is not

| Against | Limit | Drawn | Verdict |
| --- | --- | --- | --- |
| F1 hold, 70 °C | 330 mA | 219 mA steady | 111 mA spare |
| F1 hold, 70 °C, during the shared 4 ms soft start | 330 mA | **305 mA** | see below |
| U5 output | 3.0 A | 357 mA | 8.4× |
| U7 output, *in this topology* | **2.21 A**, not 3 A | 63.5 mA | 35× |
| U3 LT3045 output | 500 mA | 60–185 mA | ≥2.7× |
| U8 LT3094 output | 500 mA | 63.5 mA | 7.9× |
| U8 programmed ILIM | 151 mA (3.75 kΩ·A / 24.9 k, verified) | 63.5 mA | 2.4× |

**The 4 ms row is new and belongs to the missing converter.** Both enables are
the same net, so both converters soft-start simultaneously: charging 66.4 µF to
5.016 V and 47.1 µF to 5.98 V inside one 4 ms window is 83 mA and 70 mA of
output current on top of the load, which is **305 mA at the jack** against
330 mA of hold at 70 °C. `power_input_transient.py`'s S-5 reports 190 mA for
the same instant because there is no inverter in it. The right conclusion is
*not* that F1 is marginal — a PPTC integrates, and 4 ms at 305 mA is
microjoules against tens of joules — but that the hold-current comparison is
the wrong criterion for a 4 ms event, and that the check which looked
comfortable was comfortable because a converter was missing.

---

# Part 3 — U7, the inverting buck-boost

The piece least likely to be right. Everything below is computed in **the
device's own frame**, where PGND is the −6 V rail and system ground is the
output node, because that is the frame in which the datasheet's numbers are
written and the frame whose absence caused both faults already found here.

Work: `hardware/sim/power_negative_rail.py`, sections B and C, 8 analytic
checks and 3 ngspice circuits, each tamper-tested.

## 3.1 Feedback referencing — correct, and verified twice

FB regulates to VFB above the device's GND pin. The divider runs from system
ground (which is the output node in the device's frame) down to −6V_A:

    FB sits at −4.980 V in board terms = exactly 1.000 V above U7's GND
    124 k leg: 40.2 µA      24.9 k leg: 40.2 µA      agree to 0.00 %
    |Vout| = 1.000 × (1 + 124/24.9) = 5.980 V

ngspice, solving the real divider closed around a regulator that holds
FB − PGND = 1.0 V, settles at **−5.980 V**. The same two resistors with the
loop closed around FB − *system ground* = 1.0 V — the frame error — run the
rail to the **−30 V** clamp, i.e. the divider has no solution and the converter
would drive to its limit. So the referencing is right, and the failure mode of
getting it wrong is not a small offset but an unbounded rail.

I also read the divider out of the generated netlist rather than trusting the
comment: 124 k from GND to FB, 24.9 k from FB to −6V_A, giving −5.980 V (A-3).

## 3.2 Duty cycle, on-time, and why the on-time question has a surprising answer

    D = |Vout| / (Vin + |Vout|)

| Vin at U7 | VIN−PGND | D | I_L | I_VIN | ΔI_L | I_pk | t_on | f | mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10.83 V | 16.81 | 0.3557 | 98.6 mA | 35.1 mA | 963 mA | 0.690 A | 637 ns | 160 kHz | DCM |
| 11.43 V | 17.41 | 0.3435 | 96.7 mA | 33.2 mA | 982 mA | 0.690 A | 604 ns | 160 kHz | DCM |
| 12.03 V | 18.01 | 0.3320 | 95.1 mA | 31.6 mA | 999 mA | 0.690 A | 574 ns | 160 kHz | DCM |
| 18.43 V | 24.41 | 0.2450 | 84.1 mA | 20.6 mA | 1129 mA | 0.690 A | 374 ns | 160 kHz | DCM |

**Inductor current is not load current in this topology, and that is the whole
trap.** KCL at PGND: the load returns into PGND and the low-side switch draws
out of it, so `I_load = (1 − D)·I_L` and therefore `I_L = I_load/(1 − D)` =
96.7 mA, not 63.5 mA. Reading it as a buck understates the inductor current by
a third and the input current by everything.

**The converter is in deep discontinuous conduction**: ΔI_L is 982 mA against
96.7 mA of average, so at the design load it cannot be continuous. I expected
minimum on-time to bind, and it does not, for a reason worth recording:
`IPEAK-MIN = 0.69 A` (table 7.6) is a floor on the commanded peak, so the part
**folds frequency back rather than shortening the pulse** — 160 kHz at
604 ns, against a minimum on-time of **75 ns typical / 108 ns maximum for the
DDA package** (the front page's 68 ns is the RNX package). 5.6× of margin, and
it is structural: t_on = L·I_pk/(VIN−PGND − |Vout|) falls only as 1/Vin, so no
input this board can present makes it bind. I tampered a 60 V input in and
t_on was still 115 ns.

ngspice cross-check on the algebra: driving the real switch pair open loop at
D = 0.3435 into 800 mA — where the prediction is continuous — lands the rail at
−6.143 V with 1253 mA of inductor current against `I_load/(1−D)` = 1219 mA.
At the design load of 63.5 mA the same duty overshoots to −6.275 V, which is
what DCM does, independently confirming the mode.

## 3.3 Current capability — the datasheet's 3 A does not apply

    I_out(max) = (I_SC − ΔI_L/2) × (1 − D) = (3.85 − 0.49) × 0.657 = 2.21 A

using the **minimum** high-side limit. The load conducts only during (1 − D),
so the rating scales by 0.657 and the ripple comes off the top.
`verify_power.py` compares 63.5 mA to 0.3 × 3 A, which reaches the right
verdict from a number that does not apply; at 800 mA the two answers diverge
and the 30 % criterion correctly fails against 2.21 A while passing against
3 A. Nothing on this board asks for 800 mA, so this is a latent rather than a
live error.

## 3.4 Every pin against its rating, in the device's frame

| Pin | Stress | Rating | Verdict |
| --- | --- | --- | --- |
| VIN−PGND, 12.6 V adapter | 18.58 V | 36 V op / 38 V abs | fine |
| VIN−PGND, 19 V brick | 24.98 V | 36 V op | fine |
| VIN−PGND, **TVS clamped surge** | **35.18 V** | 36 V op / 38 V abs | **0.82 V of margin** |
| EN − VIN | 0 V (same net) | ≤ VIN + 0.3 V | correct, and the only simple arrangement that works |
| EN − PGND | 17.41 V | expressed relative to VIN, so legal | fine |
| PG − AGND, released | +5.98 V | 0–18 V op, 0–22 V abs | fine |
| AGND − PGND | 0 V (pin 1 and the pad are the same net) | ±0.3 V | correct |
| BOOT − SW | ≤ 5.5 V | 5.5 V | 100 nF across SW to BOOT, correct |
| VCC − AGND | ≈ 5 V | −0.3 to 5.5 V | 1 µF to −6V_A, **correct** |

Three of these are worth drawing out.

**The clamped surge leaves 0.82 V, not 6.8 V.** `verify_power.py`'s
"Buck rating covers the TVS clamp" compares 29.2 V to 36 V and reports 6.8 V of
margin. For U5 that is right. For U7 the stress is `V_clamp + |Vout|` =
35.18 V, because |Vout| adds to every input stress on this device — and there
is no U7 in that check at all. 0.82 V against a *recommended operating*
maximum, 2.8 V against absolute. Not a fault: a TVS clamp is a microsecond
event and the absolute maximum is what applies. But it is the tightest number
anywhere in the input chain and nothing in the repository contains it.

**EN tied to VIN is the correct answer, not a shortcut.** The rating is
"EN must not exceed VIN by more than 0.3 V" — relative to VIN, not absolute —
so EN on VIN is compliant at any input. A logic-level enable referenced to
system ground would sit 5.98 V *below* this device's ground and hold it off
permanently. This is where naive inverting designs die and this one does not.

**PG is inside its rating and is useless as a signal.** Now that it is
connected (it was on a single-node net until this round), the 100 k to system
ground is a pull-*up* relative to AGND = −5.98 V, which is right. But the flag
swings 0 V to −5.98 V, which no 2.5 V logic on either board can receive, and
**before the converter starts, AGND is 0 V, so an asserted low reads 0 V —
identical to good.** It cannot distinguish "not started" from "in regulation"
at the only moment a sequencer would care. It is a scope point. If anyone later
tries to gate MUTE_N or a supervisor from it, that is a fault waiting.

## 3.5 VCC and the bootstrap — both correct

`decouple(inv["VCC"], v["-6V_A"], "1uF")` puts the internal LDO's bypass on the
device's own ground, which is what pin 6 asks for and what the 5.5 V
VCC-to-AGND absolute maximum requires. Bypassing it to system ground instead
would hold it 5.98 V off its own reference and inject the whole switching
excursion of AGND into the control supply. The bootstrap is 100 nF across SW to
BOOT, datasheet value, correct.

## 3.6 U7 had no input capacitor — found here, fixed, and what it bought

`caps_between()` over the generated netlist, when this review first ran:

    +12V to GND      22.10 uF     <- U5's input capacitor
    +12V to -6V_A     0.00 uF     <- U7's input capacitor
    GND  to -6V_A    47.10 uF     <- U7's output capacitor

It now reads **10.10 µF** on the middle row. The measurement below is why.

SNVSAN3F 9.2.2.6: *"A minimum of 10 µF of ceramic capacitance is required on
the input of the LMR33630 … In addition, a small case size, 220-nF ceramic
capacitor must be used at the input, as close as possible to the regulator."*
And pin 2's own description: *"Connect a high-quality bypass capacitor or
capacitors directly to this pin and PGND."* For U7, PGND is −6V_A. **Nothing is
fitted there.**

What it costs, measured. I injected the 0.69 A peak collapsing in the
datasheet's own 2 ns dead time (tD, System Characteristics) into the
VIN/PGND pin pair and measured where it returns:

| | VIN−PGND excursion | through the plane | through a local cap |
| --- | --- | --- | --- |
| as it was, no VIN-to-PGND cap | **7.6 V** | **690 mA (100 %)** | — |
| as built now, 10 µF + 100 nF | 2.6 V | 63 mA (9 %) | 627 mA (91 %) |

**The entire switch transition returns through the ground plane** — from the
+12 V capacitor, across the plane, into the −6 V capacitor — because there is
no other path between VIN and PGND. That is two capacitors in series, roughly
11 nH of loop, and a 0.69 A / 2 ns edge injected into the analog return of a
board whose whole premise is a quiet ground. Tampering the plane inductance to
1 pH does not help: the path is a topology fact, not a parasitic one.

A 7.6 V loop excursion also implies SW undershoot beyond the **−3.5 V /
100 ns** transient floor (−0.3 V DC), which I did not model directly but which
follows from the same inductance. So this is a rating question as well as an
EMI one.

**Fixed** by fitting 10 µF + 100 nF from +12 V to −6V_A. Two things remain
worth saying. The datasheet asks specifically for a *small case size* 220 nF
as well as the bulk, "as close as possible to the regulator"; 100 nF is in the
right place and is the value the rest of the board uses. And the 9 % that still
returns through the plane, plus the 2.6 V that remains across the pin pair, are
set by loop inductance and are therefore a **layout** obligation now rather
than a schematic one: this is the one place on either board where the
placement of two specific capacitors is load-bearing for the analog ground.

This was the third fault found in U7, after the feedback-frame assumption and
the power-good pull-up, and **all three were the same mistake** — reasoning
about a device whose GND pin is the negative output as though its GND were the
board's. That is the pattern to carry into layout review.

## 3.7 Light-load behaviour, recorded not flagged

Frequency foldback makes the switching frequency load-dependent:
f ≈ I_load / 398 nC. At 63.5 mA that is 160 kHz. With MUTE_N low the LT3094
goes to its 3 µA shutdown quiescent and the only load left is the 149 kΩ
feedback divider, so f falls into the audio band — a few kHz to a few hundred
hertz. The analog stage is off then and nothing is listening, but L2 is a
12 × 12 mm inductor pulsing at audio rates next to the mezzanine, and the
board's power-on state is MUTE_N low. Worth a bench look, not a design change.

---

# Part 4 — Sequencing

Modelled in `power_negative_rail.py` section D, with both switchers and all
five module post-regulators, each following the mechanism its datasheet names
rather than a time quoted in prose. Ramp times agree with the analytic
`2.3·R_SET·C_SET` to better than 1 %, which is the cross-check.

| Rail | 10 % | 90 % | set by |
| --- | --- | --- | --- |
| +12V | 0.02 ms | 0.08 ms | the plug |
| +5V | 0.44 ms | 3.66 ms | U5's internal 4 ms soft start |
| −6V_A | 0.44 ms | 3.64 ms | U7's, same enable, same 4 ms |
| +2V5 (main) | — | ≈4.9 ms | LTM4622, 1.4 µA into 10 nF |
| +1V0 (main) | — | ≈4.9 ms | same |
| +3V3 (main) | — | ≈8 ms | U3, 33.2 k × **100 nF** |
| **+3V3_CLK** | 17.5 ms | **361 ms** | U6, 33.2 k × 4.7 µF |
| **+3V3_REF** | 17.6 ms | **362 ms** | U5, 33.2 k × 4.7 µF |
| **+5V_A** | 39.9 ms | **455 ms** | U14, 40.2 k × 4.7 µF, gated by MUTE_N |
| **−5V_A** | 44.7 ms | **561 ms** | U8, 49.9 k × 4.7 µF, gated by MUTE_N |
| **+2V5 (module)** | 27.3 ms | **574 ms** | U9, 24.9 k × **10 µF**, last on purpose |

## 4.1 The two switchers are correctly not sequenced

Both enables are the same net (+12 V), so both start together off their own
UVLO. This is not laziness: U7 **cannot** be sequenced behind U5 by any
ground-referenced signal, because such a signal sits 5.98 V below U7's own
ground. Any staging would need a level shift or an optocoupler. Nothing on
either board needs the staging, so the simple arrangement is also the right one.

## 4.2 The module's rails arrive 50 to 150 times later than the FPGA's

**This is the sequencing finding, and it is not in any document.** The main
board deliberately cut U3's C_SET from 4.7 µF to 100 nF because 359 ms of ramp
put VCC33 a third of a second behind VCCIO. That reasoning is written out in
`main_board.py` and in `lyrebird_parts.py`. **All five of the module's
post-regulators kept the 4.7 µF**, and because `lt3045_housekeeping` ties PGFB
to IN on every one of them — disabling the 2 mA fast-start circuit that exists
to charge exactly this capacitor — the ramp is the full `2.3·R_SET·C_SET`.

So:

- the FPGA's own rails are up at about **4.9 ms** and its 2.5 V bank drivers
  are live from then;
- the module's element-reference rail, which powers both
  **SN74ALVCH16374** register packages, does not reach voltage until
  **362 ms**;
- the module's 2.5 V rail, which powers the **74AVC4T245**'s A side — the
  header-facing domain the FPGA drives directly — does not reach voltage until
  **574 ms**, deliberately (§4.4).

The FPGA loads its bitstream from SPI flash before it drives anything, so the
race is *bitstream load time* against *271–362 ms of RC*. **Nobody has measured
the first number and nothing enforces the order.** `MUTE_N` is an *output* of
the FPGA and the module returns no power-good, so there is no signal in either
direction that could sequence this. If configuration completes first, 28
element lines plus the element clock are driven into register inputs whose VCC
is still climbing, and two translator control inputs into a VCC(A) still
climbing — current into input protection structures on parts whose datasheets I
did not fetch and which I therefore cannot clear.

Three things would settle it, cheapest first: measure the configuration time;
or hold the element outputs in the bitstream until a timer expires. Cutting
C_SET is **no longer freely available**: `+3V3_REF` must keep its 4.7 µF
because that capacitor buys the 0.8 µV RMS the whole design leans on, and
`+2V5` must stay slow because §4.4 depends on it being the last rail. That
leaves `+3V3_CLK`, which cannot be cut either without breaking §4.4's ordering
from the other side. The sequencing is now load-bearing in two directions at
once, which is worth knowing before anyone tunes one of these capacitors for a
different reason.

## 4.3 The two analog rails do not arrive together

`+5V_A` reaches 90 % at 455 ms and `−5V_A` at 561 ms — **106 ms apart**,
because their SET resistors differ (40.2 k against 49.9 k) while their C_SET
does not. The U14 fix, correct on every other count, widened this gap from
51 ms to 106 ms as a side effect.
Both are gated by the same MUTE_N and both inputs are already established, so
this is not a supply fault: the OPA1612 tolerates ±2.25 V to ±18 V and 36 V
total, and asymmetric rails are an undefined-output condition rather than a
damage one.

It matters because **the jack has no DC blocking.** For 106 ms the six
amplifiers have a positive rail well ahead of their negative one, their outputs
are undefined, and that reaches the line output directly. This is the concrete
content of open item D10 — "collapsing the supplies is a blunt mute and every
assertion is a transient into an unblocked output". Now it has a number:
106 ms of asymmetry on every unmute, plus the 455 ms ramp itself. If D10 is
ever resolved by matching the two ramps, the lever is C_SET on U8 (a 3.8 µF
against U14's 4.7 µF equalises them), not the SET resistors, which set the
voltages.

## 4.4 The translator's supply ordering: the arithmetic holds, the coverage does not

`output_module.py` ties both `~OE` pins low, against SCES576I's instruction to
pull OE up and not enable before both supplies are fully ramped — and meets the
datasheet's *intent* instead by making VCC(A) the last rail to arrive, with
10 µF rather than 4.7 µF on U9's SET. I was asked to check that reasoning. It
divides cleanly into two halves and only one of them holds.

**The arithmetic is sound and unusually robust.** Both rails are 100 µA into
`R_SET ‖ C_SET` with the fast-start circuit disabled by PGFB-to-IN, so each is
a clean exponential `V(t) = 100µ·R·(1 − e^(−t/RC))`:

| | R_SET | C_SET | τ | V(∞) | crosses 1.2 V | 90 % |
| --- | --- | --- | --- | --- | --- | --- |
| VCC(B) = `+3V3_CLK`, U6 | 33.2 k | 4.7 µF | 156 ms | 3.32 V | **70 ms** | 359 ms |
| VCC(A) = `+2V5`, U9 | 24.9 k | 10 µF | 249 ms | 2.49 V | **164 ms** | 573 ms |

Because τ_A > τ_B *and* V_A(∞) < V_B(∞), VCC(A) lags VCC(B) at **every
instant** — in absolute volts and as a fraction of final — so there is no
crossing to worry about, not merely a later 90 % point. The ordering inverts
only if τ_A/τ_B falls below **0.682**; it is **1.596**, a factor of 2.34. That
survives ±20 % on both capacitors *and* DC-bias derating on both at once. The
mechanism works and the choice of 10 µF is a good one.

(1.2 V is my assumed minimum operating supply for the part. I did **not** fetch
SCES576I, so that number is unverified — but the conclusion is insensitive to
it: the ordering holds for any threshold both rails can reach.)

**The coverage is the problem, and it is a direction question.** The two banks
run opposite ways:

| Bank | DIR | Direction | Outputs on | Powered by | Arrives |
| --- | --- | --- | --- | --- | --- |
| 1 | `1DIR` → GND | B → A | **A side** (`1A1`, element clock to the FPGA) | VCC(A) | **last** ✓ |
| 2 | `2DIR` → `+2V5` | A → B | **B side** (`2B1`/`2B2`, both oscillator enables) | VCC(B) | **first** ✗ |

For bank 1 the construction does exactly what is claimed: the output cannot
drive before VCC(A) exists, and VCC(A) is last. For bank 2 the output drivers
live on the side whose supply comes up *first*, so making VCC(A) late does not
delay them — it lengthens the window in which they are powered and enabled
while VCC(A), which controls what they should be driving, is between 0 V and
its minimum. That window is **70 ms to 164 ms, about 94 ms**, and the
deliberate 10 µF made it longer rather than shorter.

What sits on those two outputs is the thing that makes it worth writing down:
both CCHD-957 enables, on a **single shared `OSC_RAW` net that is only legal
while exactly one oscillator is enabled** — `interface.md` states that rule and
`output_module.py`'s own comment records that the module's 100 kΩ pull-downs
"are downstream of a push-pull output that can source milliamps, so they only
decide the case where the translator is itself high impedance."

I am **not** claiming a fault: `Ioff` / partial-power-down may cover a
partially-powered VCC(A), and SCES576I was not fetched, so the device's
behaviour in that region is exactly what I cannot answer. I am claiming the
remedy does not reach bank 2 and that nobody has checked whether it needs to.
Three ways to settle it, cheapest first: read SCES576I's Ioff and
power-sequencing sections; or move `2~OE` to a pull-up after all — it is
referenced to VCC(A), and `MUTE_N` has the wrong polarity, but `ID1`, already
strapped low on the module through 10 kΩ, is a spare the main board also pulls
low; or accept it and record why in `interface.md`, since the exposure is
bounded and happens once per power-up with the analog stage muted.

## 4.5 Nothing sees I/O before core, and nothing sees an out-of-window supply

Checked explicitly:

- **FT601Q**: VCCIO (2.5 V) at 4.9 ms, VCC33 at 8 ms. VCCIO leads by 3 ms,
  the same direction as before the C_SET fix and 85× smaller. `AVDD` is on
  `+1V0_FT`, the bridge's own internal LDO, not on +3V3 — verified from the
  netlist, and it is the fault that made `check_freshness.py` exist.
- **GateMate**: VDD (1.0 V) and VDDIO (2.5 V) both from the LTM4622, within
  microseconds of each other, and DS1001 states no ordering requirement.
- **LT3094**: its input (−6V_A) is up at 3.6 ms, long before MUTE_N can
  assert. If MUTE_N ever asserted first it would start into a rising input,
  which is slow rather than faulty.
- **U7 at start-up**: before the rail exists, VIN−PGND is 12 V, not 18 V, and
  FB sits at PGND so the part commands maximum duty — a normal start. The 3.8 V
  minimum operating input is cleared from the first millisecond.

The one check in my own suite that is weaker than it looks: **D-3 compares the
rail's arrival against a hard-coded 20 ms rather than against MUTE_N's own
time**, so moving MUTE_N to t = 0 does not move it. Tamper-tested and recorded
as a hole in my own work rather than quietly fixed, since fixing it changes
nothing about the design.

---

# Part 5 — The mezzanine

Both halves read out of the generated netlists and compared pin by pin. **They
agree exactly: all 80 pins, same net on both sides, no gaps.** The power and
ground allocation changed while this review was running, in response to §5.2
below; what follows is the current map.

| | pins | which |
| --- | --- | --- |
| element lines | 32 | odd 1–63 |
| ground | **38** | even 2–64, plus 71, 72, 75, 76, 78, 80 |
| MCLK | 1 | 65 |
| control | 5 | 66 OSC_EN_441, 67 OSC_EN_48, 68 MUTE_N, 69 ID0, 70 ID1 |
| **−6V_A** | 2 | **73, 74** — column 37, with full ground columns either side |
| +5V | **2** | 77, 79 |

## 5.1 The return path

38 ground pins for 28 switching lines, 32 of them interleaved one per element
line, which is the structure that matters. DC is trivial either way: +5 V
carries 123 mA out through 2 contacts and the −6 V rail carries 63.5 mA *in*
through 2, its return leaving through ground and partially cancelling, so net
DC in the ground pins is about 59 mA and every contact drop is sub-millivolt.
AC — 28 lines at 12.29 MHz — is a loop-area question and therefore layout's.

Two recorded facts rather than problems. **+5 V is now down to two contacts**,
from five before the negative rail and four after it: 61.5 mA per pin, and a
single failed contact leaves one pin carrying the module's whole 123 mA. That
is inside a 1.27 mm contact's rating with room, but the redundancy argument
both `power.md` files make from "five parallel header contacts" no longer
holds, and they still say five. And the arithmetic in `main_board.py`'s comment
and in 0015 — "37 of them ground … 35 remain" — was never right at any point in
this sequence: it was 36 before the rework and it is 38 now.

## 5.2 −6 V next to a logic input — found here, fixed

**Closed.** When this review started, the map put −6V_A at pins 71/72, which on
a 2×40 odd/even header is the column immediately beside 69/70 — ID0 and ID1,
two GateMate GPIO — and pins 65 to 70 contained **no ground pin at all**. One
bridge or whisker between pins 70 and 71 would have put −6 V onto a net
reaching a GateMate input through nothing but two 10 kΩ pull-downs, with the
input's clamp diode the only thing conducting and the bridge the only thing
limiting current.

The pair is now column 37 (pins 73/74) with complete ground columns at 71/72
and 75/76 on either side, and both netlists regenerate with all 80 pins still
agreeing. The reason for keeping the two −6 V pins adjacent *to each other* was
always sound and is retained: in the same column they mate simultaneously, so a
half-inserted connector cannot present one without the other.

## 5.3 What the two assertions can and cannot express

`assert_below_abs_max` is **one-sided**: `ABS_MAX_V = 2.75`, and every
comparison asks whether a net is one of the declared high-voltage rails. There
is no voltage sign and no lower limit anywhere in it.

`assert_core_rail` was added during this review and asks the complementary
question for supplies — a core ball may touch `+1V0` and ground and nothing
else, whatever the other net's voltage. Its construction is right, including
the part that took two attempts: it requires that **only** allowed names appear
in the net group rather than that an allowed name is *present*, which is the
distinction that matters because a short merges nets rather than replacing them,
so the core rail's own name survives every short. And it separately walks
two-terminal parts, because a resistive bridge does not merge the groups at all.

Four things neither assertion covers. The first is the one I would close next:

1. **The bridge's own core rail is not protected.** `assert_core_rail` is
   called with `protected=[fpga]` and `core_rails={"+1V0"}`. The FT601Q has a
   1.0 V core rail of its own — `+1V0_FT`, six bridge pins — and `AVDD` on it
   has a **1.4 V absolute maximum**. `main_board.py`'s own comment calls
   putting 3.3 V there "a destroy-the-part error", and it is an error this
   board has already made once. Extending the call to `[fpga, ftdi]` with
   `+1V0_FT` also needs `VD10`/`AVDD`/`DV10` added to `CORE_SUPPLY_NAMES`,
   which is a hardcoded tuple of GateMate ball names.
2. **No subject count is asserted.** `CORE_SUPPLY_NAMES` is matched by exact
   string. It currently finds 32 FPGA balls; if a symbol renames one, or a
   future part calls its core `VCORE`, the loop finds nothing, `core_groups`
   stays empty and the check passes. This is the third instance of the same
   failure mode in this repository — the `pinfunction` reader, `ldo_rails`'
   three silent skips (§1.1), and now this. **One assertion of "I expected N
   subjects and found N" in each of the three would close the whole class.**
3. **Only two-terminal bridges are walked.** `if len(pins) != 2: continue`
   skips a ferrite or filter symbol with four pins, a resistor network, and any
   transistor — all of which can tie a core ball to another rail.
4. **No absolute *minimum* is expressible by either.** With §5.2 fixed there is
   no live exposure, but the structure remains: if `-6V_A` ever reached a logic
   pin, the main board would catch it only because that rail happens to be
   declared in `hv_rails` — a positive-direction mechanism doing a
   negative-direction job — and the module **would not catch it at all**,
   because `-6V_A` is still absent from the module's `hv_rails` (PWR-S3).
   0014's own words for this are "an undeclared rail reaching a protected pin
   passes silently."

---

# Part 6 — Thermals, from computed dissipation

Not from either `power.md`. Every current here is the one computed in Part 2;
every thermal resistance is a fetched datasheet figure except D1's.

| Part | Dissipation | θJA | Rise | Junction at 25 °C amb |
| --- | --- | --- | --- | --- |
| F1 1812L050/30 | 48 mW | — | surface, not junction | 219 mA² × 1.0 Ω at R1max |
| D1 SS34 | 77 mW | 55 °C/W | 4.2 °C | 29 °C — VF assumed |
| U5 LMR33630 → +5V | 177 mW | 42.9 °C/W | 7.6 °C | 33 °C |
| **U7 LMR33630 → −6V** | **11 mW itemised / 67 mW from the datasheet curve** | 42.9 °C/W | **0.5 / 2.9 °C** | 28 °C |
| U3 LT3045 → +3V3 | **315 mW** at 185 mA (102 mW at 60 mA) | 34 °C/W | **10.7 °C** (3.5 °C) | 36 °C |
| U8 LT3094 → −5V_A | 62 mW | 34 °C/W | 2.1 °C | 27 °C |
| U14 LT3045 → +5V_A | 11 mW | 34 °C/W | 0.4 °C | 25 °C |

**Nothing is thermally interesting, and that conclusion is robust** — which is
worth saying plainly, because it is the one part of the power design that needs
no further work. Three caveats that belong in the record rather than in a fix:

- **U7's itemised loss is not credible and does not need to be.** I computed
  1.5 mW high-side I²R, 1.9 mW low-side, 1.9 mW inductor DCR, 0.4 mW quiescent
  and 7.7 mW switching — but Csw and Qg are assumed, and the datasheet's own
  efficiency curve reads about 85 % at 60 mA, which is 67 mW. Either way the
  rise is under 3 °C, and **any efficiency above 30 % keeps it under 38 °C**.
  `verify_power.py`'s assumed 85 % reaches the same answer; it is the right
  answer for the wrong reason, since at 6 % of rated current this part's loss
  is switching and quiescent rather than conduction.
- **U7's exposed pad is at −6 V.** Pin 1 is PGND and the thermal pad is AGND
  (table 6-1); both are correctly on `-6V_A`, which is what the ±0.3 V
  AGND-to-PGND absolute maximum demands. The consequence is that U7's only
  thermal path is a −6 V copper island, not the ground plane — and table 7.4's
  42.9 °C/W is a 4-layer JEDEC number the datasheet **explicitly forbids using
  for design**. At 67 mW this survives any plausible island. It would not
  survive someone later raising this rail's load, and there is nothing in the
  repository that would notice.
- **U3's row is the unresolved one.** 315 mW or 102 mW depending on which
  document you believe (§2.2). Both are fine thermally. The 500 mA part is not
  stressed either way. But `verify_power.py` reports the smaller figure while
  the board's own page implies the larger, and no check compares them.

The LTM4622's two channels I did not compute: its efficiencies are `ASSUMED`
in `verify_power.py`, its RUN and feedback figures reach this repository through
a review rather than a datasheet, and its land pattern has just been found
transposed. It wants its own datasheet pass, which this review did not do.

---

# Part 7 — Which constants are datasheet-verified and which are assumed

**Fetched and read for this review**, values quoted with their table:

| Datasheet | Used for |
| --- | --- |
| **LMR33630**, TI SNVSAN3F rev F, Nov 2020 | tables 6-1 (pin functions, PGND on pin 1 and AGND on the pad), 7.1 (all absolute maxima), 7.3 (3.8–36 V, PG 0–18 V), 7.4 (42.9 °C/W, DDA, with its own warning), 7.5 (VFB 0.985/1.000/1.015, fSW 340/400/460 kHz for the "A" version, ISC 3.85/4.5/5.05 A, RDS-ON 95/66 mΩ, tSS 2.9/4/6 ms, IQ 24 µA), 7.6 (tON-MIN **75/108 ns for DDA**, tOFF-MIN 50/85 ns, IPEAK-MIN 0.69 A, IZC −0.106 A), 7.7 (tD 2 ns), 9.2.2.5–6 (COUT and the required CIN), Device Information (HSOIC-8, 5.00 × 4.00 mm) |
| **LT3045**, Linear 3045f | EN/UV trip 1.18/1.24/1.32 V; **dropout 220 typ / 275 max / 330 over temperature at I_LOAD = 1 mA and 50 mA**; IN ±22 V; ILIM pin −0.3 to 1 V; minimum output capacitor 10 µF; DD package θJA 34 °C/W with **the exposed pad as GND** |
| **LT3094**, ADI Rev 0 | SET 100 µA ±1 %; **ILIM scale factor 3.75 kΩ·A**, so 24.9 k = 151 mA; EN/UV ±1.20/1.26/1.33 V **referenced to GND, bidirectional**; IN −22 V to +0.3 V; dropout 235 mV; shutdown IQ 3 µA; DD θJA 34 °C/W with **the exposed pad as IN** |

Verified consequences worth naming: the LT3094's EN/UV really is
ground-referenced and bidirectional, so `MUTE_N` at 2.5 V enables it and 0 V
shuts it down — the netlist's claim is correct. Its ILIM at 24.9 k really is
151 mA. Both exposed pads are on the correct net in the netlist, which for the
LT3094 means IN (−6V_A) and not ground — an easy one to get wrong and it is
right.

**Assumed, and used anyway** (each marked in the code):

| Constant | Why |
| --- | --- |
| adapter 12 V ±5 %, and 19 V as the plug-in fault | the adapter is unchosen — out of scope by instruction |
| D1 VF = 0.35 V | read off a curve; not a spec limit. It sets the buck's input headroom and D1's 77 mW |
| L2 DCR = 43 mΩ | the BOM's 744314100 is itself marked UNVERIFIED |
| SW node capacitance 60 pF, gate charge 3 nC | my own switching-loss estimate; superseded by the datasheet curve |
| PCB/package inductance 1.5–4 nH, cap ESR 5 mΩ, ESL 2 nH | the commutation result's *magnitude* depends on these; its *conclusion* does not, since the plane-return share is 100 % at any value |
| I_3V3, I_2V5, I_1V0 | unresolved between two documents, §2.2 |

**Not fetched, and therefore not cleared by this review**: SS34, SMAJ18A and
the 1812L050/30 (all read in full by `power_input_transient.py`, whose numbers
I used without re-verifying); FT601Q VCC33 current; GateMate DS1001; LTM4622;
OPA1612; SN74ALVCH16374 and 74AVC4T245 input-current-with-VCC-low, which is
what §4.2 turns on.

One attribution error I did notice without a fetch: `power_input_transient.py`'s
`D2_ALPHA = 0.088 %/°C` is annotated *"%/C column of the **SMAJ15A** row"* and
is applied to an SMAJ18A. The tempco column varies with standoff voltage in the
Vishay table, and the file's own tamper shows that this single constant is the
entire difference between a part that survives the 19 V case and one that does
not. It should be re-read from the 18 V row.

---

## Cross-section flags

Every inconsistency this review found between the documentation, the schematic
as generated, and the checks. Each is tagged, says which side I believe, and
names the file and place. The netlists are treated as the authority on what is
built; `hardware/lyrebird-*/​*.net` is what I actually read.

### Schematic — the netlist itself

Three of these were closed while the review was running, and they are kept
because the reconciling agent needs to know they were real and are now
resolved, not silently dropped.

| Tag | Where | What |
| --- | --- | --- |
| **PWR-S1** | `main_board.py`, U5 and U7 footprints | Footprint `Package_SO:HTSSOP-8-1EP_3x3mm_P0.65mm_EP1.5x2.1mm` on an HSOIC-8 part. The datasheet's Device Information gives HSOIC (8), 5.00 × 4.00 mm; the KiCad symbol's own `fplist` names `Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm_ThermalVias`. A 0.65 mm-pitch 3 × 3 land cannot take a 1.27 mm-pitch 5 × 4 body. **Build-stopping.** Same class as the LTM4622 land-transposition found this round; that makes two footprint faults in the power tree. |
| **PWR-S2** | `main_board.py`, U7's input | **CLOSED during this review.** There was no capacitor from +12 V to −6V_A; U7's PGND *is* −6V_A, so SNVSAN3F 9.2.2.6's "minimum of 10 µF … required on the input" and pin 2's "directly to this pin and PGND" were unsatisfied. Measured: 100 % of the 0.69 A switch transition returned through the ground plane with 7.6 V across the pin pair. 10 µF + 100 nF is now fitted: 91 % local, 9 % plane, 2.6 V. **Residual:** the remaining 9 % and 2.6 V are set by loop inductance, so placement of these two parts is now a layout obligation, and it is the one place on either board where that is load-bearing for the analog ground. |
| **PWR-S3** | `output_module.py`, the module's `assert_below_abs_max` call | `hv_rails` omits `-6V_A` — the board's most dangerous net is invisible to `assert_below_abs_max` on the module side — and still declares four nets deleted with the charge pump: `PUMP_P`, `PUMP_N`, `+5V7_A`, `-5V7_A`. 0014 records this exact mechanism in its own words. |
| **PWR-S4** | `lyrebird_parts.py`, both assertions | Neither can express an absolute **minimum**. `assert_below_abs_max` has `ABS_MAX_V = 2.75` and no sign anywhere; `assert_core_rail` asks which net, not how negative. With PWR-S5 closed there is no live exposure, but if `-6V_A` ever reached a logic pin the main board would catch it only because that rail happens to be declared in `hv_rails` — a positive-direction mechanism doing a negative-direction job — and the module would not catch it at all (PWR-S3). |
| **PWR-S5** | mezzanine pin map, both boards | **CLOSED during this review.** −6V_A sat at pins 71/72, the column immediately beside 69/70 (ID0/ID1), with **no ground pin anywhere in pins 65–70**; one bridge between 70 and 71 would have put −6 V onto a GateMate GPIO through nothing but two 10 kΩ pull-downs. The pair is now column 37 (73/74) with full ground columns at 71/72 and 75/76, both netlists regenerated, all 80 pins still agreeing across the connector, and the half-inserted-connector reasoning for keeping the pair adjacent to itself correctly retained. |
| **PWR-S6** | `output_module.py`, U14 SET = 40.2 k | **CLOSED.** Independently rechecked across the full stack: dropout bound +433 mV (rail low corner 4.863 V, U14 high corner 4.100 V at the LT3045's 102 µA SET maximum, against 330 mV of over-temperature dropout) and swing bound +510 mV (U14 low corner 3.940 V against the 3.43 V the ±2.83 V output needs). The intermediate 45.3 k had only 3 mV on the dropout bound. **Side effect, still open:** widening U14's SET resistance from 45.3 k to 40.2 k moved its ramp from 511 ms to 455 ms while U8 stayed at 561 ms, so the two op amp rails now arrive **106 ms apart** rather than 51 ms, into a jack with no DC blocking (open item D10). |
| **PWR-S7** | both `bom.csv` | U5 and U7 rows carry the wrong footprint in the Package column *and* are marked **VERIFIED**. Separately, **no capacitor in either BOM carries a voltage rating or dielectric** — they are grouped by value alone — on a 12 V rail whose TVS clamps at 29.2 V, where the datasheet asks for "at least the maximum input voltage, preferably twice". |
| **PWR-S8** | `output_module.py`, translator OE and U9's SET capacitor | **Verdict on the ramp claim: the arithmetic holds, and robustly.** Both rails are 100 µA into `R_SET ‖ C_SET` with fast-start disabled by PGFB-to-IN, so each is an exponential; VCC(A) reaches a 1.2 V minimum at **164 ms** against VCC(B) at **70 ms**, and because τ_A > τ_B *and* V_A(∞) < V_B(∞), VCC(A) lags at **every instant** rather than merely at the 90 % mark. The order inverts only if τ_A/τ_B falls below 0.682 against 1.596 fitted — a factor of **2.34**, which survives ±20 % on both capacitors and DC-bias derating on both at once. The 10 µF choice is a good one. **But it protects only bank 1**, whose outputs are on the A side. Bank 2 has `2DIR` high, so it runs A→B and its outputs sit on the **B side, powered by the rail that arrives first**; the deliberate delay lengthens rather than shortens the ≈94 ms window in which those drivers are powered and enabled while VCC(A) is between 0 V and its minimum. Both CCHD-957 enables are on those outputs, sharing one `OSC_RAW` net that is only legal with exactly one part enabled. Not shown to be a fault — SCES576I was not fetched and `Ioff` may cover it — but the remedy does not reach this bank and the comment in `output_module.py` reads as though it covers both. |
| **PWR-S9** | `lyrebird_parts.py`, `assert_core_rail` | Correctly built — requiring that *only* allowed names appear rather than that an allowed name is present is the distinction that makes it work at all, since a short merges nets rather than replacing them. Three scope gaps: **(a)** it is called with `protected=[fpga]`, so the **FT601Q's own 1.0 V core rail is unprotected** — `+1V0_FT`, six pins, with `AVDD`'s 1.4 V absolute maximum on it, and `main_board.py` calls putting 3.3 V there "a destroy-the-part error" this board has already made once; extending to `[fpga, ftdi]` also needs `VD10`/`AVDD`/`DV10` added to the hardcoded `CORE_SUPPLY_NAMES`. **(b)** No subject count is asserted: `CORE_SUPPLY_NAMES` is matched by exact string, so a renamed ball leaves `core_groups` empty and the check passes. **(c)** `if len(pins) != 2: continue` skips ferrites, resistor networks and transistors as bridges. |
| **PWR-S10** | mezzanine +5 V allocation | +5 V is now on **two** pins (77, 79), from five before the negative rail and four after it: 61.5 mA per contact, and a single failed contact leaves one pin carrying the module's whole 123 mA. Inside a 1.27 mm contact's rating with room, but the redundancy argument both `power.md` files draw from "five parallel header contacts" no longer holds — see PWR-M6 and PWR-A6. |

### Decision records 0014 and 0015 versus what is built

0014 has been substantially corrected since this review started — the TVS is
now recorded as 18 V, the "what this did not do" section is reconciled, and the
missing record for what everything called "decision 5" now exists as **0015**.
What is left:

| Tag | Where | What |
| --- | --- | --- |
| **PWR-D1** | `0014`, "Why 12 V and not 5 V" | "That second stage **is not built yet** — see 'What this does not yet do'." 0015 built it, and the section it points at has since been retitled "What this did not do, and what has since". One sentence, and the only place in 0014 still asserting the inverter is unbuilt. |
| **PWR-D2** | `0014`, Decision | "everything downstream of +5V is unchanged — the LTM4622, the LT3045 and **the mezzanine** all see the rail they were designed against." The mezzanine now carries −6 V on two pins taken from the ground and +5 V allocations. 0015 supersedes it, so an amendment marker is enough. |
| **PWR-D3** | `0014`, "What this did not do" | "**The isolator is not fitted.** Still true. The SuperSpeed pairs **are routed**…" The isolator half is still true; the SuperSpeed half is not — `grep -c 'SSTX\|SSRX'` over `lyrebird-main.net` returns 0, so the pairs are gone and the hardest constraint in the main board's layout went with them. One bullet, now stale in the opposite direction from the rest of its own section. |
| **PWR-D4** | `0014`, the `hv_rails` paragraph | Lists `+12V`, `VIN_RAW` and `VIN_FUSED` as declared, and states the mechanism — "an undeclared rail reaching a protected pin passes silently" — as a general lesson. `-6V_A`, the rail 0015 went on to introduce, is declared on the main board and **not on the module** (PWR-S3). The paragraph should name it. |
| **PWR-D5** | `0015`, the Decision list | "Two mezzanine pins, **taken from the ground allocation**. All 80 were assigned, **37** of them ground for 28 switching lines; **35** remain." Wrong at every stage of the sequence: before the §5.2 rework the netlist had **36** ground and 4 of +5 V (one pin came from the +5 V allocation, not from ground, because taking 71/72 shifted the alternating tail's parity); after it there are **38** ground and **2** of +5 V. Same arithmetic error as PWR-C3 — the two texts share it — and now also the wrong pin numbers, since the pair moved to 73/74. |
| **PWR-D6** | `0015`, Decision and Consequences | "An LT3045 takes the header's 5 V to **+4.53 V**" and "It is **45.3 kΩ and 4.53 V** now." The netlist is **40.2 kΩ / 4.02 V** — 45.3 k was an intermediate value that had 3 mV of margin on the dropout bound at the tolerance corner (PWR-S6). |

### `main_board.py` comments versus `main_board.py` output

| Tag | Where | What |
| --- | --- | --- |
| **PWR-C1** | `main_board.py:157–159` | "That part is not built yet: the mezzanine still carries +5V and the module still has its charge pump" — U7, the inverter it is describing as unbuilt, is 60 lines further down the same function. |
| **PWR-C2** | `main_board.py`, MUTE_N pull-down note | "MUTE_N … is a direct input to the charge pump's enables rather than a translator input." The charge pump is deleted; MUTE_N now drives U14's and U8's EN/UV. |
| **PWR-C3** | `main_board.py`, mezzanine power allocation | "Two pins … taken from the ground allocation. 37 returns for 28 switching lines is generous; 35 still is." The netlist now has **38** ground pins and **2** of +5 V, and before the §5.2 rework it had 36 and 4 — never 37 or 35. The conclusion (generous) survives; the arithmetic never did, and the comment also needs the new pin numbers. |

### `output_module.py` comments versus `output_module.py` output

| Tag | Where | What |
| --- | --- | --- |
| **PWR-C4** | `output_module.py`, the LT3094 block | A full paragraph about "the inverting pump's output", "LDO− is a 50 mA part", "the doubled-then-inverted rail … at the bottom of the USB range". None of those parts or constraints exist. |
| **PWR-C5** | `output_module.py`, LT3094 ILIM note | "151 mA … well above the **22 mA** this rail carries and below what the pump's LDO can deliver into a fault." This rail carries **63.5 mA** worst case — 22 mA is the *positive* rail's figure — and there is no pump. The 151 mA value itself is correct and datasheet-verified. |

### `lyrebird-main-reva/power.md`

| Tag | Where | What |
| --- | --- | --- |
| **PWR-M1** | opening line | "Bus powered, no external input ([0009])". The board is externally powered from 12 V; 0009 is superseded. |
| **PWR-M2** | "Where the boundary sits" | "+5 V pins … J2 pins 71, 73, 75, 77 and 79". The netlist says **77 and 79** — two pins. 71/72 and 75/76 are ground and 73/74 are `-6V_A`. Also "downstream of the VBUS ferrite", which no longer supplies anything. |
| **PWR-M3** | same section | "The header carries **unregulated bus voltage and ground, and no other rail**." It carries a regulated 5.016 V from a buck, and it carries −6 V. |
| **PWR-M4** | rail table | +3V3 at **185 mA**, +2V5 at **15 mA**, +1V0 at **149 mA** against `verify_power.py`'s 60 / 90 / 80 mA. Reflected to +5 V these give 231 mA and 136 mA respectively, while both files state a 234 mA subtotal. Unresolved; needs the FT601Q's VCC33 figure from its datasheet. |
| **PWR-M5** | "12 V input" summary block | "against **6.3 J** to trip F1" — `power_input_transient.py` computes **31.9 J** from the same model it cites. |
| **PWR-M6** | "Totals at the input" | "**Five** parallel header contacts at 20 mΩ drop 2 mV at 123 mA" — **two** contacts now, and the drop is 1.2 mV. See PWR-S10: the redundancy this sentence implies is gone. |
| **PWR-M7** | "What has no source today" (final section) | Claims the LTM4622 is absent from `main_board.py`, that +2V5 and +1V0 "exist as nets with loads and no regulator", that the VBUS ferrite is absent and that there is no USB connector. **All four are false** — the netlist has U4 sourcing both rails, and `open-items.md` records the gap as closed. Delete the section. |
| **PWR-M8** | Margin table | "F1 hold at 70 °C / 330 mA / 219 mA" omits the **305 mA** peak while both converters soft-start simultaneously. Not a trip risk (a PPTC integrates over seconds) but the table's own criterion is nearly met. |

### `lyrebird-dac-reva/power.md`

| Tag | Where | What |
| --- | --- | --- |
| **PWR-A0** | rail table (line 41) and the op amp rail paragraph (line 55) | `+5V_A` given as **+4.53 V** with "U14 is programmed to +4.53 V, which leaves 3.93 V of swing". The netlist is 40.2 kΩ, i.e. **4.02 V**, leaving 3.42 V of swing against the 2.83 V needed. Same stale value as PWR-D6. |
| **PWR-A1** | opening line | "regulates its own rails from the +5 V the main board hands it ([0009], interface.md)". The negative rail arrives pre-inverted at −6 V; `interface.md` already documents that. |
| **PWR-A2** | "Where the boundary sits" | "J1 pins 71, 73, 75, 77 and 79 … **five pins** of unregulated bus voltage downstream of the main board's VBUS ferrite" and "**Nothing else crosses.**" Two pins (77, 79); regulated from a buck, not bus voltage; and −6V_A crosses on 73/74. |
| **PWR-A3** | "Reflected to the USB input, and margin" | Still reads main 234 + module **238** = **472 mA**, with USB 3.0/2.0 utilisation tables and "the USB 2.0 line is no longer comfortable … 94 %". The same page's own totals are 123 mA of +5 V and 64 mA of −6 V. 0014 retired the whole budget. |
| **PWR-A4** | "Against 0009's budget" | Module subtotal **238 mA**, from the same retired era. |
| **PWR-A5** | "What is still uncertain here" | Two rows are about the deleted charge pump: "3 mA of pump quiescent" and "4.43 V at the header … it decides whether the charge pump is inside its input range". |
| **PWR-A6** | "Headroom at the worst input" | "**five** parallel header contacts" — two; and the paragraph reasons from a 5.02 V header without the tolerance spread that made the earlier U14 value marginal (PWR-S6, PWR-V16). |
| **PWR-A7** | "The op amp rails" / open item D10 | The page treats MUTE_N gating as an open audio question with no numbers. It now has numbers: 511 ms of ramp on `+5V_A`, 561 ms on `-5V_A`, and **51 ms of asymmetry** between them into a jack with no DC blocking. |

### The checks, as documentation of the circuit

| Tag | Where | What |
| --- | --- | --- |
| **PWR-V1** | `verify_power.py`, `ldo_rails` | Three silent-skip paths, each tamper-demonstrated: a SET value spelled in ohms rather than kilohms, an IN rail not in the two-entry `known` dict, or a part whose `value` string loses the family name — each drops a regulator and reports "17/17 checks pass". **Assert the subject count: the design has six post-regulators.** |
| **PWR-V2** | `verify_power.py`, `U3_DROPOUT` | **Closed.** Now 0.330 V, "LT3045 max at 1-50 mA, not the 500 mA figure", which matches 3045f. It is still applied to U8, an **LT3094** whose own figure is 235 mV — conservative, so harmless, but it is the wrong part's number. |
| **PWR-V16** | `verify_power.py`, `V5_TOL_LO = 0.0157` | Annotated "LMR33630 VFB 0.985 V min **with 1 % divider**", but 1.57 % is the feedback tolerance alone. With 1 % on both 100 k and 24.9 k the ratio spreads to 3.9366–4.0972, so the rail's real low corner is **4.863 V (−3.06 %)**, not 4.941 V. Every corner check is therefore about 79 mV optimistic. No verdict changes — U14 has +432 mV rather than the reported +511 mV — but the constant does not do what its own note says. |
| **PWR-V17** | `verify_power.py`, the dropout loop | `vin_lo = abs(vin) * (1 - V5_TOL_LO.value)` inside the loop **rebinds the function-scope `vin_lo`** that the summary banner prints afterwards. A passing run now reports **"Input 4.9 to 12.6 V at the jack"** — the +5 V rail's low corner presented as the adapter voltage. No verdict is affected (the checks using the outer `vin_lo` run before the loop), but the file's headline output is wrong. |
| **PWR-V3** | `verify_power.py`, FT601Q skew check | The only check no perturbation of any constant can flip. Its two inputs, 33.2 k and 100 nF, are bare literals in a `ramps` list rather than `Fact`s, and the threshold is 6.6× the value. `power_input_transient.py`'s S-2 tests the same property properly and does fail on the C_SET tamper. |
| **PWR-V4** | `verify_power.py`, TVS clamp check | Compares 29.2 V to 36 V and reports 6.8 V of margin. For U7 the stress is `V_clamp + \|Vout\|` = **35.18 V**, leaving 0.82 V against the recommended maximum — and U7 is not in the check. |
| **PWR-V5** | `verify_power.py`, inverter current check | Compares 63.5 mA to 0.3 × 3 A. The 3 A does not apply in inversion: the topology limit is `(I_SC − ΔI_L/2)(1 − D)` = **2.21 A**. Right verdict, wrong number. |
| **PWR-V6** | `verify_power.py`, `I_3V3` note | "FT601Q VCC33 + flash" — the flash (U6) is on **+2V5**, verified from the netlist. |
| **PWR-V7** | `power_input_transient.py`, `F1_NETLIST_VALUE` | Still `"1.1 A hold, 2.2 A trip"`, printed at the top of every run as *"NOTE: main_board.py says …"* with a warning that no 1812L part matches. `main_board.py` says `1812L050/30 PPTC 0.5A hold 30V 100A`. A passing run emits a false warning about a fault that was fixed. |
| **PWR-V8** | `power_input_transient.py`, load constants | `I_LOAD_5V = 0.472 A` sourced to "verify_power.py: 238 mA module + 234 mA main" (now 357 mA, 123 mA module) and `I_MEZZ = 0.238 A`, which sets `Rmezz`, the load the sequencing model actually drives. |
| **PWR-V9** | `power_input_transient.py`, docstring | "all twelve of its checks pass" (now 18); the ASCII art still shows `D2 SMAJ15A`; scenario 4 still promises "the WAKEUP_N core gating that 0014 says was retired **and the netlist still builds**" — the netlist has not built it for two rounds, and the model is correctly ungated by default. |
| **PWR-V10** | `power_input_transient.py`, `D2_ALPHA` | 0.088 %/°C annotated "%/C column of the **SMAJ15A** row", applied to an SMAJ18A. That column varies with standoff voltage, and the file's own tamper shows this one constant is the entire difference between surviving the 19 V case and not. |
| **PWR-V11** | `power_input_transient.py`, F1 thermal model | `F1_TTRIP_8A` is assigned twice (0.15 s then 0.50 s, both marked `datasheet`); the comment block above derives τ from "I_hold = 1.10 A", the superseded part; and the fitted τ = 128 s implies C_th = 0.30 J/K for an 1812 body, an order of magnitude high. No verdict in the file depends on τ — every trip verdict is decided by current being below the hold current — so this is a record, not a fix. |
| **PWR-V12** | `power_input_transient.py`, S-4 | "the core rail does not start and then collapse" is `glitch_peak < 0.05 or t90 is not None`. Demonstrated: a rail that reaches 998 mV at 4.9 ms and collapses to 0 V at 40 ms passes S-1, S-3, S-4 and S-6 together. |
| **PWR-V13** | `power_input_transient.py`, S-6 | The verdict is computed from the no-host run; the detail string prints `rows_h['+1V0']['peak']` from the host run. Latent mismatch between verdict and evidence. |
| **PWR-V14** | both checkers, netlist parsing | Both split on the bare token `(comp`, which also matches `(component_classes)` inside every component block. The final fragment runs into the nets section and takes the first node's ref with no value, so `verify_power.py` carries `val["C8"] = ""` (main) and `val["C36"] = ""` (module). Harmless only because neither is a SET resistor. |
| **PWR-V15** | both checkers, scope | Neither can express "does this rail reach the right ball of the right package". Rails are strings and voltages are constants. That assumption has now failed twice in the power tree — the LTM4622 land, and PWR-S1. |

### Open questions this review could not close

| Tag | What |
| --- | --- |
| **PWR-O1** | The +3V3 / +2V5 / +1V0 currents (PWR-M4). Needs the FT601Q datasheet and a GateMate figure that depends on a bitstream. |
| **PWR-O2** | Bitstream load time against the module's 361–574 ms rail ramps (§4.2). Nothing on either board sequences this; `MUTE_N` is an FPGA output and the module returns no power-good. Cutting C_SET is no longer freely available as a remedy: `+3V3_REF` must keep 4.7 µF for the noise specification, `+2V5` must stay slow for PWR-S8's ordering, and cutting `+3V3_CLK` breaks that ordering from the other side. The sequencing is now load-bearing in two directions, which anyone tuning one of these capacitors needs to know. |
| **PWR-O3** | SN74ALVCH16374 and 74AVC4T245 input current with VCC below the driven input level, and the 74AVC4T245's `Ioff` behaviour with VCC(A) *partially* powered. Datasheets not fetched; PWR-O2's and PWR-S8's severity both turn on these. |
| **PWR-O4** | Loop stability of U7. The LMR33630's compensation is internal and specified for buck operation; the inverting plant has a right-half-plane zero (about 2 MHz at this light load, but 64 kHz at 2 A). TI's inverting application note is the authority and the design cites none. Benign at 63.5 mA; not transferable if this rail's load grows. |
| **PWR-O5** | LTM4622: efficiencies `ASSUMED`, RUN and feedback figures reaching the repo through a review rather than a datasheet, and a land pattern just found transposed. Wants its own datasheet pass, which this review did not do. |

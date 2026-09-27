# Power design review — 12 V wall wart, two boards

Reviewed 2026-09-25/26 against `hardware/netlist/main_board.py`,
`hardware/netlist/output_module.py` and the generated
`lyrebird-main.net` / `lyrebird-dac.net`, which are the authority used
throughout: where a Python comment and the generated netlist disagree, the
netlist wins and the disagreement is a flag.

Two things are out of scope by instruction and are not reported as faults: the
adapter is unchosen so its tolerance is assumed, and the reference-rail
transition-current item is signal integrity rather than supply.

## Verdict

The architecture is sound and the inverting converter is, against expectation,
wired correctly — the feedback referencing, the enable, the bootstrap, the
inductor return and the exposed-pad assignment are all right, and I verified
each against the LMR33630 datasheet rather than against the comment beside it.
Three things are wrong and one of them stops a build:

| | |
| --- | --- |
| **B-1** | Both LMR33630s carry a footprint for the wrong package: `HTSSOP-8 3x3 P0.65mm` against an HSOIC-8, 3.9 × 4.9 mm, 1.27 mm pitch. The KiCad symbol's own `fplist` names the right one. Nothing in either check suite looks at footprints. |
| **B-2** | U7 has **no input capacitor**. Its PGND is the −6 V rail, so the datasheet's "minimum of 10 µF ... directly to this pin and PGND" means +12 V to −6V_A, and the only capacitors fitted are +12 V to system ground. The high-side commutation loop is closed through two capacitors in series and the ground plane — on a board whose entire premise is a quiet ground. |
| **B-3** | The +5 V rail's tolerance is nowhere accounted for. `verify_power.py` and both `power.md` files use 5.02 V as if it were exact; the LMR33630's own feedback tolerance (±1.5 %, datasheet 7.5) plus the 1 % divider puts it at **4.86 V to 5.17 V**. Every module dropout margin is computed from the nominal, and U14 — just moved to 4.53 V — has 330 mV at the low corner against a 330 mV over-temperature dropout maximum. |

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

- **U14 (+5V_A, just moved to 45.3 k / 4.53 V).** Headroom at nominal is
  490 mV. At the low corner it is **4.863 − 4.530 = 333 mV**, against an
  LT3045 dropout of 220 mV typical, 275 mV maximum and **330 mV over
  temperature at this load** (3045f, I_LOAD = 1 mA and 50 mA rows). That is
  3 mV of margin at the corner. The fix was in the right direction and did
  not go far enough; 43.2 k (4.32 V) buys 213 mV more and the stage needs only
  about 3.5 V.
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

## 3.6 The one real defect: U7 has no input capacitor

`caps_between()` over the generated netlist:

    +12V to GND      22.10 uF     <- U5's input capacitor
    +12V to -6V_A     0.00 uF     <- U7's input capacitor
    GND  to -6V_A    47.10 uF     <- U7's output capacitor

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
| as built | **7.6 V** | **690 mA (100 %)** | — |
| + 2.2 µF 0603 at the pins | 2.6 V | 63 mA (9 %) | 627 mA (91 %) |

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

**Fix:** 10 µF + 220 nF, or at minimum a 2.2 µF X7R 0603 rated 50 V, from
+12 V to −6V_A, placed at U7's pin 1 and pin 2. It is one BOM line and it is
the single highest-value change in this review.

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
| **+2V5 (module)** | 13.4 ms | **271 ms** | U9, 24.9 k × **4.7 µF** |
| **+3V3_CLK** | 17.5 ms | **361 ms** | U6, 33.2 k × 4.7 µF |
| **+3V3_REF** | 17.6 ms | **362 ms** | U5, 33.2 k × 4.7 µF |
| **+5V_A** | 42.5 ms | **511 ms** | U14, 45.3 k × 4.7 µF, gated by MUTE_N |
| **−5V_A** | 44.7 ms | **561 ms** | U8, 49.9 k × 4.7 µF, gated by MUTE_N |

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
  **271 ms**.

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
or cut C_SET on `+2V5` and `+3V3_CLK` as the main board's U3 already was (the
reference rail must keep its 4.7 µF — that capacitor buys the 0.8 µV RMS the
whole design leans on, so it is the one rail where the ramp is the price of the
specification); or hold the element outputs in the bitstream until a timer
expires.

## 4.3 The two analog rails do not arrive together

`+5V_A` reaches 90 % at 511 ms and `−5V_A` at 561 ms — **51 ms apart**, because
their SET resistors differ (45.3 k against 49.9 k) while their C_SET does not.
Both are gated by the same MUTE_N and both inputs are already established, so
this is not a supply fault: the OPA1612 tolerates ±2.25 V to ±18 V and 36 V
total, and asymmetric rails are an undefined-output condition rather than a
damage one.

It matters because **the jack has no DC blocking.** For 51 ms the six
amplifiers have a positive rail and essentially no negative one, their outputs
are undefined, and that reaches the line output directly. This is the concrete
content of open item D10 — "collapsing the supplies is a blunt mute and every
assertion is a transient into an unblocked output". Now it has a number:
51 ms of asymmetry on every unmute, plus the 511 ms ramp itself.

## 4.4 Nothing sees I/O before core, and nothing sees an out-of-window supply

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
agree exactly: all 80 pins, same net on both sides, no gaps.**

| | pins | which |
| --- | --- | --- |
| element lines | 32 | odd 1–63 |
| ground | **36** | even 2–64, plus 74, 76, 78, 80 |
| MCLK | 1 | 65 |
| control | 5 | 66 OSC_EN_441, 67 OSC_EN_48, 68 MUTE_N, 69 ID0, 70 ID1 |
| **−6V_A** | **2** | **71, 72** |
| +5V | **4** | 73, 75, 77, 79 |

## 5.1 The return path is adequate, and the comment describing it is wrong

`main_board.py` says *"Two pins for the negative analog rail, taken from the
ground allocation. 37 returns for 28 switching lines is generous; 35 still
is."* The netlist says **36**, and one of the two pins came from the +5 V
allocation, not from ground: pins 71 and 72 were previously 71 (+5V) and 72
(GND) in the alternating tail, and taking them shifted the tail's parity so
+5V went from 5 pins to 4 and ground from 37 to 36. Arithmetic in the comment,
not in the circuit.

The conclusion survives. DC: +5 V carries 123 mA out through 4 contacts
(31 mA each) returning through 36; the −6 V rail carries 63.5 mA *in* through
2 contacts and its return goes *out* through ground, partially cancelling, so
net DC in the ground pins is about 59 mA. At 20 mΩ per contact that is
sub-millivolt everywhere. AC is the real question — 28 lines at 12.29 MHz — and
36 returns interleaved one-per-line for the first 32 is the right structure;
what matters beyond that is loop area, which is layout.

## 5.2 A −6 V rail sits one column from a 2.5 V logic input, with no ground between

On a 2×40 odd/even header, pins 2k−1 and 2k share column k. So:

    column 35 = pins 69, 70   ID0, ID1        2.5 V logic, GateMate GPIO
    column 36 = pins 71, 72   -6V_A, -6V_A
    column 37 = pins 73, 74   +5V, GND

The whole control block, pins 65–70, has **no ground pin in it** — MCLK, two
oscillator enables, MUTE_N and both ID straps sit in three adjacent columns
with returns only at either end — and the column immediately beside ID1 is now
−6 V. On a 1.27 mm header, one bridge or one whisker between pins 70 and 71
puts −6 V onto a net that reaches a GateMate GPIO through nothing but two 10 kΩ
pull-downs. The input's clamp diode to ground conducts and the current is
limited only by the bridge.

Putting the −6 V pair *adjacent to each other* is well reasoned — the netlist
comment is right that a half-inserted connector then cannot present one without
the other. Putting them next to the ID straps is not. Moving the pair into the
alternating tail, flanked by ground (e.g. 75/76 with 73/74 and 77/78 as
ground), costs nothing and is a pin-map change rather than a circuit change.
It does change `interface.md` and both netlists, so it is a decision, not a fix.

## 5.3 The absolute-maximum assertion cannot see this, in two separate ways

`assert_below_abs_max` is the guard that exists precisely because both boards
have shipped a rail onto a pin rated lower. It is **one-sided**: `ABS_MAX_V =
2.75` and every comparison asks whether a net *is* one of the declared
high-voltage rails. There is no voltage sign, no lower limit, and no concept of
a negative rail anywhere in it. The design now carries a rail 20× outside a
protected pin's negative absolute minimum and the guard is structurally unable
to express the question.

Beyond that, the two boards declare different rails:

- **main board**: `hv_rails` includes `-6V_A`, and `protected` lists
  `mez: {"+5V", "-6V_A"}` — so a stray `-6V_A` on an *FPGA* pin would be
  caught (the FPGA is allowed nothing), which is the important half.
- **module**: `hv_rails = {"+5V", "+3V3_CLK", "+3V3_REF", "+5V_A", "-5V_A",
  "PUMP_P", "PUMP_N", "+5V7_A", "-5V7_A"}` — **`-6V_A` is absent**, so on the
  module the most dangerous net on the board is invisible to the check, and
  four of the nine declared rails (`PUMP_P`, `PUMP_N`, `+5V7_A`, `-5V7_A`)
  belong to the deleted charge pump and no longer exist.

Decision 0014 records this exact mechanism in its own words — *"the overvoltage
assertion is blind to any rail it is not told about: an undeclared rail
reaching a protected pin passes silently"* — and the module's copy has been
left in that state for the rail the decision itself introduced.

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


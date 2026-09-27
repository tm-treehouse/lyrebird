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


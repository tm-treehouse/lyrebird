# Reconciliation — 2026-09-25 review round

Three validators each read one section and flagged what they believed crossed
into the others. Nobody checked those flags against each other. This document
does that, and only that: it is not a fourth review. Its subject is the
128 cross-section flags in

- [`documentation.md`](documentation.md) — 37 flags, written 27 Sep 13:47
- [`schematic.md`](schematic.md) — 32 flags, written 27 Sep 14:00
- [`power.md`](power.md) — 59 flags, written 29 Sep 19:38

**The tree moved after all three.** Both netlists and all three generators were
regenerated at **29 Sep 19:43**, five minutes after the power review was saved;
`hardware/interface.md` at 19:34. So the power review is the only one whose
"current state" claims can be trusted without re-checking, and even it is four
minutes behind the generators. Every item below was verified against the tree
as it stands, by reading the netlists, running the three checkers, and — where
a check's blindness was the claim — by tampering with a copy of `hardware/`
in a scratch directory and watching whether the build failed. Nothing in the
design was modified.

Authority, in order: the generated netlists (`hardware/lyrebird-*/​*.net`) for
what is built; the generators for why; then the checkers; then prose. Where a
review and the tree disagree, the tree wins and the item says so.

**Ordering is by what it costs to get wrong**, not by which review raised it or
by how many raised it. The 24 items are referred to as "item N" rather than by
a letter prefix, because every plausible prefix collides with a component
reference on one of these boards. Each item carries its kind —
**contradiction** (two reviews assert incompatible things), **corroboration**
(two reviews reached one conclusion by different routes), **compound** (items
harmless alone that interact), **orphan** (nobody owned it, or the flag points
at a section whose own review was silent) — its sources, and its state in the
tree.

Coverage is complete: every one of the 128 flags is cited somewhere below, in
§1, §2 or §3. Where a flag turned out to be one half of a finding another
review reached differently, the two are merged into one item and both are
named.

Items the reviews raised that are now closed are in
§2, listed once so
they are not re-reported. Things this pass could not settle are named in
§3.

---

## 1. The reconciled list

### Item 1 · Crystek CCHD-957 pad numbering — three documents, three different claims, and a destroy-the-part failure mode
**Kind:** contradiction (three-way) · **Sources:** documentation 37, and the
schematic review's own retraction at documentation 16 · **State: OPEN,
unresolved at the datasheet level.**

Three live documents say three different things about one fact:

| Where | Claim |
| --- | --- |
| `docs/decisions/0012-module-clock-architecture.md:17-18` | "Its pad *numbering* is still wrong — rotated 90° against the bottom view — and that is the one open defect that would stop a board working" |
| `hardware/lyrebird-dac-reva/brief.md:110` | "pad numbering is rotated 90°" against the datasheet's bottom view |
| `hardware/lyrebird-dac-reva/parts-notes.md:291-299` | Lists "which corner is pad 1" as one of two things "read rather than stated", to be checked against the vendor drawing |

`parts-notes.md` has the status right and the other two overstate it. The
"90°" claim is refutable from the footprint's own geometry, which I measured:
`Oscillator_SMD_Crystek_CCHD-957_9x14mm.kicad_mod` puts its four pads at
(±3.556, ±2.54) mm — 7.112 mm along x, 5.08 mm along y — inside an `F.Fab`
rectangle 14.2 mm along x by 9.14 mm along y. That is the datasheet's
`0.280 (7.11)` × `0.200 (5.08)` pad grid lying along the 14.2 mm body axis,
which is the only way those two dimensions can be assigned. A 90° error would
require the drawing's pad-label grid to run the other way, and the
documentation review established from rev N that it does not (labels on a grid
1184.4 wide by 947.5 tall). The silkscreen pin-1 dot at (−6.3, +3.8) agrees
with pad 1 at (−3.556, +2.54); both are lower-left in top view, which is the
convention `parts-notes.md:297-299` says was used. The footprint is internally
consistent and geometrically correct.

**What is actually open is 0° versus 180°**, and it is the most expensive open
item in the repository. Pads 1/2/3/4 are `E/D`/`GND`/`OUT`/`Vcc`; a 180° error
swaps 1↔3 and 2↔4, which puts `+3V3_CLK` on `GND` and ground on `Vcc` for
**both** Y1 and Y2, verified from `lyrebird-dac.net` (Y1.4 and Y2.4 on
`+3V3_CLK`, Y1.2 and Y2.2 on `GND`). That destroys both oscillators and leaves
the module with no clock. It cannot be settled from the PDF text layer.

**Action:** this needs the vendor drawing read as an image, or a
pin-1-to-package-marking measurement on a real part, before fabrication.
Independently and at zero cost, the phrase "rotated 90°" should not survive in
`0012` or `brief.md`, because it names a defect that provably is not there and
so will be dismissed by whoever checks it.

### Item 2 · On the module, −6 V or +5 V landing on any mezzanine signal pin passes the build silently
**Kind:** compound (new; neither review could see it) · **Sources:** schematic 6 and power
PWR-S3, which are the same finding by two routes and are closed · PWR-D2/0015 ·
power PWR-S4 · **State: OPEN, demonstrated by
tamper.**

PWR-S3 asked for `-6V_A` to be added to the output module's `hv_rails`, on the
grounds that "the board's most dangerous net is invisible to
`assert_below_abs_max` on the module side". That has been done —
`output_module.py:713` now reads
`hv_rails={"+5V", "+3V3_CLK", "+3V3_REF", "+5V_A", "-5V_A", "-6V_A"}`, and the
four dead charge-pump rails are gone. PWR-S4 then reasoned that with PWR-S3
closed the module would catch a negative rail on a logic pin.

**It does not**, because 0015 also had to add `-6V_A` to the header's
*allowance*: `protected={mez: {"+5V", "-6V_A"}}` (`output_module.py:716`). The
allowance is per **part**, not per **pin**, and `assert_below_abs_max` skips a
protected pin whenever the net it sits on carries any allowed name
(`lyrebird_parts.py:390`, `if ... groups[g][0] & ok: continue`). So the same
net name is simultaneously declared dangerous and declared permitted, and the
permission wins on all 80 header pins.

Tamper-tested against a scratch copy, module build, one line inserted before
the assertion:

| Injected fault | Verdict |
| --- | --- |
| `elem[0] += v3v3_clk` (3.3 V onto ELEM0) | **caught** — `J1.1 (Pin_1) on net +3V3_CLK/ELEM0` |
| `elem[0] += mez_neg` (−6 V onto ELEM0) | **passes, netlist written** |
| `mclk_out += v5` (+5 V onto MCLK) | **passes** |
| `lp.pin_named(regs[0], "1D1") += mez_neg` | **passes** |
| `ctrl["OSC_EN_48"] += mez_neg` | **passes** |

The last two pass for a second reason: on the module the header is the *only*
protected part, so a rail on a register input or on the translator's 2.5 V A
side is outside the check's subject set entirely.

The main board is asymmetric here, and only by luck. `protected={fpga: set(),
mez: {"+5V", "-6V_A"}}`, so `-6V_A` onto `ELEM0` **is** caught — reported as
`U1.R6 (IO_SA_A1)`, the FPGA ball, never the header pin. The main board catches
it only because the FPGA happens to sit on the same net.

Why this matters more than it reads: the 32 element lines, `MCLK`, `MUTE_N` and
`ID0`/`ID1` run across the connector to GateMate balls with a 2.75 V maximum
and a −0.4 V minimum. A −6 V short on the module side reaches those balls, and
the module's netlist is generated independently of the main board's, so the
main board's check never sees the module's fault. Each board has a guard; the
system does not.

**Action:** the allowance needs to be per pin (the two `-6V_A` pins and the two
`+5V` pins), not per part — the netlist already knows which pins those are. The
module also needs its logic parts in `protected`.

### Item 3 · The FT601Q's own 1.0 V core rail is unprotected, and this board has already made that exact error
**Kind:** corroboration in kind, orphan in fact · **Sources:** power PWR-S9(a);
schematic 1 asked for "a rail-to-pin-class map, not another list entry" and got
`assert_core_rail`, which was scoped to the FPGA only · **State: OPEN,
demonstrated by tamper.**

`main_board.py:887` calls `lp.assert_core_rail(..., [fpga], core_rails={"+1V0"})`.
The FT601Q is not in the subject list, and `CORE_SUPPLY_NAMES` is
`("VDD", "VDD_PLL", "VDD_SER", "VDD_SER_PLL")` — none of the bridge's core pin
names. From `lyrebird-main.net`, `+1V0_FT` carries six pins: `AVDD` (2),
`VD10` (3, 30, 33, 48) and `DV10` (39), and `AVDD`'s absolute maximum is 1.4 V.
`main_board.py:95` calls putting 3.3 V there "a destroy-the-part error", and
`brief.md:91-93` records that an earlier revision of this file did it.

Tamper-tested on the main board:

| Injected fault | Verdict |
| --- | --- |
| `v["+1V0"] += v["+2V5"]` (FPGA core dead short) | **caught**, 44 pins reported |
| `v["+1V0_FT"] += v["+3V3"]` (bridge core dead short) | **passes, netlist written** |
| 10 k from `+3V3` to the bridge's `VD10` | **passes** |

The fix PWR-S9(a) names is right and small: `[fpga, ftdi]` plus
`VD10`/`AVDD`/`DV10` in `CORE_SUPPLY_NAMES`. Note the two rails are not the
same net — `+1V0` and `+1V0_FT` are separate, the latter sourced from the
bridge's own internal LDO at `DV10` — so `core_rails` has to be per subject,
not one set.

### Item 4 · Both absolute-maximum checks are blind to a resistor **array** as a bridge — which is this project's preferred resistor form
**Kind:** corroboration · **Sources:** power PWR-S9(c) (the code gap) and
schematic 18 (which asked `netlist/README.md` to say the check is blind to
"any path through a resistor array") · **State: OPEN, demonstrated by tamper.**

Both `assert_core_rail` (`lyrebird_parts.py:268`) and `assert_below_abs_max`
(`:370`) walk bridges with `if len(pins) != 2: continue`. Tamper-tested on the
main board with a four-element array, one leg on a core `VDD` ball, one leg on
`+2V5`, two legs on ground:

- single 10 k resistor, `+2V5` to one core ball → **caught**,
  `R33 bridges the core rail to +2V5`
- `R_Pack04` array, same connection → **passes, netlist written**

The output module fits **17** `RN` arrays and only 14 discrete resistors, so
the one part shape the check cannot see through is the shape this design
prefers. Two independent reviews arrived at the same blind spot from opposite
ends — one reading the code, one reading the documentation that describes the
code — and neither knew the other had.

A second, related gap is also tamper-confirmed (PWR-S9(b)): `assert_core_rail`
asserts no subject count. With `CORE_SUPPLY_NAMES` made to match nothing, a
dead short of `+2V5` onto `+1V0` builds clean. A renamed ball in a symbol
revision silently empties the check.

### Item 5 · The translator's bank 2, the shared `OSC_RAW` net, and three documents that disagree about whether one-oscillator is enforced
**Kind:** compound + contradiction · **Sources:** power PWR-S8 and PWR-O2/O3;
schematic 3 and schematic 5 (which recommends the opposite of what was done);
schematic 31 (no ERC) · **State: OPEN — and one of the three documents is the
newest file in the tree.**

The mechanism, verified pin by pin from `lyrebird-dac.net` and
`output_module_sklib.py`:

- U2 74AVC4T245: `VCCA` = `+2V5` (U9), `VCCB` = `+3V3_CLK` (U6).
- `1DIR` = GND → bank 1 runs B→A, outputs on the **A** side (`1A1` = `MCLK`).
- `2DIR` = `+2V5` → bank 2 runs A→B, outputs on the **B** side
  (`2B1`/`2B2` = `OSC_EN_48_3V3`/`OSC_EN_441_3V3`).
- `1~{OE}` and `2~{OE}` both hard to GND (`output_module.py:227`, `:238`),
  against SCES576I's "`OE` must be tied to VCCA through a pullup resistor and
  must not be enabled until VCCA and VCCB are fully ramped and stable".
- Y1.3 and Y2.3 are both `OUTPUT` on one net, `OSC_RAW`, legal only with
  exactly one part enabled — and their `E/D` inputs are bank 2's outputs.

The fitted SET networks are U9 = 24.9 k ‖ 10 µF and U6 = 33.2 k ‖ 4.7 µF.
PWR-S8's arithmetic reproduces exactly: τ_A = 249 ms, τ_B = 156 ms, and with
`PGFB` tied to `IN` disabling fast-start each rail is a plain exponential, so
VCC(A) reaches the 1.2 V minimum at **164 ms** against VCC(B) at **70 ms**, and
because τ_A > τ_B *and* V_A(∞) < V_B(∞) it lags at every instant. That is a
deliberate and robust fix — **for bank 1**, whose outputs are on the rail that
arrives last. Bank 2's outputs are on the rail that arrives **first**, so
lengthening the delay lengthens the window in which they are powered and
enabled while their own inputs' supply is between 0 V and its minimum.
**≈94 ms per power-up**, during which both `E/D` lines are driven from
indeterminate A-side inputs onto a shared output net.

The three documents:

1. `hardware/interface.md:82-95` (modified 29 Sep 19:34, the newest file
   involved) says the "exactly one oscillator" rule "is now enforced rather
   than merely stated", and gives pull-downs as the mechanism: "**Both boards
   now pull the enables down** … the module as well because a pull-down there
   only decides the case where the translator's output is high impedance."
   That sentence is its own refutation. With `2~{OE}` tied low the outputs are
   never high impedance — they are driven throughout the window — and the
   module's pull-downs (R2, R3, 100 k on `OSC_EN_*_3V3`, verified in the
   netlist) are fighting a push-pull driver. `main_board.py:686-689` states
   this correctly about the module's own resistors and then `interface.md`
   claims the enforcement anyway.
2. `output_module.py:362-372` presents the sequencing as satisfying SCES576I
   "by construction" and marks `2~{OE}` "same as bank 1, same reason". Bank 2
   does not have bank 1's reason.
3. Schematic flag 5 asks for the opposite change: cut U9's `C_SET` because
   "nothing on it reaches the signal". Doing that now would invert bank 1's
   ordering and re-open the fault the 10 µF closed. PWR-O2 says the same thing
   from the other side: `+3V3_REF` must keep 4.7 µF for noise, `+2V5` must stay
   slow for bank 1, cutting `+3V3_CLK` breaks the ordering from the other end —
   the sequencing is now load-bearing in two directions.

Compounding it: `main_board.erc`, `output_module.erc` and every other `*.erc`
in the tree are **zero bytes** (verified), SKiDL's ERC is never invoked, and no
step in `regenerate.sh` runs it. An output-to-output net is exactly what ERC
reports, and `OSC_RAW` is one by construction.

**Action:** the remedy is not another capacitor. `2~{OE}` needs a gate that is
referenced to VCC(A) — or bank 2's direction needs reversing so its outputs sit
on the rail that arrives last, which would put bank 1's on the early rail and
trade the problem rather than fix it. Whether `Ioff` covers the window is
PWR-O3 and needs SCES576I. Also note the aside in schematic flag 5 is wrong on
its own terms: `+2V5` powers the driver of `MCLK`, the element clock the module
hands back to the FPGA, so "nothing on it reaches the signal"
(`output_module.py:59-60`) is at best loose.

### Item 6 · The mezzanine's +5 V allocation has halved twice, the two reviews disagree about it, both are quotable, and only one is now right
**Kind:** contradiction (resolvable) + compound · **Sources:** documentation 6;
power PWR-M2, PWR-A2, PWR-S10, PWR-C3, PWR-D5 · **State: documents OPEN;
the review disagreement is resolved below.**

Read out of both netlists as they stand (all 80 pins agree across the
connector, zero mismatches):

```
1–63 odd   ELEM0–31        2–64 even  GND
65 MCLK    66 OSC_EN_441   67 OSC_EN_48   68 MUTE_N   69 ID0   70 ID1
71 GND     72 GND          73 -6V_A       74 -6V_A    75 GND   76 GND
77 +5V     78 GND          79 +5V         80 GND
```

Totals: **GND 38, +5V 2, −6V_A 2.**

The two reviews say different things and both were correct when written:

- documentation 6: "+5V is on **pins 73, 75, 77, 79 — four pins** on both
  boards, and **pin 71 carries `-6V_A`**". True of the tree on 27 Sep.
- PWR-M2/PWR-A2/PWR-S10: two pins, 77 and 79; `-6V_A` on 73/74; ground at
  71/72 and 75/76. True of the tree now.

**The power review is right; documentation 6's correction is itself now stale.**
Determined by reading both netlists and by re-deriving the generator's tail
loop, which alternates `+5V`/`GND` from wherever the preceding block leaves the
index: with no negative pair the tail gives `+5V` on 71, 73, 75, 77, 79 — which
is exactly what both `power.md` files still say, so those pages are simply
pre-0015 rather than wrong about their own era.

The sequence, and what nobody has revisited:

| State | GND | +5V | −6V_A |
| --- | --- | --- | --- |
| pre-0015 (what both `power.md` files describe) | 37 | 5 | — |
| 0015 as first built (what documentation 6 describes) | 36 | 4 | 71/72 |
| now, after PWR-S5's flanking fix | **38** | **2** | **73/74** |

Three consequences, none of them recorded anywhere:

1. **`interface.md:55` attributes the cost to the wrong allocation.** "Four
   pins out of a ground surplus removes that." Ground did not pay: it went
   **up**, 37 → 38. Three of the four pins came out of `+5V` (71 and 75 became
   ground, 73 became the negative rail) and one out of ground (74). This is the
   newest statement in the tree about the change and it is backwards.
2. **PWR-C3 and PWR-D5 are the same arithmetic error in two files, and it was
   never right at any stage.** `main_board.py:647-648` ("37 returns for 28
   switching lines was generous, 35 still is") and
   `0015:52-53` ("37 of them ground … 35 remain"). The verdict — generous —
   survives; 38 returns for 28 lines is more generous than the comment claims.
   Both also now carry the wrong pin numbers.
3. **The redundancy argument in both `power.md` files is gone and nothing
   replaced it.** PWR-M6 and PWR-A6: "**Five** parallel header contacts at
   20 mΩ drop 2 mV at 123 mA" is two contacts and 1.2 mV, at **61.5 mA per
   contact**, with a single failed contact putting the module's whole 123 mA on
   one pin. Electrically fine for a 1.27 mm contact; the argument the pages
   make is not.

Still open, verified, in: `lyrebird-main-reva/power.md:16,22`,
`lyrebird-dac-reva/power.md:19-20,23`, `docs/open-items.md:73`,
`main_board.py:647`, `0015:52`, `interface.md:55`.

### Item 7 · The element-adjacency rule describes an arrangement the boards do not have, and `MCLK` has no return beside it
**Kind:** orphan (schematic only; the power review's mezzanine flags PWR-S5 and
PWR-S10 do not touch either point) · **Sources:** schematic 21 and schematic 22 ·
**State: OPEN, and the PWR-S5 rework did not address it.**

`hardware/interface.md:80-81` says "**Every element line sits adjacent to a
ground pin.** Element return currents are the analog signal." What both
generators build, verified pin by pin, is all 32 element lines on the odd pins
1–63 and all 32 grounds on the even pins 2–64: a solid ground row directly
*opposite* each element, with each element flanked **within its own row** by two
other element lines. That is arguably the better arrangement — every element has
a return 1.27 mm away across the row, and the row of grounds is continuous — but
it is not what the sentence describes, and a module designer reading it would
expect interleaving and lay out for it. Recorded alongside as confirmation: the
two boards agree pin for pin on all 80 mezzanine pins, zero mismatches, verified
after the regeneration.

`MCLK` is the exception, and it is the signal the reclocking architecture exists
to keep clean. On pin 65 its in-row neighbours are `ELEM31` (63) and
`OSC_EN_48` (67), its across-row neighbour is `OSC_EN_441` (66), and its nearest
ground is pin 64 — diagonal, not adjacent. Every element line has a ground
directly opposite; the element *clock* does not.

Two things make this worth more than a pinout note:

- **The PWR-S5 rework did not fix it, and its own reasoning says why it should
  have been considered.** `interface.md:50-52`, written as part of that fix,
  states the problem explicitly — "MCLK, both oscillator enables, `MUTE_N` and
  both ID straps run from pin 65 to 70 with returns only at either end" — and
  then solves a different problem, moving the negative rail out of the control
  block rather than putting a return into it. The four ground pins the fix added
  are at 71/72 and 75/76, outside the block. Whether that was the right trade is
  a judgement; that it was never stated as a trade is the gap.
- **It compounds with item 5.** `MCLK` is driven by the translator's bank-1
  A-side output, powered by `+2V5` — the rail item 5 is about, the last to
  arrive, and the one whose supply comment (`output_module.py:59-60`) says
  "nothing on it reaches the signal". So the one mezzanine signal without a
  return beside it is also the one whose driver sits on the rail the design has
  deliberately made slowest.

`interface.md:80` should either describe what is built or say why the
opposite-row arrangement was chosen, and should name `MCLK` as the exception.

### Item 8 · U14's SET resistor: the netlist says 40.2 k, seven other places say 45.3 k, and one BOM row says both
**Kind:** corroboration (closed in the netlist) + contradiction between the two
reviews' recommended values (resolved) · **Sources:** documentation 4 and 21;
schematic 4; power PWR-S6, PWR-D6, PWR-A0 · **State: netlist CLOSED; seven
documents OPEN.**

The netlist is `R10 = 40.2k 0.1%`, and `U14`'s own value string reads
"LT3045 op amp positive rail, **+4.02 V** from mezzanine 5 V". `verify_power.py`
reports `+511 mV of margin at the corner`. This is the second fix: 49.9 k → 45.3 k
→ 40.2 k.

**Where the two reviews disagreed, and who was right.** Both independently
found the 45.3 k intermediate value marginal — schematic 4 computed −90 mV of
stacked worst-case dropout margin, PWR-S6 computed +3 mV on the same bound.
They then recommended different replacements: schematic 4 said "the rail only
needs ~3.5 V; **36.5 k** would give ~1.2 V of margin"; PWR-S6 solved two
inequalities and took the midpoint at **40.2 k**. **PWR-S6 is right and 36.5 k
would have been a fresh fault.** Schematic 4 priced only the dropout bound and
treated the swing requirement as satisfied at "~3.5 V". The real swing floor is
3.43 V (±2.83 V peak plus the OPA1612's 600 mV), and at 36.5 k the rail's own
±2 % `ISET` low corner is 3.577 V — **+147 mV**, against 40.2 k's +510 mV. The
fitted value trades one bound against the other instead of moving the problem.
`output_module.py:583-597` records this reasoning.

**What is still wrong.** 45.3 k / 4.53 V propagated into seven places in the
four days before it was superseded, and all seven are live:

| File | What it says |
| --- | --- |
| `hardware/make_bom.py:151` | "Takes the mezzanine's 5 V straight down to **+4.53 V**" — the BOM *generator* |
| `hardware/lyrebird-dac-reva/bom.csv:16` | value column "+4.02 V", notes column "+4.53 V" — **one row, both numbers** |
| `hardware/lyrebird-dac-reva/power.md:41,55` | rail table `+4.53`, "leaves 3.93 V of swing" |
| `hardware/lyrebird-dac-reva/parts-notes.md:409,424,440,441` | "**+4.53 V by 45.3 kΩ**", and the SET-pin note |
| `hardware/sim/power_negative_rail.py:1077` | `(5.02 - 4.53) * 0.0216`, "after the SET fix" — see item 16 |
| `docs/decisions/0015:56,89` | "to **+4.53 V**", "It is **45.3 kΩ and 4.53 V** now" |

The BOM row is the sharp one: it is machine-generated, it is the document a
board house is sent, and it contradicts itself in two adjacent columns. It also
mixes eras inside one sentence — "+4.53 V, chosen for 490 mV of headroom … the
swing, which needs only 3.43 V" pairs the 45.3 k voltage and headroom with the
40.2 k swing floor. This is exactly what documentation 27 predicted:
`check_freshness.check_bom` compares reference **sets** only and never values,
so a revalued part passes, and its docstring at `:22-24` promises otherwise.

### Item 9 · The capacitors PWR-S2 added are the highest-stressed pair on either board, and carry no voltage rating
**Kind:** compound · **Sources:** power PWR-S2 (closed), PWR-S7 (second half),
PWR-V4, PWR-V14; schematic 2 (closed) · **State: the bypass is CLOSED; the
rating gap is OPEN.**

Schematic 2 and PWR-S2 found the same missing part by different routes —
schematic 2 enumerated it from the netlist, PWR-S2 measured it in ngspice
(100 % of the 0.69 A switch transition returning through the ground plane with
7.6 V across the pin pair). It is fitted: `C15 = 10 µF` (1210) and
`C16 = 100 nF` (0603), both from `+12V` to `-6V_A`, verified in
`lyrebird-main.net`.

Three separate flags meet on those two parts and nobody joined them:

- **Their working voltage is not 12 V, it is 18 V nominal and 35.2 V at the
  clamp.** `+12V` to `-6V_A` is `VIN + |VOUT|`. PWR-V4 computed the same
  35.18 V for U7's own rating and noted "U7 is not in the check" —
  `verify_power.py` compares the TVS's 29.2 V clamp against U5's 36 V only.
  Nothing anywhere prices these two capacitors against 35.2 V.
- **Neither carries a voltage rating or a dielectric** (PWR-S7). Verified:
  `bom.csv` groups capacitors by value alone, and `C15` appears as
  `C15,1,10uF,,,C_1210_3225Metric,,GROUPED` while `C18 C19,2,10uF` — on `+5V` —
  is a separate line only because the footprint differs. A 10 µF 1210 X5R is
  commonly 16 V or 25 V; at 35 V it is destroyed, and at 25 V its DC-bias
  derating at 18 V would also undo PWR-S2's measured 91 %-local result.
- **`C15` is the reference `verify_power.py`'s netlist parser loses.** PWR-V14
  reported `val["C8"] = ""` on the main board; re-running that parse against
  the current netlist gives `val["C15"] = ""` — the reference **moved with the
  regeneration**, and it has landed on this part. Still harmless (it is not a
  SET resistor), but "harmless only because neither is a SET resistor" is an
  accident that is re-rolled on every rebuild. The cause is unchanged:
  `text.split("(comp")[1:]` at `verify_power.py:151` also splits on
  `(component_classes)`, which appears in every component block.

**Action:** rate these two parts explicitly at 50 V, say so in the BOM, and
make the placement obligation PWR-S2 left as a residual a line in the layout
notes rather than a sentence in a review.

### Item 10 · The bridge's 3.3 V current: 187 mA, 60 mA, and a 400 mW thermal-via instruction that lives only in a superseded record
**Kind:** corroboration + orphan · **Sources:** documentation 13 and 14; power
PWR-M4 and PWR-O1 · **State: OPEN, and better instrumented than either review
knew.**

Two reviews reached the same conclusion by different routes. Documentation 13
found it by reading the prose: `main-reva/power.md:91` keeps 0009's 185 mA
*active SuperSpeed* figure while relabelling the row "High Speed", against
`verify_power.py:112`'s `I_3V3 = 0.060` whose own comment reads
"`main power.md is stale`". PWR-M4 found it by reflecting the rail table to the
input: 185/15/149 mA against 60/90/80 mA. Both are verified still live —
`power.md` has not been touched since 25 Sep 19:46.

What neither knew: **a third checker already carries both numbers side by
side.** `hardware/sim/power_negative_rail.py:1066-1067` computes
`p_u3_ds = (5.02 - 3.32) * 0.185` and `p_u3_vp = (5.02 - 3.32) * 0.060`,
reports both, and settles check E-3 on the conservative one. So the repository
has three figures for U3's dissipation — **102 mW** (`verify_power.py`),
**315 mW** (`power_negative_rail.py`, which calls it 10.7 °C of rise) and
**"roughly 400 mW"** (`0009:44`) — and one file that at least declares the
dispute. That is the place to resolve it.

The orphan half is documentation 14, which the power review did not raise:
`0009:44`'s "it dissipates roughly 400 mW, **so tie the exposed pad to plane
with thermal vias**" is quarantined in a superseded record. `hardware/README.md:62-65`
describes the same rail and omits both the dissipation and the requirement.
Whatever the current turns out to be, the layout instruction exists only in a
retired document, attached to a number four times the one the live checker
uses. PWR-O1 is right that closing this needs the FT601Q datasheet; the
thermal-via line does not, and should be restated live now.

### Item 11 · The element resistor split still rests on a rule that no longer exists, and the noise argument now points the other way
**Kind:** corroboration · **Sources:** documentation 31; schematic 9 · **State:
OPEN — the cheapest item on this list to act on.**

Both reviews independently found that `1.69 k + 1.65 k` exists only to clear
the retired one-unit-load-at-power-on limit. Verified still fitted: `RN1`–`RN7`
at 1.69 k and `RN8`–`RN14` at 1.65 k, both `0.1% thin film`, in
`lyrebird-dac.net`. Verified still justified by the retired rule:
`parts-notes.md:307-311`, verbatim — "it stays above the 3312 Ω that the
one-unit-load-at-power-on argument requires; an even 1.65 + 1.65 split would be
3.30 kΩ and fail that by a hair."

The rule is gone, and the same file says so two hundred lines earlier
(`:216-222`, which was rewritten and is now correct — see §2). And the noise
argument has since been corrected to point **downward**:
`dac-reva/power.md:330-336` now states, correctly, that 2585 Ω "is **not** an
optimum … that noise falls monotonically as R does, so lower is always quieter
and always costs more current." So 1.65 + 1.65 = 3.30 kΩ is marginally
*better* than what is fitted on every surviving criterion, and it is one part
number instead of two.

Nothing electrical blocks this. It is two identical arrays where there are
currently two different ones, and it is the only item in this document that
costs nothing and improves the design.

### Item 12 · `verify_power.py`'s `ldo_rails` fails open three ways and asserts no subject count
**Kind:** known open (context) · **Sources:** power PWR-V1 · **State: OPEN,
verified.**

The current run reports **18/18** and covers all six post-regulators (`main U3`,
`module U5/U6/U8/U9/U14`), so the fault documentation 22 recorded is genuinely
closed. The three silent-skip paths are unchanged at `verify_power.py:158-186`:
`re.match(r"([\d.]+)k", …)` drops a SET value spelled in ohms; `rail not in
known` drops a regulator whose IN rail is not `+5V` or `-6V_A`; and
`fam in v` drops one whose value string loses its family name. Each drops a
regulator and the run still says all checks pass.

PWR-V1's fix — assert the subject count, six — is the same fix item 4 needs for
`assert_core_rail`, which has the identical gap (PWR-S9(b), tamper-confirmed:
with `CORE_SUPPLY_NAMES` matching nothing, a `+2V5`-to-`+1V0` dead short builds
clean). One convention, applied to both: **a check that finds no subjects
fails.**

### Item 13 · Two constants inside `verify_power.py` that do not do what their own notes say
**Kind:** known open (context) · **Sources:** power PWR-V16, PWR-V17 · **State:
OPEN, verified.**

- `V5_TOL_LO = Fact(0.0157, …, "LMR33630 VFB 0.985 V min with 1% divider")` at
  `:86`. 1.57 % is the feedback tolerance alone; with 1 % on both 100 k and
  24.9 k the real low corner is 4.863 V, not 4.941 V. Every corner verdict in
  the run above is therefore about **79 mV optimistic** — U14 has +432 mV where
  the run prints +511 mV. No verdict flips, and item 8's choice of 40.2 k survives
  either way.
- `vin_lo` is rebound inside the dropout loop at `:319` and printed by the
  summary banner at `:367`. Confirmed in the current output: the header reads
  **"Input 4.9 to 12.6 V at the jack"** — the +5 V rail's low corner presented
  as the adapter voltage. The checks that use the outer `vin_lo` run before the
  loop, so nothing is wrong except the file's headline.

### Item 14 · Neither checker can ask whether a rail reaches the right ball, and the example chosen to show it is already answered in hardware
**Kind:** corroboration, with a correction to the demonstration · **Sources:**
schematic 28; power PWR-V15 · **State: the limitation is OPEN; the specific
example is already mitigated in hardware.**

Both reviews reached the same limitation from different ends. PWR-V15 states it
generally: "neither can express *does this rail reach the right ball of the
right package*. Rails are strings and voltages are constants" — and notes the
assumption has failed twice in the power tree, at the LTM4622 land and at
PWR-S1. Schematic 28 states it as a gap against `verify_power.py`'s own
docstring, which says the file exists "so that changing a component value
changes the verdict instead of only the prose": reading the six LT3045/LT3094
SET resistors out of the netlists closes part of it, but `V_1V0`, `V_2V5`,
`V_3V3`, `V_5V` and `V_N6V` remain hand-written (`verify_power.py:106-119`,
with `V_2V5` and `V_1V0` marked `DS` and annotated "LTM4622 table value 19.1 k"
and "90.9 k"). Both are right, and the two together are the reason
`assert_symbol_footprints` closes the *override* class of footprint fault while
leaving the *hand-drawn land* class open — the LTM4622's land is project-local,
so no symbol default contradicts it, which is exactly how the transposition
survived.

**But schematic 28's demonstration is the weakest example available, and the
review did not credit what the design does.** Its test T15 swaps the LTM4622's
two feedback resistors — "the error the generator itself calls the worst single
assembly mistake on the board" — and observes that neither
`verify_power.py`'s verdict nor `assert_below_abs_max`'s changes. True: the net
names are unchanged, so nothing a netlist check can see moves. What the review
did not report is `main_board.py:453-464`, which anticipates precisely this and
answers it in the only layer that can:

> "the worst single assembly error on this board is swapping these two: 19.1k on
> FB2 puts 2.5 V onto +1V0, which reaches VDD x28, VDD_PLL, VDD_SER x2 and
> VDD_SER_PLL against a 1.20 V absolute maximum, and kills the FPGA on first
> power-up. … So the core rail's resistor is deliberately a DIFFERENT PACKAGE."

Verified in the netlist and both BOMs: `R8 = 19.1k 1%` on `R_0402_1005Metric`
at FB1, `R9 = 90.9k 1%` on `R_0603_1608Metric` at FB2. A mutual transposition
requires putting the 0603 part on the 0402 land, which does not happen.

**Two residues, and they are worth stating because the comment overstates its
own guard.** "A 0603 part cannot be placed on an 0402 land, which makes the
fatal direction of the swap a physical impossibility" is not quite the fatal
direction: the fatal *placement* is 19.1 k landing on FB2, and an 0402 part on
an 0603 land is not impossible. What the asymmetry defeats is a **mutual**
swap, by blocking its other half. It does not defeat a mis-loaded feeder
putting 19.1 k in both positions, which produces the same 2.5 V on 32 core
balls, and nothing in the netlist, the BOM, or either checker would see it. So
PWR-V15's limitation stands and schematic 28's conclusion stands; the example
chosen to demonstrate it is the one case where hardware already does most of
the work, and a reader who checks T15 will find the design in better shape than
the flag implies.

Where the limitation actually bites is items 2, 3 and 4 — three tamper-confirmed
cases where a rail reaches a pin it must not and the check reasons over net
names instead of over the pin.

### Item 15 · The exported schematics assert 49 shorts the netlists do not contain
**Kind:** known open (context) + compound with the absent ERC · **Sources:**
schematic 32, schematic 31 · **State: OPEN, reproduced exactly.**

Re-measured against the sheets as regenerated on 29 Sep 19:43: **23 coordinates
on the main board and 26 on the module — 49**, the schematic review's number to
the unit. Both mechanisms are unchanged in `tools/netlist_to_schematic.py`:
`collect_pins` recurses through every unit of a symbol while only unit 1 is
drawn (`:164-178`, `:344` emits `(unit 1)`), and `round(v / GRID) * GRID` with
`GRID = 2.54` snaps pins on a 1.27 grid, with banker's rounding merging them in
pairs (`:316-317`, `:358-359`).

Current worst cases, for anyone reading the PDFs as a check:

```
main 01-U1-CCGM1A1  (45.72, 116.84)  ELEM17 / ELEM21 / FT_DATA17 / FT_RXF_N
main 01-U1-CCGM1A1  (45.72, 114.30)  ELEM13 / ELEM20 / FT_DATA13 / FT_TXE_N
dac  03-Reclocking  (78.74, 152.40)  ELEM7 / GND
dac  03-Reclocking  (78.74, 177.80)  ELEM_CLK_L / GND
```

The specific `ELEM21`/`GND` pair the review cited has moved with the
regeneration; element-to-ground collisions have not. Note also that schematic
17 counts "20 sheet files" — there are **19** (10 main, 9 module); the
conclusion it draws from them is unaffected.

Compounded by schematic 31: no ERC runs anywhere, so nothing reports the
phantom shorts and nothing reports the real output-to-output net at `OSC_RAW`
(item 5). `check_freshness.py`'s single-node-net check is the right shape for this
and passes on both boards; extending it to driver conflicts is the same one
function.

### Item 16 · `power_negative_rail.py` reads the netlist for one constant and hard-codes the superseded value for another
**Kind:** orphan (no review's flag list names this file) · **State: OPEN, no
verdict affected.**

The file's docstring declares "**A. NETLIST AUDIT.** Reads the generated
netlists and compares every power constant the two existing checkers restate
against what is actually fitted." Its ramp model does exactly that —
`:796` carries `("s14", 40.2e3, 4.7e-6, 4.02, "mute", "p5v")`, read out of the
netlist. Its dissipation table at `:1077` carries
`("U14 LT3045 +5V_A", (5.02 - 4.53) * 0.0216, 34.0, "after the SET fix")` —
the superseded 4.53 V, annotated as post-fix. Correct is
`(5.02 − 4.02) × 0.0216 = 21.6 mW`, not 10.6 mW; at 34 °C/W that is 0.7 °C
against 0.4 °C, so no verdict moves and E-3 is decided by U3 regardless.

It is worth recording anyway, for two reasons. It is the seventh instance of
item 8's stale constant, and it is a second-generation example of the exact fault
class `0015:84` names in its own words — "a constant left behind beside a
changed circuit" — sitting inside the file built to find those. The two reviews
that read the simulations read `power_input_transient.py`; this file was read
only for its results.

### Item 17 · The board files are seventeen days behind the netlists, contain deleted parts, and no check names them
**Kind:** orphan · **Sources:** documentation 15 (power and schematic reviews
both silent) · **State: OPEN, and worse than reported.**

Re-measured. Both `.kicad_pcb` files are dated **12 Sep 22:20** against netlists
dated **29 Sep 19:43** — seventeen days, not thirteen.

| | netlist | `.kicad_pcb` |
| --- | --- | --- |
| main components | 159 | 133 footprints, 0 `(segment` |
| main, parts not in the netlist | — | `FB1` (deleted VBUS ferrite), `Q1` (deleted `WAKEUP_N` NMOS) |
| main, U / J | 7 / 4 | 5 / 3 |
| module components | 112 | 42 footprints, 0 `(segment` |
| module C / RN / U | 64 / 17 / 13 | 16 / 7 / 7 |

`check_freshness.py`'s `BOARDS` dict (`:44-57`) names `dir`, `net`, `gen` and
`pdf` and **never names the board file**, so none of this is visible to the
tool whose docstring was written about this failure, and the run reports
`0 stale`. `main-reva/brief.md:95-96`'s "The `.kicad_pcb` holds placed
footprints from the netlist import and zero tracks" is half true: zero tracks,
but not this netlist's import.

The reason this sits here rather than lower: `FB1` and `Q1` are the two parts
whose deletion 0014 and `main-reva/power.md:129-145` describe as the most
consequential changes on the board — `Q1` is the NMOS that held the FPGA core
rail off on every power-up — and both are still in the file a layout would be
started from.

### Item 18 · Stale comments in the generators, and one that asserts and refutes itself 25 lines apart
**Kind:** mixed; several corroborations · **Sources:** power PWR-C1–C5;
schematic 24, 25, 26, 27, 29, 30 · **State: verified individually below.**

All three generators were regenerated 29 Sep 19:42, so these are current.

| Flag | Where | State |
| --- | --- | --- |
| PWR-C1 | `main_board.py:170-171` "That part is not built yet: the mezzanine still carries +5V and the module still has its charge pump" | **OPEN** — U7 is 60 lines below, and the mezzanine carries `-6V_A` on 73/74 |
| PWR-C2 | `main_board.py:690` `MUTE_N` "is a direct input to the charge pump's enables rather than a translator input" | **OPEN** — it drives U14.3 and U8.3 `EN/UV` |
| PWR-C3 | `main_board.py:647-648` "37 returns … 35 still is" | **OPEN** — see item 6 |
| PWR-C4 **+** schematic 25 | `output_module.py:616,622` "the inverting pump's output", "the doubled-then-inverted rail … at the bottom of the USB range" | **OPEN** |
| PWR-C5 | `output_module.py:646` "well above the **22 mA** this rail carries and below what the pump's LDO can deliver into a fault" | **OPEN** — 63.5 mA worst case; 22 mA is the positive rail's figure; the 151 mA limit value itself is right |
| schematic 24 | `output_module.py:644` "the LT3094's pin description gives no instruction for an unused `ILIM`" | **OPEN** — LT3094 Rev 0 gives the LT3045's instruction verbatim; the 24.9 k is still a legitimate choice |
| schematic 26 | `output_module.py:505` "Pole 3 of three: 1.3 nF across **604 ohm** is 203 kHz" | **OPEN** — directly above code fitting 3.9 nF (`C47`–`C50`) across 200 Ω (`RN16`/`RN17`); the same file gets it right at `:480` |
| schematic 27 | `main_board.py:224` "the **unresolved** −0.40 V against −0.3 V in the review" | **OPEN** — `:265` of the same file records D3 resolving it to −0.233 V, and `power_input_transient.py` prints −0.233 V |
| schematic 29 | `output_module.py:174` "17.5 fs typical" (SNAS791D says 7.5 fs); `:614,639` "±1.35 V" (datasheet 1.26 V typical) | **OPEN** — both are figures a part was selected on, both wrong in the safe direction |
| schematic 30 | `main_board.py:123-125` "on a B-type receptacle SSTX is what the device transmits … because the cable ties StdA_SSTX to the B-side SSRX" | **OPEN as a statement, CLOSED as a fault** |

Schematic 30 deserves the extra line. The fault is gone — `grep -c 'SSTX\|SSRX'`
over `lyrebird-main.net` returns **0**, the pairs are deliberately unconnected
at `:136`, and `:147-155` now records the correct analysis including "USB 3.0
cables have no such crossover". But the false premise is still stated as
present-tense fact at `:123-125`, above the code, and `:119-120` still says
"Both the SuperSpeed pairs and the USB 2.0 pair land here" and points at 0009's
retired 500 mA ceiling. One file now asserts and refutes the same convention
twenty-five lines apart, which is the shape that produced the original error.

### Item 19 · Documents that describe a power tree the boards no longer have
**Kind:** corroborations, mostly · **State: verified individually below.**

| Flag(s) | Where | State |
| --- | --- | --- |
| documentation 5 **+** PWR-M7 | `main-reva/power.md:164-174`, the "What has no source today" section | **OPEN.** All four claims false: `U4 LTM4622IV#PBF` is in the netlist on the `lyrebird:` land pattern sourcing `+2V5` and `+1V0`; `J1` exists; the VBUS ferrite is deliberately absent. Both reviews say delete the section |
| documentation 7 **+** PWR-M1, PWR-M3 | `main-reva/power.md:3-4,16-18,22` | **OPEN.** "Bus powered, no external input ([0009])", "downstream of the VBUS ferrite", "unregulated bus voltage and ground, and no other rail" — contradicted by the same page's rail table at `:36-38` |
| documentation 12 | `main-reva/power.md:158` "the netlist says 1 kΩ", in the "Against 0009's budget" table | **OPEN.** 1.69 k + 1.65 k = 3.34 kΩ, inside a live reconciliation table |
| PWR-M5 | `main-reva/power.md:66` "against **6.3 J** to trip F1" | **OPEN.** `power_input_transient.py` prints **31.9 J** from the model the page cites |
| PWR-M8 | `main-reva/power.md` margin table | **OPEN.** Omits the 305 mA simultaneous soft-start peak |
| documentation 8 and documentation 10 **+** PWR-A3, PWR-A4 | `dac-reva/power.md:276-317` and `:344-353` | **OPEN.** "The declared figure is 900 mA regardless" survives at `:311`; "Against 0009's budget … this page now gets 238 mA" at `:344-345`, against the same page's own 123 mA + 64 mA; and `:351` still prices the op amp line with "a doubler that pays for all of it twice" |
| documentation 9 **+** PWR-A5 | `dac-reva/power.md:392-393` | **OPEN.** "3 mA of pump quiescent" and "4.43 V at the header … it decides whether the charge pump is inside its input range", both retired by the same file at `:272-275` |
| PWR-A1, PWR-A6 | `dac-reva/power.md:1-3`, "Headroom at the worst input" | **OPEN.** See item 6 for the five-contacts half |
| PWR-A7 | `dac-reva/power.md`, open item D10 | **OPEN, and the numbers moved.** PWR-A7 offers 511/561 ms and 51 ms of asymmetry; PWR-S6's 40.2 k fix changed that to **455/561 ms and 106 ms**, into a jack with no DC blocking. Whichever is quoted, the page still has none |
| documentation 3 | `dac-reva/parts-notes.md:66-69` and the Status table at `:636` | **OPEN, and half-fixed in a way that makes it worse.** The body is now correct (`:93` "200 Ω is fitted, and the 2.1 dB is recovered"), but `:66-69` still reads "they are **604 Ω** rather than the 200 Ω analog.txt names" and the Status table still says "Difference network \| **604 Ω, not 200**". The file now contradicts itself, and the Status table is what a reader checks |
| documentation 4 | `dac-reva/parts-notes.md:422-441` | **OPEN, second generation.** The 49.9 k/4.99 V/charge-pump text is gone; 45.3 k/4.53 V replaced it. See item 8 |
| — | `dac-reva/parts-notes.md:636-638` Status table | **OPEN, unflagged by any review.** Two more rows are stale beside the 604 Ω one: "`MUTE_N` \| **gates the charge pump**" (`:637`) and "power.md \| **updated** — module 238 mA, board 472 mA" (`:638`) |
| PWR-D1 | `0014:54` | **OPEN.** "That second stage **is not built yet** — see 'What this does not yet do'." 0015 built it, and the section it points at is now titled "What this did not do, and what has since" (`:120`). One sentence, the only place in 0014 still asserting the inverter is unbuilt |
| PWR-D2 | `0014:42` | **OPEN.** "everything downstream of +5V is unchanged — the LTM4622, the LT3045 and **the mezzanine** all see the rail they were designed against." The mezzanine now carries −6 V on two pins, and the +5 V allocation went from five contacts to two (item 6). 0015 supersedes it, so an amendment marker is enough |
| PWR-D3 | `0014:129` | **OPEN, and stale in the opposite direction from the rest of its own section.** "**The isolator is not fitted.** Still true. The SuperSpeed pairs **are routed**…" The isolator half is still true; the pairs are gone — `grep -c 'SSTX\|SSRX'` over `lyrebird-main.net` returns 0 — and the hardest constraint in the main board's layout went with them |
| PWR-D4 | `0014:101` | **OPEN, and it now matters more than when it was flagged.** The paragraph lists `+12V`, `VIN_RAW` and `VIN_FUSED` as declared in `hv_rails` and states the general lesson: "an undeclared rail reaching a protected pin passes silently." `-6V_A`, the rail 0015 went on to introduce, is declared on both boards now — and item 2 shows declaring it was not sufficient, because the same name is also in the header's allowance. The paragraph should name the rail *and* the second mechanism |
| PWR-D5 | `0015:52-53` | **OPEN.** See item 6 — wrong at every stage of the sequence, and now the wrong pin numbers too |
| PWR-D6 | `0015:56,89` | **OPEN.** See item 8 |
| documentation 11 | `hardware/README.md:39,48-56,71-73,243-247` | **OPEN, verified line by line.** "Bus power and data, one cable"; "Bus powered … See 0009"; a rail table sourcing 5 V through "Ferrite only" with no `+12V` or `-6V_A`; "Gate the FPGA rails with the LTM4622 run pins … so the board respects the one-unit-load limit"; "generate [the bipolar supply] on the module … at a charge pump's switching frequency" |
| — | `README.md:70` (repository root) | **OPEN, unflagged by any review.** "Bus powered from a single USB cable" |
| documentation 18 and documentation 19 | `docs/open-items.md:108,122` | **OPEN.** ":108 The symbol exists; the LGA-25 land pattern does not" — it exists, at `hardware/footprints/lyrebird.pretty/Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm.kicad_mod`, and it carried the transposition. ":122 the ferrite is at `VBUS`" — there is no ferrite, while `main-reva/power.md:172` calls the same absence a *defect*. Two live documents treat one fact oppositely |
| documentation 33 | `0008:52-53`, `open-items.md:182`, `dac-reva/brief.md:38-39` | **OPEN.** `model/README.md:149` says "One percent mismatch costs **33.3 dB** with rotation, not 0.5 dB"; 0008 still says one percent is "adequate" unqualified, `open-items.md:182` inverts the correction ("33 dB without and 0.5 dB with"), and `brief.md:38` quotes "0.5 dB against 70 dB without it". The parts fitted are 0.1 % thin film, so only the documents are wrong |
| documentation 35 | `0013:106-120` | **OPEN, confirmed against the builds.** `hdl/build/` holds four designs; 0013 tabulates two. `lyrebird_elastic` is **612,869 bytes**, `CPE_LT 8256/40960 (20 %)`, `RAM_HALF 50/64`. So "both designs are still under one percent of the part" is false, "2 Mbit leaves only about 1.4 times headroom" is **0.43×** (2 Mbit = 262,144 bytes) so 2 Mbit is excluded rather than thin, and "Do not pick a flash part" is overtaken by `U6 MX25R6435F 64Mb` already fitted. The flash choice is sound; 0013 is the only document still calling it open. (The same `RAM_HALF 50/64` independently confirms 0011 — documentation 20.) |

### Item 20 · Two model figures the hardware rests on: one unsourced and load-bearing, one mismarked as a datasheet value
**Kind:** orphan (both `[MODEL→HW]`; the power review, which owns the rail
arithmetic, raised neither) · **Sources:** documentation 32, 34 · **State: both
OPEN, one partly mitigated.**

**The 0.37 mA per element filter capacitor (documentation 32).** Verified still
live and still underived: `dac-reva/power.md:106-111` gives "about **0.37 mA**
per element averaged over a cycle" and `28 x 0.37 mA = 10.4 mA`, repeated at
`parts-notes.md:341`. `28 × 0.37 = 10.4` is internally consistent, but the 0.37
has no derivation anywhere, on a page whose own opening rule is "shows the
arithmetic behind every number" and which shows it for every other figure
including the 13.92 mA immediately above. Documentation 32's own application of
the page's `I = C·V·f` to 180 pF at 12.288 MHz gives **7.34 mA** at the full
rail, **3.63 mA** at the midpoint node's 1.64 V swing and **about 1.0 mA**
allowing for the 1.06 MHz pole the capacitor sits behind — 1–7 mA per element,
**27–205 mA across 28**.

This matters more than its size suggests, and the power review's silence is the
notable part: it is the dominant *non-constant* term on `+3V3_REF`, the rail
`docs/open-items.md:10-61` calls the project's largest risk, and
`reference-current.txt` scales its −101.1 dBFS prediction through it —
the figure `interface.md:123` and `open-items.md:27` both now carry as the
project's lead open item.

Partly mitigated since the review: the figure is marked `(estimate)`,
`dac-reva/power.md:116-118` now defers it to measurement with the modulator
running, and `interface.md:107-122` documents the mechanism properly (the DWA
pointer advancing by the code makes the count of changing lines a full-wave
rectification of it, so the current is signal-correlated; eight 100 nF parts
are about 100 Ω where that lives against the 170 µΩ the chain's floor would
need). So the *reasoning* is now sound and recorded; the *number* is still a
bare estimate carrying a −101 dBFS prediction.

**Two provenance marks that contradict the same page (documentation 34).**
Verified still live on a page whose stated discipline is provenance marking,
two of five rows in the clock-rail table:

- `dac-reva/power.md:179` — "CCHD-957, running \| 15.5 \| **datasheet**, 15 mA
  typical and 25 mA maximum" against `:189` of the same file,
  "`I_running = 17 - 1.5 = 15.5 mA` **(calculation)**". It is a
  back-calculation from 0012's 17 mA, and it disagrees with the datasheet's own
  15 mA typical — which documentation 17 confirmed exact against rev N — by
  0.5 mA.
- `dac-reva/power.md:182` — "LMK1C1104 fanout buffer \| 10 \| **datasheet**,
  current against frequency at 24.576 MHz" against `:391`, "Read off a **curve**
  rather than a table; the tabulated figure is 33 mA at 100 MHz with four
  outputs loaded".

Neither changes a verdict — the rail totals 33.5 mA against 35.5 mA of `+5V`
and `verify_power.py` reports +1225 mV of dropout margin on U6 — but both are
marked as the strongest class of evidence on a page that exists to distinguish
the classes, and one of the two parts was selected on the figure. See also
schematic 29, in item 18: two of this module's *datasheet* figures are
themselves wrong, in the safe direction.

### Item 21 · `hardware/netlist/README.md` has not been touched since 12 September and every flag against it stands
**Kind:** corroboration of a kind — six flags, one file, one cause · **Sources:**
schematic 14–20 · **State: all OPEN, verified.**

The file is dated 12 Sep 21:53, before every change in this round. Verified
against the tree:

- **schematic 14** — `:16` "It holds **two** symbols so far", and it tabulates two.
  `hardware/symbols/lyrebird.kicad_sym` holds **seven**: `LTM4622`,
  `MX25R6435F`, `SN74ALVCH16374`, `SN74LVC1G74`, `LMK1C1104`, `CCHD-957`, and
  `LTC3265` — the last one dead, the charge pump deleted by 0015, referenced by
  no generator. `check_freshness.py` has `"LTC3265"` in `SUPERSEDED` but scans
  only `.md` and `.csv` (`:304-306`), so a `.kicad_sym` is outside it.
- **schematic 15** — `:24` "The LTM4622 still needs a footprint drawn; its `Footprint` field names
  `lyrebird:Analog_LGA-25_…`, **which does not exist yet**." It exists, and it
  carried the axis transposition. The sentence would have told a reader not to
  look.
- **schematic 16** — `:55-58` lists four placeholders (`ASE-xxxMHz`, `74AUP1G74`,
  `74HCT574` pairs, `OPA1612AxD`); all four are now selected real parts
  (CCHD-957, SN74LVC1G74 + LMK1C1104, SN74ALVCH16374, OPA1612AID). `:152` still
  says "The element resistor value is still a placeholder"; it is 1.69 k + 1.65 k.
- **schematic 17** — `:121` "So the flow stops at the netlist." `regenerate.sh`
  drives `tools/netlist_to_sheets.py` and `kicad-cli` to **19** sheet files and
  two PDFs (schematic 17 says 20; the conclusion it draws is unaffected).
- **schematic 18** — `:71-73` "The absolute maximum is asserted, not reviewed"
  describes what the check catches and nothing about what it cannot see. After items 2, 3 and 4 it
  should name four blind spots, three of which are now tamper-demonstrated.
- **schematic 20** — `:155-165` "Pins left open on purpose" omits FT601Q
  `~{WAKEUP}` (verified
  unconnected, pin 16), the translator's `1A2`, the registers' `1Q8`/`2Q8`, the
  buffer's `Y3` and the LT3094's `VIOC`.

Both `missing.md` files also still document a command that raises
(schematic 19), verified by inspection: `for part in b.build():` then
`part.pins`, where `main_board.build()` returns `(fpga, ftdi, elem_nets)` — the
third is a list — and `output_module.build()` has no `return` at all. Both
files present this as the way to regenerate the authoritative open-pin list,
which is the measure `hardware/README.md:9-12` calls "the honest measure of how
finished a board is".

### Item 22 · Four flags where a review pointed at a section whose own reviewer said nothing
**Kind:** orphan — silence from the owning section · **State: all OPEN.**

These are power-design questions raised by the schematic reviewer. The power
review's 59 flags do not mention any of them, and that silence is information:
it means one person has looked, not two.

- **schematic 7 — five FPGA supply pins have no decoupling capacitor.**
  Verified exactly. `main_board.py:856-859` keys its decoupling loops on
  `^VDD$` (28 balls) and `^VDD_(NA|NB|EA|EB|SA|SB|WA|WB|WC)$` (9 balls), so
  `VDD_PLL` (P16), `VDD_SER` (U12, V17), `VDD_SER_PLL` (T16) and `VDD_CLK`
  (T14) get none. The first three are on `+1V0`, the last on `+2V5`. DS1001
  §2.10 asks for noise **filters**, not capacitors, on the core-domain
  supplies, and none is fitted. `VDD_CLK` matters most: `+2V5` also supplies
  `POR_ADJ`'s divider (R22, 47 k, verified) and the POR that R3a detunes.
  Worth noting alongside: `assert_core_rail` protects exactly the three pins
  whose decoupling is missing, and correctly excludes `VDD_CLK`, which is a
  2.5 V pin.
- **schematic 8 — R3a is used outside its documented purpose.** `R22 = 47k 1%`
  from `POR_ADJ` to `+2V5` with `C28 = 2.2uF`, verified. DS1001 §3.2.2 says
  `POR_ADJ` should be left open with `VDD_CLK` in 1.8–2.7 V, which it is; the
  arithmetic is exactly right and the orientation is right, but the reset
  threshold on that rail drops from ~1.44 V to ~0.66 V and Table 4.8
  characterises R3a only at 250 k and 500 k.
- **schematic 11 — `USB_VBUS` reaches the FT601Q with nothing on it.** Verified:
  a two-node net, `J1.1 (POWER-OUT)` to `U2.37 (VBUS, PWRIN)`, no capacitor, no
  series resistor, no TVS, straight from a cable-facing contact. `USB_VBUS` is
  declared in the main board's `hv_rails`, so the check knows it is dangerous
  and the bridge's supply pin is skipped by construction. Whether pin 37 is a
  supply or a sense input could not be established without the FTDI datasheet.
- **documentation 14 — the thermal-via requirement.** See item 10.

### Item 23 · Superseded-string coverage: the recommended fix was taken, the spelling gap was not
**Kind:** corroboration, half-closed · **Sources:** documentation 25 (closed),
documentation 26, 27, 29 · **State: mixed, verified.**

Documentation 25 recommended keying the superseded-string exemption on a
record's Status line rather than exempting `docs/decisions/` wholesale. **That
is exactly what was done**: `SUPERSEDED_OK` is now
`("docs/review/", "CHANGELOG", "notes-")` and `is_superseded_record()` reads the
head of a file for "superseded by". Closed, and implemented as advised.

The rest stands, and the run reports `0 stale`:

- **documentation 26 — the keys are literal.** Verified live in the tree:
  `"604R"`/`"604 ohm"` miss **`604 Ω`** (`parts-notes.md:66,90,93,98,101,418`,
  `dac-reva/power.md:238,240,266`, `dac-reva/brief.md:106`);
  `"one unit load"` misses **`one-unit-load`** (`hardware/README.md:72`,
  `parts-notes.md:310`); `"USB bus power"` misses **`Bus powered`**
  (`hardware/README.md:48`, `main-reva/power.md:3`), **`Bus power and data`**
  (`hardware/README.md:39`) and **`Bus powered from a single USB cable`**
  (root `README.md:70`).
  `"SMAJ15A"` no longer has a live miss — 0014's "a 15 V TVS" was fixed.
- **documentation 27 — BOM coverage.** `check_bom` filters `r[0] in "UJYFLD"`
  (`:197`), so "dac: BOM covers every major reference, 17 checked" is 17 of 112
  and excludes all 17 `RN` arrays — the 28 elements and the difference network.
  It compares reference sets only and never values, which is why item 8's
  self-contradicting BOM row passes.
- **documentation 29 — the timestamp pass and the string scan cannot cover what
  they do not list.** The scan takes `.md` and `.csv` only, so every stale
  comment in item 18 and the dead `LTC3265` symbol are outside it. The four
  timestamp warnings the run emits are all correct and all four documents are
  in this report.
- **documentation 28 — nothing asserts a documented number against the
  netlist.** Still true, and it is the single change that would close most of
  items 6, 8, 19 and the `RN` half of documentation 27 at once.
  `check_footprints` is the one check of the right shape, and its
  `FOOTPRINT_RULE` covers only `LT3045` and `LT3094` — not the LMR33630 whose
  land was wrong (§2) nor the LTM4622 whose land was transposed.

### Item 24 · Remaining `power_input_transient.py` drift
**Kind:** known open (context) · **Sources:** power PWR-V7–V13 · **State: OPEN,
all verified by running it.** The file is dated 24 Sep and nothing in it has
moved.

- **PWR-V7 — a passing run emits a false warning about a fixed fault.** The
  header prints `NOTE: main_board.py says "1.1 A hold, 2.2 A trip".` and "No
  1812L part has 1.1 A hold with a 2.2 A trip above 6 Vdc". `main_board.py`
  says `1812L050/30 PPTC 0.5A hold 30V 100A`. The constant to change is
  `F1_NETLIST_VALUE`.
- **PWR-V9** — docstring says "all twelve of its checks pass" (18); the ASCII
  art still draws `D2 SMAJ15A`; scenario 4 still promises "the `WAKEUP_N` core
  gating that 0014 says was retired **and the netlist still builds**" — the
  netlist has not built it for two rounds (no `Q1`; it survives only in the
  stale `.kicad_pcb`, item 17).
- **PWR-V10** — `D2_ALPHA = 0.088e-2`, annotated as the SMAJ15A row, applied to
  an SMAJ18A, and the file's own tamper shows this one constant decides the
  19 V case.
- **PWR-V11** — `F1_TTRIP_8A` assigned twice (`:182` 0.15 s, `:185` 0.50 s,
  both marked `datasheet`); the derivation above it uses `I_hold = 1.10 A`, the
  superseded part; the run prints `tau 127.7 s`, implying an implausible
  0.30 J/K for an 1812 body. No verdict depends on τ.
- **PWR-V8** — `I_LOAD_5V = 0.472 A` sourced to "238 mA module + 234 mA main"
  (now 357 mA total, 123 mA module) and `I_MEZZ = 0.238 A`, which sets `Rmezz`,
  the load the sequencing model actually drives.
- **PWR-V12, PWR-V13** — S-4's verdict is
  `glitch_peak < 0.05 or rows["+1V0"]["t90"] is not None` (`:1096`), which a
  rail that reaches 998 mV and collapses passes; S-6 computes its verdict from
  the no-host run and prints `rows_h['+1V0']['peak']` from the host run
  (`:1126`).
- **PWR-V3, PWR-V5, PWR-V6** in `verify_power.py` — the FT601Q skew check's two
  inputs are bare literals in a `ramps` list (`:350-352`) rather than `Fact`s;
  the inverter current check compares 63.5 mA against `0.3 × 3 A` where the
  topology limit is 2.21 A (right verdict, wrong number); and `I_3V3`'s note
  "FT601Q VCC33 + flash" is wrong about the flash — verified, `U6` pin 8 sits
  on **`+2V5`**, which also means the 2.5 V constant omits it.

---

## 2. Closed since the reviews, verified — do not re-report

Each was a real finding. Each is confirmed closed in the tree as it stands, by
the evidence named.

| Was | Now | Verified by |
| --- | --- | --- |
| **PWR-S1** — both LMR33630s on `Package_SO:HTSSOP-8-1EP_3x3mm_P0.65mm` on an HSOIC-8 part. Build-stopping | `Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm_ThermalVias` on U5 and U7 | `lyrebird-main.net`; both `bom.csv` Package columns now match and their `VERIFIED` marks are earned |
| **PWR-S1**, second half — nothing stopped a symbol's own footprint being overridden | `lp.assert_symbol_footprints` fails the build on an unexplained override, with a `justified` map for the one legitimate case (`U8`, whose KiCad `LT3094xDD` symbol carries an MSOP-12) | `lyrebird_parts.py:183-229`; both boards build |
| **schematic 1** — the 1.20 V core maximum unguarded; `+2V5` on a `VDD` ball passed | `lp.assert_core_rail` with `CORE_ABS_MAX_V = 1.20`, asking whether only allowed names appear rather than whether an allowed name is present | tamper: core rail moved to `+3V3` → caught; to `+2V5` → caught; a single 10 k from `+2V5` to one `VDD` ball → caught (`R33 bridges the core rail to +2V5`); `+1V0` shorted to `+2V5` → caught, 44 pins. **Three residual gaps: items 3 and 4** |
| **schematic 6 / PWR-S3** — the module's `hv_rails` omitted `-6V_A` and declared four deleted pump rails | `-6V_A` declared; the dead names replaced by a comment explaining the membership weakness | `output_module.py:705-716`. **But see item 2** |
| **PWR-S2 / schematic 2** — no capacitor across U7's own terminals | `C15` 10 µF + `C16` 100 nF from `+12V` to `-6V_A` | `lyrebird-main.net`. **Residual: item 9** |
| **PWR-S5 / schematic 23** — `-6V_A` at pins 71/72, immediately beside `ID0`/`ID1`, with no ground in 65–70 | pins 73/74, with full ground columns at 71/72 and 75/76; both netlists agree on all 80 pins; the half-insertion reasoning retained; `interface.md:46-56` documents it | both netlists. **But see item 6** |
| **documentation 21 / schematic 4 / PWR-S6** — U14's SET resistor above what its input can supply | `R10 = 40.2k 0.1%`, +433 mV on the dropout bound and +510 mV on the swing bound | `lyrebird-dac.net`; `verify_power.py` reports +511 mV. **Documents: item 8. Ramp side effect: item 19** |
| **documentation 22 / PWR-V1** — the dropout check covered only the regulator that could not fail | all six post-regulators read from the netlists, with stacked corners | `verify_power.py` run: 18/18, U3 + U5/U6/U8/U9/U14. **Residual: item 12** |
| **documentation 23** — `PG_5V`/`PG_N6V` each constructed twice, giving four single-node nets | `PG_5V` = `R1`:1 + `U5`:4; `PG_N6V` = `R4`:1 + `U7`:4 | `lyrebird-main.net` |
| **documentation 24** — no single-node-net check | `check_freshness.check_single_node_nets`, with a four-entry reasoned allowlist | run: both boards ok; the only single-node nets in either netlist are `ELEM28`–`ELEM31` on the module, exactly the allowlist. **Residual: it counts nets, not pins — and see item 15 on ERC** |
| **documentation 18 / schematic 15** — the LTM4622 land pattern transposed | A–E along x at 1.27 mm, 1–5 along y | the `.kicad_mod`'s 25 pads. **The stale open-item entry: item 19** |
| **schematic 30 / PWR-D3** — the USB SuperSpeed pairs wired with no driving pin | removed; `grep -c 'SSTX\|SSRX'` over `lyrebird-main.net` returns 0 | netlist. **The comment and 0014's bullet: item 18** |
| **documentation 36** — the largest power change in the repository had no decision record; "decision 5" appeared in twelve files | `docs/decisions/0015-negative-rail-across-the-mezzanine.md`, which opens by recording that it was missing | the file. **Two of its own constants: items 6 and 8** |
| **documentation 1** — 0014 specified a 15 V TVS against a fitted SMAJ18A | `0014:37` now reads "an **18 V** TVS — 15 V when this was written, changed because a 15 V part conducts on a 19 V adapter" | 0014; `D2 SMAJ18A` in the netlist |
| **documentation 2** — 0014's "the module is untouched", three of four claims false | struck through at `0014:126-127` with "**Done by 0015**" | 0014 |
| **documentation 30 / PWR** — 0014's "noise-optimal 2585 Ω … costing 1.1 dB" | struck and replaced at `0014:76-87`, and `dac-reva/power.md:326-331` now states the monotonicity correctly and prices it at 0.67 dB | both files |
| **documentation 25** — `SUPERSEDED_OK` exempted all of `docs/decisions/` | keyed on the record's Status line via `is_superseded_record()`, as recommended | `check_freshness.py:61-83`. **Spelling gap: item 23** |
| **schematic 10** — the clock-chain part selection rested on the retired budget | `parts-notes.md:216-222` now says "the reason for rejecting it has since evaporated, and the choice survives anyway", with a new reason | parts-notes.md |
| **PWR-S7** (first half) — both BOMs carried the wrong footprint for U5/U7 *and* were marked VERIFIED | correct footprint, mark earned | both `bom.csv`. **Capacitor ratings: item 9** |
| **PWR-V2** — `U3_DROPOUT` was the 500 mA figure | `Fact(0.330, "V", DS, "LT3045 max at 1-50 mA, not the 500 mA figure")` | `verify_power.py:84`. Residual, as PWR-V2 says: it is applied to U8, an LT3094 whose own figure is 235 mV — conservative, so harmless |

**Confirmed correct, do not re-open:** documentation 16 (the CCHD-957 footprint
is not oversized — retracted by its own author, and item 1 confirms the geometry
independently), documentation 17 (every other CCHD-957 figure in
`parts-notes.md` is exact against rev N), documentation 20 (0011 reproduces:
`RAM_HALF 50/64`), schematic 12 (open items E-4 and E-5 are arithmetically
correct; `VDD_SER`'s 1.00 V minimum is missed at nominal and centring on `VDD`
is the right call), PWR-S9's assessment that `assert_core_rail` is correctly
built — asking whether *only* allowed names appear is the distinction that makes
it work at all, and the tamper results in §2 confirm it.

---

## 3. What this pass could not settle

Named rather than guessed at.

1. **CCHD-957 pad 1: 0° or 180°** (item 1). The footprint is self-consistent and
   the "90°" claim is refuted, but which corner Crystek calls pad 1 cannot be
   read from the PDF text layer. This is the one open item that can destroy
   both oscillators, and it blocks fabrication.
2. **The +3V3 / +2V5 / +1V0 currents** (item 10, PWR-O1). Three dissipation figures
   for U3 — 102 mW, 315 mW, "roughly 400 mW" — and nothing in the repository
   adjudicates. Needs the FT601Q's `VCC33` figure and a GateMate number that
   depends on a bitstream.
3. **Whether the bank-2 window is a fault or only a violation** (item 5, PWR-O3).
   Turns on the 74AVC4T245's `Ioff` behaviour with VCC(A) *partially* powered,
   and on the SN74ALVCH16374's input current with VCC below the driven level.
   SCES576I was not fetched by any of the four passes. The remedy is needed
   either way, because the comment claims coverage the circuit does not have.
4. **Bitstream load time against the module's rail ramps** (PWR-O2). The
   elastic design is 612,869 bytes; `MUTE_N` is an FPGA output and the module
   returns no power-good, so nothing sequences configuration against the
   analog rails. Compounded by the fact that cutting a `C_SET` is no longer a
   free remedy in any direction (item 5).
5. **Loop stability of U7 in inversion** (PWR-O4) and **the topology's absence
   from its own datasheet** (schematic 13). SNVSAN3F contains no inverting
   buck-boost configuration; every absolute maximum the topology stresses does
   check out, but the configuration rests on TI application notes no pass has
   fetched. Benign at 63.5 mA; not transferable if the rail's load grows. Two
   reviews reached this from different directions and neither could close it.
6. **The LTM4622 generally** (PWR-O5). Efficiencies `ASSUMED`, RUN and feedback
   figures reaching the repository through a review rather than a datasheet,
   and a land pattern found transposed. Wants its own datasheet pass.
7. **Whether the FT601Q's `VBUS` pin is a supply or a sense input** (item 22,
   schematic 11). The datasheet was unobtainable in both the schematic pass and
   this one, so the two-node net cannot be judged.

---

## 4. If only five things are done

Ordered by cost of getting them wrong, not by effort.

1. **Settle the CCHD-957 pad numbering from the drawing** (item 1), and delete
   "rotated 90°" from `0012` and `dac-reva/brief.md` whatever the answer is.
2. **Make the abs-max allowance per pin, and add the module's logic parts to
   `protected`** (item 2). Four lines; it is currently the only guard on the
   mezzanine contract and the negative rail walks straight through it.
3. **Extend `assert_core_rail` to `[fpga, ftdi]`, walk bridges of any pin
   count, and fail when a check finds no subjects** (items 3, 4 and 12). One
   function, three gaps, all three tamper-demonstrated, and the same
   subject-count convention closes PWR-V1.
4. **Gate `2~{OE}` against VCC(A), and stop `interface.md` claiming the
   oscillator rule is enforced until it is** (item 5).
5. **Fit `1.65 k + 1.65 k`** (item 11). Both reviews agree, it is better on every
   surviving criterion, and it removes a part number.

Two documentation changes are worth as much as any of these and cost less:
strike the "What has no source today" section from `main-reva/power.md`
(item 19 — four false claims in five sentences, about the rails that power the
FPGA), and correct the U14 voltage in `make_bom.py:151`, which is the one stale
constant that reaches a board house (item 8).

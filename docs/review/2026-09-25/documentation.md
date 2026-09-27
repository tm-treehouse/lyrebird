# Documentation review — 2026-09-25

Scope: `docs/decisions/0001`–`0014` + index, `docs/open-items.md`,
`hardware/interface.md`, `hardware/README.md`, `model/README.md`, both boards'
`brief.md` and `power.md`, `hardware/lyrebird-dac-reva/parts-notes.md`, and an
audit of `hardware/check_freshness.py` itself.

Ground truth used throughout: the two generated netlists
(`lyrebird-main.net`, 159 components / 142 nets; `lyrebird-dac.net`,
112 components / 133 nets, both regenerated 2026-09-25 19:52), the local
footprint and symbol libraries, `hardware/verify_power.py`, `hdl/build/*`,
and `model/results/*`.

Method note. Every assertion below names a file and line and says what the
correct value is and where it came from. Where the repository does not contain
the evidence to settle a claim — `hardware/datasheets/` is empty, so no vendor
PDF is checkable — the finding says "cannot verify" rather than guessing.

---

## 1. The freshness checker: what it structurally cannot see

`hardware/check_freshness.py` reports `0 stale, 0 to look at, 4 clean`. That
result is close to uninformative. Nine distinct blind spots, in rough order of
how much real staleness each one is currently hiding.

### 1.1 Every decision record is exempt from the only content check

`check_freshness.py:73`

    SUPERSEDED_OK = ("docs/decisions/", "docs/review/", "CHANGELOG", "notes-")

The superseded-string scan is the only check in the file that reads prose, and
`docs/decisions/` is excluded wholesale. The stated reason — a decision record
is "the record of the change rather than a description of the board" — is true
of the *superseded* record and false of the *superseding* one. `0014` is the
current power authority for this project, and it contains, at line 116:

> the mezzanine still carries +5V, the **LTC3265** charge pump is still fitted,
> and the difference network is still 604 Ω

`LTC3265` and `604 Ω` are both on the checker's own `SUPERSEDED` list, both are
asserted here in the present tense, and both are false against
`lyrebird-dac.net` (no LTC3265 component exists; `RN16`/`RN17` are
`200R, 0.1% RATIO matched, thin film array`). The exemption is what hides it.

**Section 4 is this check run by hand over those fourteen files.** It also
revises the obvious remedy: deleting the exemption trades one real catch for
five false positives, and the sound fix is to key it on each record's own Status
line (§4.1).

### 1.2 The superseded strings are literal, so paraphrase walks straight past

The map is keyed on exact substrings. Three that are currently evaded:

| `SUPERSEDED` key | What the stale document actually says | Where |
| --- | --- | --- |
| `"USB bus power"` | "Bus powered, no external input" | `lyrebird-main-reva/power.md:3` |
| `"USB bus power"` | "Bus power and data, one cable" | `hardware/README.md:39` |
| `"one unit load"` | "the one-unit-load limit" (hyphenated) | `hardware/README.md:72` |
| `"SMAJ15A"` | "a 15 V TVS" | `docs/decisions/0014-wall-wart-power.md:37` |

The hyphen case is the sharpest: `"one unit load" in "the one-unit-load limit"`
is `False`, and that line is a live instruction to gate the FPGA rails on a
rule that 0014 retired.

### 1.3 The paragraph window exempts a whole paragraph on one word

`check_freshness.py:264-269`

    start = i - 1
    while start > 0 and lines[start - 1].strip():
        start -= 1
    context = " ".join(lines[start:i + 1]).lower()
    if any(m in context for m in HISTORICAL):
        continue

`HISTORICAL` (line 78-82) includes `"closed"`, `"deleted"`, `"retired"`,
`"removed (was"`, `"there is no "`, `"no longer"`. These are among the most
common words in this repository's prose. Because the window is the whole
paragraph up to the hit plus one line, **a single occurrence of any of them
anywhere earlier in the paragraph exempts every superseded string later in that
same paragraph.** In a document whose house style is "here is what changed, and
here is the current state", that is precisely the paragraph shape where a stale
current-state sentence will sit. `hardware/lyrebird-dac-reva/power.md:369-372`
is a live example of the shape: a paragraph containing `deleted` three times, in
which a sentence about the alternatives would be unscannable.

### 1.4 The blockquote exemption is a general-purpose opt-out

`check_freshness.py:273` skips any line starting with `>`. But the five
corrections added on 2026-09-25 are *all* written as blockquotes (0002:5,
0005:8, 0007:6, 0012:7, 0013:5). Those blocks are not quotations of superseded
text — they are the newest and most authoritative prose in the repository, and
they are the only part of a decision record that a reader is told to read first
(`0007:4`: "Read the correction first"). They are also, by this rule,
unscannable. An error introduced *in a correction* is invisible twice over:
once for being in `docs/decisions/`, once for being in a blockquote.

### 1.5 BOM coverage ignores 91 % of the parts, and never compares values

`check_freshness.py:178`

    interesting = {r for r in np_ if r[0] in "UJYFLD"}

`R`, `C`, `RN` and `Q` are excluded. On the DAC board that skips 64 capacitors,
14 resistors and — the entire point of this converter — **all 17 `RN` resistor
arrays, which are the 28 elements and the difference network.** "BOM covers
every major reference, 17 checked" on a 112-component board means 17 of 112.

Worse, the module docstring (line 22-24) promises "Every reference in the
netlist should appear in the BOM **with the same value**". `check_bom` computes
`missing` and `extra` by reference only; `np_[r]` and `bp[r]` are never
compared. A part revalued in the netlist and not in the BOM — which is stated
as the thing timestamps cannot catch — passes. This is a documented check that
does not exist in the code.

### 1.6 The timestamp check cannot fail after `regenerate.sh`

All netlists, sheets, PDFs and BOMs carry mtime 2026-09-25 19:52; the two
generators are dated 2026-09-24. Since every derived artifact is rewritten in
one batch, the comparisons at `check_freshness.py:139-166` are a test of
"was `regenerate.sh` run recently", not of whether anything describes anything.
The doc-vs-generator warning (line 159) deliberately compares against the
generator rather than the netlist for good stated reasons — but that means a
document edited five minutes *before* a design change, then not touched, only
warns; and the check covers just `power.md`, `brief.md`, `bom.csv`.

### 1.7 Six of the eleven in-scope documents are not timestamp-checked at all

`check_freshness.py:159` lists `("power.md", "brief.md", "bom.csv")` inside the
two board directories. Not covered anywhere: `docs/decisions/*` (14 files),
`docs/open-items.md`, `hardware/interface.md`, `hardware/README.md`,
`model/README.md`, and — notably, since it sits in a board directory next to
two files that *are* checked — `hardware/lyrebird-dac-reva/parts-notes.md`.

### 1.8 Only `.md` and `.csv` are scanned

`check_freshness.py:241`. So `hardware/verify_power.py`'s embedded prose,
`hardware/netlist/*.py` comments, `hdl/**/*.sv`, `model/export/coefficients.json`
and `hdl/rtl/lyrebird_coeffs_pkg.sv` are outside the scan. `verify_power.py:102`
carries the comment `"main power.md is stale"` next to a constant that
disagrees with `power.md` by 3×; nothing correlates the two (section 4.3).

### 1.9 Nothing checks a number against its source

The three checks are timestamps, reference-set equality, and a hand-curated
nine-entry string list. No check ties a figure in prose to a netlist value, a
`model/results/*` line, or a `hdl/build/*` artifact. Every finding in sections
2 through 5 below is of that kind, and none of them contains a superseded
string. Concretely: the checker cannot see that `open-items.md:145` says the
DAC netlist has "126 components and 144 nets" when it has 112 and 133, nor that
`open-items.md:154` says the reconstruction filter is "2.0 nF and 1.3 nF" when
the netlist fits 3.9 nF.

### 1.10 One thing the checker does get right, and it is worth keeping

`check_footprints` (line 202) asks the netlist rather than the prose, and the
docstring at line 192-195 says exactly why the string-matching version failed.
That is the right shape, and it is the only check here that is immune to
rewording. Both regulator footprints pass genuinely: `U3` on
`DFN-10-1EP_3x3mm` and `U8` on `DFN-12-1EP_3x3mm`, verified in the netlists.
The lesson generalises and has not been generalised: the same structural
approach applied to component counts, rail voltages and BOM values would catch
most of section 3.

### 1.11 The `.kicad_pcb` files are not checked, and both are thirteen days behind

This is the largest single gap, because it is the *same* failure the checker's
own docstring was written about. `BOARDS` (line 43-56) names `net`, `gen` and
`pdf`; it never names the board file. Both are dated 2026-09-12 against
netlists dated 2026-09-25, and both contain a pre-0014 design:

| Board | Evidence |
| --- | --- |
| main | `lyrebird-main.kicad_pcb` holds **`FB1`** (an `L_0603_1608Metric`, the deleted VBUS ferrite) and **`Q1`** (a `SOT-23`, the deleted `WAKEUP_N` NMOS). It has no `J4` barrel jack, no `U5`/`U7` LMR33630s, no `F1`, `D1`, `D2`, `D3`, `L1`, `L2`, and only `C1`–`C100` against the netlist's `C1`–`C109`. |
| dac | `lyrebird-dac.kicad_pcb` holds 16 capacitors, 5 resistors, 7 `RN` and `U1`–`U9` with split `U3a`/`U3b`/`U4a`/`U4b`; the netlist has 64 capacitors, 14 resistors, 17 `RN` and `U1`–`U14`. No `U10`–`U14`, no `J2` jack. |

Both have zero `(segment` entries, so "zero tracks" is true. But
`lyrebird-main-reva/brief.md:95-96` says the board file "holds placed
footprints **from the netlist import**", and it does not: it holds footprints
from a netlist that showed bus power and a charge pump — verbatim the condition
the checker exists to prevent.

### 1.12 ERC is not run, and unconnected pins are not counted

Every `*.erc` file in the repository is zero bytes. `main_board.log` ends
`324 warnings found`, `0 errors found`, and "0 errors" is what
`lyrebird-main-reva/brief.md:73` reports as "runs clean". Meanwhile
`hardware/README.md:9-12` states the project's own measure of completeness —
"Unconnected pins in the generated netlist are the honest measure of how
finished a board is" — and nothing computes it. Section 5.1 is a real defect
that this gap hides.

**Partly closed during this review.** `check_freshness.py` now reports nets with
a single node, which caught four of them on the main board — see cross-section
item 23 for the fault and item 24 for the check and its residual. It counts
nets, not pins, so a pin attached to no net remains invisible, and no ERC runs.

---

## 2. Verdicts on the fourteen decision records

One line settles each. "Correct" means the record, including any correction on
it, matches the design as built.

| # | Verdict | The line that settles it |
| --- | --- | --- |
| 0001 | **correct** | `lyrebird-main.net` `U2` is `FT601Q`, and 0001:31 named "FT600/FT601, 16 or 32-bit FIFO" as the upgrade path it took. Status line already defers part selection to 0005. |
| 0002 | **corrections correct** | Both are verifiable. `Y1`/`Y2` in `lyrebird-dac.net` are `CCHD-957X-25-49.152` and `-45.1584`, and 0011's 38,400 is exactly 192 000 × 2 × 0.1 s. |
| 0003 | **one stale figure** | 0003:26's "roughly 35 MB/s available" is an FT2232H High-Speed number; the link is an FT601Q and 0005/0014 quote 480 Mbit/s = 60 MB/s. Conservative, so the conclusion holds. |
| 0004 | **correct** | Nothing in the netlists or HDL contradicts it; `hdl/rtl/` contains no USB device controller. |
| 0005 | **amendment correct in substance, one retired paragraph left standing** | 0005:84-85 still reads "**The board is harder.** USB 3.0 SuperSpeed differential pairs need controlled impedance" — which the amendment at 0005:17-19 declares retired. It is also still *true of the netlist*: `USB_SSRX_P/N` reach `U2` pins 34/35 and `J1` pins 6/7 reach `U2` 31/32 through `C7`/`C6`. So the amendment describes an intention and the record's body describes the board; a reader cannot tell which is current. See §3.5 for the 1.9 % figure. |
| 0006 | **correct, one instruction overtaken** | `CFG_MD` is strapped 0b0000 (`main_board.py:659-660`, every pin to `GND`) ✓ and `U6` is the flash ✓. But 0006:30-31 says "confirm the actual bitstream size from a first build **before committing the part**" — the part is committed (`MX25R6435F 64Mb` in the netlist) and four builds exist in `hdl/build/`. |
| 0007 | **correction INCOMPLETE** | The 2026-09-25 correction fixes only the I2S boundary. Two power statements survive untouched and both lost their premise with 0014: 0007:76 "This is what keeps the board inside **the tighter budget when it falls back to a USB 2.0 port**", and 0007:80-81 "**Declare worst-case current in the USB descriptor**; it is fixed at enumeration and cannot be renegotiated when a module changes." There is no USB current budget and no declared current. |
| 0008 | **correction correct; the 2018-era mismatch claim still unrepaired** | The correction's numbers trace exactly (§3.1). But 0008:52-53 still says rotation "means ordinary one percent resistors are adequate" with no qualification, and `model/README.md:149` retracts the reading that made that free: one percent costs 33.3 dB, not 0.5 dB. The 2026-09-21 review named this as unrepaired in 0008; it is still unrepaired. Also 0008:89 and :95-96 argue from "an oversampling ratio of 256" and "a 24.576 MHz master clock against a 96 kHz sample rate"; 0010 added 192 kHz, where the ratio is 128. |
| 0009 | **correctly marked superseded, but still load-bearing** | The status line is right. What is wrong is that seven other documents cite it as live authority for things 0014 retired (§4.4), and 0009:44's "It dissipates roughly 400 mW, so tie the exposed pad to plane with thermal vias" is contradicted by `verify_power.py`, which computes 102 mW for the same rail. |
| 0010 | **correct; one arithmetic slip in the superseded table** | The rate encoding checks out (48 kHz = 0x10, 96 = 0x11, 192 = 0x12, 44.1 = 0x00, stage count = 9 − multiplier) and the ratio table is exact. 0010:90 says 192 kHz at 50 ms prefill needs 20 blocks of TDP 40K; 9 600 frames is 19 200 samples and 19 200 / 1 024 = 18.75 → **19 blocks**. The figure was got by doubling the 96 kHz row. |
| 0011 | **correct, and the best-verified record in the set** | Every row reproduces, and the build confirms the conclusion independently: `hdl/build/lyrebird_elastic.pnr.log` reports `RAM_HALF: 50/64`, which is exactly 25 of 32 blocks and leaves 7 free, as 0011:35 and 0011:52 state. |
| 0012 | **amendment half right; its footprint claim is wrong and its defect claim is unverified** | Divider and fanout ✓ (`U1 SN74LVC1G74DCUR`, `U12 LMK1C1104PWR`, 6 mA + 10 mA = the stated 16 mA). The 73 fs integration reproduces to 0.5 fs when computed independently. The 3.3 V element rail ✓ (`+3V3_REF` at 3.32 V, set by 33.2 kΩ on `U5` SET). **But "The oscillator footprint is drawn, 9 × 14 mm" is wrong** (§3.6) and "Its pad *numbering* is still wrong — rotated 90°" is asserted as a known defect where `parts-notes.md:296-299` records it as a thing to check (§3.7). |
| 0013 | **correction announces a fix it did not make** | 0013:5-8 says "This record contradicted itself two table rows apart: git-lfs was listed as 'installed' and as '**missing**'. The tool is installed; the repository is **not configured to use it**." Both rows are still in the table: 0013:136 (correct) and **0013:138 `\| git-lfs \| **missing** \|` (still there)**. The correction describes the contradiction accurately and leaves it in place. The bitstream figures are worse than "stale" (§3.2). |
| 0014 | **three of four "not yet done" bullets are false, plus a wrong TVS and a misread model figure** | 0014:116-118 says "The module is untouched. The mezzanine still carries +5V, the LTC3265 charge pump is still fitted, and the difference network is still 604 Ω." `lyrebird-dac.net` contains no LTC3265, `RN16`/`RN17` are `200R, 0.1% RATIO matched, thin film array`, and `J1` pins 71/72 carry `-6V_A`. 0014:37's "a 15 V TVS" is `D2 SMAJ18A` in the netlist. §3.3 for the 2585 Ω claim. |

`docs/decisions/README.md` — the index is accurate about which records were
corrected, but 0014's row says only "Supersedes 0009"; nothing warns that
0014's own forward-looking section is now the stalest passage about the module
in the repository. And line 22 uses the phrase "**decision 5**" inside a table
of links to 0001–0014 (§4.1).

---

## 3. Quantitative claims traced to evidence

### 3.1 What does reproduce, so the failures below are not the pattern

Verified against the logs and reproduced independently where arithmetic
allowed. Recording these because the list that follows is short by comparison
and would otherwise read as a verdict on the whole model.

* `model/README.md:57-63` interpolation table — byte-for-byte `results/measurements.txt:5-11`.
* `model/README.md:68-75` cost table — `measurements.txt:16-18, 25-30`, all nine figures.
* `model/README.md:91-99` coefficient widths and the 340-adder total — `measurements.txt:39-47`.
* `model/README.md:35-38` order sweep — `measurements.txt:57-60`, all eight figures.
* `model/README.md:123-127` order-2 rotation table — `measurements.txt:70-74`, all fifteen figures.
* `model/README.md:196-203` "chain as it will actually be built" — `results/idle.txt:420-431`, 2^20 windowed column, all twelve.
* `model/README.md:551-558` datapath table — same log, matched column.
* `model/README.md:517-524` ties table including the "as published" column — `results/idle.txt`, and the account of the error is correct.
* `model/README.md:211-213` — 111.5 dB is `programme.txt:106`; 128.6 dB is that row's median −132.3 dBFS against the −3.7 dBFS tone; 1.1 dB and 27.7 dB are that table's own spreads.
* `model/README.md:860-864, 871-877, 883-887` word widths — `results/modarith.txt:11, 31, 35-48`.
* 0012's 73 fs: −169 dBc/Hz over 12 kHz–20 MHz, both sidebands, against a 49.152 MHz carrier gives **72.6 fs**. Independently reproduced.
* 0012's 2.4 dB (20·log₁₀(3.3/2.5) = 2.41), 8 µV → 10 µV (2.5 V and 3.3 V at −110 dB = 7.9 and 10.4 µV), 40.7 ns, 20.3 ns, 24 ns, 147:160, and "a common multiple of 7.056 MHz" (LCM(44 100, 48 000) = 7 056 000 exactly) all reproduce.
* 0011's every row: 512 × 3 = 1 536 samples/block; 38 400/1 536 = 25; 32 × 1 536/384 000 = 128 ms; 32 − 25 = 7.
* 0005's 1.9 %: 192 000 × 24 × 2 = 9.216 Mbit/s; /480 = 1.92 %.
* `parts-notes.md` filter poles: 180 pF across 1.69 k‖1.65 k = 835 Ω → **1.059 MHz** (claimed 1.06); 2.0 nF across 402 Ω → **197.9 kHz** (claimed 198); 3.9 nF across 200 Ω → **204.0 kHz** (claimed 204). All three exact.
* `dac/power.md` arithmetic: 14 × 3.32/3340 = 13.92 mA; 28 × 30 pF × 3.32 V × 12.29 MHz = 34.3 mA; 37 pF × 3.3 × 49.152 MHz = 6.0 mA; 5 pF × 3.3 × 24.576 MHz = 0.41 mA; 6.96 mA × 1 ns / 800 nF = 8.7 µV; 6 × 3.6 = 21.6 mA; 21.6 + 13.9 + 21.0 = 56.5. All exact.
* 0013's 1.4× (262 144 / 184 050 = 1.424) — the arithmetic is right; the input is not (§3.2).
* `verify_power.py` rail programming against the netlist: `V_5V` 1.0 × (1 + 100 k/24.9 k) = 5.016 ✓ (`R2`, `R3`); `V_N6V` 1.0 × (1 + 124 k/24.9 k) = 5.98 ✓ (`R5`, `R6`); `V_3V3` 100 µA × 33.2 k = 3.32 ✓ (`R7`). All three resistor values are in `lyrebird-main.net`.

### 3.2 The seven claims the 2026-09-21 review named: four fixed, three not

`docs/review/2026-09-21/actions.md` item B6 listed seven README claims that
traced to no log. Status today:

| B6 claim | Status |
| --- | --- |
| Ties table "as published" column | **fixed.** `README:517-524` now prints the log's own columns and explains the error. |
| Modulator peak-state table, six-rate sweep not performed | **fixed.** Replaced by `README:860-887`, which matches `modarith.txt`. The six-rate claim is gone. |
| "the fitted gain came out 1.207" | **fixed in framing.** `README:782` now presents it as the error it was, correctly. |
| "−77 dBFS" | **fixed in framing.** `README:793` presents it as the residual of a bad fit and gives the corrected result. |
| **Volume-placement table** | **NOT fixed** — §3.4. The log now exists and the table still disagrees with it, by up to 24 dB. |
| **Alignment margin, three incompatible values** | **NOT fixed** — §3.9. It is now a fourth value, and the log falsifies it. |
| **"−143.1 against −159.5 dBFS"** | **NOT fixed.** Still at `README:746-747`, still in no log (`grep -rn '143\.1\|159\.5' model/results/` returns nothing), and the conclusion drawn from it does not follow from it: 159.5 − 143.1 = **16.4 dB**, where `README:747` says "made the datapath look **18 dB** worse than it is". |

### 3.3 0014's "second 1.1 dB nobody was looking for" misreads `analog.txt`

`docs/decisions/0014-wall-wart-power.md:72-81` says:

> `analog.txt` Q1c measures the **noise-optimal element resistor at 2585 Ω**,
> giving 133.5 dB, and records 3.32 kΩ as costing 1.1 dB against it. […] The
> other two reasons both argue *downward* — the optimum is at 2585 Ω […]

`model/results/analog.txt:130-133` actually says:

> 1. The element resistors should not be the loudest thing in the chain. Their
>    own thermal noise **equals the measured digital floor of 133.5 dB at
>    2585 ohm**. At 3.32 kohm they measure 132.4 dB, −1.1 dB against it, so
>    they cost the pair 3.6 dB.

Three errors:

1. **2585 Ω is a break-even point, not an optimum.** The Q1c table
   (`analog.txt:86-94`) has the element-resistor column falling monotonically
   with R — 137.6 dB at 1 kΩ, 132.4 dB at 3.32 kΩ, 127.6 dB at 10 kΩ — and
   `analog.txt:79-81` explains why ("both resistor terms fall 3 dB per doubling
   of R"). There is no interior optimum anywhere on that sweep. 2585 Ω is
   simply where the element noise crosses the digital chain's 133.5 dB floor.
2. **The 1.1 dB applies to a sub-term, not to the stage.** 133.5 − 132.4 is the
   *element resistors alone*, which are 11.9 % of stage noise power at 1 kΩ and
   less above it (`analog.txt:104-108`). The columns that matter are `stage SNR`
   and `with chain`: 3.32 kΩ gives 125.84 / 125.15 dB, and interpolating the
   table at 2585 Ω gives about 126.5 / 125.7 dB. **The recoverable amount is
   about 0.6 dB of system noise, not 1.1 dB.**
3. **"The other two reasons both argue downward" is not what reason 3 says.**
   `analog.txt:140-143` prices going down: "1 kohm to 3.32 kohm **saves 32 mA
   and costs 2.0 dB of system noise**". Reason 3 is a current-against-noise
   trade that argued *upward* on current grounds; with the current constraint
   gone it stops resisting, but it never pointed at 2585 Ω.

The recommendation — re-run the sweep now the power constraint is gone — is
right. The number that motivated it is a misreading, and it is repeated at
`hardware/lyrebird-dac-reva/power.md:328-329` ("`analog.txt`'s noise optimum at
2585 Ω is available and worth 1.1 dB").

0014:80's "about 4 mA of extra element current" does reproduce:
14 × 3.32/2585 − 13.92 = 3.95 mA.

**Confirmed against the code that produces the figure.** `run_analog.py:299-300`
computes it as a break-even solve, not an optimisation:

    say(f"   of {signal_dbfs-floor_db:.1f} dB at "
        f"{10.0**((analog.noise_budget(1000.0).snr_elem_db - (signal_dbfs-floor_db))/10.0)*1000.0:.0f} ohm. "

That is `R = 1 kΩ × 10^((S_elem(1 kΩ) − floor)/10)` — it inverts the monotone
3 dB-per-octave relation to find the R at which element noise equals the digital
floor. There is no derivative, no argmax and no optimum anywhere in the
expression. Evaluated directly: `analog.noise_budget(1000.0).snr_elem_db` is
**137.602 dB**, and against a 133.5 dB floor that gives **2572 Ω** (the log's
2585 follows from its unrounded floor). Calling the output of that expression an
optimum is a category error, not a rounding one.

And the sweep is monotone over its whole range, so no optimum exists to find:

| R_elem | element noise alone | stage SNR | with the chain |
| --- | --- | --- | --- |
| 1 000 Ω | 137.60 dB | 128.35 dB | 127.19 dB |
| 2 200 Ω | 134.18 dB | 126.89 dB | — |
| **2 585 Ω** | **133.48 dB** | **126.50 dB** | **125.72 dB** |
| 3 010 Ω | 132.82 dB | 126.11 dB | — |
| **3 320 Ω** | **132.39 dB** | **125.84 dB** | **125.16 dB** |
| 4 700 Ω | 130.88 dB | 124.82 dB | — |

Computed by calling `lyrebird_model.analog.noise_budget` directly, which
reproduces `analog.txt`'s Q1c table. **Moving 3.32 kΩ → 2585 Ω is worth 0.66 dB
of stage SNR and 0.56 dB once power-summed with the digital chain, not 1.1 dB.**
The 1.1 dB is the element-resistors-alone delta, a term that is 11.9 % of stage
noise power at 1 kΩ and less above it.

So, precisely: 0014:72-81 should strike "noise-optimal", strike "the optimum is
at 2585 Ω", and restate the prize as **about 0.6 dB**. The action it recommends
— re-run the sweep now the current constraint is gone — survives intact, and
`hardware/lyrebird-dac-reva/power.md:328-329` carries the same two errors.


### 3.4 The volume-placement table disagrees with its own log by up to 24 dB

`model/README.md:894-899` against `model/results/idle.txt:446-455` (section F3,
"Where the volume control goes, 96 kHz", `corrected` column — the only
measurement of this in the repository, produced by `run_idle.py:_job_f_vol`):

| Attenuation | README, chain input | **log** | README, modulator input | **log** |
| --- | --- | --- | --- | --- |
| −6 dB | 140.3 dB | **134.60** | 140.3 dB | **140.27** |
| −20 dB | 138.7 dB | **120.59** | 140.2 dB | **140.16** |
| −40 dB | 123.9 dB | **100.16** | 134.2 dB | **133.47** |
| −60 dB | 104.2 dB | **80.54** | 114.6 dB | **113.44** |

All eight disagree. The chain-input column is out by 5.7, 18.1, 23.7 and
23.7 dB. Both conclusions drawn from it are consequently wrong:

* `README:901` "**Identical to about −6 dB**" — the log shows a 5.7 dB gap
  already at −6 dB.
* `README:901` "then late placement pulls ahead by **roughly 10 dB**" — the
  log's gaps are 5.7, 19.6, 33.3 and 32.9 dB.

The recommendation (volume at the modulator input) is *more* strongly supported
by the log than by the table, so the conclusion is safe and the evidence for it
is misstated.

### 3.5 The order-3 rotation column is in no log, and four headline figures rest on it

`model/README.md:143-147` order-3 column: 167.9, 154.5, 77.1, 134.7, 57.1 dB.

The only logged order-3 measurement is `results/idle.txt:440-444`: **169.24,
154.81, 77.07, 134.96, 57.06**. The giveaway is the two rotation-off rows:
README gives 77.1 and 57.1 for *both* orders, which are `measurements.txt`'s
order-2 values copied into the order-3 rows; the log shows order 2 at
76.74/56.72 and order 3 at 77.07/57.06, so they genuinely differ.

Downstream, against the log:

| README claim | Log gives |
| --- | --- |
| `:149` "One percent mismatch costs **33.3 dB** with rotation" | 169.24 − 134.96 = **34.28 dB** |
| `:158` "Rotation still buys **77.6 dB** at one percent mismatch" | 134.96 − 57.06 = **77.90 dB** |
| `:158-159` "clears the 110 dB target by **24.7 dB**" | 134.96 − 110 = **24.96 dB** |
| `:164` "order 2 to order 3 buys **8.3 dB** at one percent" | 134.96 − 127.71 = **7.25 dB** |

None of these changes a conclusion. All four are quoted elsewhere as if
measured, and the last is out by 1.0 dB.

A third set of values for the same quantity exists at
`results/reference-current.txt:63-68`: plain DWA 133.79 dB, no rotation
57.05 dB. So "SNDR at one percent elements with rotation" is 134.7 (README),
134.96 (`idle.txt`) or 133.79 (`reference-current.txt`) depending on where a
reader looks, and no document says which site is canonical.

### 3.6 RETRACTED — the CCHD-957 footprint is the right size, and this finding was wrong

**This section originally claimed the footprint's body outline was drawn twice
the size of the part. That claim was wrong and is withdrawn in full.** It is
recorded rather than deleted because the way it was wrong is the same way this
project has been wrong before: I reasoned from a general convention instead of
reading the drawing.

The reasoning was that four pads on a 7.11 × 5.08 mm centre grid must belong to
a roughly 7 × 5 mm body, because that is where pads sit on an ordinary SMD
oscillator, and that a 14.2 × 9.14 mm outline containing those pads was
therefore a factor-of-two error. The CCHD-957 is not an ordinary SMD
oscillator. Its pads sit well inboard of its body edges.

Settled against Crystek's own spec sheet, rev N dated 25-Aug-2026, fetched from
the URL in `hardware/symbols/lyrebird.kicad_sym` and read out of the PDF's text
layer:

| Datasheet | Value | Footprint |
| --- | --- | --- |
| Page 1 header and body | "9×14 mm SMD", "housed in a 9×14 mm SMT package" | name says `9x14mm` ✓ |
| Top View | `0.360 ±0.005 (9.14 ±0.127)` | `F.Fab` rect is 9.14 mm tall ✓ |
| Top View / Side View | `0.560 ±0.005 (14.2 ±0.127)` | `F.Fab` rect is 14.2 mm wide ✓ |
| Side View height | `0.210 (5.3) Max` | not represented; 3D only |
| SUGGESTED PAD LAYOUT | `0.280 (7.11)`, `0.200 (5.08)` centres; pads `0.050 (1.27)` × `0.090 (2.28)` | pads at (±3.556, ±2.54), size 2.28 × 1.27 ✓ |
| Bottom View pad metal | `0.040 (1.01)` × `0.070 (1.77)` | matches `parts-notes.md:287` ✓ |

The `F.Fab` rectangle is 14.2 × 9.14 mm, which is the datasheet's Top View
dimensions to three significant figures. The courtyard at 14.7 × 9.64 mm is
that plus a 0.25 mm margin. **The footprint's body, courtyard and pad geometry
are all correct.** `parts-notes.md:269` — "The package is 9 × 14 mm, not a
7050" — is right, and so are `0012:17`, `open-items.md:157` and the footprint
name.

While the datasheet was open, every other CCHD-957 specification in
`parts-notes.md` was checked against it. All of them are exact:

| `parts-notes.md` | Datasheet rev N |
| --- | --- |
| `:272` "3.3 V ±0.3 V, 15 mA typical and 25 mA maximum running, 1.5 mA maximum disabled" | `Input Voltage: 3.3V ±0.3V`; `Input Current: 15mA Typical, 25mA Max`; `Input Current (Disabled Mode): 1.5mA Max` ✓ |
| `:274` "Phase noise floor −169 dBc/Hz typical, −100 dBc/Hz at 10 Hz offset" | `Phase Noise Floor: -169 dBc/Hz Typical, -165 dBc/Hz Max`; `Phase Noise: -100 dBc/Hz Typical … at 10Hz offset` ✓ |
| `:275` "Option X is −40 to +85 °C at ±25 ppm … the part number example in the datasheet is exactly `CCHD-957X-25-49.152`" | `(Option X) -40°C to +85°C (±25ppm, ±50ppm)`; `Part Number Example: CCHD-957X-25-49.152` ✓ |
| `:270` "1 = E/D, 2 = GND, 3 = OUT, 4 = Vcc. E/D is active high, with '1' at 0.7 × Vcc minimum, and an **open pin runs**" | Pad Connection table `1 E/D, 2 GND, 3 OUT, 4 Vcc`; `"1" level 0.7×Vcc Min`; `Function pin 1: Open → Active` ✓ |
| `:279-280` the quoted sentence on disable mode | verbatim from page 1 ✓ |

That is an unusually clean result for a part with no PDF in the repository, and
it is worth saying so: the one claim in this section that was wrong was mine,
not the document's.


### 3.7 The pad-numbering defect is real as an open question, but it is not "rotated 90°"

With §3.6 withdrawn, the pad numbering is the only remaining question on this
footprint — which makes the wording of it matter, because two documents state it
as a confirmed, board-stopping defect and a third states it as unverified.

`0012:17-19`: "Its pad *numbering* is still wrong — **rotated 90°** against the
bottom view — and that is the one open defect that would stop a board working."
`lyrebird-dac-reva/brief.md:109-113` repeats it and adds "the pad geometry is
confirmed correct and only the numbering is wrong, and the two candidate fixes
differ by a mirror".

`parts-notes.md:296-299` says instead: "**Which corner is pad 1.** The pad
*functions* are the datasheet's own Pad Connection table. Their geometric
arrangement follows the universal four-pad oscillator convention … pad 1 lower
left in top view, then 2, 3, 4 anticlockwise" — listed as one of two things
"read rather than stated, and both should be checked against the vendor drawing
before a board is fabricated".

What the drawing settles. The Bottom View's four pad-number labels sit at these
text origins in the PDF's own coordinates (x right; `Tm_f` increases *down* the
page, because the text matrix carries `d = −1` under a y-flipping page CTM):

| Digit | x | `Tm_f` (down) |
| --- | --- | --- |
| 1 | 3111.0 | 21034.7 |
| 2 | 4295.4 | 21034.7 |
| 4 | 3111.0 | 21982.2 |
| 3 | 4295.4 | 21982.2 |

Two things follow, and only two.

**The long axis is not transposed, so "rotated 90°" is not what the drawing
shows.** The label grid spacing is 1184.4 in x against 947.5 in y, so the wider
spacing lies along x. Consistent with labels set a constant 1.524 mm outboard
of pad centres on a 7.112 × 5.08 mm grid — (3.556+1.524)/(2.54+1.524) = 1.250,
which is the observed ratio exactly. The KiCad footprint also puts its wider
spacing along x (pads at ±3.556 in x, ±2.54 in y). A 90° relationship would
require these to be transposed and they are not. The captions are unrotated
(`a = 1`, `d = −1`), so the figure is not turned on the page either.

**The cyclic handedness matches.** In the bottom view, 1→2→3→4 runs
left-up → right-up → right-down → left-down, which is clockwise in a y-up
frame; mirrored to a top view that is anticlockwise. The footprint, converted
to a y-up frame, runs 1 left-down → 2 right-down → 3 right-up → 4 left-up,
which is also anticlockwise. So the numbering is either correct or **180°**
out — not 90°.

**What I could not settle, and will not guess.** Handedness cannot separate 0°
from 180°, and a rectangular four-pad package offers no other absolute
reference in its pad pattern; resolving it needs the position of the digits
relative to the package outline and the top-view laser marking, which means the
figure's vector geometry rather than its text layer. I extracted the text
positions only. The footprint is internally self-consistent — its silkscreen
pin-1 dot at (−6.3, 3.8) sits beside pad 1 — which is necessary but not
sufficient.

This matters because the two candidate errors are not equally bad, and neither
document that asserts the defect states which one it is:

* a **90°** error, as written, is geometrically impossible on this pad grid;
* a **180°** error swaps pad 1 with pad 3 and pad 2 with pad 4, which swaps
  `E/D` with `OUT` and — the part that would destroy the oscillator —
  **`Vcc` with `GND`**;
* **0°** means there is no defect here at all.

`parts-notes.md` has this right and the other two documents overstate it. The
correct status is the one `parts-notes.md:288-289` already gives: read the
vendor drawing with a person in front of it before fabricating. What should
change is `0012:17-19`'s and `brief.md:110`'s characterisation — "rotated 90°"
is a specific claim the drawing does not support, and "confirmed correct" is
not the state of the numbering either way.


### 3.8 The element filter capacitors' 0.37 mA does not follow from the stated inputs

`lyrebird-dac-reva/power.md:101-109` and `parts-notes.md:337-342` both say:

> At the rotation's assumed transition rate — half the element clock […] that
> is about **0.37 mA per element** averaged over a cycle, or roughly **10 mA
> across 28 elements**

`28 × 0.37 = 10.4` is internally consistent, and the figure is marked
*(estimate)*. But `power.md:9` promises "This page shows the arithmetic behind
every number", and this is the one figure on the page with no arithmetic. The
page's own method — `I = C × V × f`, used at `:125`, `:178` and `:203` — gives,
for 180 pF at 12.288 MHz:

* at the full rail, 180 pF × 3.32 V × 12.288 MHz = **7.34 mA** per element;
* at the midpoint node's actual swing (3.32 × 1.65/3.34 = 1.64 V), **3.63 mA**;
* allowing for the 1.06 MHz pole the capacitor sits behind — the node ripples
  rather than swinging fully, ripple ≈ 1.64 × tanh(T/4RC) = 0.22 V pp —
  **about 1.0 mA**.

So the plausible range is 1–7 mA per element, i.e. 27–205 mA across 28, against
a claimed 10.4 mA. I could not find any calculation in the repository producing
0.37: `hardware/verify_power.py` does not model it (`grep -n '180' ` returns
nothing), and it appears in no `model/results/` log. **This figure is
unsourced, and it is load-bearing** — it is the dominant non-constant term on
the rail that `open-items.md` calls the project's largest risk, and
`reference-current.txt` scales its prediction through it.

### 3.9 The alignment margin is now a fourth value, and the log falsifies it

`model/README.md:801`: "a correct alignment wins by **90 dB or more**".

`results/programme.txt:672-673`: "the in-band error at the offset used is at
least **27 dB** below what it becomes when the two paths are slid 256 samples
apart, over 138 segments that had signal to check."
`programme.txt:62-67` gives per-rate tone figures of **+110.2 to +112.7 dB**.

So the log reports a floor of 27 dB and a tone-case value near 111 dB, and
README quotes 90 dB, which matches neither and is above the log's own stated
minimum. The surrounding methodological point (`:795-800`) is correct and
reproduces — "it false-alarmed on 34 of 90 segments" is `programme.txt:667`
exactly.

### 3.10 Smaller figures that do not trace

| Claim | Where | Log / netlist says |
| --- | --- | --- |
| "gains 42.3 dB if it is the first and **0.1 to 0.3 dB** if it is either of the others" | `model/README.md:867-868` | `modarith.txt:16-18`: **42.2**, and **−0.2** and **−0.0** — widening integrator 2 or 3 does not gain, it very slightly loses |
| "made the datapath look **18 dB** worse" | `model/README.md:747` | its own inputs give 159.5 − 143.1 = **16.4 dB**; neither number is in a log |
| order-3 MSA **0.918** | `model/README.md:36, 47` | the same file at `:309` and `:399-401` says **0.900** over 2^18 and calls 0.918 "0.17 dB optimistic" — the table was not updated |
| DAC module "**126 components** and 637 pins" | `parts-notes.md:601` | `lyrebird-dac.net`: **112 components**, 133 nets. `brief.md:82` has it right |
| "**126 components and 144 nets**" | `open-items.md:145` | **112 components, 133 nets** |
| reconstruction filter "2.0 nF and **1.3 nF**" | `open-items.md:154` | `C47`–`C50` are **3.9 nF C0G 2%**. `parts-notes.md:98` explains the change and gets it right: "3.9 nF across 200 Ω is 204 kHz, the same corner 1.3 nF across 604 Ω gave" |
| element resistor "**3.32 kΩ**" | `0014:74, 76` | fitted as 1.69 k + 1.65 k = **3.34 kΩ** (`RN1`–`RN14`). 3.32 kΩ is the model's recommendation; both briefs and `parts-notes.md:307` say 3.34 |
| "+5 V pins … **71**, 73, 75, 77 and 79" / "five pins" | `main-reva/power.md:16`, `dac-reva/power.md:19-20` | +5V is on **73, 75, 77, 79 only — four pins**; pin **71 carries `-6V_A`** on both boards |
| "two mezzanine pins taken from **the ground allocation**" | `open-items.md:72-73` | pin 72 came from ground; pin **71 came from the +5V allocation**, which is why +5V dropped from five pins to four |
| "**Five** parallel header contacts at 20 mΩ drop **2 mV** at 123 mA" | both `power.md` (`main:108`, `dac:269`) | four contacts; and five 20 mΩ contacts in parallel are 4 mΩ, which at 123 mA is **0.49 mV**. 2 mV is one contact's drop, not five in parallel |
| "the ferrite is at `VBUS`" | `open-items.md:123` | there is **no ferrite in `lyrebird-main.net`**. `L1`/`L2` are the two 10 µH buck inductors. `FB1` exists only in the thirteen-day-old `.kicad_pcb` |
| "the **LGA-25 land pattern does not** [exist]" | `open-items.md:108` | it exists: `hardware/footprints/lyrebird.pretty/Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm.kicad_mod`, and `U4` in the netlist uses it |
| "U14 … sitting on the **pump's +5.69 V LDO output** and programmed to **+4.99 V**" | `parts-notes.md:422-423` | the pump is deleted (same file, `:389`); `U14` IN is the header's `+5V`. The 4.99 V *is* what `R10` = 49.9 kΩ programs — see §3.11, because that is a problem, not a typo |
| "173 → module **238 mA**, board **472 mA**" | `parts-notes.md:607`, `:628`, `dac/power.md:284, 338` | `dac/power.md:254` itself gives **123 mA of +5V and 64 mA of −6V**; `main/power.md:99` gives **219 mA at 12 V** |
| "this board already reaches about **416 mA** at the USB input" | `parts-notes.md:577` | a fifth figure for the same board, alongside 380 (0009), 381 (`main/power.md:162`), 472 (0014) and 509 (`open-items.md:100`) |
| "**Sixteen parts**" removed with the charge pump | `parts-notes.md:393`, `dac/brief.md:106` | `dac/power.md:369` itemises "two flying capacitors, two ADJ dividers and two reference bypasses"; the parts are gone from the netlist so the count **cannot be verified** from the repository |
| "**73 mA** of conversion overhead" | `parts-notes.md:413`, `dac/power.md:259` | not derivable from any figure on either page: 238 − 123 = 115 mA of +5V removed, of which 64 mA reappears on −6V, leaving 51 mA |
| "cost **33 dB without** and **0.5 dB with**" | `open-items.md:182` | **inverted, and resurrects a retracted figure.** `model/README.md:149`: "One percent mismatch costs 33.3 dB **with** rotation, **not 0.5 dB**". Without rotation it costs 77.9 dB |
| "measured at **0.5 dB against 70 dB** without it" | `dac-reva/brief.md:38-39` | both retracted. With rotation: 33.3 dB (README) / 34.3 dB (log). Rotation's benefit: 77.6 dB (README) / 77.9 dB (log). 70 dB appears nowhere |
| "0009 has a 30 mA line … against **37.5 mA** estimate" | `parts-notes.md:261` | `dac/power.md:181` now says 33.5 mA; the 37.5 mA page it is arguing against no longer exists |
| "CCHD-957, running \| 15.5 \| **datasheet**, 15 mA typical" | `dac/power.md:176` | the same page at `:187` derives it: `I_running = 17 − 1.5 = 15.5` *(calculation)* from 0012's 17 mA. `parts-notes.md:272` gives the datasheet as **15 mA typical**. The provenance column is wrong on a page whose stated discipline is provenance |
| "LMK1C1104 … \| 10 \| **datasheet**" | `dac/power.md:179` | same page, `:384`: "Read off a curve rather than a table" |
| bitstream "1.4 times headroom" / "**both designs** under one percent of the part" | `0013:116-119` | §3.2 / below |

### 3.11 The module's `+5V_A` rail is programmed above what its input can supply

This is arithmetic, not prose, and nothing in the repository checks it.

* `lyrebird-dac.net`: `U14` (LT3045) `SET` → `R10` = **49.9 kΩ 0.1 %**.
  LT3045 SET sources 100 µA, so the programmed output is **4.99 V**.
* `U14` IN is the header's `+5V`, which `verify_power.py:110` puts at
  **5.02 V**, less the header contact drop.
* The only LT3045 dropout figure in the repository is
  `verify_power.py:81`: `U3_DROPOUT = Fact(0.26, "V", DS, "LT3045 at 500 mA; less at our load")`.

So the part has roughly **10–30 mV of headroom against a 260 mV dropout
figure**. `dac/power.md:55` asserts "U14 drops tens of millivolts at 22 mA and
gives +4.94 V" with no cited source, and `hardware/datasheets/` is empty, so
**I cannot verify the low-current dropout**. What is verifiable is that the
netlist programs 4.99 V, two documents say the rail is 4.94 V, and the repo's
own dropout constant says neither is reachable from 5.02 V.

`verify_power.py`'s "LT3045 dropout" check passes on **1700 mV** of headroom —
that is the main board's `U3` (5 V → 3.32 V). **The module's LT3045s are not
checked at all**, and `U14` is the only one in the design with less than a volt
of headroom.

### 3.12 0013's bitstream figures are not "two designs old", they are the wrong side of a decision

`hdl/build/` holds four designs, not two. From the `.bit` files and
`.pnr.log` utilisation reports:

| Design | CPE_LT | CPE_FF | RAM_HALF | Bitstream |
| --- | --- | --- | --- | --- |
| `lyrebird_tag_decode` | 94 | 28 | 0 | 97,566 B |
| `lyrebird_unpack` | 290 | 92 | 0 | 184,050 B |
| `lyrebird_ft601q_read` | 289 | 71 | 0 | 156,815 B |
| **`lyrebird_elastic`** | **8,256 (20 %)** | 365 | **50/64 (78 %)** | **612,869 B** |

Three consequences for 0013:

1. `0013:116` "**Both designs are still under one percent of the part**" — 
   `lyrebird_elastic` is 20 % of `CPE_LT` and 78 % of the block RAM.
2. `0013:119` "2 Mbit leaves only about 1.4 times headroom over the second
   figure here, which is too thin to commit to." 2 Mbit is 262,144 bytes;
   against `lyrebird_elastic`'s 612,869 bytes it is **0.43×** — 2 Mbit does not
   fit at all, by a factor of 2.3. The conclusion is not "too thin", it is
   "excluded".
3. `0013:116-118` "the real design **adds** … the elastic buffer" and
   `0013:117-118` "**Do not pick a flash part** until something close to the
   full design has been built and measured." The elastic buffer is built, and
   the flash part **is** picked: `U6 MX25R6435F 64Mb` in the netlist, with
   `hardware/README.md:264-270` giving the reasoning. 0013 is the only document
   still telling a reader not to choose it.

`0013:5-11`'s correction says the figures "should be re-read from `hdl/build/`
rather than from here", which is right, and understates it: re-reading them
reverses one conclusion and retires another.

### 3.13 0013's environment table, verified locally

Everything checkable checks out, which makes the one unfixed row conspicuous.

| 0013 row | Verified |
| --- | --- |
| Verilator 5.048 | `Verilator 5.048 2026-04-26` ✓ |
| Yosys 0.67+post | `Yosys 0.67+post (git sha1 b8e7da6f…)` ✓ |
| cocotb 2.1.0, Python 3.14.6 | `.venv` reports both exactly ✓ |
| openFPGALoader | on PATH ✓ |
| git-lfs 3.8.0, repository not configured | `git-lfs/3.8.0` ✓, and there is **no `.gitattributes`** ✓ |
| `git-lfs` \| **missing** (`:138`) | **false, and contradicts `:136` two rows up** — the row the correction says it fixed |

One ambiguity worth noting: `0013:127` lists "Yosys 0.67+post" as installed
while `0013:101` says the OSS CAD Suite "ships its own Yosys, **0.69+24**". Both
can be true (Homebrew's is 0.67), but the table is headed "Environment as
verified" and names only one, so a reader cannot tell which built `hdl/build/`.

---

## 4. What is actually stale inside `docs/decisions/`

`SUPERSEDED_OK` at `check_freshness.py:73` exempts `docs/decisions/` from the
only content check in the tool. This section is that check, run by hand, and
then extended to the kinds of staleness no string grep would find either.

### 4.1 First, what removing the exemption would and would not buy

Running the checker's own `SUPERSEDED` map, `HISTORICAL` window and blockquote
rule against `docs/decisions/` produces **six hits that would be reported as
FAIL**. Only one of them is real:

| Hit | Real? |
| --- | --- |
| `0014:116` "the **LTC3265** charge pump is still fitted" | **YES.** No LTC3265 in `lyrebird-dac.net`. §3 and §5.2 |
| `0009:1` the title "USB bus power, and which rails are precision" | no — it is the superseded record's own title |
| `0014:9` "0009 chose USB bus power and argued it well" | no — 0014 citing what it supersedes |
| `0009:101` "One unit load, 150 mA, applies before…" | no — inside a record marked superseded |
| `0014:75` quoting `analog.txt`'s retired reason, in order to retire it | no |
| `0014:23` "gated through an inverting NMOS off `WAKEUP_N`" | no — it is in 0014's list of what it removes |

So the fix is **not** to delete the exemption: five of six would be noise, and
noise is how the transient simulation taught a reader to ignore red. The
structural fix is to key the exemption on the record's own **Status line** —
scan a record whose status does not say "superseded by", exempt one that does —
which would have caught `0014:116` and produced none of the other five. That is
a two-line change and it is the only one of the checker's heuristics that can be
made sound, because "is this record current?" is written down in every file.

### 4.2 And then the part a string grep cannot reach

Six lines is not the size of the problem. The staleness that matters in these
fourteen files contains **no superseded string at all**. Enumerated, worst
first. Each is a constant or a premise sitting beside a circuit that changed —
the same shape as the three faults this round's schematic work found.

**1. `0014:111-122`, "What this does not yet do" — three of four bullets false.**
The single stalest passage about the module in the repository, in the record
that is the current authority on power.

| 0014 says | `lyrebird-dac.net` says |
| --- | --- |
| "the mezzanine still carries +5V" | it carries +5V **and `-6V_A`**, on `J1` pins 71/72 |
| "the **LTC3265** charge pump is still fitted" | no LTC3265 component exists |
| "the difference network is still **604 Ω**" | `RN16`/`RN17` are `200R, 0.1% RATIO matched, thin film array` |
| "The **2.1 dB** is recoverable but not recovered" | recovered — `open-items.md:80`, `parts-notes.md:93`, and the netlist |
| "Neither board's `power.md` reflects any of this" | partly true and now the wrong way round: both `power.md` files describe the *new* rails in their tables and the *old* budget in their later sections (§5.3) |

Only the isolator bullet still holds: there is no ADuM4165/4166 in either
netlist, and `USB_SSRX_P/N` plus `J1` pins 6/7 are wired.

**2. `0014:37`, "a 15 V TVS".** `D2` is `SMAJ18A unidirectional`. This is the
one the project already knows about: `check_freshness.py:62` lists
`"SMAJ15A": "SMAJ18A -- the 15 V part conducted on a 19 V adapter forever"`, and
`verify_power.py:64-69` carries the whole story in a comment. The decision
record that *introduced* the TVS still specifies the part that fails. Missed
twice over — by the exemption, and because "a 15 V TVS" is not the string
`SMAJ15A`.

**3. `0013:138`, `| git-lfs | **missing** |`.** The row the correction at
`0013:5-11` says it fixed. Still present, two rows below the correct one at
`:136`. Verified locally: `git-lfs/3.8.0` is installed and there is no
`.gitattributes`, so `:136` is right and `:138` is wrong.

**4. `0013:106-120`, the bitstream table and both conclusions drawn from it.**
Two designs listed where `hdl/build/` holds four; "both designs are still under
one percent of the part" against `lyrebird_elastic` at 20 % of `CPE_LT` and
78 % of block RAM; "2 Mbit leaves only about 1.4 times headroom" against a
0.43× shortfall; and "Do not pick a flash part" against `U6 MX25R6435F 64Mb`
already in the netlist. §3.12.

**5. `0007:76` and `0007:80-81` — a correction that fixed the boundary and left
the budget.** "This is what keeps the board inside **the tighter budget when it
falls back to a USB 2.0 port**" and "**Declare worst-case current in the USB
descriptor**; it is fixed at enumeration and cannot be renegotiated when a
module changes." Neither sentence has a referent any more. `J1`'s `USB_VBUS`
reaches exactly one pin, `U2` pin 37. The 2026-09-25 correction on this record
touches only the I2S boundary and says nothing about power, so a reader who
follows the instruction at `0007:4` — "Read the correction first" — is told the
record has one problem when it has three.

**6. `0008:52-53` — the claim four documents are built on, still unqualified.**
"It also means ordinary one percent resistors are adequate." That reading came
from an order-2 measurement in which the modulator's own floor hid the rotation
residual. `model/README.md:134-166` retracts it under a heading that says so,
and re-establishes the cost at 33.3 dB. The 2026-09-21 review flagged 0008 as
unrepaired; it is still unrepaired, and 0008 has no correction block at all on
this point — only the 2.5 V rail note in its Status line. Downstream, the
retracted reading is still quoted as current in `open-items.md:182` ("0.5 dB
with") and `dac-reva/brief.md:38-39` ("0.5 dB against 70 dB without it").

**7. `0008:89` and `0008:95-96` — an argument whose premise 0010 widened.**
"At an oversampling ratio of 256 the quantization noise already sits far below
…" and "A 24.576 MHz master clock against a 96 kHz sample rate does not put us
there." 0010 added 192 kHz, where the ratio is 128 — inside the "around 32 to
64" band 0008 names as where four bits would be right, by a factor of two rather
than four. The conclusion survives (`model/README.md:200` measures 192 kHz as
the *best* rate, 143.8 dB matched), but the record argues from a number the
design no longer has a single value for.

**8. `0009:44`, 400 mW and the thermal vias.** "It dissipates roughly 400 mW,
so tie the exposed pad to plane with thermal vias." `verify_power.py` now
computes **102 mW** for the same rail. The instruction is in a superseded
record, so it is correctly quarantined — but `hardware/README.md:62-65`
describes the same rail and drops the dissipation figure and the thermal-via
instruction entirely, so the only place the layout requirement is written down
is a retired record with a number four times too large.

**9. `0006:30-31`, an instruction already carried out.** "Size the flash with
headroom rather than to a measured figure; confirm the actual bitstream size
from a first build before committing the part." The part is committed and four
builds exist. Harmless, but it is the second record telling a reader the flash
is undecided (§3.12 item 3).

**10. `0003:26`, a bandwidth figure from the part that was replaced.** "against
roughly 35 MB/s available" is an FT2232H High-Speed number. `0005`'s amendment
and `0014:105` quote 480 Mbit/s, i.e. ~60 MB/s, for the same link. Both make
the padding overhead free, so nothing turns on it.

**11. `0005:84-85`, a paragraph the record's own amendment retires.** "**The
board is harder.** USB 3.0 SuperSpeed differential pairs need controlled
impedance" — `0005:17-19` says "anything below about the SuperSpeed pairs being
the hardest constraint in the main board's layout is retired". The paragraph
does not say "hardest constraint", so whether it is covered is a judgement
call, and a reader making it is doing the document's work. It is also still
true of the netlist, which is the confusing part: the amendment states an
intention and the body states the board.

**12. `0010:90`, 20 blocks where the arithmetic gives 19.** 9 600 frames is
19 200 samples; at 1 024 samples per TDP 40K block that is 18.75 → 19. The
figure was obtained by doubling the 96 kHz row. In a table 0011 supersedes, so
it is inert.

**13. `docs/decisions/README.md:22`, "decision 5".** The index row for 0012
reads "analog rails moved by **decision 5**", inside a table whose other twelve
rows use bare numbers to mean records 0001–0014. There is no decision record
numbered for this change. The phrase originates in a code comment —
`hardware/netlist/output_module.py:500`, "The bipolar rail (decision 5,
option B; supersedes 0009's arrangement and the LTC3265 that implemented it)" —
and has since propagated into twelve files including `check_freshness.py:61`,
`docs/open-items.md`, both `power.md`, `parts-notes.md`, `dac-reva/brief.md`,
`0012`'s amendment, and both boards' generated sheet titles. In a repository
whose `docs/decisions/README.md:3` states "One file per decision, numbered,
never rewritten", the largest change since 0014 — deleting the module's only
switching converter and carrying a negative rail across the mezzanine — has no
record, and its informal name collides with `0005`. `0014:124-127` says it
"deserves its own pass"; it has not had one.

### 4.3 The pattern, stated once

Eleven of the thirteen items above are a **number or a premise that stayed put
while the circuit beside it moved**. That is the same fault as the SET resistor
left at 49.9 kΩ when its input moved from 5.69 V to 5.02 V, and as the two
power-good nets that were built twice and connected once. In prose the
consequence is slower but not smaller: a decision record is what a reader
consults *instead of* the netlist.

None of the eleven would be caught by a superseded-string list, because none
names a part that was replaced — they name a value, a ratio, a budget or a
constraint. What would catch them is the shape `check_footprints` already uses
at `check_freshness.py:202`: assert the document's number against the netlist's,
and let the netlist be the authority. Candidates that are one query each:
rail voltages against SET resistors, difference-network and element resistance
against `RN*` values, component and net counts, mezzanine pin allocations, and
TVS/fuse part numbers.

---

## 5. Contradictions between documents that both look current

Not "one is superseded and says so" — both read as live descriptions of the
board, and a reader has no way to choose.

### 5.1 Both `power.md` files contradict themselves within one document

Neither is stale throughout. Both carry a **correct new rail table** and a
**retired old budget** in later sections, with nothing marking the seam. That is
worse than a wholly stale page, because the correct half lends the stale half
its authority.

`hardware/lyrebird-main-reva/power.md`:

| Line | Says | Contradicted by |
| --- | --- | --- |
| `:3-4` | "**Bus powered, no external input** ([0009])" — the first sentence of the document | `:36` "+12V \| 11.4–12.6 \| barrel jack, via F1, D1" and `:129` "0014 replaced bus power with a 12 V supply" |
| `:16-18` | boundary is "downstream of the **VBUS ferrite** named in 0009" | no ferrite exists in `lyrebird-main.net`; and `:37` sources +5V from `LMR33630, U5` |
| `:22` | the header carries "**unregulated bus voltage and ground, and no other rail**" | `:38` in the same table gives `-6V_A` crossing the mezzanine, and `:37` gives a regulated 5.02 V |
| `:164-170` | "**The 1.0 V and 2.5 V rails have no supply.** The LTM4622 selected in 0009 is **not in `main_board.py`** … It is also absent from the stock KiCad libraries, so it needs a symbol before it can be wired. Until then **the FPGA cannot be powered**" | `U4 LTM4622IV#PBF` is in the netlist on `Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm`; `:40-41` of the same file lists both rails against it; `open-items.md:118-119` and `main-reva/brief.md:78-79` both say it is fitted |
| `:172-174` | "**there is no USB connector**, so the 5 V input has no entry point either" | `J1 Connfly DS1104-01` on `USB3_Micro-B_Connfly_DS1104-01`; and the 5 V input is now `J4`, a barrel jack |

`hardware/lyrebird-dac-reva/power.md`:

| Line | Says | Contradicted by |
| --- | --- | --- |
| `:19-21` | "**five pins of unregulated bus voltage** downstream of the main board's **VBUS ferrite**" | four pins (73/75/77/79); regulated 5.02 V from `U5 LMR33630`; no ferrite; and `:268` in the same file — "The main board's buck holds +5V at 5.02 V" |
| `:23` | "**Nothing else crosses.**" | `:42`, nineteen lines later — `-5V_A … from the mezzanine's **−6V**` |
| `:276-309` | a whole section headed "Reflected to the USB input, and margin": 472 mA, "USB 2.0 host \| 500 mA \| 472 mA \| 94 %", "**The USB 2.0 line is no longer comfortable**, and it is the one number on this page that should worry a reader", "185 mA of bridge in *active SuperSpeed*", "**The declared figure is 900 mA regardless**, fixed at enumeration" | `:311-317`, the *next* section: "**That rule no longer applies.** 0014 replaced bus power with a 12 V supply". And `:254` gives the module at **123 mA of +5V**, not 238 |
| `:347` | "Op amp stage and charge pump \| 65 \| 139 \| … and **a doubler that pays for all of it twice**" | `:45` "**There is no charge pump.**" and `:372` "**The charge pump is deleted**" |
| `:388` | "3 mA of **pump** quiescent" as a live uncertainty | same |
| `:389` | "4.43 V at the header … **it decides whether the charge pump is inside its input range**" | `:272-275`: "The part that used to need checking here was the charge pump … **It is gone, and so is the question.**" Also on 0014's own "Retired" list |

### 5.2 `parts-notes.md` states the difference network at both values, 560 lines apart

| Line | Says |
| --- | --- |
| `:65-69` | "**The difference amplifier's four resistors are one array, and they are 604 Ω rather than the 200 Ω `analog.txt` names.**" |
| `:88` | "\| **200 Ω — fitted** \| **21.0 mA mid code, 28.0 worst** \| **56.5–63.5 mA** \| **125.6 dB** \|" |
| `:93` | "**200 Ω is fitted, and the 2.1 dB is recovered.**" |
| `:626` | "\| Difference network \| **604 Ω, not 200** — a supply-current finding, 2.1 dB of noise paid for 28 mA of USB current \|" |

The netlist settles it: `RN16`/`RN17` are `200R, 0.1% RATIO matched, thin film
array`. `:88` and `:93` are right; `:65-69` and `:626` are wrong.

**This is the cleanest demonstration in the repository of §1.2.** The checker
scans `hardware/lyrebird-dac-reva/parts-notes.md` — that path is not in
`SUPERSEDED_OK` — and its `SUPERSEDED` map contains both `"604R"` and
`"604 ohm"`. The document writes **`604 Ω`**, with the Greek capital omega.
Neither key matches, so a file the tool does read, looking for a string the tool
is explicitly hunting, passes clean.

Two adjacent rows of the same status table also contradict each other:
`:623` "Charge pump \| **deleted**" beside `:627` "`MUTE_N` \| **gates the
charge pump**".

### 5.3 The oscillator standby argument is given with the wrong reason in `interface.md`

`hardware/interface.md:77-78`: "the CCHD-957 **tri-states its output** in
standby, **so** an idle part neither drives nor radiates."

`0012:63-65`: "Its standby mode **shuts the resonator down rather than only
tri-stating the output**, which is what the one-oscillator-at-a-time rule
actually needs: an idle oscillator next to the analog section **radiates a spur
regardless of whether its output is connected**."

The datasheet (§3.6) supports 0012: "the internal oscillator is completely shut
down **in addition to** its output buffer being placed in Tri-State".
`interface.md` names only the half that 0012 says is insufficient, and asserts
the conclusion *from* it. The conclusion is right; the reason given is the one
the design rejected. `dac-reva/brief.md:15-16` and `hardware/README.md:113-115`
both state it correctly, so `interface.md` is the outlier.

### 5.4 `hardware/README.md` is the most stale in-scope document on power

It reads as current throughout — no correction blocks, no superseded markers —
and four passages describe a board that no longer exists.

| Line | Says | Reality |
| --- | --- | --- |
| `:39` | "USB 3.0 Micro-B \| **Bus power and data, one cable**" | `USB_VBUS` reaches one pin, `U2` pin 37 |
| `:48-49` | "**Bus powered**, with the core in economy mode. See [0009]" | 0009 is superseded; power is `J4` → `F1` → `D1` → two LMR33630s |
| `:51-56` | rail table with "5 V \| Passed through to the module \| **Ferrite only**" | +5V is made by `U5 LMR33630` from 12 V; there is no ferrite; `+12V` and `-6V_A` are absent from the table entirely |
| `:71-73` | "**Gate the FPGA rails with the LTM4622 run pins**, releasing them after the bridge enumerates, so the board respects the **one-unit-load** limit that applies before configuration" | both RUN pins are tied on; the gating "was worse than unnecessary" (`open-items.md:107`) and its NMOS is deleted |
| `:243-247` | "If the output stage needs a bipolar supply, **generate it on the module** and post-regulate it … at **a charge pump's** switching frequency the op amp rejects far less" | the pump is deleted and the negative rail crosses the mezzanine |
| `:3` | "Two boards, split at the **I2S boundary** per 0007" | 0007's own correction says "The *boundary* this record describes does not exist" |

`:72`'s "one-unit-load" is the hyphenation case from §1.2 — the
`SUPERSEDED` key is `"one unit load"` and does not match.

### 5.5 Live instructions citing a superseded record as authority

`0009` is correctly marked superseded, and seven live passages nonetheless rest
on it. Each one reads as current, and none carries a note.

| Passage | What it takes from 0009 |
| --- | --- |
| `hardware/README.md:48-49` | "Bus powered … See 0009" |
| `main-reva/power.md:3-4` | "Bus powered, no external input ([0009])" |
| `dac-reva/power.md:3-4` | "regulates its own rails from the +5 V the main board hands it ([0009])" |
| `dac-reva/power.md:302-306` | headphone stage "roughly 200 mA more, reaching about 580 mA … over the 500 mA of a USB 2.0 host" |
| `dac-reva/brief.md:74-76` | "**No headphone amplifier on this variant.** A headphone stage driven hard adds roughly 200 mA and does not fit a USB 2.0 host ([0009])" |
| `main-reva/brief.md:63-66` | "A *further* supply on the module is **0009's deferred answer**" |
| `interface.md:90-91` | "should take its own supply input (**0009 defers that case** for a headphone stage)" |
| `open-items.md:241` | "Headphone power **beyond bus limits**, a module carries its own jack \| 0009" |
| `parts-notes.md:44, 56-57, 570-580` | "76 % of a USB 2.0 host's"; "inside 0009's 65 mA for the op amp stage and charge pump"; "about 416 mA at the USB input" |

The deferral itself is sound and worth keeping — a headphone module that needs
more than the main board's inverter should carry its own input. What is wrong is
the premise every one of these gives for it: a bus limit that no longer exists.
The right home for the deferral is a live record, and there is none, because the
change that removed the bus has no decision record (§4.2 item 13).

### 5.6 Component and net counts disagree across three documents

| Document | DAC module |
| --- | --- |
| `lyrebird-dac.net` (authority) | **112 components, 133 nets** |
| `dac-reva/brief.md:82-83` | 112 components, 133 nets ✓ |
| `parts-notes.md:601` | "126 components and 637 pins" ✗ |
| `open-items.md:145` | "126 components and 144 nets" ✗ |

`main-reva/brief.md:73-74` gives 159 components / 142 nets for the main board,
which matches exactly. So the two briefs are the only documents whose counts are
right, and they are the two the checker's timestamp pass currently warns about.

One count that does check out: `dac-reva/brief.md:83`'s "**12 pins deliberately
open**" equals `parts-notes.md:541-548`'s table exactly — `U3`/`U4` `1Q8`+`2Q8`
(4), `U12 Y3` (1), `U8 VIOC` (1), five `PG` pins, `U2 1A2` (1) = 12.

### 5.7 The element resistance is quoted at three values

| Value | Where | Status |
| --- | --- | --- |
| **3.34 kΩ** | `lyrebird-dac.net` (`RN1`–`RN7` 1.69 k + `RN8`–`RN14` 1.65 k), `parts-notes.md:307`, both briefs, `dac/power.md:90` | what is fitted |
| 3.32 kΩ | `analog.txt` Q1 recommendation, `notes-analog.md`, `0014:74,76`, `dac/power.md:89` | the model's recommendation; 0.6 % below what is fitted |
| **1 kΩ** | `main-reva/power.md:158` — "25 mA implies a 3.1 kΩ element; **the netlist says 1 kΩ**" | the placeholder the netlist carried before the parts were chosen; `dac/power.md:98` calls it "the 1 kΩ placeholder this page used to carry" |

`main-reva/power.md:158` is the live one and it is wrong: it is a row in the
table reconciling this page against 0009, so a reader is told the current
netlist has a 1 kΩ element.

### 5.8 The `.kicad_pcb` files contradict everything else

Covered at §1.11. Worth restating as a contradiction rather than only as a
checker gap: `main-reva/brief.md:95-96` says the board file "holds placed
footprints from the netlist import", and the file it describes contains `FB1`
(the deleted VBUS ferrite) and `Q1` (the deleted `WAKEUP_N` NMOS) and none of
the 12 V input section. Both boards' `.kicad_pcb` predate 0014 entirely.

---

## 6. What I could not verify, stated as such

Listed because a review that does not separate "checked" from "assumed" repeats
the failure it is auditing.

1. **Low-current LT3045/LT3094 dropout.** `hardware/datasheets/` is empty. The
   only figure in the repository is 260 mV at 500 mA (`verify_power.py:81`).
   `verify_power.py` now checks all six regulators and says so honestly in its
   own output — "the low-current dropout is smaller and is not published in
   anything fetched here". `U14` at 490 mV of headroom is the closest, and
   whether that is adequate is not settled by anything here.
2. **The CCHD-957 pad-1 corner, 0° versus 180°.** §3.7. Needs the drawing's
   vector geometry or a person; I read only the text layer.
3. **`SN74ALVCH16374` output-to-output skew.** `parts-notes.md:156-160` states
   plainly that SCES021L does not publish it and that the one-package-per-channel
   argument rests on die-sharing instead. Correctly stated as a gap, and I could
   not close it.
4. **The 0.37 mA per element filter capacitor.** §3.8. Not derivable from the
   inputs given, and no calculation for it exists anywhere in the repository.
   I give a plausible range of 1–7 mA per element; I cannot say which is right.
5. **Whether GateMate GPIO are high-impedance before configuration.**
   `parts-notes.md:192-196` says the datasheet does not spell it out. Unresolved,
   and it bounds the bus-hold argument at `parts-notes.md:162-190`.
6. **"Sixteen parts" removed with the charge pump**, and the **"73 mA of
   conversion overhead"**. Both describe a circuit that is gone from the netlist,
   so neither is checkable from the repository as it stands.
7. **The `.kicad_pcb` placement quality.** I confirmed zero tracks and a stale
   component set; I did not assess placement.
8. **Everything downstream of the HDL.** I read `hdl/build/*.pnr.log`
   utilisation and bitstream sizes only. No claim here rests on reading the RTL.

---

## Cross-section flags

Every inconsistency found in this review that involves the power design or the
schematic rather than only prose. Each line names the file, the line, what is
wrong, and what the correct value is with its source. Tags:

`[POWER]` rail topology, voltages, currents, protection · `[SCHEMATIC]`
connectivity, components, footprints, counts · `[MODEL→HW]` a hardware value
resting on a model figure · `[TOOLING]` a check that cannot see a fault ·
`[PROCESS]` a record or convention gap with electrical consequences

Status: **OPEN** unless marked FIXED DURING REVIEW (verified in the current
netlist by me) or RETRACTED.

### Blocking — wrong value or wrong claim about a built circuit

1. `[POWER][SCHEMATIC]` **`docs/decisions/0014-wall-wart-power.md:37` specifies a 15 V TVS.** The netlist fits `D2 SMAJ18A unidirectional`. Correct value **SMAJ18A**, 18 V standoff / 20 V minimum breakdown, from `lyrebird-main.net` and `verify_power.py:68-70`. The 15 V part conducts indefinitely on a 19 V adapter — 41 mA at a junction near 117 °C without tripping `F1` — per `main-reva/power.md:81-85` and `hardware/sim/power_input_transient.py`. The decision record that introduced the TVS names the part that fails. **OPEN**

2. `[POWER][SCHEMATIC]` **`docs/decisions/0014-wall-wart-power.md:116-118` states the module is untouched.** Three of its four claims are false against `lyrebird-dac.net`: the mezzanine carries **+5V and `-6V_A`** (`J1` pins 71/72, not +5V alone); there is **no LTC3265** component; the difference network is **`200R, 0.1% RATIO matched, thin film array`** (`RN16`/`RN17`), not 604 Ω. The 2.1 dB is **recovered**, not recoverable. Only the isolator bullet still holds. **OPEN**

3. `[SCHEMATIC]` **`hardware/lyrebird-dac-reva/parts-notes.md:65-69` and `:626` state the difference network is 604 Ω.** Correct value **200 Ω** (`RN16`/`RN17` in `lyrebird-dac.net`), which the same file states correctly at `:88` and `:93`. `:626` reads "604 Ω, **not** 200", i.e. it asserts the wrong value against the right one. **OPEN**

4. `[POWER]` **`hardware/lyrebird-dac-reva/parts-notes.md:422-423` describes `U14` as "sitting on the pump's +5.69 V LDO output and programmed to +4.99 V by 49.9 kΩ on SET".** Wrong on all three counts now: there is no pump; `U14` IN is the header's `+5V`; and its SET resistor is **`R10` = 45.3 kΩ 0.1 %**, programming **4.53 V**. Source: `lyrebird-dac.net`, whose `U14` value string reads "+4.53 V from mezzanine 5 V". **OPEN** — this is the paragraph that documented the fault fixed under item 21 and it still carries the pre-fix constant.

5. `[POWER][SCHEMATIC]` **`hardware/lyrebird-main-reva/power.md:164-174`, "What has no source today", is false in every clause.** It says the LTM4622 "is **not in `main_board.py`**", is "absent from the stock KiCad libraries, so it needs a symbol", that "**the FPGA cannot be powered**", that the VBUS ferrite is "absent", and that "**there is no USB connector**". Against `lyrebird-main.net`: `U4 LTM4622IV#PBF` on `Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm`, sourcing `+2V5` and `+1V0`; `J1 Connfly DS1104-01`; and the 5 V input is `J4`, a barrel jack, so no VBUS ferrite is wanted. Contradicted by `:40-41` of the same file. **OPEN**

6. `[POWER][SCHEMATIC]` **Both `power.md` files place +5V on five mezzanine pins including pin 71.** `main-reva/power.md:16` and `dac-reva/power.md:19`. Correct: +5V is on **pins 73, 75, 77, 79 — four pins** on both boards, and **pin 71 carries `-6V_A`** together with pin 72. Source: `lyrebird-main.net` and `lyrebird-dac.net`. Consequences: `dac-reva/power.md:20` "five pins of unregulated bus voltage" is wrong three ways (four pins, regulated, 5.02 V from `U5 LMR33630`); and `open-items.md:72-73`'s "two mezzanine pins taken from **the ground allocation**" is half right — pin 72 came from ground, pin 71 came from the +5V allocation, which is why +5V lost a pin. **OPEN**

7. `[POWER]` **`hardware/lyrebird-main-reva/power.md:3-4` opens "Bus powered, no external input ([0009])",** and `:16-18` places the boundary "downstream of the VBUS ferrite", and `:22` says the header carries "unregulated bus voltage and ground, **and no other rail**". All four contradicted by the same document's rail table at `:36-38` (`+12V` from a barrel jack; `+5V` at 5.02 V from `LMR33630, U5`; `-6V_A` crossing the mezzanine) and by `:129`. **OPEN**

8. `[POWER]` **`hardware/lyrebird-dac-reva/power.md:276-309` presents a live USB current budget.** 472 mA against 500 mA at 94 %, "the one number on this page that should worry a reader", "185 mA of bridge in *active SuperSpeed*", and "**The declared figure is 900 mA regardless**, fixed at enumeration". Retired by 0014, as the *next section* of the same file states at `:311-317`. The module's own total four sections earlier is **123 mA of +5V and 64 mA of −6V** (`:254`), and the board draws **219 mA at 12 V** (`main-reva/power.md:99`, `verify_power.py`). **OPEN**

9. `[POWER]` **`hardware/lyrebird-dac-reva/power.md:389` keeps "4.43 V at the header … it decides whether the charge pump is inside its input range" as a live uncertainty,** and `:388` keeps "3 mA of pump quiescent". Both retired: `:272-275` of the same file says of the 4.43 V case "**It is gone, and so is the question**", and 0014 lists it under "Retired". **OPEN**

10. `[POWER]` **`hardware/lyrebird-dac-reva/power.md:347` prices the op amp line with "a doubler that pays for all of it twice".** No doubler exists (`:45`, `:372`, and the netlist). The whole "Against 0009's budget" section (`:335-353`) reports the module at **238 mA**, the pre-decision-5 figure, against `:254`'s **123 mA**. **OPEN**

11. `[POWER][SCHEMATIC]` **`hardware/README.md` describes the pre-0014 power tree as current, with no marker.** `:39` "USB 3.0 Micro-B \| Bus power and data, one cable"; `:48-49` "**Bus powered** … See 0009"; `:51-56` a rail table that omits `+12V` and `-6V_A` and sources 5 V through "**Ferrite only**"; `:71-73` "**Gate the FPGA rails with the LTM4622 run pins** … so the board respects the **one-unit-load** limit"; `:243-247` "generate [the bipolar supply] **on the module** … at a **charge pump's** switching frequency". Correct: `J4` → `F1 1812L050/30` → `D1 SS34` → `U5`/`U7` LMR33630s; both RUN pins tied on; the negative rail crosses the mezzanine. Sources: `lyrebird-main.net`, `open-items.md:68-85`, `0014:32-45`. **OPEN**

12. `[POWER]` **`hardware/lyrebird-main-reva/power.md:158` says the netlist's element resistor is 1 kΩ.** Correct: **3.34 kΩ**, fitted as `RN1`–`RN7` at 1.69 k plus `RN8`–`RN14` at 1.65 k in `lyrebird-dac.net`. 1 kΩ is the placeholder the netlist carried before the parts were chosen, as `dac-reva/power.md:98` says. The row is inside a live reconciliation table, so it reads as the current state. **OPEN**

13. `[POWER]` **`hardware/lyrebird-main-reva/power.md:91` keeps 187 mA for the bridge's 3.3 V rail while relabelling it "High Speed".** 0009's 185 mA was an *active SuperSpeed* figure, and 0009:111 itself says "falling back to High Speed also lowers the bridge's own draw". Relabelling the row without changing the number asserts that High Speed costs the same as SuperSpeed. `verify_power.py:104` independently assumes **60 mA** for the same rail with the comment "`main power.md is stale`". Between 60 mA and 187 mA nothing in the repository adjudicates, and the LT3045's dissipation follows from it: 102 mW (`verify_power.py`) against ~315 mW (from 185 mA) against 0009:44's "roughly 400 mW, so tie the exposed pad to plane with thermal vias". **OPEN, and it is the largest unresolved power number in the design.**

14. `[POWER]` **`docs/decisions/0009-usb-bus-power.md:44`'s thermal-via instruction is quarantined in a superseded record and not restated anywhere live.** `hardware/README.md:62-65` describes the same rail and omits both the dissipation figure and the thermal-via requirement. Whatever the correct dissipation turns out to be (item 13), the layout requirement currently exists only in a retired document, attached to a number four times `verify_power.py`'s. **OPEN**

15. `[SCHEMATIC][TOOLING]` **Both `.kicad_pcb` files are thirteen days behind their netlists and contain deleted parts.** `lyrebird-main.kicad_pcb` holds `FB1` (an `L_0603_1608Metric` — the deleted VBUS ferrite) and `Q1` (a `SOT-23` — the deleted `WAKEUP_N` NMOS), and lacks `J4`, `U5`, `U7`, `F1`, `D1`, `D2`, `D3`, `L1`, `L2` and `C101`–`C109`. `lyrebird-dac.kicad_pcb` has 16 capacitors against 64, 7 `RN` against 17, and no `U10`–`U14` or `J2`. Both have zero `(segment`. `check_freshness.py`'s `BOARDS` dict names `net`, `gen` and `pdf` and **never names the board file**, so this is invisible to the tool whose docstring was written about exactly this failure. `main-reva/brief.md:95-96`'s "holds placed footprints from the netlist import" is false. **OPEN**

### Verified correct — do not re-open

16. `[SCHEMATIC]` **RETRACTED: the CCHD-957 footprint is not oversized.** I claimed `Oscillator_SMD_Crystek_CCHD-957_9x14mm.kicad_mod` had its body drawn at twice the part's size. **That was wrong.** Crystek spec sheet rev N (25-Aug-2026) gives Top View `0.360 ±0.005 (9.14 ±0.127)` × `0.560 ±0.005 (14.2 ±0.127)` and says twice on page 1 that the part is a "9×14 mm SMD" package; the footprint's `F.Fab` rectangle is 14.2 × 9.14 mm, which is exact. Pads at (±3.556, ±2.54) match the datasheet's `0.280 (7.11)` × `0.200 (5.08)` suggested-pad centres, and pad size 2.28 × 1.27 matches `0.090 (2.28)` × `0.050 (1.27)`. Body, courtyard, pad geometry and name are all correct, and so are `parts-notes.md:269`, `0012:17` and `open-items.md:157`. I reasoned from the ordinary 7050 oscillator convention instead of reading the drawing. **RETRACTED**

17. `[SCHEMATIC]` **Every other CCHD-957 specification in `parts-notes.md` is exact against rev N**: 15 mA typ / 25 mA max running, 1.5 mA max disabled (`:272`); −169 dBc/Hz floor and −100 dBc/Hz at 10 Hz (`:274`); Option X −40 to +85 °C ±25 ppm and the part-number example `CCHD-957X-25-49.152` (`:275`); pad connection 1 = E/D, 2 = GND, 3 = OUT, 4 = Vcc with `"1"` at 0.7 × Vcc min and an open pin running (`:270`); and the quoted standby sentence (`:279-280`) is verbatim. **NO ACTION**

18. `[SCHEMATIC]` **`open-items.md:108` says the LTM4622 LGA-25 land pattern does not exist. It does** — `hardware/footprints/lyrebird.pretty/Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm.kicad_mod`, referenced by `U4` in the netlist. The open item is stale as written. Separately, I verified the current pad grid runs A–E along x at 1.27 mm pitch and 1–5 along y, i.e. the transposition reported by the schematic validator is corrected in the file as it now stands. **OPEN only as a stale open-item entry**

19. `[SCHEMATIC]` **`open-items.md:123` says "the ferrite is at `VBUS`". There is no ferrite in `lyrebird-main.net`** — `L1`/`L2` are the two 10 µH 3 A buck inductors. Per `0014:43-45` `VBUS` is no longer a supply and reaches one pin, so no ferrite is wanted; the open-items line describes it as a closed gap that was in fact deleted. `main-reva/power.md:172` calls the same absence a *defect*. Two live documents treat one fact oppositely. **OPEN**

20. `[MODEL→HW]` **`docs/decisions/0011` is confirmed by the build, independently of its own arithmetic.** `hdl/build/lyrebird_elastic.pnr.log` reports `RAM_HALF: 50/64`, which is exactly the 25 of 32 blocks 0011:35 claims and leaves the 7 free it claims at `:52`. Every row of its prefill table reproduces. **NO ACTION**

### Fixed while this review was in progress — confirmed in the netlist

21. `[POWER]` **`U14`'s SET resistor was programmed above what its input can supply.** Was `R10` = 49.9 kΩ → 4.99 V from a 5.02 V input, against the repository's only LT3045 dropout figure of 260 mV. Now **45.3 kΩ → 4.53 V with 490 mV of headroom**, confirmed in `lyrebird-dac.net`. `dac-reva/power.md:41,55-56` is updated; **`parts-notes.md:422-423` is not** (item 4). **FIXED DURING REVIEW**

22. `[TOOLING]` **`verify_power.py` checked only the one regulator that could not fail.** Its dropout check covered the main board's `U3` at 1.7 V of headroom and none of the module's five. It now reads all six LT3045/LT3094 SET resistors out of the netlists — `main U3`, `module U14/U5/U6/U8/U9` — and reports 18/18 with the unverified constants flagged. Confirmed by running it. **FIXED DURING REVIEW**

23. `[SCHEMATIC]` **Four single-node nets on the main board: both LMR33630 power-good pins and both their pull-ups.** `Net("PG_5V")` was constructed twice at `main_board.py:285-286` and `Net("PG_N6V")` twice at `:335-336`; SKiDL makes a new net per call and uniquifies the second name, so `PG_5V`/`PG_5V1` and `PG_N6V`/`PG_N6V1` were four separate nets — two resistors with a floating lead, two flags reading a permanent level. Now `PG_5V` = `R1`:1 + `U5`:4 and `PG_N6V` = `R4`:1 + `U7`:4. **FIXED DURING REVIEW**

24. `[TOOLING]` **`check_freshness.py` now reports single-node nets,** and the check is the right shape: `SINGLE_NODE_OK` is a four-entry, per-board, reasoned allowlist (`ELEM28`–`ELEM31` on the dac, which `interface.md` requires the main board to drive) rather than a heuristic. Both boards pass. Note the residual: it counts **nets**, not **pins**, so a pin on no net at all is still invisible — which is the measure `hardware/README.md:9-12` names as "the honest measure of how finished a board is". No ERC runs anywhere; every `*.erc` file is zero bytes and `main_board.log` ends "324 warnings, 0 errors". **FIXED DURING REVIEW, with a residual**

### Tooling gaps that let power and schematic faults through

25. `[TOOLING]` **`SUPERSEDED_OK` exempts `docs/decisions/` from the only content check.** Running the checker's own map against those files yields six FAILs, of which exactly one is real (`0014:116`, the LTC3265). So deleting the exemption trades one catch for five false positives. The sound fix is to key it on the record's **Status line**: scan a record whose status does not say "superseded by", exempt one that does. That catches `0014:116` and produces none of the five. **OPEN**

26. `[TOOLING]` **The `SUPERSEDED` keys are literal, and four live stale passages evade them by spelling.** `"604R"`/`"604 ohm"` miss **`604 Ω`** (`parts-notes.md:66`, `:626` — a file the tool *does* read); `"one unit load"` misses **`one-unit-load`** (`hardware/README.md:72`); `"USB bus power"` misses **`Bus powered`** (`main-reva/power.md:3`) and **`Bus power and data`** (`hardware/README.md:39`); `"SMAJ15A"` misses **`a 15 V TVS`** (`0014:37`). **OPEN**

27. `[TOOLING]` **BOM coverage ignores `R`, `C`, `RN` and `Q`, and never compares values.** `check_freshness.py:178` filters to `r[0] in "UJYFLD"`, so "dac: BOM covers every major reference, 17 checked" is 17 of 112 components and excludes **all 17 `RN` arrays — the 28 elements and the difference network**, the two things this review found misdocumented. And the docstring at `:22-24` promises "with the same value"; `check_bom` compares reference sets only, so a revalued part passes. **OPEN**

28. `[TOOLING]` **Nothing asserts a documented number against the netlist.** Every item 1–14 above is a constant in prose disagreeing with a netlist value, and none contains a superseded string. `check_footprints` (`:202`) is the one check of the right shape — it asks the netlist rather than the prose, and its own docstring explains why the string version failed. The same shape applied to rail voltages against SET resistors, `RN*` values, mezzanine pin allocations, component and net counts, and TVS/fuse part numbers would catch items 1, 2, 3, 4, 6, 11, 12 and the §5.6 counts. **OPEN**

29. `[TOOLING]` **The timestamp pass cannot cover what it does not list.** `check_freshness.py:159` checks `power.md`, `brief.md` and `bom.csv` inside the two board directories. Not covered: `docs/decisions/*` (14 files), `docs/open-items.md`, `hardware/interface.md`, `hardware/README.md`, `model/README.md`, and — though it sits beside two files that are checked — `hardware/lyrebird-dac-reva/parts-notes.md`, which carries items 3 and 4. Also `.py`, `.sv` and `.json` are outside the string scan (`:277`), which is why `verify_power.py:104`'s "`main power.md is stale`" comment sits unnoticed next to a constant that disagrees with that page by 3× (item 13). **OPEN**

### Model figures that hardware decisions rest on

30. `[MODEL→HW]` **`docs/decisions/0014:72-81` misreads `analog.txt`, and the claim should be struck rather than qualified.** It says "`analog.txt` Q1c measures the **noise-optimal element resistor at 2585 Ω**, giving 133.5 dB, and records 3.32 kΩ as costing **1.1 dB** against it", and repeats "the optimum is at 2585 Ω". `run_analog.py:299-300` computes that number as `R = 1 kΩ × 10^((S_elem(1 kΩ) − floor)/10)` — a **break-even solve**, with no derivative and no argmax. It is where the element resistors' own thermal noise **equals** the digital chain's floor, which `analog.txt:130-132` states in those words. No optimum exists: `analog.noise_budget().snr_elem_db` is strictly monotone in R across the sweep (137.60 dB at 1 kΩ → 130.88 dB at 4.7 kΩ). And the 1.1 dB is the element-resistors-alone delta, a term worth 11.9 % of stage noise power at 1 kΩ. Computed directly from the model: stage SNR is **126.50 dB at 2585 Ω against 125.84 dB at 3.32 kΩ**, and 125.72 against 125.16 power-summed with the chain. **The prize is 0.66 dB of stage SNR, 0.56 dB system — not 1.1 dB.** Strike "noise-optimal" and "the optimum is at 2585 Ω"; the recommendation to re-run the sweep survives. `dac-reva/power.md:328-329` carries the same two errors. **OPEN**

31. `[MODEL→HW]` **`hardware/lyrebird-dac-reva/parts-notes.md:307-311` justifies the 1.69 k + 1.65 k split by a retired constraint, and the constraint pointed the wrong way.** "The total is 0.6 % above the decided 3.32 kΩ … and it stays above the **3312 Ω that the one-unit-load-at-power-on argument requires**; an even 1.65 + 1.65 split would be 3.30 kΩ and **fail that by a hair**." That rule is retired (0014; and `:216-218` and `dac-reva/power.md:326-327` both say so). With it gone, and with the noise argument pointing *downward* (item 30), 1.65 + 1.65 = 3.30 kΩ is now marginally **better** than what is fitted, not a failure. The only stated reason for the asymmetric split no longer exists. **OPEN** — and it is the cheapest item on this list to act on, being two identical arrays instead of two different ones.

32. `[MODEL→HW]` **The 0.37 mA per element filter capacitor is unsourced and load-bearing.** `dac-reva/power.md:101-109` and `parts-notes.md:337-342` both give "about 0.37 mA per element … roughly 10 mA across 28". `28 × 0.37 = 10.4` is internally consistent but the 0.37 has no derivation anywhere, on a page whose own rule (`power.md:9`) is "shows the arithmetic behind every number" and which shows it for every other figure. Applying the page's own `I = C·V·f` to 180 pF at 12.288 MHz gives **7.34 mA** at the full rail, **3.63 mA** at the midpoint node's actual 1.64 V swing, and **about 1.0 mA** allowing for the 1.06 MHz pole the capacitor sits behind — a range of 1–7 mA per element, 27–205 mA across 28. This is the dominant non-constant term on the rail `open-items.md:10-61` calls the project's largest risk, and `reference-current.txt` scales its −101.1 dBFS prediction through it. **OPEN**

33. `[MODEL→HW]` **`docs/decisions/0008:52-53` still says one percent resistors are "adequate" with no qualification.** `model/README.md:134-166` retracts the reading that made it free and measures the cost at **33.3 dB** at order 3. The retracted 0.5 dB figure is still quoted as current in `open-items.md:182` — which also inverts it, giving "33 dB **without** and 0.5 dB **with**" where the model says 33.3 dB *with* — and in `dac-reva/brief.md:38-39` as "0.5 dB against 70 dB without it", a figure that appears nowhere. The elements actually fitted are **0.1 % thin film** (`lyrebird-dac.net`), which `model/README.md:210` measures as costing 0.1–0.3 dB, so the hardware is on the right side of this and only the documents are wrong. **OPEN**

34. `[MODEL→HW]` **`hardware/lyrebird-dac-reva/power.md:176` and `:179` mark two figures "datasheet" that the same file derives or estimates.** `:176` "CCHD-957, running \| 15.5 \| datasheet, 15 mA typical" against `:187` "`I_running = 17 − 1.5 = 15.5 mA` **(calculation)**" — a back-calculation from 0012's 17 mA, and 0.5 mA off the datasheet's own 15 mA typical (rev N, confirmed). `:179` "LMK1C1104 \| 10 \| datasheet" against `:384` "Read off a **curve** rather than a table". On a page whose stated discipline is provenance marking, two of five rows in the clock-rail table are mislabelled. **OPEN**

35. `[MODEL→HW]` **`docs/decisions/0013:106-120`'s bitstream figures reverse a conclusion when re-read.** `hdl/build/` holds four designs, not two. `lyrebird_elastic` is **612,869 bytes, 8,256 CPE_LT (20 %), RAM_HALF 50/64 (78 %)**. So "**both designs are still under one percent of the part**" is false; "2 Mbit leaves only about **1.4 times headroom**" becomes **0.43×**, i.e. 2 Mbit is excluded rather than thin; and "**Do not pick a flash part**" is overtaken by `U6 MX25R6435F 64Mb` already in the netlist, chosen with reasons at `hardware/README.md:264-270`. The flash choice is sound; 0013 is the only document still saying it is open. **OPEN**

### Process

36. `[PROCESS][POWER]` **The largest power change in the repository has no decision record.** Deleting the module's only switching converter and carrying a negative rail across the mezzanine is referred to as "**decision 5**" in twelve files — including `docs/decisions/README.md:22`, `docs/open-items.md`, both `power.md`, `parts-notes.md`, `dac-reva/brief.md`, `0012`'s amendment, `check_freshness.py:61`, and both boards' generated sheet titles. The phrase originates in a code comment at `hardware/netlist/output_module.py:500`. There is no such record, `docs/decisions/README.md:3` states "One file per decision, numbered, never rewritten", and in a table of links to 0001–0014 a bare "5" reads as `0005-ft601q-bridge-io-voltage.md`. `0014:124-127` says the change "deserves its own pass". **OPEN — and writing that record would resolve items 2, 8, 9, 10 and the §5.5 orphaned deferral at once, because it is the missing live home for all of them.**

37. `[PROCESS][SCHEMATIC]` **The CCHD-957 pad numbering is stated as a confirmed 90° defect in two documents and as unverified in a third, and the drawing supports neither.** `0012:17-19` — "rotated 90° against the bottom view … the one open defect that would stop a board working" — and `dac-reva/brief.md:109-113`, which adds "the pad geometry is confirmed correct and only the numbering is wrong". `parts-notes.md:296-299` lists it instead as one of two things "read rather than stated" that "should be checked against the vendor drawing". From rev N: the Bottom View's pad labels sit on a grid 1184.4 wide by 947.5 tall, i.e. **long axis along the 7.11 mm direction — the same as the footprint**, so no 90° relationship exists; and the cyclic handedness matches once the bottom view is mirrored to a top view. The live question is **0° versus 180°**, which I could not settle from the PDF's text layer. It matters because a 180° error swaps pad 1 with 3 and 2 with 4, which swaps `E/D` with `OUT` and **`Vcc` with `GND`**. `parts-notes.md` has the status right; the other two overstate it, and "rotated 90°" should not survive into a fabrication decision. **OPEN**

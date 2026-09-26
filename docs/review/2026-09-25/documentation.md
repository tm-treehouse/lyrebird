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
Sections 3.14 and 3.15 below.

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

### 3.6 The CCHD-957 footprint is drawn twice the size of the part, and its own description proves it

`hardware/footprints/lyrebird.pretty/Oscillator_SMD_Crystek_CCHD-957_9x14mm.kicad_mod`.

The pads are at (±3.556, ±2.54) mm — a 7.11 × 5.08 mm centre grid, which is
what the descriptor says the datasheet's suggested layout asks for, and the pads
are right. The **body and courtyard are not**:

    (fp_rect (start -7.35 -4.82) (end 7.35 4.82) ... F.CrtYd)   -> 14.7 x 9.64 mm
    (fp_rect (start -7.1  -4.57) (end 7.1  4.57) ... F.Fab)     -> 14.2 x  9.14 mm

14.2 is exactly 2 × 7.1, and 9.14 is exactly 2 × 4.57: **the outline was drawn
using the full pad-centre pitch as a half-width.** The result puts all four
pads entirely inside the body outline, which is geometrically impossible for a
4-pad SMD oscillator — the pads have to reach the body edge to form a fillet.

`parts-notes.md` contains the refutation of its own claim. It states the
package is "9 × 14 mm" (`:269`) and, seventeen lines later, that the pads sit
"on a 0.280 in (7.11 mm) by 0.200 in (5.08 mm) centre grid, against package pad
metal of 0.040 × 0.070 in (1.01 × 1.77 mm)" (`:286-287`). Pad metal on that
grid spans 8.88 × 6.09 mm overall. A body of 9 × 14 mm cannot contain pads with
that footprint; a body of about 7.1 × 5.1 mm is what those numbers describe,
and 0.280 × 0.200 in is the package outline being read as a pad pitch.

What I can verify from the repository: the footprint's outline is internally
inconsistent with its own pads and with `parts-notes.md`'s own dimensions.
What I cannot verify: the true package size, because `hardware/datasheets/` is
empty and the only reference is the URL in
`hardware/symbols/lyrebird.kicad_sym`. **The correct action is to read the
Crystek drawing**, but the outline is wrong by construction either way.

The "9 × 14 mm" figure has propagated to `0012:17`, `open-items.md:157`,
`parts-notes.md:269, 284`, the footprint name, and the symbol's Description
property.

### 3.7 The "pad numbering rotated 90°" defect is asserted in two places and recorded as unverified in a third

`0012:17-19`: "Its pad *numbering* is still wrong — rotated 90° against the
bottom view — and **that is the one open defect that would stop a board
working**." `lyrebird-dac-reva/brief.md:109-113` repeats it and adds "the pad
geometry is confirmed correct and only the numbering is wrong".

`parts-notes.md:296-299` says the opposite:

> **Which corner is pad 1.** The pad *functions* are the datasheet's own Pad
> Connection table. Their geometric arrangement follows the universal four-pad
> oscillator convention, the same one KiCad's SG-8002CA footprint uses: pad 1
> lower left in top view, then 2, 3, 4 anticlockwise.

The footprint does exactly that: pad 1 at (−3.556, +2.54), then 2, 3, 4
anticlockwise in top view, with the descriptor's `1 = E/D, 2 = GND, 3 = OUT,
4 = Vcc`; the symbol agrees (`lyrebird.kicad_sym`, `E/D` on 1, `OUT` on 3,
`Vcc` on 4). **I cannot confirm or refute the 90° claim without the vendor
drawing.** What is certain is that one document calls it a confirmed
board-stopping defect and another calls it a convention-following arrangement
that wants checking, and they cannot both be acted on.

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

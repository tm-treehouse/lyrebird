# What is left to act on

Consolidated from the section reviews in this directory. Two reviews are
complete (`dsp-model.md`, `output-module.md`), two are partial
(`main-board.md`, `hdl.md`) and one is in progress (`docs-audit.md`), so this
list will grow. Nothing here is speculative: every item names the file and the
evidence.

Ordered by what it costs to get wrong, not by effort.

---

## A. Blocking — a board built today would not work

| # | Item | Where | Action |
| --- | --- | --- | --- |
| A1 | **Crystek CCHD-957 footprint pad numbering is rotated 90°.** The datasheet bottom view places pins 1 and 2 at the same end, 0.200 in apart; the footprint has them at opposite ends, 7.112 mm apart. Rotating the part cannot recover it, and either placement puts a supply or ground on an oscillator signal pin. The pad *geometry* is confirmed correct — only the numbering is wrong. | `hardware/footprints/lyrebird.pretty/Oscillator_SMD_Crystek_CCHD-957_9x14mm.kicad_mod` | Renumber the pads from the datasheet drawing. The two ways of putting 1 and 2 on one end differ by a **mirror**, so this needs the drawing in front of a person — guessing replaces a known fault with an unknown one. |

That is the only item in this class. Everything else that was blocking has been
fixed in this pass; see section E.

---

## B. The model or the documents state something untrue

These mislead anyone who trusts them, which is the whole purpose of the
documents.

| # | Item | Where | Action |
| --- | --- | --- | --- |
| B1 | **The analog model prices four amplifiers; the board has six.** Two transimpedance stages per channel plus a difference amplifier, with `n_fb = 3` and noise gains 1.857/2.858 describing a topology that was not built. So `analog.txt`'s Q1c stage SNR, its 125.2 dB system figure, and the claim "the output stage is the noise floor of this design" are all computed for a different circuit. The real figure is about 123.5–123.9 dB, which `parts-notes.md` already derived by hand. | `model/lyrebird_model/analog.py` | Regenerate the model against the netlist. **The netlist is right.** |
| B2 | **`run_analog.py` hard-codes power figures that have since changed.** 8.1 mA of registers against the real 34.3, 40 mA of clock chain against 35.5, 51 mA for the op amp stage against 139. Q1a's module and board columns print 115/349 mA against `power.md`'s 238/472. | `model/run_analog.py` | Read the figures from one place, or regenerate. No component value moves — the 3.34 kΩ element clears both — but the numbers do not reproduce. |
| B3 | **The amplifier parameters are not the OPA1612's.** `E_N = 1.3e-9` against 1.1 nV/√Hz typical, `I_N = 1.5e-12` against 1.7 pA/√Hz. | `model/run_analog.py` | Correct to the datasheet values. `GBW = 40e6` is already right. |
| B4 | **`hardware/README.md` attributes a table to the model that the model never produced.** It lists 0.05 % and 0.5 % element-mismatch rows when the only values ever measured are 0, 0.1 % and 1 %; its 192 kHz column reads 138.1/137.9/137.6 where the log measures 143.83/143.52/133.97; and it makes 192 kHz the *worst* rate where the model makes it the *best*. The conclusions drawn from it rest on rows that do not exist. | `hardware/README.md:190-198` | Delete the table and quote the log, or re-run to produce the rows it claims. |
| B5 | **The volume-placement regression measures a different experiment than its name.** It applies the gain *before* the 24-bit source quantizer and omits `sig_frac`/`acc_frac`, disagreeing with README by up to 23.7 dB. Reproduced correctly, **README is right and the test is wrong** — which is the more dangerous direction, because an audit would conclude the opposite. | `model/run_idle.py:531, 727` | Fix the regression to match the documented experiment. |
| B6 | **Seven README claims do not trace to any log.** The ties table's "as published" column (four of six values disagree), the volume-placement table (in no log), the modulator peak-state table (matches no log, claims a six-rate sweep that is not performed), "the fitted gain came out 1.207" (quoted four times, computed and discarded), "−77 dBFS" (the log's prediction, measured −124.3), the alignment margin (three incompatible values), and "−143.1 against −159.5 dBFS" (does not reproduce; 2.0 dB at the recommended widths). | `model/README.md` | Trace each to a log or remove it. The large majority of README *does* reproduce exactly. |
| B7 | **`results/idle.txt` cannot be produced by any invocation of the current script.** A full run appends 216 lines of section H; a partial run does not write the file at all. | `model/run_idle.py` | Make the log reproducible, or record how it was made. |
| B8 | **Programme results depend on fourteen macOS system sounds, and their absence is handled silently.** On any other machine that run measures nothing and says so nowhere. | `model/run_programme.py` | Fail loudly, or vendor the material. |
| B9 | **The reason given for the 604 Ω difference network is false.** Both documents say it was chosen because the charge pump's internal LDO is rated 50 mA. The LT3094 is fed from `VOUT−` directly and `LDO−` drives nothing — the netlist says so in its own comment. The binding reason is the USB total: 509 mA against 500 at 200 Ω. The "recovers 2.1 dB" conclusion survives, but the stated cause is the clause someone would act on. | `docs/open-items.md`, `hardware/lyrebird-dac-reva/parts-notes.md` | Correct the reason in both. |
| B10 | **A retracted figure is still quoted**, in the section headed "Answered by the modelling, and no longer open": "one percent elements cost 33 dB without and 0.5 dB with". The 0.5 dB is the order-2 reading that README explicitly retracts; at order 3 it is 33.3 dB. `hardware/README.md` was corrected; this was not. | `docs/open-items.md:177` | Correct to 33.3 dB. |
| B11 | **The coefficient generator mislabels the format it correctly generates.** "Two integer bits are allocated" and `# Q2.22` in the same four lines as `MOD_FRAC = 22`, in a comment an HDL integrator reads precisely because this scaling is the unusual one. The arithmetic is Q1.22. | `model/export_coefficients.py:37-39` | Settle on Q1.22 throughout. |
| B12 | **A sixth site removes the arithmetic mean before a windowed transform.** Measured, it moves nothing by more than 0.01 dB, because the record there is a cascade *difference* whose offset is a genuine constant. Fix it anyway: the guarantee `remove_dc` provides is that no caller has to remember, and this caller never reaches the place that remembers. | `model/lyrebird_model/datapath.py:305` | `band_power_dbfs(spectra.remove_dc(e), ...)`, keeping `e.mean()` for the separately reported DC figure. |

---

## C. The same quantity has different values in different places

None of these change a conclusion. All of them will waste someone's afternoon.

| # | Quantity | Values in the tree | Which is right |
| --- | --- | --- | --- |
| C1 | Element resistor | 3320 Ω as 1660+1660 (`run_analog.py:69`, not an E96 pair), 3336 Ω as 1.668 k halves (`idle.py:457`), **3340 Ω as 1.69 k + 1.65 k** (board) | The board |
| C2 | Element filter capacitor | 192 pF (`run_analog.py`, and `analog.txt` line 249), **180 pF** (`analog.txt` line 405, `notes-analog.md`, board) | 180 pF |
| C3 | Reference rail | 3.3 V (`analog.py:74`, cites 0012), 3.32 V (`idle.py:456`, `parts-notes.md:348`) | 0012 says **3.3 V**; 3.32 is suspiciously the element resistance in kΩ |
| C4 | Oscillator frequency | `interface.md` names 22.5792 and 24.576 MHz; 0012 and the netlist fit **45.1584 and 49.152 MHz**, at twice the element clock | The netlist — this is the point of 0012's "1024 multiple" section |
| C5 | Module current | 238 mA (`power.md`), 182 mA (`parts-notes.md`) | `power.md`. parts-notes assumes a symmetric ±21.6 mA load its own preceding section disproves |
| C6 | LT3045 package | `bom.csv` records the DFN-12 that was wrong | DFN-10; the netlist is now fixed, the BOM is not |
| C7 | Volume position | `hdl/README.md:148-150` and `0010:102-105` say "inside the interpolation chain"; the model measured only the chain input and the modulator input | Pin it to "after the final half-band stage, at the modulator input" until a middle position is measured |

---

## D. Decisions outstanding

Rewritten 2026-09-24. Several items here moved since the first pass: D3 has
been measured, the wall wart is half built, and the lock state machine turned
out to be done already. Each is a judgement call rather than a defect — the
work to *do* them is known; what is missing is somebody choosing.

### D.1 — Signal quality, where the trade is known and costed

| # | Decision | What it buys | What it costs |
| --- | --- | --- | --- |
| **1** | **The reference rail carries the signal.** The DWA pointer advancing by the code is what shapes mismatch *and* what ties transition current to the code; four alternative rules each trade the whole benefit away. The untested idea is a **transition ballast** — `T` is bounded above by 14, so dummy lines toggled to make up the deficit flatten the current without touching the selection rule. | Predicted error goes from −101.1 dBFS to nothing. It is currently 35 dB above the chain's own floor and 12.6 dB over target. | The current of a fully toggling array, and a block nobody has designed. **Blocked on a bench measurement** — the −101.1 dBFS is a prediction from a digital proxy, and the model has no supply in it. |
| **2** | **The difference amplifier's unequal loading (was D3).** Now measured rather than estimated: the output currents differ **1.499 : 1**, not the 1.25 the load ratio suggests, and the positive half's output current **crosses zero at −3.5 dBFS — inside the signal**, where an output stage's crossover lives. Even-order cancellation measures **5.1 dB** against what 0008 puts both polarities on one die to buy. Fix: non-inverting leg at **R/3 = 201 Ω**. | Cancellation past 40 dB. | 4.6 mA on the negative rail at mid code, 9.2 mA at −FS, and one matched array becomes two matched pairs. **0008's property to trade.** |
| **3** | **The element resistor, 3.32 kΩ → 2585 Ω.** One of the three reasons for 3.32 kΩ was fitting one unit load before enumeration. That rule no longer exists; the other two arguments both point *down*. | 1.1 dB. `analog.txt` Q1c puts the noise optimum at 2585 Ω. | ~4 mA, which was the entire objection. **Blocked on fixing `analog.py`**, which prices four amplifiers where the board has six. |
| **4** | **The difference network, 604 Ω → 200 Ω.** | 2.1 dB. | Needs decision 5 first — at 200 Ω the negative rail wants 63 mA, which a charge pump makes expensive. |

Decisions 3 and 4 are worth **3.2 dB between them** against a design whose worst
real-material window sits 1.5 dB above target. Neither needs new parts.

### D.2 — Following the wall wart through

0014 is built on the main board and stops at the mezzanine.

| # | Decision | Note |
| --- | --- | --- |
| **5** | **Does the mezzanine carry a negative rail from the main board?** With 12 V available, an inverter there is cheap, and it deletes the LTC3265 entirely — its flying-capacitor ground return with it. This is the enabling decision for #4. | Changes the mezzanine contract in `interface.md`. |
| **6** | **Fit the ADuM4166 isolator?** 0014 argues for it; it is not in the netlist. Forces USB 2.0 High Speed, which costs nothing — 192/24 stereo is 1.9 % of it — and removes two 5 Gbps pairs from the layout. | The SuperSpeed pairs are still routed. |
| **7** | **Does supply ground tie to chassis?** Named as undecided in 0014 and still is. | |
| **8** | **Which fuse.** Three requirements must hold together — ≥24 Vdc, hold well above 236 mA, Imax above the inrush — and no catalogue line was confirmed to satisfy all three. The netlist says PART UNCHOSEN rather than naming a 6 V device that cannot work. | |

### D.3 — Contracts the HDL needs before it can be finished

| # | Decision | Note |
| --- | --- | --- |
| **9** | **Status word bit layout.** Prose in 0010, never mapped to bits. | Blocks the status path only. |
| **10** | **What `MUTE_N` should actually do.** It mutes by collapsing the analog supplies, and there is no DC blocking or output mute device at the jack — so every assertion and release is a supply transient straight into the output. Mute relay, or an HDL ramp, or accept the pop? | Nothing in `hdl/` asserts it at all yet. |
| **11** | **Should control words bypass the lock gate?** They do, deliberately and with a comment, and the word-alignment argument makes it safe. But it leaves the flush path unprotected by lock, which is the one place un-validated stream content reaches a destructive action. | Currently an accident rather than a choice. |
| **12** | **`ELEM[31:28]`.** `interface.md` requires the main board to drive them low; there is no synthesizable top-level in `hdl/rtl/` at all. | Scope, but on the critical path to a working board. |

### D.4 — Behaviour nobody has specified

| # | Decision |
| --- | --- |
| **13** | **Underrun.** Counted in the status word and prefill exists to prevent it, but what the converter should *do* is undefined. |
| **14** | **Host idle.** No defined behaviour when the host simply stops sending. |
| **15** | **Module hot-swap.** The ID pins can change while running. Nothing says what happens. |

### D.5 — Product scope

| # | Decision |
| --- | --- |
| **16** | **Which module to build first** — line, headphone, or combined. The ID encoding supports all three. |
| **17** | **Headphone amplifier part**, if 16 says headphone. None chosen. |
| **18** | **Provision an unpopulated quad-SPI PSRAM footprint?** Six pins, as insurance. |
| **19** | **git-lfs for `hardware/datasheets/`** — much cheaper before the directory fills with multi-megabyte PDFs than after. |

### Deliberately deferred, and still correctly so

USB Audio Class driverless operation (0004); four-bit differential, which would
need a main board respin (0008); headphone power beyond bus limits, now partly
reopened by the wall wart (0009); external SRAM, since the requirement is
latency-bounded rather than memory-bounded (0011).

## E. Closed in this pass

Recorded so nobody re-reports them.

- **LT3045 footprint** was DFN-12 on an 11-pin symbol; now DFN-10. The LT3094's DFN-12 is correct and was left alone — it has 13 pins.
- **Oscillator enables floated on both boards**, allowing two CCHD-957s to drive the shared `OSC_RAW` into each other. Pulled down on the module's translated side *and* on the main board, because the module side alone only decides the case where the translator is high impedance; the floating translator *input* had to be fixed at source.
- **JTAG handed a 3.3 V adapter direct access to a 2.75 V bank** (E-2). 1 k series on TMS/TCK/TDI, pull-ups moved to the FPGA side. Not UG1003's 10 k, which in series with Cologne Chip's own 10 k pull-up would divide a driven low to 1.25 V.
- **`SER_CLK`/`SER_CLK_N` floated on a powered receiver** (E-3). Grounded.
- **Nothing bounded either FPGA rail** (E-1). The review's mechanism was inverted — an open feedback resistor is *safe*, collapsing the rail to ≈0.6 V. The real hazard is a swapped resistor putting 2.5 V on the 1.0 V core rail, now prevented by a package poka-yoke: 0603 on the core rail, 0402 on the other.
- **E-4 and E-5 recorded** in the netlist beside the values they concern. The two operating windows on `+1V0` overlap by less than the regulator's own spread, so the rail is centred on VDD and VDD_SER is knowingly out of spec on an unused block.
- **The coefficient package's scaling rule** said a tap of width N is tap/2\*\*(N−1), which is wrong for the modulator's Q1.22 words by exactly a factor of two — 6.02 dB of loop gain in all three feedback paths. A trap for the first HDL consumer; no RTL imports the package yet.


---

## F. Decision records that no longer describe the design

From `docs-audit.md`, which produced the verdict-per-record mapping that did not
exist anywhere. 0004 and 0011 hold outright; 0001, 0003 and 0010 are amended and
properly marked. The rest are not.

| # | Record | Verdict | Action |
| --- | --- | --- | --- |
| F1 | **0007 — two boards, split at I2S** | **Contradicted**, not merely amended | It names the boundary as I2S and the module as carrying a "DAC", and rests its oscillator argument on "a delta-sigma DAC in slave mode" and a bit clock. 0008 deletes all of it — the boundary is element lines and the module carries resistors. The status line is a bare "accepted". **The filename itself carries the false claim into eight other files.** |
| F2 | **0009 — USB bus power** | **Superseded**, marked nowhere inside `docs/decisions/` | Not in its status line, not in the index, and no 0014 exists — against the index's own stated convention. Only `open-items.md` records it. |
| F3 | **0005, 0012** | Amended, unmarked | 0005:70-71 still tells a reader the SuperSpeed pairs are the hardest layout constraint, which is exactly what the amendment retires. 0012:134-135 still lists two parts as open that are chosen and wired. |
| F4 | **0002 — the FPGA owns the audio clock** | Contradicted, and nobody had noticed | It names the oscillators as 22.5792/24.576 MHz — those are now the *element clock*; the parts fitted are 45.1584/49.152 MHz. It also sizes the crossing FIFO at "a few thousand samples" against 0011's 38,400. |
| F5 | **0013 — toolchain** | Self-contradictory | git-lfs is "installed" at :128 and "**missing**" at :130, two table rows apart. Its bitstream table is two designs behind `hdl/build/`. |
| F6 | **0008 — the correction is real but incomplete** | | The retired form is still stated *above* the correction in the same file. And 0008:52-53's "**ordinary one percent resistors are adequate**" rests on the retracted 0.5 dB, where the model now measures 33.3 dB at order 3 — while the board actually fits **0.1 % thin film**. This is the only place in `docs/decisions/` where a part specification rests on a retracted measurement. The conclusion may well survive (1 % still gives 134.65 dB against a 110 dB target); the stated reason does not. |

### The corrected constant-current claim has two more homes

`interface.md:75-80` — the contract a module designer reads — and
`hardware/README.md:158-167` both still say the reference load is
signal-independent and that decoupling handles it. Neither was on anyone's
list. Both are wrong in the same way 0008 was, and `interface.md` is the more
dangerous of the two because it is what somebody designing a different output
module would build against.

### The largest single contradiction: the main board's power page

`hardware/lyrebird-main-reva/power.md` prints **module 147 mA, board 381 mA,
42 % of USB 3.0**, against the module page's **238 / 472 / 94 % of USB 2.0** —
while both pages state that they must agree. Its "What has no source today"
section is false in **every clause**: the LTM4622, the ferrite, the USB
connector and the 5 V capacitors are all in the netlist. Its pre-enumeration
analysis is indexed on a 1 kΩ element placeholder that the built 3.34 kΩ
replaced. Both board briefs describe netlists two rounds of work old.

`parts-notes.md` carries *both* budgets — 182/416 and 238/472 — and is the only
file in the repository that identifies the main page's figures as superseded.

### `open-items.md` corrections

The best-maintained file in the repository, and still: one item closed (the
LTM4622 footprint exists), two overtaken by the HDL (the prefill threshold and
the drain/fill/run state machine are implemented; underrun emits zero and
asserts mute), and three genuine gaps missing — no owner for the model's
clipper recommendation, no record of the 5.3 dB single-seed spread or the
untested above-10 kHz material, and no HDL task for `MUTE_N`, which now gates
both analog rails.

Every Markdown link in the audited set resolves. Zero dead targets.


---

## G. From the completed main-board review

| # | Item | Status |
| --- | --- | --- |
| G1 | **The `+3V3` rail took 359 ms to come up**, and the module's op-amp positive rail 539 ms. Two individually-correct, individually-datasheet-quoted choices multiplied: a 4.7 µF `C_SET` (the condition for the 0.8 µVRMS 0009 quotes) with `PGFB` tied to IN (which disables the 2 mA fast-start circuit that exists for exactly that capacitor), giving `t_ss ≈ 2.3·R_SET·C_SET`. It put the FT601Q's `VCCIO` up **355 ms before its own `VCC33`**. | **Fixed** on the main board — `C_SET` is now a parameter, 100 nF on the digital rail (7.6 ms) since it reaches only the bridge and the flash and buys no noise there. Every rail that reaches the signal keeps 4.7 µF. **The module's four remaining calls are unreviewed** and one of them is the 539 ms rail. |
| G2 | **`CFG_FAILED_N` had no pull-up.** DS1001 §3.3.3, verbatim: "requires a pull-up resistor". Open-drain with nothing holding it. | **Fixed** — 10 k to +2V5, without the series protection the adapter-driven pins get, since the FPGA drives it. |
| G3 | **The POR `R3a` at 47 k disables `VDD_CLK` brown-out detection permanently.** DS1001 gives a "no reset condition when R3a ⩽ 100 kΩ" regime; the design sits inside it to buy a 19.4 ms delay the datasheet says a 2.5 V `VDD_CLK` does not need. The comment's arithmetic is right — every step recomputed. | **Open.** Trading brown-out detection for an unnecessary delay is a decision nobody made deliberately. |
| G4 | **`power.md` line 37 still lists `AVDD` on `+3V3`** — the destroy-the-part bug that `open-items.md` records as *fixed*. The netlist is correct; the document still describes the fault. | **Open**, and the most dangerous stale line in the repository: it is the one a reader would act on. |
| G5 | **`brief.md` and `bom.csv` describe a netlist two rounds old.** brief says 111 open pins, 3 active devices and no USB connector; reality is 76, 6 and fitted. All six of `bom.csv`'s `MISSING` rows are present. | **Open.** |

### The assertion's real coverage, demonstrated rather than argued

The reviewer tested `assert_below_abs_max` rather than reasoning about it, and
its **first test was a bad test** — connecting `VDD_CLK` to `+5V` on the built
circuit merged `+2V5` into `+5V`, so twelve signal pins fired and the
conclusion would have been "supply pins are covered", the opposite of the
truth. The passing version builds a minimal circuit with a matched control.

That is the third time in this review round that a first attempt at testing
this assertion produced a confident wrong answer, mine included. The result:

- **supply balls pass silently** — the check skips them by construction;
- **undeclared rails pass silently** — a rail absent from `hv_rails` is
  invisible, so **`"+12V"` must be added when the wall wart lands**, or the
  new supply enters the design with no guard at all.

### What checked out

All 324 GateMate balls, all 25 LTM4622 balls, the FT601Q pin numbers and the
flash pinout match their datasheets exactly. Every regulator programming pin is
fitted. DS1001 §3.2.1's "No restrictions concerning order of voltage
switch-on" makes the unusual core-gating scheme legal.

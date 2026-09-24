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

## D. Needs a decision, not a fix

| # | Question | Why it is open |
| --- | --- | --- |
| D1 | **The reference rail carries the signal.** Predicted −101.1 dBFS third harmonic against a chain held to −136.5 and a target allowing −113.7. The DWA pointer advancing by the code is what shapes mismatch *and* what ties the changing-line count to the code, so the two properties look inseparable; four alternative rules each trade the whole benefit away. Decoupling does not address it — the disturbance is at audio frequency, where the chain's floor would need 170 µΩ at 2 kHz. | The untested idea is a **transition ballast**: `T` is bounded above by 14 and the modulation is the deficit, so dummy lines toggled to make it up flatten the current without touching the selection rule, at the cost of a fully toggling array. Not designed, not costed. It is a prediction from a digital proxy and wants a bench. |
| D2 | **`MUTE_N` mutes by collapsing the analog supplies**, and there is no DC blocking or output mute device at the jack. So every assertion and release is a supply transient straight into the output. | Nothing in `hdl/` asserts it yet, and `parts-notes.md` records the contract. Decide whether the output stage needs a mute relay or the HDL needs a ramp. |
| D3 | **0008's even-order cancellation works against the output stage's loading.** 0008 puts both polarities of a channel on one register die and calls it "real work, not tidiness". The difference amplifier then loads them unequally — the positive transimpedance sees 402 ‖ 604 = 241 Ω, the negative 402 ‖ 1208 = 301 Ω. Both are below the 600 Ω of the OPA1612's lowest published distortion curve, so the asymmetry cannot be costed from the datasheet. | Worth 0008's attention because it works against the property 0008 exists to buy. |
| D4 | **Control words bypass the lock gate**, so the flush path is not protected by lock and a control word seen while hunting will flush the elastic buffer. Safe under the word-alignment argument, and arguably right — but currently an accident rather than a decision. | The real toplevel has not made this choice yet. Make it consciously; it is the one place un-validated stream content reaches a destructive action. |
| D5 | **`ELEM[31:28]` are reserved and nothing drives them.** `interface.md` requires the main board to drive them low; there is no synthesizable top-level in `hdl/rtl/` at all. | Scope, not a bug — but it is on the critical path to a working board. |
| D6 | **The wall-wart redesign is agreed and unimplemented.** 12 V supply, USB data-only with an ADuM4166 at High Speed, charge pump deleted, 200 Ω recoverable. | Needs a decision record superseding 0009, then netlist work. Recorded in `docs/open-items.md`. |
| D7 | **Status word bit layout**, described in prose in 0010 and never mapped to bits. | Blocks the status path only. **Correction:** the prefill threshold and lock state machine were listed here and are already done — `lyrebird_elastic.sv` implements the mute/drain/fill/run sequence with `PrefillWords = 6400`, underrun returning to fill without discarding, and a mute output. `docs/open-items.md` still lists both as open. |

---

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

# Review: the DSP model (`model/`)

Reviewer: review agent, 2026-09-21. Scope: `model/lyrebird_model/*.py` (13
modules), `model/run_*.py`, `model/README.md`, `model/notes-*.md`,
`model/results/*.txt`, `model/export_coefficients.py`. Read-only on everything
else; no git commands run.

Priorities, as given: (1) a sixth stale measurement site, (2) README claims
against the result logs, (3) reproducibility, (4) the model against its own
trap list, (5) coefficient-export consistency.

Out of scope by instruction, and *not* reported below as a defect: the
reference-rail transition-current result in `notes-idle.md` section H is
deliberately a prediction from a digital proxy, and the model has no supply.

---

## Summary

**The sixth stale site exists.** `datapath.rounding_noise`
(`datapath.py:305`) subtracts the arithmetic mean before a Kaiser-windowed
band power, via a second band-power implementation (`band_power_dbfs`) that
never touches `spectra.Measurement`. Measured both ways on the same records:
**it moves nothing, anywhere, by more than 0.01 dB.** The whole datapath-width
section of README.md stands unchanged. The reason is structural -- the record
there is a cascade *difference*, whose offset is a genuine constant, and the
arithmetic and windowed means of a constant are the same number. Fix it
anyway: the guarantee `spectra.remove_dc` was built to provide is "no caller
has to remember", and this caller does not go through the place that
remembers.

**What actually costs something is README.md against the logs.** Seven claims
do not survive the trace:

1. the ties-table "as published" column shows two ~124 dB rows where its own
   argument requires exactly one, and four of its six values disagree with the
   log (2.1);
2. the volume-placement table is in no log, and `run_idle.py`'s F3 -- the only
   thing in the tree that measures it -- runs a different experiment two ways
   over, disagreeing by up to 23.7 dB. I re-ran it: **README is right, the
   regression is wrong** (2.2);
3. the modulator peak-integrator-state table matches no log line and its
   inter-sample row is out by a factor of two; the "worst of six rates" label
   describes a sweep `run_modarith.py` does not perform (2.3);
4. "the fitted gain came out 1.207" is quoted in four places and produced by
   nothing -- `run_programme.py:777` computes it and discards it (2.4);
5. "-77 dBFS" is the log's *prediction*; its measurement is -124.3 (2.5);
6. the alignment margin is given three incompatible values across README, the
   notes and the log (2.6);
7. the "-143.1 against -159.5 dBFS, 18 dB worse" pair is in no log and does not
   reproduce at the recommended widths, where the penalty is 2.0 dB (2.7).

Plus a handful of smaller ones in 2.8, including README quoting **-160.4 dBFS
and -168.7 dBFS for the same offset twenty lines apart**.

Against that, the large majority of README reproduces exactly -- every
cascade, coefficient, order, rotation, end-to-end, headroom, datapath and
programme table checked number by number (2.9).

**Reproducibility is good.** Five of six logs and all three export artefacts
regenerate byte-identically. Two exceptions: `results/idle.txt` cannot be
produced by any invocation of the current `run_idle.py` (section 8), and the
programme results depend on fourteen macOS system sounds whose absence the
script handles *silently* (3.3).

**The export is sound.** JSON, SystemVerilog and hex agree exactly with each
other and with a fresh computation from the model, Q1.22 included, and the
overflow the scaling exists for is real (1.3376 needs 11220984 against a
2^23-1 limit). One latent hazard: the `.sv` header states a scaling rule that
is **wrong for `ModA` by exactly a factor of two** (5.3).

**One trap the code still steps in**: trip criteria are still relative to a
median, including in the regression `run_endtoend.py` explicitly keeps for the
purpose, where a relative criterion cannot see a uniform shift (4.3).

**The retracted claim is still in the tree.** "A delta-sigma loop turns a
static input offset into idle tones" survives in `datapath.py`'s module
docstring with its retracted 16.8 dB, and is printed into the current
`results/endtoend.txt` twice -- once directly above the table that measures the
cost at 0.02 dB (4.5).

---

## 1. Stale measurement sites

### 1.1 FINDING (high): `datapath.rounding_noise` removes the arithmetic mean before a Kaiser transform

`model/lyrebird_model/datapath.py:305-306`

```python
offset = float(e.mean())
noise = band_power_dbfs(e - offset, mode.element_clock, band)
```

`band_power_dbfs` (`datapath.py:256-263`) calls
`spectra.power_spectrum(x)` with no window argument, so it windows with the
same Kaiser beta 26 every other measurement uses, and integrates
`f >= 20 Hz`. The mean subtracted one line earlier is the *arithmetic* mean.
This is the exact construction `spectra.remove_dc` exists to prevent, at a
sixth site that `notes-idle.md`'s "five sites" table does not list.

It is not routed through `spectra.Measurement`, so the `dedc=True` default
never sees it, and `spectra.remove_dc` is never called on this path.

What it feeds -- every number in README.md's "Datapath width" section:

* the per-stage minimum-fractional-bits table (27/26/26/25/24/24/24/23/22);
* the taper-versus-flat table (-155.9 / -153.3 / -160.5 / **-165.5** /
  -172.0 dBFS) and therefore the "the taper is 9.6 dB noisier" finding and the
  28-bit signal-word recommendation;
* the accumulator table's "signal word alone" column and its 35/33/31 grouping;
* the "Datapath noise" column of "What the recommended datapath measures";
* the trap-list claim "Measured on the nine-stage chain it was -143.1 dBFS
  against a rounding noise of -159.5 dBFS".

Measured below in section 1.2.

### 1.2 Quantified: the sixth site is real but numerically inert

Measured the way the idle thread did it -- **one record, two mean removals,
nothing else changed** -- by replicating `rounding_noise` and taking both
`e - e.mean()` and `spectra.remove_dc(e)` through the same
`band_power_dbfs`.

README's taper-versus-flat table, both ways, 48 kHz / 192 kHz:

| Schedule | 48 k arith | 48 k windowed | moved | 192 k arith | 192 k windowed | moved |
| --- | --- | --- | --- | --- | --- | --- |
| taper 26..22 | -155.88 | -155.89 | +0.00 | -156.31 | -156.31 | +0.00 |
| flat 24 | -153.31 | -153.31 | +0.00 | -159.06 | -159.06 | +0.00 |
| flat 25 | -160.54 | -160.54 | +0.00 | -165.45 | -165.45 | +0.00 |
| **flat 26** | **-165.52** | **-165.52** | +0.00 | **-172.32** | **-172.32** | +0.00 |
| flat 27 | -171.98 | -171.98 | +0.00 | -178.79 | -178.79 | +0.00 |

The recommended widths (flat 26, `ACC_FRAC` as shipped), all six rates, both
rounding rules -- the half-up rows are the interesting ones because that is
where a real offset exists:

| Rate | Rounding | arith | windowed | moved | mean left in | offset |
| --- | --- | --- | --- | --- | --- | --- |
| 48 kHz | half even | -165.85 | -165.85 | +0.000 | -165.85 | -327.3 dB |
| 48 kHz | half up | -165.73 | -165.74 | +0.004 | -163.71 | -168.8 dB |
| 96 kHz | half up | -168.65 | -168.65 | +0.002 | -165.20 | -169.2 dB |
| 192 kHz | half up | -172.34 | -172.34 | +0.000 | -166.70 | -169.3 dB |
| 44.1 kHz | half up | -165.90 | -165.90 | +0.001 | -163.92 | -169.1 dB |
| 88.2 kHz | half up | -168.45 | -168.46 | +0.001 | -165.33 | -169.3 dB |
| 176.4 kHz | half up | -171.78 | -171.78 | +0.000 | -166.68 | -169.4 dB |

The per-stage grid was also taken both ways at 22..27 fractional bits for all
nine stages: **every one of the 54 cells moves by less than 0.05 dB.**

**Nothing in README.md moves.** The 28-bit signal word stands, the 9.6 dB
taper claim stands, the accumulator grouping stands, and the "at most 0.07 dB"
sizing cost stands. The reason is structural and worth recording: `e` here is
the *difference* of two cascade runs, so it is stationary rounding noise whose
offset is a genuine constant. The arithmetic and windowed means of a constant
are the same number. The artefact bites when the offset **drifts across the
window**, which is what a modulator trajectory does and a cascade difference
does not.

**Still fix it.** The defence `spectra.remove_dc` provides is that no caller
has to remember; this caller does not go through `Measurement` at all, so the
defence has a hole in exactly the shape of the bug it was built for. If anyone
ever points `rounding_noise` at a record with a drifting offset -- a modulator
output, a longer record, a signal-dependent width schedule -- it will be wrong
and there is nothing in the code to stop it. The one-line fix is
`noise = band_power_dbfs(spectra.remove_dc(e), ...)`, keeping `offset =
float(e.mean())` for the separately-reported DC figure, which is the right
statistic for a DC report.

`band_power_dbfs` itself (`datapath.py:256`) is the second half of the hole: it
is a public function that windows with the Kaiser and integrates from 20 Hz,
and it does no DC removal of its own. It has one caller today.

### 1.3 `dedc=False` audit

`dedc=False` appears at six places, all legitimate side-by-side demonstrations:

* `run_idle.py:179,203` -- the A-section "same record measured two ways" table;
* `run_idle.py:499` (`_legacy_measure`, used by section D/E) and
  `run_idle.py:915` -- the window-length sweep figure;
* `lyrebird_model/idle.py:341` -- `Trial.b_legacy`, documented at
  `idle.py:268` as "what was measured before";
* `lyrebird_model/idle.py:146` -- the `bands(..., dedc=)` parameter itself.

No production measurement path uses it. One documentation slip: `spectra.py:143`
and `notes-idle.md` both say `dedc=False` "exists only so `run_idle.py` can
show the two side by side", but `lyrebird_model/idle.py:341` also uses it (for
`run_idle.py`'s benefit, so the claim is true in spirit) and **`run_programme.py`
runs the same comparison by hand** at `run_programme.py:688` with
`raw - raw.mean()` rather than through the `dedc` flag. That is deliberate and
correctly labelled in its own log text, but it means there are two independent
spellings of "the old way" in the tree.

### 1.4 Other `x.mean()` uses, checked and cleared

| Site | Verdict |
| --- | --- |
| `idle.py:489-491` (`component_at`) | **Fine.** The projection there is an unwindowed inner product against cos/sin, and for a rectangular window the arithmetic mean *is* the mean the transform sees. |
| `idle.py:344-345` (`out_mean`, `lsb_per_window`) | **Fine and required.** These count unbalanced samples on the `(2/7)/N` grid; the arithmetic mean is the definition. |
| `run_idle.py:218` (per-block imbalance) | Same, fine. |
| `run_idle.py:1202,1258,1286,1375` (rail current) | **Fine.** The arithmetic mean defines the DC term of the rail current; the AC remainder is then measured through `spectra.remove_dc`. |
| `run_programme.py:1034` (`wp - wp.mean() + 1.0`) | Fine, element-weight trimming, not a spectrum. |
| `programme.py:141` (`rms`), `material.py:143` (stereo fold) | Fine. |
| `analog.py:237` (`mean_square`) | See section 4.3 -- it is a Parseval total, not a band measure, but it does include DC. |

---

## 2. README.md against the result logs

Method: every quantitative claim in README.md was traced to a line in
`model/results/`. Most of them land. The tables that reproduce **exactly**,
claim for claim, are listed in 2.9 so the failures below are not read as a
verdict on the whole document.

### 2.1 FINDING (high): the "which way ties go" table's last column cannot be what it says it is

README.md:513-525 (table at 517-525). Caption: *"the last column is the figure this table used to
print, from the same records over 2^20 with the arithmetic mean removed."*

| Rate | README:517-525 "Ties up, as published" | `results/idle.txt:295-306`, half_up, 2^20 plain |
| --- | --- | --- |
| 48 kHz | 137.45 | **137.56** |
| 96 kHz | **124.58** | **140.23** |
| 192 kHz | 143.43 | **143.76** |
| 44.1 kHz | 124.73 | 124.73 |
| 88.2 kHz | 140.14 | 140.14 |
| 176.4 kHz | 142.79 | **143.20** |

Four of six rows disagree with the log. Two of the six (44.1 kHz and
88.2 kHz) match today's re-run exactly; the other four do not, and at least one
of them is provably historic -- `results/idle.txt:282` names **124.58 at
96 kHz** as the number README *used to* report, quoted there as history rather
than measured. So the column mixes at least two sources, whatever the
provenance of the remaining three.

This is not cosmetic. **The column shows a ~124 dB row at 96 kHz and another
at 44.1 kHz simultaneously**, and the paragraph immediately below it makes the
central argument of the retraction from the fact that there is only one and it
moved: *"re-running the old code today puts the 124 dB row at 44.1 kHz, not
96 kHz."* One set of records cannot produce both. As printed, the table
undercuts the argument it is there to support.

The first two columns (Ties up / Ties to even) match `results/idle.txt`'s
2^22-windowed column exactly, and "Worst case costs 0.02 dB" matches
`results/endtoend.txt:227`. Only the third column is wrong.

### 2.2 FINDING (high): the volume-placement table has no log, and the regression that claims to cover it runs a different experiment

README.md:889-902, "Volume goes at the modulator input".

No file in `model/results/` contains that table. `gain_at` exists in exactly
one place in the tree -- `run_idle.py:505` (`_chain_record`) -- and the only
log of it is `results/idle.txt:446-455`, section F3, which disagrees badly:

| Attenuation | README, chain input | idle.txt F3, input | README, mod input | idle.txt F3, modulator |
| --- | --- | --- | --- | --- |
| -6 dB | 140.3 | **134.60** | 140.3 | 140.27 |
| -20 dB | 138.7 | **120.59** | 140.2 | 140.16 |
| -40 dB | 123.9 | **100.16** | 134.2 | 133.47 |
| -60 dB | 104.2 | **80.54** | 114.6 | 113.44 |

Up to 23.7 dB apart on the input column. I ran the experiment myself to find
out which is right, and **README is right and F3 is wrong**, for two
independent reasons in `run_idle.py`:

1. `run_idle.py:531` applies the input gain **before** `quantize_pcm`. The
   volume control is in the FPGA, downstream of the 24-bit PCM the host sends,
   so the gain belongs *after* the source quantizer. As coded, the input
   column mostly measures the 24-bit source losing the attenuation -- which is
   why it falls very nearly 1 dB per dB (134.6 / 120.6 / 100.2 / 80.5).
2. `run_idle.py:727` (`_job_f_vol`) passes `coeff_bits` but **not**
   `sig_frac` / `acc_frac`, so the interpolator runs at exact precision. The
   interpolator's rounding is the entire mechanism README's recommendation
   rests on ("the interpolator's rounding is added after the attenuation and
   stays fixed while the signal shrinks"), and it is absent from the run.

Reproduced at 96 kHz, order 3, 2^20, one tone, three ways:

| Attenuation | gain before the 24-bit quantizer (F3 as coded) | gain after it, exact datapath | gain after it, **sized datapath** | at the modulator input | README |
| --- | --- | --- | --- | --- | --- |
| -6 dB | 133.82 | 139.62 | **139.47** | 139.55 | 140.3 / 140.3 |
| -20 dB | 119.82 | 139.57 | **137.95** | 139.55 | 138.7 / 140.2 |
| -40 dB | 99.24 | 132.63 | **123.06** | 133.16 | 123.9 / 134.2 |
| -60 dB | 79.83 | 102.98 | **102.98** | 114.58 | 104.2 / 114.6 |

The bolded column reproduces README to within about 1 dB (dither seed and
coherent-tone length differ). Note the middle column: **with an exact
datapath the two placements are identical at every attenuation.** So F3 could
not have shown the effect even with the gain in the right place.

Consequences:

* README's volume table and the "roughly 10 dB" conclusion are **sound**, and
  nothing in the tree currently regenerates them.
* `notes-idle.md:274-275` reports F3 as confirming that "the 'volume goes at
  the modulator input' result" is unaffected by the mean-removal fix. The
  *delta* it measured is genuinely 0.00-0.01 dB, but the run it measured that
  delta on is not the experiment README reports, so the confirmation does not
  reach as far as the note claims.

### 2.3 FINDING (medium): the modulator peak-state table is not in any log and contradicts the one that is

README.md:849-852:

| | Integrator 1 | Integrator 2 | Integrator 3 |
| --- | --- | --- | --- |
| 1 kHz tone at -3.7 dBFS, worst of six rates | 0.069 | 0.265 | 0.361 |
| Inter-sample content at its max stable level | 0.082 | 0.400 | 0.630 |

None of those six numbers appears anywhere in `model/results/`.
`results/modarith.txt:28-33` is the only peak-state table in the tree:

```
   1000 Hz  -3.7     166.3      0     [0.070, 0.266, 0.340]
   6000 Hz  -3.7     166.4      0     [0.068, 0.259, 0.348]
  19000 Hz  -3.7     169.8      0     [0.068, 0.257, 0.344]
   1000 Hz  -0.9     165.5      0     [0.100, 0.520, 0.823]
        inter-sample       n/a      0     [0.050, 0.210, 0.279]
```

Two problems. `run_modarith.py:33` fixes `FS = chain.ELEMENT_CLOCK["48k"]`
and sweeps *tone frequency*, not sample rate -- **there is no six-rate sweep
to take a worst case over**, so the row label is wrong as well as the numbers.
And the inter-sample row disagrees by more than a factor of two on every
integrator (0.082/0.400/0.630 against 0.050/0.210/0.279).

The recommendation around it survives on the log's own numbers -- the worst
state in the log is 0.823, so one integer bit is still required and still
sufficient -- but the table as printed is unsupported.

### 2.4 FINDING (medium): "the fitted gain came out 1.207" is computed and thrown away

README.md:782 and `notes-programme.md`:634 and `programme.py:63,336` all state
that the un-centred gain fit returned **1.207** instead of 0.9988. That number
is in no log. `results/programme.txt:634-637` prints:

```
    PCM level   fitted gain   error, mean left in   error, mean removed
        -12.0      0.998570                 -88.4                -133.9
        -40.0      0.998569                 -88.4                -122.0
        -70.0      0.998556                 -88.4                -124.1
```

The cause is in `run_programme.py:777-779`:

```python
g_bad, e_bad = fit(False)
g_ok, e_ok = fit(True)
say(f"   {lv:>+10.1f}  {g_ok:>12.6f}  {e_bad:>20.1f}  {e_ok:>20.1f}")
```

`g_bad` is computed and discarded. The table prints the **corrected** gain in
the column headed "fitted gain" beside the **uncorrected** error, under a
heading that says the fit is the thing being demonstrated. So the one number
that would show the trap is the one number not printed, and the 1.207 figure
quoted in three places has no evidence behind it anywhere in the tree. The fix
is to print `g_bad` in that column, or both.

### 2.5 FINDING (medium): a prediction quoted as a measurement, off by 47 dB

README.md:792-793: *"The leftover gain error then injects a pure in-band
residual around -77 dBFS. Restricting the fit to 20 Hz-20 kHz drops it below
-160."*

`results/programme.txt:644-651` says:

```
   in-band residual. Predicted at about -77 dBFS; measured:
   broadband fit: gain 0.998569, in-band error -124.3 dBFS
   in-band  fit: gain 0.998570, in-band error -135.7 dBFS
```

-77 dBFS is explicitly the *prediction*; the measurement is -124.3. README
states the prediction as the result. And "drops it below -160" is in no log --
`programme.py:52` is the only other place it appears, also as an assertion.
The log's demonstration is -124.3 -> -135.7, an 11.4 dB improvement.

The recommendation (fit in band) is right either way; the numbers attached to
it are not the ones measured.

### 2.6 FINDING (medium): the alignment-margin figure disagrees three ways

* README.md:801 -- *"a correct alignment wins by 90 dB or more."*
* `notes-programme.md`:639 -- *"It reads +93 to +112 dB across the six rates."*
* `results/programme.txt:61-67` -- the six-rate column reads **+110.8, +110.2,
  +111.0, +111.7, +112.2, +112.7**.
* `results/programme.txt:672` -- the material guard: *"at least 27 dB below
  what it becomes when the two paths are slid 256 samples apart, over 138
  segments."*

The log's own two numbers are +110 (tone, six rates) and +27 (material, 138
segments). Neither README's "90 dB or more" nor the note's "+93 to +112"
matches either, and the note contradicts its own table earlier in the same
file, which prints +110.2 to +112.7. The number a reader should carry away --
27 dB on material -- is the one neither document states.

### 2.7 FINDING (medium): the interpolator-offset pair in the trap list is in no log, and the penalty it quotes is not reproducible

README.md:745-748: *"Measured on the nine-stage chain it was -143.1 dBFS
against a rounding noise of -159.5 dBFS, so reporting the chain without
removing it made the datapath look 18 dB worse than it is."* Repeated verbatim
at `datapath.py:291-293`.

Neither -143.1 nor -159.5 appears in any log. The current
`results/endtoend.txt:145-149` DC-offset column reads **-327.3 on every
schedule**, because ties-to-even is the default and leaves no offset at all.

Forcing half-up and measuring both ways myself (same records, section 1.2
method):

| Configuration | offset | noise, mean removed | noise, mean left in | penalty |
| --- | --- | --- | --- | --- |
| taper 26..22, half up, 48 kHz | -143.3 dB | -155.78 | — | — |
| **flat 26 + shipped accumulators, half up, 48 kHz** | -168.8 dB | **-165.74** | **-163.71** | **2.0 dB** |
| flat 26 + shipped accumulators, half up, 192 kHz | -169.3 dB | -172.34 | -166.70 | 5.6 dB |

So the offset figure (-143.1) belongs to a *tapered, half-up* chain that is
not the recommendation, the noise figure (-159.5) matches nothing, and at the
widths actually recommended the penalty for leaving the mean in is 2.0 to
5.6 dB, not 18. The claim as written cannot be checked against anything in the
tree.

### 2.8 Smaller mismatches

| Claim | Where | Log says |
| --- | --- | --- |
| "Measured at the modulator input that offset is **-160.4 dBFS**" | README.md:505 | Nowhere. Twenty lines later README itself quotes **-168.7 to -170.3 dBFS** from `results/endtoend.txt:208-227`, for the same quantity. The two differ by 8 dB in one section. |
| near silence, -100 dBFS: "**-126** to -140 dBFS" (corrected column) | README.md:644, `notes-idle.md`:118 | `results/idle.txt:84-114` corrected column runs **-130 to -140**. The -126 is from the *uncorrected* table (`idle.txt:139`, 44.1 kHz) -- a value has leaked across the very columns the section exists to separate. |
| "the in-band figure stays at **-179 dBFS**" for the DC sweep | README.md:654 | `results/idle.txt:198` -- "In band **-181 to -173** dBFS". `notes-idle.md` states the range correctly; README flattens it to a single value that hides the worst row. |
| "widening one to 28 gains 42.3 dB if it is the first and **0.1 to 0.3 dB** if it is either of the others" | README.md:867-868 | `results/modarith.txt:16-18` -- gains are **+42.2**, **-0.2**, **-0.0**. Widening integrator 2 or 3 makes it very slightly *worse*, not better; and the first is 42.2, not 42.3. |
| "one percent elements span **1.2 dB**" | README.md:262 | `results/endtoend.txt` "as built": 133.97 - 132.83 = **1.14 dB**. |
| taper "**9.6 dB** noisier" (README) vs "**10 dB** noisier" (`datapath.py:64`) | both | Log gives -165.5 against -155.9 = 9.6 dB. The module docstring rounds differently. |

### 2.9 What reproduces exactly

Recorded so the above is read in proportion. Every one of these was checked
number by number against its log line and is correct as printed:

* the interpolation-cascade table and the FPGA cost table (`measurements.txt`);
* the coefficient-width table, all seven stages, and the 340-adder total;
* the modulator order sweep and every figure derived from it (16 dB, 42 dB,
  0.7 dB of range);
* the order-2 rotation table and the order-3 correction, including 33.3 dB,
  77.6 dB, 24.7 dB and 8.3 dB;
* the whole "chain end to end" per-rate table and "+27.6 dB";
* the whole "chain as it will be built" table and the 132.8 dB worst case;
* the subsystem-gap table (168.1 / 167.9 / 137.6) and the 4.5 dB undithered
  figure;
* the entire headroom/MSA table, including the 0.918 -> 0.900 correction;
* the datapath budget, the per-stage signal-word minima, the taper-versus-flat
  table, the accumulator table, the L1 bounds, and the recommended-datapath
  verification table;
* all the idle-channel figures: 125.06 -> 143.40, the window sweep, the
  (2/7)/N grid, `+1 -1 +1 -1 0 0 0 0`, 22-of-180 and 6-of-180, 1-of-72 and
  0-of-72, and four of the five idle-material ranges;
* the whole programme section: 111.5 dB, 128.6 dB, 1.1 dB and 27.7 dB, the
  quiet-window table, the overshoot and headroom-needed tables, the rail-
  fraction table, 3.75 dB / 0.09 dB, 1.5 s / 5.9 s, -88.4 dBFS, 34-of-90 and
  the 5.3 dB element-draw spread.

---

## 3. Reproducibility

### 3.1 What I ran, and what came back

All runs were done against a **copy of `model/` in a scratch directory**, so
nothing in the repository was modified. Interpreter:
`/Users/torsten/lyrebird/.venv/bin/python`, numpy 2.5.3, scipy 1.18.1,
macOS 26.6.2.

One exception to "nothing was modified": the very first run, of
`run_modarith.py`, was done in place before I set the sandbox up. It
rewrote `model/results/modarith.txt` with **byte-identical content** (diff
against a copy taken beforehand is empty); only the file's mtime changed.
Every later run was sandboxed. No other file under `model/` was written,
and no figure was regenerated in the repository.

| Script | Wall time | Result |
| --- | --- | --- |
| `run_modarith.py` | 25 s | `results/modarith.txt` **byte-identical** |
| `run_experiments.py` | 8 s | `results/measurements.txt` **byte-identical** |
| `run_endtoend.py` | 2 min 27 s | `results/endtoend.txt` **byte-identical** |
| `run_analog.py` | ~3 min | `results/analog.txt` **byte-identical** |
| `export_coefficients.py` | 2 s | JSON, `.sv` and all seven `.hex` **byte-identical** to the committed files |
| `run_idle.py` | 570 s | `results/idle.txt` identical except timings -- but see section 8 |
| `run_programme.py` | 489 s (the committed log's own footer says 2375 s) | `results/programme.txt` identical except timings and two absolute-path lines |

Determinism is good and deliberate: every random draw in the tree is
explicitly seeded (`quantize_pcm(seed=11)`, `dwa.mismatch(seed=7)`,
`default_rng(4242)`, `default_rng(100 + k)`, …), and there is no bare
`np.random.*` call anywhere. The identical reruns confirm it.

### 3.2 The one unseeded default

`dwa.mismatch(sigma, n, *, seed=None)` (`lyrebird_model/dwa.py:82-91`) passes
`seed` straight to `np.random.default_rng`, so the default draws from OS
entropy. Every call site in the tree passes a seed, so no published figure is
affected — but element mismatch is the term that sets this converter's
performance, and an unseeded default on it is the wrong default. Make it
required, or give it a fixed value.

### 3.3 FINDING (high): the programme results depend on files outside the repository, and their absence is silent

`run_programme.py:104-130`:

```python
if not SOUNDS.is_dir() or shutil.which("afconvert") is None:
    return None, []
...
    except Exception:
        continue
```

`SOUNDS = Path("/System/Library/Sounds")`. The entire real-audio half of
`notes-programme.md` -- the 111.5 dB worst window, the 27.7 dB spread, the
quiet-window penalty, the crest-factor table, the clipping study -- rests on
fourteen `.aiff` files shipped with macOS, converted with `afconvert`.

On this machine it does reproduce: `/System/Library/Sounds` holds exactly the
fourteen files `results/programme.txt:19-32` names, and `afconvert` is at
`/usr/bin/afconvert`. But:

* **On any machine without them the script does not fail.** It prints "No real
  audio found on this machine; synthetic material only" into the log and
  carries on, and most of the tables then silently become synthetic-only. The
  log stays superficially similar -- same headings, same shape -- which is
  precisely the failure mode this repository has been bitten by before.
* **The per-file `except Exception: continue`** discards conversion failures
  one at a time with no record, so a partial set produces a quietly different
  record with no indication in the log beyond the file table.
* macOS ships different sound sets across versions, so "same machine, later
  OS" is enough to change the record.

This is not a reason to stop using real audio -- the finding it produced is
the most interesting one in the model. It is a reason to (a) record the file
list and a checksum of the joined record in the log so a rerun can be shown to
be the same record, and (b) make the absence of the material loud rather than
a footnote, since the alternative is a log that reports synthetic results
under headings that say "real audio".

### 3.4 Other environment dependencies

* `run_idle.py:62` `WORKERS = 8` and `run_programme.py:69` `WORKERS = 6` are
  hard-coded. Results are unaffected (each job is independently seeded and the
  pool only maps), but on a smaller machine these oversubscribe.
* `run_analog.py` imports `scipy.signal.lfilter`; `datapath.self_check` imports
  `scipy.signal.upfirdn`. scipy is therefore a hard dependency of the analog
  path, which `model/README.md` does not state anywhere.
* Nothing reads or writes outside `model/` except `export_coefficients.py`,
  which writes into `hdl/rtl/` and `hdl/sim/coeffs/` (by design).

---

## 4. The code against its own trap list

README.md's "Measurement traps found while building this" is the checklist.
Taken one at a time.

### 4.1 "The FFT has to be long" -- held, with two exceptions

Every reported spectrum is taken at 2^20 or longer: `run_endtoend.N_MEAS`,
`run_modarith.N`, `run_programme.WINDOW`, `run_analog.N_MEAS` are all `1 << 20`;
`run_experiments` measures rotation at 2^21; `run_idle` works at 2^20, 2^22 and
2^23. `N_MSA = 1 << 18` in `run_endtoend` is explicitly commented "stability
only, no spectrum taken", which is correct.

Two places sit below the stated minimum:

* `programme.alignment_margin` (`programme.py:347`) defaults to `n = 1 << 18`
  and takes a band power there. At 2^18 the element-clock bin is 93.75 Hz, so
  the 20 Hz band edge falls below the first non-DC bin and the Kaiser main lobe
  spans 1.1 kHz. It excises no lobes, so the harmonic trap does not apply, and
  it centres with `centre()` first -- but it is a band-limited measurement
  taken at a quarter of the length the model requires of every other one, and
  nothing in the docstring says why that is acceptable here.
* `modulator.max_stable_amplitude` still defaults to `n = 1 << 15`, and
  `results/measurements.txt`'s order sweep still prints the 0.918 that comes
  from it. README corrects this in the headroom section (0.900 at 2^18,
  "0.17 dB optimistic") but the order-sweep table it corrects is left
  uncorrected in both README and the log.

### 4.2 "DC offset dominating a band that starts at 20 Hz" -- held at five sites, open at two

Covered by `spectra.remove_dc` through `Measurement.of` everywhere except the
two paths that do not go through `Measurement`:

* `datapath.rounding_noise` / `datapath.band_power_dbfs` -- section 1.1;
  measured harmless, structurally wrong.
* `analog.Held` (`analog.py:214-258`) -- an independent spectrum and
  `band_power` implementation with **no DC removal at all**. Unlike the
  datapath case this one is *not* the same bug: `Held` uses a rectangular
  transform (plain `rfft`, no Kaiser), for which the arithmetic mean genuinely
  is the mean the transform sees, and `mean_square = np.mean(y*y)` is the
  matching Parseval total. So it is internally consistent. What it does mean is
  that its `band_power(20, 20000)` row carries whatever DC the record has,
  spread by a rectangular window's 1/k skirt. In the log that row reads
  -3.71 dBFS, i.e. it is the tone, so nothing is affected today. Worth a
  comment in the code saying the window choice is what makes the arithmetic
  mean correct there, because the next reader will see `np.mean` and reach for
  `remove_dc`.

(Cosmetic, same table: `results/analog.txt:172` prints "of OOB 1039.19%" for
the audio-band row, a column that has no meaning applied to that row.)

### 4.3 FINDING (medium): "trip criteria relative to a median rather than physical" -- the code still does it, including in the kept regression

`notes-idle.md` lists this among what is *not* established: *"The trip
criterion was relative, not physical."* The code still is:

* `run_endtoend.py:466-473` counts "runs more than 5 dB below their rate's
  median" and the log says *"A non-zero count here means something real has
  appeared, which is why the experiment is kept."*
* `run_idle.py` section B counts trials more than 10 dB above **their own
  cell's median**.

As a regression guard the relative criterion has a specific blind spot worth
stating: it can only fire on *dispersion*. If a future change moved every run
in a row down by 20 dB together, the median moves with them and the count stays
zero. The experiment that is "kept as a regression" cannot detect the class of
regression a reader would most expect it to catch.

The fix is cheap and the model already has the number for it: the corrected
per-rate figures are flat to 0.1 dB, so an absolute floor (say, more than 1 dB
below the corrected figure recorded in `results/endtoend.txt`) would be both
tighter and meaningful. This is the one item on the trap list where the code
still steps in the trap rather than having been fixed.

### 4.4 The rest of the list -- held

| Trap | Where it is honoured |
| --- | --- |
| harmonics must clear the signal lobe (`n > half_lobe * fs / f_sig`) | 2^20 everywhere a tone is measured; `spectra.coherent_bin` forces an odd bin |
| peaks must be read off a faded record | `run_endtoend.head_room` states and does it; `results/endtoend.txt:175` |
| a scalar fit must be taken in the band | `programme.band_gain_terms` restricts to `sel`; demonstrated in the log |
| the mean must be removed from the gain fit too | `programme.band_gain_terms:337-339` centres **both** `x` and `ref` before the fit |
| a headroom window must be centred on the reconstructed peak | done, and demonstrated at `results/programme.txt:656-661` |
| a lag check over a few samples proves nothing | replaced by `alignment_margin`'s ±256-sample comparison |
| per-stage results do not compose | the taper-versus-flat table exists precisely to show it |

### 4.5 Stale prose that contradicts the retraction

The retraction removed the claim *"a delta-sigma loop turns a static input
offset into idle tones at the bottom of the audio band"* from README.md.
It survives in four places, two of which are printed into a current log:

| Site | Text |
| --- | --- |
| `lyrebird_model/datapath.py:42-47` | "8.0e-9 of it ... at the modulator input **costs 16.8 dB of in-band SNR**, because a delta-sigma loop turns a static input offset into idle tones in the lowest bins of the audio band." The retracted claim, with a retracted number, in the module docstring of the module that measures it. |
| `lyrebird_model/datapath.py:291-293` | the -143.1 / -159.5 / "18 dB worse" pair -- section 2.7. |
| `run_endtoend.py:371-372` -> `results/endtoend.txt:370-371` | "it is not harmless -- a delta-sigma loop turns a **static input offset into idle tones** in the lowest bins of the band", printed directly above the table that measures the cost at 0.02 dB. |
| `run_endtoend.py:663` -> `results/endtoend.txt:353-354` | the RECOMMENDATION block: "Round ties to even everywhere: half-up leaves an offset **the modulator turns into low-frequency idle tones**." |

`lyrebird_model/material.py` -- which `notes-idle.md` flags as still stale in
three docstrings -- **has since been corrected** (`material.py:8-12`,
`material.py:64-67`). The note is now the stale one.

Minor: `datapath.py:63` says the taper is "10 dB noisier"; README and the log
say 9.6 dB.

---

## 5. Coefficient export

### 5.1 Verdict: the three outputs agree, exactly

I regenerated all three in a scratch tree and diffed against the committed
files: `model/export/coefficients.json`, `hdl/rtl/lyrebird_coeffs_pkg.sv` and
all seven `hdl/sim/coeffs/stage*.hex` are **byte-identical**. So the committed
artefacts are what the committed source produces.

Then I checked them against each other and against the model independently of
the generator -- parsing the SystemVerilog `'{...}` literals and the hex files
back to integers and comparing with a fresh `halfband.build("48k")` and
`modulator.synthesize_ntf(3)`. Per distinct stage (1, 4, 5, 6, 7, 8, 9):

* JSON taps == `st.hb.quantized(bits)` re-quantized by hand -- **pass**, all 7;
* SV `Stage<i>Coeff` == JSON taps -- **pass**, all 7 (241 taps in total);
* hex, decoded as two's complement at the stage width, == JSON taps --
  **pass**, all 7, including line counts and digit widths;
* `Stage<i>Bits` / `Stage<i>Taps` == JSON `coeff_bits` / `n_taps` -- **pass**;
* JSON taps / 2^(bits-1) reproduces the float taps to 1e-15 -- **pass**;
* stopband figures match -- **pass**.

Widths agree with what the model measures with: `STAGE_BITS` (defaulting to 26
for stages 2 and 3) == `run_endtoend.COEFF_BITS` on all nine stages.
`signal_bits = 28`, `state_bits = [28, 20, 20]`, `state_frac_bits = [26, 18, 18]`
and `state_int_bits = 1` all match README's recommendations and
`results/modarith.txt`.

### 5.2 The Q1.22 scaling is correct, and correctly necessary

`modulator.synthesize_ntf(3).a` = `[0.176262056, 0.763422199, 1.337645586]`.
The third exceeds 1, so a pure signed 24-bit fraction cannot hold it:
`1.3376 * 2^23 = 11220984` against a limit of `2^23 - 1 = 8388607`. Confirmed
by measurement, not by reading the comment.

Exported as `[739297, 3202025, 5610492]` at `coeff_frac_bits = 22`. Dividing
by 2^22 reproduces the floats to a maximum error of 8.4e-8, which is half an
LSB of Q1.22 -- correct rounding. The representable range is |x| < 2.0 against
a needed 1.3376, so there is 0.58 of headroom and no risk of the next NTF
re-synthesis silently overflowing (it would raise in `q()`, which does check).

### 5.3 FINDING (high, latent): the SystemVerilog header states a scaling rule that is wrong for the modulator coefficients

`hdl/rtl/lyrebird_coeffs_pkg.sv:3-4`, the file's only statement about scaling:

```
// Coefficients are signed fixed-point integers. A tap of width N
// represents tap / 2**(N-1).
```

`ModA` is 24 bits wide but scaled at **2^22**, not 2^23. Applying the stated
rule to `ModA` gives `[0.088131, 0.381711, 0.668823]` against the true
`[0.176262, 0.763422, 1.337646]` -- **every modulator coefficient exactly half
its correct value**, i.e. 6.02 dB of loop gain missing in all three feedback
paths. That is not a small error in a third-order loop; it changes the NTF
entirely.

The package does export `ModCoeffFrac = 22`, so a careful integrator has what
it needs. But the header is the thing a reader reads, it is unqualified, and
it is directly adjacent to the array it is wrong about. **No RTL file in
`hdl/` currently imports `lyrebird_coeffs_pkg`**, so nothing is broken today --
this is a trap set for the first consumer, not a live bug. The JSON's own
`note` field gets it right ("half-band taps divide by `2**(coeff_bits-1)`;
modulator coefficients divide by `2**coeff_frac_bits`"); the SV header should
say the same.

### 5.4 The generator contradicts itself about which Q format this is

`export_coefficients.py:37-39`:

```python
# ... Two integer bits are allocated,
# so a coefficient is value * 2**MOD_FRAC in a signed MOD_BITS word.
MOD_BITS = 24
MOD_FRAC = 22          # Q2.22: sign, 1 integer bit, 22 fractional
```

Three namings in four lines: "two integer bits", "Q2.22", and "1 integer bit".
The arithmetic settles it -- 24 = 1 sign + 1 integer + 22 fractional -- and
`q()`'s own error message spells it `Q{bits-1-frac}.{frac}` = **Q1.22**, which
is also the convention README uses elsewhere ("Sign, one integer bit, 26
fractional bits" for the 28-bit signal word). So the label `Q2.22` and the
phrase "two integer bits" are both wrong for a format that is right. Given
that a reader reaching for this comment is reaching for it precisely because
the scaling is unusual, it should say one thing.

### 5.5 Stages 2 and 3 are absent from the package with no explanation

`cascade.distinct()` yields stages 1, 4, 5, 6, 7, 8, 9, so the SV package
defines `Stage1Coeff` and then jumps to `Stage4Coeff`. That stages 2 and 3
reuse stage 1's coefficients at their own rates is stated in README.md and in
`results/measurements.txt`, and is implied by `STAGE_BITS.get(st.index, 26)` --
but the generated package, which is what the RTL reads, says nothing about it.
A one-line comment in the SV (and a `stages_reusing_stage1` field in the JSON)
would close it. Note the JSON's `stages_by_rate` gives stage *counts*, not the
mapping.

### 5.6 Positive check worth recording: one coefficient set really does serve both families

README's "Both rate families share one coefficient set" is load-bearing for the
export, because `export_coefficients.py:69` builds `halfband.build("48k")` and
exports that alone. Verified directly: `halfband.build("48k")` and
`halfband.build("44k1")` produce **bit-identical taps on all nine stages**
(max difference 0.000e+00) and the same `distinct()` set `[1, 4, 5, 6, 7, 8, 9]`.
Exporting one family is correct.

One detail the claim carries with it: `chain.ALPHA = 0.4535` puts the 44.1 kHz
family's passband edge at **19.999 kHz**, one hertz below the 20 kHz top of the
band every measurement in the model integrates to. The droop there is
micro-dB and nothing is affected, but the two numbers are not the same number
and `chain.py:63-65` is the only place that says so.

---

## 6. The notes documents against the logs

`notes-idle.md` and `notes-programme.md` are the primary accounts of the four
retractions, and they are cited from README.md as the full record. Both have
drifted from the logs they describe.

### 6.1 `notes-idle.md` section F5 contradicts itself and the log

Three statements in the same section:

* line ~256: **"Re-run and fixed.** `run_analog.py` was rerun after the
  correction went in, and the diff against the old log is ten lines."
* line 294: "`results/analog.txt` **currently prints** a matched row 12.5 dB
  below the reference it quotes in the following sentence, and does not
  reconcile the two."
* line 315: "Outside README.md, `results/analog.txt`'s Q2e table **needs
  re-running**."

The first is right and the other two are stale. `results/analog.txt:358-364`
holds the corrected table (132.93 / 132.94 / 132.93 / 132.84 / 132.41, costs
+0.00 / -0.01 / -0.01 / +0.08 / +0.52), it quotes the 132.92 dB reference row
two lines later, and the two now agree to 0.01 dB. I re-ran `run_analog.py` and
the log is byte-identical. A reader who acts on line 315 will re-run a script
to fix something already fixed; a reader who acts on line 294 will distrust a
correct log.

### 6.2 `notes-idle.md` section C: "the rotation pointer takes all seven values"

`notes-idle.md:149`. `results/idle.txt:249`: **"pointer takes 5 of its 7
values over 33 trials."** The conclusion the sentence supports (nothing about
the entering state predicts the result) is fine and the correlations quoted
alongside it do match the log. The coverage claim does not.

### 6.3 `notes-idle.md`'s closing item is now the stale one

The note ends with: *"Not changed, and worth a look from whoever owns it:
`lyrebird_model/material.py` still describes the limit cycle as real in three
docstrings."* All three have since been corrected -- `material.py:8-12` now
opens "There is no limit cycle -- that was an analysis-window artifact", and
`material.py:64-67` (`dc_offset`) now says "the loop was once thought to turn
it into idle tones. It does not". The open item should be closed. The genuinely
stale docstrings are in `datapath.py` instead (section 4.5), and no note
mentions them.

### 6.4 `notes-programme.md` contradicts its own table on the alignment margin

Section 2.6 above. The note's instrument table prints +110.8 through +112.7;
its traps section says "+93 to +112 dB across the six rates".

### 6.5 Both notes carry the 1.207 gain figure that no run produces

Section 2.4. `notes-programme.md`:634, README.md:782, `programme.py:63` and
`programme.py:336` all state it; `run_programme.py:777` computes it and throws
it away.

### 6.6 `notes-idle.md` near-silence range

Section 2.8. The "Corrected" column reads "-126 to -140 dBFS" where the log's
corrected column is -130 to -140; -126 is the uncorrected column's value.

---

## 7. Internal inconsistencies inside the model

These are model-versus-model, not model-versus-log.

### 7.1 FINDING (medium): two different element resistors and two different filter capacitors

| Module | Element resistor | Filter cap | Implied pole |
| --- | --- | --- | --- |
| `run_analog.py:69` + `analog.split_element` | 3320 Ω, split 1660 + 1660 | **192 pF** (computed) | 1.000 MHz |
| `lyrebird_model/idle.py:456-458` | `R_HALF = 1.668e3`, so **3336 Ω** | **180 pF** | 1.060 MHz |

`results/analog.txt` contains both inside one section: the split table at line
249 gives `1.00M  1660  1660  830  192 pF`, and the Q2 recommendation at line
405 says "at 1 MHz it costs **180 pF** per element". `notes-analog.md` reports
180 pF. So the analog study recommends a part it did not compute, and the
rail-current study (`idle.py`) uses different values again.

`idle.py`'s values are the right ones in the sense that they match the
hardware (see the cross-section flags), but the analog recommendation and the
two logs should not be quietly at odds about the pole frequency the whole Q2
section is designed around.

### 7.2 The order sweep still prints the short-record MSA

`modulator.max_stable_amplitude` defaults to `n = 1 << 15`, and
`results/measurements.txt`'s order sweep prints MSA 0.918 for order 3. README
corrects it to 0.900 at 2^18 in the headroom section but leaves the number in
the recommendation table it is quoted from. The recommendation does not change;
the table is 0.17 dB optimistic and says so only 400 lines later.

### 7.3 `endtoend.run` removes DC twice

`endtoend.py:235` calls `spectra.remove_dc(x)` and then passes `x` to
`Measurement.of`, which removes it again at `spectra.py:149`. Idempotent and
harmless (the second pass subtracts ~0), but it is the kind of belt-and-braces
that makes the next reader unsure which layer owns the invariant. Now that
`Measurement` owns it, the explicit call can go -- or, better, stay with a
comment saying it is redundant, since `dedc=False` would otherwise silently
change what this function returns.

### 7.4 `run_programme.py:688` spells "the old way" by hand

`raw - raw.mean()` rather than `dedc=False`. Deliberate, correctly labelled in
its own log text, and it is in the section whose whole purpose is the
side-by-side. But it means the tree has two independent spellings of the
retracted method, and only one of them is greppable via the `dedc` flag that
`spectra.py:143` describes as the single controlled way to reproduce it.

---

## 8. Reproducibility, continued: `results/idle.txt` cannot be regenerated by the documented command

Added after the `run_idle.py` rerun finished (570 s on this machine).

Everything in `results/idle.txt` reproduces **bit-identically** except four
elapsed-time lines (`558 s` -> `272 s`, `20 s` -> `15 s`, `121 s` -> `61 s`,
`46 s` -> `37 s`, and the `total`). `results/reference-current.txt` reproduces
byte-identically with **zero** differences. Sections A through G are exact,
including every number section 2 of this review leans on.

But the rerun's `idle.txt` is **216 lines longer**. The committed file ends at
"total 1208 s" after section G; a full run appends the whole of section H to
it as well as writing `reference-current.txt`. And a partial run cannot have
produced the committed file either -- `run_idle.py:main` sets
`_FULL_RUN = set(want) >= set(SECTIONS)` and prints "(partial run: ...;
idle.txt not rewritten)", so `run_idle.py A B C D E F G` does not write
`idle.txt` at all.

So the committed `results/idle.txt` was produced by a version of the script
that predates section H, and **no invocation of the current script reproduces
it**. The evidence is not wrong -- every number in it is confirmed -- but the
file is not what its own generator now emits, which is exactly the property a
result log exists to have.

(Cosmetic, in the same block: section H prints its banner twice, once through
`head()` into the main log and once into `hlog`, so a full run puts
"THE REFERENCE RAIL: TRANSITION RATE, NOT CODE" in `idle.txt` twice in a row.)

### 8.1 Summary of the reproduction

| Log | Reproduces? |
| --- | --- |
| `results/measurements.txt` | byte-identical |
| `results/modarith.txt` | byte-identical |
| `results/endtoend.txt` | byte-identical |
| `results/analog.txt` | byte-identical |
| `results/reference-current.txt` | byte-identical |
| `results/idle.txt` | identical except timings, **but the current script emits 216 extra lines** |
| `model/export/coefficients.json`, `hdl/rtl/lyrebird_coeffs_pkg.sv`, `hdl/sim/coeffs/*.hex` | byte-identical |
| `results/programme.txt` | identical except elapsed times and the two absolute paths in its footer; the fourteen macOS sounds were present on this machine (3.3) |

---

## 9. What this review did not cover

* The analog study's physics (noise budget, amplifier intermodulation, slew)
  was read but not re-derived; only its measurement machinery was checked.
* `halfband.py`'s filter design was checked for output consistency (taps,
  stopbands, both families) but the design method itself was not reviewed.
* `modulator.py`'s NTF synthesis was exercised, not verified against an
  independent implementation.
* `run_programme.py` is 1278 lines and only its measurement paths, its trap
  section and its material loading were read closely.

---

## Appendix: the `run_programme.py` reproduction (added after the run finished)

489 s on this machine against the committed log's 2375 s footer. The diff
against `results/programme.txt` is **56 lines and contains no measurement**:
fourteen elapsed-time stamps in section headers, and the three footer lines
that print `figures ->`, `log ->` and `total ->`. Every number in the file --
the crest-factor table, all 776 windows' statistics, the quiet-window split,
the overshoot and MSA tables, the rail sweep, the element-draw spread, the
instrument cross-check, the detector table and all five trap demonstrations --
reproduces exactly.

The fourteen `/System/Library/Sounds` files were present on this machine and
matched the log's table, so the external-material path was exercised rather
than skipped. That confirms 3.3 as a *latent* hazard, not a live one here.

Two small things the diff exposes:

* `results/programme.txt` embeds **absolute paths** in its footer
  (`/Users/torsten/lyrebird/model/figures`), so the log is not path-independent
  and a rerun from anywhere else diffs on those lines. `results/idle.txt` does
  the same for `reference-current.txt`. Printing paths relative to the
  repository root would make the logs diffable across checkouts.
* The committed log's "WHAT ONE TONE UNDERSTATES" section is stamped 2150 s
  where mine took 389 s, a 5.5x difference on one section while the rest match
  within 3 %. That is machine load rather than anything in the model, but it is
  worth knowing that the timings printed into these logs are not a stable
  property of the code.

**Final reproduction tally: all six result logs and all nine export artefacts
regenerate from the committed source, with the single structural exception of
`results/idle.txt`'s missing section H (section 8).**

---

## Cross-section flags

Every item below is a disagreement between `model/` and something outside it.
Tagged with the review section that covers it.

### Against the hardware

**H1. Three different element resistors and two different filter capacitors.**
*(sections 7.1, 2.9)*
`model/run_analog.py:69` uses 3320 Ω split evenly into 1660 + 1660 (not an E96
pair) with a computed **192 pF** for a 1.000 MHz pole.
`model/lyrebird_model/idle.py:457-458` uses `R_HALF = 1.668e3` (3336 Ω) with
**180 pF**. The built board is **1.69 kΩ + 1.65 kΩ = 3.34 kΩ** with **180 pF**,
giving **1.06 MHz** (`hardware/lyrebird-dac-reva/parts-notes.md:304, 324, 719`).
`results/analog.txt` contains both capacitor values nine lines apart -- the
split table at line 249 says 192 pF, the Q2 recommendation at line 405 (and line 289) says
180 pF -- and `model/notes-analog.md` reports 180 pF as the model's own answer,
which the model did not compute. Audio-band impact is nil (the pole is three
decades up, and `analog.txt`'s own Q2e sweep shows 20 % capacitor tolerance
costing 0.52 dB), but the capacitor-tolerance study is built around a 1 MHz
pole that the board does not have, and one number should serve all three
places.

**H2. Two reference-rail voltages inside the model, one of which disagrees
with 0012.** *(section 7.1)*
`model/lyrebird_model/analog.py:74` sets `V_REF = 3.3` and cites 0012;
`model/lyrebird_model/idle.py:456` sets `V_REF = 3.32`.
`docs/decisions/0012-module-clock-architecture.md:67-70` specifies **3.3 V**.
`hardware/lyrebird-dac-reva/parts-notes.md:348` also writes 3.32 V, so the
value has propagated between model and hardware. Every current in the
reference-rail prediction scales linearly with it, so the study is 0.6 % (0.05 dB)
high -- immaterial to its conclusion, but it is a transcribed hardware constant
in the one study whose credibility rests on its constants being transcribed
correctly, and 3.32 is suspiciously the element resistance in kΩ.

**H3. `hardware/README.md:190-198` attributes an element-mismatch table to the
model that the model does not contain, and it contradicts the model's logs.**
*(section 2.9)*
That table ("Measured end-to-end, order 3, averaged over three element draws")
lists **0.05 % and 0.5 % rows that no model run has ever produced** -- the only
mismatch values measured anywhere in `model/` are 0, 0.1 % and 1 %. Its
192 kHz column reads 138.1 / 137.9 / 137.6 / 133.5 / 129.9 dB where
`model/results/endtoend.txt:324-326` measures **143.83 / 143.52 / 133.97**, and
it makes 192 kHz the *worst* rate where the model makes it the *best*
(137.5 -> 140.2 -> 143.8 matched). The "three element draws" average matches no
run; the only draw study in the tree is five draws at 48 kHz
(`results/programme.txt:456-467`, spanning 5.3 dB). The conclusions drawn from
it -- "one percent to half buys about 4 dB", "past a tenth of a percent buys
nothing" -- rest on rows that do not exist. The page cites
`model/README.md` as its source.

### Against the HDL

**H4. The generated SystemVerilog package states a scaling rule that is wrong
for the modulator coefficients by a factor of two.** *(section 5.3)*
`hdl/rtl/lyrebird_coeffs_pkg.sv:3-4` -- the file's only statement about
scaling -- says "A tap of width N represents tap / 2**(N-1)". `ModA` is
24 bits wide but scaled at 2^22. Applying the stated rule gives
`[0.088131, 0.381711, 0.668823]` against the correct
`[0.176262, 0.763422, 1.337646]`: **every feedback coefficient exactly half
value, 6.02 dB of loop gain missing in all three paths**, which changes the NTF
entirely. `ModCoeffFrac = 22` is exported correctly two lines below, and the
JSON's `note` field states the rule correctly, so this is a header comment
error rather than a data error. **No RTL currently imports the package**, so
nothing is broken today -- it is a trap for the first consumer. Fix at
`model/export_coefficients.py:107-110`.

**H5. The package omits stages 2 and 3 with no explanation.** *(section 5.5)*
`Stage1Coeff` is followed by `Stage4Coeff`. That stages 2 and 3 reuse stage 1's
taps at their own rates is stated in `model/README.md` and
`results/measurements.txt` but nowhere in the generated artefact the RTL reads.
The JSON's `stages_by_rate` gives stage *counts*, not the reuse mapping.
Verified correct on the model side: `halfband.build("48k")` and
`halfband.build("44k1")` produce bit-identical taps on all nine stages, so one
exported set genuinely serves both families and all three rate groups.

**H6. `hdl/README.md:148-150` and `0010:102-105` place volume at a position the
model has not measured.** *(section 2.2)*
Both say volume is "applied inside the interpolation chain at full internal
precision". The model measured exactly two positions -- the chain input and the
modulator input (after stage 9) -- and found roughly 10 dB between them; every
intermediate position is recorded as unmeasurable in
`docs/open-items.md:187-191` ("splitting the cascade breaks either the settling
offset or the coherent FFT window"). The HDL wording permits a middle position
that carries no measured figure. Pin it to "after the final half-band stage,
at the modulator input" until a middle position is measured. **And note that
the model's own supporting evidence for this recommendation is currently
broken** -- see H7.

**H7. The volume-placement figures the HDL is being asked to honour exist only
in `model/README.md`.** *(section 2.2)*
No log in `model/results/` contains them, and the one experiment that does
measure volume placement (`results/idle.txt:446-455`, section F3) disagrees by
up to 23.7 dB because `run_idle.py:531` applies the input gain *before* the
24-bit source quantizer and `run_idle.py:727` omits `sig_frac`/`acc_frac`.
I reproduced the experiment correctly and README's numbers are right to within
about 1 dB, so the HDL guidance is sound -- but anyone auditing it against the
logs will find the opposite and should be told this first.

**H8. Arithmetic the HDL must implement, currently consistent -- keep it pinned
to the export.** *(sections 5.1, 5.2)*
Verified agreeing across `model/README.md`, `results/endtoend.txt`,
`results/modarith.txt`, `model/export/coefficients.json`,
`hdl/rtl/lyrebird_coeffs_pkg.sv`, the seven `.hex` files and
`docs/open-items.md:178-179`:
signal word **28 bits** (1 sign, 1 integer, 26 fractional), flat across all
nine stages; accumulators **35 / 33 / 31 bits** for stages 1-3 / 4-5 / 6-9
(fractional 31 / 30 / 29, above the point 4 / 3 / 2); **round ties to even** at
every rounding; coefficient widths **26, 26, 26, 22, 19, 18, 10, 8, 8**;
modulator states **[28, 20, 20]** at Q1.26 / Q1.18 / Q1.18; modulator
coefficients **Q1.22 in 24-bit words** (`results/modarith.txt` says 10 bits
total would do, so the export is deliberately generous). No disagreement found
-- flagged so the reconciler has the list.

**H9. `export_coefficients.py` mislabels the format it generates correctly.**
*(section 5.4)*
`export_coefficients.py:37-39` says "Two integer bits are allocated" and
comments the constant `# Q2.22: sign, 1 integer bit, 22 fractional`. The
arithmetic is Q1.22 (24 = 1 + 1 + 22), which is what `q()`'s own error message
prints and what README uses elsewhere ("Sign, one integer bit, 26 fractional
bits"). Three namings in four lines, in the comment a HDL integrator reads
precisely because this scaling is the unusual one.

### Against the decision records

**H10. `docs/open-items.md:177` still carries a retracted figure.**
*(section 2.9, README.md:184-200)*
"Plain rotation, which one percent elements cost 33 dB without and **0.5 dB
with**." The 0.5 dB is the order-2 reading `model/README.md` explicitly
retracts: at the recommended order 3, one percent mismatch costs **33.3 dB
with rotation** (167.92 dB -> 134.65 dB, `results/endtoend.txt:54-59`).
`hardware/README.md:175-180` has already been corrected on this point;
`open-items.md` has not. The line sits in the section headed "Answered by the
modelling, and no longer open".

**H11. 0012's 110 dB dynamic-range target now has 1.5 dB of margin, not
22.8 dB.** *(section 2.9)*
`docs/decisions/0012:71` sets the 110 dB target and the model's headline
answer against it is 132.8 dB, "22.8 dB over". Measured against real programme
material window by window, the worst 42.7 ms window is **111.5 dB**
(`results/programme.txt:106`). `docs/open-items.md:193-197` records this;
0012 itself does not, and the "+27.5 to +33.8 dB over target" column in
`results/endtoend.txt` is a tone's margin presented without that caveat.

**H12. No decision record carries the headroom budget the model has just
revised.** *(section 2.9)*
The model now measures **5.39 dB** needed for clipped percussive material
against the standing 3 dB budget, and recommends a **clipper at the modulator
input rather than a -3 dBFS volume default**
(`results/programme.txt:308-311`). `0010` covers volume placement and
ultrasonic headroom but states no headroom budget and mentions no clipper, and
`hdl/README.md` does not either. The recommendation currently lives only in
`model/README.md` and `notes-programme.md`.

**H13. Seen and deliberately not flagged.** The reference-rail transition-current
result (`notes-idle.md` section H, `results/reference-current.txt`) is a
prediction from a digital proxy, the model has no supply, and
`docs/decisions/0008:112-120` already carries the correction it prompted.
Recorded here only so the reconciler knows it was checked rather than missed.

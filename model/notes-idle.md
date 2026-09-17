# Idle-channel behaviour: the low-frequency limit cycle

Run: `./.venv/bin/python model/run_idle.py`. Log in `results/idle.txt`,
figures in `figures/idle*.png`.

## The headline

**The 15 to 19 dB loss is a measurement artifact, not a loop fault.** The
tripped run README.md reports at 125.06 dB measures **143.40 dB** when the
*windowed* mean is removed from the same record instead of the arithmetic
mean, and **143.69 dB** when the same trajectory is measured over 2^21 with
nothing else changed. Both agree with the 143.31 dB its neighbour in the table
reports.

The same term is behind two other published results:

* **The 15.7 dB attributed to round-half-up is the same artifact.** Corrected,
  half-up and ties-to-even differ by 0.01 dB. Section D.
* **The capacitor-tolerance table in `results/analog.txt` (Q2e) is 12.5 to
  15.7 dB low on every row, and its cost column is wrong by up to 3.2 dB.**
  Section F5.

Everything else checked is unaffected, to 0.01 dB. The full list is in
section F.

There is a real effect underneath all of it, and it is 128 dB down and below
the audio band.

## A. What a 2^20 transform does to a 20 Hz question

The tripped 176.4 kHz run reproduces exactly, so it can be taken apart.

| | |
| --- | --- |
| Kaiser beta 26 main lobe half-width | 12 bins |
| 2^20 bin width at 22.5792 MHz | 21.53 Hz |
| so the DC main lobe reaches | +/-258 Hz |
| shortest transform keeping it below 20 Hz | 13.55 M samples, 2^23.7 |

At 2^20 the DC main lobe covers the whole 20-100 Hz band and most of
100 Hz-2 kHz. **At that record length, near-DC energy and low-band energy are
not different measurements.**

And the loop always has near-DC energy, for a reason that has nothing to do
with limit cycles. The output takes eight levels spaced 2/7 apart, so the mean
of an N-sample record can only sit on a grid of (2/7)/N:

| Window | One unbalanced sample is |
| --- | --- |
| 2^20 | -128.3 dBFS |
| 2^22 | -140.3 dBFS |
| 2^23 | -146.3 dBFS |
| 2^24 | -152.4 dBFS |

Measured on the tripped record, per 2^20 block, as a count of unbalanced
samples: `+1.00 -1.00 +1.00 -1.00 +0.00 +0.00 -0.00 +0.00`. One sample per
million, alternating sign. That is a -128.3 dBFS component at about 10.8 Hz —
the smallest non-zero value the output alphabet can express over that window.

### The same 2^20 record, measured two ways

| Mean removed | SNDR | 20-100 Hz | 0.1-2 kHz | 2-20 kHz |
| --- | --- | --- | --- | --- |
| arithmetic (`x - x.mean()`) | 125.06 dB | -130.2 dBFS | -3.7 | -148.4 |
| windowed | **143.40 dB** | **-172.9 dBFS** | -3.7 | -148.4 |

**18.34 dB of the reported figure is the arithmetic mean not being the mean
the transform sees.** The Kaiser weights the centre of the record far above
its ends, so a record whose offset drifts across the window still has a DC bin
after `x - x.mean()`, and that bin's main lobe lands in the lowest audio bins.
Subtracting the windowed mean, `x - sum(w*x)/sum(w)`, removes it exactly. It
is one line and costs nothing:

```python
w = spectra.analysis_window(len(x))
x = x - (w * x).sum() / w.sum()
```

### The same trajectory over longer windows, nothing corrected

Plain mean removal throughout, i.e. the original method:

| Window | Bin | DC lobe reaches | SNDR | 20-100 Hz | below 20 Hz |
| --- | --- | --- | --- | --- | --- |
| 2^20 | 21.53 Hz | 258 Hz | 125.06 dB | -130.2 dBFS | (no bins) |
| 2^21 | 10.77 Hz | 129 Hz | 143.69 dB | -173.9 dBFS | -187.5 dBFS |
| 2^22 | 5.38 Hz | 65 Hz | 143.94 dB | -174.2 dBFS | -189.7 dBFS |
| 2^23 | 2.69 Hz | 32 Hz | 144.11 dB | -173.4 dBFS | -182.0 dBFS |

**The loss is gone by 2^21 and does not come back.** It was never in the loop.

## D. The 15.7 dB attributed to round-half-up is the same artifact

`run_endtoend.rounding_rule` rerun today reproduces the shape of the published
table but at a *different rate*: 44.1 kHz reads 124.73 against ties-to-even's
137.55, where README.md reports the loss at 96 kHz. That alone is the
giveaway — half-up leaves the same offset at every rate, so a fault caused by
the offset cannot move between rates from one run to the next. A lottery over
records can.

Same records, four measurements:

| Rate | Rounding | DC at mod in | 2^20 plain | 2^20 windowed | 2^22 windowed |
| --- | --- | --- | --- | --- | --- |
| 48 kHz | half up | -169.1 dBFS | 137.56 | 137.56 | 138.41 |
| 48 kHz | half even | -198.5 | 137.54 | 137.55 | 138.41 |
| 96 kHz | half up | -169.6 | 140.23 | 140.23 | 141.39 |
| 96 kHz | half even | -193.8 | 140.23 | 140.25 | 141.41 |
| 192 kHz | half up | -169.2 | 143.76 | 143.82 | 144.35 |
| 192 kHz | half even | -204.1 | 143.83 | 143.83 | 144.35 |
| **44.1 kHz** | **half up** | **-169.0** | **124.73** | **137.53** | **137.98** |
| 44.1 kHz | half even | -210.3 | 137.55 | 137.55 | 137.99 |
| 88.2 kHz | half up | -170.3 | 140.14 | 140.15 | 140.88 |
| 88.2 kHz | half even | -187.3 | 140.15 | 140.15 | 140.88 |
| 176.4 kHz | half up | -169.8 | 143.20 | 143.33 | 144.10 |
| 176.4 kHz | half even | -196.8 | 143.31 | 143.33 | 144.07 |

**Measured as published, half-up is up to 12.8 dB worse. Measured properly it
is 0.01 dB worse.**

What survives: half-up does leave a real static offset at the modulator input,
about -169 dBFS against -187 to -210 dBFS for ties-to-even, and that offset
does reach the output as DC. Convergent rounding removes it and costs one
adder's difference, so **the recommendation stands**. The reason given for it
does not.

The sentence in README.md that needs to go is "a delta-sigma loop turns a
static input offset into idle tones at the bottom of the audio band", together
with the table that appears to demonstrate it. At -169 dBFS it does not,
measurably.

## F. Blast radius

`x - x.mean()` is used at five sites that produced published figures. Each row
below is **one record measured twice**, not two runs, so the difference is the
mean removal and nothing else.

### F1. End to end per rate, and the chain as it will be built

| Rate | Elements | As published | Corrected (2^20) | Moved by |
| --- | --- | --- | --- | --- |
| 48 kHz | matched | 137.57 | 137.57 | -0.00 |
| 48 kHz | 1% | 132.92 | 132.92 | -0.00 |
| 96 kHz | matched | 140.27 | 140.29 | +0.01 |
| 96 kHz | 1% | 133.72 | 133.73 | +0.00 |
| 192 kHz | matched | 143.83 | 143.83 | +0.00 |
| 192 kHz | 1% | 133.97 | 133.97 | +0.00 |
| 44.1 kHz | matched | 137.56 | 137.56 | +0.00 |
| 44.1 kHz | 1% | 132.84 | 132.84 | +0.00 |
| 88.2 kHz | matched | 140.18 | 140.18 | +0.01 |
| 88.2 kHz | 1% | 132.83 | 132.83 | +0.00 |
| **176.4 kHz** | **matched** | **125.06** | **143.40** | **+18.34** |
| 176.4 kHz | 1% | 133.32 | 133.32 | +0.00 |

**One row of twelve moves.** It is the one README.md already flags with an
asterisk in the datapath verification table. Everything else is correct as
printed, including the 132.8 dB worst case the hardware is held to.

### F2, F3, F4. Rotation, volume placement, order sweep

Nothing moves, to 0.01 dB, in any row:

* element mismatch and rotation (`run_experiments.py:210`), 10 rows at 2^21,
  orders 2 and 3, mismatch 0/0.1/1%, rotation on and off — max move 0.00 dB;
* volume at the chain input against volume at the modulator input, 8 rows —
  max move 0.01 dB;
* the modulator order sweep, orders 2 to 5 — max move 0.00 dB.

So the rotation recommendation, the 33.3 dB mismatch correction, the "volume
goes at the modulator input" result and the order choice are all unaffected.

### F5. The analog section: `results/analog.txt` Q2e is wrong on every row

This is the second real casualty. The capacitor-tolerance table applies a
1 MHz pole per element to the 48 kHz, 1% element record and re-measures.

| C tolerance | As published | Corrected (2^20) | Corrected (2^21) | Moved by |
| --- | --- | --- | --- | --- |
| matched | 120.43 | 132.93 | 133.75 | +12.50 |
| 2% | 119.98 | 132.94 | 133.75 | +12.96 |
| 5% | 119.34 | 132.93 | 133.73 | +13.59 |
| 10% | 118.37 | 132.84 | 133.62 | +14.47 |
| 20% | 116.70 | 132.41 | 133.15 | +15.70 |

And the column the table exists for, the cost of tolerance:

| C tolerance | Cost as published | Cost corrected |
| --- | --- | --- |
| 2% | +0.45 dB | -0.01 dB |
| 5% | +1.09 dB | -0.01 dB |
| 10% | +2.06 dB | +0.08 dB |
| 20% | +3.72 dB | +0.52 dB |

The corrected matched row, 132.93 dB, is the reference row's own 132.92 dB to
0.01 dB — which is the check that says the corrected numbers are the right
ones, because a pole three decades above the band should cost nothing and now
does. `results/analog.txt` currently prints a matched row 12.5 dB below the
reference it quotes in the following sentence, and does not reconcile the two.

The conclusion drawn there is unchanged and in fact stronger: ordinary C0G
parts are adequate, 20% tolerance costs 0.52 dB rather than 3.72 dB.

## Which published numbers in README.md are wrong

1. **The "which way ties go" table**, and the claim that half-up costs 15.7 dB
   worst case. Corrected, the worst case is 0.01 dB. The recommendation
   survives; the justification does not.
2. **The low-frequency limit cycle section in full.** There is no limit cycle.
   The 125.1 dB figure, the 15-19 dB range, the 1-in-36 rate and the statement
   that dither moves which run trips are all descriptions of the transform.
3. **The asterisked 176.4 kHz reference row** in the datapath verification
   table, 125.06 dB, is 143.40 dB.

Everything else checked — every per-rate figure, the 132.8 dB worst case, the
rotation table, the order sweep, the volume placement, the datapath widths —
is correct as printed.

Outside README.md, `results/analog.txt`'s Q2e table needs re-running.

## What the real effect is, and why it does not matter

The loop's output over any finite window carries a residual DC of a few times
(2/7)/N, because the output alphabet cannot express the input's mean exactly
over a finite record. Over 2^20 samples that is one sample in a million, a
-128.3 dBFS component at around 10 Hz. It is:

* below the audio band, not in it;
* at the smallest level the output alphabet can express over that window, so
  it cannot be reduced by anything in the digital design;
* removed from the output by the coupling capacitor the design already has.

It is not a limit cycle, it is not periodic, and nothing in the loop is
locking. The rest of this note's measurements confirm that directly.

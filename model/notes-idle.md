# Idle-channel behaviour: the low-frequency limit cycle

Run: `./.venv/bin/python model/run_idle.py`. Log in `results/idle.txt`,
figures in `figures/idle*.png`.

*Written incrementally as the runs finished; sections appear in the order they
were measured.*

## The headline

**The 15 to 19 dB loss is a measurement artifact, not a loop fault.** The
tripped run README.md reports at 125.06 dB measures **143.40 dB** when the
*windowed* mean is removed from the same record instead of the arithmetic
mean, and **143.69 dB** when the same trajectory is measured over 2^21 with
nothing corrected at all. The two agree with the 143.31 dB its neighbour in
the table reports.

There is a real effect underneath, and it is 128 dB down and below the audio
band. It is described below. It is not a reason to change anything in the
design.

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
Subtracting the windowed mean, `x - sum(w*x)/sum(w)`, removes it exactly.

### The same trajectory over longer windows, nothing corrected

Plain mean removal throughout, i.e. the original method:

| Window | Bin | DC lobe reaches | SNDR | 20-100 Hz | below 20 Hz |
| --- | --- | --- | --- | --- | --- |
| 2^20 | 21.53 Hz | 258 Hz | 125.06 dB | -130.2 dBFS | (no bins) |
| 2^21 | 10.77 Hz | 129 Hz | 143.69 dB | -173.9 dBFS | -187.5 dBFS |
| 2^22 | 5.38 Hz | 65 Hz | 143.94 dB | -174.2 dBFS | -189.7 dBFS |
| 2^23 | 2.69 Hz | 32 Hz | 144.11 dB | -173.4 dBFS | -182.0 dBFS |

**The loss is gone by 2^21 and does not come back.** It was never in the loop.

### Consequence for the existing tables

Every figure in README.md measured over 2^20 with `x - x.mean()` carries this
term. It is only visible when the loop's near-DC wander happens to be large
enough, which is why it looked like a rare fault: the 1-in-36 rate is the rate
at which a residual of one or two unbalanced samples per window lines up with
the window's centre weighting, not the rate of anything happening in the loop.
Two consequences worth checking in the other results:

* **`x - x.mean()` is not enough anywhere.** Use `x - sum(w*x)/sum(w)`.
* The 15.7 dB attributed to round-half-up in the "which way ties go" table has
  the same size and the same signature. It is checked in section D below.

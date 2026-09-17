# The chain against programme material

Measured by `run_programme.py`, log in `results/programme.txt`, figures
`figures/programme*.png`. README.md closes with "Only tones have been run".
This runs material with a real crest factor, window by window over a long
record, against the four claims that rested on tones: the 132.8 dB worst case,
the 3 dB headroom budget, the low-frequency wander, and the habit of reporting
one in-band number per record.

*(Draft in progress — sections are filled in as the run produces them.)*

## The material is real, at one rate

Fourteen 48 kHz 24-bit recordings from `/System/Library/Sounds`, converted to
WAV with `afconvert` (format only, no resampling) into a temporary directory
and read through `material.read_wav`. Nothing downloaded, nothing resampled.

| | Real, joined | programme-like | percussive | sustained bass | 1 kHz sine |
| --- | --- | --- | --- | --- | --- |
| Crest factor | 24.8 dB | 11.6 dB | 21.8 dB | 5.0 dB | 3.0 dB |

16.72 seconds, 392 windows of 2^20 element samples. Per-file crest factors run
from 15.3 to 26.5 dB, which is the range programme material actually occupies
and the range a sine never reaches.

**Real audio exists here only at 48 kHz**, and `material.read_wav` refuses to
resample, which is right. The other five rates are measured with `material.py`'s
synthetic stand-ins and are labelled synthetic everywhere below. The real
recordings also carry nothing above 10 kHz, so they say nothing about the
ultrasonic intermodulation 0010 warns about; that gap stays open.

## The instrument, and why it is not SNR

Signal-to-noise against a tone works by excising the signal lobe. Broadband
material has no lobe to excise and excising the occupied band leaves nothing,
so what is measured here is the **error** against the ideal reconstruction of
the same PCM:

    e = x - g * u_ref

`u_ref` is the cascade output for the unquantized float record at exact
datapath precision; `x` is the element sum for the same record through
everything the hardware does. Both run the same quantized coefficients, so the
cascade's response cancels and what is left is exactly the set of terms the
end-to-end SNDR figure is made of.

Checked against the measurement it replaces, on the one signal where both
work — 1 kHz at -3.7 dBFS, one percent elements, settled widths:

| Rate | Classic SNR | Classic SNDR | Error instrument | Error, dBFS |
| --- | --- | --- | --- | --- |
| 48 kHz | 133.49 | 132.94 | 134.21 | -137.91 |
| 96 kHz | 124.29 | 124.23 | 125.72 | -129.42 |
| 192 kHz | 134.07 | 133.74 | 135.11 | -138.81 |
| 44.1 kHz | 132.96 | 132.49 | 133.65 | -137.35 |
| 88.2 kHz | 134.06 | 133.53 | 134.69 | -138.39 |
| 176.4 kHz | 134.12 | 133.69 | 134.88 | -138.58 |

**The two instruments agree to between +1.16 and +1.49 dB, mean +1.27 dB**, and
the offset has a known cause: the classic figure rescales the noise bins it
kept to cover the ones it excised, which is about +1.1 dB of noise it did not
measure. Every material figure below is on the error instrument and carries
that offset; it is stated rather than corrected away.

The fitted gain came back 0.998570 at every one of the six rates, which is the
check that a scalar is the right model for element mismatch: the same physical
weights, the same gain, independent of rate and of material.

Two traps were handled rather than reasoned about, and both would have produced
confident nonsense.

**The gain has to be fitted in band.** One percent elements leave a static gain
error of 0.14 percent. A tone measurement never sees it because the fundamental
is excised; an error measurement sees all of it, and 0.14 percent of a -3.7 dBFS
signal is an error at -60 dBFS sitting on top of a floor at -138. Fitting the
gain broadband does not fix it: the fit is then dominated by the modulator's
out-of-band noise, which is 90 dB louder than the in-band error, and the
resulting gain error injects a spurious in-band residual of about -77 dBFS.
Restricting the fit to 20 Hz-20 kHz drops that artefact below -160 dBFS.

**The alignment has to be checked, not assumed.** It came back at lag 0 at
every rate, as the topology says it must — the STF is exactly 1 with zero
delay. The check itself needed hardening: taken on the first samples of a
record it reports the lag of whatever silence happens to start the record, so
it is taken on the loudest stretch and skipped when there is nothing loud
enough to decide on.

### Decomposition, 48 kHz, one percent elements

| | In band |
| --- | --- |
| Total error | -137.91 dBFS |
| 24-bit TPDF source alone | -142.45 dBFS |
| Everything else (mismatch residual) | -139.79 dBFS |

Which is README.md's claim, now measured by subtraction rather than inferred:
source word length and element tolerance are within 2.5 dB of each other and
nothing else in the digital chain is close.

### A tone tripped the wander at 96 kHz

The 96 kHz row above is 9.4 dB below its neighbours in **both** instruments.
That is the low-frequency wander README.md describes, tripped by a 1 kHz tone
at the recommended widths with ties to even. The only difference from
`run_endtoend.py`'s 133.7 dB at the same rate and the same widths is that this
run feeds the modulator 2^18 samples of warm-up before the measured window, so
the loop enters the window in a different state. README.md says a perturbation
of 2^-40 switches this on or off; a quarter of a second of warm-up does the
same. It is more evidence that the fault is real, that it is a property of the
loop, and that a single record's figure cannot be trusted without looking at
where in the band it came from.

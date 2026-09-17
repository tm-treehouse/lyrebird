# The chain against programme material

Measured by `run_programme.py`, log in `results/programme.txt`, figures
`figures/programme*.png`. README.md closes with "Only tones have been run".
This runs material with a real crest factor, window by window over a long
record, against the four claims that rested on tones: the 132.8 dB worst case,
the 3 dB headroom budget, the low-frequency wander, and the habit of reporting
one in-band number per record.

*(Draft: Q1, Q3 and Q4 tables are being refilled from a corrected run; see
"A measurement trap that cost a whole pass" below for why.)*

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
synthetic stand-ins and are labelled synthetic everywhere. The real recordings
also carry nothing above 10 kHz, so they say nothing about the ultrasonic
intermodulation 0010 warns about; that gap stays open.

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

### Decomposition, 48 kHz, one percent elements

| | In band |
| --- | --- |
| Total error | -137.91 dBFS |
| 24-bit TPDF source alone | -142.45 dBFS |
| Everything else (mismatch residual) | -139.79 dBFS |

Which is README.md's claim, now measured by subtraction rather than inferred:
source word length and element tolerance are within 2.5 dB of each other and
nothing else in the digital chain is close.

## A measurement trap that cost a whole pass

This is the most transferable thing in these notes, so it goes first.

README.md's rule is "remove the mean before measuring". That is necessary and
it is not sufficient. This measurement removes the mean from the error, as the
rule says — but the **scalar gain fitted before that subtraction** was fitted on
un-centred signals. Element mismatch leaves a static offset on the element sum;
at 23.4 Hz bins a Kaiser main lobe is twelve bins wide, so that offset leaks up
to 280 Hz, which is inside the 20 Hz-20 kHz band the fit is taken over. The
offset therefore biases the fitted gain by whatever the reference happens to
carry down there — nothing when the music is loud, everything when it is quiet.

Measured, on a real-audio record at one percent elements:

| PCM level | Fitted gain, mean removed | Error, mean left in | Error, mean removed |
| --- | --- | --- | --- |
| -12 dBFS | 0.998570 | -88.4 dBFS | -130.3 dBFS |
| -70 dBFS | 0.998518 | -88.4 dBFS | -123.5 dBFS |

Left in, the fitted gain came out 1.207 instead of 0.9988 on the -70 dBFS
record, and 20 percent of the signal was subtracted as if it were error.

**The tell was that the error stopped moving when the level did.** An error
figure that is identical at -12, -40 and -70 dBFS, to the last decimal and in
the same FFT bins, is not measuring the converter. That is worth adding to the
trap list on its own: *if a figure does not move when you move the input, the
instrument has stopped listening to the input.*

It produced a whole pass of confident, wrong numbers, including an apparent
40 dB collapse of element-mismatch performance against real material that does
not exist. Everything below is from the corrected pass.

Two smaller traps, both handled from the start:

**The gain fit has to be restricted to the band.** Fitted over the whole
record it is dominated by the modulator's out-of-band noise, 90 dB above the
in-band error, whose inner product with the signal is not zero. The leftover
gain error injects a pure in-band residual at around -77 dBFS.

**A lag check over a few samples cannot check anything.** The signal is
band-limited to 20 kHz and sampled at 24.576 MHz, so its autocorrelation is
flat over plus or minus eight samples: an argmax there reports where the
out-of-band noise fell, and it false-alarmed on 34 of 90 segments of real
material. What replaced it is the in-band error at the offset used against the
in-band error 256 samples away — a fifth of a period at 10 kHz, and therefore
a real displacement.

## Q2: the 3 dB budget is right about limited material and short of the worst case

### Nothing but clipping makes an inter-sample over

Peak the cascade presents to the quantizer against the peak in the samples.
Records faded at both ends and scanned in blocks.

| Material | Crest | Samples at FS | True peak | Overshoot |
| --- | --- | --- | --- | --- |
| Real audio, 16.7 s | 24.81 dB | 1 | 1.0000 | **+0.000 dB** |
| Real, clipped 3 dB | 21.86 dB | 190 | 1.0029 | +0.025 dB |
| Real, clipped 6 dB | 19.06 dB | 998 | 1.0083 | +0.072 dB |
| Real, clipped 12 dB | 14.45 dB | 10343 | 1.0781 | +0.653 dB |
| Percussive, synthetic | 21.81 dB | 1 | 1.0033 | +0.029 dB |
| Percussive, clipped 6 dB | 16.09 dB | 542 | 1.3139 | +2.371 dB |
| Percussive, clipped 12 dB | 12.13 dB | 3915 | 1.7532 | **+4.876 dB** |
| Programme, clipped 12 dB | 3.98 dB | 35345 | 1.0399 | +0.340 dB |
| 1 kHz tone | 3.01 dB | 5461 | 1.0000 | +0.000 dB |
| Fs/4 inter-sample probe | 0.00 dB | 131072 | 1.4142 | +3.010 dB |

**Unprocessed material of any crest factor produces no inter-sample overshoot
at all.** Sixteen seconds of real recording, peak normalised to full scale,
hands the quantizer 1.0000. The synthetic percussive record, at a 21.8 dB crest
factor, hands it 1.0033.

What creates the overshoot is the flat run of samples at full scale that only
clipping produces, and the probe is the limiting case of that: every one of its
samples sits at full scale by construction, which is why it reaches exactly
3.010 dB. So the README's framing is right — the probe stands in for heavily
limited material, not for loud material.

**But 3 dB is not a ceiling.** Percussive material clipped 12 dB reaches
+4.876 dB of overshoot, 1.87 dB past the probe. A budget set from the probe is
not conservative for the worst real case; it is 1.9 dB short of it.

### Where material actually overloads the quantizer

Bisection on the PCM level, the same bound as `modulator.max_stable_amplitude`
and `endtoend.max_stable_pcm` — no integrator past 50 quantizer LSBs — with the
window centred on the loudest moment in the record.

| Material | 48 kHz | 192 kHz | Headroom needed |
| --- | --- | --- | --- |
| Real audio | -0.80 dBFS | -0.66 dBFS | 0.8 dB |
| Real, clipped 12 dB | -0.89 dBFS | -0.89 dBFS | 0.9 dB |
| Percussive, synthetic | -0.66 dBFS | -0.42 dBFS | 0.7 dB |
| Percussive, clipped 12 dB | **-3.75 dBFS** | **-3.66 dBFS** | 3.8 dB |
| Programme, synthetic | -0.75 dBFS | -0.56 dBFS | 0.8 dB |
| 1 kHz tone | -0.84 dBFS | -0.84 dBFS | 0.8 dB |
| Fs/4 inter-sample probe | -3.84 dBFS | -3.61 dBFS | 3.8 dB |

**Real material needs 0.8 dB, not 3 dB. Heavily clipped percussive material
needs 3.75 dB, which is what the probe predicted to within 0.09 dB.**

So the probe was not pessimistic and it was not a corner case invented for the
occasion. It is an accurate stand-in for the worst thing a host can send, and
the 3 dB recommendation should stay — but the honest statement of it is that it
is a budget for limited material, and that anything not limited leaves 2.2 dB
of it unused.

The peak the quantizer actually sees at the overload point is -0.3 to -0.9 dBFS
in every row, which is README.md's finding intact: the loop overloads at the
same place regardless of content, and what changes is how much PCM level that
corresponds to.

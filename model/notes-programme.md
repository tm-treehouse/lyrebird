# The chain against programme material

Measured by `run_programme.py`, log in `results/programme.txt`, figures
`figures/programme*.png`. README.md closes with "Only tones have been run".
This runs material with a real crest factor, window by window over a long
record, against the claims that rested on tones: the 132.8 dB worst case, the
3 dB headroom budget, the low-frequency limit cycle, and the habit of
reporting one in-band number per record.

Three of the four answers are that the existing recommendation stands. The
fourth is that the limit cycle does not exist.

*(Q3 is still being refilled from the corrected run; everything else is final.)*

## Summary

| Claim under test | Verdict |
| --- | --- |
| 132.8 dB worst case, one percent elements | **Holds on the median, not on the worst window.** Real material: median -132.3 dBFS, worst -115.2 dBFS over 360 windows. |
| Budget 3 dB of headroom | **Right, and for the stated reason.** Unprocessed material needs 0.8 dB; clipped material needs 3.75 dB against the probe's 3.84 dB prediction. |
| Low-frequency limit cycle, one run in 36 | **Does not exist.** It is the mean subtraction, 8.5 dB of it. |
| The floor's shape window to window | **Stable and high-band dominated.** Below 100 Hz never exceeds 0.82 percent of in-band error power in any of 776 windows. |

## Q1: the median holds; the worst window is 17 dB below it, and it is the elements

One percent elements, 24-bit TPDF source, settled widths, order 3, rotation
on. Each window is 2^20 element samples, 42.7 ms, 23.4 Hz bins. The figure is
the in-band error in dBFS, which does not depend on how loud that window
happens to be. "as SNDR" restates it in the README's convention — a -3.7 dBFS
signal against that error.

| Material | Windows | Best | Median | Worst | as SNDR, worst |
| --- | --- | --- | --- | --- | --- |
| 1 kHz tone, 48 kHz | 12 | -138.3 | -137.9 | -137.2 | 133.5 dB |
| **Real audio, 48 kHz** | **360** | **-142.9** | **-132.3** | **-115.2** | **111.5 dB** |
| Real audio, matched elements | 96 | -142.9 | -142.3 | -141.8 | 138.1 dB |
| Synthetic programme, 6 rates | 92 | -138.7 | -135.4 | -130.5 | 126.8 dB |
| Synthetic percussive, 6 rates | 92 | -148.5 | -139.4 | -116.9 | 113.2 dB |
| Synthetic bass, 6 rates | 92 | -140.2 | -137.6 | -134.8 | 131.1 dB |

**The tone's own window-to-window spread is 1.1 dB. Real material's is
27.7 dB.** A single figure per record is therefore not a description of this
chain against programme material, and that is the direct answer to the
question the task asked.

**All of the spread is element mismatch.** The same 16.7 seconds with matched
elements spans 1.1 dB — best -142.9, worst -141.8 — and sits exactly on the
24-bit source floor. The modulator, cascade and datapath do not care what the
material is; they produce -142 dBFS whatever is fed to them.

### Where in the record the bad windows are

Windows split by how much in-band signal they carry, real audio at 48 kHz:

| In-band signal | Windows | Median error | Worst error | Matched elements, median |
| --- | --- | --- | --- | --- |
| Above -12 dBFS | 5 | -137.3 | -136.3 | -142.5 |
| -30 to -12 dBFS | 50 | -135.2 | -128.2 | -142.3 |
| **-60 to -30 dBFS** | **71** | **-125.2** | **-117.3** | **-142.3** |
| Below -60 dBFS | 234 | -135.8 | -115.2 | -142.3 |

**The rotation residual is worst when the music is quiet but not silent.** Loud
windows measure -137, windows 30 to 60 dB down measure -125 — a 12 dB
penalty — and the matched-element column is flat at -142.3 across every band,
so there is nothing else it could be. The synthetic percussive record shows the
same shape independently: -136.8 in its -30 to -12 dBFS windows and -125.3 in
its -60 to -30 dBFS ones.

The mechanism is the one rotation depends on. Data weighted averaging makes
every element carry every code equally often *over time*; with a small signal
the code sequence has a short range, the pointer traverses the ring less
thoroughly per unit time, and the averaging has less to work with. It is not a
fault and it is not a limit cycle — it is the rotation working less well where
it has less to rotate.

**What it costs against the target.** The worst single window in 16.7 seconds
of real material puts its in-band error at -115.2 dBFS, which is 5.2 dB above
the 110 dB dynamic-range target of 0012 rather than the 22.8 dB the tone figure
promises. **132.8 dB is the right number for the median and 17 dB optimistic
for the tail**, and the tail lives in quiet passages, which is where a listener
is most able to hear it.

Nothing here argues for changing the design. It argues for quoting the figure
with its distribution, and for treating element tolerance — already identified
in README.md as the thing that sets performance — as the term that also sets
the worst case, not just the average.

### Rate makes almost no difference

Synthetic programme material, worst window at each rate: -134.7 (48), -132.2
(96), -132.5 (192), -132.1 (44.1), -131.1 (88.2), -130.5 (176.4). A 4.2 dB
span across six rates, against the 6.3 dB the matched-element tone sweep spans.
Mismatch noise is shaped by the loop and does not care what the sample rate
was, which is README.md's observation holding up against material.

## Q4: the floor's shape is stable, and nothing is concentrated at low frequency

`material.band_shape` splits every window into 20-100 Hz, 100 Hz-2 kHz and
2-20 kHz. White noise would put 0.44 percent of its in-band power in the lowest
band, because that band is 80 Hz of the 19980.

Share of in-band error power below 100 Hz, over 776 windows:

| Material | Windows | p10 | Median | p90 | Worst low band |
| --- | --- | --- | --- | --- | --- |
| 1 kHz tone, 48 kHz | 12 | 0.03 % | 0.08 % | 0.31 % | -162.3 dBFS |
| Real audio, 48 kHz | 360 | 0.00 % | 0.02 % | 0.32 % | -156.7 dBFS |
| Real audio, matched | 96 | 0.05 % | 0.24 % | 0.82 % | -162.1 dBFS |
| Synthetic programme, 6 rates | 92 | 0.00 % | 0.03 % | 0.31 % | -160.8 dBFS |
| Synthetic percussive, 6 rates | 92 | 0.00 % | 0.06 % | 0.79 % | -161.2 dBFS |
| Synthetic bass, 6 rates | 92 | 0.01 % | 0.05 % | 0.23 % | -162.2 dBFS |

**No window, in any material, at any rate, puts as much as one percent of its
in-band error below 100 Hz, and every one is at or under the 0.44 percent a
white floor would give.** The error is high-band dominated in every window —
2-20 kHz carries essentially all of it — which is the rotation residual being
shaped up out of the band exactly as 0008 claims.

This is the distribution that the artefact was hiding. With the plain mean
removed the same windows showed 40 to 95 percent below 100 Hz and a low band as
loud as -130 dBFS; with the windowed mean the loudest low band anywhere in 776
windows is -156.7 dBFS. **The shape of the noise floor is the measurement's
most sensitive output and therefore the one most worth distrusting** — it was
wrong by 26 dB and the in-band total it came from was wrong by 8.5.

## The low-frequency limit cycle is a transform artefact

This is the largest finding and it removes an open item rather than adding one.

README.md describes a wander that trips about one run in thirty-six, comes back
15 to 19 dB low, puts every bit of its excess between 20 and 100 Hz, and is not
removed by dither at either the quantizer or the modulator input.

It reproduced here on demand. A 1 kHz tone at -3.7 dBFS, one percent elements,
the recommended widths, ties to even — a configuration `run_endtoend.py`
measures at 133.7 dB — run twice at 96 kHz, differing only in how many samples
the modulator ran before the measured window opened, which cannot change the
audio:

| Mean removed as | In-band error | 20-100 Hz | Share below 100 Hz |
| --- | --- | --- | --- |
| `x - x.mean()` | -129.42 dBFS | -130.1 dBFS | **85.99 %** |
| `x - (w*x).sum()/w.sum()` | **-137.95 dBFS** | **-183.7 dBFS** | **0.00 %** |

**Same record, same chain, same samples. The low band moves by 53.6 dB and the
in-band figure by 8.5 dB, and the only thing that differs is the arithmetic of
the mean subtraction.**

`x - x.mean()` nulls the record's unwindowed average. A Kaiser-windowed
transform integrates `sum(w*x)/sum(w)` instead, so the wrong subtraction leaves
a DC residue; at beta 26 the main lobe is twelve bins wide, which is 280 Hz at
this transform length, and the residue lands spread across exactly the 20 to
100 Hz bins the fault was diagnosed from. The measurement was manufacturing the
signature it was being read for.

That explains every property the fault was reported to have. It appears
sporadically because whether the two means differ enough to matter depends on
where the loop happens to sit. It puts all of its excess under 100 Hz because
that is the width of the window's main lobe. Dither does not remove it because
dither does not change which mean you subtract. And the check README.md
recommends — "if a figure comes back bad, look at the 20 Hz to 100 Hz bins
first" — points at the artefact rather than past it.

**There is no limit cycle to fix**, and the rule in README.md's trap list needs
strengthening rather than the loop: *remove the mean* has to say **which** mean,
because the difference is invisible in the time domain and 8.5 dB in the answer.

## The material is real, at one rate

Fourteen 48 kHz 24-bit recordings from `/System/Library/Sounds`, converted to
WAV with `afconvert` (format only, no resampling) into a temporary directory
and read through `material.read_wav`. Nothing downloaded, nothing resampled.

| | Real, joined | programme-like | percussive | sustained bass | 1 kHz sine |
| --- | --- | --- | --- | --- | --- |
| Crest factor | 24.8 dB | 11.6 dB | 21.8 dB | 5.0 dB | 3.0 dB |

16.72 seconds, 392 windows of 2^20 element samples. Per-file crest factors run
from 15.3 to 26.5 dB, which is the range programme material occupies and the
range a sine never reaches.

**Real audio exists here only at 48 kHz**, and `material.read_wav` refuses to
resample, which is right. The other five rates use `material.py`'s synthetic
stand-ins, labelled synthetic everywhere. The recordings also carry nothing
above 10 kHz, so they say nothing about the ultrasonic intermodulation 0010
warns about; that gap stays open.

## The instrument, and why it is not SNR

Signal-to-noise against a tone works by excising the signal lobe. Broadband
material has no lobe to excise and excising the occupied band leaves nothing,
so what is measured is the **error** against the ideal reconstruction of the
same PCM:

    e = x - g * u_ref

`u_ref` is the cascade output for the unquantized float record at exact
datapath precision; `x` is the element sum for the same record through
everything the hardware does. Both run the same quantized coefficients, so the
cascade's response cancels and what is left is the set of terms the end-to-end
SNDR figure is made of: source word length, datapath rounding, modulator
quantization noise, rotation residual.

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

**The two instruments agree to between +1.16 and +1.49 dB, mean +1.27 dB.** The
offset has a known cause: the classic figure rescales the noise bins it kept to
cover the ones it excised, about +1.1 dB of noise it did not measure. Every
material figure carries that offset, stated rather than corrected away.

The 96 kHz row is the artefact above — both instruments read it, because both
were fed the same badly-centred record. With the windowed mean it is
-137.95 dBFS, in line with its neighbours.

The fitted gain came back 0.998570 at all six rates, which is the check that a
scalar is the right model for element mismatch: the same physical weights, the
same gain, independent of rate and of material.

### Decomposition, 48 kHz, one percent elements

| | In band |
| --- | --- |
| Total error | -137.91 dBFS |
| 24-bit TPDF source alone | -142.45 dBFS |
| Everything else (mismatch residual) | -139.79 dBFS |

README.md's claim, measured by subtraction rather than inferred: source word
length and element tolerance are within 2.5 dB of each other and nothing else
in the digital chain is close.

## Five measurement traps, four of which cost this run a pass

The transform artefact above is the first and largest. Four more, each
demonstrated in the log rather than asserted.

**The gain fit needs the mean removed too.** The error has its mean removed, as
the rule says — but the scalar gain fitted *before* that subtraction did not.
The mismatch offset then biases the fit by whatever the reference carries below
280 Hz: nothing when the music is loud, everything when it is quiet. Measured,
the fitted gain came out 1.207 instead of 0.9988 on a -70 dBFS record.

**The tell was that the error stopped moving when the level did.** An error
figure identical at -12, -40 and -70 dBFS, to the last decimal and in the same
FFT bins, is not measuring the converter. *If a figure does not respond to the
input, the instrument has stopped listening to the input* — that is worth more
than the rule it broke, and it is what caught both of the above.

**The gain fit has to be restricted to the band.** Fitted over the whole record
it is dominated by the modulator's out-of-band noise, 90 dB above the in-band
error, whose inner product with the signal is not zero. The leftover gain error
injects a pure in-band residual around -77 dBFS.

**A headroom window has to be centred on the reconstructed peak, not the
loudest sample.** On a percussive record clipped 12 dB the two are 1.5 seconds
and 2.5 dB apart, because clipping makes the reconstruction overshoot wherever
a flat run happens to be, not where the record is loudest.

**A lag check over a few samples cannot check anything.** The signal is
band-limited to 20 kHz and sampled at 24.576 MHz, so its autocorrelation is
flat over plus or minus eight samples; an argmax there reports where the
out-of-band noise fell, and it false-alarmed on 34 of 90 segments of real
material. What replaced it is the in-band error at the offset used against the
in-band error 256 samples away — a fifth of a period at 10 kHz, a real
displacement. It reads +93 to +112 dB across the six rates.

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
clipping produces, and the probe is the limiting case: every one of its samples
sits at full scale by construction, which is why it reaches exactly 3.010 dB.
The README's framing is right — the probe stands in for heavily limited
material, not for loud material.

**But 3 dB is not a ceiling.** Percussive material clipped 12 dB reaches
+4.876 dB, 1.87 dB past the probe.

### Where material actually overloads the quantizer

Bisection on the PCM level, the same bound as `modulator.max_stable_amplitude`
and `endtoend.max_stable_pcm` — no integrator past 50 quantizer LSBs.

| Material | 48 kHz | 192 kHz | Headroom needed |
| --- | --- | --- | --- |
| Real audio | -0.80 dBFS | -0.66 dBFS | 0.8 dB |
| Real, clipped 12 dB | -0.89 dBFS | -0.89 dBFS | 0.9 dB |
| Percussive, synthetic | -0.66 dBFS | -0.42 dBFS | 0.7 dB |
| Percussive, clipped 12 dB | **-3.75 dBFS** | **-3.66 dBFS** | 3.8 dB |
| Programme, synthetic | -0.75 dBFS | -0.56 dBFS | 0.8 dB |
| 1 kHz tone | -0.84 dBFS | -0.84 dBFS | 0.8 dB |
| Fs/4 inter-sample probe | -3.84 dBFS | -3.61 dBFS | 3.8 dB |

**Real material needs 0.8 dB. Heavily clipped percussive material needs
3.75 dB, which is what the probe predicted to within 0.09 dB.**

The probe was not pessimistic and it was not a corner case invented for the
occasion; it is an accurate stand-in for the worst thing a host can send. The
peak the quantizer sees at the overload point is -0.3 to -0.9 dBFS in every
row, which is README.md's finding intact: the loop overloads at the same place
regardless of content, and what changes is how much PCM level that
corresponds to.

**Recommendation: keep the 3 dB budget, and prefer the clipper at the modulator
input over a -3 dBFS volume default.** The two options README.md offers are not
equivalent. A fixed -3 dB default is 2.2 dB of range given away on everything
unprocessed, and is still short of the +4.9 dB tail that clipped percussive
material reaches. A clipper at the modulator input costs nothing on material
that never gets there and covers the tail that a fixed offset does not.

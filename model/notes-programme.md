# The chain against programme material

Measured by `run_programme.py`, log in `results/programme.txt`, figures
`figures/programme*.png`. README.md closes with "Only tones have been run".
This runs material with a real crest factor, window by window over a long
record, against the claims that rested on tones: the 132.8 dB worst case, the
3 dB headroom budget, the low-frequency limit cycle, and the habit of
reporting one in-band number per record.

One claim survives intact, two survive with their numbers changed, and one
turns out not to describe anything real. Comparisons are against the current
`results/endtoend.txt`, which still reports 132.8 dB worst case at one percent
elements after its own re-run.

## Summary

| Claim under test | Verdict |
| --- | --- |
| 132.8 dB worst case, one percent elements | **Holds on the median, not on the worst window.** Real material: median -132.3 dBFS, worst -115.2 dBFS over 360 windows. |
| Budget 3 dB of headroom | **Right in kind, 2.4 dB short in size.** No music asks for it: real audio needs 0.66-0.80 dB, the same as a sine. Clipped percussive material needs 5.39 dB against the probe's 3.84 dB. |
| Low-frequency limit cycle, one run in 36 | **Does not exist.** It is the mean subtraction, 8.5 dB of it. |
| The floor's shape window to window | **Stable and high-band dominated.** The 20-100 Hz band is under 0.82 percent of in-band error power at the 90th percentile, and never louder than -156.7 dBFS, across 776 windows. |
| Bass against a low-frequency fault | **Separable, for free.** A monitor on `u - v` inside the loop is blind to programme content by construction; one on the output is not. |
| *(this thread's own claim)* mid-band distortion provoked by broadband content | **Does not exist.** It was the gain fit on un-centred signals. What survives is 4.1 dB: a tone understates the cost of one percent elements by that much. |

## The four tone-based claims, against real material

This was the point of the exercise, so it is stated plainly.

### 1. "132.8 dB is the worst case over every rate with one percent elements"

**Survives as a median. Does not survive as a worst case.**

Against 16.7 seconds of real 48 kHz material at one percent elements, measured
in 42.7 ms windows: median -132.3 dBFS, which restated in the README's
convention is 128.6 dB; worst window -115.2 dBFS, which is 111.5 dB. The tone
that produced 132.8 dB varies by 1.1 dB window to window. Real material varies
by 27.7 dB.

The claim is not wrong about what it measured. It is wrong as a description of
the chain's behaviour over a record, and the gap is 17 dB. The number to hold
the hardware to is still 132.8 dB for the average case; **the number that
bounds it is 111.5 dB**, 1.5 dB above the 110 dB target of 0012 rather than
22.8 dB above it.

The whole of that spread is element mismatch. The same record with matched
elements spans 1.1 dB and sits on the 24-bit source floor at -142 dBFS.

### 2. "Budget 3 dB of headroom"

**The reasoning survives. The number does not: the worst case measured is
5.39 dB.**

The inter-sample probe is the right kind of stand-in — it is the only signal in
the model that produces an inter-sample over at all, and clipping is the only
thing in real material that does. Unprocessed material of any crest factor
needs 0.8 dB and overshoots by 0.000 dB; sixteen seconds of real recording
normalised to full scale hands the quantizer exactly 1.0000.

But the probe's overshoot is pinned at 3.01 dB by construction, and clipped
percussive material reaches 4.88 dB. Measured end to end, that material needs
**5.39 dB** of headroom against the probe's 3.84 dB. **Budget 3 dB and heavily
limited material overloads the loop.**

Of the two implementations README.md offers, **the clipper at the modulator
input is the right one and a -3 dBFS volume default is not.** The default gives
away 2.2 dB on everything unprocessed and is still 2.4 dB short of the worst
case.

### 3. "A low-frequency limit cycle trips one run in thirty-six"

**Does not survive. It is not a property of the loop and there is nothing to
fix.**

It is `x - x.mean()` where a Kaiser-windowed transform needs
`x - sum(w*x)/sum(w)`. Reproduced on demand at 96 kHz and then removed by
changing only the arithmetic of the mean subtraction: the in-band figure moves
8.5 dB and the 20-100 Hz band moves 53.6 dB. Across 776 windows of material
measured correctly, **no window puts as much as one percent of its in-band
error below 100 Hz**, against the 40 to 95 percent the artefact produced.

This also disposes of the same figure's consequences: the 15.7 dB attributed to
round-half-up rounding is the same artefact, established independently in
`notes-idle.md`.

### 4. "Only tones have been run" — the in-band figure as a single number

**Does not survive, and this is the durable one.**

A single in-band figure per record is an adequate description of the chain
against a tone, where the window-to-window spread is 1.1 dB. It is not an
adequate description against material, where the spread is 27.7 dB and the
worst window is 17 dB below the median. Nothing in the tone measurement is
wrong; it simply does not have a tail to report, and the chain does.

**Report the distribution.** `figures/programme_windows.png` is what that looks
like.

### And one claim of this thread's own, which also did not survive

An earlier pass here reported that broadband material provoked mid-band
distortion that a tone did not, up to 37 dB of it. That was the gain fit taken
on un-centred signals. What is left after three checks — level dependence, a
level-matched tone, and a transform twice as long — is that **one percent
elements cost 4.8 dB against a single sine and 8.9 dB against two tones, so a
tone understates element cost by 4.1 dB.** Real and small.

Three findings in this thread began as large effects and ended as measurement
artefacts: this one, the limit cycle, and the 8.5 dB at 96 kHz. All three were
DC in the lowest bins, arriving by three different routes. That is the pattern
worth carrying forward more than any individual number.

**Since there is no mid-band term, the question of its origin does not arise.**
Stating it explicitly because the hardware thread has since found a candidate
mechanism — element filter capacitors drawing a change-dependent current, with
a possible signal-correlated modulation of the reference rail around -90 dB.
This model contains no supply, no reference rail and no capacitor current, so
it could not have produced that effect and did not. What it produced was a
gain fit taken on un-centred signals. **Everything measured here is digital in
origin, and the reference-rail mechanism remains untested by anything in
`model/`.**

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

## Q2: no music asks for the 3 dB budget, and clipped material asks for more

### Nothing but clipping makes an inter-sample over

Peak the cascade presents to the quantizer against the peak in the samples.
Records faded at both ends and scanned in blocks.

| Material | Crest | Samples at FS | True peak | Overshoot | Peaks apart |
| --- | --- | --- | --- | --- | --- |
| Real audio, 16.7 s | 24.81 dB | 1 | 1.0000 | **+0.000 dB** | 1.5 ms |
| Real, clipped 3 dB | 21.86 dB | 190 | 1.0029 | +0.025 dB | 4.3 ms |
| Real, clipped 6 dB | 19.06 dB | 998 | 1.0083 | +0.072 dB | 7.2 ms |
| Real, clipped 12 dB | 14.45 dB | 10343 | 1.0781 | +0.653 dB | 5887 ms |
| Percussive, synthetic | 21.81 dB | 1 | 1.0033 | +0.029 dB | 1.5 ms |
| Percussive, clipped 6 dB | 16.09 dB | 542 | 1.3139 | +2.371 dB | 1958 ms |
| Percussive, clipped 12 dB | 12.13 dB | 3915 | 1.7532 | **+4.876 dB** | 1515 ms |
| Programme, clipped 12 dB | 3.98 dB | 35345 | 1.0399 | +0.340 dB | — |
| 1 kHz tone | 3.01 dB | 5461 | 1.0000 | +0.000 dB | — |
| Fs/4 inter-sample probe | 0.00 dB | 131072 | 1.4142 | +3.010 dB | — |

"Peaks apart" is the distance between the loudest sample and the loudest
reconstructed peak. For unprocessed material they are the same event, 1.5 ms
apart, which is the cascade's group delay. For clipped material they are
seconds apart, because clipping makes the reconstruction overshoot wherever a
flat run happens to sit rather than where the record is loudest. **A headroom
measurement windowed on the loudest sample therefore measures the wrong
moment**, and that is the fourth trap in the list above.

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
| Real, clipped 12 dB | -1.22 dBFS | -1.17 dBFS | 1.2 dB |
| Percussive, synthetic | -0.61 dBFS | -0.38 dBFS | 0.6 dB |
| **Percussive, clipped 12 dB** | **-5.39 dBFS** | **-4.78 dBFS** | **5.4 dB** |
| Programme, synthetic | -0.66 dBFS | -0.61 dBFS | 0.7 dB |
| 1 kHz tone | -0.84 dBFS | -0.84 dBFS | 0.8 dB |
| Fs/4 inter-sample probe | -3.84 dBFS | -3.61 dBFS | 3.8 dB |

**Real material needs 0.66 to 0.80 dB. Heavily clipped percussive material
needs 5.39 dB, which is 1.55 dB more than the probe predicts.**

**So the 3 dB budget is set by the inter-sample probe and not by music.** That
is worth saying outright, because it is the difference between a budget with an
arbitrary value and one with a named cause. Nothing in 16.7 seconds of real
recording, at any crest factor from 15 to 26 dB, asks for more than 0.8 dB —
the same 0.84 dB a 1 kHz sine asks for. The entire budget exists to survive one
specific thing a host can send, which is material that has been clipped, and
the right way to size it is therefore to ask how hard the worst plausible
limiting is, not how loud the music is.

**This is the one place a standing recommendation is wrong, and the number that
shows it is 5.39 against 3.84.** The 3 dB budget is not conservative for
heavily limited material; it is 2.4 dB short of the worst case measured here.
The probe is still the right *kind* of stand-in — it is the only synthetic
signal in the model that produces an inter-sample over at all — but it
understates the magnitude, because its overshoot is fixed at 3.01 dB by
construction while clipped percussive material reaches 4.88 dB.

The earlier version of this measurement agreed with the probe to 0.09 dB and
was wrong. It centred the analysis window on the loudest *sample*; the loudest
reconstructed peak is 1.5 seconds away in that record, so the bisection never
saw it and reported 3.75 dB. Centring on the reconstructed peak gives 5.39 dB.

The peak the quantizer sees at the overload point is -0.83 to +0.10 dBFS in
every row, which is README.md's finding intact: the loop overloads at the same
place regardless of content, and what changes is how much PCM level that
corresponds to.

### The approach to the cliff is gradual, and the FPGA can see it coming

Stability is a cliff, but the run-up to it is not. `rail` is the fraction of
samples sitting on the top or bottom quantizer code — a counter, one comparator
wide, that the FPGA gets for free:

| PCM level | Real audio | Real, clipped 12 dB | Percussive, clipped 12 dB |
| --- | --- | --- | --- |
| -12 dBFS | 0.0000 | 0.0000 | 0.0000 |
| -6 dBFS | 0.0000 | 0.0000 | 0.0002 |
| -4.5 dBFS | 0.0000 | 0.0001 | **unbounded** |
| -3 dBFS | 0.0016 | 0.0052 | — |
| -2 dBFS | 0.0056 | 0.0163 | — |
| -1 dBFS | 0.0164 | **unbounded** | — |
| 0 dBFS | **unbounded** | — | — |

**The rail fraction rises about three-fold per dB for several dB before the
loop lets go**, so a threshold anywhere in the 1e-4 to 1e-2 range gives warning
with margin in hand. The in-band error meanwhile stays flat at -135 to -137 dBFS
right up to the edge: performance does not degrade gracefully into the overload,
it is fine and then it is gone. **That makes the rail counter the more useful
half of this question than the maximum stable amplitude is** — the MSA is a
number for a datasheet, the rail count is something the hardware can act on.

The one caveat is the last row. Percussive material clipped 12 dB goes from
`rail = 0.0002` to unbounded in 1.5 dB, so the warning is shortest exactly where
it is most needed. A counter alone is not a guarantee; it is a cheap
early indication that pairs with the clipper, not a replacement for it.

**Recommendation: use the clipper at the modulator input, not a fixed volume
default.** README.md offers the two as alternatives; they are not equivalent.
A fixed -3 dBFS default gives away 2.2 dB of range on everything unprocessed
*and* leaves clipped percussive material 2.4 dB short. A clipper at the
modulator input costs nothing on material that never reaches it and covers a
tail whose size depends on how hard the host's material was limited — which is
not a number this design can bound in advance.

## Q3: bass and a low-frequency anomaly are separable, and the detector is free

The question was posed against the limit cycle. That fault does not exist, so
what is left is the general version, and it is still the one the hardware has
to answer: if anything ever does put energy between 20 and 100 Hz that is not
music, can a monitor tell, given that music puts energy there too?

Three detectors, all measuring 20-100 Hz power, against sustained 41 Hz bass
at -6 dBFS, a 1 kHz tone, and near-silence, each run four ways that differ only
in things that cannot change the audio:

| Detector | Bass | 1 kHz tone | Near silence | Spread from music alone |
| --- | --- | --- | --- | --- |
| Output (element sum) | -6.7 to -14.8 | -170 to -184 | -133 to -146 | **177 dB** |
| Error vs ideal reconstruction | -171 to -187 | -170 to -185 | -168 to -182 | 19 dB |
| **Loop error, v - u** | **-303 to -317** | **-329 to -345** | **-314 to -325** | **42 dB** |

Two incidental confirmations fall out of those four variations. Round-half-up
and round-half-even measure identically on every row — bass at 48 kHz reads
-135.4 and -135.6 dBFS, within the run-to-run spread — which is the same
conclusion `notes-idle.md` reaches from the other direction: the 15.7 dB
attributed to the rounding rule was the same mean-subtraction artefact. And no
variation trips anything, which is what "there is no limit cycle" looks like
when you go looking for one on purpose.

**A monitor on the output cannot work.** It reads -6.7 dBFS on bass and
-179.5 dBFS on a 1 kHz tone: 173 dB of swing caused by nothing but what the
music happens to contain. Any threshold that flags a low-frequency anomaly
flags every bass note.

**The loop error is blind to the music, and the FPGA already has it.** The STF
of this topology is exactly 1 with zero delay, so `v - u` — the modulator's
output code minus its own input — cancels the programme exactly and leaves the
shaped quantization error. It is the `d` the integrators are already driven by,
so it costs no arithmetic to observe. On 41 Hz bass at -6 dBFS it reads
-303 dBFS, which is the model's numerical floor rather than a measurement: the
loop puts essentially nothing below 100 Hz, whatever the music is doing there.

Two limits on that, both real:

* **It stops at the codes.** Element mismatch happens after it, so `v - u`
  cannot see an element fault. It is a loop monitor, not a converter monitor.
  The thing Q1 found — the rotation residual rising 12 dB in quiet passages —
  is invisible to it.
* **-303 dBFS is float64, not silicon.** In hardware the floor would be set by
  the width of the subtraction and of whatever accumulates it. The useful
  statement is not the number but the structure: because the STF is exactly
  unity, the music cancels by construction rather than by filtering, so the
  detector's floor is set by arithmetic and not by how loud the bass is.

**Recommendation: if a low-frequency health monitor is ever wanted, put it on
`u - v` inside the loop, not on the output.** It is free, it is immune to
programme content by construction, and it is the only one of the three that a
converter can actually compute about itself.

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

**In nine cases out of ten the 20-100 Hz band carries under half a percent of
the in-band error, which is what a white floor would give, and the loudest low
band anywhere in 776 windows is -156.7 dBFS.** The error is high-band dominated
in every window — 2-20 kHz carries essentially all of it — which is the
rotation residual being shaped up out of the band exactly as 0008 claims.

A handful of real-audio windows show shares above one percent (the outliers in
`figures/programme_shape.png`). They are not a low-frequency fault: they are
windows whose *total* error is near the -142 dBFS source floor, so the same
absolute low-band power is a larger fraction of a smaller total. The share is
the right statistic for spotting a concentration and the wrong one for sizing
it, which is why the absolute low band is tabulated beside it.

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

## The mid-band distortion does not exist either

**Verdict: it was a measurement artefact.** This section records the check
rather than the claim, because the claim was mine and it was wrong.

An earlier pass of this script reported that broadband material provoked
mid-band error that tracked the signal level and reached 40 dB worse than the
same chain on a tone — element mismatch apparently costing 0.5 dB against a
sine and 37 dB against real audio. It would have been the most consequential
thing here, because every figure in README.md comes from a tone and would have
missed it.

It was the scalar gain fit being taken on un-centred signals, which is the
second trap in the list below. Three independent checks kill it: the error's
dependence on level, a level-matched tone in the same band, and a transform
twice as long. All three are below.

**The error does not track the signal.** Real audio at one percent elements,
the same record at falling level, corrected instrument:

| PCM level | In-band signal | In-band error | 100 Hz-2 kHz | 2-20 kHz |
| --- | --- | --- | --- | --- |
| -12 dBFS | -15.8 | -135.0 | -151.7 | -135.0 |
| -40 dBFS | -43.8 | -123.5 | -151.1 | -123.5 |
| -70 dBFS | -73.8 | -123.2 | -140.2 | -123.3 |

The error moves with level in the wrong direction for distortion — it gets
*worse* as the signal shrinks, which is the rotation residual of Q1 — and it
is 2-20 kHz in every row, 12 to 28 dB above the mid band. Under the broken fit
the same rows read -88.4 dBFS at every level with the excess in the mid band.

**A tone at the same level in the same band shows the same thing.** Sources
matched on in-band signal power at -16 dBFS, 48 kHz:

| Source | Matched | 1% | Cost | 1%: 20-100 Hz | 100 Hz-2 kHz | 2-20 kHz |
| --- | --- | --- | --- | --- | --- | --- |
| 1 kHz sine | -142.5 | -137.6 | 4.8 dB | -167.4 | -151.7 | -137.8 |
| Two tones, 1.0 + 1.1 kHz | -142.4 | -133.5 | **8.9 dB** | -167.1 | -150.6 | -133.6 |
| 8-tone multitone | -142.2 | -135.6 | 6.6 dB | -174.6 | -150.2 | -135.7 |
| White noise to 20 kHz | -142.7 | -135.9 | 6.8 dB | -173.8 | -153.9 | -136.0 |
| Sustained 41 Hz bass | -142.2 | -137.6 | 4.6 dB | -181.9 | -151.8 | -137.7 |
| Programme, synthetic | -142.0 | -135.5 | 6.5 dB | -171.9 | -149.4 | -135.7 |
| Real audio | -142.4 | -137.2 | 5.2 dB | -169.1 | -152.0 | -137.3 |

Matched elements give -142.0 to -142.7 for every source — the 24-bit floor,
content-independent, as it must be. The error is 2-20 kHz on every row, 14 dB
or more above the mid band and 30 dB or more above 20-100 Hz, so rotation is
shaping mismatch out of the band against broadband content exactly as it does
against a tone.

**Checked at a longer transform**, which halves the bin width and so halves how
far any leftover DC could reach:

| Source | 2^20 matched | 2^20 at 1% | 2^21 matched | 2^21 at 1% | 2^21 mid band |
| --- | --- | --- | --- | --- | --- |
| 1 kHz sine | -142.5 | -137.6 | -142.4 | -137.2 | -153.1 |
| White noise | -142.7 | -135.9 | -141.9 | -135.5 | -152.6 |
| Real audio | -142.4 | -137.2 | -142.1 | -135.9 | -151.9 |

Nothing moves by more than 1.3 dB and the mid band stays where it was. The
result is a property of the chain, not of the window.

**What survives is small and still worth having: a tone understates the cost of
one percent elements by 4.1 dB.** A sine pays 4.8 dB, the worst
multi-component source pays 8.9 dB, and the whole spread across every source
measured is 4.3 dB. That is real — two tones show it on the
old instrument too, with both fundamentals excised, at -142.5 dBFS matched
against -136.3 dBFS at one percent — and it is the expected consequence of
what a tone measurement does: with one tone the mismatch error can only land
on the fundamental, which is excised as signal, or its harmonics, which are
excised as distortion. Add a second tone and the same error lands on
intermodulation products that neither excision removes.

It is 4.1 dB, not 37, and it does not change any recommendation.

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

| Rate | Classic SNR | Classic SNDR | Error instrument | Error, dBFS | Alignment margin |
| --- | --- | --- | --- | --- | --- |
| 48 kHz | 133.49 | 132.94 | 134.21 | -137.91 | +110.8 dB |
| 96 kHz | 133.40 | 132.94 | 134.25 | -137.95 | +110.2 dB |
| 192 kHz | 134.07 | 133.74 | 135.11 | -138.81 | +111.0 dB |
| 44.1 kHz | 132.96 | 132.49 | 133.65 | -137.35 | +111.7 dB |
| 88.2 kHz | 134.06 | 133.53 | 134.69 | -138.39 | +112.2 dB |
| 176.4 kHz | 134.12 | 133.69 | 134.88 | -138.58 | +112.7 dB |

**The two instruments agree to between +1.16 and +1.37 dB, mean +1.24 dB.** The
offset has a known cause: the classic figure rescales the noise bins it kept to
cover the ones it excised, about +1.1 dB of noise it did not measure. Every
material figure carries that offset, stated rather than corrected away.

Both columns are now measured with `spectra.remove_dc`, which `Measurement.of`
applies to every measurement. Before that landed, this table's 96 kHz row read
124.29 / 124.23 / 125.72 on both instruments — the artefact described below,
which both instruments reported faithfully because both were handed the same
badly-centred record. Two instruments agreeing is not evidence that either is
right when they share an input.

The fitted gain came back 0.998570 at all six rates, which is the check that a
scalar is the right model for element mismatch: the same physical weights, the
same gain, independent of rate and of material. The alignment margin is how
much worse the in-band error gets when the two paths are slid 256 samples
apart; at +110 dB or better everywhere, the settling offset is not in question.

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

## What this did not test

* **Nothing above 10 kHz.** The real recordings available on this machine are
  band-limited well under the audio band's top, so 0010's warning about
  high-level ultrasonic content eating modulator headroom is still untested
  against anything but the passband-edge tones already in README.md.
* **Real material at one rate only.** 48 kHz. The other five rates are
  measured with `material.py`'s synthetic stand-ins, which have the right
  spectral shape and the wrong crest factor.
* **One board.** Every figure except the element-draw table uses one mismatch
  seed. That table spans several dB across five draws of the same one percent
  specification, so a single seed is a sample, not a bound.

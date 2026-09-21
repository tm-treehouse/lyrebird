# model

A numerical model of the audio chain, built to answer the questions the
repository left open with numbers rather than adjectives. Run it:

```
./.venv/bin/python model/run_experiments.py   # order, cascade, coefficients, rotation
./.venv/bin/python model/run_endtoend.py      # the chain connected, and datapath width
./.venv/bin/python model/run_idle.py          # idle channel, and what the window was doing
./.venv/bin/python model/run_programme.py     # real programme material, window by window
```

Figures land in `figures/`, the logs in `results/measurements.txt`,
`results/endtoend.txt`, `results/idle.txt` and `results/programme.txt`.

**If you read an earlier version of this file, four of its claims were wrong.**
Two were measurement errors: the low-frequency limit cycle it reported does not
exist, and the 15.7 dB it attributed to round-half-up was the same error. Two
were correct measurements stated with the wrong scope: **132.8 dB is a tone's
figure and a median window's figure, not a worst case** -- real material's
worst window is 111.5 dB -- and **3 dB of headroom does not cover the case the
headroom budget exists for**, which is clipped material, at 5.39 dB. All four
are corrected below, with what actually caused them.

Real material also turned up one thing nothing predicted: **the error is worst
where the signal is quietest.** See "The error is worst where the signal is
quietest" below.

## Recommendations

### Modulator order: 3

| Order | Max stable amplitude | SNDR, 20 Hz to 20 kHz |
| --- | --- | --- |
| 2 | 0.996 | 126.3 dB |
| 3 | 0.918 | 168.1 dB |
| 4 | 0.855 | 204.2 dB |
| 5 | 0.818 | 215.3 dB |

Order 2 already clears the 110 dB target by 16 dB, so the honest statement is
that every order works and [0008](../docs/decisions/0008-multibit-delta-sigma-with-dwa.md)
was right that the modulator is not where performance is decided.

Take order 3 anyway. It costs one integrator and buys 42 dB, which covers the
idealisations this model does not include: coefficient quantisation, finite
integrator gain, and clock jitter. The real cost is stability, not logic.
Maximum stable amplitude falls from 0.996 to 0.918, so roughly 0.7 dB of
output range is given up. Going beyond order 3 spends more range for margin
that is already far past what the analog section will deliver.

### Interpolation cascade: nine stages, 163 taps in the first

Designed for a 120 dB stopband, then measured after design.

| Stage | In | Out | Taps | Non-zero | Stopband |
| --- | --- | --- | --- | --- | --- |
| 1 | 48 kHz | 96 kHz | 163 | 83 | -122.1 dB |
| 4 | 384 kHz | 768 kHz | 27 | 15 | -133.6 dB |
| 5 | 768 kHz | 1.536 MHz | 15 | 9 | -130.3 dB |
| 6 | 1.536 MHz | 3.072 MHz | 11 | 7 | -135.6 dB |
| 7 | 3.072 MHz | 6.144 MHz | 11 | 7 | -168.9 dB |
| 8 | 6.144 MHz | 12.288 MHz | 7 | 5 | -140.7 dB |
| 9 | 12.288 MHz | 24.576 MHz | 7 | 5 | -163.6 dB |

Stages 2 and 3 reuse the stage-1 design at their own rates, which is why only
seven distinct filters appear. The cost that matters for the FPGA:

| | 48 kHz | 192 kHz |
| --- | --- | --- |
| Multipliers at the element clock | 2.86 | 2.62 |
| Coefficient words | 62 | 62 |
| Delay words | 567 | 241 |
| Group delay | 1501 us | 235 us |
| Passband ripple, peak to peak | 34.9 micro-dB | 15.0 micro-dB |
| Worst image | -122.1 dB | -122.1 dB |

Under three multipliers at the element clock is the number to design against.
The delay line storage is small next to the elastic buffer.

**The group delay at 48 kHz is 1.5 ms and is not free.** It adds to the
prefill latency rather than hiding inside it.

### Coefficient word width: 26 bits worst case, 8 bits for the fast stages

Float is not buildable on an FPGA, so every filter is specified as a fixed
signed fraction. The criterion is the 120 dB design target rather than the
double-precision result, because several stages land far past the target in
float and holding them there would buy stopband nobody asked for at the price
of wider words.

| Stage | Rate in | Min bits | Stopband achieved | CSD adders |
| --- | --- | --- | --- | --- |
| 1 | 48 kHz | 26 | -120.1 dB | 249 |
| 4 | 384 kHz | 22 | -120.4 dB | 41 |
| 5 | 768 kHz | 19 | -120.2 dB | 18 |
| 6 | 1.536 MHz | 18 | -123.0 dB | 17 |
| 7 | 3.072 MHz | 10 | -142.2 dB | 9 |
| 8 | 6.144 MHz | 8 | -122.7 dB | 3 |
| 9 | 12.288 MHz | 8 | -146.8 dB | 3 |

The shape is the useful part and it favours the hardware. The stages needing
wide coefficients run slowly, so they can be time-shared. The stages running at
the element clock need only eight bits and three adders each, so they can be
built as shifts and adds with no multiplier at all.

Worst case is 26 bits. The 340 adder total is dominated by stage 1's 249, and
stage 1 runs at the base sample rate, so it does not need 249 physical adders.

**Both rate families share one coefficient set.** The passband edge is
normalised so 20 kHz falls at the same fraction of the lower family's rate,
which means the 44.1 and 48 kHz families use identical filters and only the
oscillator changes. That halves the coefficient storage.

### Rotation: plain data weighted averaging is enough

Measured over 2^21 samples, with the DC offset removed. Element
mismatch produces a static output offset that real hardware trims or couples
away, and the lowest FFT bins otherwise fall inside a band starting at 20 Hz,
which would count that offset as audio-band noise.

| Element mismatch | Rotation | SNDR | THD |
| --- | --- | --- | --- |
| none | on | 126.9 dB | -144.4 dB |
| 0.1% | on | 126.9 dB | -144.3 dB |
| 0.1% | off | 77.1 dB | -77.1 dB |
| 1% | on | 126.4 dB | -142.5 dB |
| 1% | off | 57.1 dB | -57.1 dB |

Without rotation the output is distortion-limited: SNDR and THD track each
other exactly, which is the signature of mismatch appearing as harmonics rather
than as noise. Element loading was verified constant at seven across every
code, which is the invariant the differential drive exists to provide.

#### Correction: that table is at order 2, and 0.5 dB was the wrong reading

`run_experiments.py` selects the lowest order meeting the 110 dB target, which
is 2, and measures rotation there. At order 2 the modulator's own floor is
126.3 dB, which sits *above* the rotation residual and hides it. Re-measured at
order 3, with the source quantizer removed so nothing else masks it either:

| Element mismatch | Rotation | SNDR, order 2 | SNDR, order 3 |
| --- | --- | --- | --- |
| none | on | 126.9 dB | 167.9 dB |
| 0.1% | on | 126.9 dB | 154.5 dB |
| 0.1% | off | 77.1 dB | 77.1 dB |
| 1% | on | 126.4 dB | 134.7 dB |
| 1% | off | 57.1 dB | 57.1 dB |

**One percent mismatch costs 33.3 dB with rotation, not 0.5 dB.** The residual
is a real noise floor at 134.7 dB, and it only looked free because a noisier
modulator was sitting on top of it. The lower panel of
[endtoend_spectrum.png](figures/endtoend_spectrum.png) shows it directly: with
rotation on, the mismatch error is shaped, rising out of the audio band exactly
as 0008 claims; with rotation off it is a flat -125 dBFS floor plus a comb of
harmonics.

The recommendation is unchanged and the argument for it is stronger. Rotation
still buys 77.6 dB at one percent mismatch, it still clears the 110 dB target
by 24.7 dB, and it still confirms the claim in
[hardware/README.md](../hardware/README.md) that ordinary one percent parts are
adequate.

What changes is what sets the floor. **Above order 2 it is element matching,
not modulator order.** Going from order 2 to order 3 buys 8.3 dB at one percent
mismatch, not the 41.8 dB the order sweep promises. Tighter elements buy more
than a higher order does: 0.1 percent parts measure 154.5 dB.

## The chain end to end

`run_endtoend.py` connects the two halves that had only ever been measured
apart: real 24-bit PCM at Fs, through the cascade, into the modulator, through
the rotation and the differential elements, and out of the weighted sum. Order
3, a 1 kHz tone at -3.7 dBFS, which is 3 dB below the order-3 maximum stable
amplitude, 2^20 samples at the element clock, matched elements.

| Rate | SNR | SNDR | THD | Source floor in band |
| --- | --- | --- | --- | --- |
| 48 kHz | 138.5 dB | 137.6 dB | -144.9 dB | -142.2 dBFS |
| 96 kHz | 141.4 dB | 140.3 dB | -146.8 dB | -145.1 dBFS |
| 192 kHz | 144.8 dB | 143.8 dB | -150.5 dB | -148.6 dBFS |
| 44.1 kHz | 138.4 dB | 137.6 dB | -145.0 dB | -142.1 dBFS |
| 88.2 kHz | 141.1 dB | 140.2 dB | -147.4 dB | -144.8 dBFS |
| 176.4 kHz | 144.3 dB | 143.4 dB | -150.5 dB | -148.0 dBFS |

**Every rate clears the 110 dB target by at least 27.6 dB.** The quantizer
never clipped and the loop never left its bound at any rate.

### The chain as it will actually be built

The table above has perfect elements. With everything at once -- 24-bit TPDF
PCM, coefficients at their settled widths, the datapath at the widths
recommended below, order 3, rotation on, and elements with real tolerance:

SNDR, 20 Hz to 20 kHz:

| Rate | Matched | 0.1% elements | 1% elements |
| --- | --- | --- | --- |
| 48 kHz | 137.5 dB | 137.4 dB | 132.9 dB |
| 96 kHz | 140.2 dB | 140.1 dB | 133.7 dB |
| 192 kHz | 143.8 dB | 143.5 dB | 134.0 dB |
| 44.1 kHz | 137.6 dB | 137.5 dB | 132.8 dB |
| 88.2 kHz | 140.2 dB | 140.0 dB | 132.8 dB |
| 176.4 kHz | 143.3 dB | 143.0 dB | 133.3 dB |

**132.8 dB is the worst case over every rate with one percent elements, for a
tone**, 22.8 dB above the 110 dB target of 0012.

**It is not a bound, and an earlier version of this section said it was.**
Measured against real programme material window by window -- `run_programme.py`,
`notes-programme.md` -- the same chain at the same widths gives a median of
128.6 dB and a worst window of **111.5 dB**, 1.5 dB above the target rather
than 22.8. A tone's figure varies by 1.1 dB from window to window; real
material's varies by 27.7 dB.

So the number keeps its meaning and loses its scope. 132.8 dB is what a tone
measures, and it is also what a typical window of music measures, which is why
it is still the right figure to quote for the design and to hold the hardware
to on a bench. What it does not do is bound the worst 42 ms of a record. The
distribution, not this number, is the description of the chain against music;
see [Q1 in notes-programme.md](notes-programme.md) and
[programme_windows.png](figures/programme_windows.png).

### The error is worst where the signal is quietest

This is the one result real material turned up that nothing in the tone
measurements predicted, and it is the wrong way round.

16.7 seconds of real 48 kHz recording, one percent elements, split by how much
in-band signal each 42.7 ms window carries:

| In-band signal in the window | Windows | Median error | Matched elements |
| --- | --- | --- | --- |
| Above -12 dBFS | 5 | -137.3 dBFS | -142.5 dBFS |
| -30 to -12 dBFS | 50 | -135.2 dBFS | -142.3 dBFS |
| **-60 to -30 dBFS** | **71** | **-125.2 dBFS** | **-142.3 dBFS** |
| Below -60 dBFS | 234 | -135.8 dBFS | -142.3 dBFS |

**Windows 30 to 60 dB down measure 12 dB worse than loud ones.** The
matched-element column is flat at -142.3 dBFS across every band, so there is
nothing else it can be: it is the rotation residual, and rotation works less
well where there is less to rotate. Data weighted averaging makes every element
carry every code equally often *over time*; with a small signal the code
sequence has a short range and the pointer traverses the ring less thoroughly
per unit time.

It is not a fault, it is not a limit cycle, and it does not threaten the 110 dB
target -- the worst single window of 360 still measures 111.5 dB. What makes it
worth stating in the README rather than leaving in the notes is that **quiet
passages are where a listener is most able to hear a converter's floor**, and
this chain's floor is at its worst exactly there. Any listening test that plays
loud material will miss it.

The lever is element tolerance, which README already identifies as the term
that sets performance. This says it also sets the worst case, and that the
worst case is not where a tone measurement would look for it.

Note which term dominates. With one percent elements the mismatch residual sits
close to the 24-bit source floor, so element tolerance and source word length
are within a few dB of each other and everything else in the digital chain --
modulator, cascade, coefficients, datapath -- is 25 dB or more below both. The
rate spread also collapses: matched elements span 6.3 dB across the rates,
one percent elements span 1.2 dB, because mismatch noise is shaped by the loop
and does not care what the sample rate was. That is 0008's "the digital side
has large headroom, the analog side sets performance", now with numbers.

### Yes, it differs from the subsystem numbers, by 30 dB

| | SNDR |
| --- | --- |
| Modulator alone, tone generated at the element clock | 168.1 dB |
| Same modulator behind the cascade, source quantizer removed | 167.9 dB |
| Same, fed real 24-bit TPDF-dithered PCM at 48 kHz | 137.6 dB |

The first two lines answer the question the gap was actually about: **the
cascade costs 0.2 dB, which is the measurement floor.** Its transition-band
behaviour reaches the modulator and does nothing to it. The modulator order
sweep, the cascade design and the coefficient widths all survive contact with
each other unchanged. The rotation *recommendation* survives too; the 0.5 dB
figure quoted for it does not, and is corrected above.

The third line is the one that matters. **The end-to-end figure is set by the
24-bit source, not by anything in the FPGA.** A 24-bit TPDF-dithered sample
stream carries a floor of -142.2 dBFS in a 20 Hz to 20 kHz band at 48 kHz, and
the modulator's own floor is 30 dB below that. The rate trend is the giveaway:
the source floor is white over Fs/2, so every doubling of the sample rate
spreads it over twice the bandwidth and buys about 3 dB in band. Nothing else
in the chain behaves that way.

Two consequences for the HDL:

* **Do not spend logic on modulator order beyond 3.** At order 2 the
  end-to-end figure is 126.8 dB against order 3's 137.6 dB, so order 3 earns
  its integrator. Order 4 would earn nothing: the order-3 modulator floor
  already sits 30 dB below the source floor, and 6 dB of that is spent for
  free by moving from 48 to 192 kHz.
* **Undithered 24-bit input measures 4.5 dB better, not worse** (142.1 dB at
  48 kHz against 137.6 dB), because the cascade decorrelates what would
  otherwise be distortion. Both are reported since the chain has no say in
  which the host sends.

## Headroom: the cascade moves where full scale is

Maximum stable amplitude was characterised against a clean tone generated at
the element clock. Re-measured with PCM through the cascade, same bisection and
same bound, so the numbers compare directly:

| Content | MSA at the PCM input | Peak reaching the quantizer |
| --- | --- | --- |
| Modulator alone, clean tone | 0.900, -0.92 dBFS | -0.92 dBFS |
| 1 kHz tone, 48 kHz | 0.900, -0.92 dBFS | -0.92 dBFS |
| 1 kHz tone, 192 kHz | 0.911, -0.81 dBFS | -0.81 dBFS |
| Passband-edge tone, 21.6 kHz at 48 kHz | 0.911, -0.81 dBFS | -0.81 dBFS |
| Passband-edge tone, 86.4 kHz at 192 kHz | 0.955, -0.40 dBFS | -0.40 dBFS |
| Fs/4 inter-sample, 48 kHz | 0.644, **-3.83 dBFS** | -0.82 dBFS |
| Fs/4 inter-sample, 192 kHz | 0.659, **-3.63 dBFS** | -0.62 dBFS |

**Max stable amplitude holds, measured at the quantizer. It does not hold
measured at the PCM input.** Every row above overloads at the same place, a
peak of -0.4 to -0.9 dBFS at the quantizer. What changes is how much PCM level
that corresponds to, and for inter-sample content it is 3 dB less.

The last two rows are the standard inter-sample overload probe: a tone at Fs/4
sampled at 45 degrees, so every sample sits at the stated level and the
reconstructed waveform peaks 3.01 dB above it. The cascade is a reconstruction
filter, so it produces that peak faithfully and hands it to a modulator that
cannot take it. Measured peak out of the cascade for a 0 dBFS record of this
kind is exactly 1.4142.

This is not a corner case. Heavily limited material contains inter-sample overs
routinely.

### The headroom budget exists for clipping, and 3 dB does not cover it

Measured against real material by `run_programme.py`, two things changed here.

**Nothing that has not been clipped asks for any headroom at all.** Sixteen
seconds of real 48 kHz recording, crest factors 15 to 26 dB, normalised so its
loudest sample sits at full scale, hands the quantizer a peak of exactly
1.0000 -- zero overshoot -- and survives to within 0.66 to 0.80 dB of full
scale. A 1 kHz sine asks for 0.84 dB. The synthetic percussive record, at a
21.8 dB crest factor, overshoots by 0.029 dB.

What creates an inter-sample over is the run of samples sitting flat at full
scale that only clipping produces, and the probe is the limiting case of it:
every one of its samples is at full scale by construction, which is why it
reaches exactly 3.010 dB. **So the budget has a named cause. It is not sized by
how loud music is; it is sized by how hard the host's material was limited.**

**And 3 dB is 2.4 dB short of the worst case measured.** Percussive material
clipped 12 dB overshoots by 4.876 dB and needs **5.39 dB** of headroom against
the probe's 3.84:

| Material | Overshoot | Headroom needed |
| --- | --- | --- |
| Real audio, unprocessed | +0.000 dB | 0.80 dB |
| Real audio, clipped 12 dB | +0.653 dB | 1.22 dB |
| Percussive, unprocessed | +0.029 dB | 0.61 dB |
| **Percussive, clipped 12 dB** | **+4.876 dB** | **5.39 dB** |
| 1 kHz tone | +0.000 dB | 0.84 dB |
| Fs/4 inter-sample probe | +3.010 dB | 3.84 dB |

**Recommendation: clip at the modulator input. Do not use a -3 dBFS volume
default.** README previously offered the two as equivalent alternatives; they
are not. A fixed -3 dB default gives away 2.2 dB of range on everything that
was never limited *and* is still 2.4 dB short of material that was. A clipper
costs nothing on material that never reaches it and has no upper bound to get
wrong. Either sits inside the interpolation chain, which is where
[0010](../docs/decisions/0010-192khz-and-control-word.md) already puts the
volume control and for the same reason.

**A cheap indicator comes with it.** The fraction of samples sitting on the top
or bottom quantizer code -- one comparator, free in the FPGA -- rises about
threefold per dB for several dB before the loop lets go:

| PCM level | Real audio | Real, clipped 12 dB |
| --- | --- | --- |
| -6 dBFS | 0.0000 | 0.0000 |
| -3 dBFS | 0.0016 | 0.0052 |
| -2 dBFS | 0.0056 | 0.0163 |
| -1 dBFS | 0.0164 | **unbounded** |
| 0 dBFS | **unbounded** | -- |

The in-band error stays flat at -135 to -137 dBFS right up to the edge, so
performance does not degrade into the overload: it is fine, and then it is
gone. A threshold anywhere between 1e-4 and 1e-2 gives warning with margin.
One caveat: percussive material clipped 12 dB goes from 0.0002 to unbounded in
1.5 dB, so the warning is shortest where it is most needed. The counter is an
early indication to pair with the clipper, not a replacement for it.

A measurement note that cost a wrong answer here: **the analysis window has to
be centred on the peak the cascade reconstructs, not on the loudest sample.**
For unprocessed material they are the same event. For clipped material they are
seconds apart -- 1.5 s on the percussive record, 5.9 s on the real one --
because clipping makes the reconstruction overshoot wherever a flat run happens
to sit, not where the record is loudest. Windowed on the loudest sample this
same bisection returned 3.75 dB and appeared to confirm the probe to 0.09 dB.

A smaller correction to the existing table: the 0.918 in the order sweep was
measured over 2^15 samples, which is 1.3 cycles of a 1 kHz tone. Over 2^18 it
is 0.900. The order recommendation does not change; the figure is 0.17 dB
optimistic.

## Datapath width

Coefficient width was settled above. These are the other two numbers the HDL
needs, both measured rather than reasoned.

The criterion is stated before the measurement. The most demanding source floor
of any supported rate is 192 kHz at -148.6 dBFS, so the whole interpolator is
budgeted 10 dB below that, at -158.6 dBFS, which costs 0.41 dB end to end. Nine
stages share it equally, so each gets -168.2 dBFS.

Noise is measured by difference: the same record is run twice, once at the
stated widths and once exact, and the in-band power of the difference is taken.
The difference carries no signal, so there is no lobe to excise and no pair of
near-equal spectra to subtract, and a floor 80 dB below the signal reads as
directly as one 10 dB below it.

### Signal word: 28 bits, flat across all nine stages

Sign, one integer bit, 26 fractional bits. One integer bit because the largest
peak the cascade can present is the inter-sample 1.4142, and anything past that
is already overloading the quantizer and belongs clipped rather than
represented.

Measured one stage at a time, with the rest exact, the minimum does taper with
the rate, exactly as the noise argument predicts -- a stage's rounding is white
over its own output rate, so the same word is 3 dB quieter in band at every
doubling:

| Stage | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Output rate, MHz | 0.096 | 0.192 | 0.384 | 0.768 | 1.536 | 3.072 | 6.144 | 12.288 | 24.576 |
| Minimum fractional bits | 27 | 26 | 26 | 25 | 24 | 24 | 24 | 23 | 22 |

**Building that taper is a mistake, and this is the main datapath finding.** A
half-band stage has two phases. The filtered phase accumulates products and has
to round. The pass-through phase is the centre tap against an interpolation
gain of two -- a wire -- and it rounds only if the next word is narrower than
the one the sample already sits on. A tapering chain therefore re-rounds every
sample at every stage. Measured on the whole chain:

| Schedule | 48 kHz, 9 stages | 192 kHz, 7 stages | Delay-line bits at 48 kHz |
| --- | --- | --- | --- |
| taper 26..22 | -155.9 dBFS | -156.3 dBFS | 15,259 |
| flat 24 | -153.3 dBFS | -159.1 dBFS | 14,579 |
| flat 25 | -160.5 dBFS | -165.4 dBFS | 14,983 |
| **flat 26** | **-165.5 dBFS** | **-172.3 dBFS** | **15,387** |
| flat 27 | -172.0 dBFS | -178.8 dBFS | 15,791 |

**The taper is 9.6 dB noisier than a flat word of the same starting width and
saves 0.8 percent of the delay-line storage.** Per-stage minima are real;
composing them is not, because the per-stage measurement cannot see a cost that
only exists where two stages meet. The taper measured is 26..22, one bit
narrower at stage 1 than the per-stage table asks for, so if anything the
comparison flatters it.

25 fractional bits is the narrowest flat word that meets the budget at every
rate. 26 is the recommendation, for 5 dB of margin at 2.7 percent more storage,
which is nothing against the 25 block RAMs 0011 spends on the elastic buffer.

The equal per-stage share of -168.2 dBFS is an allocation device for the table
above, not a constraint on the answer. The flat word is chosen against the
chain budget directly, and clears it by 6.9 dB, because only stage 1 comes
anywhere near its share and the other eight land far under it.

### Accumulator: 35 bits at the steep stages, 31 at the fast ones

Each product is rounded into the accumulator, which is the pessimistic reading:
a MAC whose output register is the accumulator rounds every product, not only
the final sum. The criterion is that the accumulator must not be the louder of
the two noise sources in its own stage, at or below 0.5 dB added to the signal
word's own contribution.

| Stage | Products | Signal word alone | Min fractional bits | Guard | Bits above the point | Total | Full precision would be |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 41 | -167.8 dBFS | 30 | +4 | 4 | 34 | 51 |
| 2 | 41 | -170.8 dBFS | 31 | +5 | 4 | 35 | 51 |
| 3 | 41 | -174.2 dBFS | 31 | +5 | 4 | 35 | 51 |
| 4 | 7 | -177.4 dBFS | 30 | +4 | 3 | 33 | 47 |
| 5 | 4 | -180.7 dBFS | 30 | +4 | 3 | 33 | 44 |
| 6 | 3 | -182.9 dBFS | 28 | +2 | 2 | 30 | 43 |
| 7 | 3 | -185.4 dBFS | 28 | +2 | 2 | 30 | 35 |
| 8 | 2 | -188.2 dBFS | 28 | +2 | 2 | 30 | 33 |
| 9 | 2 | -191.7 dBFS | 29 | +3 | 2 | 31 | 33 |

Rounded into three groups the HDL can parameterise: **35 bits for stages 1-3,
33 for stages 4-5, 31 for stages 6-9.** A full-precision accumulator would be
51 bits at stage 1, so this saves 16 bits there and 2 at stage 9.

Bits above the binary point come from the L1 norm of each stage's filtered
phase against the largest peak the cascade can present. That bound is 4.06 at
the three steep stages and under 2 from stage 6 on. The symmetric pre-add is
exact and one bit wider than the signal word; keeping it costs nothing.

The shape is the opposite of the coefficient result and favours the hardware
the same way. The stages needing the widest accumulators run slowest, so they
are time-shared; the stages at the element clock need 31 bits and two products.

### Round ties to even

Round-half-up is one adder and is the obvious choice. It is also biased: a word
already sitting on a finer grid ties exactly half the time and every tie goes
up, so each rounding leaves about a quarter of an LSB of offset and nine stages
of them add. Measured at the modulator input that offset is -160.4 dBFS, which
is half an LSB of a 26-bit word and looks like nothing.

It is also very nearly nothing, and an earlier version of this section said
otherwise. **The 15.7 dB this table used to report was a measurement error, not
a property of the rounding.** The corrected figures, from `run_idle.py`
section D:

Measured over 2^22, which is what the corrected columns are; the last column
is the figure this table used to print, from the same records over 2^20 with
the arithmetic mean removed.

| Rate | Ties up | Ties to even | Ties up, as published |
| --- | --- | --- | --- |
| 48 kHz | 138.41 dB | 138.42 dB | 137.45 dB |
| 96 kHz | 141.39 dB | 141.41 dB | **124.58 dB** |
| 192 kHz | 144.35 dB | 144.35 dB | 143.43 dB |
| 44.1 kHz | 137.98 dB | 137.99 dB | 124.73 dB |
| 88.2 kHz | 140.88 dB | 140.88 dB | 140.14 dB |
| 176.4 kHz | 144.10 dB | 144.07 dB | 142.79 dB |

**Worst case costs 0.02 dB**, and `results/endtoend.txt` now prints the same
figure from its own table. The old numbers came from subtracting the
arithmetic mean rather than the windowed mean before a 2^20 transform, which
counts a sub-20 Hz residue as audio-band noise; `spectra.remove_dc` now does
it correctly for every measurement in the model and explains why. The full
account is in [notes-idle.md](notes-idle.md).

The giveaway, had anyone looked: re-running the old code today puts the 124 dB
row at **44.1 kHz**, not 96 kHz. Half-up leaves the same offset at every rate,
so a fault caused by that offset cannot move between rates from one run to the
next.

**Round ties to even anyway.** It costs one adder's difference and it removes a
real static offset: measured at the modulator input, half-up leaves -168.7 to
-170.3 dBFS where ties to even leaves -187.3 to -210.3 dBFS. That offset
reaches the output as DC, where it is the output coupling capacitor's problem rather than
the FPGA's, and an unbiased rounding is the cheaper place to deal with it. What
is no longer claimed is that it costs audio-band performance. It does not,
measurably.

### What the recommended datapath measures

Signal word 28 bits flat, accumulators as above, coefficients as settled, ties
to even. `SNDR exact` is the same chain with an infinite-precision datapath.

| Rate | Datapath noise | SNDR exact | SNDR sized | Cost |
| --- | --- | --- | --- | --- |
| 48 kHz | -165.8 dBFS | 137.57 dB | 137.54 dB | 0.03 dB |
| 96 kHz | -168.6 dBFS | 140.29 dB | 140.25 dB | 0.04 dB |
| 192 kHz | -172.7 dBFS | 143.83 dB | 143.83 dB | 0.00 dB |
| 44.1 kHz | -165.6 dBFS | 137.56 dB | 137.55 dB | 0.01 dB |
| 88.2 kHz | -168.6 dBFS | 140.18 dB | 140.15 dB | 0.03 dB |
| 176.4 kHz | -171.7 dBFS | 143.40 dB* | 143.33 dB | 0.07 dB |

**The whole sized datapath costs at most 0.07 dB.**

\* This row used to read 125.06 dB and carried a footnote blaming a limit
cycle. **That was a measurement error.** The same record, with the windowed
mean removed instead of the arithmetic mean, measures 143.40 dB; measured over
2^21 with nothing else changed it measures 143.69 dB. The conclusion the
footnote drew -- that the discrepancy had nothing to do with word width -- was
right, for the wrong reason. See below and [notes-idle.md](notes-idle.md).

## There is no low-frequency limit cycle. That was a measurement error.

This section used to report one, and several figures elsewhere in this file
were adjusted for it. **All of it was the analysis window.** Anyone who read
the earlier text should discard it: there is no intermittent fault in the loop,
dither was never failing to fix anything, and the 1-in-36 rate was a count of
how often a rounding residue landed where a too-short transform could see it.
`run_idle.py` establishes this and [notes-idle.md](notes-idle.md) gives the
full account.

### What was measured

The claim was that one run in 36 came back 15 to 19 dB low with every bit of
the excess in the 20 Hz to 100 Hz bins, worst case 125.1 against 143.3 dB. That
run reproduces exactly, so it could be taken apart:

| The same 2^20 record | SNDR | 20-100 Hz |
| --- | --- | --- |
| DC removed arithmetically, `x - x.mean()` | 125.06 dB | -130.2 dBFS |
| DC removed with the window | **143.40 dB** | **-172.9 dBFS** |

and the same trajectory, with nothing corrected, simply measured for longer:

| Window | Bin width | DC main lobe reaches | SNDR |
| --- | --- | --- | --- |
| 2^20 | 21.5 Hz | 258 Hz | 125.06 dB |
| 2^21 | 10.8 Hz | 129 Hz | 143.69 dB |
| 2^22 | 5.4 Hz | 65 Hz | 143.94 dB |
| 2^23 | 2.7 Hz | 32 Hz | 144.11 dB |

The Kaiser at beta 26 has a main lobe 12 bins wide, which at 2^20 samples of a
22.6 MHz element clock is ±258 Hz. **At that record length, near-DC energy and
20-100 Hz energy are the same bins.** Subtracting the arithmetic mean does not
remove the DC the transform sees, because the window weights the centre of the
record far above its ends, so whatever residue is left lands in the lowest
audio bins at nearly full strength.

Rerunning the whole limit-cycle experiment -- six rates, six perturbations,
with and without 0.25 LSB of quantizer dither -- gives **1 run of 72 more than
5 dB below its row median as published, and 0 of 72 on the same records
measured correctly.** Dither was not moving the fault around; every remedy
changes the record, every record leaves a different residue, and the short
window reported the residue.

### What is really there, and why it does not matter

A residue is unavoidable and it is not a limit cycle. The output takes eight
levels spaced 2/7 apart, so **the mean of an N-sample record can only sit on a
grid of (2/7)/N**: a finite record of this alphabet cannot express its own mean
exactly. One unbalanced sample per window is

| Window | |
| --- | --- |
| 2^20 | -128.3 dBFS |
| 2^22 | -140.3 dBFS |
| 2^24 | -152.4 dBFS |

and that is what the tripped record had -- measured per 2^20 block, an
imbalance of `+1 -1 +1 -1 0 0 0 0` samples. A -128 dBFS component at about
10 Hz. It is **below the audio band**, it is at the smallest level the output
alphabet can express over that window so nothing in the digital design can
reduce it, and it is DC at the output, which is what the coupling capacitor is
already there for.

Measured directly at idle it is not even that large. Over 180 trials of
`material.py`'s idle catalogue -- fades into silence, digital silence, near
silence at -100 dBFS, small DC offsets, six rates, six preambles each -- the
20 Hz to 100 Hz band of the element sum measures:

| Idle material | 20-100 Hz, over 180 trials |
| --- | --- |
| digital silence | -324 to -346 dBFS |
| small DC offset, -60 dBFS | -321 to -331 dBFS |
| after a fade to silence | -147 to -153 dBFS |
| digital silence, dithered 24-bit source | -162 to -175 dBFS |
| near silence, -100 dBFS | -126 to -140 dBFS |

The last two rows are the source's own noise arriving at the output, which is
what should happen. The first two are nothing at all. Measured the old way the
same trials put 22 of 180 more than 10 dB above their own median, with digital
silence reading -130 dBFS where it is really -340.

A constant at the modulator input does not produce an idle tone either. Swept
from -160 to -60 dBFS, including the -133 to -119 dBFS range where a
first-order loop's correction rate would land between 20 and 100 Hz, the
in-band figure stays at -179 dBFS and all of it is the shaped floor above
2 kHz. A third-order loop with an eight-level quantizer does not lock to a
constant.

### What this cost, and what stops it recurring

Three published results were wrong: this section, the ties table above, and the
capacitor-tolerance table in `results/analog.txt`. Everything else checked --
every per-rate figure, the 132.8 dB tone figure, the rotation table, the order
sweep, the volume placement, the datapath widths -- is unaffected to 0.01 dB,
because the term only shows when the residue happens to be large.

(132.8 dB survived this correction unchanged, and was then corrected for a
different reason: it is a tone's figure and a median window's figure, not a
bound. See the end-to-end section above and `notes-programme.md`.)

The fix is in one place. `spectra.remove_dc` removes the windowed mean and
documents why; `spectra.Measurement` now calls it for every measurement, so a
new measurement site cannot get this wrong by forgetting.

### What this leaves unmeasured

Closing this item is a negative result, and it is worth being precise about how
negative. **The low-frequency behaviour of this loop has not been
characterised; it was mis-measured, and the mis-measurement has been removed.**
What is established is that 180 near-idle trials and 72 tone runs show nothing
in the audio band, and that a constant at the modulator input produces no idle
tone. What is not established: nothing here was measured *below* 20 Hz on
purpose, since every measurement treats sub-20 Hz energy as something to
remove; no record longer than 341 ms was run, so a wander slower than about
3 Hz would not have been seen; and no threshold in physical units was ever set
for what an idle-channel fault worth acting on would look like, because nothing
came close enough to need one. `notes-idle.md` lists these in full.

## Measurement traps found while building this

Each cost real time and would cost it again.

**The FFT has to be long.** At the 24.576 MHz element clock, a 2^16 transform
gives 375 Hz bins, so the entire audio band is about 53 bins. Removing the
signal lobe and the harmonic lobes leaves nothing, and the measurement reports
infinite signal-to-noise with nonsensical distortion. Use 2^20 or longer, which
gives 23.4 Hz bins and around 600 usable noise bins. Simulation is not the
bottleneck: 2^20 samples takes under a second.

**Element mismatch produces a DC offset as well as noise.** Left in, it lands
in the lowest FFT bins, which sit inside a band starting at 20 Hz, and it then
dominates the in-band figure and makes the rotation look ineffective. It showed
up as in-band power 55 dB above a band nine times wider, which is the signature
of concentrated rather than broadband energy.

**Removing the mean means removing the mean the *transform* sees, and this one
cost three published results and two investigations to find.**

`x - x.mean()` zeroes the flat average of the record. The transform does not
take a flat average: it weights by the window, and a Kaiser at beta 26 weights
the record's centre enormously more than its ends. A record whose offset drifts
across the window therefore still has a DC bin after `x - x.mean()`, and that
bin is not confined to bin 0 -- the main lobe is 12 bins, ±281 Hz at 2^20 of
the element clock -- so the leftover lands inside a band starting at 20 Hz and
is counted as audio. Use `spectra.remove_dc`, which subtracts
`sum(w*x)/sum(w)`. `spectra.Measurement` now calls it for every measurement, so
a new measurement site cannot reintroduce this by forgetting.

*What it looks like when you hit it.* A figure comes back 15 to 19 dB low.
Every bit of the excess is in the 20 Hz to 100 Hz bins, so it looks like a
low-frequency fault rather than a raised floor. It is intermittent: most runs
are fine and roughly one in thirty is not. It survives every remedy you try,
and dither appears to *move* it to a different run rather than remove it. It
responds to perturbations far below the audio -- adding 2^-40 at the modulator
input switches it on or off -- so it looks like a real property of an exact
loop. Every one of those is the artifact, and together they are convincing
enough to have been written up here as a loop fault.

The reason a delta-sigma record always has the offset to leak: the output
alphabet is eight levels 2/7 apart, so the mean of an N-sample record can only
sit on a grid of (2/7)/N. One unbalanced sample per 2^20 window is already
-128 dBFS, which is 18 dB above the floor being measured. Which side of that
grid a record lands on is a lottery, and every remedy -- dither, a different
seed, one more sample of settling -- reshuffles it.

*The signature that gives it away, and the general rule.* Rerunning the ties
table today put the bad row at 44.1 kHz where it had been published at 96 kHz.
Round-half-up leaves the same offset at every rate, so **a fault that migrates
between rates from one run to the next cannot be caused by something that is
identical at every rate.** When a fault moves like that, it is a lottery over
records, and a lottery over records means the measurement, not the design. The
cheap confirmation is to measure the same record over a longer window: a real
in-band fault stays, an artifact of this kind is gone by 2^21.

**A DC offset is not only a mismatch problem, and removing the mean is not
optional anywhere.** The interpolator's own rounding leaves one too. Measured
on the nine-stage chain it was -143.1 dBFS against a rounding noise of
-159.5 dBFS, so reporting the chain without removing it made the datapath look
18 dB worse than it is. An earlier version of this paragraph went on to say
that the same offset at the modulator input was "not a measurement problem at
all but a real 15.7 dB fault". It was a measurement problem: see the ties
section above, where it now measures 0.02 dB. Removing the mean correctly is
what settles both. Any time a figure comes back bad, look at the 20 Hz to 100 Hz bins
first: if the excess is all there, it is an offset, not noise. Note what that
check cannot tell you, since it took two independent investigations to notice:
excess confined to those bins is equally the signature of a DC residue the
window is spreading into them, which is what the "limit cycle" turned out to
be. Confirm by re-measuring the same record over a longer window before
believing the loop did it.

**The FFT has to be long enough for the tone's harmonics to clear its own main
lobe, which is a stricter rule than having enough noise bins.** At 2^18 the
element-clock bins are 93.75 Hz and the Kaiser main lobe is 12 bins, so a
1 kHz tone's second harmonic falls inside the signal lobe, the harmonic
excision removes the signal, and SNDR is reported as 0.41 dB. The requirement
is `n > half_lobe * fs / f_sig`, which for a 1 kHz tone at 24.576 MHz is 2^19.
2^20 is the working minimum for both reasons.

**Peaks read off an un-faded record are the record's edge, not the signal.** A
record that switches on at a non-zero sample is a step and the cascade rings on
it. An un-faded 0 dBFS sine measured a peak of 1.118 through the chain where
the true reconstructed peak is 1.000, and the inter-sample probe measured 1.429
where its true peak is sqrt(2) = 1.4142. That is 1 dB of headroom invented out
of nothing, on the one measurement where headroom is the answer.

**If a figure does not move when the input level moves, the instrument has
stopped listening to the input.** This is the cheapest check in the list and it
caught the largest error `run_programme.py` made. An error figure that came
back at -88.4 dBFS at -12, -40 and -70 dBFS, to the last decimal and in the
same FFT bins, was not measuring the converter -- it was measuring a gain fit
that had been taken on un-centred signals, so the mismatch DC offset biased it
by whatever the reference happened to carry below 280 Hz. The fitted gain came
out 1.207 instead of 0.9988 on the quiet record. It cost a complete pass and
produced a 40 dB finding that did not exist. **Removing the mean from the error
is not enough; anything fitted to the error has to have it removed too.**

**A scalar fitted to broadband data has to be fitted in the band you report.**
Signal-to-noise against a tone excises the signal lobe; broadband material has
no lobe to excise, so the equivalent is fitting and removing a scalar gain --
element mismatch is a static weight and shows up as one. Fitted over the whole
record, that fit is dominated by the modulator's out-of-band noise, which is
90 dB above the in-band error and whose inner product with the signal is not
zero. The leftover gain error then injects a pure in-band residual around
-77 dBFS. Restricting the fit to 20 Hz-20 kHz drops it below -160.

**A lag check over a few samples cannot check alignment.** The signal is
band-limited to 20 kHz and sampled at 24.576 MHz, so its autocorrelation is
flat to six decimal places over plus or minus eight samples: an argmax there
reports where the out-of-band noise fell, and it false-alarmed on 34 of 90
segments of real material. Check the in-band error at the offset used against
the in-band error a few hundred samples away instead -- 256 samples is a fifth
of a period at 10 kHz, and a correct alignment wins by 90 dB or more.

**A peak window has to be centred on the reconstructed peak, not the loudest
sample.** They are the same event in unprocessed material and seconds apart in
clipped material. Getting this wrong made a headroom bisection return 3.75 dB
where the answer is 5.39 dB, and it looked right because it agreed with the
inter-sample probe to 0.09 dB.

**Per-stage results do not always compose.** Each interpolator stage's minimum
signal word, measured with the other stages exact, is real. The chain built
from those minima is 9.6 dB noisier than the flat word they suggest is
wasteful, because the cost lives where two stages meet and no single-stage
measurement can see it. Measure the whole chain before believing a schedule.

## What this model does not include

Three gaps listed here previously are now closed and their results are above.
**The interpolator and the modulator are connected**, measured with real
24-bit PCM at all six rates, and the cascade costs 0.2 dB against the
modulator measured alone. **The datapath is sized**: 28-bit signal word flat
across the nine stages, 35/33/31-bit accumulators, ties to even. **The
low-frequency limit cycle did not exist**: it was the analysis window, the
loop is clean at idle down to -324 dBFS in the 20-100 Hz band, and the
measurement is fixed in `spectra.remove_dc` so it cannot recur.

What is still missing, in the order it is likely to matter:

**Programme material has now been run**, by `run_programme.py` against 16.7
seconds of real 48 kHz recording plus multitone and noise; see
`notes-programme.md`. Three things came back: 132.8 dB is a median and not a
bound, the error is worst in quiet passages, and the 3 dB headroom budget is
2.4 dB short of clipped material. All three are in the sections above.

**What programme material still has not tested is anything above 10 kHz.** The
real recordings available carry nothing up there, so 0010's warning that
high-level material above 20 kHz eats modulator headroom remains tested only by
the passband-edge rows in the headroom table. Intermodulation between a signal
and the ultrasonic content a 192 kHz source may carry is still untested. Real
material was also available at 48 kHz only -- the other five rates use
synthetic stand-ins with the right spectra and the wrong crest factors -- and
every figure except the element-draw table uses a single mismatch seed, which
spans 5.3 dB across five draws of the same one percent specification.

**The modulator's arithmetic is sized**, by `run_modarith.py`. Peak integrator
states are small, which is the CIFB-with-feedforward topology doing what its
docstring claims -- every integrator is driven by the loop error, not by the
signal, so the states never carry the audio:

| | Integrator 1 | Integrator 2 | Integrator 3 |
| --- | --- | --- | --- |
| 1 kHz tone at -3.7 dBFS, worst of six rates | 0.069 | 0.265 | 0.361 |
| Inter-sample content at its max stable level | 0.082 | 0.400 | 0.630 |

So the states need no integer bits beyond the sign over the range measured.
That is a starting point for sizing, not a size: how many fractional bits they
need, and what happens when the loop coefficients are truncated, is untested.

### Modulator word widths

| | Total bits | Sign | Integer | Fractional |
| --- | --- | --- | --- | --- |
| Feedback coefficients | 10 | 1 | 1 | 8 |
| Integrator 1 state | 28 | 1 | 1 | 26 |
| Integrators 2 and 3 | 20 | 1 | 1 | 18 |

**Only the first integrator needs a wide word, and that is the opposite of the
obvious guess.** Holding all three at 20 bits and widening one to 28 gains
42.3 dB if it is the first and 0.1 to 0.3 dB if it is either of the others.
Rounding at the first integrator is integrated twice more before it reaches the
quantizer, so it is amplified at low frequency; rounding at the last is not
integrated at all. Sizing per integrator rather than flat costs 68 bits of
state instead of 84.

**The integer bit is required, not margin.** Near the maximum stable input the
third integrator reaches between 0.8 and 1.13 depending on how the coefficients
round, so zero integer bits would overflow. One gives a range of plus or minus
two.

**The coefficients need far less than they are exported at.** Ten bits total
holds full performance, against the 24 in the export. The export is not wrong,
only generous; narrowing it is free if the multiplier size ever matters.

Checked against tones at 1, 6 and 19 kHz and against the inter-sample probe at
its maximum stable level, with no overflow in any case. Tones below about
200 Hz cannot be measured at this transform length, because at 23.4 Hz bins the
signal and its harmonics occupy the whole lower band; their peak states and
overflow counts are still valid.

### Volume goes at the modulator input

Measured at 96 kHz, order 3, comparing a digital gain applied at the chain
input against one applied after the interpolator:

| Attenuation | At the chain input | At the modulator input |
| --- | --- | --- |
| -6 dB | 140.3 dB | 140.3 dB |
| -20 dB | 138.7 dB | 140.2 dB |
| -40 dB | 123.9 dB | 134.2 dB |
| -60 dB | 104.2 dB | 114.6 dB |

Identical to about -6 dB, then late placement pulls ahead by roughly 10 dB.
What decides it is which noise sits downstream of the multiply. Applied at the
input, the interpolator's rounding is added after the attenuation and stays
fixed while the signal shrinks. Applied at the modulator input, that rounding
is attenuated along with the signal, and only the modulator's own quantization
noise stays put, which is 168 dB down and has room to spare.

**Cost: one multiplier at the element clock**, against the 2.86 the
interpolator already needs there. If that binds, the gain could be folded into
the final stage's coefficients instead, merging two multiplies into one, at the
price of wider coefficients and a glitch-free update on volume changes.

**A middle position was not measured.** The datapath analysis puts rounding at
stage 9 some 24 dB quieter in band than the same rounding at stage 1, so the
harm concentrates early and a gain after the first few stages should capture
most of the benefit at a far lower clock rate. Two attempts to measure it both
produced invalid numbers: splitting the cascade breaks the settling offset, and
compensating by taking the settled tail breaks the coherent FFT window. Only
the two endpoints above are trustworthy.

Also absent, as before: finite integrator gain, clock jitter, and the analog
reconstruction filter.

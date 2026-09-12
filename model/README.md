# model

A numerical model of the audio chain, built to answer three questions the
repository left open with numbers rather than adjectives. Run it:

```
./.venv/bin/python model/run_experiments.py
```

Figures land in `figures/`, the full log in `results/measurements.txt`.

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

### Rotation: plain data weighted averaging is enough

Measured at order 3 over 2^21 samples, with the DC offset removed. Element
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

**One percent mismatch costs 0.5 dB with rotation and 70 dB without.** That is
the whole argument for thermometer coding, and it confirms the claim in
[hardware/README.md](../hardware/README.md) that ordinary one percent parts are
adequate. Without rotation the output is distortion-limited: SNDR and THD track
each other exactly, which is the signature of mismatch appearing as harmonics
rather than as noise.

No more sophisticated rotation scheme is needed. Element loading was verified
constant at seven across every code, which is the invariant the differential
drive exists to provide.

## Measurement traps found while building this

Both cost real time and would cost it again.

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

## What this model does not include

Coefficient quantisation, finite integrator gain, clock jitter, and the analog
reconstruction filter. Those are where the remaining margin goes.

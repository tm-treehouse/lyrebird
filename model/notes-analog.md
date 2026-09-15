# Element resistor and reconstruction filter

Measured by `run_analog.py`. Both values were placeholders and the board
cannot be finished without them.

## Element resistor: 3.32 kohm

E96, thin film array, one package per four elements.

| | |
| --- | --- |
| Rail current, constant by construction | 13.92 mA |
| Full-scale current per channel | 6.958 mA peak |
| Feedback resistor for 2 V | 406.5 ohm, so 402 ohm E96 |
| Output at digital full scale | 1.978 V RMS |
| Element dissipation | 45.9 mW total, 3.28 mW per 0402 |

**Three independent arguments land within 300 ohm of each other.**

The resistors should not be the loudest thing in the chain. Their own thermal
noise equals the measured digital floor of 133.5 dB at 2585 ohm. At 3.32 kohm
they sit 1.1 dB below it, costing the pair 3.6 dB.

The board has to fit one unit load before enumeration **with the registers in
an undefined state**, so all 28 elements must be assumed high rather than the
14 that are high by construction once running. That needs at least 3312 ohm,
and 3.32 kohm is the first E96 value above it. At the netlist's 1 kohm
placeholder the power-on total is 214 mA against a 150 mA limit, which would
have been found on a bench rather than in a model.

Past about 3 kohm each doubling buys 3 dB of resistor noise and returns less
current. Going from 1 kohm to 3.32 kohm saves 32 mA and costs 2.0 dB; going on
to 10 kohm would save 9 mA more and cost another 3.3 dB.

**This moves where the noise floor is.** System noise at 3.32 kohm is 125.2 dB,
15.2 dB above the target. The analog stage measures 125.8 dB against the
digital chain's 133.5, so the output stage is now the floor of this design and
the amplifier's own voltage noise is the largest single term in it.

Two smaller effects, both favourable. The register's output impedance is 0.6
percent of the element at 3.32 kohm against 2.0 percent at 1 kohm, and it
appears identically on every element so it is gain error rather than
distortion. Self-heating falls from 10.9 to 3.28 mW per element, and the
differential arrangement cancels the first-order thermal term exactly, leaving
a gain drift that holds while both sides track.

## Reconstruction filter: three poles, 1 MHz and two at 200 kHz

180 pF per element at the summing node gives the first pole for one part, since
the summing resistors are already in the path.

| | |
| --- | --- |
| In-band droop at 20 kHz | 0.088 dB against a 0.100 dB budget |
| Intermodulation from the first amplifier | -190.3 dBFS |
| Margin against threshold | 43 dB |
| Group delay at DC | 1.75 us |
| Peak slew at the output | 0.03 V/us against 40 V/us unfiltered |

**The two corners are set by different things**, which is why they are not the
same. The 1 MHz pole is set by the amplifier rather than the spectrum: it is
the loosest corner that still clears the intermodulation threshold with a
10 MHz amplifier, and it costs 0.0017 dB in band. The 200 kHz poles are set by
the droop budget: two real poles at f cost twice 10log10(1+(20k/f)^2) at
20 kHz, so 0.1 dB puts the floor at 187 kHz and 200 kHz is the first round
value above it.

The measurement is taken at 98.3 MHz rather than at the element clock, so the
images the staircase carries at every multiple of 24.576 MHz are measured
rather than assumed away.

**Rejected:** a pre-emphasis in the interpolator's first stage would pay the
droop back and let all three poles drop an octave, and it is free in tap count.
Not recommended, because the filter already clears every threshold by 20 dB or
more and a response correction living in two places is a maintenance hazard
rather than a saving.

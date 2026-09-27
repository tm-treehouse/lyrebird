# Open items

What is not decided. The [decision records](decisions/) cover what is, and say
almost nothing about what is not, which is how a list like this gets
reconstructed from memory six months later.

Keep this file honest. Delete an item when a decision record covers it, rather
than leaving both.

## The most significant open item: the reference rail carries the signal

**The DWA rotation makes the reference-rail current track the signal, and the
predicted error is 35 dB above the chain's own floor.** This is the largest
outstanding risk in the design and it has no accepted answer yet.

0008 guarantees seven elements high at every code, so the *DC* load on the
reference is constant. It guarantees nothing about how often lines change, and
the 180 pF element filter capacitors and the registers both draw current in
proportion to that. Because the DWA pointer advances by the code, consecutive
windows are disjoint until they wrap and the number of changing lines is
`T = 14 − 4|s|` about mid scale — a full-wave rectifier, so the transition
rate carries the signal's magnitude onto the even harmonics, and its product
with the signal lands on the odd ones.

| | |
| --- | --- |
| Predicted in-band error | **−101.1 dBFS**, third harmonic |
| The chain's own noise | −136.5 dBFS |
| What 0012's 110 dB target allows here | −113.7 dBFS |

Worst at full scale, because the level dependence is quadratic — which is
where the target is specified. Programme material gives −104.4 dBFS and
sustained bass −99.0, so real content does not escape it.

What is known, and what is not:

- **The two properties appear inseparable.** DWA shapes mismatch to first
  order *because* the pointer advance equals the code, which is exactly what
  ties the changing-line count to the code. Four alternative rules were tried
  and all four trade the whole benefit away: no rotation 57.05 dB SNDR at one
  percent elements, advance-by-one 84.23 dB, LFSR 77.82 dB, shared pointer
  81.33 dB, against plain DWA's 133.79 dB.
- **Decoupling is not the mitigation**, and both 0008 and parts-notes.md said
  it was. The disturbance is at twice the signal frequency and at the
  programme envelope, so the eight 100 nF parts are about 100 Ω where it lives
  and the regulator's 10 mΩ is what the rail sees. The chain's floor would
  need 170 µΩ at 2 kHz.
- **A transition ballast is the untested idea.** `T` is bounded above by 14
  and the modulation is the deficit, so dummy lines toggled to make it up
  flatten the current without touching the selection rule, at the cost of a
  fully toggling array's current. Nobody has designed or costed it.
- **It is a prediction, not a measurement.** The model has no supply in it;
  this is a digital proxy through hardware constants, every one of them listed
  in the log for rescaling. A bench measurement of the rail with the modulator
  running is what settles it.
- **The register `Cpd` uncertainty changes the size, not the existence.** Per
  package rather than per flip-flop drops that row 24 dB, and the
  capacitors-only case is still 21 dB above the chain's floor.

Source: [model/results/reference-current.txt](../model/results/reference-current.txt),
section H of [model/notes-idle.md](../model/notes-idle.md).

## Wall-wart power: built. Isolated USB: not yet

[0014](decisions/0014-wall-wart-power.md) supersedes 0009 and amends 0005 and
0012. The supply half is in both netlists; the isolator is not.

**Done.** A 12 V barrel jack feeds a resettable fuse, a series Schottky for
reverse polarity, a Schottky clamp holding the reversed rail out of the
converter's negative limit, and an 18 V TVS. An LMR33630 takes 12 V to 5 V and
everything downstream of `+5V` is unchanged. A second LMR33630, wired as an
inverting buck-boost, makes −6 V and sends it to the module across two
mezzanine pins taken from the ground allocation. USB's `VBUS` now reaches one
pin, the bridge's own sense input.

The module's charge pump is deleted with all of its support parts, so **the
analog board now contains no switching converter at all** — which was the
reason for choosing this arrangement over the three alternatives, each of
which relocated a switcher rather than removing one. The difference network is
back to 200 Ω and the **2.1 dB is recovered**, not merely recoverable.

What it retired, all of it confirmed gone from the netlists: the 472 mA
against 500 mA margin, the 150 mA pre-enumeration rule, the 4.43 V worst case
on `VIN_P`, the LTM4622 run-pin gating and its NMOS, and the flying-capacitor
ground return.

**Still to do.** The ADuM4165/4166 is not fitted and the SuperSpeed pairs are
still routed. Isolation forces USB 2.0 High Speed, which costs nothing —
192/24 stereo is 1.9 % of it — and removes two 5 Gbps pairs from the layout.
Whether supply ground ties to chassis is undecided.

**What it did not fix**, as 0014 said it would not: the reference-rail item
above. That is transition current into rail impedance and is indifferent to
where the rail's power comes from.

**A correction worth keeping.** The 604 Ω network was recorded here and in
parts-notes.md as having been chosen because the charge pump's internal LDO is
rated 50 mA. That was false — the LT3094 took `VOUT−` directly and `LDO−`
drove nothing, as the netlist's own comment said. The constraint that actually
bound was the USB total: 509 mA against 500 at 200 Ω. The conclusion survived
the correction; the stated reason did not.

## Flagged in the repo, blocking nothing yet

| Item | Where | Note |
| --- | --- | --- |
| ~~LTM4622 run-pin behaviour~~ | [0014](decisions/0014-wall-wart-power.md) | **Closed, by deletion.** The gating existed to keep the board inside one unit load until USB activity released it. It was worse than unnecessary once the board was externally powered: the enable came from the bridge's suspend output, which is asserted whenever no host is present, so the FPGA core rail never came up at all — and a transient showed it starting and collapsing to 319 mV on every power-up besides. Both RUN pins are tied on. Found by `hardware/sim/power_input_transient.py`, not by reading the netlist, where every net was connected exactly as intended |
| LTM4622 footprint | `hardware/symbols/` | The symbol exists; the LGA-25 land pattern does not. Pad size is a manufacturer number, not a guess |
| Connector pin assignment | [interface.md](../hardware/interface.md) | Waits on layout by design |

## Blocking a schematic

Found by auditing unconnected pins in the generated netlists, not by reading
this list, so treat the netlist as the authority on what is missing.

### Closed

The main board's connectivity gaps are wired. The LTM4622 has a symbol in
`hardware/symbols/lyrebird.kicad_sym` and sources both switching rails; the
flash is an MX25R6435F at 64 Mbit, which is what Cologne Chip's own board for
this die fits and which runs at the 2.5 V `VDD_WA` where an ordinary 2.7 V
part cannot; the JTAG pins go to a 2x5 header; the ferrite is at `VBUS`; a
USB 3.0 Micro-B receptacle carries both the 2.0 pair and the SuperSpeed
pairs; the crystal, its load capacitors and the `RREF` resistor are fitted to
datasheet values; and the power-on reset network is sized from the GateMate
formula. The FT601Q is down to one open pin, the one its datasheet says not
to connect.

Three real errors surfaced while wiring it, all now fixed: the bridge's
`AVDD` was on 3.3 V when it is a 1.0 V PLL supply with a 1.4 V absolute
maximum; every LT3045 had `SET` open, so no rail had a programmed voltage;
and the bridge's `GPIO[1:0]` FIFO mode straps were not strapped.

The mezzanine had two of its own, both of which put 3.3 V on pins rated
2.5 V: the element clock went straight to the header instead of through the
translator, and `ID0` was strapped to the 3.3 V element reference rail. The
translator's signal pins were not wired at all, which is what let the clock
bypass it. `assert_below_abs_max` in `hardware/netlist/lyrebird_parts.py`
now fails the build on this whole class of error.

### Chosen since, with the datasheet each was verified against

Every part the module was missing now exists in the netlist, which generates
with zero errors at 126 components and 144 nets. Reasons and verified
specifications are in
[parts-notes.md](../hardware/lyrebird-dac-reva/parts-notes.md).

| Item | Part | Decided by |
| --- | --- | --- |
| Output op amp | OPA1612AID | 1.1 nV/√Hz, the best row on the measured noise curve |
| Registers | SN74ALVCH16374DGGR | VIH 2.0 V at a 3.3 V supply, with CMOS not BiCMOS outputs |
| Divider and fanout | SN74LVC1G74 + LMK1C1104 | 50 ps output skew; the single-chip alternative wanted 65 mA |
| Element resistor | 1.69 kΩ + 1.65 kΩ, E96 | 3.34 kΩ split around the filter capacitor |
| Reconstruction filter | 180 pF per element, then 2.0 nF and 1.3 nF | A shunt capacitor at a virtual ground forms no pole at all |
| 2.5 V module rail | Fourth LT3045 | Consistency; nothing on it reaches the signal |
| Output connector | SJ1-3523N | |
| Oscillators | CCHD-957, symbol and 9×14 mm footprint drawn | 0012 |

Both post-regulators are chosen and wired. The charge pump that used to sit in
front of them is **deleted** — 0015 moved the negative rail to the main
board, so the analog board now contains no switching converter at all. It was
fully worked out and never built, which is the cheapest way for a part
selection to end.

### Still never chosen

- **Headphone amplifier.** No part, and no decision on whether the first
  module carries one.
- **Which module to build first.** Line, headphone, or combined. The ID
  encoding in [interface.md](../hardware/interface.md) supports all three.
- **Whether to provision an unpopulated quad-SPI PSRAM footprint**, six pins,
  as insurance against a future requirement. See
  [0011](decisions/0011-pack-three-samples-per-fifo-word.md).
- **Whether to use git-lfs** for `hardware/datasheets/`. The tool is installed
  but the repository is not configured for it, and that decision is much
  cheaper before the directory fills with multi-megabyte PDFs than after.

## Answered by the modelling, and no longer open

Order 3, cascade of integrators with feedback and the input fed forward. Nine
half-band stages, 163 taps falling to 7, coefficient widths 26 bits down to 8.
Plain rotation, which one percent elements cost 33 dB without and 0.5 dB with.
The interpolator datapath at 28 bits with accumulators of 35, 33 and 31, and
the modulator's own states at 28, 20 and 20 bits.

All of it is measured in [model/README.md](../model/README.md) and exported to
`model/export/coefficients.json`, with a generated SystemVerilog package so the
RTL reads the same numbers rather than deriving its own.

## Still open on the signal chain

- **Whether volume can move earlier than the modulator input.** It is placed
  there and measured, but the cheaper middle positions could not be measured:
  splitting the cascade breaks either the settling offset or the coherent FFT
  window. Worth pursuing only if a multiplier at the element clock proves
  expensive.
- ~~**Real material.**~~ **Closed.** Fourteen real 48 kHz recordings measured
  window by window, plus synthetic material at all six rates. It changed three
  claims: 132.8 dB is a tone's figure and a median window's, not a worst case
  (worst window 111.5 dB); the 3 dB headroom budget is 2.4 dB short of the
  clipped case it exists for; and the error is worst where the signal is
  quietest. See [model/notes-programme.md](../model/notes-programme.md).
- ~~**The low-frequency limit cycle.**~~ **Closed.** There was no limit cycle:
  the 15 to 19 dB was an analysis-window artifact, and the same records measure
  correctly once the windowed mean is removed instead of the arithmetic one
  (1 of 72 runs low as published, 0 of 72 corrected). Fixed at source in
  `spectra.remove_dc`. See [model/notes-idle.md](../model/notes-idle.md).

## Blocking HDL

- **Status word bit layout.** Described in prose in
  [0010](decisions/0010-192khz-and-control-word.md), never mapped to bits.
  Blocks the status path only.
- **Prefill threshold and the lock state machine.** Fifty to a hundred
  milliseconds is a range, not a threshold, and the mute, drain, prefill,
  resume sequence exists only as prose. Blocks finishing that state machine,
  not starting it.

## Behaviour gaps

These are worth separating out, because a missing parameter shows up at review
and a missing behaviour shows up at integration.

- **Underrun.** Counted in the status word, and prefill exists to prevent it,
  but nothing says what the modulator receives when the buffer actually runs
  dry. Holding the last sample puts a DC step into a delta-sigma loop and
  clicks. Ramping to zero is the usual answer.
- **Host idle.** No defined behaviour when the host simply stops sending.
- **Module hot-swap.** The ID pins can change. Nothing says what happens if
  they do while a stream is running.

## Deliberately deferred

Not open questions. Decisions to not decide, recorded so they are not
relitigated by accident.

| Item | Record |
| --- | --- |
| USB Audio Class, driverless operation | [0004](decisions/0004-defer-usb-audio-class.md) |
| Four-bit differential, would need a main board respin | [0008](decisions/0008-multibit-delta-sigma-with-dwa.md) |
| Headphone power beyond bus limits, a module carries its own jack | [0009](decisions/0009-usb-bus-power.md) |
| External SRAM, the requirement is latency-bounded not memory-bounded | [0011](decisions/0011-pack-three-samples-per-fifo-word.md) |

## Not blocked

**Nothing blocks starting.** Four of the five tasks the original handoff
proposed depend on none of the
above: the bridge read interface, the word unpacker with tag hunting, the host
pump, and the testbench. Only the clock-domain crossing touched the open list,
and [0011](decisions/0011-pack-three-samples-per-fifo-word.md) settled its
sizing.

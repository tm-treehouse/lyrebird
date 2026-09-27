# 0015 — The negative analog rail crosses the mezzanine

**Status:** accepted. Completes [0014](0014-wall-wart-power.md), which stopped
at the main board. Amends [0008](0008-multibit-delta-sigma-with-dwa.md)'s
difference-network value and [0012](0012-module-clock-architecture.md)'s analog
rail sources.

> **This record exists because it was missing.** The change it describes was
> built, and everything in the repository referred to it as "decision 5" — a
> phrase that appears in twelve files including the decision index, where a
> bare "5" reads as 0005. A validation pass found the record it pointed at did
> not exist. The numbering here is 0015; "decision 5" was the fifth item on an
> open-items list, not a record.

## Context

0014 replaced USB bus power with a 12 V supply and stopped at the mezzanine. The
module still made both its analog rails locally, doubling the header's 5 V with
an LTC3265 and inverting the doubled rail, and that cost more than it looked:

    op amp stage and charge pump   139 mA from 5 V
    the stage itself                66 mA across both rails
    conversion overhead             73 mA -- a third of the module

A doubler costs about twice its output current at the input, and the negative
rail was inverted from the already-doubled one, so it was paid for twice over.
That overhead is also what forced the difference network to 604 Ω rather than
the 200 Ω the noise arithmetic wants, forfeiting **2.1 dB** of stage noise:
negative-rail current was expensive there in a way it is nowhere else.

## The observation that decided it

**Only the negative rail ever needed help from outside.** The output swings
±2.83 V peak and the OPA1612 reaches within 600 mV of its rails, so the positive
analog supply needs about 3.5 V — and the mezzanine had carried 5 V all along.
The doubler existed because the module made both polarities *symmetrically* from
one input, not because either polarity required it.

Four options were costed. Three of them — keeping the pump, carrying 12 V to the
module, or giving the module its own supply input — each leave a switching
converter beside the resistor array or move one there. Only one removes it.

## Decision

**The main board makes −6 V and sends it across the mezzanine. The module's
positive analog rail regulates down from the +5V already there.**

- A second LMR33630, wired as an inverting buck-boost: its GND pin sits on the
  negative output, so it sees VIN + |VOUT| = 18 V against a 36 V rating.
  Feedback is referenced to the device's own ground, so the divider runs from
  system ground down to the rail: 1.0 V × (1 + 124k/24.9k) = 5.98 V.
- **Two mezzanine pins**, taken from the ground allocation. All 80 were
  assigned, 37 of them ground for 28 switching lines; 35 remain.
- The module's LT3094 takes the −6 V and makes −5 V at the point of load, where
  its rejection is what the design leans on.
- An LT3045 takes the header's 5 V to **+4.53 V** for the op amp positive rail.

**The LTC3265 is deleted**, with two flying capacitors, two ADJ dividers, two
reference bypasses and their bulk — sixteen parts. **The analog board now
contains no switching converter of any kind**, which is the property this option
was chosen for.

## Consequences

**The 2.1 dB is recovered.** The difference network is 200 Ω, with 3.9 nF
holding pole three at 204 kHz where 1.3 nF across 604 Ω had it at 203.

**Counted rather than estimated.** The module falls from 128 parts to 112, and
from 238 mA of +5V to 123 mA of +5V plus 64 mA of −6V. Input current at the jack
*falls* from 236 mA to 219 even though a rail was added, because the doubling
overhead was larger than the rail it was making.

**`MUTE_N` now gates the two analog regulators** through their enables rather
than the pump's, so the contract in parts-notes.md holds unchanged. Its
justification did change: 0009 needed the stage held off to fit one unit load
before enumeration and 0014 retired that rule, so only the audio reason remains
— the element lines are undefined until the FPGA configures and the jack has no
DC blocking. That makes it a decision about audio rather than a requirement, and
it is open.

**The mezzanine contract changed**, so `hardware/interface.md` moved with it.

**Two faults were introduced by this change and found by review**, both recorded
because they are the same species — a constant left behind beside a changed
circuit:

- The op amp positive regulator kept the SET resistor that suited the pump's
  5.69 V, programming 4.99 V from a 5.02 V input: 30 mV against a 260 mV
  dropout. It is 45.3 kΩ and 4.53 V now. `verify_power.py` had been checking
  one regulator out of six, the one with 1.7 V of headroom, so nothing caught
  it; it now reads all six from the netlists.
- The inverter's power-good pin and its pull-up landed on separate single-node
  nets, because `Net("PG_N6V")` was called twice and SKiDL creates a new net per
  call. That mattered more than the buck's identical fault: U7's GND *is* the
  negative rail, so 100 kΩ to system ground is a pull-up relative to the device
  and the only way that flag can be read.

## What this does not do

**The isolator is still not fitted.** The ADuM4165/4166 and dropping the
SuperSpeed pairs remain 0014's unfinished half.

**It does not touch the reference-rail risk.** That is transition current into
rail impedance and is indifferent to where the rail's power comes from. It
remains the project's lead open item.

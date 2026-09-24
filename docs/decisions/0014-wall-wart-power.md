# 0014 — External 12 V supply, USB for data only

**Status:** accepted. Supersedes [0009](0009-usb-bus-power.md). Amends
[0005](0005-ft601q-bridge-io-voltage.md) and
[0012](0012-module-clock-architecture.md).

## Context

0009 chose USB bus power and argued it well: one cable, and the analog rails
regulated hard enough that the bus's noise never reached the signal. That
argument still holds. What changed is not the noise, it is the budget.

By the time every part was chosen and costed against its datasheet rather than
estimated, the board drew **472 mA**. Against a configured USB 3.0 host's
900 mA that is comfortable. Against a 500 mA USB 2.0 host it is **94 %**, at
full scale, with the fixed part of the load already counted. Everything after
that point was being designed against a ceiling:

- the difference network went to 604 Ω rather than 200 Ω, costing **2.1 dB** of
  stage noise, because the negative rail is paid for twice at a doubler's input;
- `MUTE_N` had to gate the analog supplies so the board could stay inside
  150 mA before enumeration;
- the LTM4622's core rail was gated through an inverting NMOS off `WAKEUP_N`,
  which means "bus not suspended" rather than "enumeration complete" and
  releases earlier than the one-unit-load rule strictly wants;
- the charge pump ran from a rail whose worst case, 4.43 V, is below its own
  4.5 V minimum.

None of those is a mistake. They are all correct answers to a constraint that
the design does not have to accept.

## Decision

**Power comes from an external 12 V supply. USB carries data only.**

A 2.1 × 5.5 mm barrel jack, centre positive, feeds a resettable fuse, a series
Schottky for reverse polarity, and a 15 V TVS. An LMR33630 takes 12 V to 5 V,
and **everything downstream of +5V is unchanged** — the LTM4622, the LT3045 and
the mezzanine all see the rail they were designed against. That is deliberate:
the point of this change is to remove a constraint, not to revisit work that
was done correctly under it.

The USB connector's `VBUS` now reaches exactly one pin, the bridge's own sense
input. It is no longer a supply.

### Why 12 V and not 5 V

5 V would have removed the budget and nothing else. 12 V additionally allows
the negative analog rail to be made by **inversion from a real supply** rather
than by inverting an already-doubled 5 V, which is what makes the 604 Ω
compromise unnecessary. That second stage is not built yet — see "What this
does not yet do".

### Why a Schottky rather than a P-channel MOSFET

The FET is the better part on a 5 V rail, where 0.35 V of drop is 7 % of the
supply. At 12 V it is 3 %, costing about 210 mW against a supply with a volt to
spare before the buck cares. What the diode buys for that is the absence of a
gate: no Vgs rating to check against the input voltage, no gate clamp to size,
and no body-diode conduction path in the reversed case. The simpler part is the
right one here, and it would not be at 5 V.

## Consequences

**Retired.** The 472 mA against 500 mA margin; the 150 mA one-unit-load rule and
everything shaped by it; the 4.43 V worst case on `VIN_P`; `MUTE_N`'s
pre-enumeration role; the LTM4622 run-pin gating and its `WAKEUP_N` NMOS.

**Recoverable, once the module follows.** 2.1 dB, by returning the difference
network to 200 Ω.

**And a second 1.1 dB nobody was looking for.** `analog.txt` Q1c measures the
noise-optimal element resistor at **2585 Ω**, giving 133.5 dB, and records
3.32 kΩ as costing 1.1 dB against it. One of the three reasons given for
choosing 3.32 kΩ is that "the whole board has to fit one unit load before
enumeration with the flip-flops in an undefined state. That needs R ⩾ 3312 Ω."
**That constraint is gone.** The other two reasons both argue *downward* — the
optimum is at 2585 Ω and everything past 3 kΩ buys resistor noise for less
current — so nothing now holds the element above the optimum. It costs about
4 mA of extra element current, which was the entire objection and is no longer
a budget anyone is defending.

Not acted on here, because `analog.py` prices four amplifiers where the board
has six, so the model that would size it is measuring a circuit that was not
built. Fix that first, then re-run the element sweep.

**New obligations.** A switching wall wart is now the primary noise source
where `VBUS` used to be, and it arrives through a connector a person can plug
anything into — hence the TVS, sized for the 19 V laptop bricks that share this
barrel. Supply ground's relationship to chassis is undecided.

**`+12V`, `VIN_RAW` and `VIN_FUSED` are declared in `hv_rails`.** The
overvoltage assertion is blind to any rail it is not told about: an undeclared
rail reaching a protected pin passes silently. This is recorded here because it
is the mechanism by which a new supply enters a design unguarded, and it was
found by testing the check rather than by reading it.

### USB 2.0 High Speed, not SuperSpeed

Isolating the data link is now practical, since the host no longer powers the
board — and it is worth doing, because it breaks the host's ground rather than
merely filtering it. **No galvanic isolator exists for 5 Gbps SuperSpeed.** The
ADuM4165/4166 tops out at USB 2.0 High Speed, 480 Mbps.

That costs nothing. 192 kHz / 24-bit stereo is 9.216 Mbit/s, **1.9 %** of High
Speed. The FT601Q supports High Speed natively, so 0005's choice of bridge is
unaffected and the SuperSpeed pairs simply go unrouted — which also removes the
hardest constraint in the main board's layout, two 5 Gbps impedance-controlled
differential pairs.

## What this does not yet do

Stated plainly, because a half-implemented power change is worse than either
end of it:

- **The module is untouched.** The mezzanine still carries +5V, the LTC3265
  charge pump is still fitted, and the difference network is still 604 Ω. The
  2.1 dB is recoverable but not recovered.
- **The isolator is not fitted.** The SuperSpeed pairs are still routed and the
  ADuM4166 is not in the netlist.
- **Neither board's `power.md` reflects any of this.** Both were already
  describing superseded netlists before this change.

The natural next step is to carry a negative rail across the mezzanine from the
main board, where 12 V makes it cheap, and delete the charge pump entirely.
That changes the mezzanine contract in `interface.md` and deserves its own
pass.

# lyrebird-main-reva — power

Bus powered, no external input
([0009](../../docs/decisions/0009-usb-bus-power.md)). This page shows the
arithmetic behind every number rather than quoting a total. The output
module's half is [../lyrebird-dac-reva/power.md](../lyrebird-dac-reva/power.md)
and the two have to agree.

**Provenance is marked on every figure**: *datasheet typical*, *calculation*,
or *estimate*. `hardware/datasheets/` is empty, so nothing here was re-read
from a vendor PDF; the two datasheet figures reach this page through decision
records that cite them, and are marked as such.

## Where the boundary sits

**The boundary is the +5 V pins of the mezzanine header**, J2 pins 71, 73, 75,
77 and 79 in `lyrebird-main.net`, downstream of the VBUS ferrite named in
[0009](../../docs/decisions/0009-usb-bus-power.md).

Everything upstream of those pins is budgeted here. Everything downstream is
budgeted in the module's `power.md` and enters this page as one line. The
header carries **unregulated bus voltage and ground, and no other rail** — not
2.5 V, not 3.3 V ([interface.md](../interface.md)). The 3.3 V, 2.5 V and 1.0 V
rails generated on this board stay on this board; the module regulates its own
from the +5 V it is handed.

That matters for one thing beyond arithmetic. `hardware/README.md` lists
"mezzanine logic" against the 2.5 V rail. That means the FPGA's own drivers
into the header, which sit on the bank supplies. No 2.5 V supply crosses the
connector, and the module's translator needs one — taken up on the module side.

## The rails

| Rail | V | Source | Feeds | At the rail | From 12 V |
| --- | --- | --- | --- | --- | --- |
| +12V | 11.4–12.6 | barrel jack, via F1, D1 | LMR33630 ×2 | — | 219 mA |
| +5V | 5.02 | LMR33630, U5 | LT3045 in, LTM4622 in, mezzanine | 357 mA | see above |
| −6V_A | −5.98 | LMR33630, U7, inverting | mezzanine, for the module's LT3094 | 64 mA | see above |
| +3V3 | 3.32 | LT3045, U3 | FT601Q `VCC33` ×3, `VDDA` | 185 mA | 187 mA of +5V |
| +2V5 | 2.5 | LTM4622 ch 1 | FT601Q `VCCIO` ×4, 9 GateMate bank supplies, `VDD_CLK` | 15 mA | 9 mA of +5V |
| +1V0 | 1.0 | LTM4622 ch 2 | GateMate `VDD` ×28, `VDD_PLL`, `VDD_SER` ×2, `VDD_SER_PLL` | 149 mA | 35 mA of +5V |

Pin counts are read out of `lyrebird-main.net`, not assumed.

`AVDD` is **not** on +3V3. It is a 1.0 V PLL supply with a 1.4 V absolute
maximum, fed from the bridge's own internal regulator through `+1V0_FT`. This
page said otherwise for some time; putting a 3.3 V rail on it destroys the
part, and that is why `hardware/check_freshness.py` now exists.

### 12 V input

A 2.1 × 5.5 mm barrel jack, centre positive, feeding a resettable fuse, a
series Schottky for reverse polarity, a Schottky clamp and an 18 V TVS
(0014). The adapter is not chosen, so its tolerance is assumed at ±5 %.

Every part of the chain is sized in `hardware/verify_power.py`, which runs the
arithmetic rather than asserting it, and exercised in
`hardware/sim/power_input_transient.py`, which covers inrush, reverse polarity,
the wrong adapter and the order the rails arrive in. Both are tamper-tested.
The summary:

    input           11.4 to 12.6 V, 219 mA worst case, 2.42 W
    losses          245 mW  (77 mW diode, 177 mW buck, 68 mW inverter)
    buck junction   about 33 C at 25 C ambient
    inrush          7.1 to 23.0 A over 24 parasitic corners, 0.35-1.12 mJ
                    against 6.3 J to trip F1

**F1 is a 1812L050/30**, and the three constraints that picked it are worth
keeping together: 30 Vdc clears the TVS clamping at 29.2 V, 100 A of Imax
clears the inrush, and 0.50 A of hold derates to 0.33 A at 70 °C — still above
the 219 mA drawn. The obvious smaller part, 1812L035/30, derates to 0.20 A at
70 °C, *below* the board's own draw, and would nuisance-trip in a warm
enclosure.

**Reverse polarity is held by D3, not by D1 alone.** D1 blocks, but its own
leakage then drags the protected node negative and something has to stop it.
D2's forward drop got it to −0.399 V against the converter's −0.3 V minimum;
the BAT54 at D3 holds −0.233 V, and it holds the same value at 12, 19 and 24 V
reversed because the clamp sets the level and the adapter does not.

**A 19 V laptop brick fits this barrel and the board simply runs on it.** The
LMR33630 is a 36 V part. An SMAJ15A was fitted first and conducted there
indefinitely — 41 mA at a junction near 117 °C, without ever tripping the fuse,
because a TVS breakdown has a positive tempco and the fault settles rather than
running away. The 18 V part does not conduct at 19 V at all.

## Totals at the input

| Item | Current | Provenance |
| --- | --- | --- |
| Bridge 3.3 V, High Speed, through the LT3045 | 187 mA of +5V | datasheet typical + estimate |
| FPGA core 1.0 V, through the buck | 35 mA of +5V | estimate |
| Bridge I/O and FPGA banks 2.5 V, through the buck | 9 mA of +5V | calculation |
| LTM4622 quiescent, both channels | 3 mA of +5V | estimate |
| **Main board subtotal** | **234 mA of +5V** | |
| Output module, +5V across the mezzanine | 123 mA of +5V | see the module's power.md |
| **+5V total** | **357 mA** | |
| Output module, −6V across the mezzanine | 64 mA of −6V | see the module's power.md |
| **At the jack** | **219 mA at 12 V, 2.42 W** | verify_power.py |

The input current is *lower* than the 236 mA the same board drew before the
module's charge pump was deleted, even though a rail was added. The doubling
overhead was larger than the rail it was making.

Series losses were checked rather than assumed: the fuse at its 1.0 Ω R1max
drops 219 mV at full load and the Schottky 350 mV, so the buck sees 10.83 V at
the bottom of the adapter range against the 5 V it makes. Five parallel header
contacts at 20 mΩ drop 2 mV at 123 mA.

## Margin

| Against | Limit | Drawn | Spare |
| --- | --- | --- | --- |
| A 12 V, 1 A adapter | 1000 mA | 219 mA | 781 mA |
| F1 hold at 70 °C | 330 mA | 219 mA | 111 mA |
| LMR33630 output, +5V | 3000 mA | 357 mA | 2643 mA |

**There is no USB current budget any more.** The figures this section used to
carry — 381 mA against 500, 76 % of a USB 2.0 host — belonged to a bus-powered
board and are retired with 0009. The board no longer negotiates for current and
the descriptor no longer has to declare it.

## Before enumeration — retired

This section used to size the board against a device drawing one unit load
until the host configures it: 150 mA on a USB 3.0 port, 100 mA on USB 2.0. 0009
answered it by gating the FPGA rails with the LTM4622 run pins.

**All of it is retired.** 0014 replaced bus power with a 12 V supply, so no
part of either board waits on enumeration for current, and every rail comes up
when the adapter is plugged in.

The gating is worth a paragraph of its own, because deleting it turned out to
matter more than adding it ever did. `RUN2` was pulled down by an NMOS driven
from the bridge's `WAKEUP_N`, which is asserted whenever the FT601Q is not
seeing bus
activity — including with no cable in the socket at all. On an externally
powered board that is always, so **the FPGA core rail never came up**. A
transient found worse: `CORE_RUN` reached its pull-up before the NMOS gate
crossed threshold, so channel 2 soft-started into a 1.2 ms window and was
killed mid-ramp, `+1V0` reaching about 319 mV and collapsing on every power-up
whether a host was present or not.

Both RUN pins are tied on now. The lesson is in
`hardware/sim/power_input_transient.py`: a netlist review could not have found
this, because every net was connected exactly as intended.

## Against 0009's budget

Checked line by line rather than copied. The totals agree to 1 mA, which is
partly coincidence — four lines moved and they cancelled.

| Line | 0009 | Here | Difference |
| --- | --- | --- | --- |
| Bridge 3.3 V | 185 | 187 | LDO ground-pin current added |
| FPGA core | 35 | 35 | taken as given |
| Bridge I/O and FPGA banks | 20 | 9 | built up from switched capacitance |
| Element reference rail | 25 | 56 | 25 mA implies a 3.1 kΩ element; the netlist says 1 kΩ |
| Oscillator | 30 | 40 | the fanout divider was never costed |
| Op amp stage and charge pump | 65 | 51 | four amplifiers and an 85 % pump |
| Regulator quiescent and margin | 20 | 3 | quiescent only; margin sits in the lines |
| **Total** | **380** | **381** | |

## What has no source today

**The 1.0 V and 2.5 V rails have no supply.** The LTM4622 selected in 0009 is
not in `main_board.py`, so both rails exist in the netlist as nets with loads
and no regulator. It is also absent from the stock KiCad libraries, so it needs
a symbol before it can be wired. Until then the FPGA cannot be powered and none
of the 1.0 V or 2.5 V arithmetic above can be measured.

The VBUS ferrite is likewise named in 0009 and absent, and there is no USB
connector, so the 5 V input has no entry point either. The rails that do exist
— 5 V passthrough and 3.3 V — are wired.

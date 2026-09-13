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

| Rail | V | Source | Feeds | At the rail | From 5 V |
| --- | --- | --- | --- | --- | --- |
| +5V | 4.45–5.25 | USB VBUS | LT3045 in, LTM4622 in, mezzanine | — | 381 mA |
| +3V3 | 3.3 | LT3045, U3 | FT601Q `VCC33` ×3, `VDDA`, `AVDD` | 185 mA | 187 mA |
| +2V5 | 2.5 | LTM4622 ch 1 | FT601Q `VCCIO` ×4, 9 GateMate bank supplies, `VDD_CLK` | 15 mA | 9 mA |
| +1V0 | 1.0 | LTM4622 ch 2 | GateMate `VDD` ×28, `VDD_PLL`, `VDD_SER` ×2, `VDD_SER_PLL` | 149 mA | 35 mA |

Pin counts are read out of `lyrebird-main.net`, not assumed.

### +5 V input

USB 3.0 guarantees 4.45 V at the device and the specification's upper limit is
5.25 V (*via 0009*; the 5.25 V figure is the USB limit). The LTM4622's 3.6 V
minimum input sits comfortably below the guarantee.

The 5 V net in the netlist has **no bulk or bypass capacitance and no ferrite**
— zero capacitors on `+5V` against 80 elsewhere on the board.

### +3.3 V, LT3045

Load is the FT601Q in active SuperSpeed: **185 mA** (*datasheet typical, via
[0009](../../docs/decisions/0009-usb-bus-power.md)*).

An LDO is a series pass element, so its input current is its output current
plus its own ground-pin current — no reflection ratio applies:

```
I(5V) = 185 mA + I_GND
I_GND = 2 mA                        (estimate; confirm against the datasheet)
I(5V) = 187 mA
```

Dissipation, which drives the thermal-via note in 0009:

```
P = (5.00 - 3.30) x 0.185 = 315 mW        nominal          (calculation)
P = (5.25 - 3.30) x 0.185 = 361 mW        at the USB max   (calculation)
```

0009 says "roughly 400 mW". That is conservative by 11 % against the worst
case, so its guidance stands unchanged.

Note that the FT601Q's own core runs from an internal 1.0 V regulator off
`VCC33`; its current is already inside the 185 mA. Its `VD10`/`DV10` pins are
unconnected in the netlist, so that regulator has no decoupling today.

### +2.5 V, LTM4622 channel 1

No datasheet figure covers this rail, because it is set by what the board
switches. Built from CMOS dynamic current, `I = C x V x f`, where `f` is full
cycles per second:

**Element lines**, 28 driven, each loaded by the FPGA pad, a mezzanine trace, a
connector contact and a register input. `C = 10 pF` (*estimate*). Dynamic
element matching changes a given line on roughly half of element clocks, so
`f = 24.576 MHz / 2 = 12.29 MHz` (*estimate*):

```
10 pF x 2.5 V x 12.29 MHz = 307 uA per line
307 uA x 28               = 8.6 mA                        (calculation)
```

**FIFO clock**, one line, free-running at 66.67 MHz, short on-board trace,
`C = 5 pF` (*estimate*). Sourced by the FT601Q from `VCCIO`:

```
5 pF x 2.5 V x 66.67 MHz  = 0.83 mA                       (calculation)
```

**FIFO data**, 36 lines (`DATA[31:0]` plus `BE[3:0]`). Two channels of 32-bit
padded samples at 192 kHz is 1.536 MB/s against 266.7 MB/s of bus capacity at
66.67 MHz by 4 bytes, a duty of 0.58 %, and lines toggle on about half of the
active clocks:

```
f_eff = 66.67 MHz x 0.5 x 0.0058 = 193 kHz
5 pF x 2.5 V x 193 kHz x 36      = 0.09 mA                (calculation)
```

**Handshakes and leakage.** Four FPGA-driven control lines are effectively
static, under 0.1 mA. Static and leakage current across nine bank supplies and
four `VCCIO` pins: **5 mA** (*estimate*, and the least supported term here).

```
8.6 + 0.83 + 0.09 + 0.1 + 5 = 14.6 mA, call it 15 mA
```

Reflected through the buck at 85 % (*estimate*):

```
I(5V) = 2.5 V x 15 mA / (5.0 V x 0.85) = 8.8 mA, call it 9 mA
```

15 mA is 0.75 % of the LTM4622's 2 A channel rating, where efficiency is well
below the headline figure. At 50 % it would cost 15 mA from 5 V instead of 9.
Neither number changes any conclusion below.

### +1.0 V, LTM4622 channel 2

**This is the weakest number in the budget.** 0009 allows 35 mA from 5 V.
Reflected back to the rail at the same 85 %:

```
I(rail) = 5.0 V x 35 mA x 0.85 / 1.0 V = 149 mA           (calculation)
```

149 mA at 1.0 V in economy mode is an *estimate* with no datasheet behind it.
It is almost entirely static current: the design places under 3 multipliers at
the element clock and 62 coefficient words
([model](../../model/README.md)), 25 of 32 block RAMs
([0011](../../docs/decisions/0011-pack-three-samples-per-fifo-word.md)), and
the two modules built so far sit under 1 % of the fabric
([0013](../../docs/decisions/0013-simulation-and-build-toolchain.md)). Dynamic
current on a design that small, clocked at 24.576 and 66.67 MHz, is small
against the part's quiescent draw. Read the economy-mode figure off the Cologne
Chip datasheet, or measure it, before trusting this line.

## Totals at the USB input

| Item | From 5 V | Provenance |
| --- | --- | --- |
| Bridge 3.3 V, active SuperSpeed, through the LT3045 | 187 mA | datasheet typical + estimate |
| FPGA core 1.0 V, through the buck | 35 mA | estimate |
| Bridge I/O and FPGA banks 2.5 V, through the buck | 9 mA | calculation |
| LTM4622 quiescent, both channels | 3 mA | estimate |
| **Main board subtotal** | **234 mA** | |
| Output module, all rails, across the mezzanine | 147 mA | see the module's power.md |
| **Total** | **381 mA** | |

Series losses between the connector and the module are negligible and were
checked rather than assumed: a ferrite at 50 mΩ DCR drops 19 mV at 381 mA, and
five parallel header contacts at 20 mΩ drop 0.6 mV at 147 mA (*estimates* for
both resistances, *calculation* for the drops). At the 4.45 V guarantee the
module's LT3045s still see 4.43 V against a 3.3 V output.

## Margin

| Against | Limit | Drawn | Spare | Utilisation |
| --- | --- | --- | --- | --- |
| USB 3.0, configured | 900 mA | 381 mA | 519 mA | 42 % |
| USB 2.0 host | 500 mA | 381 mA | 119 mA | 76 % |

The 381 mA is the SuperSpeed figure, so it bounds the USB 2.0 case from above:
falling back to High Speed lowers the bridge's own draw, by an amount 0009 does
not quantify and neither does this page.

**Declare 900 mA in the descriptor** regardless of the module fitted. Current
is fixed at enumeration and cannot be renegotiated when a module is swapped
(0009).

## Before enumeration, and what does not fit

A device may draw one unit load before it is configured: **150 mA on a USB 3.0
port, 100 mA on USB 2.0**. 0009 answers this by gating the FPGA rails with the
LTM4622 run pins. That is necessary and it is not sufficient, because **the
module's rails are not gated**: they take VBUS at the header and its three
LT3045s have their `EN/UV` pins unconnected in the netlist.

With the FPGA rails held off and the bridge idling near 70 mA (*via 0009*):

```
bridge idle 70 mA + LT3045 ground pin 2 mA        =  72 mA
module clock rail, oscillator already running     =  40 mA
module element reference, 14 elements high at 1k  =  56 mA
                                                     ------
                                                     168 mA   over 150 mA
```

The element reference term is what decides this, and it is set by a resistor
value nobody has chosen. The same sum at other values:

| Element resistor | Reference rail | Pre-enumeration total | Against 150 mA |
| --- | --- | --- | --- |
| 1 kΩ, the netlist placeholder | 56 mA | 168 mA | over by 18 mA |
| 2 kΩ | 33 mA | 145 mA | 5 mA spare |
| 3.1 kΩ, what 0009's 25 mA line implies | 25 mA | 137 mA | 13 mA spare |

With the flip-flop state undefined at power-on, all 28 elements high at 1 kΩ
gives 214 mA, and adding 0009's op amp stage and charge pump — 51 mA, not in
the netlist — puts every case over.

**On a USB 2.0 host nothing fits at any element value.** The bridge alone takes
72 mA of a 100 mA allowance, and the module's clock rail is 40 mA on its own.

So the honest statement is that the enumeration gating in 0009 covers half the
board. Either the module's rails gate too, or the element outputs are held low
until the FPGA is configured. Both are design questions, and this page only
records that the arithmetic requires one of them.

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

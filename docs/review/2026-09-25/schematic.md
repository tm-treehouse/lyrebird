# Schematic review — both boards as circuits

**Date** 2026-09-25/26 · **Scope** `hardware/netlist/*.py` as generators, the two
generated netlists, the custom symbols and footprints, and whether the exported
sheets represent the netlists. No PCB layout exists on either board, so nothing
here is a layout finding except where it is labelled as one.

Both netlists were regenerated before anything was judged:

```
export KICAD10_SYMBOL_DIR="/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
./.venv/bin/python hardware/netlist/main_board.py   # 159 parts, 142 nets, 0 errors
./.venv/bin/python hardware/netlist/output_module.py # 112 parts, 133 nets, 0 errors
```

Every assertion below that says "fault" was produced by regenerating, injecting
and observing. Where I could not get to a datasheet I say so rather than
reasoning from memory.

---

## 0. Two methodological notes for whoever reviews this next

**SKiDL's circuit is global.** `builtins.default_circuit` accumulates across
`build()` calls in one process. My first tamper harness built eight cases in a
single interpreter; the second board's `J1` became `J1_1`, its `GND` became
`GND1`, and because the exemption list in `assert_below_abs_max` is the literal
string `"GND"`, the renamed ground stopped being exempt, high voltage propagated
into it, and the *unmodified* output module "failed" with 42 protected pins on
`GND1`. Every injected fault in that run also silently landed on a duplicate
part rather than the one I was probing. **One process per case** is the only
safe harness. This is almost certainly the mechanism behind at least some of the
three earlier tamper attempts that produced confident wrong answers: a pin that
is already tied being tied again in the same accumulated build looks like a
fault that is not there, and an injection that lands on a shadow copy of the
part looks like a gap that is not there either.

The harness that produced the results in §1 is therefore: copy the three
generator files to a scratch directory, apply exactly one literal substitution
(asserting the anchor matches exactly once), run `build()` in a fresh
interpreter, and **probe the fully built circuit from inside a wrapper around
`assert_below_abs_max`** so that the net actually sitting on the injected pin is
printed whether or not the assertion fires. Every result below shows that
probe. A case whose probe does not show the injection is not evidence.

**The generated netlist carries no pin names or pin functions.** `(node)`
entries have `(ref)`, `(pin N)` and `(pintype)` only — no `pinfunction`, and
there is no `(libparts)` section at all. Any analysis that needs pin *names*
must take them from the symbol through SKiDL, not from the `.net` text. A
reader that keys on pin names finds zero matches and whatever it feeds passes
while checking nothing.

---

## 1. Electrical faults, and what `assert_below_abs_max` actually covers

### 1.1 Confirmed fault: both power-good pull-ups are connected to nothing

`main_board.py` builds the two LMR33630 power-good nets like this:

```python
buck5["PG"] += Net("PG_5V")
pullup(Net("PG_5V"), v["+5V"], "100k")
...
inv["PG"] += Net("PG_N6V")
resistor(Net("PG_N6V"), v["GND"], "100k")
```

`Net("PG_5V")` is called twice, and SKiDL creates a *new* net each time and
uniquifies the name. The generated netlist contains four single-node nets:

```
PG_5V   : [('U5','4','OPEN-COLLECTOR')]     <- the buck's PG pin, alone
PG_5V1  : [('R1','1','PASSIVE')]            <- the 100k pull-up, other end open
PG_N6V  : [('U7','4','OPEN-COLLECTOR')]     <- the inverter's PG pin, alone
PG_N6V1 : [('R4','1','PASSIVE')]            <- the 100k, other end open
```

These are the **only** four single-node nets on the main board, and they are the
only two `Net("literal")` strings in either generator that appear in more than
one `Net(...)` call — so the defect is exactly two instances of one idiom, not a
pattern. Everywhere else the code does `n = Net(...)` once and reuses the
variable, which is correct.

Consequences, in order of seriousness:

- R1 and R4 are placed with one lead floating. On the main board's own terms
  these resistors do nothing.
- Both PG outputs are open-drain with no pull-up, so both read as a permanent
  low regardless of rail state. The comment calls them "test points, not
  logic", which limits the damage to a test point that always reads fail.
- The inverter's pull-down-to-system-ground on `PG_N6V` was the interesting
  half: U7's GND *is* `-6V_A`, so 100 k to system ground is a pull-**up**
  relative to the device, and that is the only way to read that flag at all.
  It is not connected.
- KiCad ERC will report four unconnected-pin errors on import, which is how this
  would eventually have been found.

This is a two-line fix in the generator and I have not made it (read-only).

### 1.2 What the overvoltage assertion covers, tested rather than read

Sixteen cases, one process each, injection verified in every case. `hv_rails`
as declared by each board is printed by the harness so there is no doubt which
list was in force.

| # | Injected | Board | Result |
| --- | --- | --- | --- |
| T0a | nothing (baseline) | main | passes |
| T0b | nothing (baseline) | module | passes |
| T1 | `+3V3` straight onto free ball IO_EB_B8 | main | **fires** |
| T2 | 10 k pull-up to `+3V3` on the same ball, 2-pin `Device:R` | main | **fires** |
| T3 | same pull-up through one leg of a `Device:R_Pack04` array | main | passes — **gap** |
| T4 | `VDD`/`VDD_PLL`/`VDD_SER`/`VDD_SER_PLL` moved to `+3V3` | main | passes — **gap** |
| T5 | new undeclared 3.3 V rail from a second LT3045 onto a free ball | main | passes — **gap** |
| T6 | `+12V` onto a free ball through a 2-pin inductor | main | **fires** |
| T7 | nothing changed except adding `-6V_A` to the module's `hv_rails` | module | **fires** on J1.71/72 |
| T8 | `-6V_A` shorted onto the `ID1` header signal | module | passes — **gap** |
| T8b | the same short with `-6V_A` declared | module | **fires** on all three pins |
| T9 | module's "2.5 V" LT3045 `R_SET` changed 24.9 k → 33.2 k (rail becomes 3.32 V) | module | passes — **gap** |
| T10 | 3.3 V element clock straight to `MCLK`, bypassing the translator | module | **fires** |
| T11 | 100 k pull-up from a header signal to `+3V3_REF` | module | **fires** |
| T12 | spare 3.3 V register output `1Q8` onto `ID1` | module | **fires** |
| T13 | element summing node `SUM_LP` onto `ID1` | module | **fires** |
| T14 | declared `-5V_A` op-amp rail onto `ID1` | module | **fires** |
| T16 | element mid-node `ELEM_MID27` onto `ID1` | module | passes — **gap** |

T13 deserves a note because I predicted it would pass and it did not. `SUM_LP`
is reached from the register outputs only through `R_Pack04` arrays, so I
expected the array gap to hide it — but the 2.0 nF transimpedance feedback
capacitor is a two-terminal part with its other leg on the op-amp *output*, and
the passive-propagation clause walks through it. The check is stronger than the
array gap alone suggests, and a prediction is not a result.

The five real gaps, in the order they matter:

**(a) The 1.20 V core absolute maximum is not guarded at all — and the rail
that could violate it is already on the board, one resistor away.** This is the
worst of the five and it is worth the extra cases. DS1001 Table 4.1 gives two
absolute maxima: `VDDIO` 2.75 V (GPIO banks and `VDD_CLK`) and `VDDcore` 1.20 V
(`VDD`, `VDD_PLL`, `VDD_SER`, `VDD_SER_PLL`). `assert_below_abs_max` has one
constant, `ABS_MAX_V = 2.75`, and it skips every pin that is `PWRIN`/`PWROUT`
or whose name matches `_SUPPLY_NAME` — which is every core ball. Four
injections, each verified to land:

| # | Injected | Result |
| --- | --- | --- |
| T4 | core rail moved to `+3V3` (28 `VDD` + `VDD_PLL` + 2× `VDD_SER` + `VDD_SER_PLL` at 3.32 V) | passes |
| T4b | core rail moved to the board's **own `+2V5`** | passes |
| T4c | one 10 k resistor from `+2V5` to a single core `VDD` ball | passes |
| T4d | dead short, `+2V5` onto one core `VDD` ball (net becomes `+1V0/+2V5`) | passes |
| T4e | T4c **plus** `+2V5` added to `hv_rails` | fires — on 134 **legitimate** pins, and **not** on the core ball |

T4c and T4d are the cases that matter: 2.5 V is on the same board, one net away,
and both a resistor bridge and a dead short onto a 1.20 V ball build clean.
T4d's net carries both names, `+1V0` and `+2V5`, and still passes, because
`+2V5` is below the single threshold and so is not in `hv_rails`.

T4e shows why this is not fixable by declaring `+2V5`. Doing so makes the whole
2.5 V logic domain "high voltage": 134 protected pins are reported, 96 on the
FPGA and 38 on the mezzanine, every one of them a legitimate 2.5 V signal — and
the core ball that actually has 2.5 V on it is **still not among them**, because
the supply-pin skip means it is never examined. A single threshold cannot
express two limits for two pin classes. Guarding the core rail needs a different
check: an explicit rail-to-pin-class map (which nets may touch `VDD*` versus
`VDD_<bank>` versus signals), not another entry in a flat list.

T15 confirms the same blindness from the value side: swapping the LTM4622's two
feedback resistors — which the generator's own comment identifies as "the worst
single assembly error on this board", because 19.1 k on FB2 puts 2.5 V onto
`+1V0` and "kills the FPGA on first power-up" — builds clean. The mitigation the
generator does fit is real and good (the core resistor is deliberately 0603 so
it cannot be placed on the 0402 land), but it is a process control, not a check.

Nothing else covers it. `hardware/verify_power.py` carries `V_1V0 = Fact(1.00,
"V", DS, "LTM4622 table value 90.9 k")` as a hand-written constant, so changing
the netlist's resistor does not change its verdict — which is the one thing that
file's docstring says it exists to prevent ("so that changing a component value
changes the verdict instead of only the prose"). Its LDO reading by pin number
is new and does close part of this for the linear regulators; the LTM4622's two
feedback resistors are still constants.

**(b) The propagation clause only walks two-terminal parts (T3, T16).** The
passive step requires `len(pins) != 2: continue`. A pull-up built from a
`Device:R_Pack04` — the part type the output module uses for *every* element
resistor, both transimpedance networks and both difference networks — is
invisible. T16 shows this on the real board rather than a synthetic injection:
`ELEM_MID27`, whose only paths to the 3.3 V register outputs run through two
arrays, can be wired to a header signal that reaches a GateMate ball and the
build passes.

**(c) The check is membership-based on rail *names*, and the module's list is
missing `-6V_A` (T7, T8).** The main board declares it, with a comment
explaining exactly why ("a negative rail on a GateMate ball is as fatal as a
high one, and this check is the only thing looking"). The output module does
not. T7 proves the omission is load-bearing rather than cosmetic: adding
`-6V_A` to the module's `hv_rails` and changing nothing else makes the
*existing, unmodified* design fail, because `protected={mez: {"+5V"}}` on the
module does not allow `-6V_A` the way the main board's
`{mez: {"+5V", "-6V_A"}}` does. So the two boards disagree twice about the same
connector: on which rails are high, and on which the header may carry. T8 shows
the cost — the negative rail shorted onto `ID1`, a net that runs across the
connector to a GateMate ball whose input minimum is −0.4 V, builds clean.

The module's list also still contains four nets that no longer exist anywhere
in the design: `PUMP_P`, `PUMP_N`, `+5V7_A`, `-5V7_A`, left from the deleted
charge pump. Harmless, but it is the same list that is missing a rail that does
exist.

**(d) A regulator output is a new domain the check cannot see (T5).**
`Pin.types.PWROUT` is excluded from `_DRIVING` on purpose, so a rail is high
voltage only if its *name* is in `hv_rails`. Adding a second LT3045 at 3.3 V
and running its output to a free FPGA ball builds clean. The docstring says
"the declared rail list is the authority on supply voltages", which is true and
is the whole exposure: adding a regulator without editing the list adds an
unguarded domain.

**(e) The check reads no component values, so it cannot know what a rail's
voltage is (T9, T15).** Changing `R_SET` on the module's 2.5 V LT3045 from
24.9 k to 33.2 k makes `+3V3`-worth of voltage come out of a net still called
`+2V5`, feeding the translator's VCC(A), its `2DIR` strap and the `ID0` strap
that crosses to the FPGA. The build passes. This is the same class as (a): the
assertion checks *topology against a declared voltage map*, and every actual
voltage on both boards is set by a resistor it never reads.

### 1.3 Things the assertion structurally cannot see, confirmed by inspection

These are not gaps in the implementation so much as the boundary of the idea,
and they are worth writing down because two of them are live on this design.

- **Inputs.** `_DRIVING` excludes `Pin.types.INPUT`, which is what lets the 28
  element lines land on 3.3 V register inputs legitimately. The threshold
  question that replaces it is answered in §2.5 and is fine.
- **The real input limit is not 2.75 V.** DS1001 Table 4.1 gives 2.75 V as the
  absolute maximum of `VDDIO` — the *supply*. The input limit is Table 4.5's
  `VIN = −0.4 V to VDDIO + 0.4 V`, i.e. 2.9 V when the bank is at 2.5 V, and it
  moves with the bank supply. The assertion's fixed 2.75 V happens to be
  conservative here, but it is comparing a signal against a supply rating, and
  if a bank were ever run at 1.8 V the correct limit would be 2.2 V and a 2.5 V
  signal would be a violation the check could not express.
- **Off-board drivers.** The JTAG header's 3.3 V FTDI adapter is outside the
  netlist; `main_board.py` says so and fits 1 k series resistors. See §2.2.
- **Straps to rails are seen** (T1 and T2 fire), including negative rails when
  declared (T14).

---
## 2. The custom symbols and footprints

Six symbols and two footprints are hand-drawn. I checked every pin number of
every custom symbol against the manufacturer's own terminal assignment, and both
footprints against the manufacturer's own package drawing.

### 2.1 Confirmed fault: the LTM4622 land pattern is rotated 90° against the package

This is a second instance of the defect already known on the Crystek footprint,
on the only other hand-drawn footprint in the library — so two of two.

**What the datasheet says.** LTM4622 Rev G, PIN CONFIGURATION, LGA package,
TOP VIEW. I read the drawing geometrically rather than as a text dump, by
extracting each text run with its position matrix:

```
 y=468.7 | [133]COMP2 [157]GND [171]SYNC/MODE [190]GND [206]COMP1   <- signal labels
 y=453.7 | [133]5                                                   <- row labels, left edge
 y=438.2 | [133]4
 y=422.8 | [133]3
 y=407.4 | [133]2
 y=391.9 | [133]1
 y=377.1 | [146]A [162]B [178]C [194]D [211]E                       <- column labels, bottom edge
```

So in TOP VIEW the **letters run left to right** (A leftmost) and the **numbers
run bottom to top** (1 at the bottom). Both axes are fixed unambiguously by the
top row of labels: the five signals printed above row 5 are, left to right,
COMP2 / GND / SYNC-MODE / GND / COMP1, and PIN FUNCTIONS gives COMP2 = A5,
B5 = GND, SYNC/MODE = C5, D5 = GND, COMP1 = E5. If the letters ran the other way
that row would read COMP1 first; if the numbers ran the other way the top row
would be row 1, which is VOUT2/VOUT2/GND/VOUT1/VOUT1. Neither is what is
printed. I then checked all twenty-odd remaining labels against the same
hypothesis and every one lands on the right ball.

**What the footprint does.** In
`Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm.kicad_mod`, with KiCad's +Y pointing
down the page:

```
A1 (-2.54,-2.54)  A2 (-1.27,-2.54) ... A5 (+2.54,-2.54)   <- numbers run left to right
B1 (-2.54,-1.27)                                           <- letters run top to bottom
```

The letters and the numbers are on the opposite axes from the datasheet. Working
in top view with x right and y up, the land named `(L,N)` sits where the package
has ball `(letter index 4−w, number index u)` — the package's map rotated by a
quarter turn. Composing the two maps, **24 of the 25 lands carry the wrong ball's
net**; only `C3`/INTVCC at the centre is invariant. The destructive ones:

| Package ball at that spot | its function | Land name there | net the netlist wires to it |
| --- | --- | --- | --- |
| A1, B1 | VOUT2 (the 1.0 V core rail) | E1, E2 | `+2V5`, `+5V` |
| A2, B3 | VIN2 | D1, C2 | `+2V5`, `GND` |
| C1, C2 | GND | E3, D3 | TRACK/SS1 capacitor, `+5V` |
| D1, E1 | VOUT1 (the 2.5 V rail) | E4, E5 | FB1 divider, open |
| E2, D3 | VIN1 | D5, C4 | `GND`, FREQ resistor |
| B5, D5 | GND | A2, A4 | `+5V`, FB2 divider |

On first power-up that is `+5V` shorted to the module's GND balls, `+2V5` driven
into its VOUT2 power stage, and both VIN balls sitting on ground. The part and
very likely the FPGA core rail do not survive it.

**It is a rotation, not a reflection, and that matters.** The linear part of the
index map is `[[0,−1],[1,0]]`, determinant **+1**, so it is a pure 90° rotation.
Rotating the physical part one quarter turn clockwise relative to the footprint's
silkscreen makes all 25 connections correct. So the board is recoverable at
assembly by *ignoring* the pin-1 marker — which is exactly the trap, because the
marker (`fp_circle` at −3.725,−3.725, beside `A1`) says the opposite. Same
character as the known Crystek defect: geometry right, numbering rotated,
silently wrong if trusted.

**The geometry itself is correct.** Datasheet LGA table: D = E = 6.25 mm,
e = 1.27 mm, F = G = 5.08 mm, suggested PCB layout `Øb (25 PLACES)` at radius
0.3175 mm. The footprint has a 6.25 mm body outline, 1.27 mm pitch, 5.08 mm
outer-centre span and 0.635 mm lands. One minor deviation: the lands are drawn
**square** where the suggested layout specifies **round** Ø0.635 — 27 % more
copper and paste per land, which affects self-alignment slightly on a 25-land
module and is worth matching rather than arguing about.

### 2.2 The Crystek CCHD-957 footprint is *not* oversized — settled from Rev N

The documentation review's additional claim that this footprint is drawn twice
the size of the part is **not supported**. Crystek CCHD-957 spec sheet Rev N,
25-Aug-2026, fetched from `crystek.com/Specification/CCHD-957`:

- Body: `0.560 ±0.005 (14.2 ±0.127)` × `0.360 ±0.005 (9.14 ±0.127)` mm, 5.3 mm
  max height.
- The four numbers printed under SUGGESTED PAD LAYOUT are, verbatim:
  `0.280 (7.11)`, `0.050 (1.27)`, `0.090 (2.28)`, `0.200 (5.08)`.

The footprint's body outline is `±7.1, ±4.57` = 14.2 × 9.14 mm, which is the
datasheet body to the tenth of a millimetre. Its pads are `2.28 × 1.27 mm` on
`7.11 × 5.08 mm` centres — the four datasheet numbers used directly. Nothing is
doubled. For completeness, the part's own metallisation in the BOTTOM VIEW is
`0.040 (1.01)` × `0.070 (1.77)` on `0.200 (5.08)` centres, so the suggested land
is 26 % longer and 29 % wider than the part's own pad, which is the normal
fillet allowance and confirms the two sets of numbers are not being confused for
each other.

What I could **not** settle from the text layer is which axis the elongated
2.28 mm dimension runs along, because that is carried by the drawing's geometry
rather than by a label. The footprint runs it along the 14.2 mm axis. Someone
should put eyes on the drawing. The pad *numbering* rotation is the known
defect and I did not re-derive it.

### 2.3 Custom symbol pin numbering, part by part

| Symbol | Checked against | Verdict |
| --- | --- | --- |
| `SN74ALVCH16374` | TI SCES021L, `DGG/DGV/DL` package top view, all 48 pins | **exact match**, pin for pin |
| `LTM4622` | ADI Rev G PIN FUNCTIONS, all 25 balls | **exact match** |
| `CCHD-957` | Crystek Rev N Pad Connection table | **exact match** (1 E/D, 2 GND, 3 OUT, 4 Vcc) |
| `MX25R6435F` | not fetched — see §5 | unverified |
| `SN74LVC1G74` | not fetched — see §5 | unverified |
| `LMK1C1104` | not fetched — see §5 | unverified |
| `LTC3265` | — | dead symbol, see below |

The `SN74ALVCH16374` check is worth spelling out because it is the substitution
the netlist README calls "the one that matters". The datasheet's package view
gives pins 1–24 down the left as `1OE, 1Q1, 1Q2, GND, 1Q3, 1Q4, VCC, 1Q5, 1Q6,
GND, 1Q7, 1Q8, 2Q1, 2Q2, GND, 2Q3, 2Q4, VCC, 2Q5, 2Q6, GND, 2Q7, 2Q8, 2OE` and
48 down to 25 on the right as `1CLK, 1D1, 1D2, GND, 1D3, 1D4, VCC, 1D5, 1D6,
GND, 1D7, 1D8, 2D1, 2D2, GND, 2D3, 2D4, VCC, 2D5, 2D6, GND, 2D7, 2D8, 2CLK`.
The symbol reproduces all 48 exactly, including the eight GND and four VCC
positions. Two independent clocks (`1CLK` pin 48, `2CLK` pin 25) and two
independent output enables (`1OE` pin 1, `2OE` pin 24) exist as the generator
assumes.

`LTC3265` is still in `lyrebird.kicad_sym` (19 pins) but the charge pump it
described was deleted with decision 5 and no generator references it. Dead
weight, not a fault.

**The stock GateMate symbol is correct, all 324 balls.** I extracted DS1001's
Table 5.3 pin list (September 2026 revision) and compared it against the symbol
programmatically, normalising KiCad's overbar syntax and the combined
first/second-function names: **324 balls, zero mismatches, none missing on
either side**, including every dual-function name (`CLK0/IO_SB_A8` at N14,
`POR_EN/IO_WA_A3` at U1, `IO_WA_A2/~{CFG_FAILED}` at V2, and so on) and
`N16 = N.C.`, which the datasheet says "must be left open". The generator's
claim that bank allocation is "against the real ball map, not invented" holds.

---
## 3. Datasheet conformance, part by part

### 3.1 Confirmed fault: the USB 3.0 SuperSpeed pairs are swapped

`main_board.py` wires the receptacle's SuperSpeed contacts the wrong way round,
and the netlist proves it without reference to any naming convention.

The USB 3.0 Micro-B receptacle contact assignment (and KiCad's
`Connector:USB3_B_Micro`, whose pin numbers match it) is contacts 6/7 =
`StdA_SSTX−/+` and 9/10 = `StdA_SSRX−/+`. KiCad gives 6/7 the electrical type
**output** and 9/10 **input**, because a Micro-B receptacle's contacts are named
for the A-end signals the cable carries straight through: `StdA_SSTX` is what the
*host* transmits, so at the device it is a receive pair.

What the netlist builds:

```
USB_SSRX_P: J1.10 SSRX+ (INPUT),  U2.35 RIDP (INPUT)     <- no driver at all
USB_SSRX_N: J1.9  SSRX- (INPUT),  U2.34 RIDN (INPUT)     <- no driver at all
N$1/N$2   : U2.32 TODP (OUTPUT) -C6- J1.7 SSTX+ (OUTPUT) <- two drivers
N$3/N$4   : U2.31 TODN (OUTPUT) -C7- J1.6 SSTX- (OUTPUT) <- two drivers
```

`USB_SSRX_P` and `USB_SSRX_N` are the **only two multi-node nets on the main
board every one of whose pins is an input**. The FT601Q's receiver is wired to
the contacts it should be driving, and its transmitter — through the two 100 nF
AC-coupling capacitors — faces the host's transmitter. Both pairs are crossed.

The generator states the inverted convention explicitly and reasons from it:

> Signal naming follows the USB 3.0 connector convention: on a B-type receptacle
> SSTX is what the device transmits and SSRX is what it receives, because the
> cable ties StdA_SSTX to the B-side SSRX.

There is no crossover in a USB 3.0 cable; the crossover is in the naming being
A-centric, which is why the names are preserved end to end. The `D+`/`D−` pair
is wired correctly (contact 3 → `DP`, contact 2 → `DM`), so the symptom is that
SuperSpeed never trains and the link falls back to High Speed at 480 Mb/s. The
FIFO side keeps working, the host keeps enumerating, and the only evidence is
throughput — which makes it the kind of fault that survives bring-up.

Fix: swap which contact pair each side lands on, keeping the two capacitors on
the FT601Q's `TODP`/`TODN` (the transmitter is the side the USB specification
requires to be AC-coupled).

**Nothing in the generation path would catch this.** `main_board.erc` is zero
bytes and the run log's only warnings are about footprints; SKiDL's ERC is never
invoked, so neither a driverless net nor an output-to-output net raises anything.
KiCad's own ERC would flag both, but no board imports the netlist.

### 3.2 Confirmed fault: the inverting converter has no input capacitor

The LMR33630 datasheet's `VIN` pin description: "Connect a high-quality bypass
capacitor or capacitors directly to this pin and **PGND**." For U7, wired as an
inverting buck-boost, PGND *is* `-6V_A`. Enumerating every two-terminal part on
the main board and the net pair it spans, there is **no capacitor between `+12V`
and `-6V_A`**:

```
+12V  <-> GND    : C8=22uF, C9=100nF, D1..D3      <- U5's input caps (U5's PGND is GND)
-6V_A <-> GND    : C15=47uF, C16=100nF            <- U7's output caps
-6V_A <-> N$8    : C13=1uF                        <- U7's VCC cap, correctly to its own GND
```

U7's switching input loop therefore returns through two capacitors in series and
the system ground plane instead of through one capacitor across its own
terminals. For an inverting topology this is the single most important bypass in
the circuit, because the input current is discontinuous in that configuration. It
is also the one thing about this converter that is checkable from the netlist
rather than from a layout.

Credit where due: the same block gets three harder things right. `VCC`'s 1 µF
goes to `-6V_A` and not to system ground; the feedback divider runs from system
ground through 124 k to `FB` and 24.9 k down to `-6V_A`, so the part regulates
its own 1.0 V reference across the rail (1.0 × (1 + 124/24.9) = 5.98 V, matching
the stated −5.98 V); and every absolute maximum this topology stresses is inside
its rating: `EN to AGND` max is `VIN + 0.3 V` and EN is tied to VIN exactly;
`PG to AGND` is 0 to 22 V (18 V recommended) and PG sits 6 V above AGND; `AGND
to PGND` max ±0.3 V and they are the same net; `SW to PGND` max `VIN + 0.3`.

**What I could not verify:** the LMR33630 datasheet (SNVSAN3F) does not document
an inverting buck-boost configuration at all — the only occurrence of "invert" in
it is "AC inverters" in the applications list. The topology is supported by TI
only in separate application notes, which I did not fetch. So the −6 V rail rests
on a configuration this datasheet says nothing about, and that should be recorded
as an assumption rather than a verified design.

### 3.3 Confirmed fault: the translator's output enables violate the datasheet's sequencing instruction

SN74AVC4T245 (SCES576I), applications section: "To ensure the high-impedance
state during power up or power down, the `OE` input pin **must** be tied to VCCA
through a pullup resistor and must not be enabled until VCCA and VCCB are fully
ramped and stable."

`output_module.py` ties both enables hard low — `tr["1~{OE}"] += gnd` and
`tr["2~{OE}"] += gnd` — so the device is enabled at all times, including through
power-up.

On this module that window is long and calculable. VCCA is `+2V5` from U9 and
VCCB is `+3V3_CLK` from U6, both LT3045s, both with `PGFB` tied to `IN` (fast
start-up disabled) and both taking the helper's default 4.7 µF `C_SET`. With
t ≈ 2.3·R_SET·C_SET:

| Rail | R_SET | C_SET | ramp |
| --- | --- | --- | --- |
| `+2V5` (VCCA), U9 | 24.9 k | 4.7 µF | 269 ms |
| `+3V3_CLK` (VCCB), U6 | 33.2 k | 4.7 µF | 359 ms |

So VCCA is up about **90 ms before VCCB**, on every power-up, with the translator
enabled throughout. During that window `1A1` — the only path `MCLK` may take — is
an enabled output driving a GateMate clock ball from a B-side input that is below
its own threshold, and the FPGA's rails are already up because they come from the
other board. DS1001 Table 4.5 gives `IDD,max` 158 µA for a GPIO at its transition
point, which is the same argument the generator itself uses to justify grounding
`SER_CLK`.

The fix is the datasheet's: a pull-up to VCCA on each `OE`, and ideally `OE`
released by something that knows both rails are up. Note the two rails cannot be
made to arrive together by choosing `C_SET`, because their `R_SET` values differ
by construction — the ramp difference is a consequence of the output voltages.

### 3.4 Confirmed gap: five FPGA supply pins have no decoupling, and none of the four core-domain supplies has the filter the datasheet asks for

DS1001 §2.10: "VDD_PLL has the same voltage range as VDD. VDD_SER and
VDD_SER_PLL have a voltage range from 1.0 V to 1.15 V. **All these voltages
should be connected to noise filters.**"

The generator's decoupling loops are keyed on two regexes: `^VDD_(NA|NB|EA|EB|SA|
SB|WA|WB|WC)$` (45 bank balls, one 100 nF each) and `^VDD$` (28 core balls, one
100 nF each). Counting the generated netlist confirms 45 + 4 VCCIO + 1 flash = 50
× 100 nF on `+2V5`, and 28 × 100 nF + 22 µF on `+1V0`. What that leaves with **no
capacitor named anywhere in the netlist**:

| Pin | Ball | Rail | Datasheet description |
| --- | --- | --- | --- |
| `VDD_PLL` | P16 | `+1V0` | "Supply pin for PLLs", Table 4.7 "Clean analog supply voltage for DCO" |
| `VDD_SER` | U12, V17 | `+1V0` | SerDes core supply |
| `VDD_SER_PLL` | T16 | `+1V0` | SerDes PLL supply |
| `VDD_CLK` | T14 | `+2V5` | Supplies `SER_CLK`, `SER_CLK_N`, `RST_N`, `POR_ADJ` |

Three of the four are on rails that carry 28 and 50 other capacitors, so at the
board level they are bypassed; but none of them has a *local* part, and none of
the four core-domain supplies has the **filter** — a ferrite or an RC, not a
capacitor — that §2.10 asks for by name. `VDD_CLK` is the one I would fix first
regardless of the SerDes: it supplies `RST_N` and `POR_ADJ`, i.e. the reset
comparator's own reference divider, and the POR network hangs 2.2 µF on that node
already (see §3.5).

### 3.5 The power-on reset network is arithmetically right and outside its documented purpose

The arithmetic first, because it checks out exactly. DS1001 §3.2.2 gives

```
treset = (R3a·75k)/(R3a+75k) · C1 · ln( VDD_CLK / (VDD_CLK − (0.45V/75k)·(75k + (R3a·133k)/(R3a+133k))) )
```

and with R3a = 47 k, C1 = 2.2 µF, VDD_CLK = 2.5 V: 47k‖75k = 28.89 k,
47k‖133k = 34.73 k, 6.0 µA × 109.73 k = 0.658 V, ln(2.5/1.842) = 0.3057,
t = 19.4 ms. Every intermediate in the generator's comment reproduces. The
orientation is right too, and this is the part most likely to be misread: R3a
goes from `POR_ADJ` to VDD_CLK, in parallel with the internal 133 k, which is
what *lowers* the threshold — Table 4.8's footnotes (R3a = 500 k → 1.18 V typ,
R3a = 250 k → 1.08 V typ, against 1.44 V typ with POR_ADJ open) only make sense
that way, and the datasheet's own R3a < 10 k simplification
(`treset ≈ R3a·C1·ln(...)`) only works if R3a is the charging resistor from
VDD_CLK. The netlist does exactly that.

What is outside the datasheet is *using* R3a at all. §3.2.2: "With VDD_CLK in the
range 1.8 .. 2.7 V (normal operation), POR_ADJ should be left open. Optionally, a
capacitor can be connected to ground to improve noise suppression. ... R3a will
decrease the threshold level. **This is only necessary when VDD_CLK < 1.8 V** to
avoid a permanent reset state." VDD_CLK here is 2.5 V.

The consequence is not a non-functioning board — R3a ≤ 100 k guarantees no
permanent reset, which the generator correctly cites — but it is a real trade
that is not written down:

- The VDD_CLK reset threshold drops from ~1.44 V typical to ~0.66 V. The FPGA
  now leaves reset when VDD_CLK has reached about a quarter of its final value,
  and the 19.4 ms delay from C1 is the only thing covering the ramp.
- The POR module's advertised **voltage-drop detection on VDD_CLK** is
  effectively disabled: a brownout has to take the rail below ~0.66 V before the
  comparator reacts, and 2.2 µF on `POR_ADJ` slows even that.
- Table 4.8 characterises R3a only at 250 k and 500 k. At 47 k the threshold is
  an extrapolation from the formula, not a specified number. I could not verify
  it against the datasheet and neither can anyone else.

If the 19.4 ms is what is wanted, the datasheet's own sanctioned arrangement for
a 2.5 V VDD_CLK is POR_ADJ open with C1 only, which keeps the 1.44 V threshold
and gets its delay from the internal 133 k‖75 k with C1. That is worth comparing
before committing.

### 3.6 Part-by-part results

Everything below was checked against the datasheet named. ✓ means I verified it;
"—" means I could not.

**Cologne Chip CCGM1A1** — DS1001, September 2026, fetched from colognechip.com.
✓ Absolute maxima confirmed as the brief states them: Table 4.1 `VDDIO` 2.75 V
(GPIO banks *and* `VDD_CLK`), `VDDcore` 1.20 V (`VDD`, `VDD_PLL`, `VDD_SER`,
`VDD_SER_PLL`). ✓ Table 4.2 economy mode `VDD` 0.95/1.00/1.05 V and `VDDSER` /
`VDDSER_PLL` 1.00–1.15 V, so open item E-4's statement of the two-window problem
is accurate and so is its conclusion that no resistor satisfies both. ✓ Table 4.5
`VDDIO` operating 1.1–2.7 V and `VIN` = −0.4 V to `VDDIO` + 0.4 V, so E-5's
"187 mV to destruction, 137 mV to out of specification" against a 2.563 V worst
case is right. ✓ All 324 balls, symbol against Table 5.3, zero mismatches (§2.3).
✓ `CFG_MD[3:0]` all four tied to GND = 0b0000 = SPI Active CPOL=0 CPHA=0, and
§3.3.1's requirement that "these pins must always be connected to either GND or
VDD_WA" is met. ✓ `POR_EN` to VDD_WA and `RST_N` to VDD_CLK per §3.2.2 (both are
the same `+2V5` net here, which is what the datasheet asks for). ✓ `N16` left
open, as the pin list demands. ✓ `SER_CLK`/`SER_CLK_N` grounded — the datasheet
gives no instruction, and grounding a powered receiver's inputs is the
conservative reading.

I recomputed E-4 and E-5 from the LTM4622's own tolerances rather than taking
them: VFB 0.592/0.600/0.608 V (±1.33 %) and RFBHI 60.00/60.40/60.80 k give
channel 1 = 2.433 / 2.500 / **2.563 V** and channel 2 = **0.979** / 0.999 /
**1.019 V**. Both match the numbers recorded in the generator to the millivolt.
`VDD_SER`'s 1.00 V minimum is indeed missed at nominal, and the two windows
overlap only over 1.00–1.05 V, narrower than the regulator's own spread. The
recorded decision — centre on `VDD` and accept that an unused block is out of
specification — is the right one on this evidence.

**ADI LTM4622** — Rev G, via a mirror (analog.com is unreachable from here).
✓ All 25 balls against PIN FUNCTIONS. ✓ `R_FB` 19.1 k for 2.5 V and 90.9 k for
1.0 V are the datasheet's Table 1 values, not calculations. ✓ `R_FSET` 649 k is
the datasheet's own table entry for 1.5 MHz, and the datasheet requires
1.5–2.5 MHz for a 2.5 V output. ✓ `tON(MIN)` 20 ns typical, so 1.5 MHz on the
1.0 V channel has 133 ns against 20 ns. ✓ `TRACK/SS` 10 nF: the datasheet's own
`tSTART` = 4.3 ms is measured at exactly `TRACK/SS = 0.01 µF`. ✓ `SYNC/MODE` to
ground for forced continuous, per the pin description. ✓ `RUN1`/`RUN2` to `+5V` —
"Do not float this pin", and `RUN` abs max is `VIN + 0.3 V`. ✓ `COMP1`/`COMP2`
open — "The device is internal compensated. Do not drive this pin." ✓ `INTVCC`
open — "internally decoupled to GND with a 2.2 µF low ESR ceramic capacitor. No
additional external decoupling capacitor needed." ✓ One 4.7 µF input capacitor
per channel, which is what the datasheet requires and exactly what is fitted.
✓ VIN 5 V is inside 3.6–20 V, and VIN1 is powered, which the datasheet warns is
required for channel 2 to work at all.

**ADI LT3045 / LT3094** — LT3045 Rev via farnell mirror, LT3094 Rev 0 via digikey
mirror. ✓ LT3045 DFN-10 pin map: IN 1,2; EN/UV 3; PG 4; ILIM 5; PGFB 6; SET 7;
GND 8 + exposed pad 11; OUTS 9; OUT 10 — and the generator's name-prefix matching
puts both `OUT` and `OUTS` on the output net, which is what the datasheet wants
(OUTS is the error amplifier's non-inverting input, Kelvin-connected to the
output). ✓ `ILIM` to GND on every LT3045: "If the programmable current limit
functionality is not needed, tie ILIM to GND." ✓ `PGFB` to IN: "If power good and
fast start-up functionalities are not needed, tie PGFB to IN." ✓ `EN/UV` to IN
unless gated: "If unused, tie EN/UV to IN. Do not float the EN/UV pin." ✓ `PG`
open: "If the power good functionality is not needed, float the PG pin." ✓ 10 µF
output capacitor, which is the datasheet's stated minimum for stability.
✓ LT3094 `VIOC` open ("If unused, float the VIOC pin") and `PG` open. ✓ LT3094
`EN/UV` bidirectional, so `MUTE_N`'s 2.5 V high enables it — though the datasheet
says 1.26 V typical, not the ±1.35 V the comment claims.

One factual error and one number to correct:

- The comment "**Unlike the LT3045, the LT3094's pin description gives no
  instruction for an unused ILIM**" is wrong. LT3094 Rev 0, ILIM (Pin 6): "The
  programming scale factor is nominally 3.75 A • kΩ. **If the programmable
  current limit functionality is not needed, tie ILIM to GND. Do not float the
  ILIM pin.**" The datasheet gives exactly the same instruction as the LT3045's.
  Programming 24.9 k is still legitimate and the resulting 3.75/24.9 = 151 mA is
  comfortably above the rail's 56 mA worst case, so the circuit is fine — but the
  stated reason for deviating from the LT3045's treatment does not exist, and the
  rest of that comment justifies the value against "what the pump's LDO can
  deliver into a fault" on a pump that decision 5 deleted.
- LT3045 dropout is **220/275/330 mV at 1 mA and 50 mA**, not the 260 mV headline
  (which is the 500 mA figure). That is the number U14's 30 mV of headroom has to
  be judged against — see §6.

**TI SN74AVC4T245** — SCES576I. ✓ TSSOP-16 (PW) pin numbers: VCCA 1, 1DIR 2,
2DIR 3, 1A1 4, 1A2 5, 2A1 6, 2A2 7, GND 8/9, 2B2 10, 2B1 11, 1B2 12, 1B1 13,
2OE 14, 1OE 15, VCCB 16. ✓ VCCA and VCCB both 1.2–3.6 V, so 2.5 V and 3.3 V are
both in range. ✓ Function table: `OE` low + `DIR` low = "B data to A bus", `DIR`
high = "A data to B bus" — so bank 1 with `1DIR` low carrying `MCLK` from the
module to the header is correct, and bank 2 with `2DIR` high carrying the enables
outward is correct. ✓ `DIR` and `OE` referenced to VCCA, and both are strapped to
`+2V5` or ground, never to 3.3 V. ✓ "All unused data inputs of the device must be
held at VCCI or GND": `1B2` is tied to ground and its output side `1A2` left open,
which is the right way round. ✗ The `OE` sequencing requirement, §3.3.

**TI SN74ALVCH16374** — SCES021L. ✓ All 48 pins (§2.3). ✓ `VIH` = 2.0 V for
VCC 2.7–3.6 V, which is the whole basis for crossing the mezzanine untranslated
and it is exactly as the generator states; LVC's 0.7 × VCC = 2.31 V and AVC's
0.65 × VCC = 2.15 V confirm the family choice. ✓ `VOH` = VCC − 0.2 V at 100 µA,
so using the supply as the voltage reference is sound at the element's ~1 mA;
note the datasheet's only specified load points are 100 µA and −12 mA (2.2 V at
VCC = 2.7 V), so "a few tens of millivolts at 1 mA" is an interpolation and not a
guaranteed figure. ✓ `VI` abs max −0.5 to 4.6 V independently of VCC, so the FPGA
driving 2.5 V into these inputs while `+3V3_REF` is still ramping is safe. ✓ Bus
hold is present (`I_I(hold)` ±45 µA at 2.3 V), which is why tying the spare `D8`
inputs low rather than leaving them to the latch is right. ✓ Both `OE` pins to
ground, both `CLK` pins from one buffer output.

**TI SN74LVC1G74** — SCES794G. ✓ DCU/VSSOP-8 pinout `1 CLK, 2 D, 3 Q̄, 4 GND,
5 Q, 6 C̄L̄R̄, 7 P̄R̄Ē, 8 VCC`, matching the custom symbol exactly. ✓ The toggle
wiring (`Q̄` to `D`) and both asynchronous inputs tied inactive high. ✓ 1.65–5.5 V
supply covers 3.3 V.

**TI LMK1C1104** — SNAS791D. ✓ PW/TSSOP-8 pinout `1 CLKIN, 2 1G, 3 Y0, 4 GND,
5 Y2, 6 VDD, 7 Y3, 8 Y1`, matching the custom symbol exactly. ✓ `1G` has a
300 kΩ internal pull-down and the datasheet says "typically connected to VDD with
external pullup resistor" — the 10 k is correct and necessary. ✓ "Unused outputs
can be left floating", so `Y3` open is sanctioned. ✓ Output skew < 50 ps, which
is the figure decision 0012 leans on. ✗ The comment's "17.5 fs typical additive
jitter" is not a datasheet number: SNAS791D gives **7.5 fs typical** at
VDD = 3.3 V (8 fs typical / 20 fs maximum in the characteristics table), < 50 fs
maximum overall. The error is in the safe direction but it is the figure the part
was selected on.

**TI OPA1612** — SBOS450. ✓ `D` (SOIC-8) dual pinout: OUT A 1, −IN A 2, +IN A 3,
V− 4, +IN B 5, −IN B 6, OUT B 7, V+ 8 — exactly the generator's
`UNIT = ((1,2,3),(7,6,5))` with 8 = V+ and 4 = V−. ✓ Supply 4.5–36 V
(±2.25 to ±18 V) covers ±5 V. ✓ 1.1 nV/√Hz at 1 kHz. ✓ "Place 0.1-µF bypass
capacitors close to the power-supply pins" — one 100 nF pair per package, three
packages, three pairs.

**Crystek CCHD-957** — Rev N, 25-Aug-2026, from crystek.com. ✓ Pad connection
1 E/D, 2 GND, 3 OUT, 4 Vcc, matching the symbol. ✓ Tri-state/standby table: E/D
**open = Active**, "1" level 0.7 × Vcc min = Active, "0" level 0.3 × Vcc max =
High Z. Both halves of the generator's argument are datasheet-backed: an open
pin runs, so the pull-downs are needed; and standby tri-states the output, so one
shared `OSC_RAW` net is legal while exactly one part is enabled. ✓ 3.3 V ±0.3 V
supply, 15 mA typical / 25 mA max, 45.1584 and 49.152 MHz are both in the
"Developed Frequencies" list, and option X is −40 to +85 °C at ±25 ppm, which is
what `CCHD-957X-25-...` orders. ✓ Body and pad geometry (§2.2).

**Not verified, and why:**

- **FTDI FT600Q/FT601Q.** I could not obtain the datasheet: ftdichip.com,
  mouser.com, sos.sk and arrow all returned HTML or timed out from this
  environment. So **everything about the bridge except the connectivity above is
  unverified**: the 1.6 k 1 % `RREF` value, the 30 MHz / 18 pF / 50 Ω crystal
  requirement and the 27 pF load capacitors, `GPIO[1:0]` = 00 selecting 245
  synchronous FIFO mode, the `DV10`/`VD10`/`AVDD` arrangement and its 4.7 µF, the
  VCCIO range at 2.5 V, whether `VBUS` is a sense input or a supply, and whether
  pin 19 "Reserved" must be left open. A web search returns FTDI text describing
  `VBUS` as "USB BUS power input" and `WAKEUP_N` as low when USB is active / high
  in suspend, which is consistent with the generator's comments, but a search
  summary is not a datasheet and I am not treating it as one.
- One thing I can say from the netlist regardless: **`USB_VBUS` has exactly two
  nodes, J1.1 and U2.37, and no capacitor, no series resistor and no TVS.** A
  cable-facing 5 V pin with no bypass and no transient protection is worth a
  look whichever kind of pin it turns out to be.
- **Macronix MX25R6435F.** Not fetched. The symbol's pinout is the standard
  8-SOP serial NOR arrangement (`1 C̄S̄, 2 SO/SIO1, 3 W̄P̄/SIO2, 4 GND, 5 SI/SIO0,
  6 SCLK, 7 R̄ĒSĒT̄/SIO3, 8 VCC`) and the `M2I` order suffix is the 150-mil body
  that `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` describes, but I did not confirm
  either against Macronix.
- **Littelfuse 1812L050/30, SMAJ18A, SS34, BAT54.** Not fetched; the ratings in
  `verify_power.py` are marked `DS` but I did not independently confirm them.
- The **LTM4622 A1-corner orientation** is settled (§2.1) but the **CCHD-957 pad
  long-axis orientation** is not (§2.2) — that one needs a human to look at the
  drawing, because it is carried by geometry rather than by a dimension label.

---

## 4. Unconnected pins, enumerated

89 open pins across the two boards. Regenerated list, each with a verdict.

### 4.1 Main board — 77 open pins

| Part | Pins | Count | Verdict |
| --- | --- | --- | --- |
| U1 | `SER_RX_P/N`, `SER_TX_P/N`, `SER_RTERM` | 5 | **Deliberate.** SerDes unused. `SER_RTERM` is "Line termination" and Table 4.3's 200 Ω calibration reference would be needed only if the block ran; the datasheet gives no must-connect instruction. Note the generator *does* ground `SER_CLK`/`SER_CLK_N` — the asymmetry is justified, because those two are powered receiver inputs with no configurable alternative, while these are unused differential I/O. |
| U1 | `IO_WA_B5/SPI_FWD` | 1 | **Deliberate**, documented: only used when several FPGAs chain off one flash. |
| U1 | `NC` (N16) | 1 | **Required.** DS1001 Table 5.3: "Not connected. This pin must be left open." |
| U1 | `IO_EB_*` | 18 | **Deliberate** — whole unused bank. But see the note below. |
| U1 | remainder of `IO_EA_*` | 12 | Deliberate, spare bus-bank I/O. |
| U1 | `IO_SB_*` incl. `CLK2`, `CLK3` | 16 | Deliberate. Worth knowing that all four clock-capable pins live in bank SB and two remain spare. |
| U1 | `IO_WC_*` | 13 | Deliberate, spare control-bank I/O. |
| U1 | `IO_WB_*` | 4 | Deliberate: 32 element lines drawn from SA + WB leave four over. |
| U2 | `~{WAKEUP}` | 1 | **Probably deliberate, not documented.** The generator discusses `WAKEUP_N` only to explain why the old rail gating was removed, and the netlist README's "pins left open on purpose" table does not list it. The pin is `BIDIR` in the symbol and the generator asserts an internal pull-up holds it high. Unverified — I could not fetch the datasheet. It should be in the documented list either way. |
| U2 | `Reserved` (pin 19) | 1 | **Deliberate**, documented as "datasheet says do not connect". Unverified. |
| U3 | `PG` | 1 | **Correct.** LT3045: "If the power good functionality is not needed, float the PG pin." |
| U4 | `COMP1`, `COMP2` | 2 | **Required.** "The device is internal compensated. Do not drive this pin." |
| U4 | `INTVCC` | 1 | **Correct.** Internally decoupled with 2.2 µF; no external capacitor needed. |
| J1 | `ID` | 1 | **Deliberate.** Device port, not OTG. |

The one thing I would raise about the 63 open bank I/O: they sit on powered banks
(`VDD_EB` is supplied at 2.5 V even though every one of its 18 signals is open),
and before configuration a GateMate GPIO is high impedance, so Table 4.5's
158 µA-at-transition-point figure applies to all of them during the
configuration window. That is the identical argument the generator used to
justify grounding `SER_CLK`. The difference — and it is a real one — is that a
GPIO can be given an internal pull by the bitstream and a SerDes clock input
cannot. So the asymmetry is defensible, *provided* the constraints file sets a
default pull on unused I/O. `hdl/constraints/` contains a `.gitkeep` and a
README and no constraints file, so nothing does that yet.

### 4.2 Output module — 12 open pins

| Part | Pin | Verdict |
| --- | --- | --- |
| U2 `74AVC4T245` | `1A2` | **Correct.** The spare channel's B-side input `1B2` is tied to ground as the datasheet requires; `1A2` is that channel's output and an open output is fine. |
| U3, U4 `SN74ALVCH16374` | `1Q8`, `2Q8` (×2 each) | **Correct.** 14 elements per channel in a 16-bit package; the matching `D8` inputs are tied low so the spare outputs have a defined state rather than being left to bus hold. |
| U5, U6, U9, U14 `LT3045` | `PG` | **Correct**, datasheet-sanctioned float. |
| U8 `LT3094` | `PG`, `VIOC` | **Correct.** "If unused, float the VIOC pin"; PG likewise. |
| U12 `LMK1C1104` | `Y3` | **Correct.** SNAS791D: "Unused outputs can be left floating." |

Nothing on either board is an accidental open pin. The four reserved element
lines `ELEM28..31` reach the module's header and nothing else, which is
`interface.md`'s "reserved, driven low by the main board" and is correct on both
sides.

---

## 5. Do the generated sheets represent the netlists?

I reconstructed each sheet's geometry from the exported `.kicad_sch` files —
symbol placements, wires, junctions and global labels — recomputed every pin's
coordinate with the generator's own `resolve`/`collect_pins` and the same
`round(v/GRID)*GRID`, and then asked, for each of the netlist's node-connections,
whether the drawing provides it a connection at that point.

(My first attempt reported all 787 connections missing, because my property
matcher expected quoted strings and the tool's parser strips them, so it found
zero placed symbols. A checker that finds nothing and therefore reports
everything as broken is the same failure mode as a checker that finds nothing and
reports everything as fine. The diagnostic counts are what caught it — hence they
are printed above the verdict.)

**Nothing is dropped.** Both boards: zero unresolved symbols, zero parts with no
pins, zero parts placed twice, zero parts missing from all sheets, and **zero
connections not represented**.

```
lyrebird-main.net: 787 node-connections -> 70 wires + 717 labels, 0 missing
lyrebird-dac.net : 580 node-connections -> 114 wires + 466 labels, 0 missing
```

**But 49 coordinates carry global labels for two to four electrically distinct
nets at the same point** — 23 on the main board, 26 on the module. In KiCad two
global labels sharing a connection point are joined, so the drawing asserts
shorts the netlist does not contain. Examples:

```
main  01-U1-CCGM1A1 at (45.72, 114.30): ELEM13, ELEM20, FT_DATA13, FT_TXE_N
                                        via U1.U10, U1.H3, U1.C9, U1.G16
dac   02-Output-stage at (144.78, 236.22): DIFF_INV_L, DIFF_INV_R  via U11.2, U11.6
dac   03-Reclocking   at ( 35.56, 254.00): ELEM21, GND             via U4.36, U4.37
```

That last one is the sharpest: the drawing shows element line 21 and ground on
the same node.

Two independent causes, both in `tools/netlist_to_schematic.py`, and both easy to
fix:

**(1) `collect_pins` collects every unit, but only unit 1 is drawn.** It recurses
through the whole symbol node, so for a multi-unit symbol the units' local
coordinate spaces are overlaid. Measured:

| Symbol | Pins | Distinct raw coordinates | Worst pile-up |
| --- | --- | --- | --- |
| `CCGM1A1` (8 units) | 324 | **71** | **74 pins on one point** |
| `OPA1612AxD` (2 units) | 8 | 5 | 2 |
| `SN74ALVCH16374` (1 unit) | 48 | 48 | 1 |
| `LTM4622` (1 unit) | 25 | 25 | 1 |

So on the FPGA sheet a reader sees one unit's body with labels for all 324 balls
stacked into that unit's footprint. The netlist is intact; the drawing is not a
representation of it.

**(2) The grid snap is coarser than the symbols and uses banker's rounding.**
`GRID = 2.54`, but symbol pins sit at odd multiples of 1.27 — exactly half a
grid step — and Python's `round()` breaks ties to even. On the custom
`SN74ALVCH16374`:

```
pin 47  y=24.13  y/2.54=9.500 -> 10
pin 46  y=21.59  y/2.54=8.500 ->  8
pin 44  y=19.05  y/2.54=7.500 ->  8      <- collides with 46
pin 43  y=16.51  y/2.54=6.500 ->  7
pin 41  y=13.97  y/2.54=5.500 ->  6
pin 40  y=11.43  y/2.54=4.500 ->  4
pin 38  y= 8.89  y/2.54=3.500 ->  4      <- collides with 40
```

48 distinct pin positions become 36 after snapping. This is the mechanism behind
the `ELEM21`/`GND` collision and every other adjacent-pin merge on the module.
Snapping to 1.27 — or not snapping pin coordinates at all, since they are already
on a valid grid — removes it.

So the answer to the question as posed is: the sheets do not *drop* connections,
they *add* them. A reader looking at the FPGA sheet or the register sheets cannot
tell which label belongs to which pin, and KiCad's own ERC on those files would
report net conflicts. Neither board's sheets are loaded by anything that would
have said so — the `.kicad_pcb` files are empty and nothing runs ERC.

---
## 6. Stale constants beside changed circuits

The instruction to check "what each constant was chosen against and whether that
thing still holds" turned out to be the most productive single pass over these
two files. Two decisions — 0014 replacing bus power with a 12 V adapter, and
decision 5 deleting the module's charge pump — invalidated premises that several
component values still rest on.

### 6.1 U14's rail: the fix is in, and the worst case is still negative

The 49.9 k → 45.3 k change has landed; the comment now records why. Working it
through with the datasheet numbers rather than the nominal ones, the margin is
thinner than it looks:

| Quantity | Source | Value |
| --- | --- | --- |
| LMR33630 `VFB` | SNVSAN3F, ADJ option | 0.985 / 1.000 / **1.015** V |
| `+5V` = VFB·(1 + 100k/24.9k), 1 % resistors | calculation | **4.863** / 5.016 / 5.174 V |
| LT3045 `ISET` | 3045f, over full range | 98 / 100 / **102** µA |
| U14 out = ISET · 45.3 k (0.1 %) | calculation | 4.439 / 4.530 / **4.623** V |
| LT3045 dropout at 1–50 mA | 3045f, not the 260 mV headline | 220 / 275 / **330** mV |

Typical case: 5.016 − 4.530 = 486 mV against 275 mV — comfortable. Stacked worst
case: 4.863 − 4.623 = **240 mV against a 330 mV maximum dropout, i.e. −90 mV**,
before any allowance for the mezzanine contact resistance and trace drop at the
~22 mA this rail carries. The part does not fail hard in dropout, it just stops
regulating and passes its input's noise and ripple straight through — on the rail
feeding six OPA1612s whose supply rejection is the reason the regulator is there.

The clean fix is to stop programming this rail near its input. The design's own
statement is that the positive analog supply needs about 3.5 V (±2.83 V peak plus
the OPA1612's 600 mV headroom), and full scale on this rail is irrelevant — it is
an amplifier supply, not a reference. 36.5 k gives 3.65 V and about 1.2 V of
headroom at the worst-case corner, for the price of one resistor value.

### 6.2 The element resistor split clears a limit that no longer exists

```python
ELEM_R1 = "1.69k 0.1% thin film"     # register side of the split
ELEM_R2 = "1.65k 0.1% thin film"     # summing-node side of the split
```

with the recorded reason: "1.69k + 1.65k = 3.34 kohm, both E96, is the closest
even-ish split to 3.32 kohm that stays above 3312 ohm; an even 1.65k + 1.65k
would be 3.30 kohm and **fail the power-on limit by a hair**."

That power-on limit is the one-unit-load-before-enumeration rule. 0014 replaced
bus power with a 12 V adapter and `interface.md` now says in as many words:
"**There is no declared current budget any more.** This section used to require
the module to stay inside a figure fixed in the USB descriptor at enumeration.
0014 replaced bus power with a 12 V supply, so nothing is negotiated."

So the only reason the two halves of every element are *different values* is a
constraint that has been retired. The cost is not nothing: an equal split puts
both halves on one tolerance class and one reel, makes the 180 pF see exactly
R/2 either side, and removes a second part number from the most matching-critical
network on the board — which is the whole argument for using thin-film arrays
there in the first place. 1.65 k + 1.65 k = 3.30 kΩ is now permissible.

Worth noting that the *downstream* arithmetic was updated correctly: the 402 Ω
transimpedance value is justified as "6.958 mA × 402 = 1.978 V RMS", and
7 × 3.32 V / 3.34 kΩ = 6.958 mA, so the 3.34 kΩ figure is threaded through
consistently. Only the reason for the awkward split is stale.

### 6.3 The clock-chain part selection rests on the same retired budget

"Every integrated divider-plus-fanout part found is built for hundreds of
megahertz and costs 65 mA of core current (Si53308), which does not fit: the
module's clock rail is ungated, and **one unit load before enumeration** leaves
it about 50 mA including both oscillators."

Same retired rule. The two parts actually chosen (SN74LVC1G74 + LMK1C1104) are
good ones on their own merits — the divider's ±24 mA drive and the buffer's
< 50 ps skew are the figures decision 0012 needs — so nothing has to change. But
the recorded reason for rejecting the integrated alternative no longer applies,
and if that part is ever revisited the comparison has to be redone on different
grounds.

### 6.4 `C_SET` on the module's 2.5 V rail contradicts the helper's own rule

`lt3045_housekeeping`'s docstring: "Pass a smaller `c_set` on any rail where the
noise specification is not being bought. A rail that only feeds digital parts
gains nothing from 4.7 µF and pays the whole ramp for it." The main board applies
this to U3 (100 nF, cutting 359 ms to 7.6 ms) and explains why at length.

The module's U9 is the same case and does not get it. Its own comment says of the
2.5 V rail: "It is a logic supply, not a reference: **nothing on it reaches the
signal**." It nonetheless takes the default 4.7 µF and pays 269 ms — and that is
precisely what opens the 90 ms window in §3.3, because U6's `+3V3_CLK` takes
359 ms and the translator sits between them enabled the whole time. Reducing
U9's `C_SET` alone does not close the window (it widens it); the two fixes are
the `OE` pull-up and matching the ramps deliberately rather than by accident.

### 6.5 Comments still describing the deleted charge pump

The LT3094 block carries three sentences about a circuit decision 5 removed: "The
LT3094 takes the inverting **pump's** output directly, not LDO−", "**LDO− is a
50 mA part**, and its own dropout would cost another 450 mV of headroom that the
**doubled-then-inverted rail** does not have at the bottom of the USB range", and
the `ILIM` value justified as "below what the **pump's LDO** can deliver into a
fault". The rail now arrives from the main board's inverter. The values are
still fine; the reasoning describes a circuit that is gone.

Likewise the difference-amplifier block says "Pole 3 of three: 1.3 nF across
604 ohm is 203 kHz" immediately above code that fits 3.9 nF across 200 Ω. The
fitted value is the right one (3.9 nF × 200 Ω → 204 kHz); the sentence above it
belongs to the 604 Ω version that was reverted.

And `main_board.py`'s reverse-polarity narrative points at "the **unresolved**
−0.40 V against −0.3 V in the review" in one paragraph and then, two paragraphs
later, records that D3 brings the same node to −0.233 V. The first paragraph is
stale with respect to the part that resolved it.

### 6.6 Constants I checked and found still correct

Recorded so nobody re-opens them: the ID0 strap (1 k to the module's 2.49 V
against the main board's 10 k pull-down gives 2.264 V, a valid high against
DS1001's 0.51 × VDDIO = 1.275 V worst-case `VIH`); the JTAG series resistors
(1 k against the 10 k pull-up holds a driven low at 2.5 × 1/11 = 227 mV); the
LMR33630 dividers (100 k/24.9 k → 5.016 V, 124 k/24.9 k → 5.980 V, both against
a 1.000 V reference, and 124 k is inside the datasheet's 1 MΩ ceiling so the
feedforward capacitor it would then require is not needed); the crystal load
capacitors (`C = 2(CL − Cstray)` with the stated stray gives 28 pF, and 27 pF is
the neighbouring standard value — though the 18 pF `CL` itself is unverified,
§3.6); the element current (3.32 V / 3.34 kΩ = 0.994 mA, 14 lines high at any
code = 13.9 mA, matching what the negative rail is costed at); and the LTM4622
soft-start (10 nF is the capacitor the datasheet's own 4.3 ms `tSTART` is
measured with).

---

## Cross-section flags

Each item is an inconsistency involving the documentation or the power design.
Tagged `[power]`, `[docs]`, `[interface]` or a combination. Section references
are to this document.

**Power design**

1. `[power]` **The 1.20 V core absolute maximum is unguarded, and the rail that
   can violate it is already on the board.** `assert_below_abs_max` has one
   threshold (2.75 V) and skips every supply pin by construction. Demonstrated
   (§1.2a): core rail moved to `+3V3` — passes; moved to the board's own `+2V5` —
   passes; a single 10 k resistor from `+2V5` to one core `VDD` ball — passes; a
   dead short — passes. Adding `+2V5` to `hv_rails` does not fix it: it reports
   134 legitimate 2.5 V pins and still not the core ball. Needs a rail-to-pin-class
   map, not another list entry. The LTM4622 footprint fault (§2.1) was a physical
   instance of exactly this — `+2V5` landing on the 1.0 V output — which is why
   the two findings should be read together.
2. `[power]` **No input capacitor across the inverting converter's own terminals.**
   Nothing spans `+12V` and `-6V_A`; U7's PGND is `-6V_A` and the LMR33630
   datasheet's `VIN` description says to bypass directly to it (§3.2). Enumerated
   from the netlist, not inferred.
3. `[power]` **Both SN74AVC4T245 output enables are tied hard low**, against
   SCES576I's explicit "`OE` must be tied to VCCA through a pullup resistor and
   must not be enabled until VCCA and VCCB are fully ramped and stable". The
   module's own rails make that window ~90 ms on every power-up: U9 (`+2V5`,
   VCCA) ramps in 269 ms and U6 (`+3V3_CLK`, VCCB) in 359 ms (§3.3).
4. `[power]` **U14's positive analog rail still has negative worst-case dropout
   margin after the 49.9 k → 45.3 k fix**: −90 mV stacked from the LMR33630's
   ±1.5 % `VFB`, the LT3045's ±2 % `ISET` and the 330 mV maximum dropout at this
   load (the 260 mV headline is the 500 mA figure). The rail only needs ~3.5 V;
   36.5 k would give ~1.2 V of margin (§6.1).
5. `[power]` **`C_SET` on the module's 2.5 V rail contradicts the helper's own
   documented rule.** U9 keeps the 4.7 µF default on a rail its own comment says
   "nothing on it reaches the signal", paying 269 ms for a noise specification it
   cannot use — and that mismatch against U6's 359 ms is what creates flag 3's
   window (§6.4).
6. `[power]` **The two boards disagree about the mezzanine's rails.** The output
   module's `hv_rails` omits `-6V_A`, which the main board declares with a comment
   explaining that a negative rail on a GateMate ball is as fatal as a high one;
   the module's `protected` also omits it where the main board allows it. Adding
   the rail makes the unmodified module fail, so the omission is load-bearing
   (§1.2c, tests T7/T8). The same list still declares four nets deleted with the
   charge pump: `PUMP_P`, `PUMP_N`, `+5V7_A`, `-5V7_A`.
7. `[power]` **Five FPGA supply pins have no decoupling capacitor at all** —
   `VDD_PLL`, `VDD_SER` (×2), `VDD_SER_PLL`, `VDD_CLK` — because the generator's
   decoupling loops key on `^VDD$` and `^VDD_(NA|…|WC)$` only. DS1001 §2.10 asks
   for noise **filters** (not capacitors) on the four core-domain supplies, and
   none is fitted. `VDD_CLK` matters most: it supplies `RST_N` and `POR_ADJ`
   (§3.4).
8. `[power]` **The POR network uses R3a outside its documented purpose.** DS1001
   §3.2.2: with VDD_CLK in 1.8–2.7 V, POR_ADJ should be left open; R3a "is only
   necessary when VDD_CLK < 1.8 V". The arithmetic is exactly right (19.4 ms
   reproduces to the decimal) and the orientation is right, but the VDD_CLK reset
   threshold drops from ~1.44 V typical to ~0.66 V, which disables the POR's
   advertised voltage-drop detection on that rail, and Table 4.8 characterises
   R3a only at 250 k and 500 k so 47 k is an unspecified extrapolation (§3.5).
9. `[power] [docs]` **The element resistor split clears a retired limit.**
   1.69 k + 1.65 k exists only because 1.65 k + 1.65 k = 3.30 kΩ "would fail the
   power-on limit by a hair" — the one-unit-load rule that 0014 retired and that
   `interface.md` now explicitly says no longer exists. An equal split is
   permissible and better matched (§6.2).
10. `[power] [docs]` **The clock-chain part selection rests on the same retired
    budget** ("one unit load before enumeration leaves it about 50 mA"). The parts
    are fine; the recorded rejection of the integrated alternative is not (§6.3).
11. `[power]` **`USB_VBUS` reaches the FT601Q with no capacitor, no series
    resistor and no TVS** — a two-node net from a cable-facing contact straight to
    the bridge. Whether that pin is a supply or a sense input could not be
    established because the FTDI datasheet was unobtainable here (§3.6).
12. `[power]` **Confirmed, not disputed — do not re-open.** Open items E-4 and
    E-5 are arithmetically correct. Recomputed from the LTM4622's own tolerances
    (`VFB` 0.592/0.600/0.608 V, `RFBHI` 60.00/60.40/60.80 k): channel 1 gives
    2.433/2.500/**2.563** V and channel 2 **0.979**/0.999/**1.019** V, matching
    the recorded figures to the millivolt. `VDD_SER`'s 1.00 V minimum is missed at
    nominal, the two windows overlap only over 1.00–1.05 V, and centring on `VDD`
    is the right call (§3.6).
13. `[power]` **The −6 V rail's topology is undocumented by its own datasheet.**
    SNVSAN3F contains no inverting buck-boost configuration; the only occurrence
    of "invert" is "AC inverters" in the applications list. Every absolute maximum
    the topology stresses does check out (`EN`, `PG`, `AGND`-to-`PGND`, `SW`), and
    the `VCC` capacitor is correctly referenced to the device's own ground — but
    the configuration itself rests on TI application notes I did not fetch (§3.2).

**Documentation**

14. `[docs]` `hardware/netlist/README.md` says the project symbol library "holds
    two symbols so far" and tabulates two. It holds **seven**: `LTM4622`,
    `MX25R6435F`, `SN74ALVCH16374`, `SN74LVC1G74`, `LMK1C1104`, `CCHD-957`, and
    `LTC3265` (dead — the charge pump it described is deleted and no generator
    references it).
15. `[docs]` The same README says "The LTM4622 still needs a footprint drawn; its
    `Footprint` field names `lyrebird:Analog_LGA-25_…`, **which does not exist
    yet**." It exists, and it carried the most serious defect in this review round
    (§2.1). The sentence would have told a reader not to look at it.
16. `[docs]` The same README's "Placeholder symbols" table lists four parts as
    placeholders — `ASE-xxxMHz`, `74AUP1G74`, `74HCT574` pairs, `OPA1612AxD` — all
    four of which are now selected real parts (CCHD-957, SN74LVC1G74 +
    LMK1C1104, SN74ALVCH16374, OPA1612AID). Its "Known gaps" section likewise says
    "The element resistor value is still a placeholder"; it is 1.69 k + 1.65 k.
17. `[docs]` The same README's "PCB and schematic generation: tried, does not work
    here" concludes "the flow stops at the netlist". It does not: `regenerate.sh`
    drives `tools/netlist_to_sheets.py` and `kicad-cli` to produce 20 sheet files
    and two schematic PDFs.
18. `[docs] [power]` The same README's section "The absolute maximum is asserted,
    not reviewed" describes what the check catches and nothing about what it
    cannot see. After §1.2 it should say, at minimum, that the check is blind to
    the 1.20 V core maximum, to any path through a resistor array, to any rail not
    in the declared list, and to every component value on the board.
19. `[docs]` **Both `missing.md` files document a command that raises.** Verified
    by running them: the output module's snippet gives `TypeError: 'NoneType'
    object is not iterable` (`build()` returns `None`), and the main board's gives
    `AttributeError: 'list' object has no attribute 'pins'` (`build()` returns
    `(fpga, ftdi, elem_nets)` and the third element is a list). Both files present
    this as the way to regenerate the authoritative list of open pins.
20. `[docs]` `hardware/netlist/README.md`'s "Pins left open on purpose" table
    omits several that are: FT601Q `~{WAKEUP}`, the translator's `1A2`, the
    registers' `1Q8`/`2Q8`, the buffer's `Y3`, and the LT3094's `VIOC`. All are
    correct to leave open (§4); the table should say so, particularly `~{WAKEUP}`,
    which is the only one whose correctness I could not verify.
21. `[docs] [interface]` `interface.md` says "**Every element line sits adjacent
    to a ground pin.**" What both generators build is all 32 element lines on the
    odd pins 1–63 and all 32 grounds on the even pins 2–64 — a solid ground row
    directly opposite each element, with each element flanked *within its own row*
    by two other element lines. That is arguably the better arrangement, but it is
    not what the sentence describes, and a module designer reading it would expect
    interleaving. Recorded as confirmation alongside it: the two boards agree
    pin-for-pin on all 80 mezzanine pins, zero mismatches.
22. `[docs] [interface]` **`MCLK` is the one mezzanine signal with no adjacent
    ground.** It sits on pin 65, whose in-row neighbours are `ELEM31` (pin 63) and
    `OSC_EN_48` (pin 67) and whose opposite-row neighbour is `OSC_EN_441` (pin 66).
    Every element line has a ground opposite; the element *clock* — the signal the
    whole reclocking architecture exists to keep clean — does not. Its neighbours
    are all static, so this is a pinout observation for the first layout rather
    than a fault, but `interface.md`'s adjacency rule does not mention it.
23. `[docs] [interface]` **The `-6V_A` pair sits immediately beside the two ID
    straps.** Pins 71/72 are `-6V_A`, occupying both rows of connector column 36;
    pins 69/70 are `ID0`/`ID1` in column 35, which run across the connector to
    GateMate balls whose input minimum is −0.4 V. A bridge between pins 69 and 71
    — same row, adjacent columns, 1.27 mm apart — puts −6 V on an FPGA ball.
    Moving the negative pair past a ground column costs nothing and there are four
    spare `+5V`/`GND` columns at the tail to trade with.
24. `[docs]` The LT3094 comment asserts "the LT3094's pin description **gives no
    instruction for an unused ILIM**, so the current limit is programmed rather
    than the pin tied". LT3094 Rev 0, ILIM (Pin 6), gives exactly the LT3045's
    instruction: "If the programmable current limit functionality is not needed,
    tie ILIM to GND. Do not float the ILIM pin." The 24.9 k is still a legitimate
    choice (3.75 A·kΩ / 24.9 k = 151 mA against a 56 mA worst case), but the
    stated reason for deviating does not exist (§3.6).
25. `[docs] [power]` **Three comment blocks still describe the deleted charge
    pump**: the LT3094's input ("the inverting pump's output", "LDO− is a 50 mA
    part", "the doubled-then-inverted rail … at the bottom of the USB range") and
    its `ILIM` value ("below what the pump's LDO can deliver into a fault") (§6.5).
26. `[docs]` The difference-amplifier block says "Pole 3 of three: 1.3 nF across
    604 ohm is 203 kHz" directly above code fitting **3.9 nF across 200 Ω**. The
    fitted value is correct; the sentence belongs to the reverted 604 Ω version.
27. `[docs] [power]` `main_board.py`'s reverse-polarity narrative refers to "the
    **unresolved** −0.40 V against −0.3 V in the review" and then, two paragraphs
    later, records that D3 brings the same node to −0.233 V. The first paragraph
    is stale with respect to the component that resolved it.
28. `[docs] [power]` `hardware/verify_power.py`'s docstring says it exists "so
    that changing a component value changes the verdict instead of only the
    prose". Reading the LT3045s and LT3094 by pin number closes part of this, but
    `V_1V0`, `V_2V5`, `V_3V3`, `V_5V` and `V_N6V` remain hand-written constants —
    so swapping the LTM4622's two feedback resistors (test T15, the error the
    generator itself calls the worst single assembly mistake on the board) changes
    neither this file's verdict nor `assert_below_abs_max`'s.
29. `[docs]` Two quoted datasheet figures are wrong in the safe direction: the
    LMK1C1104's additive jitter is given as "17.5 fs typical" where SNAS791D says
    **7.5 fs typical** at 3.3 V (8 fs typical / 20 fs maximum in the table), and
    the LT3094's `EN/UV` threshold is given as "±1.35 V" where the datasheet says
    **1.26 V** typical. Both are figures a part was selected on.
30. `[docs]` **The USB SuperSpeed comment states an inverted convention as fact
    and reasons from it**: "on a B-type receptacle SSTX is what the device
    transmits and SSRX is what it receives, because the cable ties StdA_SSTX to
    the B-side SSRX." There is no crossover in a USB 3.0 cable. The resulting
    fault is in §3.1 and is provable from the netlist alone — the two
    SuperSpeed receive nets are the only multi-node nets on the board with no
    driving pin.
31. `[docs]` **Nothing in the generation path runs ERC.** `main_board.erc` is zero
    bytes and the run log's only warnings concern footprints. SKiDL's ERC is never
    invoked, so a driverless net (§3.1) and an output-to-output net pass silently,
    and the sheets' phantom shorts (§5) are never reported. `check_freshness.py`
    now covering single-node nets is the right shape for this; extending it to
    driver conflicts would have caught the USB fault.
32. `[docs]` **The exported sheets are not a faithful drawing of either netlist**,
    though nothing is dropped: 49 coordinates across the two boards carry global
    labels for two to four electrically distinct nets at the same point, which
    KiCad joins. Two mechanical causes, both in `tools/netlist_to_schematic.py`:
    `collect_pins` walks every unit of a symbol while only unit 1 is drawn (the
    GateMate's 324 pins occupy 71 distinct coordinates, up to 74 pins on one
    point), and `round(v/2.54)*2.54` snaps pins that sit on a 1.27 grid, with
    Python's banker's rounding merging them in pairs (§5). Anyone reading
    `lyrebird-main-schematic.pdf` as a check on the netlist is reading a document
    that asserts shorts the netlist does not contain — including `ELEM21` and
    `GND` on one node.

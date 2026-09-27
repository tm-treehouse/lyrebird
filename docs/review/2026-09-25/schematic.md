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

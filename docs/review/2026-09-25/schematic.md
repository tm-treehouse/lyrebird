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

**(a) The 1.20 V core absolute maximum is not guarded at all (T4).** The
function has one constant, `ABS_MAX_V = 2.75`, and it skips every pin that is
`PWRIN`/`PWROUT` or whose name matches `_SUPPLY_NAME`. So moving the core rail
onto `+3V3` — 3.32 V onto 28 `VDD` balls, `VDD_PLL`, two `VDD_SER` and
`VDD_SER_PLL`, against DS1001 Table 4.1's 1.20 V — builds clean. T15 (below)
confirms the same blindness from the other direction: swapping the LTM4622's
two feedback resistors, which the generator's own comment identifies as "the
worst single assembly error on this board", puts 2.5 V on `+1V0` and the check
says nothing. Skipping supply pins is deliberate and defensible; the
consequence is that the *entire* core-rail hazard is outside the only
automated electrical check either board has. Nothing else covers it either:
`hardware/verify_power.py` carries `V_1V0 = Fact(1.00, "V", DS, "LTM4622 table
value 90.9 k")` as a hand-written constant, so changing the netlist's resistor
does not change its verdict.

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

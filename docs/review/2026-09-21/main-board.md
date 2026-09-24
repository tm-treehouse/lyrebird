# Review — lyrebird-main-reva (digital main board)

Reviewer: independent hardware review pass, 2026-09-21.
Scope: `hardware/netlist/main_board.py`, `hardware/netlist/lyrebird_parts.py`,
`hardware/lyrebird-main-reva/` (netlist, `power.md`, `brief.md`, `bom.csv`,
`missing.md`), decisions 0001/0005/0006/0009/0012, `hardware/interface.md`.

The netlist was regenerated before judging it:

```
export KICAD10_SYMBOL_DIR="/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
./.venv/bin/python hardware/netlist/main_board.py
```

It runs clean: 0 errors, 272 warnings (all of them SKiDL "missing tag" noise from
the anonymous `Part("Device","C")` instantiations in `decouple()`), and
`assert_below_abs_max` passes. 133 parts. Everything below is measured against
that regenerated netlist, not against the checked-in one.

Excluded by instruction: the 12 V wall-wart / isolated-USB redesign is agreed and
deliberately not implemented, and the reference-rail transition-current risk is
the documented lead open item. Neither is reported as a defect; consequences of
the former that are *not* already in `docs/open-items.md` are reported.

---

## 0. Method and what I could not verify

`hardware/datasheets/` contains only `.gitkeep`. Nothing in this repository is a
vendor PDF. Where I state a datasheet fact below I say explicitly whether I
verified it against a fetched vendor document, against a KiCad symbol, or not at
all. `power.md` makes the same admission in its own header and is honest about
it; I have kept that discipline.

Three classes of claim were checked separately, because this project has been
bitten by a confident number that was wrong:

* what the **netlist** actually does (authoritative, re-derived from the circuit
  object rather than read out of the `.net` text);
* what the **comments in `main_board.py`** assert about electrical fact;
* what the **prose** (`power.md`, `brief.md`, `bom.csv`, `missing.md`, the
  decisions) asserts.

All three disagree with each other in places. Section 6 is the list.

Datasheets fetched and read for this review (none are in the repo; I downloaded
them to a scratch directory and extracted the text):

| Part | Document | What I used it for |
| --- | --- | --- |
| CCGM1A1 | Cologne Chip DS1001, September 2026 | Abs max, operating ranges, POR, configuration, JTAG, full 324-ball pin list |
| LTM4622 | Analog Devices LTM4622 Rev. G | Abs max, pin functions, ball map, R_FB and R_FSET tables, decoupling requirements |
| FT601Q | FTDI FT600Q-FT601Q Rev. 1.04 | Pin table with QFN-76 pin numbers, mode straps, crystal, abs max, DC characteristics |

**Could not verify** (stated rather than assumed):

* **LT3045.** analog.com refused the download from this environment and no mirror
  I tried served it. Every LT3045 claim below is marked unverified. The one that
  matters is the SET pin reference current — the netlist's 3.32 V output depends
  on it being exactly 100 µA.
* **MX25R6435F.** Not fetched. The supply range, the quad-enable default and the
  2.5 V timing derating are unverified.
* **ABM8G-30.000MHZ-18-D2Y-T.** Abracon's ordering-code suffix was not decoded
  against its datasheet. See finding M-8.
* **BSS138.** Vgs(th) and R_DS(on) at a 2.5 V gate drive not verified; the
  conclusion (it is fine driving a 100 k pull-up) does not depend on the numbers.
* **The FT601Q reference schematics** (Figures 6.1/6.2/7.2) are images in the PDF
  and did not survive text extraction, so I could not read off FTDI's own
  decoupling values.

---

## 1. Electrical errors that could destroy the board

`assert_below_abs_max` passes. It covers driving pins on protected parts, and I
re-read it: the logic is sound for what it claims. The gaps it leaves by
construction are inputs, straps, passive terminations, off-board drivers, and
the supply pins themselves — which it skips deliberately. Those are what follows.

### E-1 (high) — nothing bounds either FPGA rail if a feedback resistor is wrong

> **Editor's note, added when acting on this review.** The finding is right
> that nothing bounds either rail, and the remedy was worth applying, but the
> *mechanism below is inverted* and the heading has been changed to match.
> An open `R_FB` is **safe**: with no path to ground the FB node is pulled to
> VOUT through the internal 60.4k, the error amplifier sees FB above its 0.6 V
> reference and reduces duty, so the rail collapses to about 0.6 V. A cracked
> resistor browns the rail out; it cannot raise it. The dangerous fault is a
> *wrong or swapped* resistor -- 19.1k on FB2 puts 2.5 V onto `+1V0` against a
> 1.20 V absolute maximum -- or an FB net shorted to ground. The fix applied
> is a poka-yoke rather than a clamp: the core rail's resistor is now 0603
> where the 2.5 V rail's is 0402, so the fatal direction of the swap cannot be
> assembled. The two rails' windows are too narrow for a clamp to sit between
> the worst-case operating maximum and the absolute maximum.



Verified against LTM4622 Rev. G, PIN FUNCTIONS and Table 1.

The 2.5 V and 1.0 V rails are programmed only by `R_FB` from FB to GND
(19.1 k on FB1, 90.9 k on FB2), against a 60.4 k internal resistor from VOUT to
FB. That is the correct topology and the correct values — I checked both against
the datasheet's Table 1, which gives 19.1 k for 2.5 V and 90.9 k for 1.0 V
exactly. The problem is the failure mode, not the value:

* **FB1 open** (cracked 0402, bad joint, unpopulated) → channel 1 regulates to
  its maximum. VOUT abs max is 6 V and VIN is 5 V, so the module survives and
  drives roughly 5 V onto `+2V5`. That rail reaches **nine GateMate bank
  supplies and VDD_CLK** (2.75 V absolute maximum), **four FT601Q VCCIO pins**
  (4.0 V abs max, so the bridge survives), and the flash. The FPGA dies.
* **FB2 open** → roughly 5 V onto `+1V0`, which reaches **VDD ×28, VDD_PLL,
  VDD_SER ×2, VDD_SER_PLL**, absolute maximum **1.20 V**. The FPGA dies
  instantly and spectacularly.

The board asserts its 2.75 V invariant on the *signal* path in software and
leaves the *supply* path — which reaches 45 more balls than any signal does —
guarded by two 0402 resistors. That asymmetry is worth closing: a 2.7 V and a
1.2 V clamp (or a two-channel supervisor holding a rail-discharge FET) cost
almost nothing next to a BGA-324.

This is not hypothetical bookkeeping: `power.md` already records that an earlier
revision shipped an LT3045 with no SET resistor at all, which is the same class
of fault on the 3.3 V rail.

### E-2 (high) — the JTAG header hands an off-board adapter direct, unprotected access to bank WA

Verified against DS1001 §3.4.1 and Table 4.5.

J3 brings `JTAG_TMS`, `JTAG_TCK`, `JTAG_TDI` straight to U1 balls T3, R3 and T2
with nothing but a 10 k pull-up on each. DS1001 §3.4.1 says the configuration
bank operates over the range in Table 4.5, which I read: **VDDIO 1.1 V to 2.7 V**,
`VIN` range `−0.4 V` to `VDDIO + 0.4 V` — that is **2.9 V** with the bank at
2.5 V. Absolute maximum is 2.75 V on the supply.

0006 specifies "an ordinary external FTDI adapter … driven by openFPGALoader".
The common ones (FT2232H mini-module, FT232H breakouts, the Cologne Chip
programmer) are **fixed 3.3 V drivers**. J3 pin 1 is labelled VREF and carries
2.5 V, but VREF is an *output* of this board and an input to adapters that
happen to implement it; a fixed-3.3 V adapter ignores it and destroys the FPGA
on first connection.

`assert_below_abs_max` cannot see this, because the driver is not in the
netlist — this is precisely the hole the brief points at. The fix is cheap and
belongs on the board rather than in a document: **series resistors (≈100 Ω to
220 Ω) on TMS, TCK and TDI**, which with the GPIO's ~1 µA input current cost no
level and limit the clamp-diode current from a 3.3 V driver to a few
milliamps — or a proper 2.5 V-side translator if the fast-JTAG case matters.

Nothing in the repository warns about this. `hardware/interface.md` states
"Nothing on the main board is safe above 2.75 V" and then the one connector a
human physically plugs a third-party tool into has no protection at all.

### E-3 (medium) — `SER_CLK` and `SER_CLK_N` are floating CMOS inputs on a powered rail

Verified against DS1001 §2.10 and Table 5.3.

DS1001 §2.10: "VDD_CLK: Supply voltage for the input pins **SER_CLK, SER_CLK_N**,
RST_N and POR_ADJ." The pin list gives T12 `SER_CLK` and T13 `SER_CLK_N` as
group "Other", reset category 4 (T12) and 1 (T13).

The netlist powers VDD_CLK at 2.5 V and leaves both balls open. A floating input
on a powered receiver sits near mid-rail and can draw crossbar current
indefinitely, and on a differential receiver it can also oscillate. Table 4.5's
`IDD,max = 158 µA` "at GPIO input at transition point" is the GPIO number; the
SerDes clock receiver is not characterised for this.

This is exactly the category the brief flags — an input, invisible to
`assert_below_abs_max`. **Tie both to GND** (or to VDD_CLK). It is two resistors
or two shorts and it removes an unbounded, unmeasured current.

### E-4 (medium) — the +1.0 V rail is below the SerDes supply minimum

Verified against DS1001 Tables 4.2 and 4.3, and LTM4622 Rev. G electrical table.

DS1001 gives **two different minima on the same net**:

| Pin | Operating range | Source |
| --- | --- | --- |
| VDD, VDD_PLL (economy) | 0.95 – 1.05 V | DS1001 Table 4.2 |
| **VDD_SER, VDD_SER_PLL** | **1.00 – 1.15 V** | DS1001 Tables 4.2 and 4.3, and §2.10 |

The netlist puts all four on one `+1V0` net (correct per 0009, which lists them
together). But the LTM4622's own tolerance does not fit the SerDes minimum:

```
VOUT2 = VFB x (1 + RFBHI / RFB)
worst low:  0.592 V x (1 + 60.00k / (90.9k x 1.01)) = 0.979 V
nominal:    0.600 V x (1 + 60.40k /  90.9k)         = 0.999 V
worst high: 0.608 V x (1 + 60.80k / (90.9k x 0.99)) = 1.019 V
```

VFB 0.592/0.600/0.608 V and RFBHI 60.00/60.40/60.80 k are from the LTM4622
electrical table; the ±1 % is the netlist's own `"90.9k 1%"`. So the rail is
**below VDD_SER's 1.00 V minimum at nominal and 21 mV below it worst case**,
while sitting comfortably inside VDD's economy window.

The SerDes is unused here — every SerDes signal ball is open — so nothing
misbehaves in practice. But it is an out-of-spec supply on a powered analog
block, and the design has no recorded position on it. Either raise `+1V0` to
about 1.02 V (RFB 88.7 k E96 gives 1.009 V nominal, still inside VDD economy and
far from the 1.20 V abs max) and note why, or record that VDD_SER is knowingly
run below minimum on a block that is not used.

Worst-case high on `+1V0` is 1.019 V against the 1.20 V core absolute maximum:
comfortable.

### E-5 (low) — 2.5 V worst-case is 2.56 V against a 2.75 V absolute maximum

Same arithmetic on channel 1: `0.608 x (1 + 60.80k/(19.1k x 0.99)) = 2.563 V`
worst case, against VDDIO abs max 2.75 V and the GPIO *operating* maximum of
2.7 V (DS1001 Table 4.5). 187 mV of margin to destruction and 137 mV to
out-of-spec, before any load-step overshoot. The netlist fits 22 µF of COUT,
which is the LTM4622's stated minimum (see M-5) rather than its 47 µF typical,
so transient overshoot is at the larger end of the part's range. Not a defect;
worth knowing that this rail has no room for a tolerance mistake.

---

*Written out of order at the coordinator's request, so that the highest-value
section lands first. Sections 2 to 5 follow below it.*

## 6. Where the netlist, the comments and the prose disagree

This is the largest single finding in the review, and it is not an electrical
one. **Four of the five documents in `hardware/lyrebird-main-reva/` describe a
board that no longer exists.** They describe the netlist as it was before the
LTM4622, the USB receptacle, the crystal, the SPI flash, the JTAG header, the
ferrite and the POR network were wired — and they are confident and specific
about it, which is what makes them dangerous. `docs/open-items.md` is the one
document that *is* current; it says so explicitly ("The main board's
connectivity gaps are wired") and it is right.

Everything below was re-derived from the regenerated circuit object, not read
out of the `.net` file, and not taken from any of these documents.

### 6.1 What the netlist actually contains today

| | Count |
| --- | --- |
| Parts | 138 |
| Nets | 128 |
| Active devices | U1 CCGM1A1, U2 FT601Q, U3 LT3045, U4 LTM4622, U6 MX25R6435F, Q1 BSS138 |
| Connectors | J1 USB 3.0 Micro-B, J2 2×40 mezzanine, J3 2×5 JTAG |
| Other | Y1 30 MHz crystal, FB1 VBUS ferrite |
| Capacitors | 100 (87×100 nF, 5×4.7 µF, 2×22 µF, 2×10 µF, 2×10 nF, 2×27 pF, 1×2.2 µF) |
| Resistors | 27 |
| Unconnected pins, whole board | **76** |

Rail populations, counted from the circuit:

| Rail | Pins on the net | Decoupling caps on it | IC/connector pins |
| --- | --- | --- | --- |
| `USB_VBUS` | 2 | **0** | J1.VBUS, FB1 |
| `+5V` | 20 | 3 | U2.VBUS, U3.IN/EN-UV/PGFB, U4.VIN1/VIN2/RUN1, J2×5 |
| `+3V3` | 10 | 4 | U2.VCC33×3, U2.VDDA, U3.OUT, U3.OUTS |
| `+2V5` | 119 | 51 | U1 ×46 supply balls + POR_EN + RST_N, U2.VCCIO×4, U4.VOUT1, U6.VCC, J3.1 |
| `+1V0` | 63 | 29 | U1.VDD×28, VDD_PLL, VDD_SER×2, VDD_SER_PLL, U4.VOUT2 |
| `+1V0_FT` | 11 | 5 | U2.AVDD, U2.DV10, U2.VD10×4 |

### 6.2 `power.md` — six assertions that the netlist contradicts

| # | `power.md` says | The netlist says | Severity |
| --- | --- | --- | --- |
| P-1 | line 37: `+3V3` feeds "FT601Q `VCC33` ×3, `VDDA`, **`AVDD`**" | `AVDD` is on `+1V0_FT`, **not** `+3V3`. Putting it on 3.3 V is the destroy-the-part bug `open-items.md` records as already fixed | **high** — this page still documents the fault as if it were the design |
| P-2 | line 49: "The 5 V net in the netlist has **no bulk or bypass capacitance and no ferrite** — zero capacitors on `+5V` against 80 elsewhere" | FB1 is fitted; `+5V` carries 10 µF + 4.7 µF + 4.7 µF; there are 100 capacitors on the board, not 80 | high |
| P-3 | lines 77-78: "Its `VD10`/`DV10` pins are unconnected in the netlist, so that regulator has no decoupling today" | `DV10`, `VD10`×4 and `AVDD` are on `+1V0_FT` with the datasheet's 4.7 µF plus four 100 nF | high |
| P-4 | lines 241-249, the whole "What has no source today" section: "The 1.0 V and 2.5 V rails have no supply… the LTM4622 … is not in `main_board.py` … The VBUS ferrite is likewise … absent, and there is no USB connector" | U4 sources both rails from `+5V`; FB1 and J1 are fitted | high — this is the page's closing conclusion |
| P-5 | lines 127-128: "15 mA is 0.75 % of the LTM4622's **2 A** channel rating" | The LTM4622 is **2.5 A per channel** (datasheet title: "Dual Ultrathin 2.5A or Single 5A"). `lyrebird_parts.py`'s docstring has this right and `power.md` and `bom.csv` have it wrong | low, but it is a wrong published number |
| P-6 | line 38: `+2V5` feeds "FT601Q `VCCIO` ×4, 9 GateMate bank supplies, `VDD_CLK`" | Also U6.VCC (the flash), U1.POR_EN, U1.RST_N, J3.1 (JTAG VREF), and twelve resistors — eleven pull-ups plus POR R3a. Line 41 claims "Pin counts are read out of `lyrebird-main.net`, not assumed"; for this rail and for P-1 they were not | medium |

P-1 is the one to act on first. A reader who trusts `power.md` over the netlist
will re-introduce the `AVDD` fault, because the page presents it as the design.

### 6.3 `brief.md` — the status section is a snapshot of a superseded build

Lines 66-76, "Where the board actually is":

| `brief.md` says | Netlist |
| --- | --- |
| "three active devices (CCGM1A1, FT601Q, LT3045)" | six (add LTM4622, MX25R6435F, BSS138) |
| "one 2x40 header" | three connectors (J1, J2, J3) |
| "80 decoupling capacitors and two pull-downs" | 100 capacitors, 27 resistors |
| "leaves **111 pins** unconnected" | **76** |
| "The 1.0 V and 2.5 V rails have no source" | U4 sources both |
| "no USB connector, no crystal, no SPI flash and no programming header" | all four are fitted |

And one claim that is wrong independently of staleness:

**B-1 (medium).** Line 31: "A clock on an ordinary ball is not a toolchain error,
it silently routes through the fabric, **so the assignment is asserted in the
generator rather than hoped for**." There is no such assertion.
`grep -n assert hardware/netlist/main_board.py` returns exactly one call,
`lp.assert_below_abs_max`, plus two comments referring to it. `lp.CLOCK_PINS` is
a plain list and the code indexes `CLOCK_PINS[0]` and `[1]`; nothing checks that
what came back is clock-capable, and nothing would notice if the list were
edited or the symbol's names changed. The claim is exactly the kind this project
has been bitten by: it describes a guarantee that does not exist. Either add the
assertion (`assert "CLK" in str(pin.name)` at the point of use is enough) or
change the sentence.

### 6.4 `bom.csv` — unusable as a buy list

Every one of its six `MISSING` rows is now in the netlist: LTM4622, ferrite,
USB receptacle, SPI flash, programming header, crystal and load capacitors. It
has no row at all for U4, U6, J1, J3, Y1, FB1 or Q1, and its passive rows
(C1-C45, C46-C73, C74-C76, C77-C80, R1-R2 — 80 caps and 2 resistors) are twenty
capacitors and twenty-five resistors short of what the build emits.

Two of its notes are individually wrong against the netlist:

* U3 row: "**`EN/UV` is unconnected in the netlist**" — it is tied to IN, which
  is what the LT3045 datasheet asks for.
* C74-C76 row: "The bridge `VD10`/`DV10` pins … have no decoupling in the
  netlist" — they do.

One of its notes is **right and worth keeping** — and it is the only place in
the repository that still records this: the C1-C45 row's "0009 also requires a
noise filter between every regulator and the FPGA, **which is not in the
netlist**". I confirmed that: the only inductive part in `main_board.py` is FB1
at VBUS. See D-4.

And its J2 row is right where the code comment is wrong — see 6.5.

### 6.5 `main_board.py`'s own comments against its own netlist

The comments are in much better shape than the prose: I checked every comment
that asserts an electrical fact against the vendor datasheet, and all but one of
them hold (section 3 lists them individually). The exception:

**C-1 (low).** The mezzanine comment says "**The 8 spare pins** become extra
ground and **a second supply pin** rather than being left open." The netlist
allocates 64 pins to elements and grounds, 1 to MCLK and 5 to control, leaving
**10** spare, which the `while idx < len(mez_pins)` loop fills as **five +5V and
five GND**. `bom.csv`'s J2 row and `power.md`'s boundary section both state this
correctly — so here the prose is right and the comment is wrong, which is the
mirror image of 6.2 and is why all three have to be checked separately.

**Retracted.** I initially read `lyrebird_parts.translator()` as dead code
because `main_board.py` never calls it. It is called by
`hardware/netlist/output_module.py:179`, which is correct per 0012 — the
translator belongs on the module. Not a finding.

### 6.6 What I recommend

`missing.md` already has the right instinct — "This is deliberately not a
snapshot. The netlist is the authority on completeness, and it changes" — and it
is the one document in the directory that has not gone stale, precisely because
it refuses to state a count. `brief.md`'s status section, `power.md`'s rail
table and closing section, and `bom.csv` in its entirety all state counts.

The cheapest fix is to make them derived rather than written: `main_board.py`
already walks the circuit, and emitting `bom.csv` and a rail table from
`build()` would make staleness impossible rather than merely discouraged. Short
of that, delete the counts.

---

## 2. Unconnected pins, with a verdict on each

**76 unconnected pins** on the regenerated netlist (the figure was 72 before the
E-3 fix tied `SER_CLK`/`SER_CLK_N`). Every one is listed below. I re-derived
them from the circuit object with `pin.is_connected()` rather than reading a
document.

### U1 CCGM1A1 — 70 open of 324

| Pins | What they are | Verdict |
| --- | --- | --- |
| `IO_EB_*` ×18 | The whole of bank EB, unused | **Deliberate.** DS1001 §2.3: "Unused GPIO banks should still be supplied with power to avoid interference. Any GPIO voltage available on the PCB can be used." `VDD_EB` ×5 is on `+2V5`, so this is done correctly. See U-1 below for the one thing still owed |
| `IO_EA_*` ×12 | Spare after 42 bridge signals took NA+NB+EA | Deliberate |
| `IO_SB_*` ×14 | Spare in the clock bank | Deliberate |
| `IO_WC_*` ×13 | Spare after 5 control lines | Deliberate |
| `IO_WB_*` ×4 | Spare after 32 element lines took SA+WB | Deliberate |
| `CLK2/IO_SB_A6`, `CLK3/IO_SB_A5` | Two spare clock-capable inputs | Deliberate; `CLK0` and `CLK1` carry FT_CLK and MCLK |
| `IO_WA_B5/SPI_FWD` | SPI forward, for chaining several FPGAs off one flash | **Deliberate and correct.** DS1001 Table 3.2 gives it as an output ("O low, driver strength 12 mA"), reset category 2, and Figure 3.8 uses it only in a multi-FPGA chain. An output may be left open. The code comment says exactly this |
| `N16 NC` | | **Deliberate and required.** DS1001 pin list, verbatim: "Not connected. **This pin must be left open.**" |
| `V12 SER_RTERM` | SerDes line termination | **Deliberate, but see U-2** |
| `U11/V11 SER_RX_P/N`, `U13/V13 SER_TX_P/N` | SerDes data pairs | **Deliberate, see U-3** |

### U2 FT601Q — 1 open of 77

| Pin | Verdict |
| --- | --- |
| 19 `Reserved` | **Deliberate and required.** FT601Q datasheet §3, verbatim: "Reserved — **Do not connect.** NC". The code comment cites this correctly |

### U3 LT3045 — 1 open of 11

| Pin | Verdict |
| --- | --- |
| 4 `PG` | **Deliberate and datasheet-correct.** LT3045 Rev. C PIN FUNCTIONS: "PG is an open-collector flag… **If the power good functionality is not needed, float the PG pin.**" Note the LT3045's power-good output is therefore unused on a board whose 3.3 V rail takes 359 ms to come up (see D-6) — a PG flag would have been a free sequencing observable, but leaving it open is not an error |

### U4 LTM4622 — 3 open of 25

| Pin | Verdict |
| --- | --- |
| E5 `COMP1`, A5 `COMP2` | **Deliberate and datasheet-correct.** LTM4622 Rev. G PIN FUNCTIONS: "**The device is internally compensated. Do not drive this pin.**" They are tied together only for PolyPhase parallel operation, which this design does not use |
| C3 `INTVCC` | **Deliberate and datasheet-correct.** "Internal 3.3V Regulator Output… **This pin is internally decoupled to GND with a 2.2µF low ESR ceramic capacitor. No additional external decoupling capacitor needed.**" This is the one I most expected to be a bug and it is not |

### J1 USB3_B_Micro — 1 open of 11

| Pin | Verdict |
| --- | --- |
| 4 `ID` | **Deliberate.** A B-type receptacle on a pure device port; the code comment says "this is a device port, not OTG". Correct |

### J2, J3, U6, Y1, Q1, FB1 and all passives — 0 open

The mezzanine (80/80), the JTAG header (10/10) and the flash (8/8) are fully
wired. The crystal's two ground pads are connected — I checked, because the
KiCad `Crystal_GND24` symbol names them `G` and the code matches on that string,
which would silently connect nothing if the symbol used `GND`. It does not:
Y1.2 and Y1.4 are both on `GND`.

### The three open pins that are *not* fully justified

**U-1 (low) — unused I/O are open at the board level and undefined at the
bitstream level.** 61 GPIO balls are open on a board where every bank supply is
powered. DS1001 Table 3.2's reset category 1 is "Pin disabled, high-z", so they
float until the bitstream says otherwise, and Table 4.5 gives the GPIO's
programmable `RPU`/`RPD` as 50 kΩ. Floating CMOS inputs on a powered bank draw
crossbar current — Table 4.5 puts it at `IDD,max = 158 µA` per pin "at GPIO
input at transition point". 61 pins × 158 µA is **9.6 mA**, which is 64 % of the
entire 15 mA that `power.md` budgets for the 2.5 V rail. It will not be that bad
in practice, but nothing in the repository constrains it: `hdl/constraints/`
should pin unused I/O to a defined state, and no document says so. This is a
board-level open pin whose resolution lives in the HDL, which is exactly the
kind of thing that falls between two reviews.

**U-2 (low) — `SER_RTERM` open is probably right and the datasheet does not
quite say so.** DS1001 Table 4.3 lists `RTERM,REF` as 198/200/202 Ω and calls it
the "Internal calibration reference resistor" — the min/max on something
described as internal is confusing. Figure 5.4 and its Case 3 ("200 Ω
termination **must** be assembled") show an external 200 Ω, but the figure is
drawn for the CCGM1A2's `SER1_RTERM` at V15, and Case 1 (CCGM1A1 assembled)
says only that R1 is not assembled in the *power-on-reset* role that ball takes
on the A1. **The datasheet nowhere states what to do with CCGM1A1's V12 when the
SerDes is unused.** Leaving it open is the reasonable reading and it is what
Cologne Chip's own evaluation board would tell us, which I could not check.
Record that if the SerDes is ever used, V12 needs a 200 Ω 1 % to ground.

**U-3 (low) — the SerDes data pairs are open on a powered SerDes.**
`VDD_SER` ×2 and `VDD_SER_PLL` are on `+1V0`, so the block is alive, and all
four of its differential I/O are open. Less hazardous than E-3's single-ended
case: Table 4.3 gives `RTERM = 100 Ω` internal differential termination, so each
pair is terminated across itself and only the common mode floats. Table 4.3 also
gives `ISER,leakage = 0.324 mA`, so the cost is bounded and small. The clean
alternative — not powering `VDD_SER` at all — is not offered by the datasheet in
any form, and 0009 explicitly puts these on the core rail. **Verdict: accept, and
note that it is accepted rather than unexamined**, which is the status it has
today.

---

## 3. Datasheet conformance, part by part

### 3.0 The symbols themselves

Before checking the wiring I checked the ball maps, because `main_board.py`'s
header claims "Bank allocation is against the real ball map in the stock KiCad
GateMate symbol, not invented" and everything downstream depends on that being
true. I parsed the datasheet pin lists and compared them mechanically.

| Symbol | Result |
| --- | --- |
| `FPGA_CologneChip_GateMate:CCGM1A1` (stock KiCad 10) | **All 324 balls match DS1001 Table 5.3 exactly.** The only three differences are notation: `~{SPI_CS}`/`SPI_CS_N`, `~{RESET}`/`RST_N`, `~{CFG_FAILED}`/`CFG_FAILED_N`. Ball counts match Table 5.2 too: 162 GPIO, 78 power, 74 ground, 5 SerDes, 5 other |
| `lyrebird:LTM4622` (project symbol) | **All 25 balls match the LTM4622 Rev. G PIN FUNCTIONS section exactly** — VIN1 (D3,E2), VIN2 (A2,B3), GND (C1,C2,B5,D5), VOUT1 (D1,E1), VOUT2 (A1,B1), RUN1 (D2), RUN2 (B2), FB1 (E4), FB2 (A4), TRACK/SS1 (E3), TRACK/SS2 (A3), PGOOD1 (D4), PGOOD2 (B4), COMP1 (E5), COMP2 (A5), INTVCC (C3), FREQ (C4), SYNC/MODE (C5) |
| `Interface_USB:FT601Q` (stock KiCad 10) | All 27 signals I checked match the QFN-76 column of the FTDI pin table, plus pin 77 = exposed pad on GND, which the datasheet's 76-pin list does not carry and which is correct for QFN-76-1EP |
| `lyrebird:MX25R6435F` (project symbol) | Matches the datasheet's 8-PIN SOP (200 mil) diagram exactly: 1 CS#, 2 SO/SIO1, 3 WP#/SIO2, 4 GND, 5 SI/SIO0, 6 SCLK, 7 RESET#/SIO3, 8 VCC |

That is a genuinely good result and it is the foundation the rest of the board
stands on. The claim in the file header is true.

### 3.1 CCGM1A1 (U1)

**Verified correct.** Each of these I read in DS1001 rather than inferring:

* Core at 1.0 V on VDD ×28 — Table 4.2, economy mode 0.95/1.0/1.05 V. §2.10:
  "Economy mode: VDD = 1.0 V ± 50 mV".
* All nine bank supplies and `VDD_CLK` at 2.5 V — §2.10, "The voltage range of
  GPIO banks and VDD_CLK can be set from 1.1 V to 2.7 V"; Table 4.5 confirms.
* **Bank EB is unused and still powered** — §2.3: "Unused GPIO banks should
  still be supplied with power to avoid interference."
* `POR_EN/IO_WA_A3` → `+2V5` — §3.2.2: "POR_EN has to be connected to VDD_WA
  (1.1 .. 2.7 V)." `VDD_WA` is on `+2V5`, so this is correct.
* `RST_N` → `+2V5` — §3.2.2: "Pin RST_N must be connected to VDD_CLK."
  `VDD_CLK` is on `+2V5`.
* `CFG_MD[3:0]` all to GND — Table 3.1 gives `0b0000` = "SPI Active Mode
  CPOL = 0, CPHA = 0", and §3.3.1 says these pins "must always be connected to
  either GND or VDD_WA", so the direct tie is explicitly sanctioned, not just
  tolerated. 0006 and `brief.md` both describe this correctly.
* SPI flash pull-ups on `SPI_CS_N`, `SPI_D2`, `SPI_D3` — Figure 3.7 (quad-I/O)
  shows exactly three 10 k pull-ups to `VDD_WA` on those three nets, and
  Figure 3.6 needs the same three for the single/dual case. The code comment's
  reasoning is correct.
* JTAG pull-ups on TMS, TCK, TDI and none on TDO — Figure 3.10 shows three 10 k
  to `VDD_WA`; TDO is an output.
* **No power-sequencing constraint exists**, so gating the core rail while the
  2.5 V rail is up indefinitely is legal. §3.2.1, POR features list, verbatim:
  "**No restrictions concerning order of voltage switch-on.**" 0009's claim
  ("there are no restrictions on rail ordering, so no sequencer is needed") is
  therefore correct — I went looking for a sequencing violation here and there
  is none.

**D-1 (high) — `CFG_FAILED_N` has no pull-up, and the datasheet requires one.**

DS1001 §3.3.3, page 140, verbatim: "**`CFG_FAILED_N` requires a pull-up
resistor.**" Table 3.2 describes V2 as "I/O, pull-up, high, **open drain**,
driver strength 12 mA".

In the netlist, `CFG_FAILED_N` is U1.V2 and J3 pin 10 and nothing else:

```
CFG_FAILED_N -> ['U1.V2(IO_WA_A2/~{CFG_FAILED})', 'J3.10(Pin_10)']
```

`main_board.py` passes `pu=False` for this signal. The three JTAG signals next
to it in the same loop get pull-ups because Figure 3.10 asks for them; the
requirement for `CFG_FAILED_N` is a sentence of prose in a different section and
it was missed. Consequences: the open-drain output has no pull-up, so
"configuration successful" (Table 3.3, `CFG_DONE`=1 `CFG_FAILED_N`=1) can never
be read, and J3 pin 10 floats into whatever the adapter presents. **Fit a 10 k
to `+2V5`.** It is a one-word change — `pu=True` — and it is the only outright
datasheet violation I found on the FPGA.

**D-2 (medium) — the POR network defeats the VDD_CLK supervisor it is attached
to, and the datasheet says this rail does not need the network at all.**

The arithmetic in the comment is **right**; I recomputed every step of it
against DS1001 §3.2.2's formula and got the same answers — `R3a‖75k` = 28.89 k,
`R3a‖133k` = 34.73 k, threshold 0.658 V, `ln(2.5/1.842)` = 0.3057, **t = 19.4 ms**.
That is not the problem. The problem is what the network is for:

* §3.2.2, verbatim: "With `VDD_CLK` in the range **1.8 .. 2.7 V (normal
  operation), `POR_ADJ` should be left open.** Optionally, a capacitor can be
  connected to ground to improve noise suppression." This board's `VDD_CLK` is
  2.5 V — squarely in that range.
* "`R3a` will decrease the threshold level. **This is only necessary when
  `VDD_CLK` < 1.8 V** to avoid a permanent reset state. **There will be no reset
  condition when `R3a` ⩽ 100 kΩ.**"
* The `t_reset` formula the comment uses is introduced by: "**For very low
  `VDD_CLK` voltages** only a dynamic reset generation by means of `R3a` and
  `C1` circuitry is possible."

So `R3a` = 47 k is inside the range where, in the datasheet's own words, there
is **no reset condition** — the static `/ResetIO` comparator never asserts at
any `VDD_CLK`. The code comment reads that as a benign property ("it cannot hold
the part in reset"), and as far as it goes that is a correct reading. What it
does not say is the other half: §3.2.1 lists "**Voltage drop detection for VDD
and VDD_CLK voltages**" as a POR feature, and fitting `R3a` at 47 k **switches
the VDD_CLK half of that off permanently**. The board loses brown-out detection
on the rail that powers all nine GPIO banks, in exchange for a 19.4 ms delay it
does not need, on a design the datasheet says needs no external components
("Using the POR module, in many cases no external components are required").

The comment also justifies the delay against "2.5 V comes up … in about 4.3 ms
of programmed soft start". That is backwards as a requirement: the datasheet's
instruction is "the reset time must be adjusted to the slope time of the
`VDD_CLK` ramp-up", i.e. long enough — the built-in threshold detector already
satisfies that at 2.5 V without help.

**Recommendation: delete R3a, keep C1.** The 2.2 µF to ground is explicitly
blessed ("a capacitor can be connected to ground to improve noise suppression")
and is the whole of what §3.2.2 asks for at 2.5 V. That restores the supervisor.
If the 19.4 ms delay is genuinely wanted for some other reason, that reason
needs writing down, because the cost is not currently recorded anywhere.

**D-3 (medium) — five supply balls have no decoupling and the datasheet asks for
filters on four of them.**

DS1001 §2.10, verbatim, about `VDD`, `VDD_PLL`, `VDD_SER` and `VDD_SER_PLL`:
"**All these voltages should be connected to noise filters.**"

Counting capacitors per rail from the circuit:

| Ball | Count | Dedicated 100 nF in the netlist |
| --- | --- | --- |
| `VDD` | 28 | 28 ✔ |
| `VDD_NA…VDD_WC` | 45 | 45 ✔ |
| **`VDD_PLL`** | 1 | **0** |
| **`VDD_SER`** | 2 | **0** |
| **`VDD_SER_PLL`** | 1 | **0** |
| **`VDD_CLK`** | 1 | **0** |

`main_board.py` decouples exactly `^VDD$` and `^VDD_(NA|NB|EA|EB|SA|SB|WA|WB|WC)$`
— the two regexes that enumerate the bulk supplies — and the five singleton
supply balls fall through both. `VDD_PLL` is the PLL's "clean analog supply
voltage for DCO" (Table 4.7) and is the one that least tolerates it; `VDD_CLK`
supplies the reset and clock input receivers and is the reference the POR
threshold is measured against. The comment above the loop says "One per supply
ball is the floor, not the design", which is true of the balls it covers and not
of these five.

**D-4 (medium) — 0009's noise-filter requirement is not implemented anywhere.**

0009: "**Fit noise filters between every regulator and the FPGA.** The GateMate
datasheet asks for this explicitly." I verified both halves: DS1001 §2.10 does
ask (quoted above), and the netlist does not have them —
`grep FerriteBead hardware/netlist/main_board.py` returns exactly one part, FB1
at VBUS, and there are no other inductors. `bom.csv`'s C1-C45 row is the only
place in the repository that still records this gap; `open-items.md` does not
list it, and its "Closed" section reads as though the main board's power tree is
complete. It is not — a stated requirement from an accepted decision is
unbuilt.

### 3.2 FT601Q (U2)

Every electrical claim in `main_board.py`'s bridge section checks out against
FTDI's datasheet. I list them because the coordinator's note is exactly right
that a comment and the code can agree and both be wrong, and here they agree and
are both right:

| Comment claims | Datasheet says | Verdict |
| --- | --- | --- |
| `AVDD` is a 1.0 V PLL supply with a 1.4 V absolute maximum, not a 3.3 V pin | Pin table: "`AVDD` +1.0V power input for PLL. PWR 2". Table 5.1: "AVDD PLL Supply Voltage −0.5 to +1.4 V" | ✔ exactly right |
| `DV10` out, `VD10` and `AVDD` in, 4.7 µF to ground, "what the datasheet asks for verbatim" | "`DV10` +1.0V power output from internal LDO. **Connecting to VD10 and AVDD, with a 4.7uF cap to ground is recommended.**" | ✔ verbatim is the right word |
| `+1V0_FT` is a separate net because the rail is "not to be used for external devices" | §4: "The LDO regulator generates the +1.0V power supply for driving the internal core of the device. **Not to be used for external devices.**" | ✔ |
| `RREF`: "connect 1.6K 1% resistor to ground… Not a value to round" | "`RREF` PHY reference resistor input pin. **Connect 1.6K Ω 1% resistor to ground**, provides reference voltage to USB2 PHY" | ✔ |
| Crystal 30 MHz ±20 ppm, 18 pF, 50 Ω ESR; an oscillator will not do | §4.5: "30MHz ±20ppm Crystal 18pF 50 Ohm −40°C ~ 85°C… **It is not possible to replace the crystal with an oscillator or other clock source by tying XO to GND.**" | ✔ |
| Load caps from `C = 2 × (CL − Cstray)` with "the 2.0 pF maximum pin capacitance from the datasheet" | DC characteristics: "`Cp` Pin Capacitance — — **2.0** pF" | ✔ the cited number exists and is 2.0 pF |
| `RESET_N` pull-up goes to VCCIO "because the I/O absolute maximum is VCCIO + 0.5 V" | Table 5.1: "IOs DC Input Voltage −0.5 to **+VCCIO+0.5** V" | ✔ |
| `SIWU_N` is reserved and wants an external pull-up | Pin table: "`SIWU_N` **Reserved. Add external pull up in normal operation.** I 10" | ✔ |
| `GPIO[1:0]` are the power-on FIFO mode straps; `00` selects 245 synchronous FIFO | §4: "At the power up, FT600 or FT601 sets the chip to 245 synchronous FIFO mode or multi-channel FIFO modes depending on the GPIO[1:0] input" — table row `0 0` → "1 channel, 245 Synchronous FIFO mode" | ✔ — I went in expecting this to be the wrong one, because FT60x mode is often described as an EEPROM setting. It is a strap, *while the chip configuration is left at default* |
| `WAKEUP_N` is low when USB is active, high in suspend, so it needs inverting to drive RUN2 | Pin table: "`WAKEUP_N` Suspend/Remote Wakeup pin **by default Low when USB is active, high when USB is in suspend**… I/O 16" | ✔ — and the pin really is an I/O, so the 100 k pull-up does not fight a push-pull output when the remote-wakeup direction is used |
| The VBUS ferrite is in FTDI's bus-powered reference | §6.1: "**A ferrite bead is connected in series with the USB power supply** to reduce EMI noise from the FT60x and associated circuitry being radiated down the USB cable" | ✔ |
| `Reserved` (pin 19) left open, "the datasheet says do not connect" | "`Reserved` **Do not connect.** NC 19" | ✔ |

**One caveat on the GPIO strap**, not currently recorded: the datasheet adds "To
enable the GPIO function, the chip configuration must be updated to set the GPIO
function." The straps select the mode *only while the internal configuration is
at its default*. If anybody ever runs FTDI's chip-configuration programmer
against this board and enables the GPIO function, the two 10 k pull-downs stop
selecting 245 mode and start loading two outputs. Harmless electrically
(250 µA), fatal functionally. Worth one sentence next to the straps.

**D-5 (low) — `VDDA` has no dedicated decoupling.** The netlist places one
100 nF per `VCC33` ball (three) and nothing at `VDDA`, which is the PHY analog
3.3 V supply and sits on the same `+3V3` net. FTDI's own reference schematics
are Figures 6.1/6.2, which are **images** in the PDF and did not survive text
extraction, so **I could not verify what FTDI actually asks for here** — this is
stated, not assumed. What I can say is that the datasheet distinguishes `VDDA`
("+3.3V power input for USB2.0 and USB3.0 PHYs") from `VCC33` ("power input for
chip and internal LDO") as separate pins with separate descriptions, and the
netlist treats them as one node with no local capacitor at `VDDA`. Fit one, and
consider the ferrite between `VCC33` and `VDDA` that is conventional on this
family; the cost is two parts.

**D-11 (low) — the 185 mA figure is a different mode's typical.** The FT601Q DC
table gives `Icc_3` = 185 mA under the condition "Active, SuperSpeed,
**Multi-Channel FIFO mode**". This board runs 245 Synchronous FIFO mode, for
which the datasheet publishes no VCC current at all. 0009 and `power.md` both
present 185 mA as "the datasheet typical" for this design without the condition.
The idle figure they also use is sound: `Icc_1` = 70 mA "Idle, SuperSpeed"
matches 0009's "the bridge idles near 70 mA" exactly.

### 3.3 LT3045 (U3)

`lp.lt3045_housekeeping()` quotes the datasheet in its docstring for each pin.
I fetched the datasheet (Rev. C) and every quote is accurate:

| Pin | Netlist | Datasheet |
| --- | --- | --- |
| `SET` | 33.2 k 0.1 % to GND + 4.7 µF | "SET sources a precision 100µA current… `VSET = ISET • RSET`". `ISET` = 99/100/101 µA at 25 °C, 98/100/102 µA over temperature. **33.2 k × 100 µA = 3.32 V**; worst case 3.25 V to 3.39 V, inside the FT601Q's 3.0–3.6 V window as the comment claims ✔ |
| `EN/UV` | to IN | "**If unused, tie EN/UV to IN. Do not float the EN/UV pin.**" ✔ |
| `ILIM` | to GND | "**If the programmable current limit functionality is not needed, tie ILIM to GND.**" ✔ |
| `PGFB` | to IN | "**Tie PGFB to IN if power good and fast start-up functionalities are not needed**" ✔ as written — but see D-6 |
| `PG` | open | "If the power good functionality is not needed, float the PG pin." ✔ |
| `OUTS` | on `+3V3` with OUT | "For optimal transient performance and load regulation, Kelvin connect OUTS directly to the output capacitor and the load." ✔ topologically; the Kelvin part is a layout instruction |

**D-6 (high) — the 3.3 V rail takes about 360 ms to come up, and nothing
records it.**

This is the interaction of two individually-correct choices. The datasheet gives
the soft-start time explicitly:

> `tSS ≈ 2.3 • RSET • CSET` (Fast Start-Up Disabled)
> Ramp-up rate from 0 to 90 % of nominal VOUT

```
tSS = 2.3 x 33.2 kΩ x 4.7 µF = 359 ms
```

Fast start-up is disabled **because `PGFB` is tied to IN**. The datasheet is
explicit that these are the same decision: "Tie PGFB to IN if power good **and
fast start-up** functionalities are not needed", and "the 2 mA current source
remains engaged while PGFB is below 300 mV". With PGFB at 5 V the 2 mA source
never engages and the 4.7 µF charges at 100 µA.

The 4.7 µF itself is correct and deliberate — it is the condition under which
the 0.8 µVRMS noise figure 0009 quotes is specified (datasheet noise row:
"ILOAD = 500mA, BW = 10Hz to 100kHz, COUT = 10µF, **CSET = 4.7µF**, 1.3V ≤ VOUT
≤ 15V"). `lyrebird_parts.py`'s docstring says exactly this and is right. The
datasheet's own words for the trade are: "Adding a capacitor from SET to GND
improves noise, PSRR and transient response **at the expense of increased
start-up time**", and the whole point of the fast-start-up circuit is to let you
have both.

Consequences nobody has written down:

1. **The FT601Q sees `VCCIO` up roughly 355 ms before `VCC33`.** Channel 1 of
   the LTM4622 reaches regulation in ~4.3 ms of programmed soft start. FTDI's
   datasheet text states no supply-ordering requirement — I looked, and the
   reference figures that might show one are images I could not read — so I
   cannot call this a violation. I can say it is a 355 ms ordering skew that
   arrived as a side effect of a noise capacitor, that nobody chose it, and that
   it should be checked against FTDI before a board is built.
2. **USB enumeration.** The PHY's 3.3 V supply is not in regulation until
   ~360 ms after VBUS. A device is expected to be able to respond to the host
   well before that. This is a bring-up risk on the current bus-powered design
   and it does not go away with the wall-wart redesign, because the LT3045 and
   its 4.7 µF stay.
3. The ~20 ms POR delay on the FPGA (D-2) was sized against a 4.3 ms rail and is
   invisible next to this one.

**The fix is the configuration the datasheet intends**: replace the `PGFB`-to-IN
tie with the two-resistor divider from OUT (`0.3V • (1 + RPG2/RPG1)`, with
RPG1 < 30 k so `IPGFB` can be ignored), which engages the 2 mA fast start-up and
brings `tSS` down by a factor of 20 to roughly 18 ms, and gets a working
power-good flag on `PG` for free. That is two resistors against a 360 ms rail.

**D-7 (medium) — the 3.3 V output capacitor is at the datasheet minimum in
nominal terms, which puts it below minimum in effective terms.** LT3045 PIN
FUNCTIONS, OUT: "**For stability, use a minimum 10µF output capacitor** with an
ESR below 20 mΩ and an ESL below 2 nH." The netlist fits exactly one 10 µF 0805
(plus three 100 nF). A 10 µF 0805 X5R at 3.3 V bias typically delivers 6–8 µF.
An LDO below its minimum `COUT` does not degrade gracefully; it oscillates.
Either specify the dielectric and voltage rating so the *effective* value is
≥10 µF, or fit 22 µF. The BOM currently specifies neither ("dielectric, voltage
rating and manufacturer open"), so today there is nothing stopping a 10 µF X7R
0402 that lands at 4 µF.

**Two small corrections to `power.md` while I was in this datasheet**, both in
its favour:

* Line 62, "`I_GND = 2 mA` (estimate; **confirm against the datasheet**)" — the
  datasheet's first page gives "Operating quiescent current is nominally
  **2.2 mA**". The estimate was good and the TODO can close; `I(5V) = 187 mA`
  stands.
* Lines 69-70 compute dissipation against a 3.30 V output; the netlist programs
  **3.32 V**, which lowers the figures slightly (357 mW rather than 361 mW at the
  USB maximum). Immaterial to the conclusion, and 0009's "roughly 400 mW" is
  still conservative.

### 3.4 LTM4622 (U4)

Everything in this block is correct, and it is the best-verified part of the
board. Checked against Rev. G:

| Netlist | Datasheet | Verdict |
| --- | --- | --- |
| `R_FB1` = 19.1 k for 2.5 V, `R_FB2` = 90.9 k for 1.0 V | Table 1, VFB Resistor Table: VOUT 2.5 V → **19.1 k**, VOUT 1.0 V → **90.9 k**. Internal `RFBHI` = 60.4 k 0.5 % | ✔ both are the table values, not derived-and-rounded |
| `R_FSET` = 649 k from FREQ to GND for 1.5 MHz | "To reduce switching current ripple, 1.5MHz to 2.5MHz operating frequency is **required** for 2.5V to 5.5V output with RFSET to GND." Table: VOUT 2.5 V → fSW 1.5 MHz → **RFSET 649 kΩ** | ✔ and it is required, not optional, for the 2.5 V channel |
| 1.5 MHz is safe for the 1.0 V channel: 133 ns on-time against a 20 ns minimum | `tON(MIN)` = **20 ns**. D = 1.0/5.0 = 0.2, × 667 ns = 133 ns | ✔ arithmetic and the cited limit both check |
| `SYNC/MODE` to GND | "**Tie this pin to ground to force continuous synchronous operation at all output loads.**" | ✔ and the comment's reason (Burst Mode is wrong next to an audio board) is sound |
| 10 nF on `TRACK/SS1`/`SS2` → 4.3 ms | "There's an internal **1.4 µA** pull-up current from INTVCC on this pin, so putting a capacitor here provides soft-start function." 10 nF × 0.6 V / 1.4 µA = **4.29 ms** | ✔ |
| `RUN1` tied to `+5V` | Abs max: "RUN1, RUN2 … **−0.3V to VIN + 0.3V**", and "Enables chip operation by tying RUN above 1.27V. **Do not float this pin.**" | ✔ legal, and both RUN pins are driven |
| Both `VIN1` and `VIN2` on `+5V` | "the module internal control circuity is running off VIN1. **Channel 2 will not work without a voltage higher that 3.6V present at VIN1.**" | ✔ |
| `PGOOD1/2` pulled up to `+2V5` | Abs max PGOOD −0.3 to 18 V | ✔ |
| `INTVCC`, `COMP1`, `COMP2` left open | See section 2 — all three are datasheet-mandated opens | ✔ |
| `+5V` carries 10 µF + 4.7 µF + 4.7 µF | "For each regulator channel, **one piece 4.7µF input ceramic capacitor is required**"; DECOUPLING REQUIREMENTS `CIN` 4.7 µF min / 10 µF typ | ✔ two 4.7 µF for two channels plus bulk. Layout must place one at VIN1 and one at VIN2 — "directly between BOTH VIN1 and VIN2 pins and GND pins" |

**D-8 (medium) — both output capacitors are at the stated minimum, with the same
derating problem as D-7.** DECOUPLING REQUIREMENTS: `COUT` **22 µF minimum,
47 µF typical**. The netlist fits one 22 µF 0805 on each of `+2V5` and `+1V0`.
At 2.5 V bias a 22 µF 0805 X5R commonly lands near 15 µF, i.e. **below the
datasheet minimum**, on a channel whose loop compensation is internal and
therefore not adjustable. The 1.0 V channel derates far less and is comfortable.
The per-ball 100 nF parts (51 on `+2V5`, 29 on `+1V0`) do not substitute for
bulk at the loop's crossover. Specify the part so the effective value clears
22 µF, or fit 47 µF on `+2V5`.

**And the part is 2.5 A per channel, not 2 A** — datasheet title, "Dual
Ultrathin **2.5A** or Single 5A Step-Down DC/DC µModule Regulator".
`lyrebird_parts.py` says 2.5 A and is right; `power.md` line 127 and `bom.csv`
say 2 A and are wrong. Nothing depends on it — the loads are 15 mA and 149 mA —
but it is a wrong published number of the kind this project keeps finding.

### 3.5 MX25R6435F (U6)

**Verified correct.** Supply range "Wide Range VCC **1.65V-3.6V** for Read, Erase
and Program Operations", which is the whole reason the part was chosen and
`lyrebird_parts.py` states it accurately. At `VDD_WA` = 2.5 V it is in range. The
SOP-8 pin map matches. `WP#/SIO2` and `RESET#/SIO3` are held high by the two
10 k pull-ups, which is what Figure 3.6 requires for the single/dual-I/O case.

**D-9 (low) — the part is wired for quad-I/O and ships configured for neither
quad nor speed, and no provisioning step is recorded.**

Two non-volatile bits, both at a factory default that blocks what the comment
("Quad-I/O wiring, datasheet figure 3.7") assumes:

* **`QE` bit**: "The Quad Enable (QE) bit, non-volatile bit, while it is
  "**0**" (**factory default**), it performs non-Quad and WP#, RESET#/HOLD# are
  enable." Quad-I/O reads are unavailable until somebody writes QE = 1.
* **Configuration Register-2 bit 1**: default **0** = Ultra Low Power Mode,
  where Table 1 caps *every* Fast Read variant — 1I/2O, 2 I/O, 1I/4O, 4 I/O —
  at **8 MHz**, and plain 1-I/O READ at 33 MHz. High Performance Mode (bit = 1)
  lifts all of them to 80 MHz.

Neither is a wiring error — the board boots fine in single-I/O, which is the
safe default — but two things follow that are not written down anywhere. First,
**getting quad configuration reads requires programming the flash's status and
configuration registers**, a provisioning step 0006 does not mention. Second,
**I could not verify the GateMate's configuration SPI clock rate against that
8 MHz ceiling**: DS1001 says only that configuration uses a "free-running
oscillator" and that "the SPI clock rate is determined by the clock frequency of
the internal oscillator", and publishes no number. If that oscillator runs above
8 MHz and the controller issues a Fast Read, configuration fails on a virgin
part. This is worth measuring on the first board rather than discovering.

One useful datasheet line for the JTAG path: DS1001 §3.4.6, "Access to external
SPI data flashes works for all four SPI modes (CPOL, CPHA), but **only in
single-IO mode**" — so openFPGALoader writing the flash over JTAG-SPI bypass is
unaffected by `QE`.

### 3.6 Y1, FB1, Q1, J1

**D-10 (low) — the crystal's temperature grade is unverified and may not meet
FTDI's stated range.** FTDI asks for "30MHz ±20ppm Crystal 18pF 50 Ohm **−40°C ~
85°C**". The netlist specifies `ABM8G-30.000MHZ-18-D2Y-T`. In Abracon's ABM8G
ordering code the trailing letter before `-T` is the operating temperature
range, and on several ABM8G part numbers `Y` denotes a **−20 °C to +70 °C**
grade, not −40 to +85. I did **not** fetch Abracon's datasheet and cannot
confirm the decoding, so this is flagged as a thing to check, not a finding of
fact. It matters because the rest of the board is specified to −40/+125
(LTM4622I, MX25R…IH0) and because a commercial-grade crystal on an
industrial-grade board is the sort of detail a BOM review will not catch — the
part number looks fully specified.

The load-capacitor arithmetic is sound: `C = 2 × (CL − Cstray)` with
`Cstray = 2.0 pF` (datasheet `Cp`) + ~2 pF layout gives 28 pF, and 27 pF is the
adjacent standard value. Y1's two ground pads are connected.

**FB1** — `BLM18PG221SN1D`, 220 Ω at 100 MHz, 1.4 A, 100 mΩ. The comment says
"100 mohm" and `power.md` line 164 assumes "50 mΩ DCR" for its 19 mV drop
calculation. **At 100 mΩ the drop is 38 mV, not 19 mV.** Immaterial at 4.45 V
in, but the two numbers are in the same repository, three files apart, and
disagree by 2×; the netlist's is the one attached to a part number.

**Q1 BSS138** — gate on `FT_WAKEUP_N` (2.5 V logic), drain on `CORE_RUN` with a
100 k pull-up to `+5V`, source on GND. Pulling a 100 k pull-up down needs
essentially no drive, so the BSS138's weak specification at `VGS` = 2.5 V does
not matter; I did not fetch its datasheet and the conclusion does not depend on
one. `VGS(max)` ±20 V and `VDS(max)` 50 V are far from anything present.

**J1** — `ID` open is correct for a device port. The SuperSpeed transmit pair has
matched 100 nF AC coupling on `TODP`/`TODN` and the receive pair has none, which
is the correct asymmetry: the host provides the coupling on the leg it drives.
The comment's justification and the USB 3.2 range it quotes (75–265 nF) are
consistent with the part fitted.

---

## 4. The power tree

### 4.1 Every regulator has a programmed output — demonstrated, not assumed

The brief asks specifically whether any regulator has a floating SET pin, since
that bug has occurred here. I enumerated every control pin of both regulators
and what is attached to it:

| Device | Pin | Net | What is on it |
| --- | --- | --- | --- |
| U3 LT3045 | `SET` | `N$5` | **R1 33.2 k 0.1 %** + C8 4.7 µF |
| U3 | `EN/UV` | `+5V` | tied to IN ✔ |
| U3 | `ILIM` | `GND` | ✔ |
| U3 | `PGFB` | `+5V` | ✔ (but see D-6) |
| U3 | `PG` | open | ✔ permitted |
| U3 | `OUTS` | `+3V3` | ✔ |
| U4 LTM4622 | `FB1` | `N$6` | **R2 19.1 k 1 %** |
| U4 | `FB2` | `N$7` | **R3 90.9 k 1 %** (0603, E-1 poka-yoke) |
| U4 | `FREQ` | `N$8` | **R4 649 k 1 %** |
| U4 | `TRACK/SS1` / `SS2` | `N$9` / `N$10` | C11 / C12 10 nF |
| U4 | `RUN1` | `+5V` | always on |
| U4 | `RUN2` | `CORE_RUN` | Q1 drain + R8 100 k to `+5V` |
| U4 | `PGOOD1` / `2` | `PG_1` / `PG_2` | R5 / R6 100 k to `+2V5` |
| U4 | `INTVCC`, `COMP1`, `COMP2` | open | ✔ datasheet-mandated |

**No floating programming pin anywhere.** Both feedback resistors and the
frequency-set resistor are fitted, at datasheet-table values, and the two
soft-start capacitors are present. That specific class of bug is closed.

### 4.2 Rail summary as built

| Rail | Source | Programmed by | Nominal | Worst case | Load | Capability |
| --- | --- | --- | --- | --- | --- | --- |
| `USB_VBUS` | J1 | — | 4.45–5.25 | — | FB1 only | bus |
| `+5V` | FB1 | — | 4.4–5.2 | — | 381 mA (0009) | bus |
| `+3V3` | U3 LT3045 | R1 33.2 k | 3.320 | 3.250 – 3.390 | 185 mA | **500 mA** |
| `+2V5` | U4 ch 1 | R2 19.1 k | 2.497 | 2.433 – 2.563 | ~15–24 mA | **2.5 A** |
| `+1V0` | U4 ch 2 | R3 90.9 k | 0.999 | 0.979 – 1.019 | 149 mA (est.) | **2.5 A** |
| `+1V0_FT` | U2 internal LDO | — | 1.0 | — | U2 core only | internal |

Current capability is nowhere near binding: the worst utilisation is the LT3045
at 37 % of 500 mA. Thermally, the LT3045 dissipates `(5.25 − 3.32) × 0.185` =
357 mW into a `θJA` of 34 °C/W, a 12 °C rise — 0009's "roughly 400 mW, so tie
the exposed pad to plane with thermal vias" is conservative and still right. The
LTM4622 loses roughly 33 mW total at 22 °C/W and is thermally irrelevant.

### 4.3 Sequencing as built — and it is not what `power.md` describes

Reconstructed from the netlist plus the three datasheets, at cable insertion:

| t | Event | Source |
| --- | --- | --- |
| 0 | VBUS rises through FB1 onto `+5V` | |
| ~0 | U3 enables (EN/UV tied to IN; UVLO 1.78 V) and U4 ch 1 enables (RUN1 tied to VIN; threshold 1.27 V, needs VIN > 3.6 V) | LT3045, LTM4622 |
| **4.3 ms** | `+2V5` in regulation | 10 nF × 0.6 V / 1.4 µA |
| 4.3 ms | Nine GPIO banks, `VDD_CLK`, FT601Q `VCCIO` ×4, the flash and JTAG VREF are all live. `WAKEUP_N`'s 100 k pull-up goes high → Q1 on → `CORE_RUN` low → **`+1V0` stays off** | netlist |
| ~24 ms | FPGA POR_ADJ network has charged | 19.4 ms, D-2 |
| **359 ms** | `+3V3` reaches 90 % | `2.3 × R_SET × C_SET`, D-6 |
| ~360 ms | FT601Q `VCC33`/`VDDA` live; its internal LDO makes `+1V0_FT`; the bridge can enumerate | |
| after enumeration | `WAKEUP_N` driven low → Q1 off → R8 pulls `CORE_RUN` to `+5V` → ch 2 soft-starts | |
| +4.3 ms | `+1V0` in regulation; FPGA POR releases on VDD; configuration reads from flash | |

Three observations follow.

**S-1 (informational, and a good result).** I went looking for a
power-sequencing violation on the FPGA, because holding `VDDIO` at 2.5 V with
`VDD` at 0 V for an unbounded time is the kind of thing that destroys parts.
DS1001 §3.2.1 settles it, verbatim: "**No restrictions concerning order of
voltage switch-on.**" The design is legal and 0009's claim to that effect is
correct. Confirming this seemed worth the space, because it is the one place
where the unusual gating scheme could have been fatal and is not.

**S-2 (medium) — the 2.5 V rail is never gated, so `power.md`'s pre-enumeration
arithmetic is measuring the wrong thing.** `power.md` line 188 says "0009
answers this by gating the FPGA rails with the LTM4622 run pins", and then sums
a pre-enumeration budget on that basis. In the netlist **`RUN1` is tied to
`+5V`** — only the core rail is gated, for the reason the code comment gives
(gating channel 1 would remove the bridge's own `VCCIO`, which is the supply for
the pin that does the gating). `open-items.md` records this correctly; `power.md`
does not. The practical difference is small — the FT601Q's `Iccio_1` is 4.5 mA
typical with no data transfer, about 2.6 mA reflected through the buck — but
there is a term nobody can put a number to: **the GateMate's bank-supply current
with 45 bank balls at 2.5 V and the core at 0 V is not characterised anywhere in
DS1001.** Table 4.2's leakage figures are per core mode and assume the core is
powered. So the pre-enumeration budget has an unmeasured term in it, on the rail
that is not gated, and the page does not say so.

**S-3 — the POR delay is sized against the wrong rail.** D-2's 19.4 ms was
chosen to clear the 4.3 ms `+2V5` soft start by 4×. It does clear it. But the
FPGA cannot do anything until `+1V0` arrives, which is at least 360 ms later
because of D-6, so the delay buys nothing at all in the as-built sequence. This
is not harmful; it is evidence that the two halves of the power tree were
designed without reference to each other.

### 4.4 Inrush and the USB capacitance limit

`+5V` carries 10 µF + 4.7 µF + 4.7 µF = **19.4 µF nominal**, and `USB_VBUS`
carries none. FB1 sits between them, and a ferrite is not an inrush limiter — at
DC it is 100 mΩ. USB 2.0 §7.2.4.1 caps a device's bypass capacitance at VBUS at
**10 µF**; derated for DC bias the fitted parts are probably near 12 µF, still
over. This is a real conformance point for the current bus-powered design. It is
also one the wall-wart redesign removes entirely, so I would not spend a part on
it now — but if a bus-powered board is ever built from this netlist, it needs a
soft-start FET or a smaller `+5V` bulk.

### 4.5 The mezzanine, and the one signal-integrity defect on it

The header pinout is correct against `interface.md` and against `bom.csv`'s
description, and I dumped all 80 pins to check:

```
1..63 odd   ELEM0..ELEM31        2..64 even  GND
65 MCLK     66 OSC_EN_441        67 OSC_EN_48  68 MUTE_N
69 ID0      70 ID1
71,73,75,77,79 +5V               72,74,76,78,80 GND
```

Every element line has a ground **directly opposite it across the row**, which
satisfies `interface.md`'s "Every element line sits adjacent to a ground pin".
Along each row, though, the odd side is 32 consecutive element lines with no
ground between them, so the return path is transverse only. For 32 lines
switching at 24.576 MHz into a module where "Element return currents are the
analog signal", that is worth knowing about before layout; it is a defensible
reading of the contract rather than a violation of it.

**M-1 (medium) — `MCLK` crosses the connector with no adjacent ground at all.**
Pin 65 sits between ELEM31 (63) and OSC_EN_48 (67) along its row, and opposite
OSC_EN_441 (66). Its three nearest neighbours are all signals. `MCLK` is the
24.576 MHz element clock, the one signal 0012 calls "the single most
jitter-sensitive signal in the design" on the module side, and `interface.md`'s
own signal table lists `GND` as "Interleaved between signals". Meanwhile **ten
spare pins are grouped at 71–80** as five more `+5V` and five more `GND`, where
five `+5V` contacts already carry 147 mA that one would comfortably handle.
Moving one ground next to pin 65 costs nothing and is free to do now, before
layout fixes the connector. This is the cheapest fix in the review.

**M-2 (informational) — the 32 element lines come off two opposite faces of the
BGA.** ELEM0–17 are bank SA (balls R/T/U/V, rows 5–10, the south edge);
ELEM18–31 are bank WB (balls H/J/K/L, columns 1–4, the west edge). They then
converge on one 2×40 header. Electrically this is fine — the module re-registers
everything on `MCLK` with an 81 ns period, so hundreds of picoseconds of routing
skew is irrelevant — but it is a real floorplan constraint on a 15 × 15 mm
BGA-324 with, per DS1001 §5.1, a ball arrangement "defined for 4-layer PCB
layout with only 2 signal layers". 0005 already argues for a ground plane rather
than trusting that claim; this adds to it. Bank SA alone has only 18 GPIO, so
splitting was unavoidable without moving the bridge bus — worth recording as a
constraint the layout inherits, not as an error.

---

## 5. Two things the brief asked for specifically

### 5.1 What the wall-wart / isolated-USB redesign invalidates that is not yet recorded

The redesign itself is agreed and deliberately unimplemented, and is not
reported as a defect. `docs/open-items.md` already retires "the 472 mA against
500 mA USB 2.0 margin, the 150 mA pre-enumeration rule, the 4.43 V worst case on
`VIN_P`, `MUTE_N`'s pre-enumeration role, **the LTM4622 run-pin gating and its
`WAKEUP_N` NMOS**, and the LTC3265". Everything in that list I would otherwise
have raised — Q1, R8, the `WAKEUP_N` pull-up, the RUN2 net — is covered.

These are not:

**R-1 (high) — the netlist ties cable ground to board ground, and the whole
point of the redesign is that it must not.** J1's `GND`, `DRAIN` and `SHIELD`
all land on the board's single `GND` net, and J1's `VBUS` reaches `+5V` through
FB1. With an ADuM4165 the cable side becomes a separate isolated domain; those
four connections are the barrier, and every one of them shorts it. This is not a
component swap, it is a **net split** — `GND` has to fork into `GND` and
`USB_GND`, and `assert_below_abs_max`'s `exempt=("GND",)` argument quietly
assumes one ground net, so the safety assertion has to be revisited at the same
time. None of that is written down.

**R-2 (high) — the FT601Q's `VBUS` pin has nowhere to come from after
isolation.** FTDI's pin table gives pin 37 as "`VBUS` **USB BUS power input**",
type I: it is how the bridge knows a host is attached. Today it is fed from
`+5V`, i.e. ultimately from the cable. On the isolated side the cable's VBUS is
across the barrier and unavailable, so this pin needs a defined source — the
isolator's downstream VBUS output, or the local 5 V — and which one determines
whether the bridge can tell "host attached" from "board powered". Nothing
records the question.

**R-3 (medium) — "the SuperSpeed pairs simply go unrouted" has three unstated
consequences.** `open-items.md` says the pairs go unrouted, which removes the
hardest layout constraint. What it does not say: (a) `TODP`, `TODN`, `RIDP` and
`RIDN` become **four new unconnected FT601Q pins**, and the datasheet gives no
guidance for leaving SuperSpeed pins open; (b) the two matched 100 nF AC
coupling capacitors become unused parts to delete rather than leave; and (c) J1
is a **USB 3.0 Micro-B receptacle** — five extra contacts and an awkward
connector — chosen precisely to carry those pairs. USB 2.0-only wants a
different receptacle, which is a mechanical and enclosure decision, not just a
netlist edit.

**R-4 (medium) — the 900 mA descriptor instruction becomes wrong, and it is
stated twice.** 0009 says "**Declare 900 mA in the USB descriptor** regardless
of the module fitted" and `power.md` repeats it in bold. After the redesign the
device draws its power from the jack and its USB side is a ~20 mA isolator
supply; declaring 900 mA of bus current would be false and, on a 100 mA-limited
port, would fail configuration for no reason. Both statements need retiring
alongside the pre-enumeration rule they sit next to.

**R-5 (low) — `brief.md` still lists "No external power input" as a deliberate
non-goal**, with 0009's ground-loop reasoning attached: "A second supply means a
second ground reference next to USB ground." `open-items.md` records that the
redesign supersedes 0009; it does not record that this line in `brief.md`
inverts. Note that the redesign's answer is better than the old objection — with
galvanic isolation there is no longer a second ground reference *next to* USB
ground, because USB ground is no longer connected — which is worth capturing
rather than leaving as an apparent contradiction.

**R-6 (low) — FB1's sizing rationale evaporates.** The comment sizes it "against
the 380 mA the budget in 0009 actually draws" as a cable-EMI filter per FTDI's
bus-powered reference. After the redesign `+5V` is a local buck output, the
cable carries no power, and FB1 is filtering a different noise source in a
different direction. `open-items.md` anticipates "input filtering, because a
switching wall wart becomes the primary noise source where `VBUS` used to be" —
at the jack. It does not say FB1's existing justification stops applying.

**Hard to adapt, independent of any of the above.** The mezzanine is fully
allocated: all 80 pins are assigned and the 10 that were spare are already
committed to `+5V` and `GND`. If the redesign ever wants to hand the module a
second rail across the connector — plausible, since it deletes the module's
charge pump and adds a negative rail — **there is no spare pin to do it with**
without re-cutting the connector. That is the one structural thing in the
current design that a later change cannot absorb cheaply. If pins are going to
be re-cut, M-1 should be fixed in the same pass.

### 5.2 What `assert_below_abs_max` does and does not cover — demonstrated

The brief says the assertion "only [covers] driving pins". I did not want to
take that on trust in either direction, so I tamper-tested it: inject a fault,
run `build()`, record whether the assertion fires. Positive controls first, so
that a silent pass means something.

| Tamper | Result |
| --- | --- |
| *(none — baseline)* | PASSED (silent) — the board as built is clean |
| FPGA signal ball connected straight to `+3V3` | **FIRED** — 1 protected pin |
| FPGA signal ball strapped to `+5V` | **FIRED** — 1 protected pin |
| FPGA signal ball on the midpoint of a `+3V3`→GND resistor divider | **FIRED** — 1 protected pin |
| FPGA signal ball on a **new, undeclared** `+12V` net | **PASSED (silent)** |
| FPGA **supply** ball (`VDD_CLK`) alone on a declared 3.3 V rail | **PASSED (silent)** |

The last two are the gaps, and both are by design — the docstring says so — but
they are worth stating as demonstrated facts rather than as claims:

1. **`hv_rails` is a hand-maintained list.** A rail that exists in the netlist
   but is not named in the call is invisible. Today the call declares
   `{"+3V3", "+5V", "USB_VBUS"}` and those are in fact all the rails above
   2.75 V, so the board is safe — but the protection depends on someone
   remembering to extend that set, and the redesign adds a 12 V input. **When
   the wall wart lands, `"+12V"` must be added to `hv_rails` or the assertion
   silently stops protecting against the highest voltage on the board.** That is
   a concrete, testable follow-up and it is not in `open-items.md`.
2. **Supply pins are skipped entirely** (the `PWRIN`/`PWROUT`/`_SUPPLY_NAME`
   filter in the protected-pin loop). This is deliberate and correct — the power
   tree chooses those rails explicitly — but it means the assertion covers the
   signal path only. Forty-six FPGA supply balls sit outside it, which is the
   asymmetry E-1 was about.

A note on method, since the coordinator's advice applies directly: my first
version of the supply-pin test was a **bad test**. I connected `VDD_CLK` to
`+5V` on the built circuit, which merged `+2V5` into `+5V` and made twelve
signal pins fire — I would have recorded "supply pins are covered", which is the
opposite of the truth. The test above builds a minimal circuit where `VDD_CLK`
is placed on the high rail *at construction time* and nothing else touches it,
with a matched control that puts a signal ball on the same rail and does fire.


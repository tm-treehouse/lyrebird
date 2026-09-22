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

### E-1 (high) — nothing bounds either FPGA rail if a single feedback resistor fails open

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


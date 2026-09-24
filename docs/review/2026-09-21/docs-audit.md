# Documentation and decision-record audit

**Scope.** `docs/decisions/0001`–`0013` and their index, `docs/open-items.md`,
`README.md`, `hardware/README.md`, `hardware/interface.md`, `model/README.md`,
`hardware/lyrebird-*-reva/brief.md` and `power.md`, and
`hardware/lyrebird-dac-reva/parts-notes.md`.

This review checks the project's account of itself against the netlists, the
model logs and the HDL. It does not review the design. Nothing was changed.

Two findings already published elsewhere are not re-derived here and are not
counted again: `open-items.md:177`'s retracted 0.5 dB figure and
`hardware/README.md:190-198`'s invented mismatch table (dsp-model.md H3), and
interface.md's oscillator naming and the false "604 Ω because of the 50 mA LDO"
reason (output-module.md). They are referenced where a verdict depends on them.

---

## 1. Verdicts on the thirteen decision records

Each record is judged against the current netlists, `model/results/`, the HDL
and `docs/open-items.md`. "Marked" means the record's own **Status:** line or
an in-file correction tells a reader what changed; the index at
`docs/decisions/README.md` is judged separately because it is what a reader
scans first.

| # | Verdict | Marked in file? | Marked in index? |
| --- | --- | --- | --- |
| 0001 | amended | yes | yes |
| 0002 | amended, unmarked | **no** | partly |
| 0003 | amended | yes | yes |
| 0004 | holds | — | — |
| 0005 | amended, unmarked | **no** | **no** |
| 0006 | holds; one instruction overtaken | **no** | — |
| 0007 | **contradicted**, unmarked | **no** | partly |
| 0008 | amended; correction present but incomplete | partly | **no** |
| 0009 | **superseded**, unmarked | **no** | **no** |
| 0010 | amended | yes | yes |
| 0011 | holds | — | — |
| 0012 | amended, unmarked | **no** | **no** |
| 0013 | **contradicts itself**; table stale | **no** | — |

### 0001 — FTDI bridge instead of a ULPI PHY — *amended, adequately marked*

Status line points at 0005 for the part selection, and the index repeats it.
The body still says "FT2232H … 8-bit FIFO with a 60 MHz clock" (0001:12-13)
against the built 32-bit/66.67 MHz FT601Q, but that is precisely what the
status line hands to 0005. The rationale it exists for — bridge over PHY —
is untouched. **No action.**

### 0002 — The FPGA owns the audio clock — *amended, not marked*

Two of its own numbers have moved and neither the status line nor the index
says so. The index says only "Oscillator placement refined by 0007".

1. **0002:16-17** lists the oscillators as "22.5792 MHz for the 44.1 kHz
   family / 24.576 MHz for the 48 kHz family". Since
   [0012](../../decisions/0012-module-clock-architecture.md):27-30 the parts
   fitted are **45.1584 MHz and 49.152 MHz**, divided by two; 22.5792 and
   24.576 MHz are now the *element clock*, not any oscillator. This is the
   same fault the output-module review found in `interface.md:18-19`, in a
   second document; whoever fixes one should fix both.
2. **0002:19-20** sizes the crossing FIFO at "a few thousand samples deep".
   [0011](../../decisions/0011-pack-three-samples-per-fifo-word.md):26-36
   sizes it at 25 blocks × 1,536 samples = **38,400 samples** (100 ms at
   192 kHz). An order of magnitude, in the record a reader goes to for the
   clock-domain crossing.

The load-bearing claim — the FPGA owns the rate, the host is a data source —
holds everywhere, including `hdl/rtl/lyrebird_elastic.sv`.

### 0003 — Self-describing sample framing — *amended, adequately marked*

Status and index both point at 0005 for the rationale shift, and 0005:50-56
carries the revision. One stale figure survives inside it: **0003:26**'s
"roughly 35 MB/s available" is the FT2232H's USB 2.0 bulk throughput, not the
266.7 MB/s the FT601Q bus carries (`power.md:104`). The conclusion — padding
is free — holds by a wider margin than the record claims, so this is cosmetic.

### 0004 — Defer USB Audio Class — *holds*

Nothing in the netlists, the model or the HDL touches it. `open-items.md:234`
lists it correctly under "Deliberately deferred". **No action.**

### 0005 — FT601Q bridge, forced by GateMate I/O voltage — *amended, unmarked*

The part choice and the 2.5 V rail hold and are built
(`lyrebird-main.net`: FT601Q, `VCCIO` ×4 on `+2V5`). Two amendments are
unrecorded in the file and in the index:

1. **USB 2.0 High Speed.** `open-items.md:63-77` records that the agreed wall
   wart forces High Speed, and says in terms that it "amends 0005". 0005 says
   nothing. The consequence it draws at **0005:70-71** — "The board is harder.
   USB 3.0 SuperSpeed differential pairs need controlled impedance" — is
   exactly what the amendment retires (`open-items.md:76-77`: "The SuperSpeed
   pairs simply go unrouted, which removes the hardest layout constraint").
   A reader of 0005 alone is told the opposite of what is agreed.
2. **0005:61-64** leaves the configuration path as "the likely answer is an
   SPI flash … Decided in 0006" — correct, and 0006 closes it.

The rest of the record survives contact with the netlist: 43 signals, QFN-76,
D3XX, 66.67 MHz all check out.

### 0006 — Configure from SPI flash — *holds, with one instruction overtaken*

Decision (SPI Active, separate header) is built: `CFG_MD` straps, the
MX25R6435F and the `JTAG 2x5 1.27mm` header are all in `lyrebird-main.net`.

**0006:30-31** instructs: "Size the flash with headroom rather than to a
measured figure; confirm the actual bitstream size from a first build before
committing the part." The part *has* been committed — 64 Mbit, in the netlist
and in `hardware/README.md:245` — and the confirmation 0006 asks for has not
happened; `0013:108-112` still says "Do not pick a flash part until something
close to the full design has been built and measured." The commitment was
made on two other grounds (Cologne Chip's own board, and the 2.5 V `VDD_WA`
supply range), which are good grounds, but **two decision records still
instruct a reader not to do what the netlist has done**, and nothing records
that the instruction was consciously set aside. See §5.

### 0007 — Two boards, split at I2S — *contradicted, unmarked*

This is the worst-marked record in the set, and it is linked from eight other
files by a filename that asserts the contradicted claim.

- **0007:20** "Two boards, joined at the **I2S boundary**" and **0007:23**
  "Output module — audio oscillators, **DAC**, analog output stage".
  [0008](../../decisions/0008-multibit-delta-sigma-with-dwa.md):126-128 says
  in terms: "Bit clock, word clock, serial data, and the I2C pair all
  disappear, replaced by element lines." `interface.md:14-23` lists no I2S
  signal. `README.md:22` says "Two boards, joined at the element lines."
- **0007:34-41** rests the oscillator-placement argument on "a delta-sigma DAC
  **in slave mode** derives its conversion timing from the master clock rather
  than the bit clock". There is no DAC in slave mode and no bit clock. The
  *conclusion* (oscillator on the module) is right and is re-derived correctly
  from the reclocker in `interface.md:58-62` and `hardware/README.md:117-129`
  — but the argument in 0007 is for a part the design does not contain.
- **0007:60** "This is what keeps the board inside the tighter budget when it
  falls back to a USB 2.0 port" rests on the bus-power budget of 0009, which
  `open-items.md:63` supersedes.

The status line reads a bare "**Status:** accepted". The index says only
"Reasoning now depends on 0008's reclocker", which understates it: it is not
that the reasoning depends on 0008, it is that the boundary 0007 names no
longer exists. Every document that cites the split cites it as
`0007-two-board-split-at-i2s.md`, so the stale name propagates by reference
into `README.md`, `hardware/README.md:3`, `interface.md:4`, both briefs and
both `power.md` files.

### 0008 — Multi-bit delta-sigma with DWA — *amended; correction present but not complete*

The constant-current correction at **0008:112-124** is present, accurate and
well sourced. Two things it does not cover:

1. **The corrected claim is restated uncorrected in its own section, above the
   correction.** 0008:31-41 still reads "the current drawn from the reference
   is constant regardless of signal. … No amount of resistor precision fixes
   it", and 0008:105-110 "decouple heavily at the flip-flops … The
   constant-current property above is what makes this tractable." The
   correction is 70 lines below and headed by a blockquote; a reader quoting
   the "Why differential is not optional here" section will quote the retired
   form. `open-items.md:16-18` states the scope correctly ("the *DC* load …
   is constant").
2. **One percent resistors.** 0008:52-53 concludes "it also means ordinary one
   percent resistors are adequate", written when the cost was believed to be
   a fraction of a decibel. `model/README.md:149` now measures **33.3 dB**.
   The recommendation survives (it still clears the 110 dB target by 24.7 dB)
   and `hardware/README.md:176-181` has been rewritten to say so; 0008 has
   not. This is the convergent-rounding shape exactly: right advice, retired
   number. See §5.

The 32-line provision, the three-bit choice, the single-register-per-channel
argument and the "digital side has headroom" conclusion all hold and are
confirmed by the model (`model/README.md:257-264`).

### 0009 — USB bus power — *superseded, and marked nowhere in the decisions tree*

`open-items.md:63-65` says plainly: "This supersedes
[0009](decisions/0009-usb-bus-power.md) and amends 0005 and 0012." The record
still reads "**Status:** accepted", and the index still reads "USB bus power,
and which rails are precision" with no annotation. The convention the index
itself sets (`docs/decisions/README.md:3-4` — "If a decision is reversed, add
a new record that supersedes the old one") has not been applied, and no 0014
exists.

That the redesign is unimplemented is recorded and deliberate. What is not
recorded is anywhere inside `docs/decisions/` that 0009 is no longer the
answer — including in the record that `open-items.md:236` still cites as
authority for a *live* deferral ("Headphone power beyond bus limits").

Independently of the wall wart, one claim in 0009 is wrong as written:
**0009:97** "Gate the FPGA rails with the LTM4622 run pins" (plural).
`open-items.md:103` records that only channel 2 can be gated, because
channel 1 feeds the bridge's own `VCCIO` and gating it would remove the supply
for the pin doing the gating. `hardware/README.md:71-73` repeats 0009's plural
form, so the correction lives only in open-items. The budget table at
0009:80-91 is also 91 mA light against `power.md` — see §2.

### 0010 — 192 kHz and the control word — *amended, adequately marked*

Status line and index both point at 0011 for the buffer sizing, and the
corrected figures are in 0011. The rate encoding, tag values and opcode table
match `hdl/rtl/lyrebird_tag_decode.sv`. Two live notes rather than faults:
the status-word bit layout is correctly listed as open
(`open-items.md:206-208`), and the volume-placement wording at 0010:102-105 is
the item dsp-model.md raises as H6.

### 0011 — Pack three samples per 80-bit FIFO word — *holds*

Checked against the model rather than taken on trust: 0011:52-54 claims
"Interpolator delay lines and coefficients together come to well under one
block". `model/README.md:448` measures 15,387 delay-line bits at 48 kHz and
62 coefficient words, against a 40 kbit block. Holds with room. The 25-of-32
figure is quoted consistently in `open-items.md`, `power.md:143` and the main
brief.

### 0012 — Module clock architecture and a 3.3 V element rail — *amended, unmarked*

The oscillator choice, the 1024-multiple argument, the 3.3 V rail and the
2.0 V threshold rule are all built and all hold (`output_module.py`, the
CCHD-957 and SN74ALVCH16374 selections). Three unmarked changes:

1. **Rail sources.** `open-items.md:63-77` says the wall wart "amends 0005 and
   0012"; the negative rail moves from a charge pump to a discrete inverter
   into the LT3094. 0012 says nothing.
2. **0012:134-135 "Two open. The fanout and divider part, and the register
   part within the constrained family."** Both are chosen —
   SN74LVC1G74 + LMK1C1104 and SN74ALVCH16374DGGR — and recorded as chosen in
   `open-items.md:147-148`. The record still presents them as open, and the
   index carries no note.
3. **0012:101-106**'s translator table leaves bank 1's second channel as
   "spare". `output_module.py:200-201` now ties that spare input rather than
   leaving it, which is a refinement rather than a contradiction, but the
   table is the only place a reader learns what the four channels do.

0012 is also the source of the "110 dB target" that eight other documents
measure against, and that dependency is undocumented in the other direction:
nothing in 0012 says it is being used that way.

### 0013 — Simulation and build toolchain — *contradicts itself; the tables are stale*

1. **The environment table contradicts itself two rows apart.**
   `0013:128` reads "| git-lfs 3.8.0 | installed, repository not yet
   configured to use it |" and `0013:130` reads "| git-lfs | **missing**,
   worth deciding before `hardware/datasheets/` fills |". Both rows are in
   the same table. `open-items.md:169-171` takes the first reading ("The tool
   is installed but the repository is not configured for it"), so the second
   row is the wrong one, and it is the one that says "missing" in bold.
2. **The bitstream table is two designs out of date.** 0013:98-101 lists
   `lyrebird_tag_decode` and `lyrebird_unpack` only. `hdl/build/` now holds
   four built designs — `lyrebird_elastic` and `lyrebird_ft601q_read` as well.
   The record's own conclusion (bitstream scales with utilisation, so do not
   commit a small flash) is what `hardware/README.md:245-251` and the netlist
   have already acted against; see §5 and 0006 above.
3. **0013:141-144** "The first module through both paths was
   `lyrebird_tag_decode`: eight passing tests" is a historical statement and
   is fine as written, but `README.md:57` generalises from it to "Three HDL
   modules exist with 35 passing cocotb tests" — see §2.

The toolchain decisions themselves (Verilator, cocotb 2.1, `-luttree`, the CCF
requirement, sourcing the OSS CAD Suite per shell) all hold and are confirmed
by `tools/synth.sh` and `hdl/sim/run.py`.

---

## 2. Claims that contradict each other across documents

Ordered by how much a reader would act on the wrong one.

### 2.1 The two `power.md` files disagree by 91 mA, and each says they must agree

`hardware/lyrebird-main-reva/power.md:6-7` — "The output module's half is
`../lyrebird-dac-reva/power.md` and the two have to agree."
`hardware/lyrebird-dac-reva/power.md:6-8` — the same sentence in reverse.
They do not agree:

| Line | main `power.md` | dac `power.md` |
| --- | --- | --- |
| Element reference rail | **56 mA** (:233, "the netlist says 1 kΩ") | **60.6 mA** (:282, 3.34 kΩ) |
| Clock chain / oscillator | **40 mA** (:234) | **35.5 mA** (:283) |
| Op amp stage and charge pump | **51 mA** (:235) | **139 mA** (:284) |
| Translator A side | not carried | **3 mA** (:285) |
| **Module total across the mezzanine** | **147 mA** (:160) | **238 mA** (:286) |
| **Board total at the USB input** | **381 mA** (:161) | **472 mA** (:308) |
| USB 2.0 utilisation | **76 %**, 119 mA spare (:174) | **94 %**, 28 mA spare (:314) |

`docs/open-items.md:79` quotes the module page ("the 472 mA against 500 mA USB
2.0 margin"), so the main board's page is the outlier and it is the one a
reader reaches first from `brief.md:40`. The difference is not cosmetic: 119 mA
of spare against 28 mA is the difference between a comfortable design and one
that a headphone module cannot be added to.

The main page's own reconciliation table (`power.md:228-237`, "Against 0009's
budget … The totals agree to 1 mA") is therefore reconciling against numbers
the module page has since replaced, and its conclusion that the totals agree is
an artefact of the stale lines cancelling.

### 2.2 `hardware/lyrebird-main-reva/power.md:239-249` describes a netlist that no longer exists

The section is titled "What has no source today" and every claim in it is now
false against `lyrebird-main.net`:

| Claim | Line | Netlist |
| --- | --- | --- |
| "The 1.0 V and 2.5 V rails have no supply. The LTM4622 … is not in `main_board.py`" | :241-243 | `U4`, value `LTM4622IV#PBF`, on `+5V`, both channels wired |
| "It is also absent from the stock KiCad libraries, so it needs a symbol" | :243-245 | symbol exists in `hardware/symbols/lyrebird.kicad_sym`; footprint `lyrebird:Analog_LGA-25_…` is referenced by the netlist |
| "The VBUS ferrite is likewise named in 0009 and absent" | :247 | `FB1`, `BLM18PG221SN1D 220R@100MHz`, between `USB_VBUS` and `+5V` |
| "there is no USB connector, so the 5 V input has no entry point" | :247-248 | `J1`, `Connfly DS1104-01` |
| "The 5 V net … has **no bulk or bypass capacitance and no ferrite** — zero capacitors on `+5V`" | :49-50 | `C9`, `C13`, `C14` and `FB1` are on `+5V` |
| "Until then the FPGA cannot be powered" | :244-245 | it can |

The pre-enumeration analysis at `:184-221` rests on the same stale state: its
table at `:205-209` is indexed on "1 kΩ, the netlist placeholder" for the
element resistor, and `:202-203` says "it is set by a resistor value nobody has
chosen". The element resistor **was** chosen — 1.69 kΩ + 1.65 kΩ = 3.34 kΩ,
`open-items.md:149`, `parts-notes.md`, and 28 of each in `lyrebird-dac.net` —
which is the 3.1 kΩ row of that table, not the 1 kΩ row. Its conclusion that
"On a USB 2.0 host nothing fits at any element value" may still be right, but
it is not computed from anything the boards now contain. Likewise `:212-213`
"adding 0009's op amp stage and charge pump — 51 mA, **not in the netlist**":
the LTC3265 and three OPA1612 are in `lyrebird-dac.net`.

### 2.3 Both board briefs describe a netlist state that is two rounds of work old

**`hardware/lyrebird-main-reva/brief.md:66-76`** — "It contains three active
devices (CCGM1A1, FT601Q, LT3045), one 2x40 header, 80 decoupling capacitors
and two pull-downs, and leaves **111 pins unconnected**. The 1.0 V and 2.5 V
rails have no source … There is also no USB connector, no crystal, no SPI flash
and no programming header."

`lyrebird-main.net` now has **136 components and 128 nets**, including
`LTM4622IV#PBF`, `Connfly DS1104-01`, `ABM8G-30.000MHZ-18-D2Y-T`,
`MX25R6435F 64Mb`, a `JTAG 2x5 1.27mm` header, a `BSS138` and `FB1`. Every
absence the brief lists has been filled, and `docs/open-items.md:112-136` says
so at length ("The main board's connectivity gaps are wired"). Two documents in
the same repository give opposite answers to "how finished is this board".

**`hardware/lyrebird-dac-reva/brief.md:78-98`** — "As generated on 2026-09-12 it
contains 28 components … and leaves **57 of 293 pins unconnected**", followed
by four defects and by "the fanout divider, the 16-bit register, the op amp,
the charge pump and the element resistor value have never been chosen at all".

`lyrebird-dac.net` has **128 components and 144 nets**, with
`SN74LVC1G74DCUR` + `LMK1C1104PWR`, `SN74ALVCH16374DGGR` ×2, `OPA1612AID` ×3,
`LTC3265EDHC#TRPBF`, and the 1.69 k/1.65 k elements — every one of the five
parts it says was never chosen. `open-items.md:139-142` records the opposite
("Every part the module was missing now exists in the netlist"). The brief at
least dates its snapshot, which is the honest form; the date is the evidence
that it was not updated.

Note the second-order effect: `open-items.md:139-140` says the module netlist
"generates with zero errors at **126 components and 144 nets**". The nets
match; the component count is now 128. Small, but it is quoted as a
completeness claim.

### 2.4 The corrected constant-current claim survives uncorrected in two documents

`docs/open-items.md:44-47` states that "**Decoupling is not the mitigation**,
and both 0008 and parts-notes.md said it was", and both of those have been
fixed (`0008:112-124`, `parts-notes.md:342-367`). Two more documents say it and
are not on that list:

- **`hardware/interface.md:75-80`** — "The constant-current property of
  differential thermometer drive is what keeps that load signal-independent,
  but it still needs heavy local decoupling, because a regulator loop cannot
  hold a rail at these frequencies." Both halves are the retired form: the
  load is *not* signal-independent beyond the DC term, and the disturbance is
  at audio frequency where decoupling does nothing
  (`open-items.md:44-47`: "the eight 100 nF parts are about 100 Ω where it
  lives"). This is the *contract document*, which is where a module designer
  would look for the requirement.
- **`hardware/README.md:158-167`** — "Local ceramics supply the
  high-frequency current. Neither substitutes for the other. … Differential
  thermometer drive keeps exactly seven elements high per channel at every
  code, which is what stops the load itself from varying with the signal."
  Same two claims, in the page that introduces the rail. `hardware/README.md`
  was updated for the *rotation* correction 18 lines earlier (:176-181), so
  this section was read and left.
- `hardware/lyrebird-dac-reva/brief.md:32-36` carries the softer form ("local
  ceramics carry the rest") without the correction, and `:30-31` repeats
  "decoupled at the package because that supply pin is where the element
  switching current comes from" — true, but it is the sentence the correction
  exists to qualify.

Since this is the lead open item, four documents stating the retired version
and one stating the correction is the wrong ratio.

### 2.5 `0009` and `hardware/README.md` both say to gate rails that cannot be gated

`0009:97` "**Gate the FPGA rails with the LTM4622 run pins.**" (plural)
`hardware/README.md:71-73` "**Gate the FPGA rails with the LTM4622 run pins**,
releasing them after the bridge enumerates".
`open-items.md:103` "only channel 2, the core rail, is switched: channel 1
feeds the bridge's own `VCCIO`, so gating it would remove the supply for the
pin doing the gating."

The correction exists in exactly one place, in a table row about something else
(run-pin *behaviour*). The two documents that give the instruction still give
it in the form that cannot be built.

### 2.6 The retracted 0.5 dB rotation figure has a third site

Already reported at `docs/open-items.md:177`. It is also at
**`hardware/lyrebird-dac-reva/brief.md:38-39`**: "Rotation makes 1 % adequate —
measured at **0.5 dB** against **70 dB** without it ([model](…))". Both numbers
are the order-2 pair that `model/README.md:134-149` retracts; at the
recommended order 3 the cost is **33.3 dB** and the benefit **77.6 dB**
(`model/README.md:149,158`). The brief cites `model/README.md` as its source,
and that file now says the opposite.

`hardware/netlist/output_module.py:249` carries the same "0.5 dB cost" in a
comment — flagged below as a design-file site rather than a prose one.

### 2.7 `README.md`'s status section is stale in three places

- **`README.md:57`** "Three HDL modules exist with **35 passing cocotb tests**".
  `hdl/rtl/` holds four synthesizable modules — `lyrebird_tag_decode`,
  `lyrebird_unpack`, `lyrebird_ft601q_read`, `lyrebird_elastic` — plus two
  `sim_` scaffolds, and `hdl/sim/` defines **52** `@cocotb.test` functions
  (8 + 8 + 10 + 7 + 19). 35 is exactly the old three-file total (8 + 8 + 19).
  `hdl/build/` likewise holds four built designs where `0013:98-101` lists two.
- **`README.md:6`** the diagram and **`:69-71`** ("Bus powered from a single
  USB cable") state the pre-wall-wart configuration with no pointer to
  `open-items.md:63`. The implementation status is deliberate and recorded;
  what is not recorded is that the entry document asserts the superseded
  arrangement as current, in the same breath as sending the reader to
  open-items for what is undecided.
- **`README.md:73`** "Three-bit differential drive is a recommendation rather
  than a measurement". It has since been measured end to end at all six rates
  (`model/README.md:194-203`). The *reason for 32 lines* still holds — 0008:80-83
  gives it as element-count headroom, not as doubt about three bits — so this
  is a sentence that now argues the wrong thing for a right conclusion.

### 2.8 `hdl/README.md` disagrees with `hdl/rtl/` about what has been written

Out of my named scope but directly behind `README.md:57`:
`hdl/README.md:14-19` lists two design modules, and `:25` says "Still to write:
the bus read master, the elastic buffer, …" — both of which exist
(`lyrebird_ft601q_read.sv`, `lyrebird_elastic.sv`), with tests and bitstreams.

### 2.9 A smaller one: the padded-word arithmetic in open-items

`open-items.md:73-75` "192/24 stereo needs 9.216 Mbit/s against High Speed's
480, so utilisation is 1.9 %". `0003:14-16` pads every 24-bit sample to 32 bits
on the wire, so the figure on the bus is **12.288 Mbit/s, 2.6 %**.
`power.md:103-105` uses the padded number correctly ("Two channels of 32-bit
padded samples at 192 kHz is 1.536 MB/s"). Nothing turns on it; it is the kind
of error that gets quoted forward.

---

## 3. Is `docs/open-items.md` complete and honest?

It is the best-maintained document in the repository and it is the one a reader
is told to read first (`README.md:30`, `docs/decisions/README.md:7`). The lead
item is well stated, sourced and honest about being a prediction. What follows
is what it gets wrong, in both directions.

### 3.1 Listed as open, actually closed

- **`open-items.md:104` — "LTM4622 footprint | `hardware/symbols/` | The symbol
  exists; the LGA-25 land pattern does not."** It does:
  `hardware/footprints/lyrebird.pretty/Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm.kicad_mod`,
  whose own description reads "Geometry from the LTM4622 datasheet suggested
  PCB layout" — which is the condition the row sets ("Pad size is a
  manufacturer number, not a guess"). `lyrebird-main.net:3289` references it.
  The row's *Where* column is also wrong: it points at `hardware/symbols/`,
  which is where the symbol is, not where a footprint lives.

- **`open-items.md:209-212` — "Prefill threshold and the lock state machine.
  Fifty to a hundred milliseconds is a range, not a threshold, and the mute,
  drain, prefill, resume sequence exists only as prose."** Both halves are now
  built. `hdl/rtl/lyrebird_elastic.sv:73` sets `PrefillWords = 6400`
  (50 ms at 192 kHz) and `:120-122` defines `StDrain` / `StFill` / `StRun`,
  the sequence 0010 gave in prose. The RTL's own comment at `:47-48` says
  "docs/open-items.md lists the threshold as open and 50 to 100 ms as a range;
  this is the low end of that range" — the HDL knows the document is behind it.
  What remains genuinely open is narrower: whether 50 ms is the right split,
  and the lock state machine *above* the buffer.

- **`open-items.md:219-223` — "Underrun. … nothing says what the modulator
  receives when the buffer actually runs dry."** Something does:
  `lyrebird_elastic.sv:427-433` emits zero, leaves the buffered stream in
  place, counts the underrun and asserts `rd_mute_o` "to ramp on". The item
  overstates the gap. The real remainder is that no consumer implements the
  ramp, which is a different and smaller statement.

- **`open-items.md:239-246` — "Not blocked. Nothing blocks starting. Four of the
  five tasks the original handoff proposed …"** Three of those four are
  written and tested, and so is the fifth (the clock-domain crossing). The
  section is true and obsolete; it reads as a forward-looking statement in a
  document whose value is being current.

### 3.2 Genuinely undecided and not listed

- **No clipper is specified anywhere, and the model says one is required.**
  `model/README.md:362-369` — "**Recommendation: clip at the modulator input.
  Do not use a -3 dBFS volume default.** README previously offered the two as
  equivalent alternatives; they are not." This is a change to the signal path
  that no decision record carries: 0010 defines `SET_VOLUME` and says volume
  lives inside the interpolation chain, and says nothing about clipping or
  about a top/bottom-code counter (`model/README.md:371-388` recommends one as
  "one comparator, free in the FPGA"). open-items records the *finding* as
  closed under "Real material" (`:194-197`) but never converts it into an open
  decision or an HDL requirement. As written, the repository has a measured
  recommendation with nobody assigned to it.

- **The modelling section claims more settlement than the model does.**
  `open-items.md:173-183`, "Answered by the modelling, and no longer open",
  lists order, stages, taps, widths and rotation and ends "All of it is
  measured in model/README.md". The model's own closing section
  (`model/README.md:834-842`) records three live caveats that nothing in
  open-items carries: **nothing above 10 kHz has been tested** with real
  material, so 0010's ultrasonic-headroom warning is untested; real material
  existed at 48 kHz only and "the other five rates use synthetic stand-ins with
  the right spectra and the wrong crest factors"; and "every figure except the
  element-draw table uses a **single mismatch seed**, which spans **5.3 dB**
  across five draws of the same one percent specification." A 5.3 dB spread on
  the term the model itself names as the one that sets performance belongs in
  the open list.

- **`MUTE_N` has no owner.** `parts-notes.md` records that `MUTE_N` gates both
  analog rails and that driving it is an HDL requirement; nothing in `hdl/`
  drives it, and open-items' "Blocking HDL" (`:204-212`) and "Behaviour gaps"
  (`:214-225`) do not mention it. A board that enumerates, clocks and converts
  in silence is the failure mode. (The electrical half of this is
  output-module.md's §6.4; the documentation half is that open-items does not
  know about it.)

- **Nothing records that the 132.8 dB figure has two scopes.** open-items
  states the correction correctly at `:194-197`, but the figure is used as a
  bound in `model/notes-idle.md:245` ("including the 132.8 dB worst case the
  hardware is held to") and `:311`, and in `model/results/endtoend.txt:340`
  ("Worst case over every rate … 132.8 dB, 22.8 dB over the 110 dB target").
  `notes-programme.md:12` flags the log; nothing flags `notes-idle.md`. The
  number a bench would be held to differs by 21.3 dB depending on which
  document you opened.

### 3.3 Descriptions that understate or overstate

- **`:112-136` "Closed" is written as though the netlist is finished.** It is a
  fair account of what was wired, but it is the only place a reader is told
  the main board's state, and it sits above a "Still never chosen" list that
  does not mention the two items output-module.md raises (the CCHD-957 pad
  numbering, the ungated oscillator enables). Whether those belong here is a
  reconciliation call, not mine, but the section reads as "done" and the
  netlist audit it cites is the only thing that would say otherwise.

- **`:169-171` git-lfs** — "The tool is installed but the repository is not
  configured for it." Correct, and it is contradicted by
  `0013:130` two rows below the row that agrees with it (§1, 0013).

- **`:63-97` the wall-wart section is the model of how this should be done** —
  what it supersedes, what it retires, what it recovers, what it adds and what
  it does not fix. The one thing missing is the reciprocal marking inside
  `docs/decisions/`, which is §1's finding on 0005, 0009 and 0012.

---

## 4. Cross-references

Every Markdown link in the audited set resolves (checked mechanically across
`README.md`, `docs/`, `hardware/`, `model/` and `hdl/` — 0 dead targets). The
failures are of a different kind:

- **`open-items.md:104`** points at `hardware/symbols/` for a *footprint*
  (§3.1). The directory exists, so a link checker passes; the pointer is
  still wrong.
- **`0013:86-89`** cites `hdl/constraints/README.md` for the clock-pin trap.
  The file exists and does record it. Resolves.
- **`open-items.md:60-61`** cites "section H of `model/notes-idle.md`".
  Section H exists (`notes-idle.md:332`). Resolves.
- **`open-items.md:134`** cites `assert_below_abs_max` in
  `hardware/netlist/lyrebird_parts.py`. Defined at `:176`, called from both
  boards (`main_board.py:588`, `output_module.py:656`). Resolves, and the
  claim that it "fails the build on this whole class of error" is accurate.
- **The `0007-two-board-split-at-i2s.md` filename is a cross-reference that
  asserts a false claim** in eight files: `hardware/README.md:3`,
  `interface.md:4`, both board briefs, `0008:27`, `0009:113`, `hdl/README.md`,
  and the decisions index, which spells it out as "Two boards, split at I2S".
  The design's interface contract contains no I2S signal. Renaming a decision record is
  against the tree's own convention (`docs/decisions/README.md:3` — "never
  rewritten"), so the fix is a marked status line, not a rename; but the
  propagation is worth knowing about.

---

## 5. Recommendations whose justification has moved

The convergent-rounding case is the template: `model/README.md:538-544` keeps
"round ties to even" and replaces the retracted 15.7 dB with a different and
still-valid reason (it removes a real static offset). Four more have that
shape, in varying states of repair.

| Recommendation | Where | The number that moved | State |
| --- | --- | --- | --- |
| One percent resistors are adequate | `0008:52-53` | 0.5 dB → **33.3 dB** (`model/README.md:149`) | **unrepaired in 0008**; repaired in `hardware/README.md:176-181`; restated in the retracted form in `dac/brief.md:38` |
| 132.8 dB is the figure to hold hardware to | `notes-idle.md:245`, `endtoend.txt:340` | now a tone's and a median window's figure; the bound is **111.5 dB** | repaired in `model/README.md:205-221` and `notes-programme.md`; **unrepaired in notes-idle.md** |
| 3 dB of headroom | `model/README.md:332-369` | 3 dB → **5.39 dB** needed; recommendation *replaced* by a clipper | repaired in the model, **never carried into 0010 or open-items** (§3.2) |
| Do not commit a flash part yet | `0006:30-31`, `0013:108-112` | the part was committed at 64 Mbit on other grounds | **unrepaired**: two records still instruct against what the netlist does |
| Gate the FPGA rails at enumeration | `0009:97`, `hardware/README.md:71` | only channel 2 can be gated | correction exists only in `open-items.md:103` (§2.5) |

The 0008 row is the one worth acting on first. It is the only place in
`docs/decisions/` where a *part specification* rests on a retracted
measurement, and a purchasing decision reads that sentence, not the model.
The advice survives — 33 dB of cost still leaves 24.7 dB over the target
(`model/README.md:158`) — but the record gives a reader no reason to think the
margin is anything other than free, and `model/README.md:163-166` now says the
opposite: "**Above order 2 it is element matching, not modulator order**…
Tighter elements buy more than a higher order does."

---

## 6. `parts-notes.md` contradicts itself on the board total

The file is half-updated. Two passes of arithmetic survive side by side:

| Line | Module | Board at the USB input |
| --- | --- | --- |
| `:531` "the module lands near **182 mA** and the board near **416 mA**" | 182 | 416 |
| `:674` "this board already reaches about **416 mA** at the USB input" | — | 416 |
| `:704` "the module draws **238 mA** and the board **472 mA**" | 238 | 472 |
| `:725` "power.md | **updated** — module 238 mA, board 472 mA" | 238 | 472 |

output-module.md has already established that 238/472 is right and that
parts-notes' 182 is the outlier (a symmetric ±21.6 mA charge-pump load its own
preceding section disproves). What is worth adding is that the file carries
**both** answers, and that the conclusions drawn from the low pair are the
load-bearing ones: `:532-534` concludes the line module is "inside a USB 2.0
host's 500 mA … It is no longer comfortable there", which at 416 mA leaves
84 mA and at 472 mA leaves **28 mA**. `:674` uses 416 to argue a headphone
module is out of reach — a conclusion that gets stronger, not weaker, at the
right number, so nothing reverses; but two of the four sites would have to
change for the file to say one thing.

`parts-notes.md:704` is also the only place in the repository that identifies
`hardware/lyrebird-main-reva/power.md`'s figures as superseded — "against
147 mA and 381 mA when every figure on that page was an estimate" — and that
page still prints 147 and 381 as current (§2.1). The knowledge existed; it was
not carried across.

Finally, `:698` "the module is **126 components** and 637 pins with 12
unconnected pins" is the source of the same count in `open-items.md:140`.
`lyrebird-dac.net` now generates **128** components. Two parts appeared after
both documents were written, and neither says which.

---

## Cross-section flags

Every finding where a document disagrees with a design section — hardware,
model or HDL — rather than only with another document. Tagged with the section
concerned. Items already raised by dsp-model.md or output-module.md are not
repeated.

### Hardware

- **[hardware — main board netlist]** `hardware/lyrebird-main-reva/power.md:239-249`
  ("What has no source today") is false in every clause against
  `lyrebird-main.net`: it says the LTM4622 "is not in `main_board.py`" and needs
  a symbol (it is `U4`, `LTM4622IV#PBF`, with symbol and the
  `lyrebird:Analog_LGA-25_…` footprint), that the VBUS ferrite is "absent"
  (`FB1`, `BLM18PG221SN1D`), that "there is no USB connector" (`J1`,
  `Connfly DS1104-01`), and at `:49-50` that `+5V` has "zero capacitors … and
  no ferrite" (`C9`, `C13`, `C14`, `FB1`). Its conclusion "the FPGA cannot be
  powered" no longer holds.

- **[hardware — main board netlist]** `hardware/lyrebird-main-reva/brief.md:66-76`
  states the netlist has "three active devices (CCGM1A1, FT601Q, LT3045) … and
  leaves **111 pins unconnected**", with "no USB connector, no crystal, no SPI
  flash and no programming header". `lyrebird-main.net` has **136 components
  and 128 nets**, including the LTM4622, the `ABM8G-30.000MHZ` crystal, the
  `MX25R6435F 64Mb`, the `JTAG 2x5 1.27mm` header and a `BSS138`.
  `docs/open-items.md:112-136` says the gaps are closed; the brief says they
  are open.

- **[hardware — module netlist]** `hardware/lyrebird-dac-reva/brief.md:78-98`
  ("As generated on 2026-09-12 … 28 components … **57 of 293 pins
  unconnected**") lists the fanout divider, the 16-bit register, the op amp,
  the charge pump and the element resistor as "never been chosen at all".
  `lyrebird-dac.net` has **128 components and 144 nets** and contains all five:
  `SN74LVC1G74DCUR` + `LMK1C1104PWR`, `SN74ALVCH16374DGGR` ×2, `OPA1612AID` ×3,
  `LTC3265EDHC#TRPBF`, 1.69 kΩ + 1.65 kΩ elements. The four wiring defects it
  lists are also fixed (`open-items.md:130-136`).

- **[hardware — module power budget]** The two power pages disagree and each
  states that they must agree (`main/power.md:6-7`, `dac/power.md:6-8`):
  module **147 mA** (`main/power.md:160`) against **238 mA**
  (`dac/power.md:286`); board **381 mA** (`main:161`) against **472 mA**
  (`dac:308`); USB 2.0 spare **119 mA / 76 %** (`main:174`) against
  **28 mA / 94 %** (`dac:314`). Line by line: element reference 56 vs 60.6,
  clock chain 40 vs 35.5, op amp and pump 51 vs 139.
  `docs/open-items.md:79` follows the module page, so the main board's page is
  the outlier.

- **[hardware — element resistor]** `hardware/lyrebird-main-reva/power.md:202-213`
  bases its pre-enumeration analysis on "a resistor value nobody has chosen"
  and indexes its table on "**1 kΩ, the netlist placeholder**". The element
  resistor is chosen and built: **1.69 kΩ + 1.65 kΩ = 3.34 kΩ**
  (`open-items.md:149`, `parts-notes.md`, 28 of each in `lyrebird-dac.net`),
  which is the 3.1 kΩ row of that table. The same section says the op amp stage
  and charge pump are "not in the netlist"; `OPA1612AID` ×3 and `LTC3265` are.

- **[hardware — reference rail]** The constant-current claim corrected in
  `0008:112-124` and `parts-notes.md:342-367` survives uncorrected in two more
  documents. `hardware/interface.md:75-80`: "The constant-current property of
  differential thermometer drive is what keeps that load signal-independent,
  but it still needs heavy local decoupling". `hardware/README.md:158-167`:
  "Local ceramics supply the high-frequency current … which is what stops the
  load itself from varying with the signal."
  `docs/open-items.md:16-18,44-47` and
  `model/results/reference-current.txt` say the property covers the DC term
  only and that decoupling is not the mitigation (100 Ω at the frequency that
  matters, against a 170 µΩ requirement). interface.md is the contract a module
  designer reads. `open-items.md:44` names only 0008 and parts-notes.md as
  needing the fix.

- **[hardware — LTM4622 run pins]** `0009:97` and `hardware/README.md:71-73`
  both instruct "Gate the FPGA rails with the LTM4622 run pins" (plural).
  `docs/open-items.md:103` records that only channel 2 can be gated, because
  channel 1 feeds the bridge's own `VCCIO` and gating it removes the supply for
  the pin doing the gating. The correction exists in one table row and in
  neither instruction.

- **[hardware — footprint library]** `docs/open-items.md:104` lists the LTM4622
  footprint as an open item — "The symbol exists; the LGA-25 land pattern does
  not." The land pattern exists at
  `hardware/footprints/lyrebird.pretty/Analog_LGA-25_6.25x6.25mm_Layout5x5_P1.27mm.kicad_mod`,
  described as "Geometry from the LTM4622 datasheet suggested PCB layout", and
  `lyrebird-main.net:3289` references it. The row's *Where* column also points
  at `hardware/symbols/` for a footprint.

- **[hardware — oscillators]** `0002:16-17` names the audio clocks as
  "22.5792 MHz for the 44.1 kHz family / 24.576 MHz for the 48 kHz family".
  The parts fitted are **45.1584 MHz and 49.152 MHz** CCHD-957s
  (`0012:27-30`, `lyrebird-dac.net`), divided by two. This is the same fault
  output-module.md found in `interface.md:18-19`, in a second document.

- **[hardware — module parts]** `0012:134-135` lists "Two open. The fanout and
  divider part, and the register part within the constrained family." Both are
  chosen and wired — `SN74LVC1G74DCUR` + `LMK1C1104PWR` and
  `SN74ALVCH16374DGGR` — and recorded as chosen in `open-items.md:147-148`.
  Neither 0012 nor the decisions index says so.

- **[hardware — flash]** `0006:30-31` ("confirm the actual bitstream size from a
  first build before committing the part") and `0013:108-112` ("Do not pick a
  flash part until something close to the full design has been built and
  measured") both instruct against a commitment the netlist has already made:
  `MX25R6435F 64Mb` in `lyrebird-main.net`, justified in
  `hardware/README.md:245-251` on entirely different grounds. Neither record is
  marked.

- **[hardware — board split]** `0007` names the boundary as I2S and the module
  as carrying a "DAC" (`:20`, `:23`), and rests its oscillator argument on "a
  delta-sigma DAC **in slave mode**" and a bit clock (`:34-41`). `0008:126-128`
  deletes all of that ("Bit clock, word clock, serial data, and the I2C pair
  all disappear, replaced by element lines") and `hardware/interface.md:14-23`
  lists no I2S signal. Status line is a bare "accepted". The filename carries
  the claim into eight other files.

- **[hardware — USB budget]** `0009:80-91` budgets **380 mA** total with
  "Element reference rail 25 / Oscillator 30 / Op amp stage and charge pump 65"
  and concludes "42 percent utilisation". The built boards measure
  **472 mA** (`dac/power.md:308`), with those three lines at 61 / 35.5 / 139
  (`dac/power.md:373-376`). USB 2.0 utilisation moves from 76 % to **94 %**.

- **[hardware — parts-notes internal]** `parts-notes.md` carries both budgets:
  `:531` and `:674` say "the module lands near **182 mA** and the board near
  **416 mA**", `:704` and `:725` say "**238 mA** … **472 mA**". The conclusions
  at `:532-534` about USB 2.0 comfort are drawn from the low pair.
  `:698` "the module is **126 components**" is also the source of
  `open-items.md:140`'s count; the netlist now generates **128**.

- **[hardware — design file]** `hardware/netlist/output_module.py:249` carries
  the retracted rotation figure in a comment — "0.5 dB cost; what rotation
  cannot fix is voltage coefficient" — as does
  `hardware/lyrebird-dac-reva/brief.md:38-39` ("measured at 0.5 dB against
  70 dB without it"). `model/README.md:149,158` retracts both: **33.3 dB** cost
  and **77.6 dB** benefit at the recommended order 3. (The `open-items.md:177`
  site is already reported.)

### Model

- **[model — element tolerance]** `0008:52-53` concludes "it also means ordinary
  one percent resistors are adequate", written against a cost believed to be a
  fraction of a decibel. `model/README.md:149` measures **33.3 dB** and
  `:163-166` reverses the emphasis — "Above order 2 it is element matching, not
  modulator order". The recommendation survives; the sentence a purchasing
  decision would read does not carry the cost. `hardware/README.md:176-181` has
  been repaired; 0008 has not, and it is the only place in `docs/decisions/`
  where a part specification rests on a retracted measurement.

- **[model — scope of 132.8 dB]** `model/notes-idle.md:245` ("including the
  132.8 dB worst case the hardware is held to") and `:311` ("the 132.8 dB worst
  case") use the figure as a bound. `model/README.md:205-221` and
  `model/notes-programme.md:36-43` establish it is a tone's and a median
  window's figure, and that the bound is **111.5 dB** — 1.5 dB over the 110 dB
  target rather than 22.8. `notes-programme.md:12` flags the same usage in
  `results/endtoend.txt:340` but nothing flags notes-idle.md. A bench held to
  the wrong one is held 21.3 dB too tight.

- **[model — headroom, and HDL]** `model/README.md:362-369` recommends
  "**clip at the modulator input. Do not use a -3 dBFS volume default**" and
  `:371-388` recommends a top/bottom-code counter as an overload indicator.
  Neither appears in `0010`, which defines `SET_VOLUME` and the control word,
  nor in `docs/open-items.md` as an open decision or an HDL task. A measured
  recommendation with no owner.

- **[model — measurement basis]** `docs/open-items.md:173-183` ("Answered by
  the modelling, and no longer open") omits the three caveats
  `model/README.md:834-842` states: nothing above **10 kHz** has been tested
  with real material, so 0010's ultrasonic warning is untested; real material
  existed at 48 kHz only; and every figure except the element-draw table uses
  a **single mismatch seed, spanning 5.3 dB across five draws** of the same
  one percent specification — on the term the model names as setting
  performance.

### HDL

- **[HDL — module inventory]** `README.md:57` "Three HDL modules exist with
  **35 passing cocotb tests**". `hdl/rtl/` holds four synthesizable modules
  (`lyrebird_tag_decode`, `lyrebird_unpack`, `lyrebird_ft601q_read`,
  `lyrebird_elastic`) plus two `sim_` scaffolds, and `hdl/sim/` defines **52**
  `@cocotb.test` functions (8 + 8 + 10 + 7 + 19). 35 is the old three-file
  total. `hdl/README.md:14-19` lists two design modules and `:25` says the bus
  read master and the elastic buffer are "still to write"; both exist, with
  tests and bitstreams in `hdl/build/`.

- **[HDL — bitstreams]** `0013:98-101`'s bitstream-versus-utilisation table
  carries `lyrebird_tag_decode` and `lyrebird_unpack` only. `hdl/build/` holds
  four built designs; `lyrebird_elastic` and `lyrebird_ft601q_read` are
  unmeasured in the record whose whole argument is that bitstream size scales
  with utilisation, and which `hardware/README.md:245` cites for the flash
  choice.

- **[HDL — prefill and state machine]** `docs/open-items.md:209-212` lists
  "Prefill threshold and the lock state machine … the mute, drain, prefill,
  resume sequence exists only as prose" as blocking HDL.
  `hdl/rtl/lyrebird_elastic.sv:73` sets `PrefillWords = 6400` (50 ms at
  192 kHz) and `:120-122` defines `StDrain` / `StFill` / `StRun`. The RTL's own
  comment at `:47-48` says the open list is behind it.

- **[HDL — underrun]** `docs/open-items.md:219-223` says "nothing says what the
  modulator receives when the buffer actually runs dry".
  `lyrebird_elastic.sv:427-433` emits zero, keeps the buffered stream, counts
  the underrun and asserts `rd_mute_o` "to ramp on". The open item overstates
  the gap; what is actually missing is a consumer that implements the ramp.

- **[HDL — `MUTE_N`]** `parts-notes.md:725` records `MUTE_N` as "**gates the
  charge pump** — now an HDL requirement". Nothing in `hdl/` drives it, and
  `docs/open-items.md`'s "Blocking HDL" (`:204-212`) and "Behaviour gaps"
  (`:214-225`) do not list it. Failure mode is a board that enumerates, clocks
  and converts in silence.

- **[HDL — buffer depth]** `0002:19-20` sizes the clock-crossing FIFO at "a few
  thousand samples deep". `0011:26-36` and `lyrebird_elastic.sv:68` size it at
  25 blocks × 1,536 = **38,400 samples**. 0002 is the record a reader goes to
  for the crossing and its status line is unmarked.

- **[HDL — wire format]** `docs/open-items.md:73-75` computes High Speed
  utilisation from unpadded samples — "192/24 stereo needs 9.216 Mbit/s against
  High Speed's 480, so utilisation is 1.9 %". `0003:14-16` pads every sample to
  32 bits, giving **12.288 Mbit/s, 2.6 %**;
  `hardware/lyrebird-main-reva/power.md:103-105` uses the padded figure.
  Nothing turns on it at 2.6 % of the bus, but it is the arithmetic behind the
  "USB 2.0 is ample" claim.

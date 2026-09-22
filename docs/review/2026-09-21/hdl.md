# HDL review — 2026-09-21

Scope: `hdl/rtl/` (9 SystemVerilog files), `hdl/sim/`, `tools/synth.sh`,
decisions 0002, 0003, 0006, 0010, 0011, 0013, and `model/README.md` plus
`model/export/coefficients.json` where the HDL has to implement the arithmetic
the model sized.

Read-only on everything else. No files outside `docs/review/2026-09-21/` were
modified.

---

## 1. What exists against what the decisions specify

The HDL is deliberately partial. This section maps it honestly: absence below
is scope, not a defect, unless it is called out as one.

### Design RTL (5 files)

| Module | Lines | Role | Synthesised | Tests |
| --- | --- | --- | --- | --- |
| `lyrebird_tag_decode.sv` | 66 | one bus word → sample or control word | yes | 8 |
| `lyrebird_unpack.sv` | 142 | L/R framing, resync, lock | yes | 8 |
| `lyrebird_ft601q_read.sv` | 136 | FT601Q 245 Sync FIFO read master | yes | 10 |
| `lyrebird_elastic.sv` | 460 | CDC + prefill, 25 × `CC_FIFO_40K` | yes | 7 |
| `lyrebird_coeffs_pkg.sv` | 108 | generated coefficient constants | n/a | — |

### Simulation scaffolding (4 files, explicitly not design RTL)

`lyrebird_sim_rx.sv` (receive path wired end to end, buffer sized down to
3 blocks / 9-word prefill), `lyrebird_sim_stub_ft601q.sv`,
`lyrebird_sim_elem_dump.sv`, `lyrebird_sim_cc_fifo_40k.sv` (behavioural model
of the hard FIFO). All four are headed `SIMULATION SCAFFOLDING. NOT DESIGN
RTL.` and that boundary is respected: no design module instantiates one.

### Decision by decision

**0002 — the FPGA owns the audio clock.** *Partially implemented.* The
elastic buffer is the BRAM FIFO 0002 calls for, and `rd_tick_i` is the
sample-rate enable it describes, but the tick is an **input** to
`lyrebird_elastic` and nothing in `hdl/rtl/` generates it. The MCLK divider,
the `OSC_EN_441` / `OSC_EN_48` oscillator enables, the `CC_BUFG` clock-pin
recipe that `hdl/README.md` spends a page on, and the family-change sequence
are all absent. There is no toplevel module at all — `lyrebird_sim_rx.sv` is
the closest thing and says in its own header that it is not one. The
backpressure chain 0002 promises (`wr_ready_o` → `ready_i` → RD_N) *is* built
and tested end to end.

**0003 — self-describing sample framing.** *Implemented, and the only decision
that is complete.* `0xA5`/`0x5A` tags in `DATA[31:24]`, hunting on tag
mismatch, and 0003's "several consecutive well-formed samples before it
declares lock" is `LockWords = 4`. See §3 for the correctness argument, which
does not entirely hold.

**0006 — configure from SPI flash.** *Absent, and correctly so.* SPI Active
mode is a `CFG_MD[3:0]` strap on the board; it needs no RTL. The one HDL
consequence 0006 leaves open — "confirm the actual bitstream size from a first
build before committing the part" — is partly answered by `hdl/build/`; see
§5.

**0010 — 192 kHz and the control word.** *Decoded, not acted on.*
`lyrebird_tag_decode` extracts `0xC3` control words into
`ctrl_opcode_o`/`ctrl_payload_o` and `lyrebird_unpack` passes them through in
stream order, in any lock state. Nothing in design RTL **decodes an opcode**.
`NOP`, `SET_RATE`, `SET_VOLUME`, `MUTE` and `RESET` have no implementation;
the rate payload's `payload[4]` family bit and `payload[1:0]` multiplier are
decoded only in `hdl/sim/test_tag_decode.py::rate_encoding_maps_to_hardware`,
as a test of the encoding rather than of hardware. `SET_RATE`/`RESET` → flush
is wired in `lyrebird_sim_rx.sv` only, i.e. in scaffolding. The `0x3C` status
word has no transmit path (see §6). Digital volume is absent. The nine-stage
half-band cascade and its rate mux are absent.

**0011 — three samples per 80-bit FIFO word.** *Implemented in full, and it is
the most substantial module here.* SDP 40K, 80 bits × 512, `Blocks = 25`,
three 24-bit samples per word with the spare 8 bits carrying a write-side
sequence number. The packer, the unpacker, the round-robin across parallel
blocks, the static almost-empty offset as the prefill threshold, and the
drain/fill/run state machine are all present and tested. 0011's "sample
parity, and therefore left versus right, is tracked by a counter rather than
by word boundaries" is implemented literally — and that is where the one real
bug in this review lives (§4.1).

**0013 — simulation and build toolchain.** *Implemented.* `hdl/sim/run.py`
uses `cocotb_tools.runner`; the testbenches use `cocotb.start_soon` with no
`cocotb.fork`, and `Clock(..., unit="ns")` with no `units=`; `tools/synth.sh`
passes `-luttree`. See §5 and §7 for two toolchain nits.

### Absent by scope, per `hdl/README.md`'s own list

The interpolation cascade, the modulator, the DWA rotation, the element-line
output, the status/transmit path, the control plane, and the toplevel. This
matches what the task brief expects. The coefficient package exists so that
work has numbers to build against, but **nothing imports
`lyrebird_coeffs_pkg`, and no testbench reads `hdl/sim/coeffs/*.hex`** — both
are staged for consumers that do not exist yet.

---

## 2. Simulation results

`./.venv/bin/python hdl/sim/run.py` — **52 tests, 52 pass, 0 fail, 0 skip**,
exit 0. Verilator 5.048, cocotb 2.1.0, Python 3.14.6, which is exactly the
environment 0013 records as verified. Run twice with identical results.

| Suite | Toplevel | Tests | Result |
| --- | --- | --- | --- |
| `tag_decode` | `lyrebird_tag_decode` | 8 | pass |
| `unpack` | `lyrebird_unpack` | 8 | pass |
| `ft601q_read` | `lyrebird_sim_rx` | 10 | pass |
| `elastic` | `lyrebird_sim_rx` | 7 | pass |
| `bfm` | `lyrebird_sim_stub_ft601q` | 19 | pass |

`--Wall` is on and **the run is clean** — no Verilator lint warnings from any
source file, which for `-Wall` on 1,400 lines of RTL is worth stating. The one
`SYNCASYNCNET` waiver in `lyrebird_elastic.sv:252` is narrow, argued in a
comment, and correct: the level is held 32 write clocks against a two-flop
read-domain synchroniser.

The only diagnostic in the whole run is a cocotb 2.x deprecation:
`run.py:80: Simulator.build *verilog_sources* parameter is deprecated. Use the
language-agnostic *sources* parameter instead.` Five occurrences, one per
suite.

What the passing tests actually establish, and what they do not:

- **`ft601q_read`** covers the OE_N-leads-RD_N rule directly
  (`oe_n_leads_rd_n_by_a_clock`), that no word moves with RXF_N high, bus
  release, mid-burst backpressure stopping within one word, and partial byte
  enables being counted and dropped. This is good coverage of the handshake.
- **`elastic`** covers exact three-sample round-trip, full-scale values,
  prefill holding off reads until the threshold, a bursty stream, underrun →
  re-prefill, and rate change → flush → re-lock. It runs against
  `lyrebird_sim_cc_fifo_40k.sv`, a hand-written model of the primitive, so it
  cannot catch a misunderstanding of the real block (§4.4).
- **`bfm`** self-tests the test infrastructure, including that the RTL element
  dumper and the Python sink agree, that exactly seven lines per channel are
  high at every code, and that a code `k` sums to `2k−7`. This is the
  measurement rig 0013 describes, built and working ahead of the modulator
  that will feed it.
- **Not covered anywhere:** any Verilator two-state caveat from 0013 — there
  is no X-propagation or reset-completeness check, which 0013 explicitly warns
  is not available from this simulator.

---

## 3. `lyrebird_unpack`: the resynchronisation argument

### 3.1 The word-boundary claim — holds, but on an unstated host contract

Lines 8–11 claim:

> On a 32-bit bus with word-aligned transfers the interface preserves word
> boundaries, so misalignment can only ever be a whole word, never a byte.

For the FT601Q's 245 Synchronous FIFO mode this is **true under a condition
the repository states nowhere**: that the host always writes a multiple of
four bytes.

The FT601Q presents a byte stream from the USB OUT endpoint over a 32-bit
`DATA` bus with `BE[3:0]` marking which lanes are valid. `BE` exists precisely
because the byte count need not be a multiple of four: a transfer ending on a
partial group is presented as one word with partial `BE`, valid bytes in the
low lanes, and the *next* transfer restarts at lane 0. So the word grid is
re-anchored at every transfer boundary rather than sliding — which is what
makes the claim hold — but only because the hardware re-anchors, not because
byte loss is impossible.

Two things make this safe in practice, and both are worth recording because
neither is obvious:

1. **`lyrebird_ft601q_read` drops partial-`BE` words rather than passing
   them** (`be_ok = (fifo_be_i == 4'hF)`, lines 64 and 125–132), counting them
   in `be_error_count_o`. Its header argues this correctly: "a fragment that
   reaches the tag decoder is a sample with a plausible tag and three wrong
   bytes." This is the right call and it is tested twice
   (`a_partial_byte_enable_is_rejected`,
   `several_partial_byte_enables_are_all_counted`).
2. **The tag byte sits in `DATA[31:24]`, the highest lane**, so a partial word
   — which only ever fills low lanes — can never carry a tag at all. A short
   write therefore costs 1–3 bytes and the stream resumes word-aligned, rather
   than shifting everything after it.

So the design is robust to the failure, but the comment overstates the
guarantee: it is the byte-enable check and the tag's lane position doing the
work, not a property of the bus. What is genuinely missing is the host-side
half of the contract — **nothing in the repository says the host must write
whole 32-bit words, nor which byte of the wire stream carries the tag.**
`host/src/` and `host/include/` are empty; `host/README.md` does not state it;
`hdl/sim/bfm_ft601q.py` drives `fifo_data_i`/`fifo_be_i` as whole words and so
models the aligned case only, never the lane mapping. A host that writes
`struct.pack('<I', ...)` gets the tag into `DATA[31:24]` correctly; one that
writes big-endian gets a stream of bad tags and never locks. That mapping
should be written down somewhere before the host pump is built.

### 3.2 `LockWords` does what its comment says — for `LockWords ≥ 2`

The comment (lines 13–16) claims four consecutive well-formed words, two
complete stereo frames, about 10 µs at 192 kHz. Traced against the FSM
(`LockWords = 4`, `RunWidth = $clog2(5) = 3`):

| Word | State before | Action |
| --- | --- | --- |
| 1 (left) | `run = 0` | anchors: `run → 1`, `expect_right → 1` |
| 2 (right) | `run = 1` | match, `run → 2` |
| 3 (left) | `run = 2` | match, `run → 3` |
| 4 (right) | `run = 3` | `run == LockWords-1` → `locked_o → 1`, `run → 4` |
| 5 (left) | locked | match → **first emitted sample** |

So four sample words are consumed and suppressed, lock asserts on the fourth,
and emission begins on the fifth — which is a **left** sample, because hunting
only ever anchors on `!d_sample_right`. That matters downstream: the elastic
packer's anchor (`anchored_q || !wr_right_i`) requires the first sample after
a flush to be left, and this guarantees it. Four words is two stereo frames;
at 192 kHz a frame is 5.21 µs, so 10.4 µs. **The comment is accurate.**

Two parameter edge cases, both unguarded:

- **`LockWords = 1` never locks.** The lock test
  `run == RunWidth'(LockWords - 1)` becomes `run == 0`, but it sits inside the
  `else if (match)` arm that is only reached when `run != 0`. The condition is
  unreachable and the module hunts forever. Nothing rejects the value.
- **`LockWords = 0`** gives `RunWidth = $clog2(1) = 0` and a zero-width
  counter.

`LockWords ≥ 2` is correct for every value: `RunWidth = $clog2(L+1)` always
holds `L`. A `localparam` guard or an elaboration-time assertion on
`LockWords >= 2` would close this; it is a one-line fix and not urgent, since
the default is 4.

### 3.3 Control words bypass the lock gate

Lines 87–91 pass `ctrl_valid_o`/`ctrl_opcode_o`/`ctrl_payload_o` through in
any state, deliberately and with a comment. Under the word-alignment argument
this is safe: a *sample* word always carries `0xA5`/`0x5A` in the tag lane and
so can never be mistaken for `0xC3`. But the consequence is that the flush
path is not protected by lock, and in `lyrebird_sim_rx.sv` a control word seen
while hunting will flush the elastic buffer. That is arguably right — the real
toplevel has not made this choice yet — but it should be a conscious one when
it does, because it is the one place where un-validated stream content reaches
a destructive action.

### 3.4 Smaller observations, all benign

- `sample_right_o` and `sample_o` are registered unconditionally every cycle,
  not gated on `d_sample_valid`, so during a control word they hold the
  opcode/payload bits. `sample_valid_o` is low, so no consumer sees it. This
  is the same aliasing 0013 records synthesis exploiting (52 output bits → 28
  flip-flops); harmless and deliberate.
- A bad tag increments **both** `bad_tag_count_o` and (when locked)
  `resync_count_o`. Deliberate and covered by
  `a_bad_tag_breaks_lock_and_is_counted`.
- `d_bad_tag` and `d_sample_valid` are mutually exclusive by construction in
  `lyrebird_tag_decode`, so the `if/else if` ordering at lines 97–103 cannot
  drop a sample.
- `0x3C` (status, outbound) is correctly *not* accepted inbound and raises
  `bad_tag_o`; tested by `status_tag_is_not_accepted_inbound`.

# 0013 — Simulation and build toolchain

**Status:** accepted

## Context

Earlier records said "cocotb over Icarus or Verilator" and left the choice
open. The audio measurement described in
[0008](0008-multibit-delta-sigma-with-dwa.md) settles it, because it needs long
runs rather than short ones.

## Decision

**Verilator with cocotb** for simulation. **Yosys and nextpnr-himbaechel** for
the FPGA build. **openFPGALoader** for programming. **KiCad** for the boards.

### Why Verilator rather than Icarus

A meaningful in-band noise figure wants an FFT long enough to resolve the floor
across the audio band, which is on the order of a million modulator cycles. At
24.576 MHz that is about 41 ms of simulated time. Verilator handles that in
roughly a second of compute for a small design; Icarus is one to three orders
of magnitude slower and would turn every measurement into a break.

### Two tiers of test, deliberately

**Functional tests use cocotb.** Protocol handshakes, tag resync, control word
decoding, underrun behaviour, the lock state machine. These are short,
event-driven, and far easier to express in Python than in an HDL testbench.

**The audio measurement does not.** Reading 28 element lines from Python on
every cycle makes the language binding the bottleneck rather than the
simulator. The first suite here measured about 350,000 ns of simulated time per
wall second on a trivial design, which extrapolates to minutes for a million
cycles and worsens as the modulator grows.

Instead, dump the element lines from the simulation and analyse them afterwards
in numpy. That inverts a useful ratio: **simulate once, analyse many times.**
Testing the rotation against a dozen element mismatch distributions then costs
one simulation rather than twelve, which matters because that is exactly the
experiment [0008](0008-multibit-delta-sigma-with-dwa.md) calls for.

### cocotb 2.x, and why version matters

Verified working on cocotb 2.1.0 with Python 3.14.6. The 2.x API is not the one
in most tutorials:

- `cocotb.fork` is removed; use `cocotb.start_soon`.
- `Clock(...)` takes `unit`, not `units`.
- The runner moved to `cocotb_tools.runner`.

**The floor is 2.1, not 2.0, and that is forced rather than chosen.** cocotb
2.0.x refuses to build on Python 3.14 and says so explicitly: it supports a
maximum of Python 3.13. Since the API is identical across the 2.x line, the
only reason to pin 2.0.x would be an external constraint, and it would mean
moving to Python 3.13 as well.

### HDL language subset

SystemVerilog restricted to what Yosys accepts: `logic`, `always_ff`,
`always_comb`, `localparam`. No interfaces, no packed structs. Verilator would
take the full language, but the same sources have to synthesise, and Yosys's
SystemVerilog support is partial.

### Verilator caveats to design around

Verilator is two-state by default, so it will not show X propagation and will
happily simulate a design whose reset behaviour is incomplete. Do not rely on
it to catch uninitialised state. It also rejects delays in synthesisable code,
which is a feature here.

## The build flow, and one non-obvious requirement

```
yosys  -luttree  ->  nextpnr-himbaechel  ->  gmpack  ->  openFPGALoader
```

**`synth_gatemate -luttree` is required, not optional.** Without it ABC maps
logic to `CC_LUT4`, and nextpnr-himbaechel rejects that cell type outright.
The fabric's native element is a LUT tree, so synthesis has to target
`CC_L2T4`/`CC_L2T5`. The failure is a hard error well into place-and-route,
with a message that does not point at the cause.

**Place-and-route refuses to run without a CCF pin constraints file.** There is
an `allow-unconstrained` override, which is useful for resource counts and
never valid for hardware. See [hdl/constraints/README.md](../../hdl/constraints/README.md),
which also records the clock-pin trap from
[0012](0012-module-clock-architecture.md): a clock on an ordinary pin silently
falls back to fabric routing rather than erroring.

**The OSS CAD Suite is sourced per shell, never added to PATH permanently.** It
ships its own Yosys, 0.69+24 against the 0.67 from Homebrew, and having both on
PATH means losing track of which one built a given artifact. `tools/synth.sh`
sources its `environment` script and honours an `OSS_CAD_SUITE` override.

### Bitstream size, which settles a flash question

An essentially empty design, 0 percent of the logic fabric, already packs to
**97,566 bytes**. That suggests the configuration is close to fixed-size rather
than scaling with utilisation, so the full design will land in the same
ballpark. A 2 Mbit flash gives roughly two and a half times headroom and costs
no more than something smaller, which closes the sizing question left open in
[0006](0006-configuration-from-spi-flash.md).

## Environment as verified

| Tool | Status |
| --- | --- |
| Verilator 5.048 | installed |
| Yosys 0.67+post, with `synth_gatemate` | installed |
| cocotb 2.1.0, Python 3.14.6 | installed in `.venv` |
| KiCad 10.0.6 | installed, `kicad-cli` not on PATH |
| numpy, scipy, matplotlib | installed in `.venv` |
| GTKWave | installed, reads the FST dumps from `WAVES=1` |
| clang, make, cmake | installed |
| nextpnr-himbaechel, with CCGM1A1 and CCGM1A2 databases | installed via OSS CAD Suite |
| gmpack, gmunpack | installed via OSS CAD Suite |
| openFPGALoader 1.1.1 | installed |
| git-lfs 3.8.0 | installed, repository not yet configured to use it |
| FTDI D3XX library | universal dylib, arm64 native confirmed; not yet vendored |
| git-lfs | **missing**, worth deciding before `hardware/datasheets/` fills |

Homebrew has no generic nextpnr, only `nextpnr-ice40`, so the OSS CAD Suite is
the only practical route to the GateMate target. Its build recipes include
Project Peppercorn and the GateMate database generator.

KiCad 10.0.6 is installed but `kicad-cli` is not linked; it lives at
`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`.

## Consequences

The first module through both paths was `lyrebird_tag_decode`: eight passing
tests, and a complete run from source to bitstream. Worth noting what synthesis
found: 52 output bits collapsed into 28 flip-flops, because the sample field and
the control opcode and payload are the same 24 bits of the word and only one of
them is ever valid.

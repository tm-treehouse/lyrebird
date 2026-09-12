# lyrebird

PCM audio from a host PC to an FPGA over USB, with no USB IP in the fabric.

```
Host PC ──USB 3.0──> FT601Q ──245 Sync FIFO, 32-bit, 66.67 MHz──> GateMate
                                                                     │
                                              28 element lines over mezzanine
                                                                     │
                            reclock ──> matched resistors ──> filter ──> line / headphone
```

An FTDI bridge puts the USB device controller and endpoints in silicon and
presents the FPGA with a dumb synchronous FIFO, so the fabric needs no USB
knowledge. The FPGA owns the audio clock; the host is flow-controlled by
backpressure.

There is no DAC chip. The FPGA runs an interpolator and a three-bit
delta-sigma modulator with dynamic element matching, and drives a resistor
network directly.

Two boards, joined at the element lines. The main board carries USB, the FPGA,
and the power tree. The output module carries the oscillators, the reclocking
flip-flops, the resistors, and the analog stage, so nothing analog crosses a
connector and the output stage can be revised without respinning the expensive
half.

See [docs/usb-audio-handoff.md](docs/usb-audio-handoff.md) for the original
design context, [docs/decisions/](docs/decisions/) for the rationale behind the
load-bearing choices, and [hardware/interface.md](hardware/interface.md) for
the contract between the two boards.

## Layout

| Path | Holds |
| --- | --- |
| `hardware/` | Two KiCad projects, datasheets, fab output, board interface |
| `hdl/` | Synthesizable RTL, constraints, cocotb testbenches |
| `host/` | C driver and WAV pump against the FTDI D3XX API |
| `docs/` | Design context and architecture decision records |
| `tools/` | Build, program, and bring-up scripts |

## Toolchain

- **PCB** — KiCad
- **FPGA** — Cologne Chip GateMate CCGM1A1, Yosys plus nextpnr-himbaechel via
  Project Peppercorn, both prebuilt in the OSS CAD Suite
- **Simulation** — cocotb over Icarus or Verilator
- **Host** — C against FTDI D3XX

## Status

Skeleton only. Nothing is implemented yet.

Bus powered from a single USB cable, with precision regulation confined to the
three module rails that reach the signal. Three-bit differential drive is a
recommendation rather than a measurement, which is why 32 element lines are
provisioned for 28 in use.

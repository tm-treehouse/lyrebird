# 0007 — Two boards, split at I2S

**Status:** accepted

## Context

The output stage needs to support a line output for an external amplifier and
a headphone output. These are different power designs: a line load is high
impedance and draws under a milliamp, while 32 ohm headphones draw tens to
hundreds of milliamps and need their own bulk capacitance.

Beyond that, the analog output stage is the part of this project most likely to
need iteration. Op amp choice, filter topology, and gain structure are all
things you discover by measuring. The USB and FPGA section is the expensive,
risky part to get right, and it should not be at risk every time the analog
section is revised.

## Decision

Two boards, joined at the **I2S boundary**.

- **Main board** — USB connector, FT601Q, GateMate, power tree, mezzanine
  header. See [0005](0005-ft601q-bridge-io-voltage.md) and
  [0006](0006-configuration-from-spi-flash.md).
- **Output module** — audio oscillators, DAC, analog output stage.

Put a connector in the digital path, never the analog one. A connector carrying
clock and data costs almost nothing. The same connector carrying a line-level
analog signal adds an impedance discontinuity and a noise entry point exactly
where the design can least afford it.

## The oscillator moves to the module

The audio oscillators live on the output module, next to the DAC.

This does not contradict [0002](0002-fpga-owns-the-audio-clock.md). The FPGA
still owns the rate and still decides when a sample is read. The oscillator
simply lives where its jitter matters. A delta-sigma DAC in slave mode derives
its conversion timing from the master clock rather than the bit clock, so
master clock jitter is the audible one. With the oscillator on the module that
trace never crosses a connector. The clock travels the other way, into the
FPGA, where added jitter is harmless because it only gates FIFO reads.

Two useful consequences. The 44.1 and 48 kHz families need different
oscillators, and a module can carry both, or one module per family. And because
the module selects which oscillator runs, exactly one clock returns to the FPGA
regardless of how many are fitted, which costs one of the four dedicated clock
pins instead of several.

## Consequences

**Line versus headphone is no longer a board decision.** It is which module is
fitted, and a single module may do both: share the current-to-voltage and
filter stage, then split to a fixed-gain line buffer that bypasses volume
control, and a volume-controlled headphone amplifier.

**Gate the headphone amplifier on jack detection.** Drive its enable pin from
the switch contact in the headphone jack. Unplugged it sits in shutdown, so a
combined module costs line-out current in normal use. This is what keeps the
board inside the tighter budget when it falls back to a USB 2.0 port.

**Power crosses as raw rails and the module regulates locally**, which keeps
analog regulation next to the load it serves. Declare worst-case current in the
USB descriptor; it is fixed at enumeration and cannot be renegotiated when a
module changes.

**The FPGA must tolerate the master clock changing frequency**, because
switching sample-rate families switches oscillators. Treat it as a
reconfiguration event: mute, switch, re-lock, prefill, resume.

**The interface is now a contract** between two boards that can be revised
independently. It is written down in
[hardware/interface.md](../../hardware/interface.md).

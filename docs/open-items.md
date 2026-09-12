# Open items

What is not decided. The [decision records](decisions/) cover what is, and say
almost nothing about what is not, which is how a list like this gets
reconstructed from memory six months later.

Keep this file honest. Delete an item when a decision record covers it, rather
than leaving both.

## Flagged in the repo, blocking nothing yet

| Item | Where | Note |
| --- | --- | --- |
| LTM4622 run-pin behaviour | [0009](decisions/0009-usb-bus-power.md) | Design the enumeration gating in; verify before trusting the sequencing |
| Connector pin assignment | [interface.md](../hardware/interface.md) | Waits on layout by design |

## Blocking a schematic

Found by auditing unconnected pins in the generated netlists, not by reading
this list, so treat the netlist as the authority on what is missing.

### Selected but not yet in the netlist

- **LTM4622.** Chosen in [0009](decisions/0009-usb-bus-power.md) for the 1.0 V
  core and 2.5 V I/O rails, but absent from `main_board.py`, so both rails
  currently have no source. It is also not in the stock KiCad libraries, so it
  needs a symbol as well as wiring.
- **SPI flash.** Size settled at 2 Mbit by
  [0013](decisions/0013-simulation-and-build-toolchain.md), part not chosen and
  not wired. The configuration mode pins are strapped but the flash they read
  from does not exist yet.
- **Programming header.** The JTAG pins are unconnected.
- **Ferrite at the USB input**, named in
  [0009](decisions/0009-usb-bus-power.md), not in the netlist.

### Never chosen at all

- **USB connector.** Both the USB 2.0 pair and the SuperSpeed pairs on the
  bridge are unconnected. No connector selected.
- **Bridge crystal**, plus its load capacitors. The crystal pins are open.
- **Bridge reference resistor** on `RREF`, a precision value from its
  datasheet.
- **Power-on reset network** for `POR_ADJ` and `POR_EN`, which the GateMate
  datasheet gives a formula for.
- **Fanout and divider part.** Divides the oscillator by two and distributes
  the element clock to two register packages with tight skew, on the clean
  3.3 V rail. Constrained by
  [0012](decisions/0012-module-clock-architecture.md).
- **Register part.** Constrained to a family whose input threshold is 2.0 V at
  a 3.3 V supply, in a 16-bit package. No stock symbol exists either.
- **Element resistor value.** Thin film and arrays are specified; the value is
  not.
- **Op amp, charge pump, headphone amplifier.** No parts chosen.
- **Reconstruction filter.** Topology and corner frequency.
- **Which module to build first.** Line, headphone, or combined. The ID
  encoding in [interface.md](../hardware/interface.md) supports all three.
- **Whether to provision an unpopulated quad-SPI PSRAM footprint**, six pins,
  as insurance against a future requirement. See
  [0011](decisions/0011-pack-three-samples-per-fifo-word.md).
- **Whether to use git-lfs** for `hardware/datasheets/`. The tool is installed
  but the repository is not configured for it, and that decision is much
  cheaper before the directory fills with multi-megabyte PDFs than after.

## Outputs of the modelling task, not blockers

These three were previously listed as blocking HDL, which had it backwards.
They are what the numerical model of the audio chain produces. None of them is
an input to starting it, and none can sensibly be decided in isolation, because
they only mean anything measured as a chain.

- **Modulator order and loop topology.** Three records call the order "modest"
  and none give a number.
- **Interpolation filter design.** Stage count is fixed at seven to nine by
  [0010](decisions/0010-192khz-and-control-word.md); tap counts, passband
  ripple and stopband attenuation are open. Most of the audio quality lives
  here.
- **Dynamic element matching rotation algorithm.** Plain rotation versus
  something more sophisticated.

## Blocking HDL

- **Status word bit layout.** Described in prose in
  [0010](decisions/0010-192khz-and-control-word.md), never mapped to bits.
  Blocks the status path only.
- **Prefill threshold and the lock state machine.** Fifty to a hundred
  milliseconds is a range, not a threshold, and the mute, drain, prefill,
  resume sequence exists only as prose. Blocks finishing that state machine,
  not starting it.

## Behaviour gaps

These are worth separating out, because a missing parameter shows up at review
and a missing behaviour shows up at integration.

- **Underrun.** Counted in the status word, and prefill exists to prevent it,
  but nothing says what the modulator receives when the buffer actually runs
  dry. Holding the last sample puts a DC step into a delta-sigma loop and
  clicks. Ramping to zero is the usual answer.
- **Host idle.** No defined behaviour when the host simply stops sending.
- **Module hot-swap.** The ID pins can change. Nothing says what happens if
  they do while a stream is running.

## Deliberately deferred

Not open questions. Decisions to not decide, recorded so they are not
relitigated by accident.

| Item | Record |
| --- | --- |
| USB Audio Class, driverless operation | [0004](decisions/0004-defer-usb-audio-class.md) |
| Four-bit differential, would need a main board respin | [0008](decisions/0008-multibit-delta-sigma-with-dwa.md) |
| Headphone power beyond bus limits, a module carries its own jack | [0009](decisions/0009-usb-bus-power.md) |
| External SRAM, the requirement is latency-bounded not memory-bounded | [0011](decisions/0011-pack-three-samples-per-fifo-word.md) |

## Not blocked

**Nothing blocks starting.** Four of the five tasks the original handoff
proposed depend on none of the
above: the bridge read interface, the word unpacker with tag hunting, the host
pump, and the testbench. Only the clock-domain crossing touched the open list,
and [0011](decisions/0011-pack-three-samples-per-fifo-word.md) settled its
sizing.

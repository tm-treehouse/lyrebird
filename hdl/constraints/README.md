# constraints

GateMate pin constraints, in Cologne Chip's CCF format. One file per toplevel,
named `<toplevel>.ccf`, picked up automatically by `tools/synth.sh`.

Place-and-route **refuses to run without one**, unless overridden. The override
exists for resource counts and is never valid for hardware, since I/O would be
placed wherever the tool felt like.

## The one that will bite silently

Clocks must be assigned to the dedicated clock-capable pins, `CLK0` through
`CLK3`. A clock on an ordinary pin is not an error: the packer quietly falls
back to routing it through the fabric as a user global signal, which adds
exactly the jitter the PLL bypass path exists to avoid, and nothing warns you.

Both `MCLK` and the FT601Q bus clock therefore need explicit clock-pin
assignments here. See the clocking section of
[../README.md](../README.md) and
[0012](../../docs/decisions/0012-module-clock-architecture.md).

## Bank voltages

GPIO banks are independently supplied. The element output lines and the bridge
interface should not share a bank, per
[../../hardware/README.md](../../hardware/README.md). Nothing on this part
tolerates more than 2.75 V.

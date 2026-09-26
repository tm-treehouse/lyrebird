# Power design review — 12 V wall wart, two boards

Reviewed 2026-09-25/26 against `hardware/netlist/main_board.py`,
`hardware/netlist/output_module.py` and the generated
`lyrebird-main.net` / `lyrebird-dac.net`, which are the authority used
throughout: where a Python comment and the generated netlist disagree, the
netlist wins and the disagreement is a flag.

Two things are out of scope by instruction and are not reported as faults: the
adapter is unchosen so its tolerance is assumed, and the reference-rail
transition-current item is signal integrity rather than supply.

## Verdict

The architecture is sound and the inverting converter is, against expectation,
wired correctly — the feedback referencing, the enable, the bootstrap, the
inductor return and the exposed-pad assignment are all right, and I verified
each against the LMR33630 datasheet rather than against the comment beside it.
Three things are wrong and one of them stops a build:

| | |
| --- | --- |
| **B-1** | Both LMR33630s carry a footprint for the wrong package: `HTSSOP-8 3x3 P0.65mm` against an HSOIC-8, 3.9 × 4.9 mm, 1.27 mm pitch. The KiCad symbol's own `fplist` names the right one. Nothing in either check suite looks at footprints. |
| **B-2** | U7 has **no input capacitor**. Its PGND is the −6 V rail, so the datasheet's "minimum of 10 µF ... directly to this pin and PGND" means +12 V to −6V_A, and the only capacitors fitted are +12 V to system ground. The high-side commutation loop is closed through two capacitors in series and the ground plane — on a board whose entire premise is a quiet ground. |
| **B-3** | The +5 V rail's tolerance is nowhere accounted for. `verify_power.py` and both `power.md` files use 5.02 V as if it were exact; the LMR33630's own feedback tolerance (±1.5 %, datasheet 7.5) plus the 1 % divider puts it at **4.86 V to 5.17 V**. Every module dropout margin is computed from the nominal, and U14 — just moved to 4.53 V — has 330 mV at the low corner against a 330 mV over-temperature dropout maximum. |


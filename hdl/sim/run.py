#!/usr/bin/env python3
"""Verilator + cocotb test runner.

    python hdl/sim/run.py              # run every suite
    python hdl/sim/run.py tag_decode   # run one
    WAVES=1 python hdl/sim/run.py      # dump FST waveforms

Verilator rather than Icarus because the audio measurement needs long runs.
A meaningful in-band noise figure wants on the order of a million modulator
cycles, which Verilator does in about a second and Icarus does not do in a
coffee break. See docs/decisions/0013-simulation-and-build-toolchain.md.
"""

import os
import sys
from pathlib import Path

from cocotb_tools.runner import get_runner

RTL = Path(__file__).resolve().parent.parent / "rtl"
SIM = Path(__file__).resolve().parent

# suite name -> (toplevel module, source files)
SUITES = {
    "tag_decode": ("lyrebird_tag_decode", ["lyrebird_tag_decode.sv"]),
}

# -Wall is on deliberately. Width and unused-signal warnings in RTL headed for
# a real board are worth fixing rather than silencing.
BUILD_ARGS = ["--Wall", "-Wno-DECLFILENAME"]


def run(name: str, waves: bool) -> Path:
    toplevel, sources = SUITES[name]
    runner = get_runner("verilator")
    runner.build(
        verilog_sources=[RTL / s for s in sources],
        hdl_toplevel=toplevel,
        build_args=BUILD_ARGS,
        build_dir=SIM / "sim_build" / name,
        always=True,
        waves=waves,
    )
    return runner.test(
        hdl_toplevel=toplevel,
        test_module=f"test_{name}",
        test_dir=SIM,
        build_dir=SIM / "sim_build" / name,
        waves=waves,
    )


def main() -> int:
    waves = os.environ.get("WAVES", "0") not in ("0", "", "no")
    wanted = sys.argv[1:] or list(SUITES)

    unknown = [n for n in wanted if n not in SUITES]
    if unknown:
        print(f"unknown suite(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {', '.join(SUITES)}", file=sys.stderr)
        return 2

    for name in wanted:
        print(f"\n=== {name} ===")
        run(name, waves)
    return 0


if __name__ == "__main__":
    sys.exit(main())

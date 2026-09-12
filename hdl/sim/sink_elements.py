"""Sinks for the 28 element lines.

Two paths, because there are two tiers of test and they have opposite needs.
See docs/decisions/0013-simulation-and-build-toolchain.md.

**Short functional tests: ElementSink.** A cocotb monitor that samples the
element bus in Python on every enabled clock and keeps the words in a list.
Convenient, and fast enough for a few thousand frames.

**The long audio measurement: the dump file.** Do not use ElementSink for it.
Reading 28 lines from Python every cycle makes the language binding the
bottleneck rather than the simulator -- the first suite here managed about
350,000 ns of simulated time per wall second, and a meaningful in-band noise
figure wants on the order of a million modulator cycles. Instead let
hdl/rtl/lyrebird_sim_elem_dump.sv write the lines from inside the simulation,
then read the file here with ``read_dump()`` and analyse it in numpy. That
inverts a useful ratio: simulate once, analyse many times. Trying a dozen
element mismatch distributions against the rotation then costs one simulation
rather than twelve, which is exactly the experiment
docs/decisions/0008-multibit-delta-sigma-with-dwa.md calls for.

DUMP FILE FORMAT
================

No header. A flat sequence of 4-byte records, little-endian, one record per
clock on which the dumper's enable and sample strobe were both high. Each
record is the 32-bit element vector ELEM[31:0], bit 0 in the least significant
bit of the first byte. Lines 31:28 are reserved and read zero.

    records = numpy.fromfile("sim_build/lyrebird_elem_dump.bin", dtype="<u4")

A record is 4 bytes, so a million records is 4 MB and file size divided by four
is the record count. Truncated tails are a torn-off simulation, not a format
variant: ``read_dump()`` rejects a file whose length is not a multiple of four.

LINE ALLOCATION
===============

From hardware/interface.md. Thirty-two lines are provisioned and a three-bit
differential stereo module uses 28:

    ELEM[6:0]    left channel, positive side
    ELEM[13:7]   left channel, negative side
    ELEM[20:14]  right channel, positive side
    ELEM[27:21]  right channel, negative side
    ELEM[31:28]  reserved, driven low

For code k the positive side carries k of seven lines and the negative side
seven minus k, so exactly seven lines per channel are high at every code. That
constant reference loading is a distortion mechanism rather than a nicety, so
``constant_loading_faults()`` checks it. Which particular lines carry a code is
chosen by the dynamic element matching rotation and must not be assumed stable,
which is why every decode here counts bits rather than reading a field.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

import cocotb
from cocotb.triggers import FallingEdge

#: One record per element sample: 32 bits, little-endian.
RECORD_DTYPE = np.dtype("<u4")

ELEM_LINES = 28
LINES_PER_SIDE = 7

#: (lowest line, count) for each group, per hardware/interface.md.
LEFT_POS = (0, LINES_PER_SIDE)
LEFT_NEG = (7, LINES_PER_SIDE)
RIGHT_POS = (14, LINES_PER_SIDE)
RIGHT_NEG = (21, LINES_PER_SIDE)
RESERVED = (28, 4)

_SIM = Path(__file__).resolve().parent

#: Where hdl/rtl/lyrebird_sim_stub_ft601q.sv puts its dump. run.py runs the
#: simulation with hdl/sim as the working directory, and sim_build/ is
#: git-ignored.
DEFAULT_DUMP = _SIM / "sim_build" / "lyrebird_elem_dump.bin"


def _mask(group: tuple[int, int]) -> int:
    lo, n = group
    return ((1 << n) - 1) << lo


MASK_LEFT_POS = _mask(LEFT_POS)
MASK_LEFT_NEG = _mask(LEFT_NEG)
MASK_RIGHT_POS = _mask(RIGHT_POS)
MASK_RIGHT_NEG = _mask(RIGHT_NEG)
MASK_LEFT = MASK_LEFT_POS | MASK_LEFT_NEG
MASK_RIGHT = MASK_RIGHT_POS | MASK_RIGHT_NEG
MASK_RESERVED = _mask(RESERVED)


# ---------------------------------------------------------------------------
# Reading the dump
# ---------------------------------------------------------------------------


def read_dump(path: str | Path = DEFAULT_DUMP) -> np.ndarray:
    """Read a dump file into a ``uint32`` array, one entry per element sample."""
    path = Path(path)
    size = path.stat().st_size
    if size % RECORD_DTYPE.itemsize:
        raise ValueError(
            f"{path} is {size} bytes, not a multiple of "
            f"{RECORD_DTYPE.itemsize}: the simulation was probably torn off "
            "mid-record"
        )
    return np.fromfile(path, dtype=RECORD_DTYPE)


def unpack_lines(records: np.ndarray) -> np.ndarray:
    """Expand records into a ``(n, 32)`` uint8 array, column j being line j."""
    records = np.ascontiguousarray(records, dtype=RECORD_DTYPE)
    as_bytes = records.view(np.uint8).reshape(-1, RECORD_DTYPE.itemsize)
    return np.unpackbits(as_bytes, axis=1, bitorder="little")


def codes(records: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Decode (left, right) thermometer codes, 0 to 7, by counting bits.

    Counts the positive side, which is the code by definition. Deliberately
    independent of the rotation.
    """
    records = np.asarray(records, dtype=RECORD_DTYPE)
    left = np.bitwise_count(records & MASK_LEFT_POS).astype(np.uint8)
    right = np.bitwise_count(records & MASK_RIGHT_POS).astype(np.uint8)
    return left, right


def constant_loading_faults(records: np.ndarray) -> np.ndarray:
    """Indices of records where a channel does not have exactly seven lines high.

    Differential thermometer drive keeps the element reference loading
    signal-independent, which is what stops it becoming a distortion mechanism.
    Any record failing this is a real bug in the modulator or the DWA, not a
    tolerance.
    """
    records = np.asarray(records, dtype=RECORD_DTYPE)
    left = np.bitwise_count(records & MASK_LEFT)
    right = np.bitwise_count(records & MASK_RIGHT)
    reserved = records & MASK_RESERVED
    bad = (left != LINES_PER_SIDE) | (right != LINES_PER_SIDE) | (reserved != 0)
    return np.flatnonzero(bad)


def analog_sum(
    records: np.ndarray,
    weights: Sequence[float] | np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Sum the element lines the way the module's resistors will.

    Returns ``(left, right)`` float arrays: the positive side minus the
    negative side, each line scaled by its weight. With ``weights=None`` every
    element is perfect and the result is the code offset to straddle zero.

    ``weights`` is 28 values in line order, or 7 values applied to all four
    groups. Deliberately mismatching them is the experiment from
    docs/decisions/0008-multibit-delta-sigma-with-dwa.md: the rotation should
    turn element mismatch into out-of-band noise rather than in-band
    distortion, and that is checked by summing here and taking an FFT.
    """
    bits = unpack_lines(records).astype(np.float64)

    if weights is None:
        w = np.ones(ELEM_LINES)
    else:
        w = np.asarray(weights, dtype=np.float64)
        if w.size == LINES_PER_SIDE:
            w = np.tile(w, 4)
        if w.size != ELEM_LINES:
            raise ValueError(
                f"weights must have {LINES_PER_SIDE} or {ELEM_LINES} entries, "
                f"got {w.size}"
            )

    def side(group: tuple[int, int]) -> np.ndarray:
        lo, n = group
        return bits[:, lo : lo + n] @ w[lo : lo + n]

    left = side(LEFT_POS) - side(LEFT_NEG)
    right = side(RIGHT_POS) - side(RIGHT_NEG)
    return left, right


def write_dump(records: Sequence[int] | np.ndarray, path: str | Path) -> Path:
    """Write records in the dump format. Mainly so ElementSink can hand off."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(records, dtype=RECORD_DTYPE).tofile(path)
    return path


# ---------------------------------------------------------------------------
# In-Python monitor, for short tests only
# ---------------------------------------------------------------------------


class ElementSink:
    """Accumulates the element bus in Python, one entry per enabled clock.

    Samples on the **falling** edge of the clock, so it reads the values that
    were registered at the preceding rising edge with no NBA-region ambiguity.
    That is half a cycle later than the RTL dumper observes the same pair, so
    the two capture identical sequences.

    For short functional tests. For anything approaching the audio measurement
    use hdl/rtl/lyrebird_sim_elem_dump.sv and ``read_dump()`` instead; the
    module docstring says why.

    Args:
        elem: the element bus handle, 28 or 32 bits wide.
        clk: the clock the element bus is registered on.
        enable: optional strobe. When given, a record is kept only on clocks
            where it is high; when omitted, every clock is kept.
        limit: refuse to accumulate more than this many records, so a runaway
            test fails with a clear message instead of eating memory.
    """

    def __init__(self, elem, clk, *, enable=None, limit: int = 1_000_000) -> None:
        self._elem = elem
        self._clk = clk
        self._enable = enable
        self._limit = limit
        #: Captured records, as 32-bit ints in the dump format.
        self.samples: list[int] = []
        self._task = None
        self._stop = False

    def start(self) -> None:
        self._stop = False
        self._task = cocotb.start_soon(self._run())

    def stop(self) -> None:
        self._stop = True

    async def _run(self) -> None:
        while not self._stop:
            await FallingEdge(self._clk)
            if self._enable is not None and int(self._enable.value) == 0:
                continue
            if len(self.samples) >= self._limit:
                raise OverflowError(
                    f"ElementSink hit its {self._limit}-record limit; use the "
                    "RTL dumper for runs this long"
                )
            self.samples.append(int(self._elem.value))

    # -- convenience ------------------------------------------------------

    def __len__(self) -> int:
        return len(self.samples)

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def records(self) -> np.ndarray:
        """The captured samples as a numpy array, ready for the helpers above."""
        return np.asarray(self.samples, dtype=RECORD_DTYPE)

    def codes(self) -> tuple[np.ndarray, np.ndarray]:
        return codes(self.records)

    def constant_loading_faults(self) -> np.ndarray:
        return constant_loading_faults(self.records)

    def analog_sum(self, weights=None) -> tuple[np.ndarray, np.ndarray]:
        return analog_sum(self.records, weights)

    def write_dump(self, path: str | Path) -> Path:
        """Save what was captured, in the same format as the RTL dumper."""
        return write_dump(self.records, path)

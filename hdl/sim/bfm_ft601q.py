"""Bus functional model of the FT601Q bridge, 245 synchronous FIFO mode.

This models the *bridge* side of the bus. The FPGA is the master, so the DUT
drives RD_N, OE_N and WR_N and this model drives RXF_N, TXE_N and the receive
data. Signals and mode are per
docs/decisions/0005-ft601q-bridge-io-voltage.md; the wire format is per
docs/decisions/0010-192khz-and-control-word.md.

    from bfm_ft601q import FT601QBridge, left, right, control

    bfm = FT601QBridge(dut)
    bfm.start()                          # clock plus the bus process
    ...                                  # release reset
    bfm.queue(frames([(l, r), ...]))
    await bfm.drain()

What it does, and why each part is here:

**Timing.** Everything happens on the falling edge of CLK. The DUT's control
outputs are registered, so they only change on rising edges: a value read at a
falling edge is exactly the value that will be present at the setup of the next
rising edge, which is the edge the transfer happens on. Driving at the falling
edge puts data on the bus in time for that same rising edge. That makes the
model race-free without needing to reason about the NBA region.

**Reads.** RXF_N low means a word is available. The DUT asserts OE_N, then
RD_N a clock later, and a word transfers on every rising edge where RXF_N,
RD_N and OE_N are all low. DATA carries the word only while OE_N is low;
otherwise this model drives ``undriven_data`` (0 by default, whose tag byte is
invalid), so a DUT that samples the bus without owning it fails rather than
passing by luck.

**Bursts and gaps.** The real part has a 16 kB receive buffer and USB delivers
into it in bursts, so RXF_N is not a steady low. After every ``burst`` words
the model deasserts RXF_N for ``gap`` clocks. Both are ``(min, max)`` ranges
drawn from a seeded RNG, so a run is reproducible. Pass ``burst=None`` for an
uninterrupted stream.

**Dropped words.** ``drop_next()`` and ``drop_at()`` remove words from the
stream without ever putting them on the bus. Nothing on the bus hints that it
happened, which is the point: it is how tag resync gets exercised. A dropped
sample word breaks left/right alternation, and the decoder downstream has to
notice.

**Writes.** TXE_N low means the bridge has room. A word transfers on every
rising edge where WR_N and TXE_N are both low. ``stall_tx()`` deasserts TXE_N
for a while; the DUT is expected to hold WR_N and DATA across that, and the
model raises a protocol error if DATA moves during the stall.

**Protocol errors** are collected in ``bfm.protocol_errors`` rather than
raising from the bus process, where a raise would surface as an unrelated
timeout. Assert the list is empty at the end of a test.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Iterable, Iterator

import cocotb
from cocotb.clock import Clock
from cocotb.simtime import get_sim_time
from cocotb.triggers import FallingEdge, RisingEdge

# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------

TAG_LEFT = 0xA5
TAG_RIGHT = 0x5A
TAG_CTRL = 0xC3
TAG_STATUS = 0x3C  # outbound only

OP_NOP = 0x00
OP_SET_RATE = 0x01
OP_SET_VOLUME = 0x02
OP_MUTE = 0x03
OP_RESET = 0x04

# payload[4] selects the family, payload[1:0] the multiplier, per 0010.
RATE_44K1 = 0x00
RATE_88K2 = 0x01
RATE_176K4 = 0x02
RATE_48K = 0x10
RATE_96K = 0x11
RATE_192K = 0x12

#: Bus clock period. The board runs the FIFO at 66.67 MHz, per 0005.
CLK_PERIOD_NS = 15

#: Receive buffer in the real part, for scale when choosing burst sizes.
RX_BUFFER_WORDS = 16 * 1024 // 4

ALL_BE = 0xF


def word(tag: int, payload: int) -> int:
    """One bus word: tag byte in DATA[31:24], payload in DATA[23:0]."""
    return ((tag & 0xFF) << 24) | (payload & 0xFFFFFF)


def left(sample: int) -> int:
    """A left sample word. 24-bit two's complement in DATA[23:0]."""
    return word(TAG_LEFT, sample)


def right(sample: int) -> int:
    """A right sample word."""
    return word(TAG_RIGHT, sample)


def control(opcode: int, payload: int = 0) -> int:
    """A control word: opcode in DATA[23:16], payload in DATA[15:0]."""
    return word(TAG_CTRL, ((opcode & 0xFF) << 16) | (payload & 0xFFFF))


def frames(pairs: Iterable[tuple[int, int]]) -> list[int]:
    """Interleave (left, right) pairs into the word stream, left first."""
    out: list[int] = []
    for lo, ro in pairs:
        out.append(left(lo))
        out.append(right(ro))
    return out


def tag_of(w: int) -> int:
    return (w >> 24) & 0xFF


def payload_of(w: int) -> int:
    return w & 0xFFFFFF


# ---------------------------------------------------------------------------
# Signal map
# ---------------------------------------------------------------------------


@dataclass
class BusSignals:
    """Names of the bus signals on the DUT.

    Defaults match hdl/rtl/lyrebird_sim_stub_ft601q.sv. DATA is split into two
    unidirectional buses because a Verilator toplevel cannot usefully expose an
    inout; on the board it is one bidirectional pad.
    """

    clk: str = "clk_i"
    data_i: str = "fifo_data_i"
    be_i: str = "fifo_be_i"
    rxf_n: str = "fifo_rxf_ni"
    txe_n: str = "fifo_txe_ni"
    rd_n: str = "fifo_rd_no"
    oe_n: str = "fifo_oe_no"
    wr_n: str = "fifo_wr_no"
    data_o: str = "fifo_data_o"
    be_o: str = "fifo_be_o"
    siwu_n: str | None = "fifo_siwu_no"


class FT601QBridge:
    """The bridge side of the FT601Q FIFO bus.

    Args:
        dut: the DUT handle.
        signals: signal-name overrides.
        seed: RNG seed for the burst and gap pattern, and for ``drop_probability``.
        burst: ``(min, max)`` words delivered back to back before a gap, or
            ``None`` for an uninterrupted stream.
        gap: ``(min, max)`` clocks with RXF_N deasserted between bursts.
        drop_probability: chance that any given word is silently dropped.
        undriven_data: what DATA reads as while OE_N is deasserted.
        tx_depth: transmit buffer in words. The default never back-pressures;
            use a small value or ``stall_tx()`` to exercise TXE_N.
        tx_drain_period: clocks per word drained out of the transmit buffer.
    """

    def __init__(
        self,
        dut,
        signals: BusSignals | None = None,
        *,
        seed: int = 0,
        burst: tuple[int, int] | None = (64, 512),
        gap: tuple[int, int] = (1, 24),
        drop_probability: float = 0.0,
        undriven_data: int = 0x00000000,
        tx_depth: int = RX_BUFFER_WORDS,
        tx_drain_period: int = 1,
    ) -> None:
        self.dut = dut
        self.names = signals or BusSignals()
        self.burst = burst
        self.gap = gap
        self.drop_probability = drop_probability
        self.undriven_data = undriven_data
        self.tx_depth = tx_depth
        self.tx_drain_period = tx_drain_period

        self._rng = random.Random(seed)
        self._clk = getattr(dut, self.names.clk)
        self._data_i = getattr(dut, self.names.data_i)
        self._be_i = getattr(dut, self.names.be_i)
        self._rxf_n = getattr(dut, self.names.rxf_n)
        self._txe_n = getattr(dut, self.names.txe_n)
        self._rd_n = getattr(dut, self.names.rd_n)
        self._oe_n = getattr(dut, self.names.oe_n)
        self._wr_n = getattr(dut, self.names.wr_n)
        self._data_o = getattr(dut, self.names.data_o)
        self._be_o = getattr(dut, self.names.be_o)
        self._siwu_n = (
            getattr(dut, self.names.siwu_n, None) if self.names.siwu_n else None
        )

        # Receive side
        self._queue: deque[tuple[int, int]] = deque()
        self._source: Iterator[tuple[int, int]] | None = None
        self._front: tuple[int, int] | None = None
        self._position = 0
        self._drop_next = 0
        self._drop_at: set[int] = set()
        self._burst_left = self._rng.randint(*burst) if burst else None
        self._gap_left = 0
        self._rxf_driven = 1

        # Transmit side
        self._tx_space = tx_depth
        self._tx_stall = 0
        self._tx_drain_phase = 0
        self._tx_held: int | None = None

        #: Words actually put on the bus and read by the DUT, in order.
        self.delivered: list[int] = []
        #: Byte enables that went with each delivered word.
        self.delivered_be: list[int] = []
        #: ``(stream position, word)`` for every word dropped on purpose.
        self.dropped: list[tuple[int, int]] = []
        #: Words the DUT wrote on the transmit direction, in order.
        self.received: list[int] = []
        #: Byte enables that came with each received word.
        self.received_be: list[int] = []
        #: Human-readable bus rule violations. Assert this is empty.
        self.protocol_errors: list[str] = []
        #: How many times RXF_N went from asserted to deasserted.
        self.rxf_deassertions = 0
        #: How many clocks the DUT asserted SIWU_N for. Legal, just unused here.
        self.siwu_cycles = 0

        self._task = None
        self._clock_task = None
        self._stop = False

        self._drive_idle()

    # -- setup ------------------------------------------------------------

    def _drive_idle(self) -> None:
        self._rxf_n.value = 1
        self._txe_n.value = 1
        self._data_i.value = self.undriven_data
        self._be_i.value = ALL_BE
        self._rxf_driven = 1

    def start_clock(self, period_ns: int = CLK_PERIOD_NS) -> None:
        """Start the bus clock on its own, without the bus process.

        Use this when the DUT has to be reset before the model starts looking
        at the bus: cocotb runs every test in one simulation, so a DUT can
        still be mid-write from the previous test, and a bus process started
        before reset would record that stale word.
        """
        self._clock_task = cocotb.start_soon(
            Clock(self._clk, period_ns, unit="ns").start()
        )

    def start(self, *, clock: bool = True, period_ns: int = CLK_PERIOD_NS) -> None:
        """Start the bus process, and by default the bus clock with it."""
        if clock:
            self.start_clock(period_ns)
        self._task = cocotb.start_soon(self._run())

    def stop(self) -> None:
        self._stop = True

    # -- receive direction ------------------------------------------------

    def queue(self, words: int | Iterable[int], *, be: int = ALL_BE) -> None:
        """Append words to be delivered. ``be`` overrides the byte enables.

        The wire format asserts all four byte enables on every word, so a
        partial ``be`` is a fault injection: it lets a test check that the DUT
        rejects a word rather than treating a fragment as a sample.
        """
        if isinstance(words, int):
            words = (words,)
        for w in words:
            self._queue.append((w & 0xFFFFFFFF, be & 0xF))

    def feed(self, words: Iterable[int], *, be: int = ALL_BE) -> None:
        """Stream from an iterable, pulled lazily one word at a time.

        Use this rather than ``queue()`` for the long audio runs: a million
        words of generated signal never has to exist as a list.
        """
        it = iter(words)
        self._source = ((w & 0xFFFFFFFF, be & 0xF) for w in it)

    def drop_next(self, count: int = 1) -> None:
        """Silently drop the next ``count`` words that come up for delivery."""
        self._drop_next += count

    def drop_at(self, *positions: int) -> None:
        """Silently drop the words at these absolute stream positions.

        Position 0 is the first word ever handed to ``queue()`` or ``feed()``,
        counting dropped words themselves.
        """
        self._drop_at.update(positions)

    def idle(self, cycles: int) -> None:
        """Deassert RXF_N for this many clocks, starting at the next gap point."""
        self._gap_left += cycles

    @property
    def outstanding(self) -> int:
        """Words known to be waiting. A lazy ``feed()`` source is not counted."""
        return len(self._queue) + (1 if self._front is not None else 0)

    # -- transmit direction -----------------------------------------------

    def stall_tx(self, cycles: int) -> None:
        """Deassert TXE_N for this many clocks, from the next falling edge."""
        self._tx_stall += cycles

    def received_words(self, tag: int | None = None) -> list[int]:
        """Received words, optionally only those carrying one tag."""
        if tag is None:
            return list(self.received)
        return [w for w in self.received if tag_of(w) == tag]

    # -- the bus ----------------------------------------------------------

    async def _run(self) -> None:
        while not self._stop:
            await FallingEdge(self._clk)

            rd_n = int(self._rd_n.value)
            oe_n = int(self._oe_n.value)
            wr_n = int(self._wr_n.value)
            tx_data = int(self._data_o.value)
            tx_be = int(self._be_o.value)

            if rd_n == 0 and oe_n == 1:
                self._error("RD_N asserted while OE_N was deasserted")
            if self._siwu_n is not None and int(self._siwu_n.value) == 0:
                self.siwu_cycles += 1

            self._service_rx(rd_n, oe_n)
            self._service_tx(wr_n, tx_data, tx_be)

    def _service_rx(self, rd_n: int, oe_n: int) -> None:
        front = self._present()

        if front is None:
            if self._rxf_driven == 0:
                self.rxf_deassertions += 1
            self._rxf_n.value = 1
            self._rxf_driven = 1
            self._data_i.value = self.undriven_data
            self._be_i.value = ALL_BE
            return

        w, be = front
        self._rxf_n.value = 0
        self._rxf_driven = 0
        # The bridge only drives DATA while it owns the bus.
        self._data_i.value = w if oe_n == 0 else self.undriven_data
        self._be_i.value = be if oe_n == 0 else ALL_BE

        if rd_n == 0 and oe_n == 0:
            self._consume()

    def _present(self) -> tuple[int, int] | None:
        """The word on the bus for the coming rising edge, or None for RXF_N high."""
        if self._front is not None:
            return self._front
        if self._gap_left > 0:
            self._gap_left -= 1
            return None
        while True:
            item = self._take()
            if item is None:
                return None  # nothing queued: RXF_N stays high, which is honest
            position = self._position
            self._position += 1
            if self._should_drop(position):
                self.dropped.append((position, item[0]))
                continue
            self._front = item
            return item

    def _should_drop(self, position: int) -> bool:
        if self._drop_next > 0:
            self._drop_next -= 1
            return True
        if position in self._drop_at:
            return True
        if self.drop_probability and self._rng.random() < self.drop_probability:
            return True
        return False

    def _take(self) -> tuple[int, int] | None:
        if self._queue:
            return self._queue.popleft()
        if self._source is not None:
            try:
                return next(self._source)
            except StopIteration:
                self._source = None
        return None

    def _consume(self) -> None:
        assert self._front is not None
        w, be = self._front
        self._front = None
        self.delivered.append(w)
        self.delivered_be.append(be)
        if self._burst_left is not None:
            self._burst_left -= 1
            if self._burst_left <= 0:
                assert self.burst is not None
                self._burst_left = self._rng.randint(*self.burst)
                self._gap_left = self._rng.randint(*self.gap)

    def _service_tx(self, wr_n: int, tx_data: int, tx_be: int) -> None:
        if self._tx_stall > 0:
            self._tx_stall -= 1
            ready = False
        else:
            ready = self._tx_space > 0
        self._txe_n.value = 0 if ready else 1

        if wr_n == 0:
            if ready:
                self.received.append(tx_data)
                self.received_be.append(tx_be)
                self._tx_space -= 1
                self._tx_held = None
            else:
                # WR_N may stay asserted across a TXE_N deassertion, but the
                # word has to be held or it is lost.
                if self._tx_held is not None and self._tx_held != tx_data:
                    self._error(
                        f"DATA changed from {self._tx_held:#010x} to {tx_data:#010x} "
                        "while TXE_N was deasserted"
                    )
                self._tx_held = tx_data
        else:
            self._tx_held = None

        self._tx_drain_phase += 1
        if self._tx_drain_phase >= self.tx_drain_period:
            self._tx_drain_phase = 0
            self._tx_space = min(self.tx_depth, self._tx_space + 1)

    def _error(self, message: str) -> None:
        self.protocol_errors.append(f"{get_sim_time('ns')} ns: {message}")

    # -- waiting ----------------------------------------------------------

    async def drain(self, *, settle: int = 8, stall_limit: int = 20_000) -> None:
        """Wait until every queued word has been delivered or dropped.

        Then wait ``settle`` more clocks for the DUT pipeline to empty. Raises
        ``TimeoutError`` if the DUT stops reading, which fails the test at the
        cause rather than at a global timeout.
        """
        idle = 0
        while self._front is not None or self._queue or self._source is not None:
            before = len(self.delivered) + len(self.dropped)
            await RisingEdge(self._clk)
            if len(self.delivered) + len(self.dropped) == before:
                idle += 1
                if idle > stall_limit:
                    raise TimeoutError(
                        f"no progress for {stall_limit} clocks with "
                        f"{self.outstanding} word(s) outstanding"
                    )
            else:
                idle = 0
        for _ in range(settle):
            await RisingEdge(self._clk)

    async def wait_received(self, count: int, *, timeout: int = 20_000) -> None:
        """Wait until at least ``count`` words have arrived on the transmit side."""
        for _ in range(timeout):
            if len(self.received) >= count:
                return
            await RisingEdge(self._clk)
        raise TimeoutError(
            f"only {len(self.received)} of {count} transmit words arrived "
            f"in {timeout} clocks"
        )


async def reset(dut, *, clk: str = "clk_i", cycles: int = 3) -> None:
    """Hold rst_ni low for a few clocks, then release it and settle."""
    clock = getattr(dut, clk)
    dut.rst_ni.value = 0
    for _ in range(cycles):
        await RisingEdge(clock)
    dut.rst_ni.value = 1
    await RisingEdge(clock)

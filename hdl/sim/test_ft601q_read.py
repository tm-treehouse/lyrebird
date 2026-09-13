"""Bus tests for lyrebird_ft601q_read, driven by the FT601Q bridge model.

The toplevel is hdl/rtl/lyrebird_sim_rx.sv, which is scaffolding: the real bus
reader, unpacker and elastic buffer wired end to end with the transmit
direction tied off, so bfm_ft601q.py attaches with its default signal map. The
reader's backpressure input comes from the buffer's almost-full flag in the
real design, which is not reachable from outside, so the wrapper ANDs in
throttle_i to make it drivable.

Signals and handshake per docs/decisions/0005-ft601q-bridge-io-voltage.md; the
all-four-byte-enables rule per
docs/decisions/0010-192khz-and-control-word.md.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from bfm_ft601q import (
    FT601QBridge,
    frames,
    left,
    reset,
)

#: MCLK is 24.576 MHz on the board. The read side is idle in this suite --
#: tick_i stays low -- but the clock has to run for its reset to release.
MCLK_PERIOD_NS = 41


def audio(n: int) -> list[int]:
    """n stereo frames of distinguishable samples."""
    return frames([(0x100000 + i, 0x200000 + i) for i in range(n)])


async def bring_up(dut, **kwargs) -> FT601QBridge:
    """Bridge attached, both clocks running, reset released, no throttle.

    The clock starts before the bus process, for the reason bfm_ft601q.py
    gives: every test in a module shares one simulation, so a bus process
    watching the bus during reset would record state from the test before.
    """
    bfm = FT601QBridge(dut, **kwargs)
    dut.throttle_i.value = 0
    dut.tick_i.value = 0
    dut.mrst_ni.value = 0
    cocotb.start_soon(Clock(dut.mclk_i, MCLK_PERIOD_NS, unit="ns").start())
    bfm.start_clock()
    await reset(dut)
    dut.mrst_ni.value = 1
    bfm.start(clock=False)
    return bfm


# ---------------------------------------------------------------------------
# The handshake
# ---------------------------------------------------------------------------


@cocotb.test()
async def every_queued_word_arrives(dut):
    """A continuous stream, word for word, nothing added or lost."""
    bfm = await bring_up(dut, burst=None)
    stream = audio(24)

    bfm.queue(stream)
    await bfm.drain()

    assert bfm.delivered == stream
    assert int(dut.word_count_o.value) == len(stream)
    assert int(dut.be_error_count_o.value) == 0
    assert bfm.protocol_errors == []


@cocotb.test()
async def oe_n_leads_rd_n_by_a_clock(dut):
    """The bridge only drives DATA once OE_N is low.

    Asserting RD_N in the same cycle would read a bus nobody owns, so every
    falling edge of RD_N must find OE_N already low a full clock earlier.
    """
    bfm = await bring_up(dut, burst=(4, 9), gap=(2, 7), seed=11)
    violations = []

    async def watch():
        prev_oe = 1
        prev_rd = 1
        while True:
            await FallingEdge(dut.clk_i)
            oe = int(dut.fifo_oe_no.value)
            rd = int(dut.fifo_rd_no.value)
            if rd == 0 and oe == 1:
                violations.append("RD_N low with OE_N high")
            if rd == 0 and prev_rd == 1 and prev_oe == 1:
                violations.append("RD_N asserted without a clock of OE_N lead")
            prev_oe, prev_rd = oe, rd

    cocotb.start_soon(watch())

    bfm.queue(audio(20))
    await bfm.drain()

    assert violations == [], violations[:4]
    assert int(dut.word_count_o.value) == 40
    assert bfm.protocol_errors == []


@cocotb.test()
async def no_word_is_taken_with_rxf_n_high(dut):
    """A transfer needs RXF_N, RD_N and OE_N all low at the same rising edge.

    A word_count_o increment between two falling edges means a transfer at the
    rising edge between them, and the RXF_N governing that edge is the one
    sampled at the earlier falling edge.
    """
    bfm = await bring_up(dut, burst=(3, 3), gap=(2, 6), seed=7)
    violations = []

    async def watch():
        await FallingEdge(dut.clk_i)
        prev_rxf = int(dut.fifo_rxf_ni.value)
        prev_count = int(dut.word_count_o.value)
        while True:
            await FallingEdge(dut.clk_i)
            count = int(dut.word_count_o.value)
            if count != prev_count and prev_rxf == 1:
                violations.append(count)
            prev_count = count
            prev_rxf = int(dut.fifo_rxf_ni.value)

    cocotb.start_soon(watch())

    bfm.queue(audio(15))
    await bfm.drain()

    assert violations == [], f"word taken with RXF_N high at count {violations}"
    assert int(dut.word_count_o.value) == 30
    assert bfm.rxf_deassertions >= 5, (
        f"only {bfm.rxf_deassertions} gaps; the burst model produced no gaps"
    )
    assert bfm.protocol_errors == []


@cocotb.test()
async def the_bus_is_released_when_the_stream_stops(dut):
    """RXF_N high means the bridge is done: give OE_N and RD_N back."""
    bfm = await bring_up(dut, burst=None)
    bfm.queue(audio(4))
    await bfm.drain()

    await ClockCycles(dut.clk_i, 8)
    assert int(dut.fifo_rd_no.value) == 1, "RD_N still asserted with no data"
    assert int(dut.fifo_oe_no.value) == 1, "OE_N still asserted with no data"


@cocotb.test()
async def an_idle_gap_loses_nothing(dut):
    """The stream stops and starts again; the OE_N lead is redone each time."""
    bfm = await bring_up(dut, burst=None)
    first = audio(6)
    second = audio(6)

    bfm.queue(first)
    bfm.idle(40)
    bfm.queue(second)
    await bfm.drain()

    assert bfm.delivered == first + second
    assert int(dut.word_count_o.value) == len(first) + len(second)
    assert bfm.rxf_deassertions >= 1, "the idle gap never happened"
    assert bfm.protocol_errors == []


# ---------------------------------------------------------------------------
# Byte enables
# ---------------------------------------------------------------------------


@cocotb.test()
async def a_partial_byte_enable_is_rejected(dut):
    """One padded sample per word with all four BE; a fragment is not a sample.

    The rejected word must not reach the tag decoder either. Its tag byte is a
    perfectly good 0xA5, so accepting it would produce a sample with one real
    byte and three the bridge never drove.
    """
    bfm = await bring_up(dut, burst=None)
    good = audio(2)

    bfm.queue(good[:2])
    bfm.queue(left(0x333333), be=0x7)
    bfm.queue(good[2:])
    await bfm.drain()

    assert bfm.delivered_be.count(0x7) == 1, "the BFM never drove a partial BE"
    assert int(dut.be_error_count_o.value) == 1
    assert int(dut.word_count_o.value) == len(good)
    assert int(dut.bad_tag_count_o.value) == 0
    # The fragment vanished rather than breaking the frame behind it.
    assert int(dut.resync_count_o.value) == 0
    assert bfm.protocol_errors == []


@cocotb.test()
async def several_partial_byte_enables_are_all_counted(dut):
    """Every byte-enable pattern short of 0xF is a fragment."""
    bfm = await bring_up(dut, burst=None)
    good = audio(3)

    bfm.queue(good)
    for be in (0x0, 0x1, 0x3, 0xE):
        bfm.queue(left(0x444444), be=be)
    await bfm.drain()

    assert int(dut.be_error_count_o.value) == 4
    assert int(dut.word_count_o.value) == len(good)


# ---------------------------------------------------------------------------
# Backpressure
# ---------------------------------------------------------------------------


@cocotb.test()
async def backpressure_before_a_burst_takes_nothing(dut):
    """ready_i low in StIdle means the bus is never even claimed."""
    bfm = await bring_up(dut, burst=None)
    dut.throttle_i.value = 1
    await RisingEdge(dut.clk_i)

    bfm.queue(audio(8))
    await ClockCycles(dut.clk_i, 60)

    assert int(dut.word_count_o.value) == 0, "read while backpressured"
    assert int(dut.fifo_oe_no.value) == 1, "bus claimed with nowhere to put it"
    assert bfm.outstanding > 0

    dut.throttle_i.value = 0
    await bfm.drain()
    assert int(dut.word_count_o.value) == 16
    assert bfm.protocol_errors == []


@cocotb.test()
async def backpressure_mid_burst_stops_within_one_word(dut):
    """RD_N is registered, so one word already committed still transfers.

    That is the slack the consumer has to keep: lyrebird_elastic deasserts on
    its almost-full flag, which leaves four words rather than one.

    Everything here happens on the falling edge, for the reason bfm_ft601q.py
    gives: a count read there is settled, and a level driven there is the one
    the DUT samples at the next rising edge. Reading either at the rising edge
    is off by one in whichever direction the scheduler happens to resolve.
    """
    bfm = await bring_up(dut, burst=None)
    bfm.queue(audio(40))

    await FallingEdge(dut.clk_i)
    while int(dut.word_count_o.value) < 10:
        await FallingEdge(dut.clk_i)

    dut.throttle_i.value = 1
    at_throttle = int(dut.word_count_o.value)
    await ClockCycles(dut.clk_i, 40)
    await FallingEdge(dut.clk_i)
    after = int(dut.word_count_o.value)

    assert after - at_throttle <= 1, (
        f"{after - at_throttle} words after backpressure; at most one may be "
        "already committed"
    )
    assert bfm.outstanding > 0, "the stream drained anyway"

    dut.throttle_i.value = 0
    await bfm.drain()

    assert int(dut.word_count_o.value) == 80
    assert bfm.delivered == audio(40)
    assert bfm.protocol_errors == []


@cocotb.test()
async def repeated_backpressure_loses_no_words(dut):
    """Stop and start the consumer through a whole stream."""
    bfm = await bring_up(dut, burst=(6, 14), gap=(1, 6), seed=3)
    stream = audio(30)
    bfm.queue(stream)

    async def chop():
        while True:
            await ClockCycles(dut.clk_i, 17)
            dut.throttle_i.value = 1
            await ClockCycles(dut.clk_i, 9)
            dut.throttle_i.value = 0

    cocotb.start_soon(chop())
    await bfm.drain()

    assert bfm.delivered == stream
    assert int(dut.word_count_o.value) == len(stream)
    assert int(dut.be_error_count_o.value) == 0
    assert bfm.protocol_errors == []

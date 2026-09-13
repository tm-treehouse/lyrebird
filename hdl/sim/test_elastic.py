"""Elastic buffer tests: packing, channel tracking, prefill, drain, flush.

The toplevel is hdl/rtl/lyrebird_sim_rx.sv, so the buffer is fed the way it is
on the board -- real bus words through the real bus reader and unpacker, driven
by bfm_ft601q.py -- rather than by poking its write port. That is the only way
the three-sample packing gets tested against a stream that arrives in bursts
with gaps, which is what a USB pipe looks like.

The wrapper sizes the buffer for simulation: three blocks and a nine-word
prefill parameter, which is three words per block, so prefill completes once
every block holds four words. Twelve words is 36 samples. The real part is 25
blocks and 6,400 words, per
docs/decisions/0011-pack-three-samples-per-fifo-word.md and hdl/README.md.

lyrebird_unpack consumes the first four samples establishing lock, so the
buffer never sees them. Every expectation here starts at sample four.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from bfm_ft601q import (
    OP_SET_RATE,
    RATE_96K,
    FT601QBridge,
    control,
    left,
    reset,
    right,
)

MCLK_PERIOD_NS = 41       # 24.576 MHz
TICK_CYCLES = 8           # sample tick every 8 MCLK; the board uses 128
LOCK_SAMPLES = 4          # eaten by lyrebird_unpack establishing lock
#: The buffer holds its blocks in reset for ResetHold write clocks out of
#: reset and discards audio while it does, exactly as it does after a flush.
#: Waiting it out makes the first sample the packer sees the first sample sent,
#: which is what lets these tests compare streams element for element.
DRAIN_CYCLES = 24
PREFILL_WORDS = 12        # 3 blocks x (offset 3 + 1) as the wrapper sizes it
PREFILL_SAMPLES = PREFILL_WORDS * 3


def samples(n: int, base: int, start: int = 0) -> list[tuple[int, int]]:
    """n (channel, value) samples, left first, each value carrying its index."""
    return [((start + i) & 1, base + start + i) for i in range(n)]


def words_for(seq) -> list[int]:
    """The bus words that carry a sample sequence."""
    return [right(v) if r else left(v) for r, v in seq]


class SampleSink:
    """Drives the sample-rate tick and records what the buffer emits.

    Everything happens on the falling edge of MCLK: the outputs read there were
    registered at the previous rising edge, and a tick driven there is sampled
    at the next one, so nothing depends on delta-cycle ordering.

    A sample counts as audio only if the buffer reports locked at the same
    edge, which is exactly what separates real samples from the muted zeros
    emitted while prefilling and from the zero an underrun emits.
    """

    def __init__(self, dut, period: int = TICK_CYCLES) -> None:
        self.dut = dut
        self.period = period
        self.samples: list[tuple[int, int]] = []
        self.emitted: list[tuple[int, int, int]] = []
        self._n = 0

    def start(self) -> None:
        cocotb.start_soon(self._run())

    async def _run(self) -> None:
        dut = self.dut
        while True:
            await FallingEdge(dut.mclk_i)
            if int(dut.sample_valid_o.value):
                entry = (
                    int(dut.sample_right_o.value),
                    int(dut.sample_o.value),
                    int(dut.buf_locked_o.value),
                )
                self.emitted.append(entry)
                if entry[2]:
                    self.samples.append((entry[0], entry[1]))
            self._n += 1
            dut.tick_i.value = 1 if (self._n % self.period == 0) else 0

    async def wait_for(self, count: int, *, timeout: int = 40_000) -> None:
        for _ in range(timeout):
            if len(self.samples) >= count:
                return
            await RisingEdge(self.dut.mclk_i)
        raise TimeoutError(
            f"only {len(self.samples)} of {count} samples emitted"
        )

    async def idle(self, cycles: int) -> None:
        for _ in range(cycles):
            await RisingEdge(self.dut.mclk_i)


async def bring_up(dut, **kwargs):
    """Both clocks running, both resets released, the tick generator started."""
    bfm = FT601QBridge(dut, **kwargs)
    dut.throttle_i.value = 0
    dut.tick_i.value = 0
    dut.mrst_ni.value = 0
    cocotb.start_soon(Clock(dut.mclk_i, MCLK_PERIOD_NS, unit="ns").start())
    bfm.start_clock()
    await reset(dut)
    dut.mrst_ni.value = 1
    bfm.start(clock=False)
    await ClockCycles(dut.clk_i, DRAIN_CYCLES)
    sink = SampleSink(dut)
    sink.start()
    return bfm, sink


# ---------------------------------------------------------------------------
# Packing
# ---------------------------------------------------------------------------


@cocotb.test()
async def three_sample_packing_round_trips_exactly(dut):
    """Every sample comes back, in order, bit for bit.

    76 samples in, four eaten by lock, 72 buffered: exactly 24 words of three,
    so nothing is stranded in the packer.
    """
    bfm, sink = await bring_up(dut, burst=None)
    sent = samples(76, 0x110000)
    expected = sent[LOCK_SAMPLES:]
    assert len(expected) % 3 == 0

    bfm.queue(words_for(sent))
    await bfm.drain()
    await sink.wait_for(len(expected))

    assert sink.samples[:len(expected)] == expected
    assert int(dut.underrun_count_o.value) == 0
    assert int(dut.seq_error_count_o.value) == 0, "the blocks fell out of step"
    assert int(dut.overrun_count_o.value) == 0
    assert bfm.protocol_errors == []


@cocotb.test()
async def full_scale_samples_survive_the_packing(dut):
    """The word is 80 bits for 72 bits of audio; nothing may bleed across."""
    bfm, sink = await bring_up(dut, burst=None)
    extremes = [0x800000, 0x7FFFFF, 0xFFFFFF, 0x000000, 0xAAAAAA, 0x555555]
    sent = samples(LOCK_SAMPLES, 0x010000)
    sent += [(i & 1, extremes[i % len(extremes)])
             for i in range(LOCK_SAMPLES, LOCK_SAMPLES + PREFILL_SAMPLES + 12)]
    expected = sent[LOCK_SAMPLES:]

    bfm.queue(words_for(sent))
    await bfm.drain()
    await sink.wait_for(len(expected))

    assert sink.samples[:len(expected)] == expected


@cocotb.test()
async def channel_tracking_survives_the_packing(dut):
    """Three samples is one and a half frames, so words straddle frames.

    Left and right therefore cannot come from the word boundary; they come from
    a counter, per docs/decisions/0011-pack-three-samples-per-fifo-word.md.
    Every other word starts on a right sample, which is the case that breaks if
    the counter is wrong.
    """
    bfm, sink = await bring_up(dut, burst=None)
    sent = samples(76, 0x330000)
    expected = sent[LOCK_SAMPLES:]

    bfm.queue(words_for(sent))
    await bfm.drain()
    await sink.wait_for(len(expected))

    got = sink.samples[:len(expected)]
    for k, (is_right, value) in enumerate(got):
        assert is_right == ((value - 0x330000) & 1), (
            f"sample {k} value {value:#08x} came out as "
            f"{'right' if is_right else 'left'}"
        )
    # Word k holds samples 3k..3k+2, so odd words begin on a right sample.
    assert len(got) >= 6, "too few words to straddle a frame boundary"
    assert got[3][0] == 1, "the second word should begin on a right sample"


# ---------------------------------------------------------------------------
# Prefill
# ---------------------------------------------------------------------------


@cocotb.test()
async def prefill_holds_off_reads_until_the_threshold(dut):
    """Below the threshold nothing plays, and the mute stays asserted.

    The ticks keep coming and the buffer keeps answering them with zeros, so
    the chain downstream runs at a constant rate whatever the host is doing.
    """
    bfm, sink = await bring_up(dut, burst=None)
    short = samples(LOCK_SAMPLES + PREFILL_SAMPLES - 6, 0x440000)
    assert (len(short) - LOCK_SAMPLES) % 3 == 0

    bfm.queue(words_for(short))
    await bfm.drain()
    await sink.idle(TICK_CYCLES * 40)

    assert sink.samples == [], (
        f"{len(sink.samples)} samples played below the prefill threshold"
    )
    assert int(dut.mute_o.value) == 1
    assert int(dut.buf_locked_o.value) == 0
    assert len(sink.emitted) >= 30, "the tick generator stopped"
    assert all(value == 0 for _, value, _ in sink.emitted), \
        "a muted slot carried audio"

    # The words that complete the threshold release it.
    rest = samples(12, 0x440000, start=len(short))
    bfm.queue(words_for(rest))
    await bfm.drain()
    await sink.wait_for(6)

    assert int(dut.buf_locked_o.value) == 1
    assert int(dut.mute_o.value) == 0
    assert sink.samples[0] == short[LOCK_SAMPLES], "resumed on the wrong sample"
    assert sink.samples[0][0] == 0, "resumed on the wrong channel"
    assert int(dut.underrun_count_o.value) == 0


@cocotb.test()
async def a_bursty_stream_drains_without_loss(dut):
    """Bursts and gaps on the write side, a steady tick on the read side.

    This is the crossing doing its job: two unrelated clocks, a producer that
    arrives in lumps, and a consumer that must not notice.
    """
    bfm, sink = await bring_up(dut, burst=(5, 11), gap=(1, 9), seed=5)
    sent = samples(94, 0x550000)
    expected = sent[LOCK_SAMPLES:]
    assert len(expected) % 3 == 0

    bfm.queue(words_for(sent))
    await bfm.drain()
    await sink.wait_for(len(expected))

    assert sink.samples[:len(expected)] == expected
    assert bfm.rxf_deassertions >= 5, "the burst model produced no gaps"
    assert int(dut.seq_error_count_o.value) == 0
    assert int(dut.underrun_count_o.value) == 0


# ---------------------------------------------------------------------------
# Running dry, and starting again
# ---------------------------------------------------------------------------


@cocotb.test()
async def an_underrun_mutes_and_re_prefills(dut):
    """Running dry is counted, muted, and recovered from without losing place.

    The sample that could not be played is not late, it is absent, so the
    buffered stream stands still: when audio returns the first sample out is
    the one that was missing, on the channel it belonged to.
    """
    bfm, sink = await bring_up(dut, burst=None)
    whole = samples(76 + PREFILL_SAMPLES, 0x660000)
    first, second = whole[:76], whole[76:]
    expected_first = whole[LOCK_SAMPLES:76]

    bfm.queue(words_for(first))
    await bfm.drain()
    await sink.wait_for(len(expected_first))

    for _ in range(TICK_CYCLES * 8):
        if int(dut.underrun_count_o.value) >= 1:
            break
        await RisingEdge(dut.mclk_i)

    assert int(dut.underrun_count_o.value) >= 1, "an empty buffer kept playing"
    assert int(dut.mute_o.value) == 1
    assert int(dut.buf_locked_o.value) == 0
    assert len(sink.samples) == len(expected_first), \
        "the underrun emitted audio rather than silence"

    bfm.queue(words_for(second))
    await bfm.drain()
    await sink.wait_for(len(whole) - LOCK_SAMPLES)

    assert sink.samples[:len(whole) - LOCK_SAMPLES] == whole[LOCK_SAMPLES:]
    assert int(dut.seq_error_count_o.value) == 0


@cocotb.test()
async def a_rate_change_discards_the_buffer_and_re_locks(dut):
    """SET_RATE means the buffered audio belongs to the old rate.

    Per docs/decisions/0010-192khz-and-control-word.md: mute, drain,
    reconfigure, prefill, resume. What must not happen is old-rate samples
    playing after the change, or the channels swapping across the gap.
    """
    bfm, sink = await bring_up(dut, burst=None)
    old = samples(76, 0x110000)
    new = samples(120, 0x220000)

    bfm.queue(words_for(old))
    await bfm.drain()
    await sink.wait_for(20)

    bfm.queue(control(OP_SET_RATE, RATE_96K))
    bfm.queue(words_for(new))
    await bfm.drain()
    await sink.wait_for(len(sink.samples) + 30)

    old_out = [s for s in sink.samples if s[1] < 0x220000]
    new_out = sink.samples[len(old_out):]

    assert len(old_out) < len(old) - LOCK_SAMPLES, \
        "the flush played the whole old buffer anyway"
    assert all(v >= 0x220000 for _, v in new_out), \
        "old-rate audio played after the flush"
    assert new_out[0][0] == 0, "resumed mid-frame: the channels are swapped"

    start = new_out[0][1] - 0x220000
    assert new_out == new[start:start + len(new_out)], \
        "the post-flush stream is not contiguous"
    assert int(dut.buf_locked_o.value) == 1
    assert int(dut.seq_error_count_o.value) == 0

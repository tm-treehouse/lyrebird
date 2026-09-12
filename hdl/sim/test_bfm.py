"""Self-tests for the FT601Q bus functional model and the element sink.

These test the test infrastructure, not the design. The DUT is
hdl/rtl/lyrebird_sim_stub_ft601q.sv, which is scaffolding: it masters the FIFO
read handshake, decodes with the real lyrebird_tag_decode, tracks left/right
alternation, and generates element lines so both sinks have something to read.

The load-bearing one is ``dropped_word_breaks_left_right_framing``. A BFM that
cannot drop a word silently cannot exercise tag resync, and a drop that the DUT
cannot notice is not a drop. Both halves are checked here.
"""

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

import sink_elements as se
from bfm_ft601q import (
    ALL_BE,
    OP_MUTE,
    OP_SET_RATE,
    RATE_192K,
    TAG_STATUS,
    FT601QBridge,
    control,
    frames,
    left,
    payload_of,
    reset,
    right,
    tag_of,
    word,
)

# The stub takes the code straight from the top three bits of the sample.
CODE_SHIFT = 21


def sample_for(code: int) -> int:
    return (code & 0x7) << CODE_SHIFT


def coded_frames(pairs) -> list[int]:
    """Word stream for a list of (left code, right code) pairs."""
    return frames([(sample_for(lc), sample_for(rc)) for lc, rc in pairs])


async def bring_up(dut, **kwargs) -> FT601QBridge:
    """Bridge attached, clock running, reset released, stub controls idle.

    The clock starts first and the bus process only after reset. Every test in
    a module shares one simulation, so the DUT can arrive here still holding
    WR_N low from the previous test, and a bus process watching the bus during
    that would record a word that belongs to another test.
    """
    bfm = FT601QBridge(dut, **kwargs)
    dut.status_en_i.value = 0
    dut.dump_en_i.value = 0
    bfm.start_clock()
    await reset(dut)
    bfm.start(clock=False)
    return bfm


# ---------------------------------------------------------------------------
# The read handshake
# ---------------------------------------------------------------------------


@cocotb.test()
async def every_queued_word_arrives(dut):
    """A continuous stream, word for word, nothing added or lost."""
    bfm = await bring_up(dut, burst=None)
    stream = coded_frames([(i % 8, (i + 3) % 8) for i in range(32)])

    bfm.queue(stream)
    await bfm.drain()

    assert bfm.delivered == stream
    assert bfm.dropped == []
    assert int(dut.word_count_o.value) == len(stream)
    assert int(dut.be_error_count_o.value) == 0
    assert int(dut.bad_tag_count_o.value) == 0
    assert int(dut.resync_count_o.value) == 0
    assert bfm.protocol_errors == []
    assert bfm.siwu_cycles == 0


@cocotb.test()
async def data_never_moves_while_rxf_is_deasserted(dut):
    """The RXF_N handshake, checked against the DUT's own accepted-word count.

    A word_count_o increment seen between two falling edges means a transfer
    happened at the rising edge between them, and the RXF_N that governed that
    edge is the one sampled at the earlier falling edge.
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

    stream = coded_frames([(i % 8, 7 - (i % 8)) for i in range(30)])
    bfm.queue(stream)
    await bfm.drain()

    assert violations == [], f"word accepted with RXF_N high at count {violations}"
    assert int(dut.word_count_o.value) == len(stream)
    assert bfm.rxf_deassertions >= 10, (
        f"only {bfm.rxf_deassertions} gaps in {len(stream)} words; "
        "the burst model is not producing gaps"
    )
    assert int(dut.resync_count_o.value) == 0
    assert bfm.protocol_errors == []


@cocotb.test()
async def realistic_bursts_lose_nothing(dut):
    """The default bursty stream, which is what a real USB pipe looks like."""
    bfm = await bring_up(dut, burst=(8, 40), gap=(1, 12), seed=3)
    stream = coded_frames([(i % 8, (5 * i) % 8) for i in range(96)])

    bfm.queue(stream)
    await bfm.drain()

    assert bfm.delivered == stream
    assert int(dut.word_count_o.value) == len(stream)
    assert int(dut.resync_count_o.value) == 0
    assert bfm.protocol_errors == []


@cocotb.test()
async def a_lazy_source_streams_without_a_list(dut):
    """feed() pulls one word at a time, for runs too long to materialise."""
    bfm = await bring_up(dut, burst=(16, 16), gap=(2, 2), seed=1)
    count = 50

    def generate():
        for i in range(count):
            yield left(sample_for(i % 8))
            yield right(sample_for((i + 1) % 8))

    bfm.feed(generate())
    await bfm.drain()

    assert len(bfm.delivered) == 2 * count
    assert int(dut.word_count_o.value) == 2 * count
    assert int(dut.resync_count_o.value) == 0


# ---------------------------------------------------------------------------
# Dropped words
# ---------------------------------------------------------------------------


@cocotb.test()
async def an_undropped_stream_never_resyncs(dut):
    """The control for the drop tests: alternation holds, so resync stays at 0."""
    bfm = await bring_up(dut, burst=(5, 5), gap=(1, 4), seed=11)
    stream = coded_frames([(3, 4)] * 20)

    bfm.queue(stream)
    await bfm.drain()

    assert int(dut.word_count_o.value) == len(stream)
    assert int(dut.resync_count_o.value) == 0


@cocotb.test()
async def dropped_word_breaks_left_right_framing(dut):
    """A dropped right sample is invisible on the bus and visible downstream.

    This is what the drop injection exists for. The tags recover L/R alignment
    when a whole word is lost, per 0005, and nothing can test that unless the
    bridge can lose one.
    """
    bfm = await bring_up(dut, burst=None)
    stream = coded_frames([(i % 8, (i + 1) % 8) for i in range(16)])
    victim_position = 9  # odd position, so a right sample
    victim = stream[victim_position]
    assert tag_of(victim) == tag_of(right(0))

    bfm.drop_at(victim_position)
    bfm.queue(stream)
    await bfm.drain()

    # Invisible on the bus: it was never driven.
    assert bfm.dropped == [(victim_position, victim)]
    assert len(bfm.delivered) == len(stream) - 1
    assert bfm.delivered == stream[:victim_position] + stream[victim_position + 1 :]

    # Visible downstream: one word short, and exactly one broken alternation.
    assert int(dut.word_count_o.value) == len(stream) - 1
    assert int(dut.resync_count_o.value) == 1
    assert int(dut.bad_tag_count_o.value) == 0
    assert bfm.protocol_errors == []


@cocotb.test()
async def dropping_the_first_word_is_seen_too(dut):
    """drop_next() takes the very next word, left in this case."""
    bfm = await bring_up(dut, burst=None)
    stream = coded_frames([(2, 5)] * 8)

    bfm.drop_next()
    bfm.queue(stream)
    await bfm.drain()

    assert bfm.dropped == [(0, stream[0])]
    assert int(dut.word_count_o.value) == len(stream) - 1
    assert int(dut.resync_count_o.value) == 1


@cocotb.test()
async def several_drops_give_several_resyncs(dut):
    """Each lost sample word breaks alternation once."""
    bfm = await bring_up(dut, burst=(6, 6), gap=(1, 3), seed=5)
    stream = coded_frames([(i % 8, (i + 2) % 8) for i in range(24)])
    victims = (4, 17, 30)

    bfm.drop_at(*victims)
    bfm.queue(stream)
    await bfm.drain()

    assert [p for p, _ in bfm.dropped] == list(victims)
    assert int(dut.word_count_o.value) == len(stream) - len(victims)
    assert int(dut.resync_count_o.value) == len(victims)


@cocotb.test()
async def random_drops_are_reproducible(dut):
    """drop_probability is driven by the seeded RNG, so a failure can be rerun."""
    bfm = await bring_up(dut, burst=None, seed=42, drop_probability=0.1)
    stream = coded_frames([(1, 6)] * 60)

    bfm.queue(stream)
    await bfm.drain()

    dropped = [p for p, _ in bfm.dropped]
    assert dropped, "drop_probability dropped nothing at all"
    assert len(bfm.delivered) + len(dropped) == len(stream)
    assert int(dut.word_count_o.value) == len(stream) - len(dropped)
    assert int(dut.resync_count_o.value) > 0


# ---------------------------------------------------------------------------
# Word contents
# ---------------------------------------------------------------------------


@cocotb.test()
async def bad_tags_are_counted_not_decoded(dut):
    """0x3C is outbound only, and an unknown tag is an unknown tag."""
    bfm = await bring_up(dut, burst=None)
    bfm.queue([left(sample_for(1)), word(TAG_STATUS, 0x111111), word(0xFF, 0x222222)])
    await bfm.drain()

    assert int(dut.word_count_o.value) == 3
    assert int(dut.bad_tag_count_o.value) == 2
    assert bfm.protocol_errors == []


@cocotb.test()
async def a_partial_byte_enable_is_rejected(dut):
    """The wire format asserts all four BEs; a fragment is not a sample."""
    bfm = await bring_up(dut, burst=None)
    good = coded_frames([(1, 2), (3, 4)])

    bfm.queue(good[:2])
    bfm.queue(left(sample_for(7)), be=0x7)
    bfm.queue(good[2:])
    await bfm.drain()

    assert bfm.delivered_be.count(0x7) == 1
    assert int(dut.be_error_count_o.value) == 1
    assert int(dut.word_count_o.value) == len(good)
    assert int(dut.bad_tag_count_o.value) == 0


@cocotb.test()
async def control_words_arrive_in_stream_order(dut):
    """Control words are inline, so they take effect between samples."""
    bfm = await bring_up(dut, burst=None)
    bfm.queue(
        [
            left(sample_for(1)),
            control(OP_SET_RATE, RATE_192K),
            right(sample_for(2)),
            control(OP_MUTE, 1),
        ]
    )
    await bfm.drain()

    assert int(dut.ctrl_count_o.value) == 2
    assert int(dut.ctrl_opcode_o.value) == OP_MUTE
    assert int(dut.ctrl_payload_o.value) == 1
    assert int(dut.resync_count_o.value) == 0, "a control word broke L/R tracking"


# ---------------------------------------------------------------------------
# The transmit direction
# ---------------------------------------------------------------------------


@cocotb.test()
async def status_words_reach_the_bridge(dut):
    """The stub numbers its status words, so loss or reordering would show."""
    bfm = await bring_up(dut, burst=None)
    dut.status_en_i.value = 1
    await bfm.wait_received(8)
    dut.status_en_i.value = 0

    received = bfm.received_words()
    assert all(tag_of(w) == TAG_STATUS for w in received)
    assert all(be == ALL_BE for be in bfm.received_be)
    payloads = [payload_of(w) for w in received]
    assert payloads == list(range(len(payloads))), payloads
    assert bfm.protocol_errors == []


@cocotb.test()
async def txe_backpressure_loses_nothing(dut):
    """TXE_N high must stall the write, with DATA held rather than dropped."""
    bfm = await bring_up(dut, burst=None)
    dut.status_en_i.value = 1
    await bfm.wait_received(4)

    bfm.stall_tx(40)
    await ClockCycles(dut.clk_i, 3)  # let the deassertion reach the DUT
    stalled_at = len(bfm.received)
    await ClockCycles(dut.clk_i, 30)
    assert len(bfm.received) == stalled_at, "a word moved with TXE_N deasserted"

    await bfm.wait_received(stalled_at + 6)
    dut.status_en_i.value = 0

    payloads = [payload_of(w) for w in bfm.received_words()]
    assert payloads == list(range(len(payloads))), payloads
    assert bfm.protocol_errors == []


# ---------------------------------------------------------------------------
# The element sink
# ---------------------------------------------------------------------------


@cocotb.test()
async def sink_captures_every_frame(dut):
    """One record per stereo frame, with the codes the samples asked for."""
    bfm = await bring_up(dut, burst=(7, 7), gap=(1, 5), seed=13)
    sink = se.ElementSink(dut.elem_o, dut.clk_i, enable=dut.elem_valid_o)
    sink.start()

    pairs = [(i % 8, (7 - i) % 8) for i in range(24)]
    bfm.queue(coded_frames(pairs))
    await bfm.drain()
    await ClockCycles(dut.clk_i, 4)
    sink.stop()

    assert sink.count == len(pairs), f"{sink.count} records for {len(pairs)} frames"
    got_left, got_right = sink.codes()
    assert got_left.tolist() == [lc for lc, _ in pairs]
    assert got_right.tolist() == [rc for _, rc in pairs]


@cocotb.test()
async def element_loading_is_constant(dut):
    """Exactly seven lines high per channel at every code, at every rotation."""
    bfm = await bring_up(dut, burst=None)
    sink = se.ElementSink(dut.elem_o, dut.clk_i, enable=dut.elem_valid_o)
    sink.start()

    bfm.queue(coded_frames([(lc, rc) for lc in range(8) for rc in range(8)]))
    await bfm.drain()
    await ClockCycles(dut.clk_i, 4)
    sink.stop()

    assert sink.count == 64
    faults = sink.constant_loading_faults()
    assert faults.size == 0, f"records with uneven loading: {faults.tolist()}"


@cocotb.test()
async def the_decode_survives_rotation(dut):
    """A constant code moves around the lines, and still decodes as that code.

    The rotation state is part of the design, so nothing may assume a stable
    mapping from code to line. Here the code never changes and the raw pattern
    does.
    """
    bfm = await bring_up(dut, burst=None)
    sink = se.ElementSink(dut.elem_o, dut.clk_i, enable=dut.elem_valid_o)
    sink.start()

    bfm.queue(coded_frames([(3, 5)] * 14))
    await bfm.drain()
    await ClockCycles(dut.clk_i, 4)
    sink.stop()

    assert len(set(sink.samples)) > 1, "the line pattern never moved"
    got_left, got_right = sink.codes()
    assert set(got_left.tolist()) == {3}
    assert set(got_right.tolist()) == {5}


@cocotb.test()
async def analog_sum_tracks_the_code(dut):
    """Summed as the resistors will sum it, a code k gives 2k-7."""
    bfm = await bring_up(dut, burst=None)
    sink = se.ElementSink(dut.elem_o, dut.clk_i, enable=dut.elem_valid_o)
    sink.start()

    pairs = [(k, 7 - k) for k in range(8)]
    bfm.queue(coded_frames(pairs))
    await bfm.drain()
    await ClockCycles(dut.clk_i, 4)
    sink.stop()

    got_left, got_right = sink.analog_sum()
    assert got_left.tolist() == [2 * lc - 7 for lc, _ in pairs]
    assert got_right.tolist() == [2 * rc - 7 for _, rc in pairs]

    # A mismatched element has to change the sum, or the experiment in 0008
    # would be measuring nothing.
    weights = [1.0] * 7
    weights[0] = 1.05
    mismatched, _ = sink.analog_sum(weights)
    assert mismatched.tolist() != got_left.tolist()


# ---------------------------------------------------------------------------
# The dump file
# ---------------------------------------------------------------------------


@cocotb.test()
async def dump_file_matches_the_python_sink(dut):
    """The RTL dumper and the Python monitor must record the same sequence.

    That is the whole basis for using the dumper on the long runs: it has to be
    the same data, just gathered without a Python call per cycle.
    """
    bfm = await bring_up(dut, burst=(9, 9), gap=(1, 6), seed=17)
    sink = se.ElementSink(dut.elem_o, dut.clk_i, enable=dut.elem_valid_o)
    sink.start()

    dut.dump_en_i.value = 1
    await RisingEdge(dut.clk_i)

    pairs = [(i % 8, (3 * i) % 8) for i in range(40)]
    bfm.queue(coded_frames(pairs))
    await bfm.drain()
    await ClockCycles(dut.clk_i, 4)

    sink.stop()
    dut.dump_en_i.value = 0
    await ClockCycles(dut.clk_i, 2)  # the dumper closes the file on this edge

    records = se.read_dump()
    assert records.size == len(pairs), (
        f"{records.size} records in the dump for {len(pairs)} frames"
    )
    assert records.tolist() == sink.samples, "dump and monitor disagree"

    dumped_left, dumped_right = se.codes(records)
    assert dumped_left.tolist() == [lc for lc, _ in pairs]
    assert dumped_right.tolist() == [rc for _, rc in pairs]
    assert se.constant_loading_faults(records).size == 0

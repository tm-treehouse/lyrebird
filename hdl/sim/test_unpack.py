"""Framing and resync tests for lyrebird_unpack.

Wire format per docs/decisions/0010-192khz-and-control-word.md. The module
pipelines twice: the tag decoder registers, then the framing stage registers.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

TAG_LEFT, TAG_RIGHT, TAG_CTRL, TAG_STATUS = 0xA5, 0x5A, 0xC3, 0x3C
LOCK_WORDS = 4
PIPE = 2


def word(tag, payload):
    return ((tag & 0xFF) << 24) | (payload & 0xFFFFFF)


def frame(n):
    """n stereo frames as alternating left/right words."""
    out = []
    for i in range(n):
        out.append(word(TAG_LEFT, 0x010000 + i))
        out.append(word(TAG_RIGHT, 0x020000 + i))
    return out


async def start(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, unit="ns").start())
    dut.valid_i.value = 0
    dut.word_i.value = 0
    dut.rst_ni.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    await RisingEdge(dut.clk_i)


async def send(dut, words, collect=None):
    """Drive words back to back, optionally collecting emitted samples."""
    for w in words:
        dut.word_i.value = w
        dut.valid_i.value = 1
        await RisingEdge(dut.clk_i)
        if collect is not None and dut.sample_valid_o.value == 1:
            collect.append((int(dut.sample_right_o.value), int(dut.sample_o.value)))
    dut.valid_i.value = 0
    for _ in range(PIPE + 1):
        await RisingEdge(dut.clk_i)
        if collect is not None and dut.sample_valid_o.value == 1:
            collect.append((int(dut.sample_right_o.value), int(dut.sample_o.value)))


@cocotb.test()
async def locks_on_a_clean_stream(dut):
    await start(dut)
    await send(dut, frame(8))
    assert dut.locked_o.value == 1
    assert dut.resync_count_o.value == 0
    assert dut.bad_tag_count_o.value == 0


@cocotb.test()
async def samples_are_suppressed_until_locked(dut):
    """Mis-framed audio must never reach the modulator."""
    await start(dut)
    sent = frame(LOCK_WORDS * 2)          # 16 words
    got = []
    await send(dut, sent, got)
    # The run that establishes lock is consumed, not emitted.
    assert len(got) == len(sent) - LOCK_WORDS, \
        f"emitted {len(got)} of {len(sent)}; expected {len(sent) - LOCK_WORDS}"
    assert got[0][0] == 0, "first emitted sample should be left"


@cocotb.test()
async def anchors_on_left_not_right(dut):
    """A stream starting mid-frame must not lock to the wrong channel."""
    await start(dut)
    await send(dut, [word(TAG_RIGHT, 1)])
    assert dut.locked_o.value == 0
    await send(dut, frame(8))
    assert dut.locked_o.value == 1
    got = []
    await send(dut, frame(2), got)
    assert got and got[0][0] == 0, "first emitted sample should be left"


@cocotb.test()
async def a_dropped_word_resyncs_and_recovers(dut):
    await start(dut)
    await send(dut, frame(6))
    assert dut.locked_o.value == 1
    # Drop one word: send two lefts in a row, which breaks alternation.
    await send(dut, [word(TAG_LEFT, 0xAAAA), word(TAG_LEFT, 0xBBBB)])
    assert int(dut.resync_count_o.value) >= 1, "a broken frame should resync"
    await send(dut, frame(8))
    assert dut.locked_o.value == 1, "should recover lock"


@cocotb.test()
async def several_drops_give_several_resyncs(dut):
    await start(dut)
    await send(dut, frame(6))
    before = int(dut.resync_count_o.value)
    for _ in range(3):
        await send(dut, [word(TAG_LEFT, 1), word(TAG_LEFT, 2)])
        await send(dut, frame(8))
    assert int(dut.resync_count_o.value) - before >= 3


@cocotb.test()
async def a_bad_tag_breaks_lock_and_is_counted(dut):
    await start(dut)
    await send(dut, frame(6))
    assert dut.locked_o.value == 1
    await send(dut, [word(TAG_STATUS, 0x1234)])
    assert dut.bad_tag_count_o.value == 1
    assert dut.locked_o.value == 0
    assert dut.resync_count_o.value == 1


@cocotb.test()
async def control_words_pass_while_hunting(dut):
    """Control is self-identifying, so it must work before lock."""
    await start(dut)
    dut.word_i.value = word(TAG_CTRL, (0x01 << 16) | 0x12)
    dut.valid_i.value = 1
    await RisingEdge(dut.clk_i)
    dut.valid_i.value = 0
    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    assert dut.ctrl_valid_o.value == 1
    assert dut.ctrl_opcode_o.value == 0x01
    assert dut.ctrl_payload_o.value == 0x12
    assert dut.locked_o.value == 0


@cocotb.test()
async def control_does_not_disturb_alternation(dut):
    """A control word between two samples must not break framing."""
    await start(dut)
    await send(dut, frame(6))
    assert dut.locked_o.value == 1
    stream = [word(TAG_LEFT, 0x111111),
              word(TAG_CTRL, (0x02 << 16) | 0xFFFF),
              word(TAG_RIGHT, 0x222222)]
    await send(dut, stream)
    assert dut.resync_count_o.value == 0, "control word broke the framing"
    assert dut.locked_o.value == 1

"""Functional tests for lyrebird_tag_decode.

Wire format per docs/decisions/0010-192khz-and-control-word.md.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

TAG_LEFT = 0xA5
TAG_RIGHT = 0x5A
TAG_CTRL = 0xC3
TAG_STATUS = 0x3C  # outbound only; must decode as a bad tag inbound

OP_SET_RATE = 0x01
RATE_192K = 0x12


def word(tag: int, payload: int) -> int:
    return ((tag & 0xFF) << 24) | (payload & 0xFFFFFF)


async def start(dut):
    """Clock up, reset applied, one idle cycle."""
    cocotb.start_soon(Clock(dut.clk_i, 10, unit="ns").start())
    dut.valid_i.value = 0
    dut.word_i.value = 0
    dut.rst_ni.value = 0
    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    await RisingEdge(dut.clk_i)


async def present(dut, w: int, valid: int = 1):
    """Drive one word and return after its result is registered."""
    dut.word_i.value = w
    dut.valid_i.value = valid
    await RisingEdge(dut.clk_i)
    dut.valid_i.value = 0
    await RisingEdge(dut.clk_i)


@cocotb.test()
async def left_sample(dut):
    await start(dut)
    await present(dut, word(TAG_LEFT, 0x123456))
    assert dut.sample_valid_o.value == 1
    assert dut.sample_right_o.value == 0
    assert dut.sample_o.value == 0x123456
    assert dut.ctrl_valid_o.value == 0
    assert dut.bad_tag_o.value == 0


@cocotb.test()
async def right_sample(dut):
    await start(dut)
    await present(dut, word(TAG_RIGHT, 0xFEDCBA))
    assert dut.sample_valid_o.value == 1
    assert dut.sample_right_o.value == 1
    assert dut.sample_o.value == 0xFEDCBA


@cocotb.test()
async def full_scale_samples(dut):
    """Most negative and most positive 24-bit values must pass unaltered."""
    await start(dut)
    for value in (0x800000, 0x7FFFFF, 0x000000, 0xFFFFFF):
        await present(dut, word(TAG_LEFT, value))
        assert dut.sample_o.value == value, f"sample {value:#08x} corrupted"
        assert dut.sample_valid_o.value == 1


@cocotb.test()
async def control_word(dut):
    await start(dut)
    await present(dut, word(TAG_CTRL, (OP_SET_RATE << 16) | RATE_192K))
    assert dut.ctrl_valid_o.value == 1
    assert dut.ctrl_opcode_o.value == OP_SET_RATE
    assert dut.ctrl_payload_o.value == RATE_192K
    assert dut.sample_valid_o.value == 0
    assert dut.bad_tag_o.value == 0


@cocotb.test()
async def rate_encoding_maps_to_hardware(dut):
    """payload[4] selects the family, payload[1:0] the multiplier.

    Stage count is nine minus the multiplier, per 0010.
    """
    await start(dut)
    cases = [
        (0x00, 0, 0),   # 44.1 kHz
        (0x01, 0, 1),   # 88.2 kHz
        (0x02, 0, 2),   # 176.4 kHz
        (0x10, 1, 0),   # 48 kHz
        (0x11, 1, 1),   # 96 kHz
        (0x12, 1, 2),   # 192 kHz
    ]
    for payload, family, multiplier in cases:
        await present(dut, word(TAG_CTRL, (OP_SET_RATE << 16) | payload))
        got = int(dut.ctrl_payload_o.value)
        assert (got >> 4) & 1 == family, f"{payload:#04x} family"
        assert got & 0x3 == multiplier, f"{payload:#04x} multiplier"


@cocotb.test()
async def status_tag_is_not_accepted_inbound(dut):
    """0x3C is the outbound status tag and must never decode as audio."""
    await start(dut)
    await present(dut, word(TAG_STATUS, 0x111111))
    assert dut.bad_tag_o.value == 1
    assert dut.sample_valid_o.value == 0
    assert dut.ctrl_valid_o.value == 0


@cocotb.test()
async def unknown_tags_raise_bad_tag(dut):
    await start(dut)
    for tag in (0x00, 0xFF, 0xA6, 0x5B, 0xC4, 0x3C):
        await present(dut, word(tag, 0x000001))
        assert dut.bad_tag_o.value == 1, f"tag {tag:#04x} should be rejected"
        assert dut.sample_valid_o.value == 0


@cocotb.test()
async def nothing_asserts_without_valid(dut):
    """A well-formed word with valid low must produce no output at all."""
    await start(dut)
    await present(dut, word(TAG_LEFT, 0x123456), valid=0)
    assert dut.sample_valid_o.value == 0
    assert dut.ctrl_valid_o.value == 0
    assert dut.bad_tag_o.value == 0

# 0010 — 192 kHz support and an in-band control word

**Status:** accepted

## Context

Every budget in the project assumed 96 kHz. Supporting 192 kHz turns out to be
cheap, because 96 and 192 kHz are both in the 48 kHz family and share the
24.576 MHz oscillator. The modulator runs at that oscillator either way, so
noise shaping is fixed in absolute frequency and performance in the audible
band is identical at both rates.

Separately, the wire format had no way for the host to tell the FPGA anything.
It carried tagged samples and nothing else, so a rate change could not even be
announced.

## Decision

**Support 48, 96 and 192 kHz on the 48 kHz oscillator, and 44.1, 88.2 and
176.4 kHz on the 44.1 kHz oscillator.** All interpolation ratios are powers of
two, so the chain is a half-band cascade and the rate selects how many stages
run.

| Rate | Ratio at 24.576 MHz | Half-band stages |
| --- | --- | --- |
| 48 kHz | 512 | 9 |
| 96 kHz | 256 | 8 |
| 192 kHz | 128 | 7 |

The stages line up exactly: 192 kHz through seven stages uses the same absolute
rates as stages two through eight of the 96 kHz chain. Switching rate bypasses
stages from the front. It is a mux, not a second filter chain.

**Add two word types to the wire format**, using tag values that continue the
complementary-pair pattern of the sample tags.

| Tag | Direction | Meaning |
| --- | --- | --- |
| `0xA5` | host to FPGA | Left sample |
| `0x5A` | host to FPGA | Right sample |
| `0xC3` | host to FPGA | Control word |
| `0x3C` | FPGA to host | Status word |

The status word uses the FT601Q transmit direction, which
[0005](0005-ft601q-bridge-io-voltage.md) left available for exactly this.

### Control word layout

```
DATA[31:24]  0xC3
DATA[23:16]  opcode
DATA[15:0]   payload
```

| Opcode | Name | Payload |
| --- | --- | --- |
| `0x00` | NOP | Ignored |
| `0x01` | SET_RATE | See encoding below |
| `0x02` | SET_VOLUME | 16-bit unsigned linear gain, `0xFFFF` is unity |
| `0x03` | MUTE | Bit 0 |
| `0x04` | RESET | Flush and re-lock the pipeline |

Rate encoding, chosen so the fields map straight onto hardware:

- `payload[4]` selects the family, and therefore the oscillator enable.
  0 is the 44.1 kHz family, 1 is the 48 kHz family.
- `payload[1:0]` is the multiplier, 0 for base, 1 for double, 2 for quadruple,
  and the stage count is nine minus this value.

So 48 kHz is `0x10`, 96 kHz is `0x11`, 192 kHz is `0x12`, and 44.1 kHz is
`0x00`.

### Status word

Reports current rate, buffer fill, underrun and overrun counts, lock state, and
the module ID strapped on the mezzanine. The last one matters: it is how the
host learns whether a headphone module is attached without the user telling it.

## Consequences

**The block RAM budget finally binds.** Prefill absorbs host scheduling jitter,
which is a time-domain problem, so 192 kHz needs the same milliseconds and
therefore twice the samples. The buffer must be sized for the worst case.

| Rate | 50 ms prefill | Blocks, of 32 |
| --- | --- | --- |
| 96 kHz | 4,800 frames | 10 |
| 192 kHz | 9,600 frames | 20 |

A 100 ms prefill at 192 kHz would need 38 blocks and does not fit, capping
prefill near 80 ms. Still comfortable, but this is the first resource in the
design that is genuinely constrained rather than abundant.

**Rate changes discard buffered audio.** Control words are inline, so the FPGA
sees them in order, but samples already in the elastic buffer belong to the old
rate. A `SET_RATE` therefore mutes, drains, reconfigures, prefills and resumes,
and the host should expect a gap. Changing rate within a family is faster than
crossing families, because no oscillator has to settle.

**Volume is digital and lives in the FPGA**, which is why no volume part
appears on the output module. Apply it inside the interpolation chain at full
internal precision rather than to the incoming PCM, so the truncation happens
at the modulator input where it is shaped rather than at the input where it is
not. Note the limit: digital attenuation spends resolution, so deep cuts trade
dynamic range. With a 24-bit source against a roughly 20-bit output there is
headroom, but it is not free.

**Ultrasonic content costs modulator headroom.** At 192 kHz the source can
carry material up to 96 kHz, and high-level content up there eats headroom and
can intermodulate in the analog stage. Low-pass it.

# host

PC-side driver. The FT601Q does not enumerate as a USB Audio Class device, so
the OS will not offer it as an output. This program opens a **D3XX** handle and
writes raw PCM.

- `src/` — implementation
- `include/` — public headers

D3XX is the FT60x-family library, not the D2XX used by the older FT2232H. The
two APIs are not interchangeable.

## Contract

Write 32-bit words, little-endian, tag byte in the most significant position.
Samples alternate channels. The FPGA hunts for a valid tag if alignment is
lost. Full protocol in
[0010](../docs/decisions/0010-192khz-and-control-word.md).

| Tag | Direction | Payload |
| --- | --- | --- |
| `0xA5` | write | Left sample, 24-bit signed |
| `0x5A` | write | Right sample |
| `0xC3` | write | Control: opcode, then payload |
| `0x3C` | read | Status |

Control words are inline with audio and take effect in stream order. Opcodes
cover rate selection, volume, mute and reset.

**A rate change discards buffered audio.** Send `SET_RATE`, expect a gap while
the FPGA drains and prefills, then resume writing. Changing rate within a
family is quicker than crossing between the 44.1 and 48 kHz families, because
no oscillator has to settle.

**Read the status word to learn what is attached.** It reports current rate,
buffer fill, underrun and overrun counts, lock state, and the module ID
strapped on the mezzanine, which is how the host discovers whether a headphone
module is present.

## Throughput

2ch / 24-bit / 192 kHz padded to 32 bits is 1.54 MB/s, against a bus capable of
hundreds of MB/s. Bandwidth is not the constraint and never will be. Host
scheduling jitter is the only thing that can cause an underrun, and the FPGA's
prefill exists to absorb it.

Use large writes and keep several in flight so the pipe never drains.

## Sources

Bench bring-up reads a WAV file and pumps it. Real playback captures a loopback
device: a PipeWire null sink plus its monitor source on Linux, WASAPI loopback
or VB-Cable on Windows.

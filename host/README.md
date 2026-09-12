# host

PC-side driver. The FT601Q does not enumerate as a USB Audio Class device, so
the OS will not offer it as an output. This program opens a **D3XX** handle and
writes raw PCM.

- `src/` — implementation
- `include/` — public headers

D3XX is the FT60x-family library, not the D2XX used by the older FT2232H. The
two APIs are not interchangeable.

## Contract

Write 32-bit words, little-endian. Tag byte in the most significant position,
`0xA5` for left and `0x5A` for right, alternating channels. Each word is one
sample. The FPGA hunts for a valid tag if alignment is lost.

## Throughput

2ch / 24-bit / 96 kHz padded to 32 bits is 768 kB/s, against a bus capable of
hundreds of MB/s. Bandwidth is not the constraint and never will be. Host
scheduling jitter is the only thing that can cause an underrun, and the FPGA's
prefill exists to absorb it.

Use large writes and keep several in flight so the pipe never drains.

## Sources

Bench bring-up reads a WAV file and pumps it. Real playback captures a loopback
device: a PipeWire null sink plus its monitor source on Linux, WASAPI loopback
or VB-Cable on Windows.

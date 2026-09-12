# 0003 — Self-describing sample framing

**Status:** accepted

## Context

The 245 Sync FIFO is a raw byte stream. There are no packet boundaries and no
start-of-frame marker. A single dropped or inserted byte permanently swaps left
and right, and nothing in the hardware would ever notice.

## Decision

Make every sample self-describing rather than relying on stream position.

- Pad each 24-bit sample to 32 bits.
- Put a tag byte in the MSB position: `0xA5` for left, `0x5A` for right.
- The FPGA hunts for a valid tag whenever the expected one does not appear.

## Consequences

Recovery from a byte-level fault costs at most one sample instead of lasting
forever. The tag values are chosen to be bit-complementary and unlikely to
appear by accident at a word boundary in real audio.

The cost is padding overhead, which is free here. Two channels of 24-bit at
96 kHz is 576 kB/s raw and 768 kB/s padded, against roughly 35 MB/s available.

Note that a sufficiently pathological audio payload can contain the tag values
at the wrong offset. Resync is best-effort and should require several
consecutive well-formed samples before it declares lock.

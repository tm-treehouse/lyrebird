"""Fixed facts of the Lyrebird signal chain.

Nothing in this module is a modelling choice. It is the set of constraints the
rest of the model is measured against, transcribed from:

  docs/decisions/0008-multibit-delta-sigma-with-dwa.md
  docs/decisions/0010-192khz-and-control-word.md
  docs/decisions/0012-module-clock-architecture.md
  hdl/README.md
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Clocks (0012: oscillator at the 1024 multiple, divided by two)
# ---------------------------------------------------------------------------

OSC_48K = 49_152_000.0          # Crystek CCHD-957, 48 kHz family
OSC_441K = 45_158_400.0         # Crystek CCHD-957, 44.1 kHz family

ELEMENT_CLOCK = {
    "48k": OSC_48K / 2.0,       # 24.576 MHz
    "44k1": OSC_441K / 2.0,     # 22.5792 MHz
}

BASE_RATE = {"48k": 48_000.0, "44k1": 44_100.0}

# 0010 / hdl README: multiplier 0/1/2, stage count = 9 - multiplier.
MULTIPLIERS = (1, 2, 4)
RATIOS = (512, 256, 128)
STAGE_COUNTS = (9, 8, 7)

# The canonical cascade is the base-rate (9 stage) chain. A higher rate
# bypasses stages from the FRONT, so stage index s in 1..9 always sits at the
# same absolute rate: input BASE * 2**(s-1), output BASE * 2**s.
N_STAGES = 9

# ---------------------------------------------------------------------------
# Quantizer / elements (0008)
# ---------------------------------------------------------------------------

QUANT_BITS = 3
N_LEVELS = 1 << QUANT_BITS      # 8
N_ELEMENTS = N_LEVELS - 1       # 7 unit elements per side
# Differential: for code k, k positive-side elements and 7-k negative-side
# elements are driven, so exactly 7 elements are high at every code.
DIFF_CODES = tuple(2 * k - N_ELEMENTS for k in range(N_LEVELS))  # -7 .. +7

PCM_BITS = 24

# ---------------------------------------------------------------------------
# Audio band
# ---------------------------------------------------------------------------

AUDIO_LO = 20.0
AUDIO_HI = 20_000.0

# Passband edge as a fraction of the sample rate that a stage's input carries.
# 0.4535 puts the base-rate passband edge at 21.768 kHz (48 kHz family) and
# 19.999 kHz (44.1 kHz family) with the half-band transition centred on Fs/2.
ALPHA = 0.4535

# 0012: 3.3 V element rail, 110 dB dynamic range target, ~10 uV noise.
DYNAMIC_RANGE_TARGET_DB = 110.0


@dataclass(frozen=True)
class Mode:
    """One supported sample rate."""

    family: str                 # "48k" or "44k1"
    multiplier: int             # 1, 2 or 4
    fs: float                   # sample rate, Hz
    ratio: int                  # interpolation ratio
    n_stages: int               # half-band stages actually run
    first_stage: int            # 1-based index of the first stage run
    element_clock: float

    @property
    def name(self) -> str:
        khz = self.fs / 1000.0
        return f"{khz:g} kHz"

    @property
    def stages(self) -> tuple[int, ...]:
        return tuple(range(self.first_stage, N_STAGES + 1))


def modes(family: str | None = None) -> list[Mode]:
    """Every supported rate, or every rate of one family."""
    out: list[Mode] = []
    fams = [family] if family else ["48k", "44k1"]
    for fam in fams:
        base = BASE_RATE[fam]
        clk = ELEMENT_CLOCK[fam]
        for mult, ratio, nst in zip(MULTIPLIERS, RATIOS, STAGE_COUNTS):
            out.append(
                Mode(
                    family=fam,
                    multiplier=mult,
                    fs=base * mult,
                    ratio=ratio,
                    n_stages=nst,
                    first_stage=N_STAGES - nst + 1,
                    element_clock=clk,
                )
            )
    return out


def stage_rates(family: str = "48k") -> list[tuple[float, float]]:
    """(input rate, output rate) for canonical stages 1..9."""
    base = BASE_RATE[family]
    return [(base * 2 ** (s - 1), base * 2 ** s) for s in range(1, N_STAGES + 1)]


def osr(bandwidth: float = AUDIO_HI, family: str = "48k") -> float:
    """Noise-shaping oversampling ratio: element clock over twice the band.

    This is the ratio that sets modulator performance, and it does not depend
    on the sample rate -- the modulator always runs at the element clock.
    """
    return ELEMENT_CLOCK[family] / (2.0 * bandwidth)


def check() -> None:
    """Assert the fixed facts are self-consistent. Raises on violation."""
    assert ELEMENT_CLOCK["48k"] == 24_576_000.0
    assert ELEMENT_CLOCK["44k1"] == 22_579_200.0
    for m in modes():
        assert m.fs * m.ratio == m.element_clock, (m.name, m.fs * m.ratio)
        assert m.ratio == 2 ** m.n_stages
        assert m.n_stages == N_STAGES - (m.multiplier.bit_length() - 1)
        assert len(m.stages) == m.n_stages
    # 192 kHz stages sit at the same absolute rates as stages 2..8 of the
    # 96 kHz chain (0010).
    r = stage_rates("48k")
    m96 = modes("48k")[1]
    m192 = modes("48k")[2]
    assert [r[s - 1] for s in m192.stages] == [r[s - 1] for s in m96.stages][1:]
    assert len(DIFF_CODES) == N_LEVELS and DIFF_CODES[0] == -7 and DIFF_CODES[-1] == 7
    # exactly 7 elements high at every code
    for k in range(N_LEVELS):
        assert k + (N_ELEMENTS - k) == N_ELEMENTS


if __name__ == "__main__":
    check()
    print(f"element clock  48k family: {ELEMENT_CLOCK['48k']/1e6:.4f} MHz")
    print(f"element clock 44k1 family: {ELEMENT_CLOCK['44k1']/1e6:.4f} MHz")
    print()
    for m in modes():
        print(
            f"{m.family:5s} {m.name:>10s}  ratio {m.ratio:4d}  "
            f"stages {m.n_stages} ({m.first_stage}..{N_STAGES})  "
            f"clk {m.element_clock/1e6:.4f} MHz"
        )
    print()
    print(f"OSR to 20 kHz, 48k family: {osr():.1f}")
    print(f"OSR to 20 kHz, 44k1 family: {osr(family='44k1'):.1f}")

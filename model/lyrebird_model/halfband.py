"""Half-band interpolation cascade.

Structure is fixed by 0010: powers of two, nine stages at the base rate, and a
higher rate bypasses stages from the front. Canonical stage ``s`` in 1..9
therefore always sits at the same absolute rate -- input ``BASE * 2**(s-1)``,
output ``BASE * 2**s`` -- and the rate selector is a mux.

What is open is each stage's passband edge, tap count, ripple and stopband.
This module designs them and then measures what it designed.

Design method
-------------
A half-band filter of length ``N = 4k+3`` has every odd-offset tap zero and a
centre tap of exactly 0.5. Writing it as

    h[n] = 0.5 * delta[n - m] + upsample2(g)[n],    m = 2k+1

with ``g`` of length ``2k+2``, the zero-phase response is

    H(f) = 0.5 + G(2f)

where ``G`` is the (Type II, even length) zero-phase response of ``g``. Type II
antisymmetry gives ``G(1-nu) = -G(nu)``, so approximating ``G = 0.5`` over
``[0, 2*fp]`` and letting the rest float delivers ``H = 1 +/- delta`` in
``[0, fp]`` and ``|H| <= delta`` in ``[0.5-fp, 0.5]`` at the same time.

That means the half-band structure is exact by construction -- the zero taps
are bit-exact zeros, not small numbers -- and the whole of the minimax
accuracy goes into the response. Designing the length-``N`` filter directly and
then forcing the zeros afterwards costs about 5 dB of stopband, measured, and
is not used.

The one real choice
-------------------
How wide a passband must the stages that can be *first* have? A stage that is
ever first in the chain sees raw PCM and must protect the whole band its own
sample rate can carry. A stage that always has a band-limited signal in front
of it can take a much wider transition and far fewer taps. ``max_first_stage``
selects between:

  1 -- treat only stage 1 as ever-first, so every stage's passband edge is
       ``ALPHA * BASE``. Cheapest. 96 and 192 kHz sources get band-limited to
       the base-rate audio band.
  3 -- stages 1, 2 and 3 are each first in some mode (48 / 96 / 192 kHz), so
       all three carry the steep design and every rate keeps its own
       ``ALPHA * Fs`` bandwidth.

Because the steep stages share one normalized design, ``max_first_stage = 3``
costs no extra coefficient storage at all, only extra delay lines and
multiplier bandwidth.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.signal import firls, freqz, remez, upfirdn

from . import chain

STOPBAND_TARGET_DB = 120.0
GRID = 1 << 16
GRID_DENSITIES = (32, 128, 512, 2048, 8192, 32768, 131072)


def _kaiser_taps(atten_db: float, trans_norm: float) -> int:
    """Kaiser's length estimate, rounded up to the next N = 4k+3.

    Only ever a starting hint. It overshoots badly for the very wide
    transitions of the late stages.
    """
    n = int(np.ceil((atten_db - 13.0) / (14.6 * trans_norm))) + 1
    while (n - 3) % 4 or n < 3:
        n += 1
    return n


def _subfilter(k: int, fp: float) -> np.ndarray | None:
    """Length 2k+2 Type II filter approximating 0.5 over [0, 2*fp]."""
    length = 2 * k + 2
    band = [0.0, 2.0 * fp]
    for gd in GRID_DENSITIES:
        try:
            return remez(length, band, [0.5], fs=1.0, grid_density=gd)
        except ValueError as exc:
            if "converge" in str(exc):
                break                     # a denser grid will not fix this
    try:
        return firls(length, band, [0.5, 0.5], fs=1.0)
    except Exception:
        return None


def _assemble(k: int, g: np.ndarray) -> np.ndarray:
    """Build the length 4k+3 half-band from its Type II subfilter.

    The coefficients are used exactly as designed. Rescaling them to force a DC
    gain of exactly 1 is tempting and costs 6.0 dB of stopband, measured: the
    equiripple solution puts the passband at ``1 +/- delta`` and the stopband at
    ``0 +/- delta`` simultaneously, and DC sits on a passband ripple peak, so
    pulling DC down to 1 shifts the stopband ripple from ``+/-delta`` to
    ``0..2*delta``. The DC gain error left behind is the passband ripple itself,
    which for the steep stage is 0.0000037 dB.
    """
    h = np.zeros(4 * k + 3, dtype=np.float64)
    h[0::2] = g
    if not np.all(np.isfinite(h)) or h.sum() <= 0.25:
        raise ValueError("degenerate half-band candidate")
    h[2 * k + 1] = 0.5
    return h


def _measure(h: np.ndarray, fp: float) -> tuple[float, float]:
    """(passband ripple, +/- dB) and (worst stopband gain, dB)."""
    w, hh = freqz(h, worN=GRID, fs=1.0)
    mag = np.abs(hh)
    pb = mag[w <= fp]
    sb = mag[w >= 0.5 - fp]
    ripple = 20.0 * np.log10(pb.max() / pb.min()) / 2.0
    return float(ripple), float(20.0 * np.log10(sb.max()))


@dataclass(frozen=True)
class HalfBand:
    """One designed half-band stage, in normalized (output-rate) units."""

    fp: float                   # passband edge, cycles per output sample
    taps: np.ndarray            # unit DC gain; multiply by 2 to interpolate
    ripple_db: float            # +/- dB over [0, fp]
    stopband_db: float          # worst gain over [0.5-fp, 0.5], dB
    target_db: float

    @property
    def fstop(self) -> float:
        return 0.5 - self.fp

    @property
    def dc_gain_db(self) -> float:
        return float(20.0 * np.log10(self.taps.sum()))

    @property
    def n_taps(self) -> int:
        return len(self.taps)

    @property
    def n_nonzero(self) -> int:
        return int(np.count_nonzero(self.taps))

    @property
    def n_mults(self) -> int:
        """General multiplies per *input* sample.

        Polyphase: at interpolation gain 2 the centre tap is 1.0, so the even
        output phase is the input sample on a wire. All the arithmetic sits in
        the odd phase, runs at the input rate, and folds by coefficient
        symmetry: (N-3)/4 + 1 products.
        """
        return (self.n_taps - 3) // 4 + 1

    @property
    def group_delay_out(self) -> float:
        """Delay in output samples. Linear phase, so it is flat."""
        return (self.n_taps - 1) / 2.0

    def response(self, f_norm: np.ndarray) -> np.ndarray:
        """|H| at normalized output-rate frequencies. Periodic, unit DC gain."""
        _, h = freqz(self.taps, worN=2.0 * np.pi * np.asarray(f_norm, dtype=np.float64))
        return np.abs(h)

    def quantized(self, bits: int) -> tuple[np.ndarray, float, float]:
        """Coefficients rounded to a signed ``bits``-bit fraction.

        The centre tap stays a bit-exact 0.5 -- a shift in hardware -- so only
        the real multiplier coefficients are quantized. Returns
        (taps, ripple_db, stopband_db) measured on the quantized set.
        """
        scale = 1 << (bits - 1)
        q = np.round(self.taps * scale) / scale
        q[1::2] = 0.0
        q[(len(q) - 1) // 2] = 0.5
        ripple, stop = _measure(q, self.fp)
        return q, ripple, stop

    def csd_terms(self, bits: int = 18) -> int:
        """Non-zero signed-digit terms in the quantized coefficients.

        A rough count of adders if the stage is built as shifts and adds
        instead of multipliers, which 0008 says the late stages should be.
        """
        scale = 1 << (bits - 1)
        q = np.round(self.taps * scale).astype(np.int64)
        m = (len(q) - 1) // 2
        total = 0
        for v in np.abs(q[0 : m : 2]):       # one half, symmetry folds the rest
            n = int(v)
            while n:
                # canonical signed digit: absorb runs of ones
                if n & 1:
                    total += 1
                    n = n + 1 if (n & 3) == 3 else n - 1
                n >>= 1
        return total


@lru_cache(maxsize=64)
def design(fp: float, target_db: float = STOPBAND_TARGET_DB,
           max_taps: int = 1023) -> HalfBand:
    """Shortest N = 4k+3 half-band whose *measured* stopband meets target_db.

    Ascending scan from k = 0. That is slower than starting at Kaiser's length
    estimate, but it is the only way to get the true minimum: the estimate
    overshoots by a factor of four on the widest transitions, and for those the
    exchange algorithm stops converging above the length that is actually
    needed, so a design failure at some k says nothing about k+1. Candidates
    that fail to design are skipped; only a measured stopband accepts one.
    Results are cached, and the distinct designs in a cascade number three or
    four.
    """
    if not 0.0 < fp < 0.25:
        raise ValueError(f"passband edge {fp} must be in (0, 0.25)")

    k, skipped = 0, 0
    while 4 * k + 3 <= max_taps:
        g = _subfilter(k, fp)
        if g is not None and np.all(np.isfinite(g)):
            try:
                h = _assemble(k, g)
            except ValueError:
                h = None
            if h is not None:
                ripple, stop = _measure(h, fp)
                if stop <= -target_db:
                    return HalfBand(fp=fp, taps=h, ripple_db=ripple,
                                    stopband_db=stop, target_db=target_db)
            else:
                skipped += 1
        else:
            skipped += 1
        k += 1
    raise RuntimeError(
        f"no half-band under {max_taps} taps reaches {target_db} dB at fp={fp} "
        f"({skipped} candidates failed to design)")


# ---------------------------------------------------------------------------
# The cascade
# ---------------------------------------------------------------------------

@dataclass
class Stage:
    index: int                  # canonical 1..9
    f_in: float
    f_out: float
    fp_abs: float
    fstop_abs: float
    hb: HalfBand
    element_clock: float

    @property
    def clocks_per_input(self) -> float:
        """Element clocks available per input sample, i.e. the time-share budget."""
        return self.element_clock / self.f_in

    @property
    def mac_rate(self) -> float:
        return self.hb.n_mults * self.f_in

    @property
    def fits_one_multiplier(self) -> bool:
        return self.hb.n_mults <= self.clocks_per_input


@dataclass
class Cascade:
    family: str
    max_first_stage: int
    alpha: float
    target_db: float
    stages: list[Stage]

    def stage(self, index: int) -> Stage:
        return self.stages[index - 1]

    def for_mode(self, mode: chain.Mode) -> list[Stage]:
        return [self.stage(s) for s in mode.stages]

    def distinct(self) -> list[Stage]:
        """One representative per distinct coefficient set."""
        out: list[Stage] = []
        seen: set[int] = set()
        for s in self.stages:
            if id(s.hb) not in seen:
                seen.add(id(s.hb))
                out.append(s)
        return out

    # -- hardware cost ----------------------------------------------------
    def cost(self, mode: chain.Mode) -> dict:
        st = self.for_mode(mode)
        total_mac = sum(s.mac_rate for s in st)
        seen: set[int] = set()
        coeff = 0
        for s in st:
            if id(s.hb) not in seen:
                seen.add(id(s.hb))
                coeff += s.hb.n_mults
        return {
            "mode": mode.name,
            "stages": mode.n_stages,
            "taps_total": sum(s.hb.n_taps for s in st),
            "nonzero_total": sum(s.hb.n_nonzero for s in st),
            "mults_per_stage": [s.hb.n_mults for s in st],
            "mac_rate_msps": total_mac / 1e6,
            "multipliers_at_clock": total_mac / mode.element_clock,
            "coeff_words": coeff,
            "delay_words": sum(s.hb.n_taps for s in st),
            "group_delay_us": sum(s.hb.group_delay_out / s.f_out for s in st) * 1e6,
            "worst_stage_over_budget": [s.index for s in st if not s.fits_one_multiplier],
        }

    # -- response ---------------------------------------------------------
    def composite(self, mode: chain.Mode, f: np.ndarray) -> np.ndarray:
        """|H(f)| of the whole cascade for one mode. Unit DC gain."""
        f = np.asarray(f, dtype=np.float64)
        mag = np.ones_like(f)
        for s in self.for_mode(mode):
            mag = mag * s.hb.response(f / s.f_out)
        return mag

    def image_suppression(self, mode: chain.Mode, n_grid: int = 6001) -> list[dict]:
        """Worst composite gain over every image band the source produces.

        A source at Fs carrying 0..fp puts copies at ``m*Fs +/- fp`` for every
        m >= 1. Nothing in this chain decimates, so no copy ever folds back
        into the audio band; what matters is how far down each one is when it
        reaches the modulator.
        """
        fp = self.stage(mode.first_stage).fp_abs
        nyq = mode.element_clock / 2.0
        out: list[dict] = []
        m = 1
        while m * mode.fs - fp < nyq:
            lo = max(m * mode.fs - fp, 0.0)
            hi = min(m * mode.fs + fp, nyq)
            if hi > lo:
                f = np.linspace(lo, hi, n_grid)
                mag = self.composite(mode, f)
                j = int(np.argmax(mag))
                out.append({"m": m, "f_lo": lo, "f_hi": hi,
                            "worst_db": float(20.0 * np.log10(mag[j])),
                            "worst_f": float(f[j])})
            m += 1
        return out

    def passband_error(self, mode: chain.Mode,
                       band: tuple[float, float] | None = None,
                       n_grid: int = 20001) -> dict:
        if band is None:
            band = (chain.AUDIO_LO, chain.AUDIO_HI)
        f = np.linspace(band[0], band[1], n_grid)
        mag = 20.0 * np.log10(self.composite(mode, f))
        return {"band": band, "max_db": float(mag.max()), "min_db": float(mag.min()),
                "ripple_pp_db": float(mag.max() - mag.min()),
                "at_hi_db": float(mag[-1])}

    # -- time domain ------------------------------------------------------
    def interpolate(self, x: np.ndarray, mode: chain.Mode,
                    coeff_bits: int | None = None) -> np.ndarray:
        """PCM at mode.fs up to the element clock. Gain 1: 0 dBFS in, 0 dBFS out."""
        y = np.asarray(x, dtype=np.float64)
        for s in self.for_mode(mode):
            h = s.hb.taps if coeff_bits is None else s.hb.quantized(coeff_bits)[0]
            y = upfirdn(2.0 * h, y, up=2, down=1)
        return y

    def settle_samples(self, mode: chain.Mode) -> int:
        """Output samples to discard so the cascade transient is out of the record."""
        n = 0
        for s in self.for_mode(mode):
            n = 2 * n + s.hb.n_taps
        return int(n)


def build(family: str = "48k", max_first_stage: int = 3,
          alpha: float = chain.ALPHA,
          target_db: float = STOPBAND_TARGET_DB) -> Cascade:
    base = chain.BASE_RATE[family]
    clk = chain.ELEMENT_CLOCK[family]
    stages: list[Stage] = []
    for s, (f_in, f_out) in enumerate(chain.stage_rates(family), start=1):
        # widest input band this stage can ever be asked to carry
        fp_abs = alpha * base * 2 ** (min(s, max_first_stage) - 1)
        hb = design(round(fp_abs / f_out, 12), target_db)
        stages.append(Stage(index=s, f_in=f_in, f_out=f_out, fp_abs=fp_abs,
                            fstop_abs=f_in - fp_abs, hb=hb, element_clock=clk))
    return Cascade(family=family, max_first_stage=max_first_stage, alpha=alpha,
                   target_db=target_db, stages=stages)

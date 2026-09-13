"""Fixed-point sizing of the interpolation datapath.

:mod:`halfband` settles how wide the *coefficients* must be. It says nothing
about the words the samples travel in, and the HDL needs two more numbers per
stage: the **signal word**, which is the width of that stage's delay line and
of the samples it hands to the next stage, and the **accumulator**, which is
the width the products are summed in before the result is rounded back down to
a signal word.

What is modelled
----------------
A half-band of length ``N = 4k+3`` upsampled by two splits into two phases that
cost very different things:

* the **filtered phase**, ``y[2m] = sum_j g[j] * x[m-j]`` over the ``2k+2``
  even-index taps, folded by coefficient symmetry into ``k+1`` products; and
* the **pass-through phase**, ``y[2m+1] = x[m-k]``, which is the centre tap of
  0.5 against an interpolation gain of 2. It is a wire, not a multiplier.

Both are modelled at their real widths:

1. The symmetric pre-add ``x[m-j] + x[m-(L-1-j)]`` is exact. It is one bit
   wider than the signal word and costs nothing to keep.
2. Each product is rounded into the accumulator at ``acc_frac`` fractional
   bits. This is the pessimistic reading of "accumulator width": a narrow
   accumulator rounds every product rather than only the final sum, which is
   what a MAC whose output register is the accumulator actually does. Setting
   ``acc_frac = coeff_bits - 1 + sig_frac`` makes every product exact and gives
   the full-precision case for free.
3. The finished accumulator is rounded to the stage's own ``sig_frac``.
4. The pass-through phase is rounded to the same ``sig_frac``. That rounding is
   free whenever a stage's output word is no narrower than its input word,
   which is the normal case; it is modelled so that a chain which narrows as it
   speeds up is charged for what narrowing costs.

Which way ties go
-----------------
Round-half-up -- add half an LSB and truncate -- is one adder and the obvious
choice. It is also biased: a value already sitting on a finer grid ties exactly
half the time and every tie goes up, so each rounding leaves about a quarter of
an LSB of offset and the stages add. That offset is not the harmless DC it
looks like. Measured here, 8.0e-9 of it -- half an LSB of a 26-bit word, 162 dB
below full scale -- at the modulator input costs 16.8 dB of in-band SNR,
because a delta-sigma loop turns a static input offset into idle tones in the
lowest bins of the audio band. Removing that DC restores the figure exactly.

So the default here is ``"half_even"``, convergent rounding, which is unbiased.
``"half_up"`` is kept to reproduce the measurement above.

Why the answer is expected to fall along the chain
--------------------------------------------------
Rounding noise injected at a stage whose output rate is ``F`` is white over
``F/2`` and only the part inside the audio band survives to be heard. Stage 9
runs at 24.576 MHz and stage 1 at 96 kHz, so the same rounding at stage 9
lands 10*log10(24.576e6/96e3) = 24 dB quieter in band. The late stages, which
are the ones running at the element clock and therefore the expensive ones to
build wide, are exactly the ones that could in principle be narrow.

``run_endtoend.py`` measures that and it holds -- in isolation. It is still the
wrong thing to build. Narrowing the word means the pass-through phase has to
re-round a sample that already sits on a finer grid, at every stage where the
width steps down, and the measurement on the whole chain says the tapered
schedule ends up 10 dB noisier than a flat word of the same starting width for
0.8 percent less delay-line storage. Per-stage minima are real; composing them
is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import chain, halfband, spectra

# float64 carries a 53-bit mantissa, so a value of magnitude < 4 stays an exact
# multiple of 2**-50. Keep the sweep clear of that by a couple of bits.
MAX_FRAC_BITS = 48


ROUNDING = "half_even"          # see "Which way ties go" above


def q_round(x: np.ndarray | float, frac_bits: int | None,
            rounding: str | None = None) -> np.ndarray:
    """Round to a signed fixed-point grid of ``frac_bits`` fractional bits.

    ``None`` frac_bits means no quantization, which is the infinite-precision
    reference every measurement here is taken against. ``rounding`` is
    ``"half_even"`` (unbiased, the default) or ``"half_up"`` (one adder, and
    biased by a quarter of an LSB per rounding).
    """
    a = np.asarray(x, dtype=np.float64)
    if frac_bits is None:
        return a
    if frac_bits > MAX_FRAC_BITS:
        raise ValueError(f"{frac_bits} fractional bits exceeds float64 headroom")
    mode = ROUNDING if rounding is None else rounding
    s = 2.0 ** frac_bits
    if mode == "half_even":
        return np.round(a * s) / s
    if mode == "half_up":
        return np.floor(a * s + 0.5) / s
    raise ValueError(f"unknown rounding {mode!r}")


def int_bits_for(peak: float) -> int:
    """Bits above the binary point, sign included, that hold ``peak``."""
    if peak <= 0.0:
        return 1
    return int(np.floor(np.log2(peak))) + 2


@dataclass
class StageStats:
    """What one stage measured while it ran. Everything here is a width input."""

    index: int
    f_out: float
    n_products: int
    l1_gain: float          # sum |2h| over the filtered phase: accumulator bound
    peak_pre: float         # largest symmetric pre-add seen
    peak_acc: float         # largest accumulator value seen
    peak_out: float         # largest output sample seen
    sig_frac: int | None
    acc_frac: int | None
    coeff_bits: int | None
    offset: float = 0.0     # DC the rounding rule left behind, filled in by
                            # rounding_noise(); see its docstring

    @property
    def acc_int_bits(self) -> int:
        return int_bits_for(self.peak_acc)

    @property
    def sig_int_bits(self) -> int:
        return int_bits_for(self.peak_out)

    @property
    def acc_width(self) -> int | None:
        return None if self.acc_frac is None else self.acc_int_bits + self.acc_frac

    @property
    def sig_width(self) -> int | None:
        return None if self.sig_frac is None else self.sig_int_bits + self.sig_frac


def _pick(spec: int | dict | None, index: int) -> int | None:
    """A width spec is one number for the whole chain or a per-stage dict."""
    if isinstance(spec, dict):
        return spec.get(index)
    return spec


def stage_taps(hb: halfband.HalfBand, coeff_bits: int | None) -> np.ndarray:
    """Interpolation taps at gain 2, so the centre tap is exactly 1.0."""
    taps = hb.taps if coeff_bits is None else hb.quantized(coeff_bits)[0]
    return 2.0 * np.asarray(taps, dtype=np.float64)


def interpolate_stage(x: np.ndarray, hb: halfband.HalfBand, *,
                      coeff_bits: int | None = None,
                      sig_frac: int | None = None,
                      acc_frac: int | None = None,
                      index: int = 0,
                      f_out: float = 0.0,
                      rounding: str | None = None,
                      ) -> tuple[np.ndarray, StageStats]:
    """One half-band stage, upsampling by two, at the stated widths.

    Bit-identical to ``upfirdn(2*h, x, up=2)`` when every width is ``None``;
    :func:`self_check` asserts that.
    """
    x = np.asarray(x, dtype=np.float64)
    taps = stage_taps(hb, coeff_bits)
    n = len(x)
    N = len(taps)
    k = (N - 3) // 4
    g = taps[0::2]                       # even-index taps, length L = 2k+2
    L = len(g)
    half = L // 2                        # k+1 folded products
    out_len = 2 * n + N - 2
    m_out = n + L - 1                    # filtered-phase output samples

    # Folded filtered phase. Every term lands on the accumulator grid, so the
    # running sum stays on it exactly and only the products need rounding.
    acc = np.zeros(m_out, dtype=np.float64)
    lo = np.zeros(m_out, dtype=np.float64)
    hi = np.zeros(m_out, dtype=np.float64)
    peak_pre = 0.0
    peak_acc = 0.0
    for j in range(half):
        lo[:] = 0.0
        hi[:] = 0.0
        lo[j:j + n] = x
        hi[L - 1 - j:L - 1 - j + n] = x
        pre = lo + hi                    # exact: one bit wider than the signal
        peak_pre = max(peak_pre, float(np.abs(pre).max()))
        acc += q_round(g[j] * pre, acc_frac, rounding)
        peak_acc = max(peak_acc, float(np.abs(acc).max()))

    y = np.zeros(out_len, dtype=np.float64)
    y[0::2] = q_round(acc, sig_frac, rounding)
    # Pass-through phase: the centre tap is 1.0, so this is a delay by k.
    through = np.zeros(out_len - m_out, dtype=np.float64)
    through[k:k + n] = x
    y[1::2] = q_round(through, sig_frac, rounding)

    stats = StageStats(
        index=index, f_out=f_out, n_products=half,
        l1_gain=float(np.abs(g).sum()),
        peak_pre=peak_pre, peak_acc=peak_acc,
        peak_out=float(np.abs(y).max()),
        sig_frac=sig_frac, acc_frac=acc_frac, coeff_bits=coeff_bits,
    )
    return y, stats


def interpolate(cascade: halfband.Cascade, x: np.ndarray, mode: chain.Mode, *,
                coeff_bits: int | dict | None = None,
                sig_frac: int | dict | None = None,
                acc_frac: int | dict | None = None,
                rounding: str | None = None,
                ) -> tuple[np.ndarray, list[StageStats]]:
    """The whole cascade at fixed widths. Same contract as ``Cascade.interpolate``.

    Each width argument is either one value applied to every stage, a dict
    keyed by canonical stage index, or ``None`` for exact arithmetic. That is
    what lets one stage be quantized while the rest stay exact, which is the
    only way to see a single stage's own contribution.
    """
    y = np.asarray(x, dtype=np.float64)
    stats: list[StageStats] = []
    for st in cascade.for_mode(mode):
        y, s = interpolate_stage(
            y, st.hb,
            coeff_bits=_pick(coeff_bits, st.index),
            sig_frac=_pick(sig_frac, st.index),
            acc_frac=_pick(acc_frac, st.index),
            index=st.index, f_out=st.f_out, rounding=rounding,
        )
        stats.append(s)
    return y, stats


def full_precision_acc(hb: halfband.HalfBand, coeff_bits: int,
                       sig_frac: int) -> int:
    """Accumulator fractional bits at which no product is ever rounded."""
    return coeff_bits - 1 + sig_frac


# ---------------------------------------------------------------------------
# Measuring what a width costs
# ---------------------------------------------------------------------------

def band_power_dbfs(x: np.ndarray, fs: float,
                    band: tuple[float, float] = (chain.AUDIO_LO, chain.AUDIO_HI)
                    ) -> float:
    """In-band power of a record, in dBFS against a full-scale sine."""
    p = spectra.power_spectrum(np.asarray(x, dtype=np.float64))
    f = spectra.bin_freqs(len(x), fs)
    sel = (f >= band[0]) & (f <= band[1])
    return float(spectra.dbfs(float(p[sel].sum())))


def rounding_noise(cascade: halfband.Cascade, mode: chain.Mode,
                   pcm: np.ndarray, *, n_out: int,
                   coeff_bits: int | dict | None = None,
                   sig_frac: int | dict | None = None,
                   acc_frac: int | dict | None = None,
                   band: tuple[float, float] = (chain.AUDIO_LO, chain.AUDIO_HI),
                   rounding: str | None = None,
                   ) -> tuple[float, list[StageStats]]:
    """In-band noise a set of widths adds, in dBFS, measured by difference.

    The same record is run twice, once at the stated widths and once with the
    signal and accumulator exact, and the *difference* of the two outputs is
    measured. The difference carries no signal at all, so there is no lobe to
    excise and no near-equal spectra to subtract: a floor 80 dB below the
    signal is read as directly as one 10 dB below it. Coefficient quantization
    is applied to both runs, so what comes back is the datapath's contribution
    and nothing else.

    Quantizing one stage and leaving the rest exact is how a single stage's own
    contribution is isolated, which is what per-stage sizing needs.

    The mean of the difference is removed before the band is integrated, and
    returned separately. Round-half-up is biased: a value already sitting on a
    finer grid ties exactly half the time and every tie goes up, so each
    rounding contributes about a quarter of an LSB of offset and nine stages of
    them add. Measured on the recommended widths that offset is -143.1 dBFS
    against a rounding noise of -159.5 dBFS, so leaving it in reports the
    chain as 18 dB worse than it is. It is a static offset at the output, not
    audio-band noise -- the same distinction the element mismatch offset needs
    -- but unlike that one it is avoidable, by rounding ties to even.
    """
    settle = cascade.settle_samples(mode)
    ref, _ = interpolate(cascade, pcm, mode, coeff_bits=coeff_bits)
    got, stats = interpolate(cascade, pcm, mode, coeff_bits=coeff_bits,
                             sig_frac=sig_frac, acc_frac=acc_frac,
                             rounding=rounding)
    e = got[settle:settle + n_out] - ref[settle:settle + n_out]
    if len(e) < n_out:
        raise RuntimeError(f"only {len(e)} samples clear of the transient")
    offset = float(e.mean())
    noise = band_power_dbfs(e - offset, mode.element_clock, band)
    for st in stats:
        st.offset = offset
    return noise, stats


def predicted_noise_dbfs(frac_bits: int, f_out: float, n_roundings: int = 1,
                         band: tuple[float, float] = (chain.AUDIO_LO,
                                                      chain.AUDIO_HI)) -> float:
    """Where white rounding noise of ``frac_bits`` at rate ``f_out`` lands in band.

    ``q**2/12`` spread over ``f_out/2``, times the band's share of it. Only a
    check on the measurement: real rounding of a tone is not white, and the
    measurement is what gets reported.
    """
    q = 2.0 ** -frac_bits
    density = (q * q / 12.0) / (f_out / 2.0)
    return float(spectra.dbfs(n_roundings * density * (band[1] - band[0])))


def self_check(family: str = "48k") -> None:
    """Assert the fixed-point stage is the same filter as the float one."""
    from scipy.signal import upfirdn

    c = halfband.build(family)
    rng = np.random.default_rng(3)
    x = rng.standard_normal(200) * 0.5
    for st in c.distinct():
        ref = upfirdn(2.0 * st.hb.taps, x, up=2, down=1)
        got, _ = interpolate_stage(x, st.hb)
        assert got.shape == ref.shape, (st.index, got.shape, ref.shape)
        err = float(np.abs(got - ref).max())
        assert err < 1e-12, (st.index, err)
    m = chain.modes(family)[0]
    ref = c.interpolate(x, m)
    got, _ = interpolate(c, x, m)
    assert got.shape == ref.shape
    assert float(np.abs(got - ref).max()) < 1e-12
    # Quantized coefficients must agree with the float path's own quantizer.
    ref = c.interpolate(x, m, coeff_bits=18)
    got, _ = interpolate(c, x, m, coeff_bits=18)
    assert float(np.abs(got - ref).max()) < 1e-12


if __name__ == "__main__":
    self_check()
    c = halfband.build("48k")
    print("stage  f_out MHz  products  L1 gain  acc int bits (peak input 1.0)")
    for st in c.stages:
        g = stage_taps(st.hb, None)[0::2]
        l1 = float(np.abs(g).sum())
        print(f"{st.index:>5}  {st.f_out/1e6:>9.3f}  {len(g)//2:>8}  "
              f"{l1:>7.4f}  {int_bits_for(l1):>3}")

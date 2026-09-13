"""The whole chain, from 24-bit PCM to the element sum.

Everything else in this package measures one block against its own ideal
input. This module connects them:

    24-bit PCM at Fs -> half-band cascade -> modulator -> DWA rotation
      -> differential elements -> weighted sum -> spectrum

Two things only become visible here.

**The modulator stops seeing a clean tone.** Its order and its maximum stable
amplitude were characterised against a sine generated directly at the element
clock. What it actually receives is the cascade's output: a tone plus the
cascade's passband ripple, its residual images, and -- at 96 and 192 kHz --
whatever the source put between 20 kHz and the passband edge. Interpolation
also reconstructs the waveform *between* the samples, so a record whose samples
all sit at full scale can hand the modulator a peak well above full scale.
:func:`max_stable_pcm` measures that in the units a host controls, which is the
level of the PCM, not the level at the quantizer input.

**The loop wanders at very low frequency, and sometimes that wander lands in
band.** In 1 run of 36 across the six rates the in-band figure came back 18 dB
low, with every bit of the excess confined to the 20-100 Hz bins. A
perturbation of 2**-40 at the modulator input switches it on or off, while
1e-18, which float64 discards, does not -- so it is a real property of the
loop, not float noise. ``mod_dither_lsb`` adds TPDF at the modulator input and
:func:`modulator.dither_sequence` adds it at the quantizer, inside the loop;
measured, **neither removes it**, they only move which run trips. It is
reported rather than fixed. See README.md.

**The source is 24 bits.** The modulator's own noise floor at order 3 is far
below the floor of the PCM feeding it, so the end-to-end number is not the
modulator number. Quantizing to 24 bits without dither leaves the error
correlated with the signal and it appears as harmonics; TPDF dither at one LSB
RMS decorrelates it at the cost of 4.8 dB of floor. Both are measured, because
the chain has no say in which one the host sends.

Measurement conventions are :mod:`spectra`'s. Two traps are handled here rather
than left to the caller: the record at the element clock must be 2**20 or
longer for the audio band to contain enough bins to call noise, and the element
sum's mean must be removed, because element mismatch produces a static offset
that would otherwise land in the lowest bins of a band starting at 20 Hz and
dominate the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import chain, datapath, dwa, halfband, modulator, spectra

BAND = (chain.AUDIO_LO, chain.AUDIO_HI)
PCM_FRAC = chain.PCM_BITS - 1          # 24-bit signed fraction: 23 below the point


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def coherent_tone_freq(mode: chain.Mode, n_out: int,
                       f_target: float) -> tuple[int, float]:
    """Tone frequency that is coherent over an ``n_out`` record at the element clock.

    The measurement window sits at the element clock, so that is where
    coherence has to hold. An odd bin there is also an integer number of cycles
    in the ``n_out / ratio`` input samples that produced it, so the PCM record
    is coherent too and nothing has to be windowed twice.
    """
    return spectra.coherent_bin(n_out, mode.element_clock, f_target)


def quantize_pcm(x: np.ndarray, bits: int = chain.PCM_BITS,
                 dither: str = "tpdf", seed: int = 11) -> np.ndarray:
    """Round to a signed ``bits``-bit fraction, optionally TPDF dithered.

    TPDF is two uniform draws of half an LSB each, which is the standard
    choice: it removes both the correlation of the error with the signal and
    the modulation of the error's variance, at a floor 4.8 dB above the
    undithered value.
    """
    scale = float(1 << (bits - 1))
    a = np.asarray(x, dtype=np.float64) * scale
    if dither == "tpdf":
        rng = np.random.default_rng(seed)
        a = a + rng.random(a.shape) + rng.random(a.shape) - 1.0
    elif dither not in (None, "none", ""):
        raise ValueError(f"unknown dither {dither!r}")
    return np.floor(a + 0.5) / scale


def source_tone(n: int, fs: float, f: float, amp_dbfs: float,
                phase: float = 0.0) -> np.ndarray:
    amp = 10.0 ** (amp_dbfs / 20.0)
    return amp * np.sin(2.0 * np.pi * f * np.arange(n) / fs + phase)


def source_intersample(n: int, amp_dbfs: float) -> np.ndarray:
    """A tone at Fs/4 sampled at 45 degrees: every sample equal, peak 3.01 dB higher.

    This is the standard inter-sample overload probe. The PCM never exceeds the
    stated level, and a reconstruction filter -- which is what the cascade is --
    puts a peak of ``sqrt(2)`` times it between the samples. A modulator sized
    against sample values alone meets it unprepared, and heavily limited
    material contains it routinely.
    """
    amp = 10.0 ** (amp_dbfs / 20.0)
    return amp * np.sqrt(2.0) * np.sin(2.0 * np.pi * np.arange(n) / 4.0
                                       + np.pi / 4.0)


def fade(x: np.ndarray, n: int = 256) -> np.ndarray:
    """Raised-cosine fade at both ends of a record.

    Only for peak measurements. A record that switches on at a non-zero sample
    is a step, and the cascade rings on it: an un-faded 0 dBFS sine measures a
    peak of 1.118 through the chain when the true reconstructed peak is 1.000,
    and the inter-sample probe measures 1.429 when its true peak is sqrt(2).
    Fading removes the record's own edge and leaves the signal's real peak.
    """
    y = np.array(x, dtype=np.float64, copy=True)
    w = 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)
    y[:n] *= w
    y[-n:] *= w[::-1]
    return y


def source_multitone(n: int, fs: float, freqs, amp_dbfs: float) -> np.ndarray:
    """Equal-amplitude tones summed in phase, total level set to ``amp_dbfs``."""
    t = np.arange(n) / fs
    x = np.zeros(n, dtype=np.float64)
    for f in freqs:
        x += np.sin(2.0 * np.pi * f * t)
    x *= 10.0 ** (amp_dbfs / 20.0) / np.abs(x).max()
    return x


# ---------------------------------------------------------------------------
# The path
# ---------------------------------------------------------------------------

def input_length(cascade: halfband.Cascade, mode: chain.Mode, n_out: int) -> int:
    """PCM samples needed for ``n_out`` element-clock samples clear of transients."""
    settle = cascade.settle_samples(mode)
    return int(np.ceil((n_out + settle) / mode.ratio)) + 8


@dataclass
class Result:
    mode: chain.Mode
    order: int
    f_sig: float
    amp_dbfs: float
    sigma: float
    rotate: bool
    m: spectra.Measurement                 # element sum
    m_mod_in: spectra.Measurement | None    # cascade output, before the modulator
    mod_peak: float                        # peak |cascade output|
    mod_peak_dbfs: float
    clipped: int                           # quantizer saturations
    state_peak: np.ndarray                 # max |integrator| per stage
    stable: bool
    stage_stats: list[datapath.StageStats] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.mode.name:>10s}  SNR {self.m.snr_db:7.2f}  "
                f"SNDR {self.m.sndr_db:7.2f}  THD {self.m.thd_db:8.2f}  "
                f"peak {self.mod_peak_dbfs:+6.2f} dBFS  clip {self.clipped}")


def run(cascade: halfband.Cascade, ntf: modulator.NTF, mode: chain.Mode, *,
        pcm: np.ndarray | None = None,
        n_out: int = 1 << 20,
        f_target: float = 1000.0,
        amp_dbfs: float = -3.0,
        bits: int | None = chain.PCM_BITS,
        dither: str = "tpdf",
        coeff_bits: int | dict | None = None,
        sig_frac: int | dict | None = None,
        acc_frac: int | dict | None = None,
        rounding: str | None = None,
        mod_dither_lsb: float = 0.0,
        mod_dither_frac: int = 26,
        sigma: float = 0.0,
        rotate: bool = True,
        seed: int = 7,
        band: tuple[float, float] = BAND,
        measure_mod_in: bool = False,
        keep_psd: bool = False,
        n_harmonics: int = 10) -> Result:
    """One pass of the whole chain, measured at the element sum.

    ``pcm`` overrides the default coherent tone; it is taken as already being
    at the sample rate and already quantized. ``bits=None`` skips the source
    quantizer, which is how a datapath measurement is made without the source
    floor sitting on top of it.
    """
    n_in = input_length(cascade, mode, n_out)
    _, f_sig = coherent_tone_freq(mode, n_out, f_target)
    if pcm is None:
        pcm = source_tone(n_in, mode.fs, f_sig, amp_dbfs)
        if bits is not None:
            pcm = quantize_pcm(pcm, bits, dither, seed=seed + 4)
    pcm = np.asarray(pcm, dtype=np.float64)

    y, stats = datapath.interpolate(cascade, pcm, mode, coeff_bits=coeff_bits,
                                    sig_frac=sig_frac, acc_frac=acc_frac,
                                    rounding=rounding)
    settle = cascade.settle_samples(mode)
    if len(y) < settle + n_out:
        raise RuntimeError(f"cascade produced {len(y)} samples, need "
                           f"{settle + n_out}")
    u = y[settle:settle + n_out]
    if mod_dither_lsb:
        # TPDF, scaled in LSBs of the signal word. Breaks exact quantizer ties.
        rng = np.random.default_rng(seed + 31)
        lsb = 2.0 ** -mod_dither_frac
        u = u + mod_dither_lsb * lsb * (rng.random(n_out) + rng.random(n_out) - 1.0)
    peak = float(np.abs(u).max())

    fs = mode.element_clock
    m_in = (spectra.Measurement.of(u, fs, f_sig, band, n_harmonics=n_harmonics,
                                   keep_psd=keep_psd)
            if measure_mod_in else None)

    run_ = modulator.simulate(ntf, u, fs, f_sig=f_sig)
    codes = np.clip(np.asarray(run_.codes, dtype=np.int64), 0, chain.N_ELEMENTS)
    pos, neg = dwa.differential(codes, rotate=rotate)
    wp, wn = (None, None) if sigma == 0.0 else dwa.mismatch(sigma, seed=seed)
    x = dwa.normalise(dwa.analog(pos, neg, wp, wn))
    x = x - x.mean()                    # the mismatch offset is not audio-band noise
    m = spectra.Measurement.of(x, fs, f_sig, band, n_harmonics=n_harmonics,
                               keep_psd=keep_psd)
    return Result(mode=mode, order=ntf.order, f_sig=f_sig, amp_dbfs=amp_dbfs,
                  sigma=sigma, rotate=rotate, m=m, m_mod_in=m_in,
                  mod_peak=peak, mod_peak_dbfs=float(20.0 * np.log10(max(peak, 1e-30))),
                  clipped=run_.clipped, state_peak=run_.state_peak,
                  stable=run_.stable, stage_stats=stats)


# ---------------------------------------------------------------------------
# Stability against filtered content
# ---------------------------------------------------------------------------

def interpolated(cascade: halfband.Cascade, mode: chain.Mode,
                 pcm: np.ndarray, n_out: int,
                 coeff_bits: int | dict | None = None) -> np.ndarray:
    """Cascade output, transients discarded, ready for the modulator."""
    y, _ = datapath.interpolate(cascade, pcm, mode, coeff_bits=coeff_bits)
    settle = cascade.settle_samples(mode)
    return y[settle:settle + n_out]


def max_stable_pcm(cascade: halfband.Cascade, ntf: modulator.NTF,
                   mode: chain.Mode, make_pcm, *,
                   n_out: int = 1 << 18,
                   lo: float = 0.05, hi: float = 1.0, tol: float = 0.005,
                   state_cap: float = 50.0) -> dict:
    """Largest PCM amplitude whose interpolated form keeps the loop bounded.

    Same bisection and the same bound as
    :func:`modulator.max_stable_amplitude` -- no integrator beyond
    ``state_cap`` LSBs -- so the two numbers are directly comparable. What
    differs is the input: a PCM record put through the cascade, not a sine
    generated at the element clock. ``make_pcm(n, amp)`` builds the record.

    Returns the PCM amplitude, the level in dBFS, and the peak the cascade
    actually presented to the quantizer at that amplitude, which is the number
    that explains any difference.
    """
    limit = state_cap * modulator.LSB
    n_in = input_length(cascade, mode, n_out)
    fs = mode.element_clock
    cache: dict[float, float] = {}

    def peak_at(amp: float) -> tuple[bool, float]:
        u = interpolated(cascade, mode, make_pcm(n_in, amp), n_out)
        pk = float(np.abs(u).max())
        r = modulator.simulate(ntf, u, fs, state_limit=limit)
        return (r.stable and float(r.state_peak.max()) <= limit), pk

    ok_lo, pk = peak_at(lo)
    cache[lo] = pk
    if not ok_lo:
        return {"amp": 0.0, "amp_dbfs": float("-inf"), "peak": pk,
                "peak_dbfs": float("-inf")}
    ok_hi, pk_hi = peak_at(hi)
    cache[hi] = pk_hi
    if ok_hi:
        return {"amp": hi, "amp_dbfs": 20.0 * np.log10(hi), "peak": pk_hi,
                "peak_dbfs": float(20.0 * np.log10(pk_hi))}
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        ok, pk = peak_at(mid)
        cache[mid] = pk
        if ok:
            lo = mid
        else:
            hi = mid
    return {"amp": lo, "amp_dbfs": float(20.0 * np.log10(lo)),
            "peak": cache[lo],
            "peak_dbfs": float(20.0 * np.log10(max(cache[lo], 1e-30)))}


def tone_maker(mode: chain.Mode, f: float, bits: int | None = chain.PCM_BITS,
               dither: str = "tpdf"):
    def make(n: int, amp: float) -> np.ndarray:
        x = source_tone(n, mode.fs, f, 20.0 * np.log10(max(amp, 1e-12)))
        return x if bits is None else quantize_pcm(x, bits, dither)
    return make


def intersample_maker(bits: int | None = chain.PCM_BITS, dither: str = "tpdf"):
    def make(n: int, amp: float) -> np.ndarray:
        x = source_intersample(n, 20.0 * np.log10(max(amp, 1e-12)))
        return x if bits is None else quantize_pcm(x, bits, dither)
    return make


__all__ = ["BAND", "PCM_FRAC", "Result", "run", "coherent_tone_freq",
           "quantize_pcm", "source_tone", "source_intersample",
           "source_multitone", "fade", "input_length", "interpolated",
           "max_stable_pcm", "tone_maker", "intersample_maker"]

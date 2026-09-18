"""Test material beyond a single tone, and a way to bring in real audio.

Every figure elsewhere in this model comes from one sine or the inter-sample
probe. That is the right instrument for measuring a noise floor and the wrong
one for reaching the states a tone never visits: near idle, at digital
silence, and at the bottom of the band.

This module was written to hunt a low-frequency limit cycle. There is no
limit cycle -- that was an analysis-window artifact, and ``notes-idle.md``
records how it was found. The material is still the right material, because
the low-frequency behaviour of the loop has never actually been characterised,
only mis-measured, so what is wanted here is a measurement rather than a hunt.

Two things follow. The material deliberately includes what a tone never does:
decays into silence, digital silence itself, content only a few LSBs above
nothing, and sustained low frequencies in the 20 to 100 Hz band that a single
in-band figure cannot resolve. And the measurement is windowed, because one
number over a long record averages away anything that varies within it.

``read_wav`` exists so real audio can be substituted for any of it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import chain


def _rng(seed):
    return np.random.default_rng(seed)


def fade_to_silence(n: int, fs: float, f: float = 220.0,
                    start_dbfs: float = -3.0) -> np.ndarray:
    """A tone decaying into digital silence, then silence.

    The classic way to provoke an idle-channel fault: the loop is walked all
    the way down to nothing rather than parked at one level.
    """
    t = np.arange(n) / fs
    env = np.concatenate([
        np.logspace(0, -5, int(n * 0.7)),
        np.zeros(n - int(n * 0.7)),
    ])
    return 10 ** (start_dbfs / 20) * env * np.sin(2 * np.pi * f * t)


def digital_silence(n: int, fs: float) -> np.ndarray:
    """Exactly zero. The loop still has to behave."""
    return np.zeros(n)


def near_silence(n: int, fs: float, dbfs: float = -100.0,
                 seed: int = 5) -> np.ndarray:
    """Noise a few LSBs above nothing, where idle tones are audible."""
    return 10 ** (dbfs / 20) * _rng(seed).standard_normal(n) * 0.3


def dc_offset(n: int, fs: float, dbfs: float = -60.0) -> np.ndarray:
    """A small constant, to check the loop does nothing audible with one.

    A static input offset is what round-half-up leaves at the modulator input,
    and the loop was once thought to turn it into idle tones. It does not: a
    constant from -160 to -60 dBFS produces no in-band tone (notes-idle.md).
    """
    return np.full(n, 10 ** (dbfs / 20))


def sustained_bass(n: int, fs: float, f: float = 41.2,
                   dbfs: float = -6.0) -> np.ndarray:
    """Low E of a bass guitar, with harmonics, held.

    Sits in the band where a tripped run puts its excess, so it tests whether
    real low-frequency content and the fault are separable.
    """
    t = np.arange(n) / fs
    x = np.zeros(n)
    for k, a in enumerate((1.0, 0.5, 0.32, 0.18, 0.1), start=1):
        x += a * np.sin(2 * np.pi * f * k * t + k * 0.7)
    return 10 ** (dbfs / 20) * x / np.abs(x).max()


def percussive(n: int, fs: float, dbfs: float = -3.0,
               seed: int = 9) -> np.ndarray:
    """High crest factor: sharp transients over near-silence.

    Music peaks far above its average and a sine does not, so this is what
    exercises the headroom the maximum stable amplitude figure describes.
    """
    r = _rng(seed)
    x = np.zeros(n)
    pos = 0
    while pos < n:
        length = min(int(fs * r.uniform(0.05, 0.25)), n - pos)
        env = np.exp(-np.arange(length) / (fs * r.uniform(0.004, 0.03)))
        tone = r.standard_normal(length) * 0.3 + np.sin(
            2 * np.pi * r.uniform(60, 4000) * np.arange(length) / fs)
        x[pos:pos + length] += env * tone
        pos += length + int(fs * r.uniform(0.0, 0.2))
    return 10 ** (dbfs / 20) * x / max(np.abs(x).max(), 1e-9)


def programme(n: int, fs: float, dbfs: float = -6.0,
              seed: int = 3) -> np.ndarray:
    """A crude stand-in for programme material: bass, mids, air, dynamics."""
    r = _rng(seed)
    t = np.arange(n) / fs
    x = np.zeros(n)
    for f, a in ((49.0, 1.0), (98.0, .6), (147.0, .35), (392.0, .3),
                 (587.0, .2), (1174.0, .12), (3520.0, .06), (8000.0, .03)):
        x += a * np.sin(2 * np.pi * f * t + r.uniform(0, 6.28))
    # slow level changes, so windows differ from one another
    env = 0.55 + 0.45 * np.sin(2 * np.pi * 0.7 * t + 1.1)
    x = x * env + 0.02 * r.standard_normal(n)
    return 10 ** (dbfs / 20) * x / max(np.abs(x).max(), 1e-9)


CATALOGUE = {
    "fade to silence": fade_to_silence,
    "digital silence": digital_silence,
    "near silence -100 dBFS": near_silence,
    "small DC offset": dc_offset,
    "sustained 41 Hz bass": sustained_bass,
    "percussive, high crest": percussive,
    "programme-like": programme,
}


def read_wav(path, fs_expected: float | None = None) -> tuple[np.ndarray, float]:
    """Load a WAV as mono float in -1..1, for substituting real audio.

    Returns (samples, rate). No resampling: the chain expects material already
    at one of its supported rates, and resampling here would put a filter of
    unknown quality in front of the thing being measured.
    """
    from scipy.io import wavfile
    rate, data = wavfile.read(Path(path))
    x = np.asarray(data, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if np.issubdtype(np.asarray(data).dtype, np.integer):
        x = x / float(2 ** (8 * np.asarray(data).dtype.itemsize - 1))
    if fs_expected is not None and abs(rate - fs_expected) > 1:
        raise ValueError(
            f"{path} is {rate} Hz; the chain was asked for {fs_expected:.0f}. "
            "Supply material at a supported rate rather than resampling here.")
    return x, float(rate)


def band_shape(err: np.ndarray, fs: float) -> dict:
    """Where in the audio band an error sits, not just how big it is.

    A single in-band number cannot distinguish excess confined to the bottom
    of the band from an evenly raised floor. This reports the split that can,
    which is what showed the difference between genuine bass and a
    low-frequency anomaly, and what would show either against a flat floor.
    """
    from . import spectra
    w = spectra.analysis_window(len(err))
    p = spectra.power_spectrum(err, w)
    f = spectra.bin_freqs(len(err), fs)

    def band(lo, hi):
        sel = (f >= lo) & (f < hi)
        return float(p[sel].sum())

    low = band(chain.AUDIO_LO, 100.0)
    mid = band(100.0, 2000.0)
    high = band(2000.0, chain.AUDIO_HI)
    total = low + mid + high
    to_db = lambda v: 10 * np.log10(max(v, 1e-300))
    return {
        "total_db": to_db(total),
        "low_db": to_db(low), "mid_db": to_db(mid), "high_db": to_db(high),
        "low_share": low / total if total > 0 else 0.0,
    }

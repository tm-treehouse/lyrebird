"""Spectrum estimation and audio-band measurement.

Every number this model reports about a modulator or an element sum comes from
here, so the conventions matter:

* 0 dBFS is a sine of amplitude 1.0 into a converter whose peak output is
  +/-1.0, i.e. a mean-square of 0.5.
* Power is measured by Parseval on the windowed record, so summing
  :func:`power_spectrum` over any set of bins gives the mean-square of the
  signal in those bins directly.
* The analysis window is a Kaiser. Its sidelobe floor is measured by
  :func:`window_leakage_floor` and reported alongside the results, because a
  -150 dB noise floor cannot be read through a window that leaks at -120 dB.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Kaiser beta. Measured leakage floor is reported by window_leakage_floor();
# at beta = 26 it is far below the float64 noise of the FFT itself.
KAISER_BETA = 26.0


def analysis_window(n: int, beta: float = KAISER_BETA) -> np.ndarray:
    return np.kaiser(n, beta)


def main_lobe_bins(beta: float = KAISER_BETA) -> int:
    """Half-width of the Kaiser main lobe, in bins, rounded up with margin."""
    return int(np.ceil(np.sqrt(1.0 + (beta / np.pi) ** 2))) + 3


def power_spectrum(x: np.ndarray, window: np.ndarray | None = None) -> np.ndarray:
    """One-sided power-per-bin spectrum. ``result.sum()`` is mean-square of x."""
    n = len(x)
    w = analysis_window(n) if window is None else window
    xw = np.asarray(x, dtype=np.float64) * w
    p = np.abs(np.fft.rfft(xw)) ** 2
    p[1:] *= 2.0                     # fold the negative frequencies
    if n % 2 == 0:
        p[-1] /= 2.0                 # Nyquist bin is not paired
    p /= n * np.sum(w ** 2)
    return p


def bin_freqs(n: int, fs: float) -> np.ndarray:
    return np.fft.rfftfreq(n, d=1.0 / fs)


def dbfs(power: float | np.ndarray) -> np.ndarray:
    """Power (mean-square) to dBFS, where a full-scale sine is 0 dBFS."""
    return 10.0 * np.log10(np.maximum(np.asarray(power, dtype=np.float64), 1e-300) / 0.5)


def coherent_bin(n: int, fs: float, f_target: float) -> tuple[int, float]:
    """Pick the odd FFT bin nearest f_target and return (bin, exact freq).

    An odd bin index makes the tone incommensurate with every power-of-two
    subharmonic of the record length, which keeps modulator idle patterns from
    locking to the record and faking a clean floor.
    """
    k = int(round(f_target * n / fs))
    if k % 2 == 0:
        k += 1
    return k, k * fs / n


def window_leakage_floor(n: int, fs: float, f_sig: float,
                         band: tuple[float, float] = (20.0, 20_000.0),
                         beta: float = KAISER_BETA) -> float:
    """dBFS floor a pure full-scale tone leaves in ``band``. The measurement
    floor of every SNR number below."""
    k, f = coherent_bin(n, fs, f_sig)
    t = np.arange(n)
    x = np.sin(2.0 * np.pi * k * t / n)
    m = Measurement.of(x, fs, f, band=band, beta=beta)
    return m.noise_dbfs


@dataclass
class Measurement:
    fs: float
    f_sig: float
    band: tuple[float, float]
    signal_dbfs: float
    noise_dbfs: float               # in-band, signal and harmonics removed
    snr_db: float                   # signal / in-band noise
    sndr_db: float                  # signal / (in-band noise + harmonics)
    thd_db: float                   # total harmonic distortion, in band
    harmonics_dbfs: list[float] = field(default_factory=list)
    oob_dbfs: float = float("nan")  # band edge .. fs/2
    total_dbfs: float = float("nan")
    n_noise_bins: int = 0
    freqs: np.ndarray | None = None
    psd_dbfs: np.ndarray | None = None

    @classmethod
    def of(cls, x: np.ndarray, fs: float, f_sig: float,
           band: tuple[float, float] = (20.0, 20_000.0),
           n_harmonics: int = 20, beta: float = KAISER_BETA,
           keep_psd: bool = False) -> "Measurement":
        n = len(x)
        w = analysis_window(n, beta)
        p = power_spectrum(x, w)
        f = bin_freqs(n, fs)
        half = main_lobe_bins(beta)
        df = fs / n

        def lobe(freq: float) -> np.ndarray:
            c = int(round(freq / df))
            lo, hi = max(c - half, 0), min(c + half + 1, len(p))
            return np.arange(lo, hi)

        in_band = (f >= band[0]) & (f <= band[1])

        sig_idx = lobe(f_sig)
        sig_pow = float(p[sig_idx].sum())

        # Harmonics that land inside the measurement band. Above fs/2 they
        # alias, but this chain never decimates so they simply are not there.
        harm_pow = 0.0
        harm_levels: list[float] = []
        harm_idx: list[np.ndarray] = []
        for h in range(2, n_harmonics + 1):
            fh = f_sig * h
            if fh > band[1]:
                harm_levels.append(float("-inf"))
                continue
            idx = lobe(fh)
            hp = float(p[idx].sum())
            harm_pow += hp
            harm_idx.append(idx)
            harm_levels.append(float(dbfs(hp)))

        # Noise = in band, minus the signal lobe, minus the harmonic lobes.
        mask = in_band.copy()
        mask[sig_idx] = False
        for idx in harm_idx:
            mask[idx] = False
        # DC leakage is not a noise mechanism; it is an offset.
        mask[f < band[0]] = False
        n_kept = int(mask.sum())
        n_full = int(in_band.sum())
        noise_pow = float(p[mask].sum())
        if n_kept:
            noise_pow *= n_full / n_kept       # restore the excised bins

        oob = (f > band[1])
        oob_pow = float(p[oob].sum())

        snr = 10.0 * np.log10(sig_pow / noise_pow) if noise_pow > 0 else float("inf")
        nd = noise_pow + harm_pow
        sndr = 10.0 * np.log10(sig_pow / nd) if nd > 0 else float("inf")
        thd = 10.0 * np.log10(harm_pow / sig_pow) if harm_pow > 0 else float("-inf")

        return cls(
            fs=fs, f_sig=f_sig, band=band,
            signal_dbfs=float(dbfs(sig_pow)),
            noise_dbfs=float(dbfs(noise_pow)),
            snr_db=float(snr), sndr_db=float(sndr), thd_db=float(thd),
            harmonics_dbfs=harm_levels,
            oob_dbfs=float(dbfs(oob_pow)),
            total_dbfs=float(dbfs(p.sum())),
            n_noise_bins=n_kept,
            freqs=f if keep_psd else None,
            psd_dbfs=10.0 * np.log10(np.maximum(p, 1e-300) / 0.5) if keep_psd else None,
        )

    def summary(self) -> str:
        return (f"sig {self.signal_dbfs:8.2f} dBFS  noise {self.noise_dbfs:8.2f} dBFS  "
                f"SNR {self.snr_db:7.2f} dB  SNDR {self.sndr_db:7.2f} dB  "
                f"THD {self.thd_db:8.2f} dB  OOB {self.oob_dbfs:7.2f} dBFS")


def smooth_psd(f: np.ndarray, psd_db: np.ndarray, n_out: int = 1200,
               f_lo: float = 10.0) -> tuple[np.ndarray, np.ndarray]:
    """Log-spaced power-averaged decimation of a spectrum, for plotting.

    Averaging power (not dB) keeps the plotted curve an unbiased estimate of
    the noise density, which a max- or point-decimated plot is not.
    """
    f_hi = f[-1]
    edges = np.geomspace(max(f_lo, f[1]), f_hi, n_out + 1)
    p = 10.0 ** (psd_db / 10.0)
    idx = np.searchsorted(f, edges)
    fo, po = [], []
    for a, b in zip(idx[:-1], idx[1:]):
        if b <= a:
            continue
        fo.append(float(f[a:b].mean()))
        po.append(float(p[a:b].mean()))
    return np.asarray(fo), 10.0 * np.log10(np.maximum(np.asarray(po), 1e-300))

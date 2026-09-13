"""Multi-bit delta-sigma modulator, parameterised by order.

Quantizer is fixed by 0008: three bits, eight levels, thermometer coded,
differential, so the output alphabet is ``(2k-7)/7`` for k in 0..7 -- eight
levels spanning +/-1 with an LSB of 2/7. What is open is the order and the loop
topology.

Noise transfer function
-----------------------
All zeros at DC::

    NTF(z) = (1 - z^-1)^L / D(z^-1)

The poles come from a Butterworth high-pass whose corner is solved so that
``max |NTF| = H_inf``. scipy's ``butter`` in high-pass form already has
numerator ``g * (1 - z^-1)^L`` with ``g = b[0]``, and a Butterworth high-pass
peaks at exactly 1.0, so ``max|NTF| = 1/g`` and the solve is one-dimensional in
the corner frequency. This is the classical construction (Schreier's
``synthesizeNTF`` with unoptimised zeros).

Topology
--------
Cascade of integrators, feedback (CIFB), with the input fed forward to the
quantizer::

    x_1[n+1] = x_1[n]              + a_1 * (u[n] - v[n])
    x_i[n+1] = x_i[n] + x_{i-1}[n] + a_i * (u[n] - v[n])      i = 2..L
    y[n]     = u[n] + x_L[n]
    v[n]     = Q(y[n])

Two properties earn this arrangement rather than plain CIFB:

* The signal transfer function is exactly 1 -- unity gain, zero delay, no
  ripple of its own -- so the interpolation filter's response is the whole
  response of the chain.
* Every integrator is driven by ``u - v``, which is the loop error, not the
  signal. The states never carry the audio, so their swing is set by the
  quantization error and the word widths stay narrow. Measured below.

Coefficients fall out of a change of variable. With
``D(z) = z^L + d_{L-1} z^{L-1} + ... + d_0`` written in ``w = z - 1``, the
feedback coefficient ``a_i`` is the coefficient of ``w^(i-1)``. No matrix
inversion, and the result is exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq
from scipy.signal import butter, freqz, lfilter

from . import chain, spectra

N_LEVELS = chain.N_LEVELS            # 8
LSB = 2.0 / chain.N_ELEMENTS         # 2/7
LEVELS = np.array([(2 * k - chain.N_ELEMENTS) / chain.N_ELEMENTS
                   for k in range(N_LEVELS)])


def quantize_code(y: float) -> int:
    """Nearest of the eight levels, as a thermometer code 0..7.

    ``floor(3.5*y + 4)`` clipped is nearest-level with ties upward, and in
    hardware it is an add of a constant, a truncation and a clip.
    """
    k = int(np.floor(3.5 * y + 4.0))
    return 0 if k < 0 else (7 if k > 7 else k)


# ---------------------------------------------------------------------------
# NTF synthesis
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NTF:
    order: int
    h_inf: float                 # requested out-of-band gain
    h_inf_actual: float          # measured max |NTF|
    num: np.ndarray              # in z^-1, monic: (1 - z^-1)^L
    den: np.ndarray              # in z^-1, monic
    corner: float                # Butterworth corner used, fraction of Nyquist
    a: np.ndarray                # CIFB feedback coefficients a_1..a_L

    def response(self, f: np.ndarray, fs: float) -> np.ndarray:
        w = 2.0 * np.pi * np.asarray(f, dtype=np.float64) / fs
        _, h = freqz(self.num, self.den, worN=w)
        return np.abs(h)

    def predicted_snr_db(self, amp_dbfs: float, bandwidth: float, fs: float,
                         n_grid: int = 200001) -> float:
        """SQNR from the linearised model: white quantization error, shaped.

        Error power is ``LSB**2 / 12`` spread over ``fs/2``. Integrating the
        shaped density over the audio band gives a figure to check the
        simulation against; they agree to a few dB when the quantizer is not
        overloaded.
        """
        f = np.linspace(0.0, bandwidth, n_grid)
        mag2 = self.response(f, fs) ** 2
        e_density = (LSB ** 2 / 12.0) / (fs / 2.0)
        noise = float(np.trapezoid(mag2 * e_density, f))
        sig = 0.5 * 10.0 ** (amp_dbfs / 10.0)
        return float(10.0 * np.log10(sig / noise))


def _butter_gain(order: int, corner: float) -> float:
    b, _ = butter(order, corner, btype="high")
    return float(b[0])


def synthesize_ntf(order: int, h_inf: float = 2.0) -> NTF:
    """All-DC-zero NTF of the given order with ``max|NTF| = h_inf``."""
    if order < 1:
        raise ValueError("order must be >= 1")
    target = 1.0 / h_inf

    def err(corner: float) -> float:
        return _butter_gain(order, corner) - target

    lo, hi = 1e-9, 1.0 - 1e-9
    if err(lo) * err(hi) > 0:
        raise ValueError(f"H_inf = {h_inf} unreachable at order {order}")
    corner = brentq(err, lo, hi, xtol=1e-14, rtol=1e-14)
    b, a = butter(order, corner, btype="high")
    num = np.poly1d([1.0, -1.0]) ** order
    num = np.asarray(num.coeffs, dtype=np.float64)      # (1 - z^-1)^L in z^-1
    den = np.asarray(a, dtype=np.float64) / a[0]

    # measured peak of |NTF|
    w = np.linspace(0.0, np.pi, 1 << 16)
    _, h = freqz(num, den, worN=w)
    h_actual = float(np.abs(h).max())

    # CIFB coefficients: D(z) in powers of (z-1); den is monic in z^-1, so the
    # same coefficient list read as descending powers of z is D(z) monic.
    dz = den
    L = order
    wpoly = np.zeros(L + 1)
    for j, c in enumerate(dz):
        p = L - j                    # power of z
        # (w+1)^p
        binom = np.array([np.math.comb(p, t) if hasattr(np.math, "comb")
                          else 0 for t in range(p + 1)], dtype=np.float64) \
            if False else np.array([_comb(p, t) for t in range(p + 1)], dtype=np.float64)
        wpoly[: p + 1] += c * binom
    a_fb = wpoly[:L].copy()          # a_i = coeff of w^(i-1), i = 1..L
    return NTF(order=order, h_inf=h_inf, h_inf_actual=h_actual, num=num, den=den,
               corner=corner, a=a_fb)


def _comb(n: int, k: int) -> int:
    from math import comb
    return comb(n, k)


def cifb_ntf_check(ntf: NTF, n_grid: int = 4096) -> float:
    """Max dB error between the target NTF and the one the CIFB actually has.

    Guards the coefficient derivation: ``NTF = (z-1)^L / ((z-1)^L + sum a_i
    (z-1)^(i-1))``.
    """
    w = np.linspace(1e-6, np.pi, n_grid)
    z = np.exp(1j * w)
    zm = z - 1.0
    num = zm ** ntf.order
    den = num + sum(ntf.a[i] * zm ** i for i in range(ntf.order))
    got = np.abs(num / den)
    want = ntf.response(w / (2.0 * np.pi), 1.0)
    return float(np.max(np.abs(20.0 * np.log10(got / want))))


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@dataclass
class Run:
    codes: np.ndarray            # thermometer code 0..7, uint8
    out: np.ndarray              # (2k-7)/7, the ideal element sum
    state_peak: np.ndarray       # max |x_i|
    clipped: int                 # samples where the quantizer input was outside range
    stable: bool
    amp: float
    f_sig: float
    fs: float
    extra: dict = field(default_factory=dict)


def simulate(ntf: NTF, u: np.ndarray, fs: float, f_sig: float = 0.0,
             state_limit: float = 1e4,
             dither: np.ndarray | None = None) -> Run:
    """Run the CIFB-with-feedforward loop over the input record.

    Pure Python loop on purpose: the recursion is sequential and there is no
    vectorised form. About 1.1 s per 2**20 samples at order 5.

    ``dither`` is added at the quantizer input, inside the loop, so the
    feedback shapes it the way it shapes quantization error and it leaves the
    audio band. Dither added to ``u`` instead passes straight through, because
    the signal transfer function is exactly 1. See :func:`dither_sequence` and
    the limit-cycle measurement in ``run_endtoend.py``.
    """
    L = ntf.order
    a = [float(v) for v in ntf.a]
    n = len(u)
    codes = np.empty(n, dtype=np.uint8)
    x = [0.0] * L
    peak = [0.0] * L
    clipped = 0
    stable = True
    uu = np.asarray(u, dtype=np.float64)
    dd = None if dither is None else np.asarray(dither, dtype=np.float64)
    for i in range(n):
        ui = uu[i]
        y = ui + x[L - 1]
        if dd is not None:
            y += dd[i]
        k = int(np.floor(3.5 * y + 4.0))
        if k < 0:
            k = 0
            clipped += 1
        elif k > 7:
            k = 7
            clipped += 1
        codes[i] = k
        d = ui - (2 * k - 7) / 7.0
        for j in range(L - 1, 0, -1):
            x[j] += x[j - 1] + a[j] * d
            v = x[j] if x[j] >= 0.0 else -x[j]
            if v > peak[j]:
                peak[j] = v
        x[0] += a[0] * d
        v = x[0] if x[0] >= 0.0 else -x[0]
        if v > peak[0]:
            peak[0] = v
        if peak[L - 1] > state_limit:
            stable = False
            break
    out = (2.0 * codes.astype(np.float64) - 7.0) / 7.0
    return Run(codes=codes, out=out, state_peak=np.array(peak), clipped=clipped,
               stable=stable, amp=float(np.max(np.abs(uu))), f_sig=f_sig, fs=fs)


def dither_sequence(n: int, lsb_fraction: float = 0.5,
                    seed: int | None = None) -> np.ndarray:
    """RPDF dither for the quantizer input, scaled in quantizer LSBs.

    One LSB here is ``2/7``, the spacing of the eight output levels. The
    quantizer is multi-bit, so dither at a fraction of an LSB costs almost
    nothing in noise -- and what it does cost the loop shapes out of the audio
    band, because it is injected inside the feedback.
    """
    rng = np.random.default_rng(seed)
    return lsb_fraction * LSB * (rng.random(n) - 0.5)


def tone(n: int, fs: float, f_target: float, amp_dbfs: float) -> tuple[np.ndarray, float]:
    """Coherent sine at an odd FFT bin, amplitude set in dBFS."""
    k, f = spectra.coherent_bin(n, fs, f_target)
    amp = 10.0 ** (amp_dbfs / 20.0)
    return amp * np.sin(2.0 * np.pi * k * np.arange(n) / n), f


def max_stable_amplitude(ntf: NTF, fs: float, n: int = 1 << 15,
                         f_target: float = 1000.0,
                         lo: float = 0.05, hi: float = 1.0,
                         tol: float = 0.005,
                         state_cap: float = 50.0) -> float:
    """Largest sine amplitude, in fraction of full scale, that keeps the loop bounded.

    Bisection on a short record. "Bounded" means no integrator exceeds
    ``state_cap`` times the quantizer LSB, which is a far looser test than
    audible degradation but is the one that separates stable from not.
    """
    limit = state_cap * LSB

    def ok(amp: float) -> bool:
        u, f = tone(n, fs, f_target, 20.0 * np.log10(amp))
        r = simulate(ntf, u, fs, f, state_limit=limit)
        return r.stable and float(r.state_peak.max()) <= limit

    if not ok(lo):
        return 0.0
    if ok(hi):
        return hi
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo

"""Fixed-point sizing for the modulator's own arithmetic.

The interpolator's datapath is sized in ``datapath.py``. This does the same
for the loop itself: the integrator state words, the feedback coefficients,
and what truncating either costs.

Sizing the loop is not the same problem as sizing a filter. A filter's
rounding error passes through once; an integrator accumulates it and the
feedback carries it back round, so a state word that is one bit short does
not degrade gracefully. What makes it tractable here is the topology. With
the input fed forward the integrators are driven by the loop error rather
than the signal, so the states stay far below full scale, which is exactly
what buys back the bits a naive accumulator would need.

Rounding is ties-to-even throughout, matching the interpolator for the reason
given there: round-half-up leaves an offset the loop turns into low-frequency
tones.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import chain, spectra
from .modulator import NTF, Run


def rne(value: float, frac_bits: int) -> float:
    """Round to a fixed-point grid, ties to even."""
    scale = float(1 << frac_bits)
    return float(np.rint(value * scale)) / scale


@dataclass
class FixedRun:
    run: Run
    m: spectra.Measurement
    peak: list                  # peak |state| per integrator
    overflow: int               # samples where a state left its range
    coeff_frac: int
    state_frac: int
    state_int: int


def simulate_fixed(ntf: NTF, u: np.ndarray, fs: float, f_sig: float, *,
                   coeff_frac: int, state_frac, state_int: int,
                   band=(chain.AUDIO_LO, chain.AUDIO_HI),
                   n_harmonics: int = 10) -> FixedRun:
    """The CIFB loop with coefficients and states held on fixed-point grids.

    ``state_int`` is integer bits excluding sign, so a state must stay within
    plus or minus 2**state_int. Excursions are counted rather than clipped:
    clipping would hide the very thing the sweep is looking for.

    ``state_frac`` may be one width for all integrators or a per-integrator
    list. They do not all need the same: rounding injected at the last
    integrator reaches the quantizer directly, while rounding at the first
    passes through the rest of the loop first.
    """
    L = ntf.order
    a = [rne(float(v), coeff_frac) for v in ntf.a]
    if isinstance(state_frac, int):
        sfrac = [state_frac] * L
    else:
        sfrac = list(state_frac)
        if len(sfrac) != L:
            raise ValueError(f"state_frac needs {L} entries")
    lim = float(1 << state_int)
    n = len(u)
    codes = np.empty(n, dtype=np.uint8)
    out = np.empty(n, dtype=np.float64)
    x = [0.0] * L
    peak = [0.0] * L
    overflow = 0
    clipped = 0
    uu = np.asarray(u, dtype=np.float64)

    for i in range(n):
        ui = uu[i]
        y = ui + x[L - 1]
        k = int(np.floor(3.5 * y + 4.0))
        if k < 0:
            k = 0
            clipped += 1
        elif k > 7:
            k = 7
            clipped += 1
        codes[i] = k
        level = (2 * k - 7) / 7.0
        out[i] = level
        d = ui - level
        for j in range(L - 1, 0, -1):
            x[j] = rne(x[j] + x[j - 1] + a[j] * d, sfrac[j])
            v = abs(x[j])
            if v > peak[j]:
                peak[j] = v
            if v >= lim:
                overflow += 1
        x[0] = rne(x[0] + a[0] * d, sfrac[0])
        v = abs(x[0])
        if v > peak[0]:
            peak[0] = v
        if v >= lim:
            overflow += 1

    m = spectra.Measurement.of(out, fs, f_sig, band, n_harmonics=n_harmonics)
    run = Run(codes=codes, out=out, state_peak=peak, clipped=clipped,
              stable=overflow == 0, amp=0.0, f_sig=f_sig, fs=fs, extra={})
    return FixedRun(run=run, m=m, peak=peak, overflow=overflow,
                    coeff_frac=coeff_frac, state_frac=state_frac,
                    state_int=state_int)

"""Idle-channel behaviour: the low-frequency wander, and how to measure it.

The open item this module exists for is stated in README.md: one run in
thirty-six comes back 15 to 19 dB low with every bit of the excess in the
20 to 100 Hz bins, and neither input dither nor quantizer dither removes it.

Measuring that claim needs more care than measuring a noise floor, and the
care is the substance of this module rather than a preamble to it.

Why the 2**20 transform cannot answer a 20 Hz question
------------------------------------------------------
The analysis window is a Kaiser at beta = 26, chosen in :mod:`spectra` so its
sidelobes sit below the float64 floor. That choice costs main-lobe width: the
half-width is ``spectra.main_lobe_bins()`` = 12 bins. At the element clock a
2**20 transform has 23.4 Hz bins, so the main lobe is +/-281 Hz wide, and any
component at or near DC covers the whole 20 to 100 Hz band and a good part of
the 100 Hz to 2 kHz band with it.

A delta-sigma loop always leaves such a component. Its output is a sequence of
eight levels spaced 2/7 apart, so the mean of an N-sample record can only sit
on a grid of ``(2/7)/N``. Over 2**20 samples that grid step is 2.7e-7, which
is -128 dBFS: a single unbalanced sample per window is already a -128 dBFS
near-DC component. The band from 20 to 100 Hz cannot be told apart from it at
that record length.

:func:`min_transform` states the requirement, :func:`remove_dc` removes the
part of it that plain mean subtraction misses, and :func:`bands` reports the
sub-20 Hz energy alongside the in-band split so the two are never confused.

What a trial is
---------------
The fault is meant to live near idle, so the material is
:mod:`material`'s -- fades, digital silence, near silence, DC -- and the trial
has two parts. A **preamble** sets the loop's state and the rotation pointer
the way real music would, and is discarded. The **window** is the idle
material that follows, and is what gets measured. Varying the preamble varies
the state the loop is in when the signal goes quiet, which is the condition
the fault is supposed to depend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import chain, dwa, halfband, material, modulator, spectra

BAND = (chain.AUDIO_LO, chain.AUDIO_HI)
LOW = (chain.AUDIO_LO, 100.0)

# Settled by run_endtoend.py, carried here so the idle study runs against the
# chain that will actually be built.
COEFF_BITS = {1: 26, 2: 26, 3: 26, 4: 22, 5: 19, 6: 18, 7: 10, 8: 8, 9: 8}
SIG_FRAC = {s: 26 for s in range(1, 10)}
ACC_FRAC = {1: 31, 2: 31, 3: 31, 4: 30, 5: 30, 6: 29, 7: 29, 8: 29, 9: 29}

QLSB = modulator.LSB                      # 2/7, the spacing of the eight levels


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def min_transform(fs: float, f_lo: float = chain.AUDIO_LO) -> int:
    """Shortest transform whose DC main lobe stops below ``f_lo``.

    ``half_lobe * fs / n < f_lo``. Anything shorter reports near-DC energy as
    audio-band energy and cannot be argued with, because the two are genuinely
    the same bins. At the 48 kHz family's element clock that is 2**23.6, so
    2**24 is the shortest power of two that settles the question outright;
    :func:`remove_dc` is what makes 2**23 usable, and :func:`bands` reports
    the sub-20 Hz energy so the residue can be seen.
    """
    return int(np.ceil(spectra.main_lobe_bins() * fs / f_lo))


_WINDOWS: dict[int, np.ndarray] = {}


def window(n: int) -> np.ndarray:
    """:func:`spectra.analysis_window`, cached.

    A Kaiser at beta 26 over 2**23 points is an ``i0`` over eight million
    values and costs about as much as the transform it is for. Hundreds of
    trials all use the same handful of lengths.
    """
    w = _WINDOWS.get(n)
    if w is None:
        w = spectra.analysis_window(n)
        _WINDOWS[n] = w
    return w


def dc_grid_dbfs(n: int) -> float:
    """Level of the smallest near-DC component an N-sample record can carry.

    The output takes eight levels spaced ``2/7``, so the record mean lives on
    a grid of ``(2/7)/n``: one unbalanced sample in the whole window.
    """
    return float(spectra.dbfs((QLSB / n) ** 2))


def remove_dc(x: np.ndarray, window: np.ndarray | None = None) -> np.ndarray:
    """:func:`spectra.remove_dc`, with this module's cached window.

    The implementation lives in :mod:`spectra` so that every measurement in
    the model gets it, not only this one.
    """
    x = np.asarray(x, dtype=np.float64)
    return spectra.remove_dc(x, globals()["window"](len(x))
                             if window is None else window)


@dataclass
class Bands:
    """Where an idle record's energy sits, in dBFS."""

    wander_db: float        # 0 < f < 20 Hz, below the band
    low_db: float           # 20 to 100 Hz
    mid_db: float           # 100 Hz to 2 kHz
    high_db: float          # 2 kHz to 20 kHz
    total_db: float         # 20 Hz to 20 kHz
    low_share: float
    peak_hz: float          # loudest in-band bin
    peak_db: float
    dc_db: float            # what was subtracted, as a level

    def row(self) -> str:
        return (f"{self.wander_db:9.1f} {self.low_db:9.1f} {self.mid_db:9.1f} "
                f"{self.high_db:9.1f} {self.total_db:9.1f}")


def bands(x: np.ndarray, fs: float, dedc: bool = True) -> Bands:
    """Band split of an idle record, in dBFS, with the sub-20 Hz part shown.

    :func:`material.band_shape` does the in-band split and is used for it
    directly; what is added here is the energy *below* the band, because that
    is the part a short transform mistakes for the bottom of the band.
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    w = window(n)
    dc = float((w * x).sum() / w.sum())
    if dedc:
        x = x - dc
    bs = material.band_shape(x, fs)
    to_dbfs = 10.0 * np.log10(0.5)          # band_shape reports 10log10(power)
    p = spectra.power_spectrum(x, w)
    f = spectra.bin_freqs(n, fs)
    sub = (f > 0) & (f < chain.AUDIO_LO)
    inb = (f >= BAND[0]) & (f <= BAND[1])
    i = int(np.argmax(p[inb]))
    return Bands(
        wander_db=float(spectra.dbfs(p[sub].sum())) if sub.any() else float("nan"),
        low_db=bs["low_db"] - to_dbfs,
        mid_db=bs["mid_db"] - to_dbfs,
        high_db=bs["high_db"] - to_dbfs,
        total_db=bs["total_db"] - to_dbfs,
        low_share=bs["low_share"],
        peak_hz=float(f[inb][i]),
        peak_db=float(spectra.dbfs(p[inb][i])),
        dc_db=float(spectra.dbfs(dc ** 2)),
    )


# ---------------------------------------------------------------------------
# Loop state, reconstructed rather than re-simulated
# ---------------------------------------------------------------------------

def states(ntf: modulator.NTF, u: np.ndarray, out: np.ndarray) -> np.ndarray:
    """Integrator trajectories, from the input and the output alone.

    The loop is ``x_1 += a_1 d``, ``x_i += x_{i-1} + a_i d`` with
    ``d = u - v``, so with ``d`` known the states are running sums and come
    out vectorised. Saves simulating twice to see inside the loop, and lets
    the state at the start of a measurement window be reported without
    touching :mod:`modulator`.
    """
    a = np.asarray(ntf.a, dtype=np.float64)
    d = np.asarray(u, dtype=np.float64) - np.asarray(out, dtype=np.float64)
    x = np.zeros((ntf.order, len(d)))
    acc = a[0] * d
    x[0, 1:] = np.cumsum(acc)[:-1]
    for i in range(1, ntf.order):
        acc = x[i - 1] + a[i] * d
        x[i, 1:] = np.cumsum(acc)[:-1]
    return x


def pointer(codes: np.ndarray, n: int = chain.N_ELEMENTS) -> np.ndarray:
    """Rotation pointer before each sample: the running sum of earlier codes."""
    c = np.asarray(codes, dtype=np.int64)
    return (np.concatenate(([0], np.cumsum(c)[:-1]))) % n


# ---------------------------------------------------------------------------
# Trials
# ---------------------------------------------------------------------------

IDLE_MATERIAL = ("fade to silence", "digital silence",
                 "near silence -100 dBFS", "small DC offset")


PREAMBLES = ("tone", "fade", "bass", "programme", "percussive", "silence")


def preamble_pcm(n: int, fs: float, kind: str, seed: int,
                 dbfs: float = -20.0) -> np.ndarray:
    """PCM that leaves the loop somewhere before the material goes quiet.

    Discarded, never measured. Its only job is to make the state at the start
    of the window something other than the one state a zero-initialised loop
    always reaches. ``fade`` is the interesting one: the window then begins at
    the end of a decay rather than at a cut, which is where an idle-channel
    fault is supposed to be caught.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    if kind == "tone":
        return 10 ** (dbfs / 20) * np.sin(
            2 * np.pi * rng.uniform(200.0, 5000.0) * t + rng.uniform(0, 6.283))
    if kind == "fade":
        return material.fade_to_silence(n, fs, f=rng.uniform(80.0, 900.0),
                                        start_dbfs=dbfs)
    if kind == "bass":
        return material.sustained_bass(n, fs, dbfs=dbfs)
    if kind == "programme":
        return material.programme(n, fs, dbfs=dbfs, seed=seed)
    if kind == "percussive":
        return material.percussive(n, fs, dbfs=dbfs, seed=seed)
    if kind == "silence":
        return np.zeros(n)
    raise ValueError(kind)


def idle_pcm(n: int, fs: float, name: str, seed: int,
             dbfs: float | None = None) -> np.ndarray:
    """One of :mod:`material`'s idle records, by catalogue name."""
    if name == "fade to silence":
        return material.fade_to_silence(n, fs, start_dbfs=-3.0 if dbfs is None
                                        else dbfs)
    if name == "digital silence":
        return material.digital_silence(n, fs)
    if name == "near silence -100 dBFS":
        return material.near_silence(n, fs, dbfs=-100.0 if dbfs is None
                                     else dbfs, seed=seed)
    if name == "small DC offset":
        return material.dc_offset(n, fs, dbfs=-60.0 if dbfs is None else dbfs)
    if name == "sustained 41 Hz bass":
        return material.sustained_bass(n, fs, dbfs=-6.0 if dbfs is None
                                       else dbfs)
    if name == "programme-like":
        return material.programme(n, fs, dbfs=-6.0 if dbfs is None else dbfs,
                                  seed=seed)
    raise ValueError(name)


@dataclass
class Trial:
    mode: chain.Mode
    idle: str
    pre: str
    seed: int
    n: int
    b: Bands                       # corrected measurement
    b_legacy: Bands                # 2**20, plain mean: what was measured before
    out_mean: float
    lsb_per_window: float          # out_mean in units of (2/7)/n
    x0: np.ndarray                 # integrator state entering the window
    ptr0: int                      # rotation pointer entering the window
    code_hist: np.ndarray
    detector: dict = field(default_factory=dict)


def run_trial(cascade: halfband.Cascade, ntf: modulator.NTF, mode: chain.Mode,
              *, idle: str = "digital silence", pre: str = "tone",
              seed: int = 0, n: int = 1 << 23, n_pre: int = 1 << 19,
              pre_dbfs: float = -20.0, idle_dbfs: float | None = None,
              src_dither: str | None = "none", sigma: float = 0.0,
              rotate: bool = True, quantizer_dither: np.ndarray | None = None,
              mod_dc: float = 0.0, legacy_n: int = 1 << 20,
              idle_reset: bool = False, reset_thresh: float = 2.0 ** -20,
              scramble: bool = False, keep: bool = False) -> Trial:
    """One near-idle trial: preamble, then the idle window, measured.

    The preamble ends ``n_pre`` element samples before the window starts, and
    ``n_pre`` is longer than the cascade's settling time, so the cascade's ring
    on the transition to idle has died out before the first measured sample.
    Getting that wrong costs 70 dB: the ring alone reads as -50 dBFS of
    low-frequency energy and looks exactly like the fault being hunted.

    The source quantizer is applied to the two halves separately. The preamble
    is dithered like real programme material; the idle half is quantized with
    ``src_dither``, which defaults to none so that digital silence is exactly
    zero rather than plus or minus an LSB of TPDF noise. Turning it on is one
    of the remedies measured in ``run_idle.py``.
    """
    fs = mode.element_clock
    settle = cascade.settle_samples(mode)
    ratio = mode.ratio
    if n_pre <= settle:
        raise ValueError(f"guard {n_pre} must exceed the cascade settle "
                         f"{settle}")
    n_pre_pcm = n_pre // ratio - 16
    n_win_pcm = int(np.ceil((settle + n) / ratio)) + 40
    from . import datapath, endtoend

    pre_x = preamble_pcm(n_pre_pcm, mode.fs, pre, seed, pre_dbfs)
    idle_x = idle_pcm(n_win_pcm, mode.fs, idle, seed + 1000, idle_dbfs)
    pcm = np.concatenate([
        endtoend.quantize_pcm(pre_x, chain.PCM_BITS, "tpdf", seed=seed + 5000),
        idle_x if src_dither is None else
        endtoend.quantize_pcm(idle_x, chain.PCM_BITS, src_dither,
                              seed=seed + 6000)])
    y, _ = datapath.interpolate(cascade, pcm, mode, coeff_bits=COEFF_BITS,
                                sig_frac=SIG_FRAC, acc_frac=ACC_FRAC)
    u = y[settle:settle + n_pre + n]
    if len(u) < n_pre + n:
        raise RuntimeError(f"cascade gave {len(u)}, need {n_pre + n}")
    if mod_dc:
        u = u + mod_dc
    if idle_reset:
        o, cd, resets = simulate_idle_reset(ntf, u, fs, thresh=reset_thresh,
                                            dither=quantizer_dither)
        codes = np.asarray(cd, dtype=np.int64)
    else:
        r = modulator.simulate(ntf, u, fs, dither=quantizer_dither)
        o, resets = r.out, 0
        codes = np.asarray(r.codes, dtype=np.int64)
    if sigma == 0.0:
        x = o
    else:
        pos, neg = (differential_scrambled(codes, seed=seed + 13) if scramble
                    else dwa.differential(codes, rotate=rotate))
        wp, wn = dwa.mismatch(sigma, seed=seed + 77)
        x = dwa.normalise(dwa.analog(pos, neg, wp, wn))
    win = x[n_pre:]
    b = bands(win, fs)
    lg = bands(win[:legacy_n] - win[:legacy_n].mean(), fs, dedc=False)
    st = states(ntf, u[:n_pre + 1], o[:n_pre + 1])
    t = Trial(mode=mode, idle=idle, pre=pre, seed=seed, n=n, b=b, b_legacy=lg,
              out_mean=float(win.mean()),
              lsb_per_window=float(win.mean() * n / QLSB),
              x0=st[:, -1].copy(),
              ptr0=int(pointer(codes[:n_pre + 1])[-1]),
              code_hist=np.bincount(codes[n_pre:], minlength=chain.N_LEVELS))
    t.detector["resets"] = resets
    t.detector["u_rms"] = float(np.sqrt(np.mean(u[n_pre:] ** 2)))
    if keep:
        t.detector["record"] = win
        t.detector["codes"] = codes[n_pre:]
    return t


# ---------------------------------------------------------------------------
# Things that might remove it
# ---------------------------------------------------------------------------

def shaped_dither(n: int, lsb_fraction: float = 0.5,
                  seed: int | None = None) -> np.ndarray:
    """High-pass dither for the quantizer input: the first difference of white.

    :func:`modulator.dither_sequence` is white, so a quarter of an LSB of it
    lands a quarter of an LSB of noise in the audio band before the loop
    shapes it. Differencing white noise gives a sequence with a ``2 sin(pi f /
    fs)`` magnitude, which is 60 dB down at 20 kHz and 120 dB down at 20 Hz,
    so the same peak-to-peak perturbation reaches the quantizer with almost
    none of it in band. If breaking ties is what matters, this breaks them for
    free.
    """
    rng = np.random.default_rng(seed)
    w = lsb_fraction * QLSB * (rng.random(n + 1) - 0.5)
    return np.diff(w)


def simulate_idle_reset(ntf: modulator.NTF, u: np.ndarray, fs: float, *,
                        thresh: float = 2.0 ** -20, block: int = 1 << 16,
                        every: bool = False,
                        dither: np.ndarray | None = None):
    """Run the loop, zeroing the integrators when the input goes quiet.

    ``modulator.simulate`` starts from zero state, so a reset is exactly a new
    call. The record is cut into blocks; a block whose input never exceeds
    ``thresh`` triggers a reset, either on the transition into quiet only
    (``every=False``, what hardware would do) or at every quiet block
    (``every=True``, the strongest form). Returns output, codes and the number
    of resets.

    This is the aggressive remedy: it throws away the loop's memory of the
    error it has not yet corrected, so whatever that error was appears at the
    output as a step instead of being shaped away.
    """
    u = np.asarray(u, dtype=np.float64)
    n = len(u)
    out = np.empty(n)
    codes = np.empty(n, dtype=np.uint8)
    resets = 0
    start = 0
    i = 0
    was_quiet = True
    while i < n:
        j = min(i + block, n)
        quiet = np.abs(u[i:j]).max() < thresh
        if quiet and i > start and (every or not was_quiet):
            seg = slice(start, i)
            r = modulator.simulate(ntf, u[seg], fs,
                                   dither=None if dither is None else dither[seg])
            out[seg] = r.out
            codes[seg] = r.codes
            start = i
            resets += 1
        was_quiet = quiet
        i = j
    seg = slice(start, n)
    r = modulator.simulate(ntf, u[seg], fs,
                           dither=None if dither is None else dither[seg])
    out[seg] = r.out
    codes[seg] = r.codes
    return out, codes, resets


def select_scrambled(codes: np.ndarray, n: int = chain.N_ELEMENTS,
                     seed: int = 0) -> np.ndarray:
    """Rotation with a pseudo-random extra step, breaking the pointer's period.

    At idle the codes alternate between 3 and 4, so the plain pointer advances
    by 7 every two samples and returns to where it started: the pointer is
    periodic with period 2 and each code always lights the same elements.
    Adding a random step per sample destroys that. In hardware it is an LFSR
    and an adder.
    """
    c = np.asarray(codes, dtype=np.int64)
    rng = np.random.default_rng(seed)
    step = rng.integers(0, n, size=len(c))
    ptr = (np.concatenate(([0], np.cumsum(c + step)[:-1]))) % n
    idx = np.arange(n)[None, :]
    return ((idx - ptr[:, None]) % n) < c[:, None]


def differential_scrambled(codes: np.ndarray, n: int = chain.N_ELEMENTS,
                           seed: int = 0):
    codes = np.asarray(codes, dtype=np.int64)
    return (select_scrambled(codes, n, seed),
            select_scrambled(n - codes, n, seed + 1))


# ---------------------------------------------------------------------------
# A runtime detector
# ---------------------------------------------------------------------------

def imbalance(codes: np.ndarray, block: int) -> np.ndarray:
    """Per-block sum of ``code - 3.5``, in units of half an element.

    This is the whole detector. At idle the eight-level quantizer has no zero
    level, so a quiet loop alternates between codes 3 and 4 and the sum over
    any block is near zero. A low-frequency wander is precisely a sustained
    excess of one over the other, so the block sum is its matched filter. In
    hardware: an up/down counter, a comparator, and a shift register for the
    block length.
    """
    c = np.asarray(codes, dtype=np.int64)
    m = len(c) // block * block
    return (2 * c[:m] - 7).reshape(-1, block).sum(axis=1) / 2.0


def detector_stat(codes: np.ndarray, block: int) -> float:
    """Worst block imbalance over a record, as a fraction of the block length.

    Scale-free, so one threshold covers every block length: 1.0 would be the
    output pinned one code away from the idle pair for a whole block.
    """
    im = imbalance(codes, block)
    return float(np.abs(im).max() / block) if len(im) else 0.0


def idle_gate(u: np.ndarray, block: int, thresh: float) -> np.ndarray:
    """Which blocks of the modulator input are quiet enough to judge.

    The detector below cannot tell a limit cycle from real bass, and must not
    try: 40 Hz content at -20 dBFS *should* swing the output. The FPGA knows
    its own input, so the cheap discriminator is to run the detector only
    where the input is small, which is one comparator and an OR-tree.
    """
    a = np.abs(np.asarray(u, dtype=np.float64))
    m = len(a) // block * block
    return a[:m].reshape(-1, block).max(axis=1) < thresh


__all__ = ["BAND", "LOW", "window", "COEFF_BITS", "SIG_FRAC", "ACC_FRAC", "QLSB",
           "Bands", "Trial", "min_transform", "dc_grid_dbfs", "remove_dc",
           "bands", "states", "pointer", "preamble_pcm", "idle_pcm",
           "run_trial", "imbalance", "detector_stat", "idle_gate",
           "IDLE_MATERIAL"]

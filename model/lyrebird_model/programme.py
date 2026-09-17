"""The chain measured against broadband material instead of a tone.

Every figure in :mod:`endtoend` comes from one sine or from the inter-sample
probe. A sine is the right instrument for a noise floor and the wrong one for
three questions this module exists to answer: whether the end-to-end figure
survives material with a real crest factor, where material with a real crest
factor actually overloads the quantizer, and whether genuine low-frequency
content can be told apart from the low-frequency wander described in
README.md.

The instrument
--------------
Signal-to-noise against a single tone is meaningless for broadband material:
there is no lobe to excise, and excising the whole occupied band leaves
nothing. What is measured here instead is the **error**, against the ideal
reconstruction of the same PCM::

    e = x - g * u_ref

``u_ref`` is the cascade output for the *unquantized* float record at exact
datapath precision; ``x`` is the element sum for the same record taken through
everything the hardware does -- 24-bit source quantizer, quantized
coefficients, sized datapath, modulator, rotation, mismatched elements. Both
use the same quantized coefficients, so the cascade's own response cancels and
what is left is the set of terms the end-to-end SNDR figure is made of: source
word length, datapath rounding, modulator quantization noise and the rotation
residual.

Three details in that formula are not decoration.

**Alignment is exact and must be checked, not assumed.** The modulator's STF
is exactly 1 with zero delay, and both paths run the same cascade, so ``x`` and
``u_ref`` line up sample for sample once the same ``settle_samples`` prefix is
dropped from each. Getting that prefix wrong produces a confident number that
is wrong by tens of dB, so :func:`alignment_margin` measures how much worse
the error gets when the two paths are slid apart, rather than trusting the
offset.

**The gain has to be fitted, and fitted in band.** Element mismatch is a
static weight per element, so it shows up as a gain error of order
``sigma/sqrt(7)`` -- 0.4 percent at one percent elements. A tone measurement
never sees that, because the signal lobe is excised. An error measurement sees
all of it: 0.4 percent of a -6 dBFS signal is an error at -54 dBFS, which would
swallow a floor at -136 dBFS whole. So a scalar gain is fitted and removed,
which is the broadband equivalent of excising the fundamental.

It must be fitted over the audio band only. A least-squares fit over the whole
record is dominated by the modulator's out-of-band noise, which is 90 dB above
the in-band error; that noise is uncorrelated with the signal but its inner
product with it is not zero, and the resulting gain error injects a spurious
in-band residual of about -77 dBFS. Restricting the fit to the band the
measurement reports drops that artefact to below -160 dBFS. The fit is pooled
over all the windows of a render, because the mismatch gain is a static
property of the elements rather than something that changes window to window;
the per-window spread is reported as a check that a scalar is the right model.

**The mean has to go, and it has to go before the gain fit as well as after
it.** Element mismatch leaves a static offset, and at 23.4 Hz bins a Kaiser
main lobe is twelve bins wide, so DC leaks to 280 Hz -- straight through the
20 to 100 Hz band where the wander lives, and straight through the band the
gain is fitted over. Removing it from the error but not from the fit is not
half right, it is wrong: measured on a -70 dBFS record at one percent
elements, the gain came out 1.207 instead of 0.9988 and the reported error
stopped moving when the input level moved, sitting at -88.4 dBFS whether the
record was at -12, -40 or -70 dBFS. **An error figure that does not respond to
the input is not measuring the converter**, and that tell is worth more than
the rule it broke.

Windows
-------
One window is 2**20 element-clock samples, which is 42.7 ms and 23.4 Hz bins.
That is the shortest transform that gives the audio band enough bins to call
noise (see README.md). A long record is measured as a sequence of such
windows, continuous through the modulator within a segment, because a single
figure over a long record averages away exactly the fault this is looking for.

Each segment is preceded by :data:`WARMUP` samples that are run through the
modulator and then discarded, so the loop and the rotation pointer arrive at
the first measured window already settled rather than from zero.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import chain, datapath, dwa, endtoend, halfband, material, modulator, spectra

BAND = endtoend.BAND
WINDOW = 1 << 20                # 42.7 ms, 23.4 Hz bins at the element clock
WARMUP = 1 << 18                # 10.7 ms of modulator and rotation warm-up

# The widths settled by run_experiments.py and run_endtoend.py, carried here so
# that what is measured is the chain as it will be built.
COEFF_BITS = {1: 26, 2: 26, 3: 26, 4: 22, 5: 19, 6: 18, 7: 10, 8: 8, 9: 8}
SIG_FRAC = {s: 26 for s in range(1, 10)}
ACC_FRAC = {1: 31, 2: 31, 3: 31, 4: 30, 5: 30, 6: 29, 7: 29, 8: 29, 9: 29}

ORDER = 3
MISMATCH_SEED = 7               # one physical board: same weights everywhere


# ---------------------------------------------------------------------------
# Material handling
# ---------------------------------------------------------------------------

def concatenate(records: list[np.ndarray], gap: int = 0) -> np.ndarray:
    """Join records end to end, optionally with silence between them."""
    out: list[np.ndarray] = []
    for i, r in enumerate(records):
        if i and gap:
            out.append(np.zeros(gap))
        out.append(np.asarray(r, dtype=np.float64))
    return np.concatenate(out)


def normalise_peak(x: np.ndarray, dbfs: float) -> np.ndarray:
    """Scale so the largest *sample* sits at ``dbfs``. Says nothing about the
    peak between the samples, which is the whole subject of the headroom
    question."""
    pk = float(np.abs(x).max())
    return np.asarray(x, dtype=np.float64) * (10.0 ** (dbfs / 20.0) / max(pk, 1e-30))


def limit(x: np.ndarray, drive_db: float, ceiling: float = 1.0) -> np.ndarray:
    """Hard-clip after a gain, which is what a loudness limiter leaves behind.

    Clipping a band-limited record makes samples sit flat at full scale while
    the waveform the reconstruction filter puts back between them does not.
    That is where inter-sample overs in real releases come from, and no
    unprocessed recording contains them. ``drive_db`` is the gain applied
    before the clip, so it sets how hard the material is limited.
    """
    y = np.asarray(x, dtype=np.float64) * 10.0 ** (drive_db / 20.0)
    return np.clip(y, -ceiling, ceiling)


def crest_db(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    rms = float(np.sqrt(np.mean(x * x)))
    return float(20.0 * np.log10(float(np.abs(x).max()) / max(rms, 1e-30)))


def peak_slice(x: np.ndarray, n: int) -> np.ndarray:
    """``n`` samples of ``x`` centred on its largest sample.

    A headroom measurement taken on an arbitrary slice of programme material
    measures whatever happened to be in that slice. The loudest moment is the
    one that decides whether the loop survives, so it is the one that gets
    measured.
    """
    x = np.asarray(x, dtype=np.float64)
    if len(x) <= n:
        return np.pad(x, (0, n - len(x)))
    c = int(np.argmax(np.abs(x)))
    lo = min(max(c - n // 2, 0), len(x) - n)
    return x[lo:lo + n]


def tile_to(x: np.ndarray, n: int) -> np.ndarray:
    """Repeat a record until it is at least ``n`` long, then trim."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) >= n:
        return x[:n]
    return np.tile(x, int(np.ceil(n / len(x))))[:n]


# ---------------------------------------------------------------------------
# The elements, in bounded memory
# ---------------------------------------------------------------------------

def element_sum(codes: np.ndarray, *, rotate: bool = True,
                w_pos: np.ndarray | None = None,
                w_neg: np.ndarray | None = None,
                chunk: int = 1 << 19) -> np.ndarray:
    """:func:`dwa.differential` + :func:`dwa.analog`, chunked.

    ``select_rotated`` builds an ``(n, 7)`` integer array, which is 56 bytes a
    sample; a multi-window record does not fit. Chunking is exact rather than
    approximate because the rotation pointer is just the running code sum, so
    carrying it across the chunk boundary reproduces the unchunked result bit
    for bit. :func:`self_check` asserts that.
    """
    codes = np.asarray(codes, dtype=np.int64)
    n = chain.N_ELEMENTS
    out = np.empty(len(codes), dtype=np.float64)
    sp = sn = 0
    for i in range(0, len(codes), chunk):
        c = codes[i:i + chunk]
        comp = n - c
        if rotate:
            pos = dwa.select_rotated(c, n, start=sp)
            neg = dwa.select_rotated(comp, n, start=sn)
        else:
            pos = dwa.select_fixed(c, n)
            neg = dwa.select_fixed(comp, n)
        out[i:i + chunk] = dwa.analog(pos, neg, w_pos, w_neg)
        sp = (sp + int(c.sum())) % n
        sn = (sn + int(comp.sum())) % n
    return dwa.normalise(out, n)


# ---------------------------------------------------------------------------
# One pass of the chain, keeping the signals the measurement needs
# ---------------------------------------------------------------------------

@dataclass
class Render:
    mode: chain.Mode
    n_out: int
    sigma: float
    u_ref: np.ndarray           # ideal reconstruction, float source, exact datapath
    u_src: np.ndarray | None    # same but from the 24-bit source: isolates it
    u: np.ndarray               # what the modulator actually received
    x: np.ndarray               # element sum, normalised to +/-1
    v: np.ndarray               # ideal element sum from the codes, no mismatch
    codes: np.ndarray
    state_peak: np.ndarray
    clipped: int
    stable: bool
    peak_u: float

    @property
    def loop_error(self) -> np.ndarray:
        """``v - u``: the converter's own error with the music removed.

        The STF of this topology is exactly 1 with zero delay, so subtracting
        the modulator's input from its output cancels the programme exactly and
        leaves the shaped quantization error. Both terms exist inside the loop
        already -- the subtraction is the ``d`` the integrators are driven by --
        so this is a signal the FPGA has for free. Note that it stops at the
        codes: element mismatch happens after it and does not appear.
        """
        return self.v - self.u


def render(cascade: halfband.Cascade, ntf: modulator.NTF, mode: chain.Mode,
           pcm: np.ndarray, *,
           n_out: int | None = None,
           warmup: int | None = None,
           sigma: float = 0.0,
           rotate: bool = True,
           bits: int | None = chain.PCM_BITS,
           dither: str = "tpdf",
           seed: int = 7,
           coeff_bits=COEFF_BITS,
           sig_frac=SIG_FRAC,
           acc_frac=ACC_FRAC,
           rounding: str | None = None,
           mod_offset: float = 0.0,
           mod_gain_db: float = 0.0,
           keep_source_term: bool = False) -> Render:
    """Run ``pcm`` through everything and keep what the error measurement needs.

    ``mod_offset`` adds a static offset at the modulator input, which is how
    the low-frequency wander is provoked on purpose: README.md measures that
    half-up rounding leaves one and that the loop turns it into idle tones at
    the bottom of the band. ``mod_gain_db`` is the volume control, which 0010
    puts exactly there.
    """
    n_out = WINDOW if n_out is None else n_out
    warmup = WARMUP if warmup is None else warmup
    settle = cascade.settle_samples(mode)
    need = settle + warmup + n_out
    pcm = np.asarray(pcm, dtype=np.float64)

    ref, _ = datapath.interpolate(cascade, pcm, mode, coeff_bits=coeff_bits)
    q = pcm if bits is None else endtoend.quantize_pcm(pcm, bits, dither,
                                                       seed=seed + 4)
    got, _ = datapath.interpolate(cascade, q, mode, coeff_bits=coeff_bits,
                                  sig_frac=sig_frac, acc_frac=acc_frac,
                                  rounding=rounding)
    if min(len(ref), len(got)) < need:
        raise RuntimeError(f"cascade produced {min(len(ref), len(got))} samples, "
                           f"need {need}: give it more PCM")
    src = None
    if keep_source_term and bits is not None:
        s, _ = datapath.interpolate(cascade, q, mode, coeff_bits=coeff_bits)
        src = s[settle + warmup:need]

    gain = 10.0 ** (mod_gain_db / 20.0)
    drive = got[settle:need] * gain + mod_offset
    r = modulator.simulate(ntf, drive, mode.element_clock)
    codes = np.clip(np.asarray(r.codes, dtype=np.int64), 0, chain.N_ELEMENTS)
    wp, wn = ((None, None) if sigma == 0.0
              else dwa.mismatch(sigma, seed=MISMATCH_SEED))
    x = element_sum(codes, rotate=rotate, w_pos=wp, w_neg=wn)
    return Render(
        mode=mode, n_out=n_out, sigma=sigma,
        u_ref=ref[settle + warmup:need] * gain,
        u_src=None if src is None else src * gain,
        u=drive[warmup:], x=x[warmup:], v=r.out[warmup:],
        codes=codes[warmup:], state_peak=r.state_peak, clipped=r.clipped,
        stable=bool(r.stable), peak_u=float(np.abs(drive[warmup:]).max()),
    )


# ---------------------------------------------------------------------------
# The error instrument
# ---------------------------------------------------------------------------

def band_gain_terms(x: np.ndarray, ref: np.ndarray, fs: float,
                    band: tuple[float, float] = BAND) -> tuple[float, float]:
    """Cross and auto terms of an in-band least-squares gain fit.

    Returned unreduced so a pooled fit over many windows is the ratio of the
    sums. See the module docstring for why the fit is restricted to the band:
    a broadband fit is dominated by out-of-band shaped noise and leaves a
    spurious in-band residual around -77 dBFS.
    """
    n = len(ref)
    w = spectra.analysis_window(n)
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(ref, dtype=np.float64)
    # The mean has to go before the fit, not only after it. Element mismatch
    # leaves a static offset on the element sum, and at 23.4 Hz bins the
    # Kaiser main lobe is twelve bins wide, so that offset leaks to 280 Hz --
    # inside the band the fit is taken over. Left in, it biases the gain by
    # whatever the reference happens to carry down there, which is nothing
    # when the music is loud and everything when it is quiet: measured, it put
    # the fitted gain at 1.207 instead of 0.9988 on a -70 dBFS record and
    # invented an error at -88 dBFS that did not move when the level did.
    X = np.fft.rfft((a - a.mean()) * w)
    U = np.fft.rfft((b - b.mean()) * w)
    f = spectra.bin_freqs(n, fs)
    sel = (f >= band[0]) & (f <= band[1])
    cross = float(np.real(np.vdot(U[sel], X[sel])))
    auto = float(np.real(np.vdot(U[sel], U[sel])))
    return cross, auto


def alignment_margin(x: np.ndarray, ref: np.ndarray, fs: float,
                     band: tuple[float, float] = BAND,
                     n: int = 1 << 18, shift: int = 256,
                     floor_dbfs: float = -60.0) -> tuple[float, float]:
    """How much worse the error gets if the two paths are slid apart.

    The settling offset is the one thing in this measurement that silently
    produces confident nonsense: slice the two paths by different amounts and
    the error becomes the signal itself, delayed.

    A plain argmax of the cross-correlation over a few samples cannot check
    that. The signal is band-limited to 20 kHz and sampled at 24.576 MHz, so
    its autocorrelation is flat to six decimal places over plus or minus eight
    samples -- every small lag looks equally good and the argmax reports
    whichever way the out-of-band noise happened to fall. Measured on real
    material that false-alarmed on 34 of 90 segments.

    What is checked instead is the thing that matters: the in-band error at the
    offset actually used, against the in-band error at plus and minus
    ``shift`` samples. Correct alignment makes the first far smaller than the
    second. ``shift`` of 256 samples is 10.4 us, a fifth of a period at
    10 kHz, so it is a real displacement for anything with treble in it.

    Returns ``(error at lag 0 in dBFS, margin in dB)``. A margin of ``nan``
    means the record had nothing loud enough to decide on.
    """
    x = np.asarray(x, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    m = min(len(ref), len(x)) - 2 * shift
    n = min(n, m)
    if n <= 0:
        return float("nan"), float("nan")
    c = int(np.argmax(np.abs(ref)))
    lo = min(max(c - n // 2, shift), min(len(ref), len(x)) - n - shift)
    b = ref[lo:lo + n]
    w = spectra.analysis_window(n)
    f = spectra.bin_freqs(n, fs)
    sel = (f >= band[0]) & (f <= band[1])
    U = np.fft.rfft((b - b.mean()) * w)
    p_ref = spectra.power_spectrum(b - b.mean(), w)
    if float(spectra.dbfs(float(p_ref[sel].sum()))) < floor_dbfs:
        return float("nan"), float("nan")

    def err_db(k: int) -> float:
        a = x[lo + k:lo + k + n]
        X = np.fft.rfft((a - a.mean()) * w)
        g = (float(np.real(np.vdot(U[sel], X[sel])))
             / float(np.real(np.vdot(U[sel], U[sel]))))
        e = (a - a.mean()) - g * (b - b.mean())
        pe = spectra.power_spectrum(e - e.mean(), w)
        return float(spectra.dbfs(float(pe[sel].sum())))

    e0 = err_db(0)
    es = min(err_db(shift), err_db(-shift))
    return e0, es - e0


@dataclass
class WindowStat:
    index: int
    t0: float                   # seconds from the start of the record
    sig_dbfs: float             # in-band power of the reference
    err_dbfs: float             # in-band power of the error
    dr_db: float                # full scale over the in-band error
    snr_db: float               # reference over the error, this window
    low_db: float               # 20-100 Hz, dBFS
    mid_db: float               # 100 Hz - 2 kHz
    high_db: float              # 2 kHz - 20 kHz
    low_share: float
    peak_u_dbfs: float          # peak at the quantizer in this window
    rail_frac: float            # fraction of samples at code 0 or 7
    gain: float                 # per-window fitted gain, diagnostic only
    src_dbfs: float = float("nan")   # in-band error of the 24-bit source alone
    loop_low_dbfs: float = float("nan")   # 20-100 Hz of v-u, the free detector
    loop_db: float = float("nan")         # 20 Hz-20 kHz of v-u


def _to_dbfs(power_db: float) -> float:
    """material.band_shape reports 10log10(power); dBFS is against 0.5."""
    return float(power_db - 10.0 * np.log10(0.5))


def measure(r: Render, *, window: int | None = None, t_offset: float = 0.0,
            band: tuple[float, float] = BAND,
            sig_floor_dbfs: float = -80.0) -> list[WindowStat]:
    """Split a render into windows and measure the error in each.

    The gain fit is pooled over the windows of the render; windows whose
    reference is below ``sig_floor_dbfs`` contribute nothing to it, so a fade
    into silence cannot drag it around.
    """
    window = WINDOW if window is None else window
    fs = r.mode.element_clock
    n = len(r.u_ref)
    k = n // window
    if k == 0:
        raise ValueError(f"render is {n} samples, one window is {window}")

    f = spectra.bin_freqs(window, fs)
    inb = (f >= band[0]) & (f <= band[1])

    cross = auto = 0.0
    per: list[tuple[float, float, float]] = []
    for i in range(k):
        s = slice(i * window, (i + 1) * window)
        ref = r.u_ref[s]
        sig = spectra.power_spectrum(ref - ref.mean())
        sig_dbfs = float(spectra.dbfs(float(sig[inb].sum())))
        cr, au = band_gain_terms(r.x[s], ref, fs, band)
        per.append((cr, au, sig_dbfs))
        if sig_dbfs >= sig_floor_dbfs:
            cross += cr
            auto += au
    g = cross / auto if auto > 0 else 1.0

    out: list[WindowStat] = []
    for i in range(k):
        s = slice(i * window, (i + 1) * window)
        ref = r.u_ref[s]
        e = r.x[s] - g * ref
        e = e - e.mean()
        bs = material.band_shape(e, fs)
        cr, au, sig_dbfs = per[i]
        err_dbfs = _to_dbfs(bs["total_db"])
        d = r.loop_error[s]
        d = d - d.mean()
        dbs = material.band_shape(d, fs)
        src_dbfs = float("nan")
        if r.u_src is not None:
            es = r.u_src[s] - ref
            es = es - es.mean()
            src_dbfs = _to_dbfs(material.band_shape(es, fs)["total_db"])
        codes = r.codes[s]
        out.append(WindowStat(
            index=i, t0=t_offset + i * window / fs,
            sig_dbfs=sig_dbfs, err_dbfs=err_dbfs, dr_db=-err_dbfs,
            snr_db=sig_dbfs - err_dbfs,
            low_db=_to_dbfs(bs["low_db"]), mid_db=_to_dbfs(bs["mid_db"]),
            high_db=_to_dbfs(bs["high_db"]), low_share=float(bs["low_share"]),
            peak_u_dbfs=float(20.0 * np.log10(
                max(float(np.abs(r.u[s]).max()), 1e-30))),
            rail_frac=float(np.mean((codes == 0) | (codes == chain.N_ELEMENTS))),
            gain=cr / au if au > 0 else float("nan"),
            src_dbfs=src_dbfs,
            loop_low_dbfs=_to_dbfs(dbs["low_db"]),
            loop_db=_to_dbfs(dbs["total_db"]),
        ))
    return out


# ---------------------------------------------------------------------------
# Long records, one segment at a time
# ---------------------------------------------------------------------------

def pcm_for(cascade: halfband.Cascade, mode: chain.Mode, n_out: int,
            warmup: int | None = None) -> int:
    """PCM samples one segment of ``n_out`` element samples needs."""
    return endtoend.input_length(cascade, mode,
                                 n_out + (WARMUP if warmup is None else warmup))


def segment_starts(n_pcm: int, need: int, n_seg: int | None = None) -> list[int]:
    """Start indices of consecutive segments that fit inside a record.

    Segments overlap by exactly the settling and warm-up prefix, so every
    measured window is new material and the chain never sees a discontinuity
    inside a window.
    """
    starts: list[int] = []
    step = need
    i = 0
    while i + need <= n_pcm and (n_seg is None or len(starts) < n_seg):
        starts.append(i)
        i += step
    return starts


def _mode_of(family: str, multiplier: int) -> chain.Mode:
    return [m for m in chain.modes(family) if m.multiplier == multiplier][0]


def run_segment(job: dict) -> dict:
    """One segment, start to finish. Top level so a process pool can call it."""
    fam = job["family"]
    cascade = halfband.build(fam)
    mode = _mode_of(fam, job["multiplier"])
    ntf = modulator.synthesize_ntf(job.get("order", ORDER))
    kw = dict(job.get("kw", {}))
    n_out = kw.pop("n_out", None)
    r = render(cascade, ntf, mode, np.asarray(job["pcm"], dtype=np.float64),
               n_out=n_out, **kw)
    if not r.stable:
        return {"label": job.get("label"), "stable": False,
                "windows": [], "state_peak": r.state_peak.tolist(),
                "clipped": r.clipped, "align": (float("nan"), float("nan")),
                "peak_u": r.peak_u}
    stats = measure(r, window=job.get("window", WINDOW),
                    t_offset=job.get("t0", 0.0))
    return {
        "label": job.get("label"), "stable": True,
        "windows": [s.__dict__ for s in stats],
        "state_peak": r.state_peak.tolist(), "clipped": r.clipped,
        "align": alignment_margin(r.x, r.u_ref, r.mode.element_clock),
        "peak_u": r.peak_u,
    }


def run_jobs(jobs: list[dict], workers: int = 1, progress=None) -> list[dict]:
    """Map :func:`run_segment` over jobs, in a process pool when asked.

    Each job is self-contained and seeded, so the result does not depend on
    how the work is scheduled.
    """
    if workers <= 1 or len(jobs) == 1:
        out = []
        for i, j in enumerate(jobs):
            out.append(run_segment(j))
            if progress:
                progress(i + 1, len(jobs))
        return out
    from concurrent.futures import ProcessPoolExecutor, as_completed
    out: list = [None] * len(jobs)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_segment, j): i for i, j in enumerate(jobs)}
        done = 0
        for fu in as_completed(futs):
            out[futs[fu]] = fu.result()
            done += 1
            if progress:
                progress(done, len(jobs))
    return out


# ---------------------------------------------------------------------------
# Peaks between the samples
# ---------------------------------------------------------------------------

def true_peak(cascade: halfband.Cascade, mode: chain.Mode, pcm: np.ndarray,
              coeff_bits=COEFF_BITS, fade_n: int = 256,
              block: int = 1 << 13) -> dict:
    """Peak the cascade presents to the quantizer, against the PCM's own peak.

    This is the number the headroom recommendation is really about: a record
    whose samples never exceed full scale can still hand the modulator a peak
    above it, because the cascade is a reconstruction filter and reconstructs
    what was between the samples.

    Two things are handled rather than assumed.

    The record is faded at both ends. An un-faded record switches on at a
    non-zero sample, the cascade rings on that step, and the peak read back is
    the record's edge rather than the signal -- README.md measures 1 dB of
    headroom invented that way.

    Long records are scanned in blocks. A seventeen-second record at 48 kHz
    interpolates to 410 million samples, which does not fit in memory; each
    block carries enough input either side to fill the filters, and the
    transient at each end of the block's own output is dropped, so the blocks
    overlap and every sample of the record is covered by some block's interior.
    """
    x = endtoend.fade(np.asarray(pcm, dtype=np.float64), fade_n)
    settle = cascade.settle_samples(mode)
    guard = int(np.ceil(settle / mode.ratio)) + 8
    tp, where = 0.0, 0
    n = len(x)
    for i in range(0, n, block):
        lo = max(i - guard, 0)
        hi = min(i + block + guard, n)
        y, _ = datapath.interpolate(cascade, x[lo:hi], mode, coeff_bits=coeff_bits)
        core = y[settle:len(y) - settle] if len(y) > 2 * settle else y[settle:]
        if not len(core):
            continue
        j = int(np.argmax(np.abs(core)))
        if abs(core[j]) > tp:
            tp = float(abs(core[j]))
            where = int(round((lo * mode.ratio + j) / mode.ratio))
    sample_peak = float(np.abs(x).max())
    at = int(np.argmax(np.abs(x)))
    return {
        "sample_peak": sample_peak,
        "sample_peak_dbfs": 20.0 * np.log10(max(sample_peak, 1e-30)),
        "true_peak": tp,
        "true_peak_dbfs": 20.0 * np.log10(max(tp, 1e-30)),
        "overshoot_db": 20.0 * np.log10(max(tp, 1e-30) / max(sample_peak, 1e-30)),
        "true_peak_at": where,
        "sample_peak_at": at,
        "apart": abs(where - at),
    }


def true_peak_index(cascade: halfband.Cascade, mode: chain.Mode,
                    pcm: np.ndarray, coeff_bits=COEFF_BITS,
                    fade_n: int = 256, block: int = 1 << 13) -> tuple[int, float]:
    """Where in the PCM record the cascade reconstructs its largest peak.

    Not the same place as the largest sample, and for clipped material not
    close to it. Measured on a percussive record clipped 12 dB, the loudest
    sample is at PCM index 271 and the loudest reconstructed peak is at 73150
    -- one and a half seconds apart, and 2.5 dB higher. A headroom measurement
    windowed on the loudest sample therefore misses the moment that decides
    the answer, which is the whole point of windowing on a peak at all.
    """
    x = endtoend.fade(np.asarray(pcm, dtype=np.float64), fade_n)
    settle = cascade.settle_samples(mode)
    guard = int(np.ceil(settle / mode.ratio)) + 8
    best, where = 0.0, 0
    for i in range(0, len(x), block):
        lo = max(i - guard, 0)
        hi = min(i + block + guard, len(x))
        y, _ = datapath.interpolate(cascade, x[lo:hi], mode,
                                    coeff_bits=coeff_bits)
        core = y[settle:len(y) - settle] if len(y) > 2 * settle else y[settle:]
        if not len(core):
            continue
        j = int(np.argmax(np.abs(core)))
        if abs(core[j]) > best:
            best = float(abs(core[j]))
            where = int(round((lo * mode.ratio + j) / mode.ratio))
    return where, best


def true_peak_slice(cascade: halfband.Cascade, mode: chain.Mode,
                    pcm: np.ndarray, n: int, coeff_bits=COEFF_BITS) -> np.ndarray:
    """``n`` samples centred on the largest peak the cascade reconstructs."""
    x = np.asarray(pcm, dtype=np.float64)
    if len(x) <= n:
        return np.pad(x, (0, n - len(x)))
    c, _ = true_peak_index(cascade, mode, x, coeff_bits=coeff_bits)
    lo = min(max(c - n // 2, 0), len(x) - n)
    return x[lo:lo + n]


def survives(cascade: halfband.Cascade, ntf: modulator.NTF, mode: chain.Mode,
             pcm: np.ndarray, amp_dbfs: float, *, n_out: int,
             state_cap: float = 50.0, coeff_bits=COEFF_BITS) -> dict:
    """Does the loop stay bounded with this material at this level?

    Same bound as :func:`modulator.max_stable_amplitude` and
    :func:`endtoend.max_stable_pcm` -- no integrator past ``state_cap``
    quantizer LSBs -- so the answer is comparable with the tone and
    inter-sample numbers already in README.md.
    """
    limit_ = state_cap * modulator.LSB
    x = normalise_peak(pcm, amp_dbfs)
    x = endtoend.quantize_pcm(x)
    y, _ = datapath.interpolate(cascade, x, mode, coeff_bits=coeff_bits)
    settle = cascade.settle_samples(mode)
    u = y[settle:settle + n_out]
    if len(u) < n_out:
        raise RuntimeError("not enough material for this window")
    r = modulator.simulate(ntf, u, mode.element_clock, state_limit=limit_)
    peak = float(np.abs(u).max())
    return {
        "amp_dbfs": amp_dbfs, "peak": peak,
        "peak_dbfs": float(20.0 * np.log10(max(peak, 1e-30))),
        "stable": bool(r.stable and float(r.state_peak.max()) <= limit_),
        "clipped": int(r.clipped), "state_peak": r.state_peak.copy(),
    }


def max_stable_material(cascade: halfband.Cascade, ntf: modulator.NTF,
                        mode: chain.Mode, pcm: np.ndarray, *, n_out: int,
                        lo: float = -24.0, hi: float = 0.0,
                        tol: float = 0.05) -> dict:
    """Bisect the PCM level at which this material stops being survivable.

    ``pcm`` is taken as a fixed waveform and only its level is varied, so what
    the bisection moves is the one thing a host controls.
    """
    d_hi = survives(cascade, ntf, mode, pcm, hi, n_out=n_out)
    if d_hi["stable"]:
        return d_hi | {"bisected": False}
    d_lo = survives(cascade, ntf, mode, pcm, lo, n_out=n_out)
    if not d_lo["stable"]:
        return d_lo | {"bisected": False}
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        d = survives(cascade, ntf, mode, pcm, mid, n_out=n_out)
        if d["stable"]:
            lo, d_lo = mid, d
        else:
            hi = mid
    return d_lo | {"bisected": True}


# ---------------------------------------------------------------------------
def self_check() -> None:
    """Assert the chunked elements and the error instrument are what they claim."""
    rng = np.random.default_rng(4)
    codes = rng.integers(0, 8, 3000)
    wp, wn = dwa.mismatch(0.01, seed=MISMATCH_SEED)
    pos, neg = dwa.differential(codes, rotate=True)
    want = dwa.normalise(dwa.analog(pos, neg, wp, wn))
    for ch in (3000, 997, 128):
        got = element_sum(codes, rotate=True, w_pos=wp, w_neg=wn, chunk=ch)
        # Not bit-identical: numpy dispatches a (128,7) matmul differently from
        # a (3000,7) one and the seven products land in a different order. The
        # element selection itself is identical, which is what is being checked.
        assert float(np.abs(got - want).max()) < 1e-15, (ch, np.abs(got - want).max())
    pos, neg = dwa.differential(codes, rotate=False)
    want = dwa.normalise(dwa.analog(pos, neg, wp, wn))
    got = element_sum(codes, rotate=False, w_pos=wp, w_neg=wn, chunk=256)
    assert float(np.abs(got - want).max()) < 1e-15
    # codes themselves must be selected identically, mismatch aside
    got = element_sum(codes, rotate=True, chunk=128)
    want = dwa.normalise(dwa.analog(*dwa.differential(codes, rotate=True)))
    assert float(np.abs(got - want).max()) == 0.0

    # The in-band gain fit must recover a gain and must not invent a residual.
    n = 1 << 16
    fs = float(n)                    # one bin per hertz, so 997 is in band
    t = np.arange(n)
    ref = 0.5 * np.sin(2.0 * np.pi * 997 * t / n)
    x = 1.004 * ref + 1e-6 * rng.standard_normal(n)
    cr, au = band_gain_terms(x, ref, fs)
    assert abs(cr / au - 1.004) < 1e-4, cr / au
    # the alignment guard must reward the right offset and punish a slide
    t2 = np.arange(1 << 16)
    fs2 = chain.ELEMENT_CLOCK["48k"]
    sig = 0.4 * np.sin(2.0 * np.pi * 9000.0 * t2 / fs2)
    noise = 1e-5 * rng.standard_normal(len(t2))
    e0, margin = alignment_margin(sig + noise, sig, fs2, shift=256)
    assert margin > 20.0, (e0, margin)
    e0, margin = alignment_margin(np.roll(sig, 256) + noise, sig, fs2, shift=256)
    assert margin < 0.0, (e0, margin)


if __name__ == "__main__":
    self_check()
    print("programme.py self-check passed")

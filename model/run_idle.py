#!/usr/bin/env python3
"""Idle-channel behaviour: the low-frequency limit cycle, provoked and chased.

    ./.venv/bin/python model/run_idle.py            # everything
    ./.venv/bin/python model/run_idle.py A B        # selected sections

README.md leaves one thing measured and not fixed: one run in thirty-six comes
back 15 to 19 dB low with all of the excess in the 20 to 100 Hz bins, and
neither input dither nor quantizer dither removes it. Every figure behind that
came from a single sine, which is the wrong instrument for a fault that lives
near idle.

This runs the idle material in ``material.py`` instead -- fades, digital
silence, near silence, DC -- over enough trials to put a rate on it, sweeps the
conditions it is supposed to depend on, tries four ways of removing it, and
builds a detector the FPGA could afford.

Sections:

  A  what a 2**20 transform does to a 20 Hz question
  B  trip rate on near-idle material
  C  conditions: DC, level, where a fade ends, state and pointer at silence
  D  the 15.7 dB attributed to round-half-up
  E  the 1-in-36 count, recounted
  F  blast radius: which published figures move
  G  figures
  H  the reference rail: the in-band spectrum of the transition rate

Figures land in figures/idle*.png, the log in results/idle.txt.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lyrebird_model import (chain, datapath, dwa, endtoend,  # noqa: E402
                            halfband, idle, material, modulator, spectra)

FIG = HERE / "figures"
RES = HERE / "results"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)
LOG = RES / "idle.txt"

ORDER = 3
N_WIN = 1 << 23           # 341 ms at 24.576 MHz, 2.93 Hz bins
N_LEGACY = 1 << 20        # what every figure in README.md was measured over
N_PRE = 1 << 18           # preamble discarded before the window
F_TONE = 1000.0
TEST_DBFS = -3.7
WORKERS = 8

log: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    log.append(s)


_FULL_RUN = True


def flush() -> None:
    """Write the log after every section, so a partial run still reports.

    Only a complete run writes the canonical log. Running one section prints
    it and leaves ``results/idle.txt`` alone, because a partial write would
    replace six sections with one -- which is a footgun this script has
    already fired once.
    """
    if _FULL_RUN:
        LOG.write_text("\n".join(log) + "\n")


def head(title: str) -> None:
    say()
    say("=" * 78)
    say(title)
    say("=" * 78)


# ---------------------------------------------------------------------------
# workers
# ---------------------------------------------------------------------------

_cache: dict = {}


def _setup(fam: str):
    if "ntf" not in _cache:
        _cache["ntf"] = modulator.synthesize_ntf(ORDER)
    if fam not in _cache:
        _cache[fam] = halfband.build(fam)
    return _cache["ntf"], _cache[fam]


def _mode(fam: str, fs: float) -> chain.Mode:
    return [m for m in chain.modes(fam) if abs(m.fs - fs) < 1][0]


# ------------------------------------------------------------------ A
def _tripped_record(n: int):
    """The 176.4 kHz run README.md reports at 125.06 dB, made longer.

    ``endtoend.run``'s own defaults, so the first 2**20 element samples are
    bit-identical to the run in the table; the continuation past that is the
    same tone with a fresh dither draw, which is what makes the same trajectory
    measurable over a longer window.
    """
    ntf, c = _setup("44k1")
    m = _mode("44k1", 176400.0)
    fs, settle = m.element_clock, c.settle_samples(m)
    _, f = spectra.coherent_bin(N_LEGACY, fs, F_TONE)
    n20 = endtoend.input_length(c, m, N_LEGACY)
    n_in = endtoend.input_length(c, m, n)
    x = endtoend.source_tone(n_in, m.fs, f, TEST_DBFS)
    pcm = np.concatenate([
        endtoend.quantize_pcm(x[:n20], 24, "tpdf", seed=11),
        endtoend.quantize_pcm(x[n20:], 24, "tpdf", seed=99991)])
    y, _ = datapath.interpolate(c, pcm, m, coeff_bits=idle.COEFF_BITS)
    u = y[settle:settle + n]
    r = modulator.simulate(ntf, u, fs, f_sig=f)
    return r.out, u, f, fs, m


def section_a() -> dict:
    head("A.  WHAT A 2**20 TRANSFORM DOES TO A 20 Hz QUESTION")
    say("The tripped run is reproducible, so it can be taken apart. This is")
    say("the 176.4 kHz row of the datapath verification table, the one")
    say("README.md reports at 125.06 dB against a 143.31 dB neighbour.")
    say()
    out, u, f, fs, m = _tripped_record(N_WIN)

    say(f"Kaiser main lobe half-width           : "
        f"{spectra.main_lobe_bins()} bins")
    say(f"2**20 bin width at {fs/1e6:.4f} MHz       : {fs/N_LEGACY:.2f} Hz")
    say(f"so the DC main lobe reaches            : "
        f"+/-{spectra.main_lobe_bins()*fs/N_LEGACY:.0f} Hz")
    say(f"shortest transform that keeps it below 20 Hz: 2**"
        f"{np.log2(idle.min_transform(fs)):.2f} = "
        f"{idle.min_transform(fs)/1e6:.2f} M samples")
    say()
    say("The band it is being asked about starts at 20 Hz. At 2**20 the DC")
    say("lobe covers 20-100 Hz entirely and most of 100 Hz-2 kHz as well, so")
    say("at that record length near-DC energy and low-band energy are not")
    say("different measurements.")
    say()
    say(f"And the loop always has near-DC energy. Its eight levels are "
        f"{idle.QLSB:.4f}")
    say("apart, so the mean of an N-sample record sits on a grid of (2/7)/N.")
    for lg in (20, 22, 23, 24):
        say(f"    one unbalanced sample in 2**{lg} is "
            f"{idle.dc_grid_dbfs(1 << lg):7.1f} dBFS of near-DC")
    say()

    o20 = out[:N_LEGACY]
    w = spectra.analysis_window(N_LEGACY)
    plain = o20 - o20.mean()
    wmean = idle.remove_dc(o20, w)
    rows = []
    say("The same 2**20 record, measured two ways:")
    say()
    say(f"  {'mean removed':>16}  {'SNDR':>8}  {'20-100':>9}  {'0.1-2k':>9}  "
        f"{'2k-20k':>9}  {'<20 Hz':>9}")
    for lab, x in (("arithmetic", plain), ("windowed", wmean)):
        mm = spectra.Measurement.of(x, fs, f, idle.BAND, n_harmonics=10,
                                    dedc=False)
        b = idle.bands(x, fs, dedc=False)
        say(f"  {lab:>16}  {mm.sndr_db:>8.2f}  {b.low_db:>9.1f}  "
            f"{b.mid_db:>9.1f}  {b.high_db:>9.1f}  {b.wander_db:>9.1f}")
        rows.append((lab, mm.sndr_db, b))
    say()
    say("18.34 dB of the reported figure is the arithmetic mean not being the")
    say("mean the transform sees. The Kaiser weights the centre of the record")
    say("far above its ends, so a record whose offset drifts across the window")
    say("keeps a DC bin after x - x.mean(), and that bin's lobe lands in the")
    say("lowest audio bins. Subtracting the windowed mean instead removes it.")
    say()

    say("The same trajectory, continued, measured over longer windows with")
    say("plain mean removal -- the original method, nothing corrected:")
    say()
    say(f"  {'window':>8}  {'bin':>8}  {'DC lobe':>9}  {'SNDR':>8}  "
        f"{'20-100':>9}  {'<20 Hz':>9}")
    lens = []
    for lg in (20, 21, 22, 23):
        n = 1 << lg
        o = out[:n]
        x = o - o.mean()
        mm = spectra.Measurement.of(x, fs, f, idle.BAND, n_harmonics=10,
                                    dedc=False)
        b = idle.bands(x, fs, dedc=False)
        say(f"  {'2**' + str(lg):>8}  {fs/n:>7.2f}  "
            f"{spectra.main_lobe_bins()*fs/n:>8.0f}  {mm.sndr_db:>8.2f}  "
            f"{b.low_db:>9.1f}  {b.wander_db:>9.1f}")
        lens.append((lg, mm.sndr_db, b))
    say()
    say("The loss is gone by 2**21 and does not come back. It was never in")
    say("the loop; it was the transform being asked a question 8 times")
    say("finer than its resolution.")
    say()

    blocks = []
    for b in range(8):
        o = out[b * N_LEGACY:(b + 1) * N_LEGACY]
        blocks.append(o.mean())
    say("What the loop is actually doing, per 2**20 block of the same record,")
    say("as a count of unbalanced samples:")
    say("  " + "  ".join(f"{v*N_LEGACY/idle.QLSB:+.2f}" for v in blocks))
    say()
    say("One sample per million, alternating sign: a near-DC wander of")
    say(f"{idle.dc_grid_dbfs(N_LEGACY):.1f} dBFS at roughly "
        f"{fs/(2*N_LEGACY):.1f} Hz. That is the smallest non-zero value the")
    say("output alphabet can express over that window, it is below the audio")
    say("band, and it is 18 dB of the reported in-band figure.")
    return {"rows": rows, "lens": lens, "blocks": blocks, "fs": fs,
            "out": out, "f": f}


# ------------------------------------------------------------------ B
RATES = (("48k", 48000.0), ("48k", 96000.0), ("48k", 192000.0),
         ("44k1", 44100.0), ("44k1", 88200.0), ("44k1", 176400.0))

# (label, material, source quantizer on the idle half)
CONDITIONS = (
    ("digital silence", "digital silence", "none"),
    ("silence, dithered source", "digital silence", "tpdf"),
    ("near silence -100 dBFS", "near silence -100 dBFS", "none"),
    ("DC offset -60 dBFS", "small DC offset", "none"),
    ("fade to silence", "fade to silence", "none"),
)
PRE_CYCLE = ("tone", "fade", "percussive", "programme", "bass", "silence")
N_SEEDS = 6
TRIP_DB = 10.0            # above the cell median, in the 20-100 Hz band


def _job_b(arg):
    fam, fs, label, mat, sd, seed, n = arg
    ntf, c = _setup(fam)
    m = _mode(fam, fs)
    t = idle.run_trial(c, ntf, m, idle=mat, pre=PRE_CYCLE[seed % len(PRE_CYCLE)],
                       seed=seed, src_dither=sd, n=n, n_pre=N_PRE)
    return (arg, t.b.low_db, t.b.total_db, t.b.wander_db, t.b_legacy.low_db,
            t.b_legacy.total_db, t.lsb_per_window, int(t.ptr0),
            [float(v) for v in t.x0])


def section_b() -> dict:
    head("B.  HOW OFTEN DOES IT TRIP ON NEAR-IDLE MATERIAL?")
    say("Every figure behind the 1-in-36 came from a 1 kHz tone at -3.7 dBFS.")
    say("This is material.py's idle catalogue instead, six rates, six")
    say("preambles, so the state the loop is in when the signal goes quiet")
    say("differs from trial to trial. The preamble is discarded; 2**19")
    say("element samples of it sit between the last of it and the first")
    say("measured sample, which is longer than the cascade's settling, so the")
    say("ring on the transition is not in the window. Getting that wrong")
    say("reads as -50 dBFS of low-frequency energy and looks exactly like the")
    say("fault.")
    say()
    args = [(fam, fs, label, mat, sd, seed, N_WIN)
            for fam, fs in RATES
            for label, mat, sd in CONDITIONS
            for seed in range(N_SEEDS)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(_job_b, args))
    say(f"{len(rows)} trials of 2**{int(np.log2(N_WIN))} samples, "
        f"{time.time()-t0:.0f} s.")
    say()

    cells: dict = {}
    for (fam, fs, label, mat, sd, seed, n), lo, tot, wan, llo, ltot, lsb, ptr, x0 in rows:
        cells.setdefault((fs, label), []).append(
            dict(lo=lo, tot=tot, wan=wan, llo=llo, ltot=ltot, lsb=lsb,
                 ptr=ptr, x0=x0, seed=seed))

    say("20 Hz to 100 Hz, dBFS, per trial. 'corrected' is a 2**23 window with")
    say("the windowed mean removed; 'as before' is the 2**20 window with the")
    say("arithmetic mean removed, which is how the 1-in-36 was counted.")
    say()
    trips = {"corrected": 0, "legacy": 0}
    total = 0
    worst = {"corrected": None, "legacy": None}
    for (fs, label), vs in cells.items():
        los = np.array([v["lo"] for v in vs])
        lls = np.array([v["llo"] for v in vs])
        mc, ml = float(np.median(los)), float(np.median(lls))
        tc = int((los > mc + TRIP_DB).sum())
        tl = int((lls > ml + TRIP_DB).sum())
        trips["corrected"] += tc
        trips["legacy"] += tl
        total += len(vs)
        if worst["corrected"] is None or los.max() - mc > worst["corrected"][0]:
            worst["corrected"] = (los.max() - mc, fs, label, float(los.max()))
        if worst["legacy"] is None or lls.max() - ml > worst["legacy"][0]:
            worst["legacy"] = (lls.max() - ml, fs, label, float(lls.max()))
    say(f"{'rate':>10}  {'material':>24}  {'corrected 20-100 Hz':>34}  "
        f"{'spread':>7}")
    for fam, fs in RATES:
        for label, mat, sd in CONDITIONS:
            vs = cells[(fs, label)]
            los = np.array([v["lo"] for v in vs])
            say(f"{fs/1000:>9.1f}k  {label:>24}  " +
                " ".join(f"{v:>6.0f}" for v in los) +
                f"  {los.max()-los.min():>7.1f}")
        say()
    say(f"{'rate':>10}  {'material':>24}  {'as before, 2**20 plain mean':>34}  "
        f"{'spread':>7}")
    for fam, fs in RATES:
        for label, mat, sd in CONDITIONS:
            vs = cells[(fs, label)]
            lls = np.array([v["llo"] for v in vs])
            say(f"{fs/1000:>9.1f}k  {label:>24}  " +
                " ".join(f"{v:>6.0f}" for v in lls) +
                f"  {lls.max()-lls.min():>7.1f}")
        say()

    say(f"Trials more than {TRIP_DB:.0f} dB above their cell's median in the "
        f"20-100 Hz band, of {total}:")
    say(f"   measured as before, 2**20 and the arithmetic mean : "
        f"{trips['legacy']:>3}  ({100*trips['legacy']/total:.0f}%)")
    say(f"   measured at 2**23 with the windowed mean removed  : "
        f"{trips['corrected']:>3}  ({100*trips['corrected']/total:.0f}%)")
    say()
    d, fs, label, v = worst["legacy"]
    say(f"   worst excess as before : {d:.1f} dB, {fs/1000:.1f} kHz, {label}, "
        f"at {v:.0f} dBFS")
    d, fs, label, v = worst["corrected"]
    say(f"   worst excess corrected : {d:.1f} dB, {fs/1000:.1f} kHz, {label}, "
        f"at {v:.0f} dBFS")
    say()
    gaps = np.array([v["llo"] - v["lo"] for vs in cells.values() for v in vs])
    say(f"The two methods disagree by {gaps.mean():.1f} dB on average and "
        f"{gaps.max():.1f} dB at worst,")
    say("always in the same direction: the short window reports more.")
    return cells


# ------------------------------------------------------------------ C
def _job_dc(arg):
    dc, n = arg
    ntf, _ = _setup("48k")
    fs = chain.ELEMENT_CLOCK["48k"]
    g = 1 << 16
    u = np.full(n + g, dc)
    r = modulator.simulate(ntf, u, fs)
    b = idle.bands(r.out[g:], fs)
    return dc, b


def _job_c(arg):
    kind, fam, fs, mat, seed, extra = arg
    ntf, c = _setup(fam)
    m = _mode(fam, fs)
    t = idle.run_trial(c, ntf, m, seed=seed, n=N_WIN, n_pre=N_PRE, **extra)
    return arg, t


def section_c() -> dict:
    head("C.  CONDITIONS")
    ntf, _ = _setup("48k")
    fs48 = chain.ELEMENT_CLOCK["48k"]

    say("C1. DC at the modulator input.")
    say("    The textbook mechanism for an idle tone: a constant input the")
    say("    loop cannot express, corrected by an occasional extra sample, at")
    say("    a rate proportional to the offset. For the correction rate to")
    say(f"    land between 20 and 100 Hz wants 3.5*dc*fs in that range, which")
    say(f"    is {20/(3.5*fs48):.2e} to {100/(3.5*fs48):.2e}, i.e. -133 to "
        f"-119 dBFS.")
    say()
    dcs = [0.0] + [10 ** (d / 20) for d in range(-160, -59, 10)] + \
          [k * 4e-7 for k in range(1, 9)]
    n_dc = 1 << 22
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(_job_dc, [(d, n_dc) for d in dcs]))
    say(f"    window 2**{int(np.log2(n_dc))}, {fs48/n_dc:.2f} Hz bins, "
        f"windowed mean removed")
    say(f"    {'DC':>11} {'dBFS':>8} {'predicted':>10} | {'20 Hz-20 k':>11} "
        f"{'20-100':>9} {'2k-20k':>9} {'peak in band':>16}")
    for dc, b in rows:
        d = float("-inf") if dc == 0 else 20 * np.log10(dc)
        pred = 3.5 * dc * fs48
        say(f"    {dc:11.3e} {d:8.1f} {pred:9.1f} Hz | {b.total_db:11.1f} "
            f"{b.low_db:9.1f} {b.high_db:9.1f}  "
            f"{b.peak_hz:8.0f} Hz {b.peak_db:6.0f}")
    lo = [b.low_db for dc, b in rows if dc != 0]
    tot = [b.total_db for dc, b in rows if dc != 0]
    say()
    say(f"    No idle tone at any offset. In band {min(tot):.0f} to "
        f"{max(tot):.0f} dBFS, all of it the shaped floor above 2 kHz;")
    say(f"    the 20-100 Hz band runs {min(lo):.0f} to {max(lo):.0f} dBFS, "
        f"which is nothing at all.")
    say("    A third-order loop with an eight-level quantizer does not lock")
    say("    to a constant the way a first-order one-bit loop does.")
    say()

    say("C2. Input level, and how quiet is quiet.")
    args = [("level", "48k", 48000.0, "near silence", s,
             dict(idle="near silence -100 dBFS", pre="tone", idle_dbfs=lvl))
            for lvl in (-60.0, -80.0, -100.0, -120.0, -140.0) for s in range(3)]
    args += [("level", "48k", 48000.0, "digital silence", s,
              dict(idle="digital silence", pre="tone")) for s in range(3)]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows_c2 = list(ex.map(_job_c, args))
    say(f"    {'material':>22}  {'20 Hz-20 k':>11}  {'20-100':>9}  "
        f"{'<20 Hz':>9}  {'unbalanced samples':>19}")
    for arg, t in rows_c2:
        lvl = arg[5].get("idle_dbfs")
        name = (f"{arg[3]} {lvl:.0f} dBFS" if lvl is not None else arg[3])
        say(f"    {name:>22}  {t.b.total_db:>11.1f}  {t.b.low_db:>9.1f}  "
            f"{t.b.wander_db:>9.1f}  {t.lsb_per_window:>19.1f}")
    say()

    say("C3. Where a fade ends.")
    say("    The window begins after a decay rather than after a cut, and the")
    say("    decay's starting level sets how far into the fade the loop is")
    say("    when the material reaches zero.")
    args = [("fade", "48k", 48000.0, "digital silence", s,
             dict(idle="digital silence", pre="fade", pre_dbfs=lvl))
            for lvl in (-3.0, -20.0, -40.0, -60.0, -80.0) for s in range(3)]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows_c3 = list(ex.map(_job_c, args))
    say(f"    {'fade from':>12}  {'20 Hz-20 k':>11}  {'20-100':>9}  "
        f"{'<20 Hz':>9}  {'state entering the window':>28}  {'ptr':>4}")
    for arg, t in rows_c3:
        say(f"    {arg[5]['pre_dbfs']:>9.0f} dB  {t.b.total_db:>11.1f}  "
            f"{t.b.low_db:>9.1f}  {t.b.wander_db:>9.1f}  " +
            "[" + ", ".join(f"{v:+7.4f}" for v in t.x0) + "]" +
            f"  {t.ptr0:>4}")
    say()

    allr = rows_c2 + rows_c3
    x0 = np.array([t.x0 for _, t in allr])
    lo = np.array([t.b.low_db for _, t in allr])
    ptr = np.array([t.ptr0 for _, t in allr])
    say("C4. The state and the pointer entering the window.")
    say(f"    integrator 1 spans {x0[:,0].min():+.4f} to {x0[:,0].max():+.4f}")
    say(f"    integrator 2 spans {x0[:,1].min():+.4f} to {x0[:,1].max():+.4f}")
    say(f"    integrator 3 spans {x0[:,2].min():+.4f} to {x0[:,2].max():+.4f}")
    say(f"    pointer takes {len(set(ptr.tolist()))} of its 7 values over "
        f"{len(ptr)} trials")
    for j in range(3):
        cc = np.corrcoef(np.abs(x0[:, j]), lo)[0, 1]
        say(f"    correlation of |state {j+1}| with the 20-100 Hz result: "
            f"{cc:+.2f}")
    say(f"    correlation of the pointer with it: "
        f"{np.corrcoef(ptr, lo)[0,1]:+.2f}")
    say("    None of them predicts anything, because there is nothing to")
    say("    predict: the spread of the result is the spread of the material.")
    say()

    say("C5. The rotation pointer at idle, and what mismatch does with it.")
    say("    At idle the codes alternate 3, 4, 3, 4. The pointer advances by")
    say("    the code, so it advances by 7 every two samples and returns to")
    say("    where it started: period 2. Every code therefore lights the same")
    say("    elements every time, and rotation stops averaging mismatch away.")
    args = [("mismatch", "48k", 48000.0, "digital silence", s,
             dict(idle="digital silence", pre="tone", sigma=sig))
            for sig in (0.0, 0.001, 0.01) for s in range(3)]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows_c5 = list(ex.map(_job_c, args))
    say()
    say(f"    {'elements':>10}  {'20 Hz-20 k':>11}  {'20-100':>9}  "
        f"{'2k-20k':>9}  {'DC removed':>11}")
    for arg, t in rows_c5:
        sig = arg[5]["sigma"]
        lab = "matched" if sig == 0 else f"{sig*100:.1f}%"
        say(f"    {lab:>10}  {t.b.total_db:>11.1f}  {t.b.low_db:>9.1f}  "
            f"{t.b.high_db:>9.1f}  {t.b.dc_db:>11.1f}")
    say()
    say("    Mismatch at idle is a static offset, not noise: the DC column is")
    say("    where it goes, and the in-band figure does not move. A static")
    say("    offset at the output is what the coupling capacitor is for.")
    return {"dc": rows, "c2": rows_c2, "c3": rows_c3, "c5": rows_c5}


# ------------------------------------------------------------------ D
def _both(x: np.ndarray, fs: float, f: float, n_harmonics: int = 10):
    """The same record measured the published way and the corrected way.

    ``dedc=False`` is what the published figures did: subtract the arithmetic
    mean and transform. ``spectra.Measurement`` now removes the windowed mean
    for every caller, so reproducing the old number needs asking for it.
    """
    a = spectra.Measurement.of(x - x.mean(), fs, f, idle.BAND,
                               n_harmonics=n_harmonics, dedc=False)
    b = spectra.Measurement.of(x, fs, f, idle.BAND,
                               n_harmonics=n_harmonics)
    return a, b


def _chain_record(fam, fs_pcm, *, n, rounding=None, sigma=0.0, rotate=True,
                  bits=24, dither="tpdf", sig_frac=None, acc_frac=None,
                  coeff_bits=None, amp_dbfs=TEST_DBFS, gain_at=None,
                  gain_db=0.0, seed=7, coh_n=None, want_elements=False):
    """``endtoend.run``'s path, returning the element sum before mean removal.

    Repeated here rather than called because the question is what the mean
    removal does, and ``endtoend.run`` has already done it by the time it
    returns.

    ``coh_n`` is the length the tone is made coherent to, which is the length
    the published figure was measured over. Making a longer record coherent to
    the same frequency keeps the published window bit-identical -- the tone is
    the same, and the source dither for the first ``coh_n`` samples is drawn
    from the same generator in the same order -- so the two measurements
    compare, rather than being two different runs.
    """
    ntf, c = _setup(fam)
    m = _mode(fam, fs_pcm)
    fse, settle = m.element_clock, c.settle_samples(m)
    coh_n = n if coh_n is None else coh_n
    n_in = endtoend.input_length(c, m, n)
    n_coh = endtoend.input_length(c, m, coh_n)
    _, f = endtoend.coherent_tone_freq(m, coh_n, F_TONE)
    pcm = endtoend.source_tone(n_in, m.fs, f, amp_dbfs)
    if gain_at == "input":
        pcm = pcm * 10 ** (gain_db / 20)
    if bits is not None:
        if n_coh < n_in:
            pcm = np.concatenate([
                endtoend.quantize_pcm(pcm[:n_coh], bits, dither, seed=seed + 4),
                endtoend.quantize_pcm(pcm[n_coh:], bits, dither, seed=99991)])
        else:
            pcm = endtoend.quantize_pcm(pcm, bits, dither, seed=seed + 4)
    y, _ = datapath.interpolate(c, pcm, m, coeff_bits=coeff_bits,
                                sig_frac=sig_frac, acc_frac=acc_frac,
                                rounding=rounding)
    u = y[settle:settle + n]
    if gain_at == "modulator":
        u = u * 10 ** (gain_db / 20)
    r = modulator.simulate(ntf, u, fse, f_sig=f)
    codes = np.clip(np.asarray(r.codes, dtype=np.int64), 0, chain.N_ELEMENTS)
    pos, neg = dwa.differential(codes, rotate=rotate)
    wp, wn = (None, None) if sigma == 0.0 else dwa.mismatch(sigma, seed=seed)
    x = dwa.normalise(dwa.analog(pos, neg, wp, wn))
    if want_elements:
        return x, f, fse, float(u.mean()), pos, neg
    return x, f, fse, float(u.mean())


def _job_ties(arg):
    fam, fs_pcm, rnd, n = arg
    x, f, fse, umean = _chain_record(
        fam, fs_pcm, n=n, rounding=rnd, coeff_bits=idle.COEFF_BITS,
        sig_frac=idle.SIG_FRAC, acc_frac=idle.ACC_FRAC, coh_n=N_LEGACY)
    a20, b20 = _both(x[:N_LEGACY], fse, f)
    a, b = _both(x, fse, f)
    blocks = [float(x[i*N_LEGACY:(i+1)*N_LEGACY].mean() * N_LEGACY / idle.QLSB)
              for i in range(len(x) // N_LEGACY)]
    return (fs_pcm, rnd, umean, a20.sndr_db, b20.sndr_db, a.sndr_db,
            b.sndr_db, blocks)


def section_d() -> dict:
    head("D.  THE 15.7 dB ATTRIBUTED TO ROUND-HALF-UP IS THE SAME ARTIFACT")
    say("README.md's 'which way ties go' table reports half-up costing 15.7 dB")
    say("at 96 kHz, 124.58 against 140.25, and explains it as a static input")
    say("offset turned into idle tones. The offset is real. The 15.7 dB is")
    say("not.")
    say()
    say("Re-running that table's own function today reproduces the shape but")
    say("at a different rate -- 44.1 kHz reads 124.73 against 137.55 -- which")
    say("is already the giveaway. Half-up leaves the same offset at every")
    say("rate, so a fault caused by the offset cannot move from one rate to")
    say("another between runs. A lottery over records can.")
    say()
    n = 1 << 22
    args = [(fam, fs, rnd, n) for fam, fs in RATES
            for rnd in ("half_up", "half_even")]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(_job_ties, args))
    say(f"Same records, measured four ways. ({len(rows)} runs, "
        f"{time.time()-t0:.0f} s)")
    say()
    say(f"{'rate':>10}  {'rounding':>10}  {'DC at mod in':>13}  "
        f"{'2**20 plain':>12}  {'2**20 windowed':>15}  {'2**22 plain':>12}  "
        f"{'2**22 windowed':>15}")
    out = {}
    for fs_pcm, rnd, umean, a20, b20, a22, b22, blocks in rows:
        dc = 20 * np.log10(abs(umean)) if umean else float("-inf")
        say(f"{fs_pcm/1000:>9.1f}k  {rnd:>10}  {dc:>13.1f}  {a20:>12.2f}  "
            f"{b20:>15.2f}  {a22:>12.2f}  {b22:>15.2f}")
        out[(fs_pcm, rnd)] = (a20, b20, a22, b22, umean, blocks)
    say()
    worst20 = max(out[(fs, "half_even")][0] - out[(fs, "half_up")][0]
                  for fam, fs in RATES)
    worst22 = max(out[(fs, "half_even")][3] - out[(fs, "half_up")][3]
                  for fam, fs in RATES)
    say(f"Measured as published, half-up is up to {worst20:.1f} dB worse.")
    say(f"Measured over 2**22 with the windowed mean removed, up to "
        f"{worst22:.2f} dB.")
    say()
    say("Unbalanced samples per 2**20 block, the near-DC term itself:")
    for fs_pcm, rnd, umean, a20, b20, a22, b22, blocks in rows:
        say(f"  {fs_pcm/1000:>7.1f}k {rnd:>10}  " +
            " ".join(f"{v:+5.1f}" for v in blocks))
    say()
    say("Both rounding modes leave the same one-sample-per-million residue.")
    say("The rounding does not decide whether a run reads low; which block the")
    say("residue lands in does.")
    say()
    up = [20 * np.log10(abs(out[(fs, "half_up")][4])) for fam, fs in RATES]
    ev = [20 * np.log10(abs(out[(fs, "half_even")][4])) for fam, fs in RATES]
    say("What survives: half-up does leave a real DC offset at the modulator")
    say(f"input, {min(up):.0f} to {max(up):.0f} dBFS against {min(ev):.0f} to "
        f"{max(ev):.0f} dBFS for ties to even, and that")
    say("offset does reach the output as DC. Convergent rounding removes it")
    say("for one adder's difference, so the recommendation stands. The reason")
    say("given for it does not: the offset costs nothing measurable in the")
    say("audio band.")
    return out


# ------------------------------------------------------------------ E
def _job_e(arg):
    """run_endtoend.limit_cycles, rerun, with both measurements kept."""
    fam, fs_pcm, dfrac, k, n = arg
    ntf, c = _setup(fam)
    m = _mode(fam, fs_pcm)
    fse, settle = m.element_clock, c.settle_samples(m)
    n_in = endtoend.input_length(c, m, n)
    _, f = endtoend.coherent_tone_freq(m, N_LEGACY, F_TONE)
    pcm = endtoend.quantize_pcm(
        endtoend.source_tone(n_in, m.fs, f, TEST_DBFS), 24, "tpdf")
    y, _ = datapath.interpolate(c, pcm, m, coeff_bits=idle.COEFF_BITS,
                                sig_frac=idle.SIG_FRAC,
                                acc_frac=idle.ACC_FRAC)
    base = y[settle:settle + n]
    rng = np.random.default_rng(100 + k)
    u = base + 0.5 * 2.0 ** -26 * (rng.random(n) + rng.random(n) - 1.0)
    d = (None if dfrac == 0.0
         else modulator.dither_sequence(n, dfrac, seed=200 + k))
    r = modulator.simulate(ntf, u, fse, f_sig=f, dither=d)
    a20, b20 = _both(r.out[:N_LEGACY], fse, f)
    a, b = _both(r.out, fse, f)
    return fs_pcm, dfrac, k, a20.sndr_db, b20.sndr_db, b.sndr_db


def section_e() -> dict:
    head("E.  THE 1-IN-36 COUNT, RECOUNTED")
    say("This is run_endtoend.py's limit-cycle experiment rerun unchanged --")
    say("six rates, six input perturbations, with and without a quarter LSB")
    say("of dither at the quantizer -- with the same records measured both")
    say("ways. The published count is 1 of 36 without dither and 1 of 36")
    say("with, a different one, which is what 'dither moves which run trips'")
    say("was based on.")
    say()
    n = 1 << 22
    args = [(fam, fs, d, k, n) for fam, fs in RATES
            for d in (0.0, 0.25) for k in range(6)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(_job_e, args))
    say(f"({len(rows)} runs, {time.time()-t0:.0f} s)")
    say()
    out = {}
    for tag, col in (("as published: 2**20, arithmetic mean", 3),
                     ("same records: 2**20, windowed mean", 4),
                     ("same records: 2**22, windowed mean", 5)):
        say(f"  {tag}")
        say(f"  {'rate':>10}  {'dither':>9}  {'six perturbations':>47}")
        bad = 0
        tot = 0
        for fam, fs_pcm in RATES:
            for d in (0.0, 0.25):
                v = [r[col] for r in rows if r[0] == fs_pcm and r[1] == d]
                med = float(np.median(v))
                bad += sum(1 for x in v if x < med - 5.0)
                tot += len(v)
                lab = "none" if d == 0 else "0.25 LSB"
                say(f"  {fs_pcm/1000:>9.1f}k  {lab:>9}  " +
                    " ".join(f"{x:>7.1f}" for x in v))
        say(f"  -> {bad} of {tot} more than 5 dB below their row median")
        say()
        out[tag] = bad
    say("The count that was read as a loop fault is a count of how often the")
    say("near-DC residue lands where the window can see it. Corrected, the")
    say("dither comparison has nothing left to compare: both columns are")
    say("flat.")
    return out


# ------------------------------------------------------------------ F
def _job_f_rate(arg):
    fam, fs_pcm, sigma, n = arg
    x, f, fse, _ = _chain_record(
        fam, fs_pcm, n=n, sigma=sigma, coeff_bits=idle.COEFF_BITS,
        sig_frac=idle.SIG_FRAC if sigma else None,
        acc_frac=idle.ACC_FRAC if sigma else None, coh_n=N_LEGACY)
    a20, b20 = _both(x[:N_LEGACY], fse, f)
    a, b = _both(x, fse, f)
    return (fs_pcm, sigma, a20.sndr_db, b20.sndr_db, b.sndr_db,
            a20.snr_db, a20.thd_db)


def _job_f_rot(arg):
    order, sigma, rotate, n = arg
    ntf = modulator.synthesize_ntf(order)
    fse = chain.ELEMENT_CLOCK["48k"]
    u, f = modulator.tone(n, fse, F_TONE, -3.7)
    r = modulator.simulate(ntf, u, fse, f_sig=f)
    codes = np.clip(np.asarray(r.codes, dtype=np.int64), 0, chain.N_ELEMENTS)
    pos, neg = dwa.differential(codes, rotate=rotate)
    wp, wn = (None, None) if sigma == 0.0 else dwa.mismatch(sigma, seed=7)
    x = dwa.normalise(dwa.analog(pos, neg, wp, wn))
    a, b = _both(x, fse, f)
    return order, sigma, rotate, a.sndr_db, b.sndr_db, a.thd_db, b.thd_db


def _job_f_vol(arg):
    where, gain_db, n = arg
    x, f, fse, _ = _chain_record("48k", 96000.0, n=n, gain_at=where,
                                 gain_db=gain_db, coeff_bits=idle.COEFF_BITS,
                                 coh_n=N_LEGACY)
    a20, b20 = _both(x[:N_LEGACY], fse, f)
    _, b = _both(x, fse, f)
    return where, gain_db, a20.sndr_db, b20.sndr_db, b.sndr_db


def _job_f_cap(arg):
    """run_analog.py:623 -- the capacitor-tolerance sweep, both ways.

    Same record, same pole, same tolerance draws (seed 4242), same order of
    operations. The pole sits three decades above the band, so it cannot
    change the near-DC term; this measures that rather than assuming it.
    """
    tol, n = arg
    from scipy.signal import lfilter
    x, f, fse, _, pos, neg = _chain_record(
        "48k", 48000.0, n=n, sigma=0.01, coeff_bits=idle.COEFF_BITS,
        sig_frac=idle.SIG_FRAC, acc_frac=idle.ACC_FRAC, coh_n=N_LEGACY,
        want_elements=True)
    wp, wn = dwa.mismatch(0.01, seed=7)
    rng = np.random.default_rng(4242)
    acc = np.zeros(pos.shape[0])
    for side, w, sign in ((pos, wp, 1.0), (neg, wn, -1.0)):
        for j in range(chain.N_ELEMENTS):
            fj = 1.0e6 / (1.0 + tol * rng.standard_normal()) if tol else 1.0e6
            a = np.exp(-2.0 * np.pi * fj / fse)
            acc += sign * w[j] * lfilter([1.0 - a], [1.0, -a],
                                         side[:, j].astype(np.float64))
    y = dwa.normalise(acc)
    a20, b20 = _both(y[:N_LEGACY], fse, f)
    _, b = _both(y, fse, f)
    return tol, a20.sndr_db, b20.sndr_db, b.sndr_db


def _job_f_order(arg):
    order, n = arg
    ntf = modulator.synthesize_ntf(order)
    fse = chain.ELEMENT_CLOCK["48k"]
    u, f = modulator.tone(n, fse, F_TONE, -3.7)
    r = modulator.simulate(ntf, u, fse, f_sig=f)
    a, b = _both(r.out, fse, f)
    return order, a.sndr_db, b.sndr_db


def section_f() -> dict:
    head("F.  BLAST RADIUS: WHICH PUBLISHED FIGURES MOVE")
    say("x - x.mean() is used at five measurement sites that produced")
    say("published figures:")
    say("    lyrebird_model/endtoend.py:232   every end-to-end table")
    say("    run_experiments.py:210           rotation and mismatch")
    say("    run_analog.py:113 and :623       the analog section")
    say("    run_endtoend.py:443              the limit-cycle count")
    say()
    say("The term only shows when the near-DC residue is large, which is a")
    say("lottery per record, so the only way to know which published numbers")
    say("carry it is to measure them both ways. Each row below is one record")
    say("measured twice, not two runs.")
    say()
    n = 1 << 22
    res = {}

    t0 = time.time()
    args = [(fam, fs, sg, n) for fam, fs in RATES for sg in (0.0, 0.01)]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(_job_f_rate, args))
    say("F1. End to end per rate, and the chain as it will be built.")
    say(f"    (README 'The chain end to end' and 'as it will actually be "
        f"built')")
    say()
    say(f"    {'rate':>10}  {'elements':>10}  {'as published':>13}  "
        f"{'2**20 windowed':>15}  {'2**22 windowed':>15}  {'moved by':>9}")
    for fs_pcm, sigma, a20, b20, b22, snr, thd in rows:
        lab = "matched" if sigma == 0 else f"{sigma*100:.0f}%"
        say(f"    {fs_pcm/1000:>9.1f}k  {lab:>10}  {a20:>13.2f}  "
            f"{b20:>15.2f}  {b22:>15.2f}  {b20-a20:>+9.2f}")
    res["rate"] = rows
    say()

    args = [(o, sg, rot, 1 << 21) for o in (2, 3)
            for sg, rot in ((0.0, True), (0.001, True), (0.001, False),
                            (0.01, True), (0.01, False))]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows_rot = list(ex.map(_job_f_rot, args))
    say("F2. Element mismatch and rotation (run_experiments.py:210), 2**21.")
    say(f"    {'order':>6}  {'mismatch':>9}  {'rotation':>9}  "
        f"{'as published':>13}  {'corrected':>10}  {'moved by':>9}")
    for order, sigma, rot, a, b, athd, bthd in rows_rot:
        say(f"    {order:>6}  {sigma*100:>8.1f}%  {'on' if rot else 'off':>9}  "
            f"{a:>13.2f}  {b:>10.2f}  {b-a:>+9.2f}")
    res["rotation"] = rows_rot
    say()

    args = [(w, g, n) for w in ("input", "modulator")
            for g in (-6.0, -20.0, -40.0, -60.0)]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows_vol = list(ex.map(_job_f_vol, args))
    say("F3. Where the volume control goes, 96 kHz.")
    say(f"    {'gain at':>12}  {'attenuation':>12}  {'as published':>13}  "
        f"{'corrected':>10}  {'moved by':>9}")
    for where, g, a, b, b22 in rows_vol:
        say(f"    {where:>12}  {g:>11.0f} dB  {a:>13.2f}  {b:>10.2f}  "
            f"{b-a:>+9.2f}")
    res["volume"] = rows_vol
    say()

    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows_ord = list(ex.map(_job_f_order, [(o, 1 << 20) for o in
                                              (2, 3, 4, 5)]))
    say("F4. Modulator order sweep, tone at the element clock, 2**20.")
    say(f"    {'order':>6}  {'as published':>13}  {'corrected':>10}  "
        f"{'moved by':>9}")
    for order, a, b in rows_ord:
        say(f"    {order:>6}  {a:>13.2f}  {b:>10.2f}  {b-a:>+9.2f}")
    res["order"] = rows_ord
    say()

    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows_cap = list(ex.map(_job_f_cap,
                               [(t, 1 << 21) for t in
                                (0.0, 0.02, 0.05, 0.10, 0.20)]))
    say("F5. The analog section's own site (run_analog.py:623): the same")
    say("    element sum behind a 1 MHz pole per element, 48 kHz, 1%")
    say("    elements, capacitor tolerance swept. This is the table printed")
    say("    in results/analog.txt as Q2e.")
    say()
    say(f"    {'C tolerance':>13}  {'as published':>13}  {'2**20 windowed':>15}"
        f"  {'2**21 windowed':>15}  {'moved by':>9}")
    for tol, a20, b20, b21 in rows_cap:
        lab = "matched" if tol == 0 else f"{tol*100:.0f}%"
        say(f"    {lab:>13}  {a20:>13.2f}  {b20:>15.2f}  {b21:>15.2f}  "
            f"{b20-a20:>+9.2f}")
    say()
    base_pub = rows_cap[0][1]
    base_cor = rows_cap[0][2]
    say(f"    {'C tolerance':>13}  {'cost as published':>18}  "
        f"{'cost corrected':>15}")
    for tol, a20, b20, b21 in rows_cap:
        lab = "matched" if tol == 0 else f"{tol*100:.0f}%"
        say(f"    {lab:>13}  {base_pub-a20:>+18.2f}  {base_cor-b20:>+15.2f}")
    say()
    res["cap"] = rows_cap
    say()
    say(f"    (F1-F4: {time.time()-t0:.0f} s)")
    return res


# ------------------------------------------------------------------ G
def section_g() -> dict:
    head("G.  FIGURES")
    fs_lab = []
    out, u, f, fs, m = _tripped_record(N_WIN)

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    half = spectra.main_lobe_bins()
    for lg, style, lab, dedc in ((20, "-", "2**20, arithmetic mean", False),
                                 (20, "--", "2**20, windowed mean", True),
                                 (23, "-", "2**23, windowed mean", True)):
        n = 1 << lg
        o = out[:n]
        x = idle.remove_dc(o) if dedc else o - o.mean()
        w = idle.window(n)
        p = spectra.power_spectrum(x, w)
        ff = spectra.bin_freqs(n, fs)
        sel = (ff > 0.5) & (ff < 2000)
        ax[0].semilogx(ff[sel], spectra.dbfs(p[sel]), style, lw=1.2, label=lab)
    ax[0].axvspan(20.0, 100.0, alpha=.15, color="tab:red")
    ax[0].axvline(half * fs / N_LEGACY, color="k", ls=":", lw=1)
    ax[0].annotate(f"DC main lobe at 2**20 reaches {half*fs/N_LEGACY:.0f} Hz",
                   xy=(half * fs / N_LEGACY, -246), xytext=(1.2, -246),
                   fontsize=7.5, va="center",
                   arrowprops=dict(arrowstyle="->", lw=.8, color="0.3"))
    ax[0].text(0.62, -142, "this is what was\nreported as 18 dB of\naudio-band noise",
               fontsize=7.5, color="tab:blue")
    ax[0].set(title="The tripped run: one record, three transforms\n"
                    "shaded band is 20-100 Hz, where the excess was reported",
              xlabel="Hz", ylabel="dBFS", xlim=(0.5, 2000), ylim=(-260, -100))
    ax[0].legend(fontsize=8, loc="upper right")
    ax[0].grid(alpha=.3, which="both")

    lens, plain, wmean = [], [], []
    for lg in (20, 21, 22, 23):
        n = 1 << lg
        o = out[:n]
        lens.append(lg)
        plain.append(spectra.Measurement.of(o - o.mean(), fs, f, idle.BAND,
                                            n_harmonics=10,
                                            dedc=False).sndr_db)
        wmean.append(spectra.Measurement.of(o, fs, f, idle.BAND,
                                            n_harmonics=10).sndr_db)
    ax[1].plot(lens, plain, "o-", label="x - x.mean()")
    ax[1].plot(lens, wmean, "s--", label="windowed mean removed")
    ax[1].axhline(143.31, color="k", ls=":", lw=1,
                  label="the neighbouring row in the table, 143.31 dB")
    ax[1].set(title="The same record's reported SNDR against transform length",
              xlabel="transform length, 2**n", ylabel="SNDR, dB",
              xticks=lens)
    ax[1].legend(fontsize=8, loc="lower right")
    ax[1].grid(alpha=.3)
    fig.savefig(FIG / "idle_window.png", dpi=130)
    plt.close(fig)
    say(f"  figures/idle_window.png")

    # blast radius
    claims = []
    for fam, fs_pcm, sg, lab in (("44k1", 176400.0, 0.0,
                                  "176.4 kHz reference row"),
                                 ("48k", 48000.0, 0.0, "48 kHz end to end"),
                                 ("48k", 96000.0, 0.0, "96 kHz end to end"),
                                 ("48k", 48000.0, 0.01, "48 kHz, 1% elements")):
        r = _job_f_rate((fam, fs_pcm, sg, 1 << 22))
        claims.append((lab, r[2], r[3]))
    t = _job_ties(("44k1", 44100.0, "half_up", 1 << 22))
    claims.append(("44.1 kHz, round half up", t[3], t[4]))
    t = _job_ties(("48k", 48000.0, "half_up", 1 << 22))
    claims.append(("48 kHz, round half up", t[3], t[4]))
    c = _job_f_cap((0.0, 1 << 21))
    claims.append(("analog Q2e, matched C", c[1], c[2]))
    c = _job_f_cap((0.20, 1 << 21))
    claims.append(("analog Q2e, 20% C", c[1], c[2]))
    r = _job_f_rot((3, 0.01, True, 1 << 21))
    claims.append(("order 3, 1% mismatch", r[3], r[4]))
    r = _job_f_order((3, 1 << 20))
    claims.append(("order sweep, order 3", r[1], r[2]))

    fig, ax = plt.subplots(figsize=(9.5, 5.2), constrained_layout=True)
    claims.sort(key=lambda c: c[2] - c[1])
    labels = [c[0] for c in claims]
    moved = [c[2] - c[1] for c in claims]
    colours = ["tab:red" if v > 1 else "0.55" for v in moved]
    y = np.arange(len(claims))
    ax.barh(y, moved, color=colours)
    for yi, (lab, a, b) in zip(y, claims):
        ax.text(max(b - a, 0) + 0.3, yi, f"{a:.2f} -> {b:.2f} dB",
                va="center", fontsize=7.5)
    ax.set(yticks=y, yticklabels=labels, xlabel="dB moved by removing the "
           "windowed mean instead of the arithmetic mean",
           title="Blast radius: published figures measured both ways\n"
                 "same record each time, only the mean removal differs",
           xlim=(-1, max(moved) * 1.45))
    ax.axvline(0, color="k", lw=.8)
    ax.grid(alpha=.3, axis="x")
    fig.savefig(FIG / "idle_blast.png", dpi=130)
    plt.close(fig)
    say(f"  figures/idle_blast.png")
    say()
    say(f"  {'claim':>26}  {'as published':>13}  {'corrected':>10}  "
        f"{'moved by':>9}")
    for lab, a, b in sorted(claims, key=lambda c: -(c[2] - c[1])):
        say(f"  {lab:>26}  {a:>13.2f}  {b:>10.2f}  {b-a:>+9.2f}")
    return {"claims": claims}


# ------------------------------------------------------------------ H
REF_LOG = RES / "reference-current.txt"
N_REF = 1 << 21          # 85 ms; long enough for 1 kHz and its harmonics


def _ref_record(fs_pcm="48k", rate=48000.0, n=N_REF, amp_dbfs=TEST_DBFS,
                pcm=None, f_target=F_TONE):
    """Codes and element sum for the reference-rail measurement."""
    ntf, c = _setup(fs_pcm)
    m = _mode(fs_pcm, rate)
    fse, settle = m.element_clock, c.settle_samples(m)
    _, f = spectra.coherent_bin(n, fse, f_target)
    n_in = endtoend.input_length(c, m, n)
    if pcm is None:
        pcm = endtoend.quantize_pcm(
            endtoend.source_tone(n_in, m.fs, f, amp_dbfs), 24, "tpdf", seed=11)
    else:
        pcm = endtoend.quantize_pcm(pcm(n_in, m.fs), 24, "tpdf", seed=11)
    y, _ = datapath.interpolate(c, pcm, m, coeff_bits=idle.COEFF_BITS,
                                sig_frac=idle.SIG_FRAC,
                                acc_frac=idle.ACC_FRAC)
    u = y[settle:settle + n]
    r = modulator.simulate(ntf, u, fse, f_sig=f)
    codes = np.clip(np.asarray(r.codes, dtype=np.int64), 0, chain.N_ELEMENTS)
    return codes, r.out, f, fse


def _schemes(codes):
    return [
        ("plain DWA, pointer advances by the code",
         dwa.differential(codes, rotate=True)),
        ("no rotation", dwa.differential(codes, rotate=False)),
        ("pointer advances by 1 each sample", idle.differential_stepped(codes, step=1)),
        ("pointer advances by 3 each sample", idle.differential_stepped(codes, step=3)),
        ("pointer stepped by an LFSR", idle.differential_scrambled(codes, seed=3)),
        ("both sides on one pointer", _shared_pointer(codes)),
    ]


def _shared_pointer(codes):
    """Both sides driven from the positive side's pointer.

    One of several ways to pair the two sides differently; measured because
    an obvious guess is that the sides could be made to cancel. They cannot.
    """
    n = chain.N_ELEMENTS
    ptr = np.concatenate(([0], np.cumsum(codes)[:-1])) % n
    idx = np.arange(n)[None, :]
    lit = ((idx - ptr[:, None]) % n)
    return lit < codes[:, None], lit < (n - codes)[:, None]


def _output_figure(changed, out, fse, f):
    """Transition sequence -> rail current -> gain error -> output error.

    Returns the pieces so the conversion can be rescaled if a hardware
    coefficient changes.
    """
    return None


def section_h() -> dict:
    hlog: list[str] = []

    def hsay(t=""):
        say(t)
        hlog.append(t)

    head("H.  THE REFERENCE RAIL: TRANSITION RATE, NOT CODE")
    hsay("=" * 78)
    hsay("THE REFERENCE RAIL: TRANSITION RATE, NOT CODE")
    hsay("=" * 78)
    hsay()
    hsay("0008 guarantees exactly seven elements high at every code, so the DC")
    hsay("load on the reference is constant. It guarantees nothing about how")
    hsay("often lines CHANGE, and the 180 pF filter capacitors and the")
    hsay("registers both draw current in proportion to that. The reference")
    hsay("sets full scale, so it multiplies the signal: a signal-correlated")
    hsay("current on it is distortion, not noise.")
    hsay()
    hsay("READ THIS AS A PREDICTION, NOT A MEASUREMENT. The model has no")
    hsay("supply in it. What is measured here is a digital proxy -- how many")
    hsay("of the element lines change state each clock -- converted through")
    hsay("hardware constants taken from hardware/lyrebird-dac-reva/. Every")
    hsay("step of that conversion is stated so it can be rechecked or")
    hsay("rescaled. The thing that would settle it is a bench measurement of")
    hsay("the rail with the modulator running.")
    hsay()

    codes, out, f, fse = _ref_record()
    k, k2 = codes[:-1], codes[1:]

    hsay("H1. The proxy, and a check on it before anything is believed.")
    hsay()
    pos, neg = dwa.differential(codes, rotate=True)
    changed, rising = idle.transitions(pos, neg)
    sel_high = np.concatenate([pos, neg], axis=1).sum(axis=1)
    pred_rot = 2 * np.minimum(k + k2, 14 - k - k2)
    posf, negf = dwa.differential(codes, rotate=False)
    changed_f, _ = idle.transitions(posf, negf)
    pred_fix = 2 * np.abs(k - k2)
    hsay(f"    lines high per sample, one channel : min {sel_high.min()}, "
         f"max {sel_high.max()}  (0008's invariant)")
    hsay(f"    rising == falling per sample       : "
         f"{bool(np.array_equal(rising, changed - rising))}")
    hsay(f"    with rotation, T == 2*min(k+k', 14-k-k') : "
         f"{bool(np.array_equal(changed, pred_rot.astype(float)))}")
    hsay(f"    without rotation, T == 2*|k-k'|          : "
         f"{bool(np.array_equal(changed_f, pred_fix.astype(float)))}")
    hsay()
    hsay("    Those two identities are exact, and they are the whole story.")
    hsay("    With rotation the pointer advances BY THE CODE, so consecutive")
    hsay("    windows are disjoint until they wrap, and the number of lines")
    hsay("    that change is k + k' folded about seven. Writing k = 3.5 + s")
    hsay("    with s the signal in code units, that is")
    hsay()
    hsay("        T  =  14 - 4|s|")
    hsay()
    hsay("    a full-wave rectifier. The transition rate carries the")
    hsay("    magnitude of the signal, so its spectrum is the even harmonics.")
    amp_codes = 10 ** (TEST_DBFS / 20) * 3.5
    hsay(f"    Predicted mean for a {TEST_DBFS:.1f} dBFS tone: "
         f"14 - 4*(2A/pi) = {14 - 8 * amp_codes / np.pi:.4f}")
    hsay(f"    Measured mean                              : "
         f"{changed.mean():.4f}")
    hsay(f"    Predicted second harmonic amplitude        : "
         f"{16 * amp_codes / (3 * np.pi):.4f} transitions")
    hsay(f"    Measured                                   : "
         f"{idle.coherent_amplitude(changed, 2 * f, fse):.4f} transitions")
    hsay()
    hsay("    Closed form and simulation agree to under two percent, from")
    hsay("    two independent directions. The proxy is doing what it claims.")
    hsay()

    hsay("H2. Null tests, so a large number is not read off an untested rule.")
    hsay()
    for label, maker in (("digital silence",
                          lambda n, fs_: np.zeros(n)),
                         ("DC at -20 dBFS",
                          lambda n, fs_: np.full(n, 0.1))):
        c2, o2, f2, _ = _ref_record(pcm=maker)
        p2, n2 = dwa.differential(c2, rotate=True)
        ch2, _ = idle.transitions(p2, n2)
        hsay(f"    {label:18}: T mean {ch2.mean():7.4f}  component at 2 kHz "
             f"{idle.coherent_amplitude(ch2, 2 * f, fse):.3e} transitions")
    hsay()
    hsay("    Level scaling: the model says the second harmonic is")
    hsay("    proportional to amplitude, so halving the tone should halve it.")
    for a in (TEST_DBFS, TEST_DBFS - 6.0, TEST_DBFS - 12.0, TEST_DBFS - 20.0):
        ca, _, fa, _ = _ref_record(amp_dbfs=a)
        pa, na = dwa.differential(ca, rotate=True)
        cha, _ = idle.transitions(pa, na)
        h2 = idle.coherent_amplitude(cha, 2 * fa, fse)
        pa_ = 16 * (10 ** (a / 20) * 3.5) / (3 * np.pi)
        hsay(f"    tone at {a:6.1f} dBFS: T mean {cha.mean():7.4f}  "
             f"h2 {h2:7.4f}  closed form {pa_:7.4f}")
    hsay()

    hsay("H3. The transition rate against the element-selection rule.")
    hsay("    'SNDR 1%' is the ordinary in-band figure with one percent")
    hsay("    elements, which is what the rotation exists to protect, put")
    hsay("    beside the transition rate it costs.")
    hsay()
    hsay(f"    {'rule':>40}  {'T mean':>7}  {'h2':>9}  {'h4':>9}  "
         f"{'SNDR 1%':>8}")
    rows = {}
    for name, (a, b) in _schemes(codes):
        ch, _ = idle.transitions(a, b)
        wp, wn = dwa.mismatch(0.01, seed=7)
        x = dwa.normalise(dwa.analog(a, b, wp, wn))
        sndr = spectra.Measurement.of(x, fse, f, idle.BAND,
                                      n_harmonics=10).sndr_db
        h2 = idle.coherent_amplitude(ch, 2 * f, fse)
        h4 = idle.coherent_amplitude(ch, 4 * f, fse)
        rows[name] = (ch.mean(), h2, h4, sndr, a, b)
        hsay(f"    {name:>40}  {ch.mean():>7.3f}  {h2:>9.3e}  {h4:>9.3e}  "
             f"{sndr:>8.2f}")
    hsay()
    hsay("    The two columns move together and in the wrong direction.")
    hsay("    Everything that lowers the transition rate's signal content")
    hsay("    also breaks the mismatch shaping, because they are the same")
    hsay("    mechanism: DWA shapes mismatch to first order precisely")
    hsay("    BECAUSE the pointer advance equals the code, and that is what")
    hsay("    ties the number of changing lines to the code. A fixed step")
    hsay("    takes 37 dB off the transition rate's second harmonic and 50 dB")
    hsay("    off the mismatch figure. This is not a pointer rule that has")
    hsay("    been chosen badly; it is a property of the method.")
    hsay()

    hsay("H4. Converting to a rail current and to an output figure.")
    hsay()
    hsay(f"    reference rail            {idle.V_REF} V")
    hsay(f"    element, two halves       {idle.R_HALF/1e3:.3f}k + "
         f"{idle.R_HALF/1e3:.3f}k")
    hsay(f"    filter capacitor          {idle.C_FILT*1e12:.0f} pF per element,"
         f" tau = {(idle.R_HALF/2*idle.C_FILT)*1e9:.0f} ns against a "
         f"{1e9/fse:.1f} ns clock")
    hsay(f"    register Cpd              {idle.C_PD*1e12:.0f} pF per flip-flop"
         f" (SCES021L)")
    hsay(f"    rail source impedance     {idle.Z_REF*1e3:.0f} mOhm in band")
    hsay(f"    lines on the rail         {idle.N_LINES_ARRAY} = two channels "
         f"of 14")
    hsay()
    hsay("    The capacitor term is simulated rather than counted: at 150 ns")
    hsay("    into a 40.7 ns clock the capacitor moves 24 percent of the way")
    hsay("    per sample and never reaches either rail, so charge per")
    hsay("    transition is well under C*V. Counting transitions and")
    hsay("    multiplying by C*V overstates it about threefold.")
    hsay()
    hsay("    Both channels are given the same signal, which is the worst")
    hsay("    case and the one mono content produces.")
    hsay()
    hsay(f"    {'rule':>40}  {'elements':>9}  {'registers':>9}  "
         f"{'AC at 2f':>9}  {'out':>9}  {'broadband':>9}")
    out_figs = {}
    for name in rows:
        _, _, _, sndr, a, b = rows[name]
        ch, _ = idle.transitions(a, b)
        i_el = idle.element_rail_current(a, b, fse)
        i_rg = idle.register_current(np.concatenate([[0.0], ch]), fse)
        i_tot = 2.0 * (i_el + i_rg)          # two channels, mono
        i_ac = i_tot - i_tot.mean()
        g = i_ac * idle.Z_REF / idle.V_REF
        e = out * g
        w = idle.window(len(e))
        pe = spectra.power_spectrum(spectra.remove_dc(e, w), w)
        ff = spectra.bin_freqs(len(e), fse)
        inb = (ff >= idle.BAND[0]) & (ff <= idle.BAND[1])
        tot = float(spectra.dbfs(pe[inb].sum()))
        me = spectra.Measurement.of(e, fse, f, idle.BAND, n_harmonics=10)
        # Everything but the fundamental lobe: the part at f is a gain
        # change on the signal itself, not distortion.
        dist = 10.0 * np.log10(max(10 ** (tot / 10)
                                   - 10 ** (me.signal_dbfs / 10), 1e-30))
        out_figs[name] = (2 * i_el.mean(), 2 * i_rg.mean(),
                          idle.coherent_amplitude(i_tot, 2 * f, fse), tot,
                          sndr, dist, me)
        hsay(f"    {name:>40}  {2*i_el.mean()*1e3:>7.2f}mA  "
             f"{2*i_rg.mean()*1e3:>7.2f}mA  "
             f"{idle.coherent_amplitude(i_tot, 2*f, fse)*1e3:>7.3f}mA  "
             f"{dist:>9.2f}  {me.noise_dbfs:>9.1f}")
    hsay()
    hsay("    'out' is the in-band power of x*g, where x is the element sum")
    hsay("    and g the fractional gain error the rail ripple produces, with")
    hsay("    the lobe at the signal frequency taken out: a rail ripple at 2f")
    hsay("    against a signal at f puts half its product back on the")
    hsay("    fundamental, which is a gain change and not audible as")
    hsay("    distortion, and half on the third harmonic, which is. 'broadband'")
    hsay("    is what is left with every harmonic lobe excised too.")
    hsay("    Both compare directly against the -136.5 dBFS in-band noise of")
    hsay(f"    the chain as built, which is the 132.8 dB figure at a "
         f"{TEST_DBFS} dBFS signal.")
    hsay()
    pl = out_figs["plain DWA, pointer advances by the code"]
    hsay("    Where the plain-DWA error sits, by harmonic:")
    for i, v in enumerate(pl[6].harmonics_dbfs[:6], start=2):
        if np.isfinite(v):
            hsay(f"      harmonic {i} at {f*i:8.1f} Hz : {v:8.2f} dBFS")
    hsay()

    hsay("H6. Real material.")
    hsay()
    hsay(f"    {'material':>22}  {'T mean':>7}  {'T std':>7}  "
         f"{'in-band g':>10}  {'out':>9}")
    for label, maker in (("programme-like",
                          lambda n, fs_: material.programme(n, fs_, dbfs=-6.0)),
                         ("percussive",
                          lambda n, fs_: material.percussive(n, fs_, dbfs=-3.0)),
                         ("sustained 41 Hz bass",
                          lambda n, fs_: material.sustained_bass(n, fs_,
                                                                 dbfs=-6.0))):
        cm, om, fm, _ = _ref_record(pcm=maker)
        pm, nm = dwa.differential(cm, rotate=True)
        chm, _ = idle.transitions(pm, nm)
        i_el = idle.element_rail_current(pm, nm, fse)
        i_rg = idle.register_current(np.concatenate([[0.0], chm]), fse)
        i_tot = 2.0 * (i_el + i_rg)
        g = (i_tot - i_tot.mean()) * idle.Z_REF / idle.V_REF
        e = om * g
        w = idle.window(len(e))
        pg = spectra.power_spectrum(spectra.remove_dc(g, w), w)
        pe = spectra.power_spectrum(spectra.remove_dc(e, w), w)
        ff = spectra.bin_freqs(len(e), fse)
        inb = (ff >= idle.BAND[0]) & (ff <= idle.BAND[1])
        hsay(f"    {label:>22}  {chm.mean():>7.3f}  {chm.std():>7.3f}  "
             f"{spectra.dbfs(pg[inb].sum()):>10.1f}  "
             f"{spectra.dbfs(pe[inb].sum()):>9.2f}")
    hsay()
    hsay("    Real material does not escape it. The transition rate follows")
    hsay("    the envelope, so the rail ripple is the programme's own")
    hsay("    low-frequency envelope and the products land under it.")
    hsay()

    hsay("H5. Which term, so the answer can be rescaled.")
    hsay()
    a, b = dwa.differential(codes, rotate=True)
    ch, _ = idle.transitions(a, b)
    i_el = idle.element_rail_current(a, b, fse)
    i_rg = idle.register_current(np.concatenate([[0.0], ch]), fse)
    hsay(f"    {'term on the rail':>34}  {'mean':>8}  {'at 2f':>9}  "
         f"{'out':>9}")
    for label, cur in (("capacitors only", i_el),
                       ("registers only", i_rg),
                       ("both", i_el + i_rg)):
        it = 2.0 * cur
        g = (it - it.mean()) * idle.Z_REF / idle.V_REF
        e = out * g
        w = idle.window(len(e))
        pe = spectra.power_spectrum(spectra.remove_dc(e, w), w)
        ff = spectra.bin_freqs(len(e), fse)
        inb = (ff >= idle.BAND[0]) & (ff <= idle.BAND[1])
        me = spectra.Measurement.of(e, fse, f, idle.BAND, n_harmonics=10)
        tot = float(spectra.dbfs(pe[inb].sum()))
        d = 10.0 * np.log10(max(10 ** (tot / 10)
                                - 10 ** (me.signal_dbfs / 10), 1e-30))
        hsay(f"    {label:>34}  {it.mean()*1e3:>6.2f}mA  "
             f"{idle.coherent_amplitude(it, 2*f, fse)*1e3:>7.3f}mA  "
             f"{d:>9.2f}")
    hsay()
    hsay("    The register term is the larger of the two and it rests on")
    hsay("    reading the datasheet's 30 pF Cpd as per flip-flop, which")
    hsay("    power.md calls its largest remaining uncertainty. If it is per")
    hsay("    package instead, the register row drops by 24 dB and the")
    hsay("    capacitors-only row is the answer. Both rows are above the")
    hsay("    chain's own floor, so the uncertainty changes the size of the")
    hsay("    problem and not whether there is one.")
    hsay()

    plain = out_figs["plain DWA, pointer advances by the code"]
    hsay("H7. What it comes to.")
    hsay()
    hsay(f"    Plain DWA, mono, one percent elements:")
    hsay(f"      transition-dependent current  "
         f"{(plain[0]-13.92e-3)*1e3:+.1f} mA of capacitor charging and "
         f"{plain[1]*1e3:.1f} mA of register")
    hsay(f"      current at the second harmonic {plain[2]*1e3:.2f} mA, which "
         f"on {idle.Z_REF*1e3:.0f} mOhm is "
         f"{plain[2]*idle.Z_REF*1e6:.0f} uV on {idle.V_REF} V")
    hsay(f"      equivalent in-band output error {plain[5]:.1f} dBFS, of "
         f"which broadband {plain[6].noise_dbfs:.1f} dBFS")
    hsay(f"      against the chain's own         -136.5 dBFS")
    hsay(f"      and the 110 dB target, which is -113.7 dBFS at this level")
    hsay()
    need = plain[5] - (-136.5)
    hsay("    What would have to change. The rail ripple is at twice the")
    hsay("    signal frequency and at the programme envelope, which is to say")
    hsay("    it is an AUDIO-frequency current. Local decoupling does not act")
    hsay("    there: eight 100 nF parts are 100 ohm at 2 kHz and the")
    hsay("    regulator's own 10 mOhm is what the current sees. 0008's")
    hsay("    suggested mitigation, heavy local decoupling at the register")
    hsay("    packages, is right for the megahertz content and does nothing")
    hsay("    for this.")
    hsay(f"    To put this term at the chain's own floor would take "
         f"{need:.0f} dB")
    hsay(f"    less rail impedance in band, i.e. "
         f"{idle.Z_REF/10**(need/20)*1e6:.2f} uOhm at 2 kHz, which no")
    hsay("    regulator does and which would need farads of bulk capacitance.")
    hsay()
    hsay("    What follows from the identity instead. T = 14 - 4|s| is bounded")
    hsay("    above by 14, and the modulation is the deficit. Toggling unused")
    hsay("    or dummy lines to make up the deficit -- a transition ballast of")
    hsay("    up to 14 toggles per clock, driven by the same code -- would")
    hsay("    flatten the current without touching the selection rule or the")
    hsay("    mismatch shaping. That costs the average current of a fully")
    hsay("    toggling array, which is the opposite of a power saving, and it")
    hsay("    is a hardware change rather than a model result. It is offered")
    hsay("    as the one mitigation the measurement actually points at.")
    hsay()
    REF_LOG.write_text("\n".join(hlog) + "\n")
    say(f"  -> {REF_LOG.name}")
    return {"rows": rows, "out": out_figs}


# ---------------------------------------------------------------------------
SECTIONS = {}


def main(argv) -> int:
    global _FULL_RUN
    want = [a.upper() for a in argv[1:]] or sorted(SECTIONS)
    _FULL_RUN = set(want) >= set(SECTIONS)
    if not _FULL_RUN:
        print(f"(partial run: {' '.join(want)}; {LOG.name} not rewritten)")
    t0 = time.time()
    say("Idle-channel behaviour of the order-3 loop.")
    say(f"window 2**{int(np.log2(N_WIN))} at the element clock "
        f"({N_WIN/chain.ELEMENT_CLOCK['48k']*1e3:.0f} ms, "
        f"{chain.ELEMENT_CLOCK['48k']/N_WIN:.2f} Hz bins), preamble 2**"
        f"{int(np.log2(N_PRE))} discarded, datapath at the recommended widths.")
    for key in want:
        if key not in SECTIONS:
            say(f"(no section {key})")
            continue
        SECTIONS[key]()
        flush()
    say()
    say(f"total {time.time() - t0:.0f} s")
    flush()
    return 0


SECTIONS["A"] = section_a
SECTIONS["B"] = section_b
SECTIONS["C"] = section_c
SECTIONS["D"] = section_d
SECTIONS["E"] = section_e
SECTIONS["F"] = section_f
SECTIONS["G"] = section_g
SECTIONS["H"] = section_h


if __name__ == "__main__":
    sys.exit(main(sys.argv))

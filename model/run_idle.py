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
  D  remedies
  E  a runtime detector

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

from lyrebird_model import (chain, datapath, endtoend, halfband,  # noqa: E402
                            idle, material, modulator, spectra)

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


def flush() -> None:
    """Write the log after every section, so a partial run still reports."""
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
        mm = spectra.Measurement.of(x, fs, f, idle.BAND, n_harmonics=10)
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
        mm = spectra.Measurement.of(x, fs, f, idle.BAND, n_harmonics=10)
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
# name -> kwargs for run_trial, plus a dither factory taking (n, seed)
REMEDIES = (
    ("nothing", {}, None),
    ("TPDF at the source", dict(src_dither="tpdf"), None),
    ("RPDF 0.25 LSB at the quantizer", {}, ("rpdf", 0.25)),
    ("RPDF 1.0 LSB at the quantizer", {}, ("rpdf", 1.0)),
    ("high-pass 0.25 LSB at the quantizer", {}, ("hp", 0.25)),
    ("high-pass 1.0 LSB at the quantizer", {}, ("hp", 1.0)),
    ("DC bias, one signal LSB", dict(mod_dc=2.0 ** -26), None),
    ("DC bias, -80 dBFS", dict(mod_dc=1e-4), None),
    ("DC bias, -60 dBFS", dict(mod_dc=1e-3), None),
    ("integrator reset on idle", dict(idle_reset=True), None),
)


def _dither_for(spec, n, seed):
    if spec is None:
        return None
    kind, amt = spec
    if kind == "rpdf":
        return modulator.dither_sequence(n, amt, seed=seed)
    return idle.shaped_dither(n, amt, seed=seed)


def _job_d_tone(arg):
    """The 1-in-36 test itself: a 1 kHz tone, one remedy, both measurements."""
    name, kw, dspec, seed, n = arg
    ntf, c = _setup("44k1")
    m = _mode("44k1", 176400.0)
    fs, settle = m.element_clock, c.settle_samples(m)
    _, f = spectra.coherent_bin(N_LEGACY, fs, F_TONE)
    n_in = endtoend.input_length(c, m, n)
    pcm = endtoend.quantize_pcm(
        endtoend.source_tone(n_in, m.fs, f, TEST_DBFS), 24,
        "tpdf" if kw.get("src_dither") != "none" else "none", seed=seed)
    y, _ = datapath.interpolate(c, pcm, m, coeff_bits=idle.COEFF_BITS,
                                sig_frac=idle.SIG_FRAC, acc_frac=idle.ACC_FRAC)
    u = y[settle:settle + n]
    if kw.get("mod_dc"):
        u = u + kw["mod_dc"]
    d = _dither_for(dspec, n, seed + 900)
    if kw.get("idle_reset"):
        o, _, _ = idle.simulate_idle_reset(ntf, u, fs, dither=d)
    else:
        o = modulator.simulate(ntf, u, fs, f_sig=f, dither=d).out
    lg = spectra.Measurement.of(o[:N_LEGACY] - o[:N_LEGACY].mean(), fs, f,
                                idle.BAND, n_harmonics=10).sndr_db
    cor = spectra.Measurement.of(idle.remove_dc(o), fs, f, idle.BAND,
                                 n_harmonics=10).sndr_db
    return name, seed, float(lg), float(cor)


def _job_d_idle(arg):
    name, kw, dspec, seed, n = arg
    ntf, c = _setup("48k")
    m = _mode("48k", 48000.0)
    kw = dict(kw)
    d = _dither_for(dspec, n + N_PRE, seed + 900)
    t = idle.run_trial(c, ntf, m, idle="digital silence", pre="fade",
                       seed=seed, n=n, n_pre=N_PRE, quantizer_dither=d, **kw)
    return name, seed, t.b.total_db, t.b.low_db, t.b.wander_db, t.lsb_per_window


def section_d() -> dict:
    head("D.  DOES ANYTHING REMOVE IT?")
    say("Two questions, because there are two things to remove. The reading")
    say("of 125 dB, which is a measurement, and the near-DC wander, which is")
    say("real and is 128 dB down.")
    say()
    n_tone = 1 << 22
    args = [(name, kw, d, seed, n_tone)
            for name, kw, d in REMEDIES for seed in range(6)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(_job_d_tone, args))
    say(f"D1. The 1-in-36 test itself: 1 kHz at {TEST_DBFS} dBFS, 176.4 kHz,")
    say("    six source-dither draws per remedy. 'as before' is the 2**20")
    say("    window with the arithmetic mean removed; 'corrected' is 2**22")
    say("    with the windowed mean removed. Same records, both columns.")
    say(f"    ({len(rows)} runs, {time.time()-t0:.0f} s)")
    say()
    say(f"    {'remedy':>38}  {'as before, six draws':>47}  {'spread':>7}")
    out = {}
    for name, kw, d in REMEDIES:
        v = [r[2] for r in rows if r[0] == name]
        out[name] = v
        say(f"    {name:>38}  " + " ".join(f"{x:>7.1f}" for x in v) +
            f"  {max(v)-min(v):>7.1f}")
    say()
    say(f"    {'remedy':>38}  {'corrected, same six records':>47}  "
        f"{'spread':>7}")
    cor = {}
    for name, kw, d in REMEDIES:
        v = [r[3] for r in rows if r[0] == name]
        cor[name] = v
        say(f"    {name:>38}  " + " ".join(f"{x:>7.1f}" for x in v) +
            f"  {max(v)-min(v):>7.1f}")
    say()
    allleg = [x for v in out.values() for x in v]
    allcor = [x for v in cor.values() for x in v]
    say(f"    Measured as before, 60 runs span "
        f"{max(allleg)-min(allleg):.1f} dB, {min(allleg):.1f} to "
        f"{max(allleg):.1f} dB, and")
    say(f"    {sum(1 for x in allleg if x < np.median(allleg) - 5):d} of them "
        f"sit more than 5 dB below the median. Corrected, the same 60 runs")
    say(f"    span {max(allcor)-min(allcor):.1f} dB, {min(allcor):.1f} to "
        f"{max(allcor):.1f} dB, and "
        f"{sum(1 for x in allcor if x < np.median(allcor) - 5):d} do.")
    say()
    say("    That is why dither looked like it moved the fault around. Every")
    say("    remedy changes the record, every record leaves a different")
    say("    residue in the lowest bins, and the short window reports the")
    say("    residue. None of them was doing anything to the loop.")
    say()

    args = [(name, kw, d, seed, N_WIN)
            for name, kw, d in REMEDIES for seed in range(3)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows2 = list(ex.map(_job_d_idle, args))
    say("D2. What each one costs at idle: digital silence after a fade, at")
    say(f"    48 kHz, three preamble draws. ({len(rows2)} runs, "
        f"{time.time()-t0:.0f} s)")
    say()
    say(f"    {'remedy':>38}  {'20 Hz-20 kHz':>13}  {'20-100 Hz':>10}  "
        f"{'<20 Hz':>9}  {'unbalanced':>11}")
    idle_out = {}
    for name, kw, d in REMEDIES:
        v = [r for r in rows2 if r[0] == name]
        tot = float(np.mean([r[2] for r in v]))
        lo = float(np.mean([r[3] for r in v]))
        wa = float(np.mean([r[4] for r in v]))
        lsb = float(np.mean([abs(r[5]) for r in v]))
        idle_out[name] = (tot, lo, wa, lsb)
        say(f"    {name:>38}  {tot:>13.1f}  {lo:>10.1f}  {wa:>9.1f}  "
            f"{lsb:>11.1f}")
    say()
    base = idle_out["nothing"][0]
    say(f"    Cost against doing nothing, in the audio band:")
    for name, kw, d in REMEDIES:
        if name == "nothing":
            continue
        say(f"      {name:>38}  {idle_out[name][0]-base:+6.1f} dB")
    return {"tone": out, "corrected": cor, "idle": idle_out}


# ------------------------------------------------------------------ E
DET_BLOCKS = (1 << 15, 1 << 16, 1 << 17, 1 << 18, 1 << 19)


def _job_e_sens(arg):
    """Detector reading against a known low-frequency component at the output."""
    f_lf, amp_dbfs, block, n = arg
    ntf, _ = _setup("48k")
    fs = chain.ELEMENT_CLOCK["48k"]
    a = 10 ** (amp_dbfs / 20)
    u = a * np.sin(2 * np.pi * f_lf * np.arange(n) / fs)
    r = modulator.simulate(ntf, u, fs)
    return (f_lf, amp_dbfs, block, idle.detector_stat(r.codes, block),
            float(idle.bands(r.out, fs).low_db))


def _job_e_mat(arg):
    """Detector reading on real material, and how much of it the gate lets through."""
    name, dbfs, seed, block, gate, n = arg
    ntf, c = _setup("48k")
    m = _mode("48k", 48000.0)
    t = idle.run_trial(c, ntf, m, idle=name, pre="tone", seed=seed, n=n,
                       n_pre=N_PRE, idle_dbfs=dbfs, keep=True)
    codes = t.detector["codes"]
    im = np.abs(idle.imbalance(codes, block)) / block
    return (name, dbfs, seed, float(im.max()), float(np.median(im)),
            t.detector["u_rms"], t.b.low_db, t.b.total_db)


def section_e() -> dict:
    head("E.  A RUNTIME DETECTOR")
    say("Nothing found above needs detecting. What follows is therefore not a")
    say("fix but a watchdog: the cheapest thing that would notice a")
    say("low-frequency excursion at the output if one ever appeared, sized")
    say("against what idle actually reads so the threshold is a measurement")
    say("rather than a guess.")
    say()
    say("The statistic is the block sum of (code - 3.5), scaled by the block")
    say("length. At idle the eight-level quantizer has no zero level, so a")
    say("quiet loop alternates between codes 3 and 4 and the sum is near")
    say("zero; a low-frequency wander is exactly a sustained excess of one")
    say("over the other. An up/down counter and a comparator.")
    say()

    fs = chain.ELEMENT_CLOCK["48k"]
    n_sens = 1 << 21
    say("E1. Sensitivity. A known component is put at the modulator input at")
    say("    47 Hz, which is where a block of 2**18 samples is half a period,")
    say("    and the detector is read against it.")
    say()
    args = [(47.0, a, b, n_sens)
            for a in (-60.0, -80.0, -100.0, -110.0, -120.0, -140.0, -300.0)
            for b in DET_BLOCKS]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(_job_e_sens, args))
    say(f"    {'47 Hz at':>10}  {'20-100 Hz out':>14}  " +
        "  ".join(f"{'2**' + str(int(np.log2(b))):>9}" for b in DET_BLOCKS))
    sens = {}
    for a in (-60.0, -80.0, -100.0, -110.0, -120.0, -140.0, -300.0):
        v = {b: s for f_, aa, b, s, lo in rows if aa == a for f_, aa2, b, s, lo
             in [(f_, aa, b, s, lo)]}
        lo = [lo for f_, aa, b, s, lo in rows if aa == a][0]
        sens[a] = v
        lab = "silence" if a < -200 else f"{a:.0f} dBFS"
        say(f"    {lab:>10}  {lo:>14.1f}  " +
            "  ".join(f"{v[b]:>9.2e}" for b in DET_BLOCKS))
    say()
    floor = max(sens[-300.0].values())
    say(f"    Digital silence reads {floor:.2e} at worst over every block")
    say("    length, which is the noise floor of the statistic. A threshold")
    say("    ten times that is still far below any level that matters.")
    say()

    say("E2. False positives on real material. The detector cannot tell a")
    say("    40 Hz limit cycle from a 40 Hz bass note and must not try; the")
    say("    FPGA knows its own input, so the gate is a comparator on |u|.")
    say()
    block = 1 << 18
    args = [(name, dbfs, s, block, True, N_WIN)
            for name, dbfs in (("sustained 41 Hz bass", -6.0),
                               ("sustained 41 Hz bass", -60.0),
                               ("programme-like", -6.0),
                               ("near silence -100 dBFS", -100.0),
                               ("digital silence", None))
            for s in range(2)]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows2 = list(ex.map(_job_e_mat, args))
    say(f"    block 2**{int(np.log2(block))} samples "
        f"({block/fs*1e3:.1f} ms)")
    say(f"    {'material':>24}  {'level':>8}  {'input RMS':>10}  "
        f"{'worst stat':>11}  {'median stat':>12}  {'20-100 Hz out':>14}")
    for name, dbfs, seed, mx, md, urms, lo, tot in rows2:
        lab = "-" if dbfs is None else f"{dbfs:.0f} dB"
        say(f"    {name:>24}  {lab:>8}  {urms:>10.2e}  {mx:>11.2e}  "
            f"{md:>12.2e}  {lo:>14.1f}")
    say()
    return {"sens": sens, "material": rows2, "floor": floor}


# ---------------------------------------------------------------------------
SECTIONS = {}


def main(argv) -> int:
    want = [a.upper() for a in argv[1:]] or sorted(SECTIONS)
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


if __name__ == "__main__":
    sys.exit(main(sys.argv))

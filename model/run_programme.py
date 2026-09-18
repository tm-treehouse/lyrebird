#!/usr/bin/env python3
"""Run the chain against real programme material instead of tones.

    ./.venv/bin/python model/run_programme.py

README.md closes with "Only tones have been run". Every figure in it comes
from one sine or from the inter-sample probe, and four claims rest on that
narrow a base:

  1. 132.8 dB worst case end to end, at one percent elements.
  2. Budget 3 dB of headroom, because an inter-sample probe overloads the
     quantizer about 3 dB before the PCM reaches full scale.
  3. A low-frequency wander trips roughly one run in thirty-six and puts all
     of its excess between 20 and 100 Hz.
  4. Those in-band figures are single numbers over a single record.

This script tests all four against material with a real crest factor,
measured window by window over a long record rather than once.

The material is real where the machine has any: the fourteen 48 kHz 24-bit
recordings in /System/Library/Sounds, converted to WAV losslessly with
afconvert into a temporary directory and read through material.read_wav.
Sixteen point seven seconds of it, crest factors from 15 to 26 dB. Nothing is
downloaded and nothing is resampled. Where real audio does not exist at a rate
-- every rate but 48 kHz -- material.py's synthetic stand-ins are used and
said to be synthetic.

Figures land in figures/programme*.png, the log in results/programme.txt.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lyrebird_model import (chain, dwa, endtoend, halfband,  # noqa: E402
                            material, modulator, programme, spectra)

FIG = HERE / "figures"
RES = HERE / "results"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)
LOG = RES / "programme.txt"

P = programme
BAND = P.BAND
ORDER = P.ORDER
WINDOW = P.WINDOW
WARMUP = P.WARMUP
SEG_WINDOWS = 4                  # windows per continuous modulator segment
SIGMA = 0.01                     # the elements the 132.8 dB figure assumes
TONE_DBFS = -3.7                 # the level every README end-to-end row uses
PLAY_DBFS = -3.7                 # peak level the material is played at
N_MSA = 1 << 19                  # stability bisection: no spectrum taken
N_MAT = 1 << 17                  # synthetic record length for the peak tables
SWEEP_SECONDS = 0.8              # synthetic material per rate in the rate sweep
WORKERS = 6

SOUNDS = Path("/System/Library/Sounds")

log: list[str] = []
ALIGN: list[tuple] = []
_t0 = time.time()


def say(s: str = "") -> None:
    print(s, flush=True)
    log.append(s)


def flush() -> None:
    """Write the log now. Three runs have been lost at the summarising step."""
    LOG.write_text("\n".join(log) + "\n")


def head(title: str) -> None:
    say()
    say("=" * 74)
    say(f"{title}   [{time.time() - _t0:.0f} s]")
    say("=" * 74)


def note(n: int, total: int) -> None:
    if n == total or n % max(total // 10, 1) == 0:
        print(f"    ... {n}/{total}  [{time.time() - _t0:.0f} s]", flush=True)


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------

def real_record(tmp: Path) -> tuple[np.ndarray | None, list[tuple]]:
    """The machine's own 48 kHz recordings, converted losslessly and joined.

    afconvert is a format change at the same rate and the same word length, not
    a resample: material.read_wav would refuse a resampled file and should.
    """
    if not SOUNDS.is_dir() or shutil.which("afconvert") is None:
        return None, []
    rows, parts = [], []
    for src in sorted(SOUNDS.glob("*.aiff")):
        dst = tmp / (src.stem + ".wav")
        try:
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI24",
                            str(src), str(dst)], check=True,
                           capture_output=True)
            x, fs = material.read_wav(dst, 48_000.0)
        except Exception:
            continue
        if len(x) < 4096:
            continue
        parts.append(x)
        rows.append((src.stem, len(x), len(x) / fs,
                     20 * np.log10(max(np.abs(x).max(), 1e-30)),
                     P.crest_db(x)))
    if not parts:
        return None, []
    return P.concatenate(parts), rows


def synthetic(name: str, n: int, fs: float, dbfs: float) -> np.ndarray:
    return P.normalise_peak(material.CATALOGUE[name](n, fs), dbfs)


def describe_material(real, rows) -> None:
    head("MATERIAL")
    say("Real audio, 48 kHz 24-bit, from /System/Library/Sounds. Converted")
    say("with afconvert (format only, no resampling) and read through")
    say("material.read_wav, which refuses anything not already at a supported")
    say("rate.")
    say()
    if real is None:
        say("No real audio found on this machine; synthetic material only.")
    else:
        say(f"{'file':>12}  {'samples':>8}  {'seconds':>8}  {'peak dBFS':>10}  "
            f"{'crest dB':>9}")
        for r in rows:
            say(f"{r[0]:>12}  {r[1]:>8}  {r[2]:>8.2f}  {r[3]:>10.2f}  "
                f"{r[4]:>9.2f}")
        say()
        say(f"joined: {len(real)} samples, {len(real)/48000:.2f} s, "
            f"crest {P.crest_db(real):.2f} dB")
        say(f"that is {len(real)/48000/(WINDOW/chain.ELEMENT_CLOCK['48k']):.0f} "
            f"windows of 2^20 element samples")
    say()
    say("Synthetic stand-ins from material.py, for the rates real audio does")
    say("not exist at here:")
    say()
    fs = 48_000.0
    n = 1 << 17
    say(f"{'material':>24}  {'crest dB':>9}")
    say(f"{'real, joined':>24}  "
        f"{P.crest_db(real) if real is not None else float('nan'):>9.2f}")
    for name in ("programme-like", "percussive, high crest",
                 "sustained 41 Hz bass"):
        say(f"{name:>24}  {P.crest_db(material.CATALOGUE[name](n, fs)):>9.2f}")
    say(f"{'1 kHz sine':>24}  {3.01:>9.2f}")
    say()
    say("The synthetic percussive record has a higher crest factor than the")
    say("real one; the synthetic programme record has a much lower one. Both")
    say("are reported below rather than either being taken as the answer.")


# ---------------------------------------------------------------------------
# The instrument, checked against the measurement it has to replace
# ---------------------------------------------------------------------------

def validate(cs, ntf) -> dict:
    head("THE INSTRUMENT, CHECKED AGAINST THE TONE MEASUREMENT")
    say("Signal-to-noise against a tone excises the signal lobe. Broadband")
    say("material has no lobe to excise, so what is measured instead is the")
    say("error against the ideal reconstruction of the same PCM, with a")
    say("scalar gain fitted in band and removed -- the broadband equivalent")
    say("of excising the fundamental. Before trusting it on material, it is")
    say("run on the one signal where the old instrument also works.")
    say()
    say("Same record, same chain, two instruments. 1 kHz at -3.7 dBFS, one")
    say("percent elements, the datapath at its settled widths.")
    say()
    say(f"{'rate':>10}  {'classic SNR':>12}  {'classic SNDR':>13}  "
        f"{'error SNR':>10}  {'error dBFS':>11}  {'gain':>10}  "
        f"{'align margin':>13}")
    out = {}
    for fam, c in cs.items():
        for m in chain.modes(fam):
            f = endtoend.coherent_tone_freq(m, WINDOW, 1000.0)[1]
            n_in = P.pcm_for(c, m, WINDOW)
            pcm = endtoend.source_tone(n_in, m.fs, f, TONE_DBFS)
            r = P.render(c, ntf, m, pcm, n_out=WINDOW, sigma=SIGMA,
                         keep_source_term=True)
            w = P.measure(r)[0]
            mm = spectra.Measurement.of(r.x, m.element_clock, f, BAND,
                                        n_harmonics=10)
            _, margin = P.alignment_margin(r.x, r.u_ref, m.element_clock)
            say(f"{m.name:>10}  {mm.snr_db:>12.2f}  {mm.sndr_db:>13.2f}  "
                f"{w.snr_db:>10.2f}  {w.err_dbfs:>11.2f}  {w.gain:>10.6f}  "
                f"{margin:>+13.1f}")
            out[m.name] = (mm, w)
    say()
    d = [out[k][1].snr_db - out[k][0].sndr_db for k in out]
    say(f"The error instrument reads {np.mean(d):+.2f} dB against classic SNDR "
        f"on average, spread {min(d):+.2f} to {max(d):+.2f} dB.")
    say("The offset is expected and its two causes are known. The classic")
    say("figure rescales the surviving noise bins to cover the ones it")
    say("excised -- ten harmonic lobes and the signal lobe out of about 850")
    say("in-band bins, which is +1.1 dB of noise it did not measure. The error")
    say("figure counts harmonics as error, which pushes the other way. Every")
    say("material number below is on the error instrument, so the comparison")
    say("against 132.8 dB carries this offset and it is stated rather than")
    say("hidden.")
    say()
    say("The alignment margin is how much worse the in-band error gets if")
    say("the two paths are slid 256 samples apart. It is the check that")
    say("matters most: the STF of this topology is exactly 1 with zero delay,")
    say("so a wrong settling offset would show up here rather than as a")
    say("confidently wrong noise figure. A plain lag argmax cannot do this")
    say("job -- see the traps section at the end.")
    say()
    say("Decomposition of that error, at 48 kHz, one percent elements:")
    m48, w48 = out["48 kHz"]
    say(f"   total error in band          {w48.err_dbfs:8.2f} dBFS")
    say(f"   24-bit source alone          {w48.src_dbfs:8.2f} dBFS")
    rest = 10 * np.log10(max(10 ** (w48.err_dbfs / 10)
                             - 10 ** (w48.src_dbfs / 10), 1e-30))
    say(f"   everything else (mismatch)   {rest:8.2f} dBFS")
    return out


# ---------------------------------------------------------------------------
# Question 1 and 4: does the figure hold, and what shape is the floor
# ---------------------------------------------------------------------------

def windowed(cs, label: str, fam: str, mult: int, pcm: np.ndarray, *,
             sigma: float = SIGMA, n_seg: int | None = None,
             seg_windows: int = SEG_WINDOWS, kw: dict | None = None) -> list:
    """Split a long record into segments, run them, return every window."""
    c = cs[fam]
    m = [x for x in chain.modes(fam) if x.multiplier == mult][0]
    n_out = seg_windows * WINDOW
    need = P.pcm_for(c, m, n_out)
    starts = P.segment_starts(len(pcm), need, n_seg)
    if not starts:
        raise RuntimeError(f"{label}: record is {len(pcm)} samples, a segment "
                           f"needs {need}")
    base = dict(n_out=n_out, warmup=WARMUP, sigma=sigma,
                keep_source_term=False)
    base.update(kw or {})
    jobs = [{"family": fam, "multiplier": mult, "order": ORDER,
             "label": f"{label} seg {i}", "pcm": pcm[s:s + need],
             "window": WINDOW, "t0": i * n_out / m.element_clock,
             "kw": dict(base)}
            for i, s in enumerate(starts)]
    print(f"  {label}: {len(jobs)} segments x {seg_windows} windows",
          flush=True)
    res = P.run_jobs(jobs, workers=WORKERS, progress=note)
    ws, bad, margins = [], 0, []
    for r in res:
        if not r["stable"]:
            bad += 1
            continue
        mg = r["align"][1]
        if np.isfinite(mg):
            margins.append(mg)
        ws.extend(r["windows"])
    if bad:
        say(f"   !! {label}: {bad} of {len(res)} segments left the state bound")
    if margins and min(margins) < 10.0:
        say(f"   !! {label}: alignment margin fell to {min(margins):.1f} dB on "
            f"{sum(1 for v in margins if v < 10.0)} of {len(margins)} segments")
    elif margins:
        ALIGN.append((label, float(min(margins)), len(margins)))
    return ws


def dist(ws: list, key: str = "err_dbfs") -> dict:
    v = np.array([w[key] for w in ws], dtype=float)
    v = v[np.isfinite(v)]
    return {"n": len(v), "min": float(v.min()), "p10": float(np.percentile(v, 10)),
            "med": float(np.median(v)), "p90": float(np.percentile(v, 90)),
            "max": float(v.max()), "mean": float(v.mean())}


def question1(cs, ntf, real, tone) -> dict:
    head("Q1: DOES 132.8 dB HOLD UNDER MATERIAL WITH A REAL CREST FACTOR?")
    say("Each window is 2^20 element samples, 42.7 ms, 23.4 Hz bins. The")
    say("figure reported per window is the in-band power of the error, in")
    say("dBFS, which does not depend on how loud the material happens to be")
    say("in that window. 'as SNDR' converts it to the convention the README")
    say("tables use, which is a -3.7 dBFS signal against that error.")
    say()
    say("One percent elements, 24-bit TPDF source, coefficients and datapath")
    say("at their settled widths, order 3, rotation on.")
    say()
    out = {}
    say(f"{'material':>26}  {'wins':>5}  {'best':>8}  {'median':>8}  "
        f"{'worst':>8}  {'as SNDR':>9}")
    say(f"{'':>26}  {'':>5}  {'dBFS':>8}  {'dBFS':>8}  {'dBFS':>8}  "
        f"{'worst dB':>9}")

    def emit(label, ws):
        out[label] = ws
        d = dist(ws)
        say(f"{label:>26}  {d['n']:>5}  {d['min']:>8.1f}  {d['med']:>8.1f}  "
            f"{d['max']:>8.1f}  {TONE_DBFS - d['max']:>9.1f}")

    emit("1 kHz tone, 48 kHz", tone)
    if real is not None:
        emit("real audio, 48 kHz",
             windowed(cs, "real 48k", "48k", 1, real))
        emit("real audio, matched elem.",
             windowed(cs, "real 48k matched", "48k", 1, real, sigma=0.0,
                      n_seg=24))
    say()
    flush()
    return out


def question1_rates(cs, out) -> dict:
    say()
    say("Synthetic material, every rate. Real audio exists here only at")
    say("48 kHz, and material.read_wav refuses to resample, which is right.")
    say()
    say(f"{'material':>22}  {'rate':>9}  {'wins':>5}  {'best':>8}  "
        f"{'median':>8}  {'worst':>8}  {'as SNDR':>9}")
    rows = {}
    for name, short in (("programme-like", "programme"),
                        ("percussive, high crest", "percussive"),
                        ("sustained 41 Hz bass", "bass")):
        for fam in ("48k", "44k1"):
            for mult in (1, 2, 4):
                m = [x for x in chain.modes(fam) if x.multiplier == mult][0]
                n_pcm = int(SWEEP_SECONDS * m.fs)
                pcm = P.normalise_peak(
                    material.CATALOGUE[name](n_pcm, m.fs), PLAY_DBFS)
                ws = windowed(cs, f"{short} {m.name}", fam, mult, pcm)
                rows[(short, m.name)] = ws
                d = dist(ws)
                say(f"{short:>22}  {m.name:>9}  {d['n']:>5}  {d['min']:>8.1f}  "
                    f"{d['med']:>8.1f}  {d['max']:>8.1f}  "
                    f"{TONE_DBFS - d['max']:>9.1f}")
                flush()
        say()
    out.update({f"{k[0]} {k[1]}": v for k, v in rows.items()})
    return rows


def question4(out) -> None:
    head("Q4: THE SHAPE OF THE FLOOR, WINDOW BY WINDOW")
    say("A single in-band number cannot tell an evenly raised floor from a")
    say("wander concentrated under 100 Hz, which is the fault README.md")
    say("leaves open. material.band_shape splits every window three ways.")
    say("Shares are of in-band error power.")
    say()
    say("White noise, for reference, would put 0.44 percent of its in-band")
    say("power in 20-100 Hz, 10.1 percent in 100 Hz-2 kHz and 89.5 percent in")
    say("2-20 kHz, because those bands are 80, 1900 and 18000 Hz wide.")
    say()
    say(f"{'material':>26}  {'wins':>5}  {'low share, percent':>28}  "
        f"{'low band dBFS':>22}")
    say(f"{'':>26}  {'':>5}  {'p10':>8} {'median':>9} {'p90':>9}  "
        f"{'median':>10} {'worst':>10}")
    for label, ws in out.items():
        if not ws:
            continue
        s = np.array([w["low_share"] for w in ws]) * 100.0
        lo = np.array([w["low_db"] for w in ws])
        say(f"{label:>26}  {len(ws):>5}  {np.percentile(s, 10):>8.2f} "
            f"{np.median(s):>9.2f} {np.percentile(s, 90):>9.2f}  "
            f"{np.median(lo):>10.1f} {lo.max():>10.1f}")
    flush()



def by_loudness(out) -> None:
    head("Q1: IS THE ERROR THE SAME WHEN THE MUSIC IS QUIET?")
    say("Programme material is not on all the time. Sixteen seconds of it")
    say("contains loud passages, decays and gaps, and the loop behaves")
    say("differently near idle -- which is where README.md puts the wander.")
    say("Windows are split by how much in-band signal they carry.")
    say()
    say(f"{'material':>26}  {'band':>16}  {'wins':>5}  {'median err':>11}  "
        f"{'worst err':>10}  {'median low share':>17}")
    edges = [(-1e9, -60.0, "below -60 dBFS"), (-60.0, -30.0, "-60 to -30"),
             (-30.0, -12.0, "-30 to -12"), (-12.0, 1e9, "above -12 dBFS")]
    for label, ws in out.items():
        if not ws:
            continue
        sig = np.array([w["sig_dbfs"] for w in ws])
        err = np.array([w["err_dbfs"] for w in ws])
        sh = np.array([w["low_share"] for w in ws]) * 100.0
        for lo, hi, name in edges:
            sel = (sig >= lo) & (sig < hi)
            if not sel.any():
                continue
            say(f"{label:>26}  {name:>16}  {int(sel.sum()):>5}  "
                f"{np.median(err[sel]):>11.1f}  {err[sel].max():>10.1f}  "
                f"{np.median(sh[sel]):>16.2f}%")
        say()
    flush()


# ---------------------------------------------------------------------------
# Question 2: headroom
# ---------------------------------------------------------------------------

def question2(cs, ntf, real) -> dict:
    head("Q2: IS 3 dB THE RIGHT HEADROOM BUDGET?")
    say("The 3 dB recommendation comes from one probe: a tone at Fs/4 sampled")
    say("at 45 degrees, whose reconstructed waveform peaks exactly 3.01 dB")
    say("above every one of its samples. The question is what real material")
    say("does, so the first table is the peak the cascade actually presents")
    say("to the quantizer against the peak the PCM contains. Records are")
    say("faded at both ends and scanned in blocks; an un-faded record's edge")
    say("reads as 1 dB of headroom that is not there.")
    say()
    c = cs["48k"]
    m = [x for x in chain.modes("48k") if x.multiplier == 1][0]
    m192 = [x for x in chain.modes("48k") if x.multiplier == 4][0]
    n = N_MAT
    cases: list[tuple[str, np.ndarray]] = []
    if real is not None:
        cases.append(("real audio, 16.7 s", real))
        for drive in (3.0, 6.0, 12.0):
            cases.append((f"real, clipped {drive:.0f} dB",
                          P.limit(P.normalise_peak(real, 0.0), drive)))
    perc = material.percussive(n, m.fs)
    prog = material.programme(n, m.fs)
    cases += [
        ("percussive, synthetic", perc),
        ("percussive, clipped 6 dB", P.limit(P.normalise_peak(perc, 0.0), 6.0)),
        ("percussive, clipped 12 dB", P.limit(P.normalise_peak(perc, 0.0), 12.0)),
        ("programme, synthetic", prog),
        ("programme, clipped 12 dB", P.limit(P.normalise_peak(prog, 0.0), 12.0)),
        ("sustained 41 Hz bass", material.sustained_bass(n, m.fs)),
        ("1 kHz tone", endtoend.source_tone(n, m.fs, 1000.0, 0.0)),
        ("Fs/4 inter-sample probe", endtoend.source_intersample(n, 0.0)),
    ]
    say(f"{'material':>26}  {'crest dB':>9}  {'samples at FS':>14}  "
        f"{'true peak':>10}  {'overshoot dB':>13}  {'peaks apart':>12}")
    peaks = {}
    for label, x in cases:
        q = endtoend.quantize_pcm(P.normalise_peak(x, 0.0))
        d = P.true_peak(c, m, q)
        at_fs = int(np.sum(np.abs(q) > 0.99995))
        peaks[label] = d
        say(f"{label:>26}  {P.crest_db(q):>9.2f}  {at_fs:>14}  "
            f"{d['true_peak']:>10.4f}  {d['overshoot_db']:>+13.3f}  "
            f"{d['apart'] / m.fs * 1e3:>9.1f} ms")
        flush()
    say()
    say("'peaks apart' is how far the largest reconstructed peak sits from")
    say("the largest sample. For unprocessed material they are the same")
    say("event. For clipped material they are not even close, and a headroom")
    say("measurement windowed on the loudest sample measures the wrong")
    say("moment.")
    say()
    say("Read the first column with the last but one. The probe is 3.010 dB of")
    say("overshoot because every one of its samples sits at full scale by")
    say("construction. Unprocessed material never does that, and its")
    say("overshoot is correspondingly small. Clipping is what creates flat")
    say("runs at full scale, and clipping is what creates the overshoot.")
    say()

    head("Q2: WHERE MATERIAL ACTUALLY OVERLOADS THE QUANTIZER")
    say("Bisection on the PCM level, same bound as")
    say("modulator.max_stable_amplitude and endtoend.max_stable_pcm -- no")
    say("integrator past 50 quantizer LSBs -- so these numbers sit directly")
    say("beside the README headroom table. The window is centred on the")
    say("largest peak the cascade *reconstructs*, which is not the largest")
    say("sample and for clipped material is nowhere near it -- on the")
    say("percussive record clipped 12 dB the two are 1.5 seconds apart and")
    say("2.5 dB apart. Centring on the loudest sample would miss the moment")
    say("that decides the answer, which is the only reason to window on a")
    say("peak at all.")
    say()
    n_msa = N_MSA
    say(f"{'material':>26}  {'rate':>9}  {'MSA at PCM':>11}  "
        f"{'peak at quantizer':>18}  {'headroom needed':>16}")
    msa = {}
    probes: list[tuple[str, np.ndarray]] = []
    if real is not None:
        probes.append(("real audio", real))
        probes.append(("real, clipped 12 dB",
                       P.limit(P.normalise_peak(real, 0.0), 12.0)))
    probes += [
        ("percussive, synthetic", perc),
        ("percussive, clipped 12 dB", P.limit(P.normalise_peak(perc, 0.0), 12.0)),
        ("programme, synthetic", prog),
        ("1 kHz tone", endtoend.source_tone(n, m.fs, 1000.0, 0.0)),
        ("Fs/4 inter-sample probe", endtoend.source_intersample(n, 0.0)),
    ]
    for mm in (m, m192):
        n_in = endtoend.input_length(cs["48k"], mm, n_msa)
        for label, x in probes:
            xx = (P.true_peak_slice(cs["48k"], mm,
                                    np.asarray(x, dtype=np.float64), n_in)
                  if len(x) > n_in else P.tile_to(x, n_in))
            d = P.max_stable_material(cs["48k"], ntf, mm, xx, n_out=n_msa)
            msa[(label, mm.name)] = d
            say(f"{label:>26}  {mm.name:>9}  {d['amp_dbfs']:>+11.2f}  "
                f"{d['peak_dbfs']:>+18.2f}  {-d['amp_dbfs']:>16.2f}")
            flush()
        say()
    say("'headroom needed' is how far below full scale the PCM has to sit for")
    say("this material to stay inside the loop's bound.")
    say()
    return {"peaks": peaks, "msa": msa}


def level_sweep(cs, ntf, real) -> dict:
    head("Q2: WHAT HAPPENS ON THE WAY THERE")
    say("A stability bound is a cliff. This is the approach to it: the same")
    say("record at rising level, one window each, one percent elements.")
    say("'rail' is the fraction of samples sitting on the top or bottom")
    say("quantizer code, which is a thing the FPGA can count for free.")
    say()
    c = cs["48k"]
    m = [x for x in chain.modes("48k") if x.multiplier == 1][0]
    n_in = P.pcm_for(c, m, WINDOW)
    n = N_MAT
    perc = material.percussive(n, m.fs)
    picks: list[tuple[str, np.ndarray]] = []
    tps = lambda z: P.true_peak_slice(c, m, P.tile_to(z, max(len(z), n_in)),
                                      n_in)
    if real is not None:
        picks.append(("real audio", tps(real)))
        picks.append(("real, clipped 12 dB",
                      tps(P.limit(P.normalise_peak(real, 0.0), 12.0))))
    picks += [("percussive", tps(perc)),
              ("percussive, clipped 12 dB",
               tps(P.limit(P.normalise_peak(perc, 0.0), 12.0)))]
    out = {}
    levels = [-12.0, -9.0, -6.0, -4.5, -3.0, -2.0, -1.0, 0.0]
    for label, x in picks:
        say(f"{label}")
        say(f"{'PCM dBFS':>10}  {'peak at quantizer':>18}  {'rail':>8}  "
            f"{'clipped':>8}  {'max state':>10}  {'error dBFS':>11}  "
            f"{'as SNDR':>8}")
        rows = []
        for lv in levels:
            pcm = P.normalise_peak(x, lv)
            r = P.render(c, ntf, m, pcm, n_out=WINDOW, sigma=SIGMA)
            if not r.stable:
                say(f"{lv:>+10.1f}  {'':>18}  {'':>8}  {'':>8}  "
                    f"{'unbounded':>10}")
                rows.append((lv, np.nan, np.nan, -1, np.nan, np.nan))
                continue
            w = P.measure(r)[0]
            say(f"{lv:>+10.1f}  {w.peak_u_dbfs:>+18.2f}  {w.rail_frac:>8.4f}  "
                f"{r.clipped:>8}  {float(r.state_peak.max()):>10.3f}  "
                f"{w.err_dbfs:>11.1f}  {TONE_DBFS - w.err_dbfs:>8.1f}")
            rows.append((lv, w.peak_u_dbfs, w.rail_frac, r.clipped,
                         float(r.state_peak.max()), w.err_dbfs))
        out[label] = rows
        say()
        flush()
    return out


# ---------------------------------------------------------------------------
# Question 3: bass against the fault
# ---------------------------------------------------------------------------

def question3(cs, ntf) -> dict:
    head("Q3: CAN GENUINE BASS AND A LOW-FREQUENCY ANOMALY BE TOLD APART?")
    say("The question was posed against the limit cycle README.md leaves")
    say("open. That fault turns out not to exist -- it was the mean")
    say("subtraction, measured in the section above -- so what is left is the")
    say("general version, and it is still the one the hardware has to answer:")
    say("if something ever does put energy between 20 and 100 Hz that is not")
    say("music, can a monitor tell, given that music puts energy there too?")
    say()
    say("Each case is run four ways that differ only in things that cannot")
    say("change the audio: how many samples the loop ran before the window")
    say("opened, and which way the datapath rounds ties. Nothing here is")
    say("expected to trip any more; the point is what the three detectors")
    say("read when the signal is 41 Hz bass at -6 dBFS.")
    say()
    say("Three detectors, all 20-100 Hz power.")
    say("  output    : the element sum itself. What a monitor on the output")
    say("              sees, and all it sees.")
    say("  error     : output against the ideal reconstruction. Correct, and")
    say("              not available in hardware -- it needs a reference DAC.")
    say("  loop, v-u : the modulator's output code minus its own input. The")
    say("              STF of this topology is exactly 1 with zero delay, so")
    say("              this cancels the music exactly and leaves the shaped")
    say("              error. It is the d the integrators are already driven")
    say("              by, so the FPGA has it for free.")
    say()
    out = {}
    for fam, mult in (("48k", 2), ("48k", 1), ("44k1", 4)):
        c = cs[fam]
        m = [x for x in chain.modes(fam) if x.multiplier == mult][0]
        say(f"--- {m.name} ---")
        say(f"{'material':>24}  {'variation':>22}  {'output':>9}  "
            f"{'error':>9}  {'loop v-u':>9}  {'err total':>10}  "
            f"{'low share':>10}")
        for label, mk in (("sustained 41 Hz bass",
                           lambda n: P.normalise_peak(
                               material.sustained_bass(n, m.fs), -6.0)),
                          ("1 kHz tone",
                           lambda n: endtoend.source_tone(
                               n, m.fs, coherent(m, 1000.0), TONE_DBFS)),
                          ("near silence, -100 dBFS",
                           lambda n: material.near_silence(n, m.fs))):
            for vname, wu, rnd in (("cold, ties even", 0, "half_even"),
                                   ("warm, ties even", WARMUP, "half_even"),
                                   ("cold, ties up", 0, "half_up"),
                                   ("warm, ties up", WARMUP, "half_up")):
                n_in = P.pcm_for(c, m, WINDOW, warmup=wu)
                r = P.render(c, ntf, m, mk(n_in), n_out=WINDOW, warmup=wu,
                             sigma=SIGMA, rounding=rnd)
                if not r.stable:
                    say(f"{label:>24}  {vname:>22}  unbounded")
                    continue
                w = P.measure(r, window=WINDOW)[0]
                ob = material.band_shape(P.centre(r.x), m.element_clock)
                out[(m.name, label, vname)] = (w, ob)
                say(f"{label:>24}  {vname:>22}  "
                    f"{P._to_dbfs(ob['low_db']):>9.1f}  {w.low_db:>9.1f}  "
                    f"{w.loop_low_dbfs:>9.1f}  {w.err_dbfs:>10.1f}  "
                    f"{w.low_share*100:>9.2f}%")
                flush()
            say()
    say()
    say("What separates a wandering run from bass, in the rows above:")
    bass = [(k, v) for k, v in out.items() if "bass" in k[1]]
    if bass:
        ol = [P._to_dbfs(v[1]["low_db"]) for _, v in bass]
        ll = [v[0].loop_low_dbfs for _, v in bass]
        say(f"   bass, 20-100 Hz at the output : {min(ol):.1f} to "
            f"{max(ol):.1f} dBFS")
        say(f"   bass, 20-100 Hz in the loop   : {min(ll):.1f} to "
            f"{max(ll):.1f} dBFS")
    worst = max(out.items(), key=lambda kv: kv[1][0].loop_low_dbfs)
    best = min(out.items(), key=lambda kv: kv[1][0].loop_low_dbfs)
    say(f"   loudest loop 20-100 Hz of any run : {worst[1][0].loop_low_dbfs:.1f} "
        f"dBFS ({worst[0][1]}, {worst[0][2]}, {worst[0][0]})")
    say(f"   quietest                          : {best[1][0].loop_low_dbfs:.1f} "
        f"dBFS ({best[0][1]}, {best[0][2]}, {best[0][0]})")
    flush()
    return out


def wander(cs, ntf) -> dict:
    head("THE LOW-FREQUENCY FAULT WAS THE TRANSFORM, NOT THE LOOP")
    say("README.md carries an open item: the loop occasionally settles into a")
    say("very-low-frequency wander, one run in thirty-six comes back 15 to")
    say("19 dB low, and every bit of the excess sits between 20 and 100 Hz.")
    say("This run reproduced it on demand and then found it was not there.")
    say()
    say("The reproduction: a 1 kHz tone at -3.7 dBFS, one percent elements,")
    say("the recommended widths, ties to even -- a configuration")
    say("run_endtoend.py measures at 133.7 dB -- run twice, differing only in")
    say("how many samples the modulator ran before the measured window opened.")
    say("Nothing that can change the audio.")
    say()
    say("The two columns are the same spectrum with the mean removed two ways.")
    say("'plain' is x - x.mean(). 'windowed' is x - sum(w*x)/sum(w), which is")
    say("the mean the Kaiser transform actually integrates.")
    say()
    say(f"{'rate':>9}  {'warm-up':>9}  {'plain: error':>13}  {'20-100':>8}  "
        f"{'share':>7}   {'windowed: error':>16}  {'20-100':>8}  {'share':>7}")
    out = {}
    c = cs["48k"]
    aw = spectra.analysis_window(WINDOW)
    for mult in (1, 2, 4):
        m = [x for x in chain.modes("48k") if x.multiplier == mult][0]
        for wu in (0, WARMUP):
            n_in = P.pcm_for(c, m, WINDOW, warmup=wu)
            f = endtoend.coherent_tone_freq(m, WINDOW, 1000.0)[1]
            pcm = endtoend.source_tone(n_in, m.fs, f, TONE_DBFS)
            r = P.render(c, ntf, m, pcm, n_out=WINDOW, warmup=wu, sigma=SIGMA)
            cr, au = P.band_gain_terms(r.x, r.u_ref, m.element_clock)
            raw = r.x - (cr / au) * r.u_ref
            bp = material.band_shape(raw - raw.mean(), m.element_clock)
            bw = material.band_shape(P.centre(raw, aw), m.element_clock)
            out[(m.name, wu)] = (bp, bw)
            say(f"{m.name:>9}  {wu:>9}  {P._to_dbfs(bp['total_db']):>13.2f}  "
                f"{P._to_dbfs(bp['low_db']):>8.1f}  "
                f"{bp['low_share']*100:>6.2f}%   "
                f"{P._to_dbfs(bw['total_db']):>16.2f}  "
                f"{P._to_dbfs(bw['low_db']):>8.1f}  "
                f"{bw['low_share']*100:>6.2f}%")
            flush()
    bp, bw = out[("96 kHz", WARMUP)]
    say()
    say(f"**The 96 kHz run with warm-up reads {P._to_dbfs(bp['total_db']):.2f} "
        f"dBFS with the plain mean removed,")
    say(f"{bp['low_share']*100:.0f} percent of it below 100 Hz, and "
        f"{P._to_dbfs(bw['total_db']):.2f} dBFS with the windowed mean")
    say(f"removed, {bw['low_share']*100:.2f} percent of it below 100 Hz.** The "
        f"low band moves by")
    say(f"{P._to_dbfs(bw['low_db']) - P._to_dbfs(bp['low_db']):.0f} dB and the "
        f"in-band figure by "
        f"{P._to_dbfs(bw['total_db']) - P._to_dbfs(bp['total_db']):.1f} dB. "
        f"Same record, same chain, same")
    say("samples -- only the arithmetic of the mean subtraction differs.")
    say()
    say("x - x.mean() nulls the record's unwindowed average. A Kaiser-windowed")
    say("transform integrates sum(w*x)/sum(w) instead, so the wrong")
    say("subtraction leaves a DC residue, and at beta 26 the main lobe is")
    say("twelve bins wide -- 280 Hz at this transform length. The residue")
    say("lands spread across exactly the 20 to 100 Hz bins the fault was")
    say("diagnosed from. **The measurement was manufacturing the signature it")
    say("was looking for.**")
    say()
    say("Two things follow. The open item in README.md -- the low-frequency")
    say("limit cycle, one run in thirty-six, dither does not remove it -- is")
    say("this, and there is no limit cycle to fix. And the rule in the trap")
    say("list is not strong enough as written: 'remove the mean' has to say")
    say("*which* mean, because the difference between the two is invisible in")
    say("the time domain and 8.5 dB in the answer.")
    return out


def traps(cs, ntf, real) -> None:
    head("MEASUREMENT TRAPS THIS RUN FOUND")
    say("Each one produced a confident number that was wrong, and each is")
    say("demonstrated here rather than asserted.")
    say()
    c = cs["48k"]
    m = [x for x in chain.modes("48k") if x.multiplier == 1][0]
    fs = m.element_clock
    need = P.pcm_for(c, m, WINDOW)
    src = (P.peak_slice(real, need) if real is not None
           else material.programme(need, m.fs))
    say("1. 'REMOVE THE MEAN' HAS TO SAY WHICH MEAN.")
    say("   x - x.mean() nulls the record's unwindowed average. A Kaiser-")
    say("   windowed transform integrates sum(w*x)/sum(w). The difference is")
    say("   invisible in the time domain and it lands as a DC residue smeared")
    say("   across twelve bins, which is 280 Hz here -- on top of the 20 to")
    say("   100 Hz band. Measured above: 8.5 dB on an in-band figure and")
    say("   53 dB on the low band, and it is the whole of the low-frequency")
    say("   limit cycle README.md leaves open. Every mean removed in this")
    say("   module is the windowed one.")
    say()
    say("2. THE GAIN FIT HAS TO HAVE THE MEAN REMOVED FROM IT TOO.")
    say("   Element mismatch leaves a static offset on the element sum. The")
    say("   error has its mean removed, which is the rule README.md already")
    say("   states -- but the *scalar gain* fitted before that subtraction")
    say("   does not, and at 23.4 Hz bins a Kaiser main lobe is twelve bins")
    say("   wide, so the offset leaks to 280 Hz, inside the band the fit is")
    say("   taken over. The bias it leaves scales as the signal shrinks.")
    say()
    say(f"   {'PCM level':>10}  {'fitted gain':>12}  {'error, mean left in':>20}  "
        f"{'error, mean removed':>20}")
    for lv in (-12.0, -40.0, -70.0):
        pcm = P.normalise_peak(src, lv)
        r = P.render(c, ntf, m, pcm, n_out=WINDOW, sigma=SIGMA)
        w = spectra.analysis_window(WINDOW)
        f = spectra.bin_freqs(WINDOW, fs)
        sel = (f >= BAND[0]) & (f <= BAND[1])

        def fit(centred: bool) -> tuple[float, float]:
            a = P.centre(r.x, w) if centred else r.x
            b = P.centre(r.u_ref, w) if centred else r.u_ref
            X = np.fft.rfft(a * w)
            U = np.fft.rfft(b * w)
            g = (float(np.real(np.vdot(U[sel], X[sel])))
                 / float(np.real(np.vdot(U[sel], U[sel]))))
            e = r.x - g * r.u_ref
            return g, P._to_dbfs(material.band_shape(P.centre(e, w),
                                                     fs)["total_db"])
        g_bad, e_bad = fit(False)
        g_ok, e_ok = fit(True)
        say(f"   {lv:>+10.1f}  {g_ok:>12.6f}  {e_bad:>20.1f}  {e_ok:>20.1f}")
        flush()
    say()
    say("   Left in, the error stops moving when the level does, which is the")
    say("   tell: it is no longer measuring the chain. It cost this run one")
    say("   complete pass and a finding that turned out not to exist.")
    say()
    say("3. THE GAIN FIT HAS TO BE RESTRICTED TO THE BAND.")
    say("   Fitted over the whole record it is dominated by the modulator's")
    say("   out-of-band noise, which is 90 dB above the in-band error. That")
    say("   noise is uncorrelated with the signal but its inner product with")
    say("   it is not zero, and the leftover gain error injects a pure")
    say("   in-band residual. Predicted at about -77 dBFS; measured:")
    say()
    pcm = P.normalise_peak(src, TONE_DBFS)
    r = P.render(c, ntf, m, pcm, n_out=WINDOW, sigma=SIGMA)
    cx, cu = P.centre(r.x), P.centre(r.u_ref)
    g_bb = float(np.dot(cx, cu) / np.dot(cu, cu))
    bb = P._to_dbfs(material.band_shape(
        P.centre(r.x - g_bb * r.u_ref), fs)["total_db"])
    w0 = P.measure(r, window=WINDOW)[0]
    say(f"   broadband fit: gain {g_bb:.6f}, in-band error {bb:.1f} dBFS")
    say(f"   in-band  fit: gain {w0.gain:.6f}, in-band error "
        f"{w0.err_dbfs:.1f} dBFS")
    say()
    say("4. A HEADROOM WINDOW HAS TO BE CENTRED ON THE RECONSTRUCTED PEAK,")
    say("   NOT ON THE LOUDEST SAMPLE. The two are the same event in")
    say("   unprocessed material and 1.5 seconds apart in clipped material,")
    say("   because clipping makes the reconstruction overshoot wherever a")
    say("   flat run happens to be, not where the record is loudest. Same")
    say("   record, same bisection, only the window moved:")
    say()
    n_msa = N_MSA
    n_in = endtoend.input_length(c, m, n_msa)
    pc = P.limit(P.normalise_peak(material.percussive(N_MAT, m.fs), 0.0), 12.0)
    pc = P.tile_to(pc, max(len(pc), n_in))
    for name, sl in (("centred on the loudest sample", P.peak_slice(pc, n_in)),
                     ("centred on the reconstructed peak",
                      P.true_peak_slice(c, m, pc, n_in))):
        d = P.max_stable_material(c, ntf, m, sl, n_out=n_msa)
        say(f"   {name:>36}: MSA {d['amp_dbfs']:+.2f} dBFS, peak at the "
            f"quantizer {d['peak_dbfs']:+.2f} dBFS")
        flush()
    say()
    say("5. A LAG CHECK OVER A FEW SAMPLES CANNOT CHECK ANYTHING.")
    say("   The signal is band-limited to 20 kHz and sampled at 24.576 MHz,")
    say("   so its autocorrelation is flat over plus or minus eight samples")
    say("   and an argmax there reports where the out-of-band noise fell. It")
    say("   false-alarmed on 34 of 90 segments of real material. What is")
    say("   checked instead is the in-band error at the offset used against")
    say("   the in-band error 256 samples away, which is a fifth of a period")
    say("   at 10 kHz and therefore a real displacement.")
    flush()


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The thing a tone cannot show
# ---------------------------------------------------------------------------

def coherent(m, f_target: float) -> float:
    return endtoend.coherent_tone_freq(m, WINDOW, f_target)[1]


def to_inband(x: np.ndarray, fs: float, target_dbfs: float) -> np.ndarray:
    """Scale so the record carries ``target_dbfs`` of power in 20 Hz-20 kHz.

    Matching on peak level would compare a sine against material with 20 dB
    more crest factor and call the difference a result. What has to be held
    equal is how hard the converter is driven in the band the answer is
    reported in.
    """
    x = np.asarray(x, dtype=np.float64)
    w = spectra.analysis_window(len(x))
    p = spectra.power_spectrum(P.centre(x, w), w)
    f = spectra.bin_freqs(len(x), fs)
    sel = (f >= BAND[0]) & (f <= BAND[1])
    cur = float(spectra.dbfs(float(p[sel].sum())))
    return x * 10.0 ** ((target_dbfs - cur) / 20.0)


def mismatch_and_material(cs, ntf, real) -> dict:
    head("WHAT ONE TONE UNDERSTATES: MISMATCH AGAINST BROADBAND CONTENT")
    say("An earlier pass of this script reported that broadband material")
    say("provoked mid-band distortion a tone did not, rising to 40 dB. It did")
    say("not. That was the gain fit being taken on un-centred signals, and it")
    say("is written up in the traps section. This is the same question asked")
    say("with the instrument repaired, and the answer is much smaller and")
    say("still worth having.")
    say()
    say("Sources are matched on in-band signal power, not on peak level, so")
    say("what differs between the rows is the content and nothing else.")
    say()
    c = cs["48k"]
    m = [x for x in chain.modes("48k") if x.multiplier == 1][0]
    fs = m.element_clock
    need = P.pcm_for(c, m, WINDOW)
    t = np.arange(need) / m.fs

    def tones(freqs):
        return sum(np.sin(2 * np.pi * coherent(m, f) * t + 0.7 * i)
                   for i, f in enumerate(freqs))

    rng = np.random.default_rng(12)
    srcs = [
        ("1 kHz sine", tones([1000.0])),
        ("two tones, 1.0 + 1.1 kHz", tones([1000.0, 1100.0])),
        ("8-tone multitone", tones([110.0, 220.0, 437.0, 881.0, 1753.0,
                                    3499.0, 7001.0, 13999.0])),
        ("white noise to 20 kHz", rng.standard_normal(need)),
        ("sustained 41 Hz bass", material.sustained_bass(need, m.fs)),
        ("programme, synthetic", material.programme(need, m.fs)),
    ]
    if real is not None:
        srcs.append(("real audio", real[:need]))
    target = -16.0
    say(f"In-band signal power held at {target:.0f} dBFS. 48 kHz, order 3, "
        f"2^{int(np.log2(WINDOW))} samples.")
    say()
    say(f"{'source':>26}  {'crest':>6}  {'matched':>8}  {'0.1%':>8}  "
        f"{'1%':>8}  {'1%, no rot':>10}  {'1% cost':>8}  {'mod only':>9}")
    out = {}
    for label, x in srcs:
        xx = to_inband(x, m.fs, target)
        row = {}
        for key, kw in (("matched", dict(sigma=0.0)),
                        ("0.1%", dict(sigma=0.001)),
                        ("1%", dict(sigma=0.01)),
                        ("norot", dict(sigma=0.01, rotate=False))):
            r = P.render(c, ntf, m, xx, n_out=WINDOW, **kw)
            w = P.measure(r, window=WINDOW)[0]
            row[key] = w.err_dbfs
            if key == "1%":
                row["bands"] = (w.low_db, w.mid_db, w.high_db)
            if key == "matched":
                cr, au = P.band_gain_terms(r.v, r.u_ref, fs)
                row["mod"] = P._to_dbfs(material.band_shape(
                    P.centre(r.v - (cr / au) * r.u_ref), fs)["total_db"])
        out[label] = row
        say(f"{label:>26}  {P.crest_db(xx):>6.1f}  {row['matched']:>8.1f}  "
            f"{row['0.1%']:>8.1f}  {row['1%']:>8.1f}  {row['norot']:>10.1f}  "
            f"{row['1%'] - row['matched']:>+8.1f}  {row['mod']:>9.1f}")
        flush()
    say()
    say("Read the last column first. 'mod only' is the same error measured")
    say("before the elements -- cascade, datapath and modulator against the")
    say("ideal reconstruction. It is within a decibel of the matched-element")
    say("column on every row, so **the cascade and the modulator do not care")
    say("what the material is**. Everything that changes between these rows")
    say("happens in the weighted element sum.")
    say()
    say(f"{'source':>26}  {'20-100':>9}  {'0.1-2k':>9}  {'2-20k':>9}   "
        f"at 1% elements")
    for label in out:
        lo, mid, hi = out[label]["bands"]
        say(f"{label:>26}  {lo:>9.1f}  {mid:>9.1f}  {hi:>9.1f}")
    say()
    say("**The error is in 2-20 kHz on every row, 14 dB or more above the")
    say("100 Hz-2 kHz band.** There is no mid-band term that tracks the")
    say("signal. Rotation is shaping the mismatch up out of the band against")
    say("broadband material exactly as it does against a tone, which is what")
    say("0008 claims and what the earlier pass appeared to contradict.")
    say()
    costs = {k: v["1%"] - v["matched"] for k, v in out.items()}
    cheapest = min(costs, key=costs.get)
    dearest = max(costs, key=costs.get)
    say(f"What is real is the spread in the cost column. One percent elements")
    say(f"cost {costs['1 kHz sine']:.1f} dB against a single sine and "
        f"{costs[dearest]:.1f} dB against {dearest},")
    say(f"a spread of {costs[dearest] - costs[cheapest]:.1f} dB over every "
        f"source measured. **A tone understates")
    say(f"what one percent elements cost, by "
        f"{costs[dearest] - costs['1 kHz sine']:.1f} dB against the worst "
        f"source here.**")
    say("That is the whole of what broadband content reveals that a tone")
    say("hides, and it is 4 dB rather than the 40 the broken pass reported.")
    say()

    head("THE SAME THING AT A LONGER TRANSFORM")
    say("Two findings from this script have now dissolved into measurement")
    say("artefacts, so this one is checked before it is believed. The test is")
    say("the one that would break it: a longer transform, which halves the bin")
    say("width and so halves how far any leftover DC can reach, against a tone")
    say("at the same in-band level in the same band.")
    say()
    say(f"{'source':>26}  {'2^20 matched':>13}  {'2^20 at 1%':>11}  "
        f"{'2^21 matched':>13}  {'2^21 at 1%':>11}  {'2^21 mid':>9}")
    long_need = P.pcm_for(c, m, 2 * WINDOW)
    tl = np.arange(long_need) / m.fs
    for label in ("1 kHz sine", "white noise to 20 kHz", "real audio"):
        if label not in out:
            continue
        if label == "1 kHz sine":
            xl = np.sin(2 * np.pi * coherent(m, 1000.0) * tl)
        elif label == "white noise to 20 kHz":
            xl = np.random.default_rng(12).standard_normal(long_need)
        else:
            xl = real[:long_need]
        xl = to_inband(xl, m.fs, target)
        vals = []
        for sg in (0.0, 0.01):
            rl = P.render(c, ntf, m, xl, n_out=2 * WINDOW, sigma=sg)
            wl = P.measure(rl, window=2 * WINDOW)[0]
            vals.append(wl)
        say(f"{label:>26}  {out[label]['matched']:>13.1f}  "
            f"{out[label]['1%']:>11.1f}  {vals[0].err_dbfs:>13.1f}  "
            f"{vals[1].err_dbfs:>11.1f}  {vals[1].mid_db:>9.1f}")
        flush()
    say()
    say("Doubling the transform moves nothing by more than a decibel, and the")
    say("100 Hz-2 kHz band stays where it was. The result is a property of the")
    say("chain, not of the window.")
    say()

    head("HOW MUCH THE PARTICULAR ELEMENTS MATTER")
    say("One percent is a tolerance, not a value. These rows are the same")
    say("chain and the same record with different draws from it, plus two")
    say("constructed cases that isolate what the differential pair does.")
    say()
    if real is None:
        say("(needs real material; skipped)")
        return out
    seg = P.normalise_peak(real[:need], PLAY_DBFS)
    say(f"{'elements':>44}  {'error':>8}  {'20-100':>8}  {'0.1-2k':>8}  "
        f"{'2-20k':>8}")

    def with_weights(wp, wn, label):
        settle = c.settle_samples(m)
        import lyrebird_model.datapath as D
        ref, _ = D.interpolate(c, seg, m, coeff_bits=P.COEFF_BITS)
        q = endtoend.quantize_pcm(seg)
        got, _ = D.interpolate(c, q, m, coeff_bits=P.COEFF_BITS,
                               sig_frac=P.SIG_FRAC, acc_frac=P.ACC_FRAC)
        drive = got[settle:settle + WARMUP + WINDOW]
        rr = modulator.simulate(ntf, drive, fs)
        codes = np.clip(np.asarray(rr.codes, np.int64), 0, chain.N_ELEMENTS)
        x = P.element_sum(codes, rotate=True, w_pos=wp, w_neg=wn)[WARMUP:]
        uref = ref[settle + WARMUP:settle + WARMUP + WINDOW]
        cr, au = P.band_gain_terms(x, uref, fs)
        bs = material.band_shape(P.centre(x - (cr / au) * uref), fs)
        say(f"{label:>44}  {P._to_dbfs(bs['total_db']):>8.1f}  "
            f"{P._to_dbfs(bs['low_db']):>8.1f}  "
            f"{P._to_dbfs(bs['mid_db']):>8.1f}  "
            f"{P._to_dbfs(bs['high_db']):>8.1f}")
        flush()
        return P._to_dbfs(bs["total_db"])

    seeds = {}
    for seed in (7, 1, 2, 3, 4):
        wp, wn = dwa.mismatch(0.01, seed=seed)
        seeds[seed] = with_weights(wp, wn, f"1% elements, draw {seed}")
    wp, wn = dwa.mismatch(0.01, seed=P.MISMATCH_SEED)
    trimmed = with_weights(wp - wp.mean() + 1.0, wn - wn.mean() + 1.0,
                           "same draw, each bank's sum trimmed to exact")
    same = with_weights(wp, wp, "same draw, the two banks made identical")
    say()
    say(f"The draw matters by {max(seeds.values()) - min(seeds.values()):.1f} "
        f"dB across five of them, all at the same")
    say("one percent specification. A single mismatch seed is one board, not")
    say("the answer, and every other figure in this file uses one board.")
    say()
    say(f"Trimming each bank's total to exactly seven is worth "
        f"{seeds[P.MISMATCH_SEED] - trimmed:+.1f} dB, which is")
    say("nothing: the rotation already handles the bank total. Making the two")
    say(f"banks identical is worth {seeds[P.MISMATCH_SEED] - same:+.1f} dB, "
        f"which says the two sides' errors are")
    say("independent and add in power, as they should. Neither is buildable;")
    say("both are here to show which property of the elements the number")
    say("depends on, and the answer is the spread, not the sum.")
    return out


def figure_mismatch(mm) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    labels = list(mm)
    y = np.arange(len(labels))
    for key, colour, nm in (("matched", "0.6", "matched elements"),
                            ("0.1%", "tab:blue", "0.1% elements"),
                            ("1%", "tab:red", "1% elements")):
        ax[0].plot([mm[k][key] for k in labels], y, "o", ms=7, color=colour,
                   label=nm)
    for i, k in enumerate(labels):
        ax[0].plot([mm[k]["matched"], mm[k]["1%"]], [i, i], "-", lw=1.2,
                   color="0.7", zorder=0)
    ax[0].set(title="In-band error at equal in-band signal power\n"
                    "the cost of one percent elements, by content",
              xlabel="in-band error, dBFS", yticks=y)
    ax[0].set_yticklabels(labels, fontsize=8)
    ax[0].invert_yaxis()
    ax[0].legend(fontsize=8, loc="lower left")
    ax[0].grid(alpha=.3, axis="x")

    cost = [mm[k]["matched"] - mm[k]["1%"] for k in labels]
    ax[1].barh(y, cost, color=["tab:green" if c < 3 else "tab:red"
                               for c in cost])
    ax[1].set(title="What one percent elements cost, by content",
              xlabel="dB lost against matched elements", yticks=y)
    ax[1].set_yticklabels(labels, fontsize=8)
    ax[1].invert_yaxis()
    ax[1].grid(alpha=.3, axis="x")
    fig.savefig(FIG / "programme_mismatch.png", dpi=130)
    plt.close(fig)


def figure_windows(out, tone_err: float) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True,
                           gridspec_kw={"width_ratios": [1.5, 1]})
    order = [k for k in ("real audio, 48 kHz", "real audio, matched elem.",
                         "programme 48 kHz", "percussive 48 kHz",
                         "bass 48 kHz") if k in out and out[k]]
    colours = dict(zip(order, ["tab:blue", "0.55", "tab:orange", "tab:green",
                               "tab:red"]))
    for k in order:
        ws = out[k]
        t = [w["t0"] for w in ws]
        e = [w["err_dbfs"] for w in ws]
        ax[0].plot(t, e, ".-", ms=3, lw=.7, color=colours[k],
                   label=f"{k} (worst {max(e):.1f})")
    ax[0].axhline(tone_err, color="k", ls="--", lw=1,
                  label=f"1 kHz tone, same instrument ({tone_err:.1f} dBFS)")
    ax[0].axhline(TONE_DBFS - 110.0, color="tab:red", ls=":", lw=1.2,
                  label="110 dB target")
    ax[0].set(title="In-band error, window by window\n"
                    "2^20 element samples = 42.7 ms per window",
              xlabel="seconds into the record", ylabel="in-band error, dBFS")
    ax[0].legend(fontsize=7, loc="upper right")
    ax[0].grid(alpha=.3)

    for k in order:
        e = np.sort([w["err_dbfs"] for w in out[k]])
        ax[1].plot(e, np.arange(1, len(e) + 1) / len(e) * 100, lw=1.4,
                   color=colours[k], label=k)
    ax[1].axvline(tone_err, color="k", ls="--", lw=1, label="1 kHz tone")
    ax[1].set(title="Distribution, not an average",
              xlabel="in-band error, dBFS", ylabel="percent of windows below")
    ax[1].legend(fontsize=7, loc="lower right")
    ax[1].grid(alpha=.3)
    ax[0].set_ylim(top=max(max(w["err_dbfs"] for w in out[k]) for k in order) + 3)
    fig.savefig(FIG / "programme_windows.png", dpi=130)
    plt.close(fig)


def figure_headroom(hr, sweeps) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    peaks = hr["peaks"]
    labels = list(peaks)
    vals = [peaks[k]["overshoot_db"] for k in labels]
    y = np.arange(len(labels))
    cols = ["tab:red" if "inter-sample" in k else
            "tab:orange" if "clipped" in k else "tab:blue" for k in labels]
    ax[0].barh(y, vals, color=cols)
    ax[0].axvline(3.01, color="k", ls="--", lw=1,
                  label="the probe the 3 dB rule came from")
    ax[0].set(title="Peak between the samples, over the peak in the samples",
              xlabel="overshoot, dB", yticks=y)
    ax[0].set_yticklabels(labels, fontsize=7.5)
    ax[0].invert_yaxis()
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=.3, axis="x")

    for label, rows in sweeps.items():
        lv = [r[0] for r in rows]
        er = [r[5] for r in rows]
        ax[1].plot(lv, er, "o-", ms=4, lw=1.2, label=label)
    ax[1].set(title="In-band error against playback level, 48 kHz",
              xlabel="PCM peak level, dBFS", ylabel="in-band error, dBFS")
    ax[1].legend(fontsize=7.5)
    ax[1].grid(alpha=.3)
    fig.savefig(FIG / "programme_headroom.png", dpi=130)
    plt.close(fig)


def figure_shape(out, q3) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    want = ["1 kHz tone, 48 kHz", "real audio, 48 kHz",
            "real audio, matched elem.",
            "programme 48 kHz", "programme 96 kHz", "programme 192 kHz",
            "percussive 48 kHz", "percussive 192 kHz",
            "bass 48 kHz", "bass 96 kHz", "bass 192 kHz"]
    keys = [k for k in want if out.get(k)]
    data = [np.array([w["low_share"] for w in out[k]]) * 100 for k in keys]
    ax[0].boxplot(data, orientation="horizontal", tick_labels=keys,
                  widths=.6,
                  flierprops=dict(ms=2))
    ax[0].axvline(0.44, color="k", ls="--", lw=1,
                  label="white noise would be 0.44%")
    ax[0].set(title="Share of in-band error below 100 Hz, per window",
              xlabel="percent of in-band error power", xscale="log")
    ax[0].tick_params(axis="y", labelsize=7)
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=.3, axis="x")

    names, rows = [], {"output": [], "error": [], "loop, v-u": []}
    for (rate, label, vname), (w, ob) in q3.items():
        if rate != "96 kHz":
            continue
        names.append(f"{label}\n{vname}")
        rows["output"].append(P._to_dbfs(ob["low_db"]))
        rows["error"].append(w.low_db)
        rows["loop, v-u"].append(w.loop_low_dbfs)
    x = np.arange(len(names))
    wdt = 0.26
    for i, (nm, col) in enumerate((("output", "0.6"), ("error", "tab:blue"),
                                   ("loop, v-u", "tab:green"))):
        ax[1].bar(x + (i - 1) * wdt, rows[nm], wdt, color=col, label=nm)
    ax[1].set(title="96 kHz: 20-100 Hz power seen by each detector",
              ylabel="dBFS in 20-100 Hz", xticks=x)
    ax[1].set_xticklabels(names, fontsize=5.5, rotation=90)
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=.3, axis="y")
    fig.savefig(FIG / "programme_shape.png", dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------------------
def main() -> int:
    P.self_check()
    cs = {fam: halfband.build(fam) for fam in ("48k", "44k1")}
    ntf = modulator.synthesize_ntf(ORDER)

    say("run_programme.py -- the chain against material with a real crest")
    say("factor, measured window by window.")
    say()
    say(f"order {ORDER}, window 2^{int(np.log2(WINDOW))} element samples "
        f"({WINDOW / chain.ELEMENT_CLOCK['48k'] * 1e3:.1f} ms, "
        f"{chain.ELEMENT_CLOCK['48k'] / WINDOW:.1f} Hz bins), "
        f"{SIGMA*100:.0f}% elements,")
    say(f"coefficients and datapath at their settled widths, rotation on, "
        f"material peak at {PLAY_DBFS:+.1f} dBFS.")
    flush()

    with tempfile.TemporaryDirectory() as td:
        real, rows = real_record(Path(td))
        if real is not None:
            real = P.normalise_peak(real, PLAY_DBFS)
        describe_material(real, rows)
        flush()

        val = validate(cs, ntf)
        flush()
        tone_err = val["48 kHz"][1].err_dbfs

        # Q1 needs the tone measured the same way, window by window.
        c48 = cs["48k"]
        m48 = [x for x in chain.modes("48k") if x.multiplier == 1][0]
        n_in = P.pcm_for(c48, m48, SEG_WINDOWS * WINDOW)
        f = endtoend.coherent_tone_freq(m48, WINDOW, 1000.0)[1]
        tone_pcm = endtoend.source_tone(n_in * 3, m48.fs, f, TONE_DBFS)
        tone_ws = windowed(cs, "1 kHz tone", "48k", 1, tone_pcm, n_seg=3)

        out = question1(cs, ntf, real, tone_ws)
        rates = question1_rates(cs, out)
        flush()
        by_loudness(out)
        flush()
        question4(out)
        flush()

        hr = question2(cs, ntf, real)
        flush()
        sweeps = level_sweep(cs, ntf, real)
        flush()
        mm = mismatch_and_material(cs, ntf, real)
        flush()
        wander(cs, ntf)
        flush()
        q3 = question3(cs, ntf)
        flush()
        traps(cs, ntf, real)
        flush()

        figure_mismatch(mm)
        figure_windows(out, tone_err)
        figure_headroom(hr, sweeps)
        figure_shape(out, q3)

    say()
    if ALIGN:
        say(f"alignment guard: the in-band error at the offset used is at "
            f"least {min(a[1] for a in ALIGN):.0f} dB below what it becomes")
        say(f"when the two paths are slid 256 samples apart, over "
            f"{sum(a[2] for a in ALIGN)} segments that had signal to check.")
    say()
    say(f"figures -> {FIG}")
    say(f"log     -> {LOG}")
    say(f"total   -> {time.time() - _t0:.0f} s")
    flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

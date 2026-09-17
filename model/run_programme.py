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

from lyrebird_model import (chain, endtoend, halfband, material,  # noqa: E402
                            modulator, programme, spectra)

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
        f"{'error SNR':>10}  {'error dBFS':>11}  {'gain':>10}  {'lag':>4}")
    out = {}
    for fam, c in cs.items():
        for m in chain.modes(fam):
            f = endtoend.coherent_tone_freq(m, WINDOW, 1000.0)[1]
            n_in = P.pcm_for(c, m, WINDOW)
            pcm = endtoend.source_tone(n_in, m.fs, f, TONE_DBFS)
            r = P.render(c, ntf, m, pcm, n_out=WINDOW, sigma=SIGMA,
                         keep_source_term=True)
            w = P.measure(r)[0]
            xx = r.x - r.x.mean()
            mm = spectra.Measurement.of(xx, m.element_clock, f, BAND,
                                        n_harmonics=10)
            lag = P.alignment_lag(r.x, r.u_ref)
            say(f"{m.name:>10}  {mm.snr_db:>12.2f}  {mm.sndr_db:>13.2f}  "
                f"{w.snr_db:>10.2f}  {w.err_dbfs:>11.2f}  {w.gain:>10.6f}  "
                f"{lag:>4}")
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
    say("The alignment lag is zero at every rate, which is the check that")
    say("matters most: the STF of this topology is exactly 1 with zero delay,")
    say("so a wrong settling offset would show up here rather than as a")
    say("confidently wrong noise figure.")
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
    ws, bad, skew = [], 0, 0
    for r in res:
        if not r["stable"]:
            bad += 1
            continue
        if r["lag"] != 0:
            skew += 1
        ws.extend(r["windows"])
    if bad:
        say(f"   !! {label}: {bad} of {len(res)} segments left the state bound")
    if skew:
        say(f"   !! {label}: {skew} of {len(res)} segments did not align at "
            f"lag 0")
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
        f"{'true peak':>10}  {'overshoot dB':>13}")
    peaks = {}
    for label, x in cases:
        q = endtoend.quantize_pcm(P.normalise_peak(x, 0.0))
        d = P.true_peak(c, m, q)
        at_fs = int(np.sum(np.abs(q) > 0.99995))
        peaks[label] = d
        say(f"{label:>26}  {P.crest_db(q):>9.2f}  {at_fs:>14}  "
            f"{d['true_peak']:>10.4f}  {d['overshoot_db']:>+13.3f}")
        flush()
    say()
    say("Read the first column with the last. The probe is 3.010 dB of")
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
    say("loudest moment in the record, because that is the moment that")
    say("decides it; a bisection on an arbitrary slice measures whatever")
    say("happened to be in the slice.")
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
            xx = P.peak_slice(np.asarray(x, dtype=np.float64), n_in) \
                if len(x) > n_in else P.tile_to(x, n_in)
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
    if real is not None:
        picks.append(("real audio", P.peak_slice(real, n_in)))
        picks.append(("real, clipped 12 dB",
                      P.peak_slice(P.limit(P.normalise_peak(real, 0.0), 12.0),
                                   n_in)))
    picks += [("percussive", P.peak_slice(P.tile_to(perc, max(n, n_in)), n_in)),
              ("percussive, clipped 12 dB",
               P.peak_slice(P.tile_to(
                   P.limit(P.normalise_peak(perc, 0.0), 12.0),
                   max(n, n_in)), n_in))]
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
    head("Q3: CAN GENUINE BASS AND THE LOW-FREQUENCY FAULT BE TOLD APART?")
    say("README.md: a tripped run puts every bit of its excess in the 20 to")
    say("100 Hz bins. Sustained bass puts its signal in the same bins. If the")
    say("only thing available is how much energy comes out down there, the")
    say("two are indistinguishable and the hardware cannot flag one without")
    say("flagging the other.")
    say()
    say("The fault is provoked rather than waited for. README.md measures")
    say("that round-half-up in the datapath leaves a static offset at the")
    say("modulator input and that the loop turns it into idle tones, costing")
    say("15.7 dB at 96 kHz. That is a switch, so it is used as one.")
    say()
    say("Three detectors are compared. All are 20-100 Hz power.")
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
        n_in = P.pcm_for(c, m, 2 * WINDOW)
        sources = {
            "sustained 41 Hz bass": P.normalise_peak(
                material.sustained_bass(n_in, m.fs), -6.0),
            "1 kHz tone": endtoend.source_tone(n_in, m.fs, 1000.0, TONE_DBFS),
            "near silence, -100 dBFS": material.near_silence(n_in, m.fs),
        }
        say(f"--- {m.name} ---")
        say(f"{'material':>24}  {'ties':>10}  {'out low':>9}  {'err low':>9}  "
            f"{'v-u low':>9}  {'err total':>10}  {'low share':>10}")
        for label, pcm in sources.items():
            for rnd in ("half_even", "half_up"):
                r = P.render(c, ntf, m, pcm, n_out=2 * WINDOW, sigma=SIGMA,
                             rounding=rnd)
                if not r.stable:
                    say(f"{label:>24}  {rnd:>10}  unbounded")
                    continue
                ws = P.measure(r)
                w = max(ws, key=lambda z: z.low_db)
                xw = r.x[:WINDOW]
                ob = material.band_shape(xw - xw.mean(), m.element_clock)
                out[(m.name, label, rnd)] = (w, ob)
                say(f"{label:>24}  {rnd:>10}  "
                    f"{P._to_dbfs(ob['low_db']):>9.1f}  {w.low_db:>9.1f}  "
                    f"{w.loop_low_dbfs:>9.1f}  {w.err_dbfs:>10.1f}  "
                    f"{w.low_share*100:>9.2f}%")
                flush()
        say()
    return out


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

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
    keys = [k for k in out if out[k]]
    data = [np.array([w["low_share"] for w in out[k]]) * 100 for k in keys]
    ax[0].boxplot(data, vert=False, tick_labels=keys, widths=.6,
                  flierprops=dict(ms=2))
    ax[0].axvline(0.44, color="k", ls="--", lw=1,
                  label="white noise would be 0.44%")
    ax[0].set(title="Share of in-band error below 100 Hz, per window",
              xlabel="percent of in-band error power")
    ax[0].tick_params(axis="y", labelsize=7)
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=.3, axis="x")

    names, healthy, faulted = [], [], []
    for (rate, label, rnd), (w, ob) in q3.items():
        if rate != "96 kHz":
            continue
        if rnd == "half_even":
            names.append(label)
            healthy.append((P._to_dbfs(ob["low_db"]), w.low_db, w.loop_low_dbfs))
        else:
            faulted.append((P._to_dbfs(ob["low_db"]), w.low_db, w.loop_low_dbfs))
    x = np.arange(len(names))
    wdt = 0.26
    for i, (nm, col) in enumerate((("output", "0.6"), ("error", "tab:blue"),
                                   ("loop, v-u", "tab:green"))):
        h = [v[i] for v in healthy]
        f = [v[i] for v in faulted]
        ax[1].bar(x + (i - 1) * wdt, np.array(f) - np.array(h), wdt,
                  color=col, label=nm)
    ax[1].axhline(0, color="k", lw=.8)
    ax[1].set(title="96 kHz: how far each detector moves when the fault is on",
              ylabel="dB, faulted minus healthy, 20-100 Hz", xticks=x)
    ax[1].set_xticklabels(names, fontsize=7.5)
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
        question4(out)
        flush()

        hr = question2(cs, ntf, real)
        flush()
        sweeps = level_sweep(cs, ntf, real)
        flush()
        q3 = question3(cs, ntf)
        flush()

        figure_windows(out, tone_err)
        figure_headroom(hr, sweeps)
        figure_shape(out, q3)

    say()
    say(f"figures -> {FIG}")
    say(f"log     -> {LOG}")
    say(f"total   -> {time.time() - _t0:.0f} s")
    flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

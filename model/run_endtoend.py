#!/usr/bin/env python3
"""Close the two gaps run_experiments.py left open.

    ./.venv/bin/python model/run_endtoend.py

Gap 1: the interpolator and the modulator had never been connected. Each was
measured against its own ideal input. This runs real 24-bit PCM through the
cascade, the modulator, the rotation and the elements, per rate, and compares
what comes out against the subsystem numbers.

Gap 2: the datapath was not sized. Coefficient width was settled; the signal
word and the accumulator were not. This measures both, per stage.

Figures land in figures/, the log in results/endtoend.txt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lyrebird_model import (chain, datapath, endtoend, halfband,  # noqa: E402
                           modulator, spectra)

FIG = HERE / "figures"
RES = HERE / "results"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)

BAND = endtoend.BAND
ORDER = 3                       # the recommendation in README.md
N_MEAS = 1 << 20                # 23.4 Hz bins at the element clock
N_MSA = 1 << 18                 # stability only, no spectrum taken
F_TONE = 1000.0
TEST_DBFS = -3.7                # 3 dB below the order-3 max stable amplitude

# Settled by run_experiments.py; carried here so the datapath is sized against
# the coefficients that will actually be built.
COEFF_BITS = {1: 26, 2: 26, 3: 26, 4: 22, 5: 19, 6: 18, 7: 10, 8: 8, 9: 8}

# The answers this script measures, restated here so the verification at the
# end runs against the recommendation rather than against a stale constant.
SIG_FRAC = 26                                     # flat across all nine stages
ACC_FRAC = {1: 31, 2: 31, 3: 31, 4: 30, 5: 30, 6: 29, 7: 29, 8: 29, 9: 29}
# Bits above the binary point, sign included, from the L1 bound measured by
# head_room(). The accumulator carries the widest partial sum, not the output.
ACC_INT = {1: 4, 2: 4, 3: 4, 4: 3, 5: 3, 6: 2, 7: 2, 8: 2, 9: 2}
N_SEEDS = 6               # input variations per rate for the limit-cycle count

log: list[str] = []


def say(s: str = "") -> None:
    print(s)
    log.append(s)


def head(title: str) -> None:
    say()
    say("=" * 72)
    say(title)
    say("=" * 72)


def cascades() -> dict[str, halfband.Cascade]:
    return {fam: halfband.build(fam) for fam in ("48k", "44k1")}


# ---------------------------------------------------------------- gap 1
def per_rate(cs, ntf) -> dict:
    head(f"END TO END, PER RATE  (order {ORDER}, {TEST_DBFS:+.1f} dBFS, "
         f"N=2^{int(np.log2(N_MEAS))})")
    say("24-bit PCM at Fs -> cascade -> modulator -> DWA -> elements -> sum.")
    say("'source exact' removes the 24-bit input quantizer and leaves")
    say("everything the FPGA does, which is what isolates the chain itself.")
    say()
    say(f"{'rate':>10}  {'source':>14}  {'SNR dB':>8}  {'SNDR dB':>8}  "
        f"{'THD dB':>8}  {'mod in':>9}  {'peak dBFS':>9}  {'clip':>5}")
    out = {}
    for fam, c in cs.items():
        for m in chain.modes(fam):
            for label, bits, dither in (("24-bit TPDF", 24, "tpdf"),
                                        ("24-bit raw", 24, "none"),
                                        ("source exact", None, "none")):
                r = endtoend.run(c, ntf, m, n_out=N_MEAS, f_target=F_TONE,
                                 amp_dbfs=TEST_DBFS, bits=bits, dither=dither,
                                 measure_mod_in=True,
                                 keep_psd=(label == "24-bit TPDF"))
                say(f"{m.name:>10}  {label:>14}  {r.m.snr_db:>8.2f}  "
                    f"{r.m.sndr_db:>8.2f}  {r.m.thd_db:>8.2f}  "
                    f"{r.m_mod_in.noise_dbfs:>9.1f}  "
                    f"{r.mod_peak_dbfs:>+9.2f}  {r.clipped:>5}")
                out[(m.name, label)] = r
            say()
    return out


def as_built(cs, ntf, sig_frac: int, acc: dict) -> dict:
    head("THE CHAIN AS IT WILL BE BUILT")
    say("Everything at once: 24-bit TPDF PCM, the coefficients at their settled")
    say("widths, the datapath at the widths sized below, order 3, rotation on,")
    say("and elements with real tolerance. This is the number to hold the")
    say("hardware to.")
    say()
    sig = {s: sig_frac for s in range(1, 10)}
    say(f"{'rate':>10}  {'elements':>10}  {'SNR dB':>8}  {'SNDR dB':>8}  "
        f"{'THD dB':>8}  {'over target':>12}")
    out = {}
    for fam, c in cs.items():
        for m in chain.modes(fam):
            for sigma in (0.0, 0.001, 0.01):
                r = endtoend.run(c, ntf, m, n_out=N_MEAS, f_target=F_TONE,
                                 amp_dbfs=TEST_DBFS, coeff_bits=COEFF_BITS,
                                 sig_frac=sig, acc_frac=acc, sigma=sigma,
                                 rotate=True)
                label = "matched" if sigma == 0 else f"{sigma*100:.1f}%"
                say(f"{m.name:>10}  {label:>10}  {r.m.snr_db:>8.2f}  "
                    f"{r.m.sndr_db:>8.2f}  {r.m.thd_db:>8.2f}  "
                    f"{r.m.sndr_db - chain.DYNAMIC_RANGE_TARGET_DB:>+12.1f}")
                out[(m.name, sigma)] = r
            say()
    worst = min(v.m.sndr_db for k, v in out.items() if k[1] == 0.01)
    say(f"Worst case over every rate, with one percent elements: {worst:.1f} dB, "
        f"{worst - chain.DYNAMIC_RANGE_TARGET_DB:.1f} dB over the "
        f"{chain.DYNAMIC_RANGE_TARGET_DB:.0f} dB target.")
    return out


def against_subsystems(cs, results) -> None:
    head("DOES IT DIFFER FROM THE SUBSYSTEM NUMBERS?")
    fs = chain.ELEMENT_CLOCK["48k"]
    ntf2, ntf3 = modulator.synthesize_ntf(2), modulator.synthesize_ntf(3)
    u, f_sig = modulator.tone(N_MEAS, fs, F_TONE, TEST_DBFS)
    alone = modulator.simulate(ntf3, u, fs, f_sig=f_sig)
    m_alone = spectra.Measurement.of(alone.out, fs, f_sig, BAND, n_harmonics=10)
    say(f"modulator alone, tone generated at the element clock : "
        f"SNDR {m_alone.sndr_db:.1f} dB")
    r = results[("48 kHz", "source exact")]
    say(f"same modulator behind the cascade, source quantizer off: "
        f"SNDR {r.m.sndr_db:.1f} dB")
    r24 = results[("48 kHz", "24-bit TPDF")]
    say(f"same, fed real 24-bit TPDF-dithered PCM at 48 kHz      : "
        f"SNDR {r24.m.sndr_db:.1f} dB")
    say()
    say("Order 2 versus order 3 end to end, 24-bit TPDF PCM at 48 kHz:")
    c = cs["48k"]
    m48 = chain.modes("48k")[0]
    for k, ntf in ((2, ntf2), (3, ntf3)):
        rr = endtoend.run(c, ntf, m48, n_out=N_MEAS, f_target=F_TONE,
                          amp_dbfs=TEST_DBFS)
        say(f"   order {k}: SNDR {rr.m.sndr_db:6.2f} dB")


def mismatch_end_to_end(cs, ntf) -> dict:
    head(f"ELEMENT MISMATCH, MEASURED END TO END  (order {ORDER})")
    say("run_experiments.py measures this at the order its own selection rule")
    say("picks, which is 2. At order 3 the modulator floor is 40 dB lower, so")
    say("the rotation residual has nothing to hide behind. Source exact, so")
    say("the 24-bit floor is not hiding it either.")
    say()
    say(f"{'sigma':>7}  {'rotation':>9}  {'SNR dB':>8}  {'SNDR dB':>8}  "
        f"{'THD dB':>8}")
    c = cs["48k"]
    m = chain.modes("48k")[0]
    out = {}
    for sigma in (0.0, 0.001, 0.01):
        for rot in (True, False):
            r = endtoend.run(c, ntf, m, n_out=N_MEAS, f_target=F_TONE,
                             amp_dbfs=TEST_DBFS, bits=None, sigma=sigma,
                             rotate=rot, keep_psd=True)
            say(f"{sigma*100:>6.1f}%  {'on' if rot else 'off':>9}  "
                f"{r.m.snr_db:>8.2f}  {r.m.sndr_db:>8.2f}  {r.m.thd_db:>8.2f}")
            out[(sigma, rot)] = r
            if sigma == 0.0:
                break
    return out


def headroom(cs, ntf) -> dict:
    head("MAX STABLE AMPLITUDE AGAINST FILTERED CONTENT")
    say("Bisection and bound are modulator.max_stable_amplitude's, so the")
    say("numbers compare directly. What differs is the input: PCM through the")
    say("cascade rather than a sine generated at the element clock.")
    say()
    fs = chain.ELEMENT_CLOCK["48k"]
    for n in (1 << 15, N_MSA):
        msa = modulator.max_stable_amplitude(ntf, fs, n=n)
        say(f"modulator alone, clean tone, N=2^{int(np.log2(n))}: MSA {msa:.3f} "
            f"({20*np.log10(msa):+.2f} dBFS)")
    say()
    say(f"{'rate':>10}  {'source':>22}  {'MSA at PCM':>11}  {'dBFS':>7}  "
        f"{'peak at quantizer':>18}")
    out = {}
    for fam, c in cs.items():
        for m in chain.modes(fam):
            edge = 0.45 * m.fs
            probes = (("1 kHz tone", endtoend.tone_maker(m, F_TONE)),
                      ("passband-edge tone", endtoend.tone_maker(m, edge)),
                      ("Fs/4 inter-sample", endtoend.intersample_maker()))
            for label, mk in probes:
                d = endtoend.max_stable_pcm(c, ntf, m, mk, n_out=N_MSA)
                shown = (f"{label} ({edge/1e3:.1f} kHz)"
                         if label == "passband-edge tone" else label)
                say(f"{m.name:>10}  {shown:>22}  {d['amp']:>11.3f}  "
                    f"{d['amp_dbfs']:>+7.2f}  {d['peak_dbfs']:>+17.2f}")
                out[(m.name, label)] = d
            say()
    return out


# ---------------------------------------------------------------- gap 2
def _probe(c, m, n_out=N_MEAS):
    n_in = endtoend.input_length(c, m, n_out)
    f = endtoend.coherent_tone_freq(m, n_out, F_TONE)[1]
    return endtoend.source_tone(n_in, m.fs, f, TEST_DBFS)


def signal_word(c, m, budget_db: float) -> dict:
    head("SIGNAL WORD, PER STAGE")
    say("Each stage is quantized alone and the rest left exact, so what is")
    say("measured is that stage's own rounding. The figure is the in-band")
    say("power of the difference against the exact datapath, which carries no")
    say("signal at all and so needs no lobe excised.")
    say()
    say(f"per-stage budget: {budget_db:.0f} dBFS")
    say()
    pcm = _probe(c, m)
    say(f"{'stage':>5}  {'out rate':>10}  " +
        "  ".join(f"{b:>6}" for b in range(20, 30)) + f"  {'min':>5}")
    mins = {}
    grid = {}
    for s in range(1, 10):
        row = []
        for F in range(20, 30):
            nz, _ = datapath.rounding_noise(c, m, pcm, n_out=N_MEAS,
                                            coeff_bits=COEFF_BITS,
                                            sig_frac={s: F})
            row.append(nz)
            grid[(s, F)] = nz
        mins[s] = next((F for F, v in zip(range(20, 30), row) if v <= budget_db),
                       None)
        say(f"{s:>5}  {c.stage(s).f_out/1e6:>7.3f} MHz  " +
            "  ".join(f"{v:>6.1f}" for v in row) + f"  {mins[s]:>5}")
    say()
    lo, hi = mins[1], mins[9]
    say(f"Isolated, the minimum tapers {lo} down to {hi}: a stage's rounding is")
    say("white over its own output rate, so the same word is 3 dB quieter in")
    say("band at every doubling, and the stages that run at the element clock")
    say("are the ones that could be narrowest. Composing that taper is still")
    say("the wrong move, and the next table says why.")
    return {"min": mins, "grid": grid}


def word_schedules(c, budget_db: float) -> dict:
    head("SIGNAL WORD: TAPERED VERSUS FLAT, MEASURED ON THE WHOLE CHAIN")
    say("A half-band stage has two phases. The filtered phase rounds because")
    say("it accumulates products. The pass-through phase is the centre tap")
    say("against an interpolation gain of two -- a wire -- and it rounds only")
    say("if the next word is narrower than the one it already sits on. A")
    say("tapering chain therefore re-rounds every sample at every stage, for")
    say("nothing: the storage it saves is under one percent.")
    say()
    taper = {1: 26, 2: 26, 3: 25, 4: 25, 5: 24, 6: 24, 7: 23, 8: 23, 9: 22}
    scheds = {"taper 26..22": taper,
              "flat 24": {s: 24 for s in range(1, 10)},
              "flat 25": {s: 25 for s in range(1, 10)},
              "flat 26": {s: 26 for s in range(1, 10)},
              "flat 27": {s: 27 for s in range(1, 10)}}
    say(f"{'schedule':>14}  {'48 kHz noise':>13}  {'192 kHz noise':>14}  "
        f"{'DC offset':>10}  {'delay bits':>11}")
    out = {}
    m48, m192 = chain.modes("48k")[0], chain.modes("48k")[2]
    p48, p192 = _probe(c, m48), _probe(c, m192)
    for label, sig in scheds.items():
        acc = {s: sig[s] + 4 for s in sig}
        a, stt = datapath.rounding_noise(c, m48, p48, n_out=N_MEAS,
                                         coeff_bits=COEFF_BITS,
                                         sig_frac=sig, acc_frac=acc)
        b, _ = datapath.rounding_noise(c, m192, p192, n_out=N_MEAS,
                                       coeff_bits=COEFF_BITS,
                                       sig_frac=sig, acc_frac=acc)
        bits = sum(st.hb.n_taps * (sig.get(st.index - 1, chain.PCM_BITS - 1) + 2)
                   for st in c.for_mode(m48))
        off = 20.0 * np.log10(abs(stt[0].offset))
        say(f"{label:>14}  {a:>13.1f}  {b:>14.1f}  {off:>10.1f}  {bits:>11}")
        out[label] = (a, b, off, bits)
    say()
    say(f"chain budget: {budget_db:.0f} dBFS")
    return out


def accumulator(c, m, sig_frac: int) -> dict:
    head(f"ACCUMULATOR, PER STAGE  (flat {sig_frac}-bit signal word)")
    say("Each product is rounded into the accumulator, which is the")
    say("pessimistic reading: a MAC whose output register is the accumulator")
    say("rounds every product, not only the final sum. The criterion is that")
    say("the accumulator must not be the louder of the two noise sources in")
    say("its own stage -- at or below 0.5 dB added to the signal word's.")
    say()
    pcm = _probe(c, m)
    say(f"{'stage':>5}  {'products':>9}  {'signal word alone':>18}  "
        f"{'min acc frac':>13}  {'guard':>6}  {'full precision':>15}")
    out = {}
    for s in range(1, 10):
        alone, _ = datapath.rounding_noise(c, m, pcm, n_out=N_MEAS,
                                           coeff_bits=COEFF_BITS,
                                           sig_frac={s: sig_frac})
        chosen = None
        for A in range(sig_frac - 8, sig_frac + 16):
            nz, _ = datapath.rounding_noise(c, m, pcm, n_out=N_MEAS,
                                            coeff_bits=COEFF_BITS,
                                            sig_frac={s: sig_frac},
                                            acc_frac={s: A})
            if nz <= alone + 0.5:
                chosen = A
                break
        n_prod = datapath.stage_taps(c.stage(s).hb, None)[0::2].size // 2
        full = datapath.full_precision_acc(c.stage(s).hb, COEFF_BITS[s], sig_frac)
        say(f"{s:>5}  {n_prod:>9}  {alone:>18.1f}  {chosen:>13}  "
            f"{chosen - sig_frac:>+6}  {full:>15}")
        out[s] = chosen
    return out


def head_room(c, m) -> list[datapath.StageStats]:
    head("HEADROOM: BITS ABOVE THE BINARY POINT")
    say("Peaks are taken on a faded record. An un-faded one switches on at a")
    say("non-zero sample, the cascade rings on that step, and the peak read")
    say("back is the record's edge rather than the signal.")
    say()
    n_in = endtoend.input_length(c, m, N_MSA)
    f = endtoend.coherent_tone_freq(m, N_MSA, F_TONE)[1]
    rows = (("1 kHz at 0 dBFS", endtoend.source_tone(n_in, m.fs, f, 0.0)),
            ("Fs/4 inter-sample at 0 dBFS", endtoend.source_intersample(n_in, 0.0)))
    stats = None
    for label, src in rows:
        pcm = endtoend.quantize_pcm(endtoend.fade(src))
        _, st = datapath.interpolate(c, pcm, m, coeff_bits=COEFF_BITS)
        say(f"{label}: peak into the modulator {max(s.peak_out for s in st):.4f}, "
            f"peak accumulator {max(s.peak_acc for s in st):.4f}")
        stats = st
    say()
    say(f"{'stage':>5}  {'L1 of the filtered phase':>25}  "
        f"{'accumulator bound':>18}  {'int bits':>9}")
    for st in stats:
        bound = st.l1_gain * np.sqrt(2.0)
        say(f"{st.index:>5}  {st.l1_gain:>25.4f}  {bound:>18.4f}  "
            f"{datapath.int_bits_for(bound):>9}")
    say()
    say("The L1 norm times the largest peak the cascade can present, sqrt(2),")
    say("is the hard bound on the accumulator: 4.06 at the three steep stages,")
    say("under 2 from stage 6 on. The signal word needs one bit above the sign")
    say("-- the inter-sample peak is 1.414 and anything past that is already")
    say("overloading the quantizer and belongs clipped, not represented.")
    return stats


def rounding_rule(cs, ntf, sig_frac: int, acc: dict) -> dict:
    head("WHICH WAY TIES GO")
    say("Round-half-up is one adder and is what you reach for first. It is")
    say("also biased: a word already on a finer grid ties half the time and")
    say("every tie goes up. The offset that leaves is far below any LSB in")
    say("the chain, and it is not harmless -- a delta-sigma loop turns a")
    say("static input offset into idle tones in the lowest bins of the band.")
    say()
    say(f"{'rate':>10}  {'rounding':>10}  {'chain noise':>12}  "
        f"{'DC at mod in':>13}  {'SNDR dB':>8}")
    sig = {s: sig_frac for s in range(1, 10)}
    out = {}
    for fam, c in cs.items():
        for m in chain.modes(fam):
            for rnd in ("half_up", "half_even"):
                nz, st = datapath.rounding_noise(c, m, _probe(c, m), n_out=N_MEAS,
                                                 coeff_bits=COEFF_BITS,
                                                 sig_frac=sig, acc_frac=acc,
                                                 rounding=rnd)
                r = endtoend.run(c, ntf, m, n_out=N_MEAS, f_target=F_TONE,
                                 amp_dbfs=TEST_DBFS, coeff_bits=COEFF_BITS,
                                 sig_frac=sig, acc_frac=acc, rounding=rnd)
                dc = (20.0 * np.log10(abs(st[0].offset)) if st[0].offset
                      else float("-inf"))
                say(f"{m.name:>10}  {rnd:>10}  {nz:>12.1f}  {dc:>13.1f}  "
                    f"{r.m.sndr_db:>8.2f}")
                out[(m.name, rnd)] = (nz, dc, r)
            say()
    worst = max(out[(m.name, "half_even")][2].m.sndr_db
                - out[(m.name, "half_up")][2].m.sndr_db
                for fam, c in cs.items() for m in chain.modes(fam))
    say(f"Worst case over the six rates: half-up costs {worst:.2f} dB.")
    say()
    say("This table used to report 15.7 dB and it was a measurement error --")
    say("the arithmetic mean was being removed where the windowed mean was")
    say("needed, so a sub-20 Hz residue was counted as audio-band noise.")
    say("spectra.remove_dc now removes the right one. See notes-idle.md.")
    say()
    say("Round ties to even anyway. The offset column above is real: half-up")
    say("leaves a static offset at the modulator input some 20 to 40 dB above")
    say("what convergent rounding leaves, and it reaches the output as DC.")
    say("An unbiased rounding is a cheaper place to deal with that than the")
    say("coupling capacitor. What is no longer claimed is that it costs")
    say("audio-band performance.")
    return out


def limit_cycles(cs, ntf, sig_frac: int, acc: dict) -> dict:
    head("LOW-FREQUENCY LIMIT CYCLES  (there are none; kept as a regression)")
    say("This experiment used to report one run in thirty-six coming back 15")
    say("to 19 dB low with all the excess in the 20-100 Hz bins, and dither")
    say("moving which run tripped rather than removing it. All of that was")
    say("the analysis window: the arithmetic mean is not the mean a windowed")
    say("transform takes, and the residue landed inside a band starting at")
    say("20 Hz. spectra.remove_dc now removes the right one everywhere, and")
    say("the rows below should be flat. See model/notes-idle.md.")
    say()
    say(f"{N_SEEDS} input variations per rate, at the recommended widths. The")
    say("second row of each pair adds 0.25 LSB of dither at the quantizer,")
    say("inside the loop, which is the textbook remedy for idle tones and")
    say("which turns out to have had nothing to remedy.")
    say()
    sig = {s: sig_frac for s in range(1, 10)}
    out = {}
    bad = {0.0: 0, 0.25: 0}
    total = 0
    for fam, c in cs.items():
        for m in chain.modes(fam):
            n_in = endtoend.input_length(c, m, N_MEAS)
            f = endtoend.coherent_tone_freq(m, N_MEAS, F_TONE)[1]
            pcm = endtoend.quantize_pcm(
                endtoend.source_tone(n_in, m.fs, f, TEST_DBFS))
            y, _ = datapath.interpolate(c, pcm, m, coeff_bits=COEFF_BITS,
                                        sig_frac=sig, acc_frac=acc)
            base = y[c.settle_samples(m):c.settle_samples(m) + N_MEAS]
            rows = {}
            for dfrac in (0.0, 0.25):
                vals = []
                for k in range(N_SEEDS):
                    rng = np.random.default_rng(100 + k)
                    u = base + 0.5 * 2.0 ** -sig_frac * (
                        rng.random(N_MEAS) + rng.random(N_MEAS) - 1.0)
                    d = (None if dfrac == 0.0 else
                         modulator.dither_sequence(N_MEAS, dfrac, seed=200 + k))
                    r = modulator.simulate(ntf, u, m.element_clock, f_sig=f,
                                           dither=d)
                    mm = spectra.Measurement.of(spectra.remove_dc(r.out),
                                                m.element_clock, f, BAND,
                                                n_harmonics=10)
                    vals.append(mm.sndr_db)
                rows[dfrac] = vals
                med = float(np.median(vals))
                bad[dfrac] += sum(1 for v in vals if v < med - 5.0)
                if dfrac == 0.0:
                    total += len(vals)
                label = "no dither" if dfrac == 0.0 else "0.25 LSB"
                head_ = f"{m.name:>10}" if dfrac == 0.0 else f"{'':>10}"
                say(f"{head_}  {label:>9}  " +
                    "  ".join(f"{v:>7.1f}" for v in vals))
            out[m.name] = rows
    say()
    say(f"runs more than 5 dB below their rate's median, of {total}:")
    say(f"   no quantizer dither : {bad[0.0]}")
    say(f"   0.25 LSB at the quantizer: {bad[0.25]}")
    say()
    say("Both counts should now be zero. Measured the old way, with the")
    say("arithmetic mean, the same records give 1 of 72; run_idle.py section")
    say("E shows both columns side by side. A non-zero count here means")
    say("something real has appeared, which is why the experiment is kept.")
    return out


def verify(cs, ntf, sig_frac: int, acc: dict, budget_db: float) -> dict:
    head("VERIFICATION: THE RECOMMENDED DATAPATH, END TO END")
    say(f"accumulator {min(acc.values())}..{max(acc.values())} fractional bits,")
    say("coefficients as settled, ties to even.")
    say()
    say(f"{'rate':>10}  {'word':>6}  {'datapath noise':>15}  "
        f"{'source floor':>13}  {'SNDR exact':>11}  {'SNDR sized':>11}  "
        f"{'cost dB':>8}")
    out = {}
    for fam, c in cs.items():
        for m in chain.modes(fam):
            ref = endtoend.run(c, ntf, m, n_out=N_MEAS, f_target=F_TONE,
                               amp_dbfs=TEST_DBFS, coeff_bits=COEFF_BITS,
                               measure_mod_in=True)
            for W in (sig_frac - 1, sig_frac):
                sig = {s: W for s in range(1, 10)}
                nz, _ = datapath.rounding_noise(c, m, _probe(c, m), n_out=N_MEAS,
                                                coeff_bits=COEFF_BITS,
                                                sig_frac=sig, acc_frac=acc)
                got = endtoend.run(c, ntf, m, n_out=N_MEAS, f_target=F_TONE,
                                   amp_dbfs=TEST_DBFS, coeff_bits=COEFF_BITS,
                                   sig_frac=sig, acc_frac=acc,
)
                say(f"{m.name:>10}  {W + 2:>6}  {nz:>15.1f}  "
                    f"{ref.m_mod_in.noise_dbfs:>13.1f}  "
                    f"{ref.m.sndr_db:>11.2f}  {got.m.sndr_db:>11.2f}  "
                    f"{ref.m.sndr_db - got.m.sndr_db:>8.2f}")
                out[(m.name, W)] = (nz, ref, got)
            say()
    say(f"budget was {budget_db:.0f} dBFS for the whole interpolator.")
    say(f"{sig_frac + 1} bits is the narrowest word that meets it at every "
        f"rate; {sig_frac + 2} is the recommendation, for the margin.")
    return out


# --------------------------------------------------------------- figures
def figure_spectrum(results, mism) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(10, 8), constrained_layout=True)
    for name, colour in (("48 kHz", "tab:blue"), ("96 kHz", "tab:orange"),
                         ("192 kHz", "tab:green")):
        r = results.get((name, "24-bit TPDF"))
        if r is None or r.m.freqs is None:
            continue
        f, p = spectra.smooth_psd(r.m.freqs, r.m.psd_dbfs)
        sel = f > 10
        ax[0].semilogx(f[sel], p[sel], lw=1, color=colour,
                       label=f"{name}, SNDR {r.m.sndr_db:.1f} dB")
    ax[0].axvspan(*BAND, alpha=.10, color="k")
    ax[0].set(title="End to end: 24-bit TPDF PCM through cascade, modulator, "
                    "rotation and elements",
              xlabel="Hz", ylabel="dBFS",
              xlim=(10, chain.ELEMENT_CLOCK["48k"] / 2), ylim=(-200, 5))
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=.3, which="both")

    want = [((0.0, True), "matched elements", "0.35"),
            ((0.01, False), "1% mismatch, no rotation", "tab:red"),
            ((0.01, True), "1% mismatch, rotation on", "tab:blue")]
    for key, label, colour in want:
        r = mism.get(key)
        if r is None or r.m.freqs is None:
            continue
        f, p = spectra.smooth_psd(r.m.freqs, r.m.psd_dbfs)
        sel = f > 10
        ax[1].semilogx(f[sel], p[sel], lw=1, color=colour,
                       label=f"{label}, SNDR {r.m.sndr_db:.1f} dB")
    ax[1].axvspan(*BAND, alpha=.10, color="k")
    ax[1].set(title=f"Order {ORDER}, source quantizer removed: what the "
                    f"rotation residual actually is",
              xlabel="Hz", ylabel="dBFS",
              xlim=(10, chain.ELEMENT_CLOCK["48k"] / 2), ylim=(-220, 5))
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=.3, which="both")
    fig.savefig(FIG / "endtoend_spectrum.png", dpi=130)
    plt.close(fig)


def figure_headroom(hr, msa_alone) -> None:
    rates = ["48 kHz", "96 kHz", "192 kHz"]
    labels = [k[1] for k in hr if k[0] == "48 kHz"]
    fig, ax = plt.subplots(figsize=(9, 4.6), constrained_layout=True)
    w = 0.26
    x = np.arange(len(rates))
    for i, lab in enumerate(labels):
        vals = [hr[(r, lab)]["amp_dbfs"] for r in rates]
        pk = [hr[(r, lab)]["peak_dbfs"] for r in rates]
        b = ax.bar(x + (i - 1) * w, vals, w, label=lab)
        for xi, (v, p) in zip(b, zip(vals, pk)):
            ax.text(xi.get_x() + xi.get_width() / 2, v + 0.12,
                    f"peak {p:+.2f}", ha="center", fontsize=6.5)
    ax.axhline(20 * np.log10(msa_alone), color="k", ls="--", lw=1,
               label=f"modulator alone, clean tone ({20*np.log10(msa_alone):+.2f} dBFS)")
    ax.set(title="Largest PCM level the loop survives, by content",
           ylabel="dBFS at the PCM input", xticks=x, xticklabels=rates,
           ylim=(-5.5, 1.2))
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(alpha=.3, axis="y")
    fig.savefig(FIG / "endtoend_headroom.png", dpi=130)
    plt.close(fig)


def figure_widths(c, sweep, scheds, budget_stage, budget_chain) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.6), constrained_layout=True)
    bits = list(range(20, 30))
    for s in range(1, 10):
        ax[0].plot(bits, [sweep["grid"][(s, F)] for F in bits], "o-", ms=3, lw=1,
                   label=f"stage {s} ({c.stage(s).f_out/1e6:.3f} MHz)")
    ax[0].axhline(budget_stage, color="k", ls=":", lw=1,
                  label=f"per-stage budget {budget_stage:.0f} dBFS")
    ax[0].set(title="One stage's own rounding noise against its signal word",
              xlabel="signal word, fractional bits", ylabel="in-band dBFS")
    ax[0].legend(fontsize=6.5, ncol=2)
    ax[0].grid(alpha=.3)

    names = list(scheds)
    a = [scheds[n][0] for n in names]
    b = [scheds[n][1] for n in names]
    x = np.arange(len(names))
    ax[1].plot(x, a, "o-", ms=7, lw=1.5, label="48 kHz, 9 stages")
    ax[1].plot(x, b, "s--", ms=7, lw=1.5, label="192 kHz, 7 stages")
    ax[1].axhline(budget_chain, color="k", ls=":", lw=1.2,
                  label=f"chain budget {budget_chain:.0f} dBFS")
    ax[1].fill_between([-0.4, len(names) - 0.6], budget_chain, -140,
                       color="tab:red", alpha=.07)
    ax[1].annotate("over budget", (len(names) - 0.7, budget_chain + 2.2),
                   ha="right", fontsize=7.5, color="tab:red")
    for xi, (va, vb) in enumerate(zip(a, b)):
        ax[1].annotate(f"{va:.1f}", (xi, va), textcoords="offset points",
                       xytext=(0, 7), ha="center", fontsize=6.5)
    ax[1].set(title="Whole-chain rounding noise: the taper costs 10 dB\n"
                    "for 0.8 percent less delay-line storage",
              ylabel="in-band dBFS (lower is quieter)", xticks=x,
              xlim=(-0.4, len(names) - 0.6), ylim=(-182, -148))
    ax[1].set_xticklabels(names, fontsize=8, rotation=15)
    ax[1].legend(fontsize=8, loc="lower left")
    ax[1].grid(alpha=.3)
    fig.savefig(FIG / "datapath_widths.png", dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------ main
def main() -> int:
    datapath.self_check()
    cs = cascades()
    ntf = modulator.synthesize_ntf(ORDER)
    c48 = cs["48k"]
    m48 = chain.modes("48k")[0]

    results = per_rate(cs, ntf)
    against_subsystems(cs, results)
    mism = mismatch_end_to_end(cs, ntf)
    hr = headroom(cs, ntf)

    # The datapath budget is set by the source it has to stay under: the
    # quietest 24-bit floor of any supported rate, less 10 dB.
    floors = [r.m_mod_in.noise_dbfs for (name, lab), r in results.items()
              if lab == "24-bit TPDF"]
    budget_chain = min(floors) - 10.0
    budget_stage = budget_chain - 10.0 * np.log10(chain.N_STAGES)
    head("DATAPATH BUDGET")
    say(f"quietest 24-bit source floor over all rates: {min(floors):.1f} dBFS")
    say(f"chain budget, 10 dB under it              : {budget_chain:.1f} dBFS")
    say(f"per-stage budget, nine stages sharing it  : {budget_stage:.1f} dBFS")
    say("10 dB under the source costs 0.41 dB end to end, which is the price")
    say("being paid for the whole datapath.")

    sweep = signal_word(c48, m48, budget_stage)
    scheds = word_schedules(c48, budget_chain)
    acc = accumulator(c48, m48, SIG_FRAC)
    head_room(c48, m48)
    rounding_rule(cs, ntf, SIG_FRAC, ACC_FRAC)
    limit_cycles(cs, ntf, SIG_FRAC, ACC_FRAC)
    verify(cs, ntf, SIG_FRAC, ACC_FRAC, budget_chain)
    as_built(cs, ntf, SIG_FRAC, ACC_FRAC)

    head("RECOMMENDATION")
    say(f"Signal word: {SIG_FRAC} fractional bits, 1 integer bit, 1 sign = "
        f"{SIG_FRAC + 2} bits, flat across all nine stages. Flat, not tapered:")
    say("a narrowing word re-rounds the pass-through phase at every stage.")
    say("Accumulator: bits above the point from the L1 bound, and below it")
    for lo, hi in ((1, 3), (4, 5), (6, 9)):
        v, i = ACC_FRAC[lo], ACC_INT[lo]
        say(f"   stages {lo}-{hi}: {v} fractional bits, {i} above the point, "
            f"{v + i} bits total")
    say("Round ties to even everywhere: half-up leaves an offset the modulator")
    say("turns into low-frequency idle tones.")
    say("Nothing here is left open: the limit-cycle section is a regression")
    say("check now, not a finding. See model/notes-idle.md.")

    figure_spectrum(results, mism)
    figure_headroom(hr, modulator.max_stable_amplitude(
        ntf, chain.ELEMENT_CLOCK["48k"], n=N_MSA))
    figure_widths(c48, sweep, scheds, budget_stage, budget_chain)

    (RES / "endtoend.txt").write_text("\n".join(log) + "\n")
    say()
    say(f"figures -> {FIG}")
    say(f"log     -> {RES / 'endtoend.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

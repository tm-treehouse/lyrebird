#!/usr/bin/env python3
"""Produce the measurements and figures the repository's open items need.

    ./.venv/bin/python model/run_experiments.py

Answers three questions with numbers rather than adjectives: what modulator
order to use, what the interpolation cascade should be, and whether the
rotation actually converts element mismatch into out-of-band noise.
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

from lyrebird_model import chain, dwa, halfband, modulator, spectra  # noqa: E402

FIG = HERE / "figures"
RES = HERE / "results"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)

FS = chain.ELEMENT_CLOCK["48k"]
BAND = (chain.AUDIO_LO, chain.AUDIO_HI)
# At the element clock a short FFT gives bins hundreds of Hz wide, so the
# whole audio band is a few dozen bins and removing signal and harmonic lobes
# leaves nothing to call noise. 2^20 gives 23.4 Hz bins, ~600 usable.
N_SWEEP = 1 << 20
N_FINAL = 1 << 21
F_TONE = 1000.0
N_HARM = 10
ORDERS = (2, 3, 4, 5)

log: list[str] = []


def say(s: str = "") -> None:
    print(s)
    log.append(s)


def run_at(ntf, n, amp_dbfs):
    u, f_sig = modulator.tone(n, FS, F_TONE, amp_dbfs)
    return modulator.simulate(ntf, u, FS, f_sig=f_sig), f_sig


# ---------------------------------------------------------------- filters
def filters():
    say("=" * 72)
    say("INTERPOLATION CASCADE  (48 kHz family)")
    say("=" * 72)
    c = halfband.build("48k")
    stages = c.distinct()
    say(f"{'stage':>5}  {'in kHz':>10}  {'out kHz':>10}  {'taps':>5}  "
        f"{'nonzero':>8}  {'ripple dB':>10}  {'stop dB':>8}")
    for st in stages:
        h = st.hb
        say(f"{st.index:>5}  {st.f_in/1e3:>10.1f}  {st.f_out/1e3:>10.1f}  "
            f"{h.n_taps:>5}  {h.n_nonzero:>8}  {h.ripple_db:>10.5f}  "
            f"{h.stopband_db:>8.1f}")
    say()
    for m in chain.modes("48k"):
        pe = c.passband_error(m)
        cost = c.cost(m)
        worst = min(c.image_suppression(m), key=lambda d: -d["worst_db"])
        say(f"  {m.fs/1e3:>6.1f} kHz  ratio {m.ratio:>4}  stages {m.n_stages}  "
            f"first {m.first_stage}")
        say(f"      passband ripple  {pe['ripple_pp_db']*1e6:.1f} micro-dB "
            f"p-p, {pe['at_hi_db']*1e6:+.1f} micro-dB at 20 kHz")
        say(f"      worst image      {worst['worst_db']:.1f} dB "
            f"at {worst['worst_f']/1e3:.1f} kHz")
        say(f"      multipliers      {cost['multipliers_at_clock']:.2f} at the "
            f"element clock, {cost['mac_rate_msps']:.1f} MAC/s")
        say(f"      storage          {cost['coeff_words']} coefficient words, "
            f"{cost['delay_words']} delay words")
        say(f"      group delay      {cost['group_delay_us']:.0f} us")
    say()

    fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), constrained_layout=True)
    fn = np.linspace(0, 0.5, 4000)
    for st in stages:
        H = 20*np.log10(np.maximum(np.abs(st.hb.response(fn)), 1e-13))
        ax[0].plot(fn, H, lw=1,
                   label=f"stage {st.index} ({st.hb.n_taps} taps)")
    ax[0].set(title="Half-band stages, normalised to each stage's input rate",
              xlabel="frequency / input rate", ylabel="dB", ylim=(-160, 5))
    ax[0].legend(fontsize=7, ncol=2); ax[0].grid(alpha=.3)

    for m in chain.modes("48k"):
        f = np.geomspace(10.0, m.element_clock/2, 4000)
        H = c.composite(m, f)
        ax[1].semilogx(f, H, lw=1, label=f"{m.fs/1e3:g} kHz")
    ax[1].axvspan(BAND[0], BAND[1], alpha=.12, color="k")
    ax[1].set(title="Composite cascade response per sample rate",
              xlabel="Hz", ylabel="dB", ylim=(-180, 10))
    ax[1].legend(fontsize=8); ax[1].grid(alpha=.3, which="both")
    fig.savefig(FIG / "interpolation.png", dpi=130)
    plt.close(fig)
    return c


# --------------------------------------------------------------- modulator
def order_sweep():
    say()
    say("=" * 72)
    say(f"MODULATOR ORDER SWEEP  (fs {FS/1e6:.3f} MHz, {F_TONE:.0f} Hz tone, "
        f"band {BAND[0]:.0f}-{BAND[1]:.0f} Hz, N=2^{int(np.log2(N_SWEEP))})")
    say("=" * 72)
    say(f"{'order':>5}  {'MSA':>6}  {'amp dBFS':>9}  {'SNR dB':>8}  "
        f"{'SNDR dB':>8}  {'stable':>7}")
    out = {}
    for k in ORDERS:
        ntf = modulator.synthesize_ntf(k)
        msa = modulator.max_stable_amplitude(ntf, FS)
        amp = 20*np.log10(max(msa, 1e-6)) - 3.0
        run, f_sig = run_at(ntf, N_SWEEP, amp)
        m = spectra.Measurement.of(run.out, FS, f_sig, BAND,
                                   n_harmonics=N_HARM)
        say(f"{k:>5}  {msa:>6.3f}  {amp:>9.1f}  {m.snr_db:>8.1f}  "
            f"{m.sndr_db:>8.1f}  {str(run.stable):>7}")
        out[k] = (msa, amp, m, ntf)
    return out


# ---------------------------------------------------------------- mismatch
def mismatch_study(order, ntf, amp_dbfs):
    say()
    say("=" * 72)
    say(f"ELEMENT MISMATCH AND ROTATION  (order {order}, "
        f"N=2^{int(np.log2(N_FINAL))})")
    say("=" * 72)
    run, f_sig = run_at(ntf, N_FINAL, amp_dbfs)
    codes = np.clip(np.asarray(run.codes, dtype=np.int64), 0, chain.N_ELEMENTS)

    p_rot, n_rot = dwa.differential(codes, rotate=True)
    p_fix, n_fix = dwa.differential(codes, rotate=False)
    load = dwa.loading(p_rot, n_rot)
    say(f"element loading: min {load.min()}, max {load.max()}  "
        f"(must be constant at {chain.N_ELEMENTS})")
    say()
    say(f"{'sigma':>7}  {'rotation':>9}  {'SNR dB':>8}  {'SNDR dB':>8}  "
        f"{'THD dB':>8}")

    curves = {}
    rows = []
    for sigma in (0.0, 0.001, 0.01):
        wp, wn = (None, None) if sigma == 0 else dwa.mismatch(sigma, seed=7)
        for label, (pp, nn) in (("on", (p_rot, n_rot)), ("off", (p_fix, n_fix))):
            x = dwa.normalise(dwa.analog(pp, nn, wp, wn))
            # Element mismatch produces a DC offset as well as noise. The
            # lowest FFT bins sit inside a band starting at 20 Hz, so leaving
            # it in counts a static output offset as audio-band noise. Real
            # hardware trims or AC-couples it.
            x = x - x.mean()
            m = spectra.Measurement.of(x, FS, f_sig, BAND,
                                       n_harmonics=N_HARM, keep_psd=True)
            say(f"{sigma*100:>6.1f}%  {label:>9}  {m.snr_db:>8.1f}  "
                f"{m.sndr_db:>8.1f}  {m.thd_db:>8.1f}")
            rows.append((sigma, label, m.snr_db, m.sndr_db, m.thd_db))
            curves[(sigma, label)] = m
            if sigma == 0:
                break   # with no mismatch the two are identical by construction
    return curves, rows, f_sig


def spectrum_figure(curves):
    fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    want = [((0.0, "on"), "matched elements", "0.35"),
            ((0.01, "off"), "1% mismatch, no rotation", "tab:red"),
            ((0.01, "on"), "1% mismatch, rotation on", "tab:blue")]
    for key, label, colour in want:
        m = curves.get(key)
        if m is None or m.freqs is None:
            continue
        f, p = spectra.smooth_psd(m.freqs, m.psd_dbfs)
        sel = f > 10
        ax.semilogx(f[sel], p[sel], lw=1, color=colour, label=label)
    ax.axvspan(BAND[0], BAND[1], alpha=.10, color="k")
    ax.set(title="Output spectrum: what the rotation is for",
           xlabel="Hz", ylabel="dBFS", xlim=(10, FS/2), ylim=(-200, 5))
    ax.legend(fontsize=9); ax.grid(alpha=.3, which="both")
    fig.savefig(FIG / "mismatch_rotation.png", dpi=130)
    plt.close(fig)


def order_figure(sweep):
    fig, ax = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    ks = sorted(sweep)
    ax.plot(ks, [sweep[k][2].snr_db for k in ks], "o-", label="SNR")
    ax.plot(ks, [sweep[k][2].sndr_db for k in ks], "s--", label="SNDR")
    ax.axhline(chain.DYNAMIC_RANGE_TARGET_DB, color="k", ls=":",
               label=f"target {chain.DYNAMIC_RANGE_TARGET_DB:.0f} dB")
    ax.set(title="In-band performance against modulator order",
           xlabel="modulator order", ylabel="dB", xticks=ks)
    ax.legend(); ax.grid(alpha=.3)
    fig.savefig(FIG / "order_sweep.png", dpi=130)
    plt.close(fig)


def main() -> int:
    filters()
    sweep = order_sweep()
    ok = [k for k in ORDERS if sweep[k][2].snr_db >= chain.DYNAMIC_RANGE_TARGET_DB]
    order = min(ok) if ok else max(ORDERS, key=lambda k: sweep[k][2].snr_db)
    say()
    say(f"--> lowest order meeting the {chain.DYNAMIC_RANGE_TARGET_DB:.0f} dB "
        f"target: {order}" if ok else f"--> no order met target; best is {order}")
    msa, amp, _, ntf = sweep[order]
    curves, _, _ = mismatch_study(order, ntf, amp)
    order_figure(sweep)
    spectrum_figure(curves)
    (RES / "measurements.txt").write_text("\n".join(log) + "\n")
    say()
    say(f"figures -> {FIG}")
    say(f"log     -> {RES / 'measurements.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

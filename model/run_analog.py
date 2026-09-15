#!/usr/bin/env python3
"""Settle the two analog placeholders the board cannot be fabricated without.

    ./.venv/bin/python model/run_analog.py

Question 1: the element resistor. The netlist carries 1 kohm, never chosen. It
sets the constant current 14 high elements draw from the 3.3 V reference rail
and, through the transimpedance stage, the output level -- and the two pull
opposite ways.

Question 2: the reconstruction filter. The modulator puts almost all of its
noise above the audio band and it is still there. This measures how much, where
it sits, how much of it an amplifier may be shown before it folds back into the
band, and therefore the order and the corners.

Figures land in figures/analog*.png, the log in results/analog.txt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import lfilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lyrebird_model import (analog, chain, datapath, dwa,  # noqa: E402
                            endtoend, halfband, modulator, spectra)

FIG = HERE / "figures"
RES = HERE / "results"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)

BAND = analog.BAND
ORDER = 3
N_MEAS = 1 << 20                # 23.4 Hz bins at the element clock
OVER = 4                        # zero-order hold oversampling, reaches 49 MHz
F_TONE = 1000.0
TEST_DBFS = -3.7
SIGMA = 0.01                    # one percent elements, the worst case in README

# Settled by run_experiments.py and run_endtoend.py. Carried here so the analog
# section is measured against the chain that will actually be built.
COEFF_BITS = {1: 26, 2: 26, 3: 26, 4: 22, 5: 19, 6: 18, 7: 10, 8: 8, 9: 8}
SIG_FRAC = {s: 26 for s in range(1, 10)}
ACC_FRAC = {1: 31, 2: 31, 3: 31, 4: 30, 5: 30, 6: 29, 7: 29, 8: 29, 9: 29}

# --- stated parameters of parts that do not exist yet -----------------------
GBW = 40e6                      # amplifier gain-bandwidth, Hz
E_N = 1.3e-9                    # amplifier voltage noise, V/sqrt(Hz)
I_N = 1.5e-12                   # amplifier current noise, A/sqrt(Hz)
C_NODE = 15e-12                 # stray capacitance at a summing node, F
Z_REG = 0.010                   # reference rail source impedance in band, ohms
R_DIFF = 200.0                  # resistors in the differential-to-single-ended stage

# --- what the rest of the board already costs, from power.md ---------------
PRE_ENUM_LIMIT = 0.150          # one unit load, USB 3.0
PRE_ENUM_OTHER = 0.072 + 0.040  # bridge idling + module clock rail
REG_RAIL_OTHER = 0.0081 + 0.002  # register packages + LT3045 ground pin

# --- the recommendations this script measures ------------------------------
R_ELEM = 3320.0                 # E96
F_POLE = (1.0e6, 200e3, 200e3)  # element split, FDA feedback, output stage

log: list[str] = []


def say(s: str = "") -> None:
    print(s)
    log.append(s)


def head(title: str) -> None:
    say()
    say("=" * 74)
    say(title)
    say("=" * 74)


def dbfs(p: float) -> float:
    return 10.0 * np.log10(max(p, 1e-300) / 0.5)


# ---------------------------------------------------------------- the chain
def element_sum(cas, ntf, mode, *, sigma=SIGMA, amp_dbfs=TEST_DBFS,
                n_out=N_MEAS, per_element=False):
    """One pass of the built chain, stopping at the element sum.

    Same path as ``endtoend.run``; it is repeated here because the analog work
    needs the waveform itself and, for the mismatch-of-capacitors check, the
    individual element streams, neither of which that function returns.
    """
    n_in = endtoend.input_length(cas, mode, n_out)
    _, f_sig = endtoend.coherent_tone_freq(mode, n_out, F_TONE)
    pcm = endtoend.source_tone(n_in, mode.fs, f_sig, amp_dbfs)
    pcm = endtoend.quantize_pcm(pcm, chain.PCM_BITS, "tpdf", seed=11)
    y, _ = datapath.interpolate(cas, pcm, mode, coeff_bits=COEFF_BITS,
                                sig_frac=SIG_FRAC, acc_frac=ACC_FRAC)
    settle = cas.settle_samples(mode)
    u = y[settle:settle + n_out]
    run = modulator.simulate(ntf, u, mode.element_clock, f_sig=f_sig)
    codes = np.clip(np.asarray(run.codes, dtype=np.int64), 0, chain.N_ELEMENTS)
    pos, neg = dwa.differential(codes, rotate=True)
    wp, wn = (None, None) if sigma == 0.0 else dwa.mismatch(sigma, seed=7)
    x = dwa.normalise(dwa.analog(pos, neg, wp, wn))
    x = x - x.mean()            # the mismatch offset is not audio-band noise
    out = {"x": x, "f_sig": f_sig, "clipped": run.clipped, "mode": mode}
    if per_element:
        out["pos"] = pos
        out["neg"] = neg
        out["w"] = (np.ones(chain.N_ELEMENTS) if wp is None else wp,
                    np.ones(chain.N_ELEMENTS) if wn is None else wn)
    return out


def measure(rec):
    return spectra.Measurement.of(rec["x"], rec["mode"].element_clock,
                                  rec["f_sig"], BAND, n_harmonics=10)


def run_chain():
    head(f"THE CHAIN, STOPPED AT THE ELEMENT SUM  (order {ORDER}, "
         f"{TEST_DBFS:+.1f} dBFS, N=2^{int(np.log2(N_MEAS))})")
    say("Everything below is measured on these records. The in-band figure is")
    say("what the digital chain delivers; the out-of-band figure is what the")
    say("analog section has to survive.")
    say()
    cs = {fam: halfband.build(fam) for fam in ("48k", "44k1")}
    ntf = modulator.synthesize_ntf(ORDER)
    recs = {}
    say(f"{'case':>26}  {'SNDR dB':>8}  {'in band':>10}  {'out of band':>11}  "
        f"{'total':>8}")
    cases = [("48 kHz, 1% elements", "48k", 0, SIGMA, TEST_DBFS),
             ("48 kHz, matched", "48k", 0, 0.0, TEST_DBFS),
             ("192 kHz, 1% elements", "48k", 2, SIGMA, TEST_DBFS),
             ("44.1 kHz, 1% elements", "44k1", 0, SIGMA, TEST_DBFS),
             ("48 kHz, -60 dBFS tone", "48k", 0, SIGMA, -60.0)]
    for name, fam, idx, sig, lvl in cases:
        mode = chain.modes(fam)[idx]
        rec = element_sum(cs[fam], ntf, mode, sigma=sig, amp_dbfs=lvl,
                          per_element=(name == cases[0][0]))
        m = measure(rec)
        rec["m"] = m
        recs[name] = rec
        ms = float(np.mean(rec["x"] ** 2))
        oob = ms - 0.5 * 10.0 ** (m.signal_dbfs / 10.0) \
            - 0.5 * 10.0 ** (m.noise_dbfs / 10.0)
        say(f"{name:>26}  {m.sndr_db:>8.2f}  {m.noise_dbfs:>9.1f}  "
            f"{dbfs(oob):>10.2f}  {dbfs(ms):>7.2f}")
    say()
    say("Out-of-band here is total power less the signal and the in-band noise,")
    say("which is exact by Parseval and does not depend on where the bins fall.")
    return cs, ntf, recs


# ------------------------------------------------------ Q1: element resistor
def resistor_currents(values):
    head("Q1a  THE ELEMENT RESISTOR AGAINST THE CURRENT BUDGET")
    say("14 elements are high at every code by construction (0008), so the rail")
    say("current is constant and equal to 14 * 3.3 V / R. The swing into the")
    say("current-to-voltage stage is +/- 7 * 3.3 V / R per channel.")
    say()
    say(f"{'R_elem':>9}  {'I_rail':>8}  {'I_fs peak':>10}  {'P_elem':>8}  "
        f"{'R_f for 2 V':>12}  {'module':>8}  {'board':>7}")
    for r in values:
        i_rail = analog.rail_current(r)
        i_fs = analog.fs_current(r)
        rf = analog.feedback_resistor(r)
        p = analog.element_dissipation(r)
        # power.md: module = element rail + registers + LDO + clock 40 + analog 51
        module = i_rail + REG_RAIL_OTHER + 0.040 + 0.051
        say(f"{r:>8.0f}   {i_rail*1e3:>7.2f}  {i_fs*1e3:>9.3f}  "
            f"{p*1e3:>7.1f}  {rf:>11.1f}  {module*1e3:>7.0f}  "
            f"{(module+0.234)*1e3:>6.0f}")
    say()
    say("mA except P_elem in mW and R_f in ohms. 'module' and 'board' follow")
    say("power.md's other lines unchanged: 8.1 mA of registers, 2 mA of LT3045")
    say("ground pin, 40 mA of clock chain, 51 mA of op amp stage and charge")
    say("pump, and 234 mA of main board.")
    say()
    say("USB 3.0 configured allows 900 mA and USB 2.0 allows 500 mA, so none of")
    say("these rows fails after enumeration. The binding limit is before it.")


def pre_enumeration(values):
    head("Q1b  ONE UNIT LOAD BEFORE ENUMERATION")
    say("A device may draw one unit load until it is configured: 150 mA on USB")
    say("3.0. power.md gets 72 mA of bridge and 40 mA of ungated module clock")
    say("rail, leaving the element reference rail everything under 38 mA. At")
    say("power-on the flip-flop state is undefined, so all 28 elements may be")
    say("high, which doubles the element term.")
    say()
    spare = PRE_ENUM_LIMIT - PRE_ENUM_OTHER - REG_RAIL_OTHER
    r_min14 = analog.N_HIGH * analog.V_REF / spare
    r_min28 = analog.N_BOARD * analog.V_REF / spare
    say(f"{'R_elem':>9}  {'14 high':>9}  {'total':>7}  {'28 high':>9}  "
        f"{'total':>7}  {'verdict':>26}")
    for r in values:
        i14 = analog.rail_current(r, analog.N_HIGH)
        i28 = analog.rail_current(r, analog.N_BOARD)
        t14 = PRE_ENUM_OTHER + REG_RAIL_OTHER + i14
        t28 = PRE_ENUM_OTHER + REG_RAIL_OTHER + i28
        if t28 <= PRE_ENUM_LIMIT:
            v = "fits at power-on"
        elif t14 <= PRE_ENUM_LIMIT:
            v = "fits only once codes run"
        else:
            v = "over at every state"
        say(f"{r:>8.0f}   {i14*1e3:>8.2f}  {t14*1e3:>6.0f}  {i28*1e3:>8.2f}  "
            f"{t28*1e3:>6.0f}  {v:>26}")
    say()
    say(f"Minimum R for 14 elements high : {r_min14:7.0f} ohm")
    say(f"Minimum R for 28 elements high : {r_min28:7.0f} ohm")
    say("The second is the one that has to hold, because nothing constrains the")
    say("register state at power-on. It assumes the analog rails are gated or")
    say("absent; power.md's 51 mA of op amp stage and charge pump does not fit")
    say("inside one unit load at any element value and has to be held off.")
    return r_min28


def resistor_noise(values, floor_db, signal_dbfs):
    head("Q1c  THE ELEMENT RESISTOR AGAINST THE NOISE FLOOR")
    say("Thermal noise at 300 K. The element resistors' own contribution needs")
    say("no topology: 14 resistors each carrying 4kT/R of current noise into a")
    say("virtual ground, against a full-scale signal current of 7*3.3/R.")
    say("Holding the output level fixed makes the transimpedance proportional")
    say("to R, so both resistor terms fall 3 dB per doubling of R while the")
    say("amplifier term does not move at all -- its noise gain is")
    say(f"1 + V_peak/V_ref = {analog.noise_gain():.3f}, which R does not enter.")
    say()
    say(f"Measured in-band noise of the digital chain, one percent elements, "
        f"48 kHz: {floor_db:.1f} dBFS,")
    say(f"which is {signal_dbfs - floor_db:.1f} dB below the "
        f"{signal_dbfs:+.1f} dBFS test tone.")
    say()
    say(f"{'R_elem':>9}  {'elements':>9}  {'R_f':>8}  {'amp+R_f':>9}  "
        f"{'total nV':>9}  {'stage SNR':>10}  {'with chain':>11}")
    out = {}
    for r in values:
        nb = analog.noise_budget(r, e_n=E_N, i_n=I_N)
        rest = np.sqrt(nb.e_fb ** 2 + nb.e_amp ** 2 + nb.e_iamp ** 2)
        comb = analog.combine_db(nb.snr_db, signal_dbfs - floor_db)
        out[r] = (nb, comb)
        say(f"{r:>8.0f}   {nb.snr_elem_db:>8.1f}  {nb.e_elem*1e9:>7.2f}  "
            f"{rest*1e9:>8.2f}  {nb.e_total*1e9:>8.2f}  {nb.snr_db:>9.2f}  "
            f"{comb:>10.2f}")
    say()
    say("'elements' is the element resistors alone, in dB, and is the only")
    say("column that depends on nothing but R. The nV columns are densities at")
    say("the stage output. 'stage SNR' is the whole analog stage against 2 V")
    say("RMS; 'with chain' power-sums it with the measured digital floor.")
    say()
    nb = analog.noise_budget(values[0], e_n=E_N, i_n=I_N)
    say("Where the stage noise comes from at the placeholder 1 kohm:")
    for name, e, share in nb.terms():
        say(f"   {name:<26} {e*1e9:5.2f} nV/rtHz  {100*share:5.1f} % of power")
    say()
    say(f"The amplifier assumed is e_n = {E_N*1e9:.1f} nV/rtHz, "
        f"i_n = {I_N*1e12:.1f} pA/rtHz, two stages:")
    say("a fully differential amplifier holding both summing nodes at virtual")
    say("ground, then a unity-gain differential-to-single-ended stage. No part")
    say("is chosen, so this column is an estimate and the sensitivity is:")
    for e in (1.1e-9, 1.3e-9, 2.5e-9, 5.0e-9):
        b = analog.noise_budget(R_ELEM, e_n=e, i_n=I_N)
        say(f"   e_n {e*1e9:4.1f} nV/rtHz at {R_ELEM:.0f} ohm: stage SNR "
            f"{b.snr_db:.1f} dB")
    return out


def resistor_pick(r_min, noise, floor_db, signal_dbfs):
    head("Q1  RECOMMENDATION: 3.32 kOHM")
    nb, comb = noise[R_ELEM]
    say(f"R_elem = 3.32 kohm, E96, thin film array, one per four elements.")
    say()
    say(f"   I_rail   = 14 x 3.3 / 3320          = "
        f"{analog.rail_current(R_ELEM)*1e3:.2f} mA, constant")
    say(f"   I_fs     = 7 x 3.3 / 3320           = "
        f"{analog.fs_current(R_ELEM)*1e3:.3f} mA peak, per channel")
    say(f"   R_f      = 2.828 V / {analog.fs_current(R_ELEM)*1e3:.3f} mA       "
        f"     = {nb.r_fb:.1f} ohm -> 402 ohm E96")
    v = analog.fs_current(R_ELEM) * 402.0 / np.sqrt(2.0)
    say(f"   level    = 6.958 mA x 402 / sqrt(2) = {v:.3f} V RMS at digital "
        f"full scale")
    say(f"   P_elem   = 14 x 3.3^2 / 3320        = "
        f"{analog.element_dissipation(R_ELEM)*1e3:.1f} mW, "
        f"{analog.element_dissipation(R_ELEM)*1e3/14:.2f} mW per 0402")
    say()
    say("Three things decide it and they agree to within 300 ohm.")
    say()
    say(f"1. The element resistors should not be the loudest thing in the")
    say(f"   chain. Their own thermal noise equals the measured digital floor")
    say(f"   of {signal_dbfs-floor_db:.1f} dB at "
        f"{10.0**((analog.noise_budget(1000.0).snr_elem_db - (signal_dbfs-floor_db))/10.0)*1000.0:.0f} ohm. "
        f"At 3.32 kohm they measure "
        f"{nb.snr_elem_db:.1f} dB,")
    say(f"   {nb.snr_elem_db - (signal_dbfs-floor_db):+.1f} dB against it, so "
        f"they cost the pair "
        f"{-(analog.combine_db(nb.snr_elem_db, signal_dbfs-floor_db) - (signal_dbfs-floor_db)):.1f} dB.")
    say()
    say(f"2. The whole board has to fit one unit load before enumeration with")
    say(f"   the flip-flops in an undefined state. That needs R >= "
        f"{r_min:.0f} ohm")
    say(f"   and 3.32 kohm is the first E96 value above it. At the netlist's")
    say(f"   1 kohm the power-on total is "
        f"{(PRE_ENUM_OTHER+REG_RAIL_OTHER+analog.rail_current(1000.0, analog.N_BOARD))*1e3:.0f} mA "
        f"against a 150 mA limit.")
    say()
    say(f"3. Everything past about 3 kohm is bought at 3 dB of resistor noise")
    say(f"   per doubling and returns less and less current. 1 kohm to 3.32")
    say(f"   kohm saves {(analog.rail_current(1000.0)-analog.rail_current(R_ELEM))*1e3:.0f} mA "
        f"and costs "
        f"{noise[1000.0][1] - comb:.1f} dB of system noise;")
    say(f"   3.32 kohm to 10 kohm would save another "
        f"{(analog.rail_current(R_ELEM)-analog.rail_current(10000.0))*1e3:.0f} mA "
        f"and cost {comb - noise[10000.0][1]:.1f} dB.")
    say()
    say(f"System noise at 3.32 kohm is {comb:.1f} dB, "
        f"{comb - chain.DYNAMIC_RANGE_TARGET_DB:+.1f} dB against the "
        f"{chain.DYNAMIC_RANGE_TARGET_DB:.0f} dB")
    say("target of 0012. The digital chain is no longer what sets it: the")
    say(f"analog stage measures {nb.snr_db:.1f} dB against the chain's "
        f"{signal_dbfs-floor_db:.1f} dB, so")
    say("**the output stage is the noise floor of this design**, and the")
    say("amplifier's own voltage noise is the largest single term in it at any")
    say("element value below about 3 kohm.")
    say()
    say("Two smaller consequences of the value, both in its favour:")
    roh = 20.0
    say(f"   The register's output impedance, about {roh:.0f} ohm for this")
    say(f"   logic class, is {100*roh/R_ELEM:.2f} % of the element at 3.32 kohm "
        f"against {100*roh/1000.0:.1f} % at 1 kohm.")
    say("   It appears identically on every element, so it is a gain error and")
    say("   not distortion, but its temperature coefficient is not small.")
    say(f"   Self-heating falls from "
        f"{analog.element_dissipation(1000.0)*1e3/14:.1f} mW to "
        f"{analog.element_dissipation(R_ELEM)*1e3/14:.2f} mW per element. The")
    say("   differential arrangement cancels the first-order thermal term")
    say("   exactly -- k(1-ek/7) - (7-k)(1-e(7-k)/7) = (2k-7)(1-e) -- so what")
    say("   is left is a gain drift, but only while both sides track.")


# ------------------------------------------------------ Q2: the filter
def out_of_band(rec):
    head("Q2a  WHERE THE OUT-OF-BAND ENERGY ACTUALLY IS")
    mode = rec["mode"]
    fs = mode.element_clock
    held = analog.Held(rec["x"], fs, over=OVER)
    say(f"The element sum is a staircase, not a sequence: each sample is held")
    say(f"for one element clock, so the waveform carries images at every")
    say(f"multiple of {fs/1e6:.3f} MHz rolled off by the hold's own sinc. The")
    say(f"spectrum below is taken at {held.fs/1e6:.1f} MHz so those images are")
    say(f"measured rather than assumed away.")
    say()
    tot = held.mean_square
    edges = [(chain.AUDIO_LO, chain.AUDIO_HI, "audio band"),
             (chain.AUDIO_HI, 1e5, "20 kHz - 100 kHz"),
             (1e5, 1e6, "100 kHz - 1 MHz"),
             (1e6, 3e6, "1 MHz - 3 MHz"),
             (3e6, fs / 2, f"3 MHz - {fs/2e6:.2f} MHz"),
             (fs / 2, fs, f"{fs/2e6:.2f} - {fs/1e6:.2f} MHz, first image"),
             (fs, held.fs / 2, f"{fs/1e6:.2f} - {held.fs/2e6:.2f} MHz, second")]
    oob = held.band_power(chain.AUDIO_HI, held.fs / 2)
    say(f"{'band':>34}  {'power':>10}  {'of total':>9}  {'of OOB':>8}")
    for lo, hi, name in edges:
        bp = held.band_power(lo, hi)
        say(f"{name:>34}  {dbfs(bp):>9.2f}  {100*bp/tot:>8.2f}%  "
            f"{100*bp/oob:>7.2f}%")
    say()
    i_fs = analog.fs_current(R_ELEM)
    v_fs = i_fs * analog.feedback_resistor(R_ELEM) / 1.0
    say(f"Out of band, total          : {dbfs(oob):.2f} dBFS, "
        f"{np.sqrt(oob):.4f} of full scale RMS")
    say(f"At 3.32 kohm that is        : {np.sqrt(oob)*i_fs*1e3:.3f} mA RMS of "
        f"ultrasonic current per channel,")
    say(f"                              against "
        f"{np.sqrt(0.5)*i_fs*1e3:.3f} mA RMS for a full-scale sine.")
    say(f"Referred to a 2 V RMS output: {np.sqrt(oob)*v_fs:.3f} V RMS of "
        f"content the amplifier must not fold down.")
    say()
    step = float(np.abs(np.diff(rec["x"])).max())
    say(f"Largest one-sample step     : {step:.4f} of full scale, "
        f"{step*v_fs:.3f} V at the output,")
    say(f"                              which unfiltered is "
        f"{step*v_fs*fs/1e6:.0f} V/us. No audio amplifier slews that.")
    say()
    say("Two thirds of the out-of-band energy sits between 3 MHz and the half")
    say("element clock, and a quarter of it is in the hold's own images above")
    say("the element clock. Content above 49 MHz is not represented: the sinc")
    say("is already 18 dB down there and any filter recommended below adds 50,")
    say("which bounds it under a tenth of a percent of the residual.")
    return held, oob


def where_poles_go(held):
    head("Q2b  WHERE A POLE CAN PHYSICALLY GO")
    say("The summing node has to be a virtual ground. That is what makes the")
    say("rail current constant: a high element delivers V_ref/R only while its")
    say("far end sits at zero. Let the node float by a fraction gamma of the")
    say("element network's own R/7 and the two nodes together draw")
    say("(V/R)[7 - 3.5 gamma (1 + s^2)], where s is the normalised signal. The")
    say("s^2 is a second harmonic on the reference rail, and the rail is a")
    say("multiplier, not an adder.")
    say()
    say(f"With the rail's in-band source impedance taken as "
        f"{Z_REG*1e3:.0f} mohm (regulator")
    say("plus 8 x 100 nF), a capacitor giving a 200 kHz pole at the node:")
    say()
    say(f"{'gamma':>8}  {'R seen by C':>12}  {'C needed':>10}  "
        f"{'rail ripple':>12}  {'distortion':>11}")
    for g in (1.0, 0.1, 0.01, 0.001):
        c = analog.shunt_at_node(R_ELEM, 200e3, g)
        di = 2.0 * analog.node_load_modulation(R_ELEM, g)   # both channels
        dv = di * Z_REG
        hd = 20.0 * np.log10(dv / analog.V_REF / 2.0)
        say(f"{g:>8.3f}  {g*R_ELEM/7.0:>11.2f}   {c*1e9:>9.1f} nF  "
            f"{dv*1e6:>10.2f} uV  {hd:>10.1f} dB")
    say()
    say("A shunt capacitor at the summing node is therefore not the first")
    say("filter pole. Against a true virtual ground it sees no resistance and")
    say("forms no pole at all; buy it a resistance by floating the node and the")
    say("rail modulation arrives before the pole does. The netlist's 1 nF is")
    say("not a filter: at a virtual ground it is the transimpedance stage's")
    c_par = 1.0 / (7.0 / R_ELEM + 1.0 / analog.feedback_resistor(R_ELEM))
    say(f"input capacitance, which puts a noise-gain zero at "
        f"{1.0/(2*np.pi*1e-9*c_par)/1e3:.0f} kHz and")
    say("wants feedback compensation rather than providing it.")
    say()
    say("The pole that does work splits the element resistor in two around a")
    say("shunt capacitor. Both ends of the split stay at an AC ground -- the")
    say("flip-flop output on one side, the virtual ground on the other -- so")
    say("the capacitor sees R1||R2 while the DC current stays exactly")
    say("V_ref/(R1+R2) at every code. The constant-current property is")
    say("untouched and the pole is genuinely in front of the amplifier.")
    say()
    say(f"{'pole':>10}  {'R1':>8}  {'R2':>8}  {'R1||R2':>8}  {'C':>10}")
    for f1 in (5e6, 2e6, 1e6, 500e3, 200e3):
        r1, r2, c = analog.split_element(R_ELEM, f1)
        say(f"{f1/1e6:>9.2f}M  {r1:>7.0f}  {r2:>7.0f}  {r1*r2/R_ELEM:>7.0f}  "
            f"{c*1e12:>9.0f} pF")
    say()
    say("An even split maximises R1||R2 and so minimises the capacitor. The")
    say("cost is 28 more resistors -- seven more four-element arrays, the same")
    say("part already fitted -- and 28 capacitors.")


def build_amp(f1, f2, r_elem=R_ELEM, gbw=GBW, c_node=C_NODE):
    rf = analog.feedback_resistor(r_elem)
    if f1 is None:
        r1, r2, c1 = 0.0, r_elem, 0.0
    else:
        r1, r2, c1 = analog.split_element(r_elem, f1)
    src = analog.ElementSource(r1=r1, r2=r2, c1=c1, c_node=c_node)
    return analog.Amp(r_fb=rf, c_fb=1.0 / (2.0 * np.pi * rf * f2), z_src=src,
                      gbw=gbw)


def stage_imd(held, f_sig, f1, f2, *, gbw=GBW, window=None, r_elem=R_ELEM):
    """In-band product the first amplifier makes, dBFS, plus what it sees."""
    f = held.f
    h1 = np.ones_like(f) if f1 is None else analog.pole(f, f1)
    amp = build_amp(f1, f2, r_elem=r_elem, gbw=gbw)
    i_spec = held.spec * analog.fs_current(r_elem) * h1
    v_fs = abs(amp.h_out(np.zeros(1))[0]) * analog.fs_current(r_elem)
    v_e = np.fft.irfft(i_spec * amp.h_err(f), held.n)
    ve_pk = float(np.abs(v_e).max())
    del v_e
    d = amp.distortion(i_spec, f, held.n)
    imd = analog.in_band_noise_dbfs(d, held.fs, f_sig, full_scale=v_fs,
                                    window=window)
    oob_in = held.band_power(chain.AUDIO_HI, held.fs / 2, h1)
    return {"imd": imd, "ve_pk": ve_pk, "oob_in": oob_in, "v_fs": v_fs}


def filter_threshold(held, rec, floor_db, signal_dbfs):
    head("Q2c  HOW MUCH THE AMPLIFIER MAY BE SHOWN")
    say("The threshold, stated before the measurement. The reconstruction")
    say("filter must leave the amplifier's own intermodulation 10 dB below the")
    say(f"in-band noise the chain actually measures, {floor_db:.1f} dBFS, so")
    say(f"the limit is {floor_db-10.0:.1f} dBFS. Ten decibels is the same")
    say("allowance the datapath was budgeted against in README.md, and it costs")
    say("0.41 dB end to end.")
    say()
    say("The mechanism is modelled rather than asserted. Once the loop gain is")
    say("gone -- and at a megahertz it is -- the summing node is no longer held")
    say("and the differential error voltage at the amplifier's input is the")
    say("element current into Z_f in parallel with Z_source. A bipolar input")
    say("pair is a tanh, so its leading error is a cubic on that voltage, and a")
    say("cubic mixes pairs of megahertz components down into the audio band.")
    say(f"Assumed: {GBW/1e6:.0f} MHz gain-bandwidth, no emitter degeneration,")
    say("26 mV of thermal voltage. Degeneration would make this better, so the")
    say("answer is a lower bound on how much filtering is needed.")
    say()
    window = spectra.analysis_window(held.n)
    limit = floor_db - 10.0
    say(f"{'element pole':>13}  {'C per elem':>11}  {'OOB at amp':>11}  "
        f"{'v_err pk':>9}  {'in-band IMD':>12}  {'margin':>8}")
    rows = []
    for f1 in (None, 1e7, 5e6, 2e6, 1e6, 500e3, 200e3):
        r = stage_imd(held, rec["f_sig"], f1, F_POLE[1], window=window)
        c = "--" if f1 is None else \
            f"{analog.split_element(R_ELEM, f1)[2]*1e12:.0f} pF"
        name = "none" if f1 is None else f"{f1/1e6:.2f} MHz"
        say(f"{name:>13}  {c:>11}  {dbfs(r['oob_in']):>10.2f}  "
            f"{r['ve_pk']*1e3:>8.2f} mV  {r['imd']:>11.2f}  "
            f"{r['imd']-limit:>+7.1f}")
        rows.append((f1, r))
    say()
    say(f"With the feedback pole at {F_POLE[1]/1e3:.0f} kHz and nothing in front of it the")
    fail = rows[0][1]["imd"]
    say(f"amplifier makes {fail:.1f} dBFS in band, which is "
        f"{fail-floor_db:+.1f} dB against the")
    say(f"chain's own {floor_db:.1f} dBFS and {fail-limit:+.1f} dB against the "
        f"threshold. **That fails.**")
    say("One pole in front of it at 1 MHz costs 180 pF per element and leaves")
    pick = [r for f1, r in rows if f1 == 1e6][0]
    say(f"{pick['imd']:.1f} dBFS, {limit-pick['imd']:.0f} dB of margin.")
    say()
    say("The feedback capacitor is doing at least as much work as the element")
    say("pole, because it is what sets the node impedance once the loop has")
    say("given up. Holding the element pole at 1 MHz and moving it:")
    say()
    say(f"{'feedback pole':>14}  {'C_f':>9}  {'v_err pk':>9}  "
        f"{'in-band IMD':>12}  {'margin':>8}")
    rf = analog.feedback_resistor(R_ELEM)
    for f2 in (2e6, 1e6, 500e3, 200e3, 100e3):
        r = stage_imd(held, rec["f_sig"], 1e6, f2, window=window)
        say(f"{f2/1e3:>13.0f}k  {1.0/(2*np.pi*rf*f2)*1e9:>8.2f} nF  "
            f"{r['ve_pk']*1e3:>8.2f} mV  {r['imd']:>11.2f}  "
            f"{r['imd']-limit:>+7.1f}")
    say()
    say("And the sensitivity to the parameter nobody has chosen yet:")
    say()
    say(f"{'gain-bandwidth':>15}  {'v_err pk':>9}  {'in-band IMD':>12}  "
        f"{'margin':>8}")
    for g in (10e6, 20e6, 40e6, 100e6):
        r = stage_imd(held, rec["f_sig"], 1e6, F_POLE[1], gbw=g, window=window)
        say(f"{g/1e6:>14.0f}M  {r['ve_pk']*1e3:>8.2f} mV  "
            f"{r['imd']:>11.2f}  {r['imd']-limit:>+7.1f}")
    say()
    say("A slower amplifier is worse, because its loop gives up sooner. Even at")
    say("10 MHz the 1 MHz element pole clears the threshold, which is the")
    say("margin the choice is made for.")
    return window, limit


def filter_order(held, window, limit, floor_db):
    head("Q2d  ORDER AND CORNERS")
    say("Three points matter and each is protected by a different number of")
    say("poles: the first amplifier sees only the element pole, the")
    say("differential-to-single-ended stage sees that and the feedback pole,")
    say("and the line output sees all three.")
    say()
    say("In-band droop at 20 kHz is the cost. The interpolation cascade is flat")
    say("to 35 micro-dB (README.md), so the analog filter is the whole response")
    say("error of the product, and 0.1 dB at 20 kHz is the budget taken here.")
    say()
    f = held.f
    say(f"{'poles':>34}  {'at amp':>8}  {'at stage 2':>11}  {'at output':>10}  "
        f"{'droop':>7}  {'delay':>7}")
    cases = [((1e6,), "1 MHz only"),
             ((1e6, 500e3), "1 MHz + 500 kHz"),
             ((1e6, 200e3), "1 MHz + 200 kHz"),
             ((1e6, 500e3, 500e3), "1 MHz + 500 kHz + 500 kHz"),
             ((1e6, 200e3, 200e3), "1 MHz + 200 kHz + 200 kHz"),
             ((1e6, 100e3, 100e3), "1 MHz + 100 kHz + 100 kHz"),
             ((1e6, 200e3, 200e3, 200e3), "1 MHz + three at 200 kHz")]
    for fcs, name in cases:
        p = [dbfs(held.band_power(chain.AUDIO_HI, held.fs / 2,
                                  analog.poles(f, fcs[:k])))
             for k in (1, 2, 3)]
        p_out = dbfs(held.band_power(chain.AUDIO_HI, held.fs / 2,
                                     analog.poles(f, fcs)))
        say(f"{name:>34}  {p[0]:>8.1f}  {p[1]:>11.1f}  {p_out:>10.1f}  "
            f"{analog.droop_db(fcs):>6.3f}  "
            f"{analog.group_delay_us(fcs):>6.2f}u")
    say()
    say("dBFS of residual ultrasonic content at each point, droop in dB at")
    say("20 kHz, group delay in microseconds at DC. The 'at stage 2' column for")
    say("a one-pole row repeats the first, since there is no second pole.")
    say()
    say("The output threshold is a slew argument rather than a noise one. A")
    say("downstream amplifier at 27 V/us should not spend more than one percent")
    say("of it on content it was never asked to reproduce, and at 8 MHz that is")
    say("0.27e6/(2 pi 8e6) = 5.4 mV peak, about 1.7 mV RMS, which on a 2.83 V")
    say("peak output is -60 dBFS. Two poles reach it; three leave margin.")
    say()
    say("A fourth pole buys little: the residual is already dominated by the")
    say("100 kHz to 1 MHz region where the poles have barely started, not by")
    say("the megahertz region where each one is worth 20 dB per decade.")


def capacitor_mismatch(rec, floor_db):
    head("Q2e  DOES A CAPACITOR PER ELEMENT BREAK THE ROTATION?")
    say("Dynamic element matching assumes the elements are interchangeable. A")
    say("shunt capacitor per element makes each one a filter, and capacitors")
    say("are not matched the way a resistor array is. Measured by giving every")
    say("element its own pole and re-running the in-band figure.")
    say()
    fs = rec["mode"].element_clock
    pos, neg = rec["pos"], rec["neg"]
    wp, wn = rec["w"]
    f1 = F_POLE[0]
    say(f"{'C tolerance':>13}  {'SNDR dB':>9}  {'in-band noise':>14}  "
        f"{'cost':>7}")
    base = None
    for tol in (0.0, 0.02, 0.05, 0.10, 0.20):
        rng = np.random.default_rng(4242)
        acc = np.zeros(pos.shape[0], dtype=np.float64)
        for side, w, sign in ((pos, wp, 1.0), (neg, wn, -1.0)):
            for j in range(chain.N_ELEMENTS):
                fj = f1 / (1.0 + tol * rng.standard_normal()) if tol else f1
                a = np.exp(-2.0 * np.pi * fj / fs)
                acc += sign * w[j] * lfilter([1.0 - a], [1.0, -a],
                                             side[:, j].astype(np.float64))
        y = dwa.normalise(acc)
        y = y - y.mean()
        m = spectra.Measurement.of(y, fs, rec["f_sig"], BAND, n_harmonics=10)
        if base is None:
            base = m.sndr_db
        label = "matched" if tol == 0 else f"{tol*100:.0f}%"
        say(f"{label:>13}  {m.sndr_db:>9.2f}  {m.noise_dbfs:>13.1f}  "
            f"{base-m.sndr_db:>+6.2f}")
    say()
    say(f"The reference row, no capacitors at all, measures "
        f"{rec['m'].sndr_db:.2f} dB. The pole")
    say("itself costs nothing in band -- at 1 MHz its 20 kHz droop is")
    say(f"{analog.droop_db((f1,)):.4f} dB -- and the tolerance costs nothing "
        f"either, because")
    say("the elements differ only where the capacitor does anything, which is")
    say("three decades above the band the rotation has to protect. Ordinary")
    say("C0G parts are adequate. C0G rather than X7R is required for a")
    say("different reason: X7R's voltage coefficient is a nonlinearity in the")
    say("signal path and the rotation does not fix nonlinearity within one")
    say("element, exactly as it does not fix a thick film resistor's.")


def filter_pick(held, window, limit, floor_db, rec):
    head("Q2  RECOMMENDATION: THREE REAL POLES, 1 MHz / 200 kHz / 200 kHz")
    f = held.f
    rf = analog.feedback_resistor(R_ELEM)
    r1, r2, c1 = analog.split_element(R_ELEM, F_POLE[0])
    c_f = 1.0 / (2.0 * np.pi * rf * F_POLE[1])
    c_d = 1.0 / (2.0 * np.pi * R_DIFF * F_POLE[2])
    say("Third order, all real poles, distributed one per amplifier boundary")
    say("rather than lumped anywhere. Not Butterworth and not a two-pole")
    say("section: a resonant section needs an inductor or an active stage, and")
    say("the active stage is the thing being protected.")
    say()
    say(f"  pole 1  {F_POLE[0]/1e6:.2f} MHz   each element split "
        f"{r1:.0f} + {r2:.0f} ohm around {c1*1e12:.0f} pF C0G")
    say(f"                    28 places; the DC current stays V_ref/(R1+R2)")
    say(f"  pole 2  {F_POLE[1]/1e3:.0f} kHz   {c_f*1e9:.2f} nF across each "
        f"{rf:.0f} ohm transimpedance resistor")
    say(f"  pole 3  {F_POLE[2]/1e3:.0f} kHz   {c_d*1e12:.0f} pF across the "
        f"{R_DIFF:.0f} ohm feedback of the")
    say(f"                    differential-to-single-ended stage")
    say()
    r_amp = stage_imd(held, rec["f_sig"], F_POLE[0], F_POLE[1], window=window)
    p1 = dbfs(held.band_power(chain.AUDIO_HI, held.fs / 2,
                              analog.poles(f, F_POLE[:1])))
    p2 = dbfs(held.band_power(chain.AUDIO_HI, held.fs / 2,
                              analog.poles(f, F_POLE[:2])))
    p3 = dbfs(held.band_power(chain.AUDIO_HI, held.fs / 2,
                              analog.poles(f, F_POLE)))
    raw = dbfs(held.band_power(chain.AUDIO_HI, held.fs / 2))
    v_fs = r_amp["v_fs"]
    say(f"Ultrasonic content, unfiltered            : {raw:7.2f} dBFS")
    say(f"   at the first amplifier's input         : {p1:7.2f} dBFS  "
        f"({raw-p1:.0f} dB of attenuation)")
    say(f"   at the differential-to-single-ended in : {p2:7.2f} dBFS")
    say(f"   at the line output                     : {p3:7.2f} dBFS, "
        f"{np.sqrt(10**(p3/10)*0.5)*v_fs*1e3:.2f} mV RMS")
    say()
    say(f"In-band intermodulation from the first amplifier: "
        f"{r_amp['imd']:.1f} dBFS,")
    say(f"{limit-r_amp['imd']:.0f} dB inside the "
        f"{limit:.1f} dBFS threshold and {floor_db-r_amp['imd']:.0f} dB below "
        f"the chain's own floor.")
    say(f"In-band droop at 20 kHz : {analog.droop_db(F_POLE):.3f} dB, "
        f"against a 0.100 dB budget.")
    say(f"Group delay at DC       : {analog.group_delay_us(F_POLE):.2f} us, "
        f"which is 0.5 % of the")
    say("cascade's own 235 us at 192 kHz and nothing beside 1.5 ms at 48 kHz.")
    y = held.wave(analog.poles(f, F_POLE)) * v_fs
    say(f"Peak slew at the output : {analog.peak_slew(y, held.fs):.2f} V/us, "
        f"against {float(np.abs(np.diff(rec['x'])).max())*v_fs*held.fs/OVER/1e6:.0f} V/us unfiltered.")
    del y
    say()
    say("Why the corners are where they are:")
    say()
    say(f"   Pole 1 at 1 MHz is set by the amplifier, not by the spectrum. It")
    say(f"   is the loosest corner that still clears the intermodulation")
    say(f"   threshold with a 10 MHz amplifier, and at 1 MHz it costs 180 pF")
    say(f"   per element and {analog.droop_db((F_POLE[0],)):.4f} dB in band, "
        f"which is free. Pushing it lower")
    say(f"   buys nothing measurable and pushing it higher spends the margin")
    say(f"   on the one parameter of the amplifier that is still unchosen.")
    say()
    say(f"   Poles 2 and 3 at 200 kHz are set by the droop budget, not by the")
    say(f"   amplifier. Two real poles at f cost 2*10log10(1+(20k/f)^2) at")
    say(f"   20 kHz; 0.1 dB puts the floor at 187 kHz, and 200 kHz is the first")
    say(f"   round value above it, costing {2*10*np.log10(1+(2e4/2e5)**2):.3f} dB.")
    say()
    say("What would change the answer: a pre-emphasis in the interpolator's")
    say("first stage, which is free in tap count, would pay the droop back and")
    say("let all three poles sit an octave lower. It is not recommended here")
    say("because the filter already clears every threshold by 20 dB or more,")
    say("and a response correction that lives in two places is a maintenance")
    say("hazard rather than a saving.")


# ------------------------------------------------------------------ figures
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7"]
INK, MUTED = "#0b0b0b", "#52514e"


def figure_resistor(values, noise, r_min, floor_db, signal_dbfs):
    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.5), constrained_layout=True)
    r = np.asarray(values, dtype=float)

    i14 = np.array([analog.rail_current(v) for v in r]) * 1e3
    i28 = np.array([analog.rail_current(v, analog.N_BOARD) for v in r]) * 1e3
    budget = (PRE_ENUM_LIMIT - PRE_ENUM_OTHER - REG_RAIL_OTHER) * 1e3
    ax[0].plot(r, i14, "-", color=C[0], lw=2, label="14 high, every code")
    ax[0].plot(r, i28, "--", color=C[1], lw=2, label="28 high, at power-on")
    ax[0].axhline(budget, color=INK, ls=":", lw=1.2)
    ax[0].annotate(f"one unit load leaves {budget:.0f} mA", (1.05e3, budget + 3),
                   fontsize=8, color=INK)
    ax[0].axvline(r_min, color=MUTED, lw=1)
    ax[0].annotate(f"{r_min:.0f} ohm", (r_min * 1.05, 150), fontsize=8,
                   color=MUTED)
    for v, lab in ((1000.0, "netlist 1k"), (R_ELEM, "3.32k")):
        ax[0].plot([v], [analog.rail_current(v) * 1e3], "o", ms=7, color=C[0],
                   mec="white", mew=1.5, zorder=5)
        ax[0].annotate(f"{lab}\n{analog.rail_current(v)*1e3:.1f} mA",
                       (v, analog.rail_current(v) * 1e3), textcoords="offset points",
                       xytext=(8, 8), fontsize=8, color=INK)
    ax[0].set(xscale="log", yscale="log", xlabel="element resistor, ohm",
              ylabel="reference rail current, mA",
              title="What the elements draw, and the limit before enumeration")
    ax[0].legend(fontsize=8, frameon=False)
    ax[0].grid(alpha=.25, which="both")

    snr_e = np.array([analog.noise_budget(v, e_n=E_N, i_n=I_N).snr_elem_db
                      for v in r])
    snr_s = np.array([noise[v][0].snr_db for v in r])
    snr_c = np.array([noise[v][1] for v in r])
    digital = signal_dbfs - floor_db
    ax[1].plot(r, snr_e, "-", color=C[0], lw=2, label="element resistors alone")
    ax[1].plot(r, snr_s, "-", color=C[1], lw=2, label="whole analog stage")
    ax[1].plot(r, snr_c, "-", color=C[2], lw=2, label="stage + digital chain")
    ax[1].axhline(digital, color=INK, ls=":", lw=1.2)
    ax[1].annotate(f"digital chain measures {digital:.1f} dB", (1.05e3, digital + 0.6),
                   fontsize=8, color=INK)
    ax[1].axhline(chain.DYNAMIC_RANGE_TARGET_DB, color=MUTED, ls="--", lw=1)
    ax[1].annotate(f"{chain.DYNAMIC_RANGE_TARGET_DB:.0f} dB target of 0012",
                   (1.05e3, chain.DYNAMIC_RANGE_TARGET_DB + 0.6), fontsize=8,
                   color=MUTED)
    ax[1].axvline(R_ELEM, color=MUTED, lw=1)
    ax[1].annotate("3.32k", (R_ELEM * 1.04, 112), fontsize=8, color=MUTED)
    ax[1].set(xscale="log", xlabel="element resistor, ohm",
              ylabel="signal to noise, dB", ylim=(108, 142),
              title="3 dB per doubling, against a floor that does not move")
    ax[1].legend(fontsize=8, frameon=False, loc="upper right")
    ax[1].grid(alpha=.25, which="both")
    fig.savefig(FIG / "analog_resistor.png", dpi=130)
    plt.close(fig)


def figure_filter(held, rec, window, limit, floor_db):
    f = held.f
    fig, ax = plt.subplots(1, 2, figsize=(12.0, 4.6), constrained_layout=True)

    p = held.power()
    psd = 10.0 * np.log10(np.maximum(p, 1e-300) / 0.5)
    fo, po = spectra.smooth_psd(f, psd, n_out=900, f_lo=100.0)
    ax[0].plot(fo, po, lw=1.2, color=MUTED, label="element sum, held")
    for k, (fcs, lab) in enumerate(((F_POLE[:1], "after pole 1, at the amplifier"),
                                    (F_POLE[:2], "after pole 2"),
                                    (F_POLE, "after pole 3, at the output"))):
        pk = held.power(analog.poles(f, fcs))
        pdb = 10.0 * np.log10(np.maximum(pk, 1e-300) / 0.5)
        fk, pv = spectra.smooth_psd(f, pdb, n_out=900, f_lo=100.0)
        ax[0].plot(fk, pv, lw=1.6, color=C[k], label=lab)
    ax[0].axvline(chain.AUDIO_HI, color=INK, ls=":", lw=1)
    ax[0].annotate("20 kHz", (2.2e4, -25), fontsize=8, color=INK, rotation=90)
    ax[0].set(xscale="log", xlabel="Hz", ylabel="dBFS per bin",
              xlim=(1e2, held.fs / 2), ylim=(-230, -30),
              title="The shaped noise, and what each pole takes out of it")
    ax[0].legend(fontsize=8, frameon=False, loc="lower left")
    ax[0].grid(alpha=.25, which="both")

    f1s = np.array([2e7, 1e7, 5e6, 2e6, 1e6, 5e5, 2e5])
    imd, oob = [], []
    for f1 in f1s:
        r = stage_imd(held, rec["f_sig"], f1, F_POLE[1], window=window)
        imd.append(r["imd"])
        oob.append(dbfs(r["oob_in"]))
    ax[1].plot(f1s / 1e6, imd, "o-", ms=6, lw=2, color=C[0],
               label="in-band intermodulation the amplifier makes")
    ax[1].plot(f1s / 1e6, oob, "s--", ms=6, lw=2, color=C[1],
               label="ultrasonic content reaching its input")
    ax[1].axhline(limit, color=INK, ls=":", lw=1.2)
    ax[1].annotate(f"threshold {limit:.1f} dBFS", (0.22, limit + 4), fontsize=8,
                   color=INK)
    ax[1].axhline(floor_db, color=MUTED, ls="--", lw=1)
    ax[1].annotate(f"the chain's own floor {floor_db:.1f} dBFS", (0.22, floor_db + 4),
                   fontsize=8, color=MUTED)
    no = stage_imd(held, rec["f_sig"], None, F_POLE[1], window=window)
    ax[1].axhline(no["imd"], color=C[3], lw=1.5)
    ax[1].annotate(f"no pole before the amplifier: {no['imd']:.0f} dBFS",
                   (0.22, no["imd"] + 4), fontsize=8, color=C[3])
    ax[1].plot([1.0], [[i for f1, i in zip(f1s, imd) if f1 == 1e6][0]], "o",
               ms=11, mfc="none", mec=INK, mew=1.5, zorder=6)
    ax[1].annotate("recommended", (1.0, [i for f1, i in zip(f1s, imd) if f1 == 1e6][0]),
                   textcoords="offset points", xytext=(10, -14), fontsize=8,
                   color=INK)
    ax[1].set(xscale="log", xlabel="element pole, MHz", ylabel="dBFS",
              title="Why the first pole has to exist, and where it can sit")
    ax[1].legend(fontsize=8, frameon=False, loc="lower right")
    ax[1].grid(alpha=.25, which="both")
    fig.savefig(FIG / "analog_filter.png", dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------- main
def main() -> int:
    values = [1000.0, 1500.0, 2000.0, 2200.0, 3010.0, R_ELEM, 4700.0, 6800.0,
              10000.0]
    cs, ntf, recs = run_chain()
    primary = recs["48 kHz, 1% elements"]
    floor_db = primary["m"].noise_dbfs
    signal_dbfs = primary["m"].signal_dbfs

    resistor_currents(values)
    r_min = pre_enumeration(values)
    noise = resistor_noise(values, floor_db, signal_dbfs)
    resistor_pick(r_min, noise, floor_db, signal_dbfs)

    held, oob = out_of_band(primary)
    head("Q2a  IS IT THE SAME AT EVERY RATE?")
    say("The modulator always runs at the element clock, so the out-of-band")
    say("noise is a property of the loop and not of the sample rate. Checked:")
    say()
    say(f"{'case':>26}  {'out of band':>12}  {'above 1 MHz':>12}")
    for name, rec in recs.items():
        h = analog.Held(rec["x"], rec["mode"].element_clock, over=OVER)
        a = h.band_power(chain.AUDIO_HI, h.fs / 2)
        b = h.band_power(1e6, h.fs / 2)
        say(f"{name:>26}  {dbfs(a):>11.2f}  {dbfs(b):>11.2f}")
        del h
    say()
    say("Within 0.5 dB across every rate and 0.2 dB between a -3.7 dBFS tone")
    say("and a -60 dBFS one, which is the point: the filter is designed against")
    say("the modulator, not against the programme.")

    where_poles_go(held)
    window, limit = filter_threshold(held, primary, floor_db, signal_dbfs)
    filter_order(held, window, limit, floor_db)
    capacitor_mismatch(primary, floor_db)
    filter_pick(held, window, limit, floor_db, primary)

    figure_resistor(values, noise, r_min, floor_db, signal_dbfs)
    figure_filter(held, primary, window, limit, floor_db)

    (RES / "analog.txt").write_text("\n".join(log) + "\n")
    say()
    say(f"figures -> {FIG}/analog_resistor.png, {FIG}/analog_filter.png")
    say(f"log     -> {RES / 'analog.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The analog back end: the element resistor, and the reconstruction filter.

Everything upstream of this module ends at a normalised element sum in
``[-1, +1]``. This module turns that abstraction back into volts and amperes
and measures the two numbers the board cannot be fabricated without.

The circuit, as 0008 and 0012 fix it
------------------------------------
Each of the 28 elements is a flip-flop output on the 3.3 V reference rail
feeding one resistor into a summing node. Differential thermometer drive keeps
exactly seven elements high per channel at every code, so::

    I_rail  = 14 * V_REF / R_elem              constant, both channels
    I_diff  = (2k - 7) * V_REF / R_elem        per channel, k the code
    I_fs    = 7 * V_REF / R_elem               peak of that swing

**The summing node has to be a virtual ground.** That is not a modelling
convenience, it is what makes ``I_rail`` constant: a high element delivers
``V_REF / R_elem`` only while the far end sits at zero. Let the node float and
the current becomes ``(V_REF - V_node)/R_elem`` and the rail load turns
signal-dependent, which is the compression 0008 exists to prevent.
:func:`node_load_modulation` puts a number on that, and the number is why a
shunt capacitor at the summing node is not the first filter pole.

Noise
-----
Referred to the differential output of the current-to-voltage stage, with
``R_f`` the transimpedance:

* elements: 14 resistors, each ``4kT/R_elem`` of current noise, so
  ``R_f * sqrt(14 * 4kT / R_elem)``. Both ends of every element resistor are
  at an AC ground, so all 28 contribute whether their driver is high or low --
  but only the 14 on the two nodes of one channel reach that channel's output.
* the transimpedance resistors themselves.
* the amplifier's own voltage and current noise, at the stage's noise gain.

Holding the output level fixed makes ``R_f`` proportional to ``R_elem``, which
makes the first two terms scale as ``1/sqrt(R_elem)`` -- 3 dB per doubling --
while the amplifier term does not move at all, because the noise gain
``1 + 7 R_f / R_elem = 1 + V_peak / V_REF`` depends only on how hard the stage
is driven.

The amplifier
-------------
:class:`Amp` is a single-pole op amp with a bipolar input pair. It exists to
answer one question with a number: how much of the modulator's out-of-band
noise may reach the amplifier before the amplifier folds it back into the
audio band. The mechanism is the input pair's ``tanh``: the differential error
voltage at the summing node is ``i_in * (Z_f || Z_s)`` once the loop gain has
run out, which above a megahertz it has, and a cubic term on that voltage
mixes pairs of megahertz components down to baseband.

Nothing here is a datasheet. ``gbw``, ``e_n`` and ``i_n`` are stated
parameters of a part that has not been chosen, and every result that depends
on them is reported with its sensitivity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import chain, spectra

# ---------------------------------------------------------------------------
# Physical and fixed constants
# ---------------------------------------------------------------------------

K_B = 1.380649e-23
T_REF = 300.0                       # 27 C, stated rather than assumed
FOUR_KT = 4.0 * K_B * T_REF

V_REF = 3.3                         # element reference rail, 0012
N_SIDE = chain.N_ELEMENTS           # 7 elements per side
N_HIGH = 2 * N_SIDE                 # 14 high at every code, both channels
N_BOARD = 4 * N_SIDE                # 28 elements fitted

BAND = (chain.AUDIO_LO, chain.AUDIO_HI)
BAND_HZ = chain.AUDIO_HI - chain.AUDIO_LO

LINE_RMS = 2.0                      # V RMS at digital full scale, the target


# ---------------------------------------------------------------------------
# Currents, levels and power
# ---------------------------------------------------------------------------

def rail_current(r_elem: float, n_high: int = N_HIGH) -> float:
    """Amperes drawn from the 3.3 V reference rail. Constant by construction."""
    return n_high * V_REF / r_elem


def fs_current(r_elem: float) -> float:
    """Peak differential current one channel delivers, in amperes."""
    return N_SIDE * V_REF / r_elem


def feedback_resistor(r_elem: float, v_rms: float = LINE_RMS) -> float:
    """Transimpedance that puts digital full scale at ``v_rms`` volts RMS."""
    return v_rms * np.sqrt(2.0) / fs_current(r_elem)


def noise_gain(v_rms: float = LINE_RMS) -> float:
    """``1 + R_f / (R_elem/7)``, which the level fixes and ``R_elem`` does not."""
    return 1.0 + v_rms * np.sqrt(2.0) / V_REF


def element_dissipation(r_elem: float, n_high: int = N_HIGH) -> float:
    """Watts in the element resistors. Only high elements dissipate."""
    return n_high * V_REF ** 2 / r_elem


def node_load_modulation(r_elem: float, gamma: float) -> float:
    """Peak signal-dependent part of the rail current, in amperes, per channel.

    ``gamma`` is how far the summing node is allowed off virtual ground: the
    fraction of the element network's own ``R/7`` that the node's load
    impedance represents, so ``gamma = 0`` is a true virtual ground and
    ``gamma = 1`` is an open node summing passively.

    With ``k`` high on one side and ``7-k`` on the other, the two nodes
    together draw ``(V/R)[7 - 3.5*gamma*(1 + s^2)]`` where ``s`` is the
    normalised signal. The ``s^2`` is the whole problem: it is a second
    harmonic on the reference rail, and the rail is a multiplier.
    """
    return 3.5 * gamma * V_REF / r_elem / 2.0


# ---------------------------------------------------------------------------
# Noise
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NoiseBudget:
    r_elem: float
    r_fb: float
    e_elem: float                   # V/sqrt(Hz) at the output, each term
    e_fb: float
    e_amp: float
    e_iamp: float
    e_total: float
    v_rms: float                    # integrated over the audio band
    v_signal_rms: float
    snr_db: float                   # stage alone
    snr_elem_db: float              # element resistors alone

    def terms(self) -> list[tuple[str, float, float]]:
        """(name, density, share of total power) worst first."""
        t = [("element resistors", self.e_elem),
             ("transimpedance resistors", self.e_fb),
             ("amplifier voltage noise", self.e_amp),
             ("amplifier current noise", self.e_iamp)]
        tot = self.e_total ** 2
        return sorted([(n, e, e * e / tot) for n, e in t],
                      key=lambda x: -x[1])


def noise_budget(r_elem: float, *, v_rms: float = LINE_RMS,
                 e_n: float = 1.3e-9, i_n: float = 1.5e-12,
                 n_stages: int = 2, band_hz: float = BAND_HZ) -> NoiseBudget:
    """Output noise of the current-to-voltage stage, by term.

    ``n_stages`` is how many amplifiers the differential-to-single-ended path
    uses. Two is the arrangement that keeps both summing nodes at a true
    virtual ground with the four amplifiers power.md budgets for stereo: a
    transimpedance amplifier on the negative node, then a second amplifier
    that is simultaneously the transimpedance for the positive node and the
    inverting summer for the first one's output. That second stage needs one
    extra resistor, equal to its own feedback resistor, and it runs at a
    higher noise gain because its summing node sees that resistor in parallel
    with the element network.
    """
    r_fb = feedback_resistor(r_elem, v_rms)
    ng1 = noise_gain(v_rms)                        # 1 + R_f / (R/7)
    # Second stage: its inverting node sees R/7 in parallel with the R_f-valued
    # summing resistor from the first stage.
    r_par = 1.0 / (7.0 / r_elem + 1.0 / r_fb)
    ng2 = 1.0 + r_fb / r_par

    e_elem = r_fb * np.sqrt(N_HIGH * FOUR_KT / r_elem)
    n_fb = 3 if n_stages == 2 else 2               # R_f, R_g, R_f2
    e_fb = np.sqrt(n_fb * FOUR_KT * r_fb)
    ngs = (ng1 ** 2 + ng2 ** 2) if n_stages == 2 else (2.0 * ng1 ** 2)
    e_amp = np.sqrt(ngs) * e_n
    e_iamp = np.sqrt(float(n_stages)) * i_n * r_fb

    e_tot = float(np.sqrt(e_elem ** 2 + e_fb ** 2 + e_amp ** 2 + e_iamp ** 2))
    v_noise = e_tot * np.sqrt(band_hz)
    snr = 20.0 * np.log10(v_rms / v_noise)
    # The element resistors alone, which needs no topology at all: their
    # current noise against the full-scale signal current.
    i_noise = np.sqrt(N_HIGH * FOUR_KT / r_elem * band_hz)
    snr_e = 20.0 * np.log10(fs_current(r_elem) / np.sqrt(2.0) / i_noise)
    return NoiseBudget(r_elem=r_elem, r_fb=r_fb, e_elem=float(e_elem),
                       e_fb=float(e_fb), e_amp=float(e_amp),
                       e_iamp=float(e_iamp), e_total=e_tot,
                       v_rms=float(v_noise), v_signal_rms=v_rms,
                       snr_db=float(snr), snr_elem_db=float(snr_e))


def combine_db(*snr_db: float) -> float:
    """Power-sum independent noise contributions given as SNR figures."""
    p = sum(10.0 ** (-s / 10.0) for s in snr_db)
    return float(-10.0 * np.log10(p))


# ---------------------------------------------------------------------------
# The held waveform and its spectrum
# ---------------------------------------------------------------------------

class Held:
    """The element sum as the resistors actually produce it: zero-order held.

    The model's element sum is a sequence at the element clock. What the
    summing node carries is a staircase, which has the same mean square but
    also has images at every multiple of the element clock, rolled off by the
    hold's own ``sinc``. Those images are out-of-band energy too, and the
    amplifier sees them, so they are represented here rather than assumed
    away: the sequence is repeated ``over`` times and the spectrum taken at
    ``over`` times the element clock.

    ``over = 4`` reaches 49.152 MHz, which covers the first two image pairs.
    The next pair sits above 49 MHz where the hold's sinc is already 18 dB
    down and any filter recommended here is a further 50, so it is bounded at
    under a tenth of a percent of the residual power rather than measured.
    """

    def __init__(self, x: np.ndarray, fs: float, over: int = 4):
        x = np.asarray(x, dtype=np.float64)
        self.over = int(over)
        self.fs = fs * self.over
        self.n = x.size * self.over
        y = np.repeat(x, self.over)
        self.spec = np.fft.rfft(y)
        self.f = np.fft.rfftfreq(self.n, 1.0 / self.fs)
        self.mean_square = float(np.mean(y * y))
        del y

    # -- power ------------------------------------------------------------
    def power(self, h: np.ndarray | None = None) -> np.ndarray:
        """One-sided power per bin. ``result.sum()`` is the mean square."""
        s = self.spec if h is None else self.spec * h
        p = (np.abs(s) / self.n) ** 2
        p[1:] *= 2.0
        if self.n % 2 == 0:
            p[-1] /= 2.0
        return p

    def band_power(self, lo: float, hi: float,
                   h: np.ndarray | None = None) -> float:
        s = self.spec if h is None else self.spec * h
        m = (self.f >= lo) & (self.f < hi)
        p = (np.abs(s[m]) / self.n) ** 2
        return float(2.0 * p.sum())

    def wave(self, h: np.ndarray | None = None) -> np.ndarray:
        s = self.spec if h is None else self.spec * h
        return np.fft.irfft(s, self.n)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def pole(f: np.ndarray, fc: float) -> np.ndarray:
    """One real pole, as a complex response."""
    return 1.0 / (1.0 + 1j * np.asarray(f, dtype=np.float64) / fc)


def poles(f: np.ndarray, fcs) -> np.ndarray:
    h = np.ones(np.shape(f), dtype=np.complex128)
    for fc in fcs:
        h = h * pole(f, fc)
    return h


def droop_db(fcs, f: float = chain.AUDIO_HI) -> float:
    """In-band loss at ``f``, in dB, positive meaning attenuation."""
    return float(-20.0 * np.log10(abs(poles(np.array([f]), fcs)[0])))


def group_delay_us(fcs, f: float = 0.0) -> float:
    """Group delay of a cascade of real poles, microseconds."""
    return float(sum(1.0 / (2.0 * np.pi * fc) / (1.0 + (f / fc) ** 2)
                     for fc in fcs) * 1e6)


def split_element(r_elem: float, f_pole: float,
                  balance: float = 0.5) -> tuple[float, float, float]:
    """Split one element resistor into two around a shunt capacitor.

    This is the only place a pole can sit in front of the amplifier without
    moving the summing node off virtual ground. The driver end is an AC
    ground on the reference rail and the far end is the virtual ground, so
    the midpoint capacitor sees ``R1 || R2`` and the DC current stays exactly
    ``V_REF / (R1 + R2)`` at every code.

    Returns ``(R1, R2, C)``. ``balance`` is R1's share; an even split
    maximises ``R1 || R2`` and so minimises the capacitor.
    """
    r1 = balance * r_elem
    r2 = r_elem - r1
    r_par = r1 * r2 / r_elem
    return r1, r2, 1.0 / (2.0 * np.pi * r_par * f_pole)


def shunt_at_node(r_elem: float, f_pole: float, gamma: float) -> float:
    """Capacitor needed for a pole at the summing node itself, in farads.

    The node has to be pulled ``gamma`` of the way off virtual ground for the
    capacitor to see any resistance at all -- ``gamma * R_elem / 7`` -- and
    :func:`node_load_modulation` is what that costs on the reference rail.
    """
    return 1.0 / (2.0 * np.pi * gamma * r_elem / N_SIDE * f_pole)


# ---------------------------------------------------------------------------
# The amplifier
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ElementSource:
    """Admittance the summing node sees looking back into the elements.

    Seven elements per node, each a resistor from an AC ground -- the
    flip-flop output, high or low, sits on the reference rail or on ground and
    is a low impedance either way. With the element split for a pole, each is
    ``R2 + (R1 || 1/jwC)``. ``c_node`` is stray plus any deliberate shunt at
    the node itself.
    """

    r1: float
    r2: float
    c1: float
    c_node: float = 15e-12
    n: int = N_SIDE

    def y(self, f: np.ndarray) -> np.ndarray:
        w = 2j * np.pi * np.asarray(f, dtype=np.float64)
        if self.c1 > 0.0 and self.r1 > 0.0:
            z1 = self.r1 / (1.0 + w * self.r1 * self.c1)
        else:
            z1 = self.r1
        z = self.r2 + z1
        return self.n / z + w * self.c_node


@dataclass(frozen=True)
class Amp:
    """Single-pole op amp with a bipolar input pair, as a transimpedance.

    ``a_dc`` and ``gbw`` set the loop gain; ``vt`` is the input pair's thermal
    voltage, so the pair's transconductance is ``tanh(v_e / 2 vt)`` and its
    leading error is ``-(1/3) (v_e / 2 vt)^2``. No degeneration is assumed,
    which is the pessimistic case and the one that makes the answer a lower
    bound on how much filtering is needed.
    """

    r_fb: float
    c_fb: float
    z_src: "ElementSource"
    gbw: float = 40e6
    a_dc: float = 1e6
    vt: float = 0.026

    def a_ol(self, f: np.ndarray) -> np.ndarray:
        fp = self.gbw / self.a_dc
        return self.a_dc / (1.0 + 1j * np.asarray(f, float) / fp)

    def z_f(self, f: np.ndarray) -> np.ndarray:
        y = 1.0 / self.r_fb + 2j * np.pi * np.asarray(f, float) * self.c_fb
        return 1.0 / y

    def h_err(self, f: np.ndarray) -> np.ndarray:
        """Volts at the summing node per ampere of element current."""
        a = self.a_ol(f)
        return 1.0 / ((1.0 + a) / self.z_f(f) + self.z_src.y(f))

    def h_out(self, f: np.ndarray) -> np.ndarray:
        """Volts at the amplifier output per ampere of element current."""
        return -self.a_ol(f) * self.h_err(f)

    def loop_gain(self, f: np.ndarray) -> np.ndarray:
        zs = 1.0 / self.z_src.y(f)
        zf = self.z_f(f)
        return self.a_ol(f) * zs / (zs + zf)

    def h_dist(self, f: np.ndarray) -> np.ndarray:
        """Output volts per volt of input-referred distortion voltage."""
        return -self.a_ol(f) / (1.0 + self.loop_gain(f))

    def distortion(self, i_in_spec: np.ndarray, f: np.ndarray,
                   n: int) -> np.ndarray:
        """Output-referred distortion waveform for an input current spectrum.

        The input pair sees ``v_e``; its cubic term puts
        ``v_e^3 / (3 (2 vt)^2)`` at the amplifier's own input, and the loop
        divides that by ``1 + T`` on the way out. Above a megahertz ``T`` is
        gone and the division buys nothing, which is the whole point.
        """
        v_e = np.fft.irfft(i_in_spec * self.h_err(f), n)
        eps = v_e ** 3 / (3.0 * (2.0 * self.vt) ** 2)
        del v_e
        return np.fft.irfft(np.fft.rfft(eps) * self.h_dist(f), n)


# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------

def in_band_noise_dbfs(x: np.ndarray, fs: float, f_sig: float,
                       full_scale: float = 1.0,
                       band: tuple[float, float] = BAND,
                       window: np.ndarray | None = None) -> float:
    """In-band power of a residual, with the fundamental lobe excised.

    dBFS is against a full-scale sine of amplitude ``full_scale``, i.e. a mean
    square of ``full_scale**2 / 2``, so the number lands on the same scale as
    every other figure in this model.
    """
    n = len(x)
    w = spectra.analysis_window(n) if window is None else window
    p = spectra.power_spectrum(x, w)
    f = spectra.bin_freqs(n, fs)
    half = spectra.main_lobe_bins()
    df = fs / n
    m = (f >= band[0]) & (f <= band[1])
    c = int(round(f_sig / df))
    lo, hi = max(c - half, 0), min(c + half + 1, len(p))
    keep = m.copy()
    keep[lo:hi] = False
    n_keep, n_full = int(keep.sum()), int(m.sum())
    pw = float(p[keep].sum()) * (n_full / max(n_keep, 1))
    return float(10.0 * np.log10(max(pw, 1e-300) / (0.5 * full_scale ** 2)))


def peak_slew(y: np.ndarray, fs: float) -> float:
    """Largest sample-to-sample slope, volts per microsecond."""
    return float(np.abs(np.diff(y)).max() * fs / 1e6)


__all__ = ["K_B", "T_REF", "FOUR_KT", "V_REF", "N_SIDE", "N_HIGH", "N_BOARD",
           "BAND", "BAND_HZ", "LINE_RMS", "rail_current", "fs_current",
           "feedback_resistor", "noise_gain", "element_dissipation",
           "node_load_modulation", "NoiseBudget", "noise_budget", "combine_db",
           "Held", "pole", "poles", "droop_db", "group_delay_us",
           "split_element", "shunt_at_node", "Amp", "ElementSource",
           "in_band_noise_dbfs", "peak_slew"]

#!/usr/bin/env python3
"""Size the modulator's own arithmetic.

    ./.venv/bin/python model/run_modarith.py

Sweeps coefficient and integrator state widths against the exact loop, and
checks the result against tones across the band and against the inter-sample
probe at its maximum stable level.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lyrebird_model import chain, endtoend, modarith, modulator  # noqa: E402

FS = chain.ELEMENT_CLOCK["48k"]
N = 1 << 20
log = []


def say(s=""):
    print(s)
    log.append(s)


def main() -> int:
    ntf = modulator.synthesize_ntf(3)
    u, f = modulator.tone(N, FS, 1000.0, -3.7)
    ref = modarith.simulate_fixed(ntf, u, FS, f, coeff_frac=22,
                                  state_frac=30, state_int=1).m.sndr_db
    say(f"Reference, effectively unquantized: {ref:.1f} dB")
    say()

    say("Coefficient width, states held wide")
    say(f"  {'total bits':>10}  {'SNDR':>8}  {'loss':>6}")
    cpick = None
    for cf in (8, 10, 12, 14, 18, 22):
        r = modarith.simulate_fixed(ntf, u, FS, f, coeff_frac=cf,
                                    state_frac=30, state_int=1)
        loss = ref - r.m.sndr_db
        say(f"  {cf+2:>10}  {r.m.sndr_db:>8.1f}  {loss:>6.1f}")
        if cpick is None and loss < 0.5:
            cpick = cf
    say(f"  -> {cpick + 2} bits total is enough")
    say()

    say("Which integrator needs the width: all at 20 bits, widen one to 28")
    base = modarith.simulate_fixed(ntf, u, FS, f, coeff_frac=cpick,
                                   state_frac=[18] * 3, state_int=1).m.sndr_db
    say(f"  {'widened':>14}  {'SNDR':>8}  {'gain':>6}")
    say(f"  {'none':>14}  {base:>8.1f}  {'-':>6}")
    for j in range(3):
        w = [18] * 3
        w[j] = 26
        r = modarith.simulate_fixed(ntf, u, FS, f, coeff_frac=cpick,
                                    state_frac=w, state_int=1)
        say(f"  {'integrator ' + str(j + 1):>14}  {r.m.sndr_db:>8.1f}  "
            f"{r.m.sndr_db - base:>6.1f}")
    say("  -> only the first. Rounding there is integrated twice more before")
    say("     it reaches the quantizer, so it is amplified at low frequency;")
    say("     rounding at the last integrator is not integrated at all.")
    say()

    # Holding the first integrator at 28 bits caps the result below a fully
    # wide reference, so 2 and 3 are measured against that cap rather than
    # against a figure they cannot reach. The question is how narrow they can
    # be before they, rather than the first integrator, set the limit.
    cap = modarith.simulate_fixed(ntf, u, FS, f, coeff_frac=cpick,
                                  state_frac=[26, 30, 30], state_int=1).m.sndr_db
    say(f"Integrators 2 and 3, with the first held at 28 bits (cap {cap:.1f} dB)")
    say(f"  {'total bits':>10}  {'SNDR':>8}  {'below cap':>10}")
    spick = None
    for sf in (10, 12, 14, 16, 18, 20):
        r = modarith.simulate_fixed(ntf, u, FS, f, coeff_frac=cpick,
                                    state_frac=[26, sf, sf], state_int=1)
        loss = cap - r.m.sndr_db
        say(f"  {sf+2:>10}  {r.m.sndr_db:>8.1f}  {loss:>10.1f}")
        if spick is None and loss < 0.5:
            spick = sf
    spick = spick if spick is not None else 20
    say(f"  -> {spick + 2} bits total is enough")
    say()

    W = [26, spick, spick]
    say(f"Check: coefficients {cpick+2} bits, states {[v+2 for v in W]} bits")
    say(f"  {'input':>22}  {'SNDR':>8}  {'ovf':>5}  {'peak states':>24}")
    worst = 0.0
    for hz, amp in ((1000.0, -3.7), (6000.0, -3.7), (19000.0, -3.7),
                    (1000.0, -0.9)):
        uu, ff = modulator.tone(N, FS, hz, amp)
        r = modarith.simulate_fixed(ntf, uu, FS, ff, coeff_frac=cpick,
                                    state_frac=W, state_int=1)
        pk = "[" + ", ".join(f"{p:.3f}" for p in r.peak) + "]"
        worst = max(worst, max(r.peak))
        say(f"  {hz:>9.0f} Hz {amp:>5.1f}  {r.m.sndr_db:>8.1f}  "
            f"{r.overflow:>5}  {pk:>24}")
    x = endtoend.source_intersample(N, -3.83)
    r = modarith.simulate_fixed(ntf, x, FS, 1000.0, coeff_frac=cpick,
                                state_frac=W, state_int=1)
    pk = "[" + ", ".join(f"{p:.3f}" for p in r.peak) + "]"
    worst = max(worst, max(r.peak))
    say(f"  {'inter-sample':>22}  {'n/a':>8}  {r.overflow:>5}  {pk:>24}")
    say()
    say("  Tones below about 200 Hz are not measurable here: at 23.4 Hz bins")
    say("  the signal and its harmonics occupy the whole lower band. Their")
    say("  peak states and overflow counts are still valid.")
    say()
    say(f"  One integer bit is required, not optional. The largest state seen")
    say(f"  above is {worst:.2f}, near the maximum stable input, and it moves")
    say(f"  with the coefficient rounding: an earlier sweep reached 1.13. Zero")
    say(f"  integer bits would overflow; one gives range +/-2.")

    (HERE / "results" / "modarith.txt").write_text("\n".join(log) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

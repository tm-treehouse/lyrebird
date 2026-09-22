# Review: the DSP model (`model/`)

Reviewer: review agent, 2026-09-21. Scope: `model/lyrebird_model/*.py` (13
modules), `model/run_*.py`, `model/README.md`, `model/notes-*.md`,
`model/results/*.txt`, `model/export_coefficients.py`. Read-only on everything
else; no git commands run.

Priorities, as given: (1) a sixth stale measurement site, (2) README claims
against the result logs, (3) reproducibility, (4) the model against its own
trap list, (5) coefficient-export consistency.

Out of scope by instruction, and *not* reported below as a defect: the
reference-rail transition-current result in `notes-idle.md` section H is
deliberately a prediction from a digital proxy, and the model has no supply.

---

## 1. Stale measurement sites

### 1.1 FINDING (high): `datapath.rounding_noise` removes the arithmetic mean before a Kaiser transform

`model/lyrebird_model/datapath.py:305-306`

```python
offset = float(e.mean())
noise = band_power_dbfs(e - offset, mode.element_clock, band)
```

`band_power_dbfs` (`datapath.py:256-263`) calls
`spectra.power_spectrum(x)` with no window argument, so it windows with the
same Kaiser beta 26 every other measurement uses, and integrates
`f >= 20 Hz`. The mean subtracted one line earlier is the *arithmetic* mean.
This is the exact construction `spectra.remove_dc` exists to prevent, at a
sixth site that `notes-idle.md`'s "five sites" table does not list.

It is not routed through `spectra.Measurement`, so the `dedc=True` default
never sees it, and `spectra.remove_dc` is never called on this path.

What it feeds -- every number in README.md's "Datapath width" section:

* the per-stage minimum-fractional-bits table (27/26/26/25/24/24/24/23/22);
* the taper-versus-flat table (-155.9 / -153.3 / -160.5 / **-165.5** /
  -172.0 dBFS) and therefore the "the taper is 9.6 dB noisier" finding and the
  28-bit signal-word recommendation;
* the accumulator table's "signal word alone" column and its 35/33/31 grouping;
* the "Datapath noise" column of "What the recommended datapath measures";
* the trap-list claim "Measured on the nine-stage chain it was -143.1 dBFS
  against a rounding noise of -159.5 dBFS".

Measured below in section 1.2.

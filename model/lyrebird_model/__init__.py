"""Numerical model of the Lyrebird audio chain.

24-bit PCM at Fs -> half-band interpolation cascade -> 3-bit delta-sigma
modulator -> data weighted averaging -> 7 differential element pairs per
channel -> weighted sum -> analog output.

The fixed facts of the design live in :mod:`lyrebird_model.chain`; everything
else in this package is a measurement of a choice made against them.

Submodules: chain, spectra, halfband, modulator, dwa, datapath,
endtoend.
"""

__all__ = ["chain", "spectra", "halfband", "modulator", "dwa", "datapath",
           "endtoend"]

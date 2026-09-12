"""Data weighted averaging over the thermometer elements.

Fixed by 0008: three-bit quantizer, eight levels, seven unit elements per
side, differential. For code k the positive side drives k elements and the
negative side drives seven minus k, so exactly seven elements are high at
every code and the reference sees a signal-independent load.

Mismatch between elements is not noise-shaped. It lands in the audio band as
distortion. Rotating which physical element carries a given code makes each
one used equally over time, so the average is correct and the mismatch becomes
a high-frequency error the loop shapes out of band. Rotation only works among
elements of equal weight, which is why the coding is thermometer rather than
binary.
"""

from __future__ import annotations

import numpy as np

from .chain import N_ELEMENTS, N_LEVELS


def select_fixed(codes: np.ndarray, n: int = N_ELEMENTS) -> np.ndarray:
    """Always light the lowest-numbered elements. No rotation.

    Returns a boolean array, one row per sample, one column per element.
    This is the comparison case: it is what you get if you ignore mismatch.
    """
    codes = np.asarray(codes, dtype=np.int64)
    idx = np.arange(n)[None, :]
    return idx < codes[:, None]


def select_rotated(codes: np.ndarray, n: int = N_ELEMENTS,
                   start: int = 0) -> np.ndarray:
    """Light k consecutive elements starting where the last code stopped.

    The pointer advances by the code each sample and wraps, so over time every
    element is used equally often regardless of the signal.
    """
    codes = np.asarray(codes, dtype=np.int64)
    # Pointer before each sample: the running sum of all previous codes.
    ptr = (start + np.concatenate(([0], np.cumsum(codes)[:-1]))) % n
    idx = np.arange(n)[None, :]
    # Element j is on when its offset from the pointer is below the code.
    offset = (idx - ptr[:, None]) % n
    return offset < codes[:, None]


def differential(codes: np.ndarray, rotate: bool = True,
                 n: int = N_ELEMENTS) -> tuple[np.ndarray, np.ndarray]:
    """Split codes across the two sides, k positive and n-k negative.

    Each side rotates independently, so each side's elements are exercised
    evenly. Returns (positive, negative) selection arrays.
    """
    codes = np.asarray(codes, dtype=np.int64)
    if codes.min() < 0 or codes.max() > n:
        raise ValueError(f"codes must lie in 0..{n}")
    pick = select_rotated if rotate else select_fixed
    return pick(codes, n), pick(n - codes, n)


def loading(pos: np.ndarray, neg: np.ndarray) -> np.ndarray:
    """Elements high per sample. Must be constant; that is the whole point."""
    return pos.sum(axis=1) + neg.sum(axis=1)


def analog(pos: np.ndarray, neg: np.ndarray,
           w_pos: np.ndarray | None = None,
           w_neg: np.ndarray | None = None) -> np.ndarray:
    """Weighted difference of the two sides, as the resistors will sum them.

    Weights default to unity, meaning perfectly matched elements. Supplying
    weights is how element mismatch is injected without re-simulating.
    """
    n = pos.shape[1]
    w_pos = np.ones(n) if w_pos is None else np.asarray(w_pos, float)
    w_neg = np.ones(n) if w_neg is None else np.asarray(w_neg, float)
    return pos @ w_pos - neg @ w_neg


def mismatch(sigma: float, n: int = N_ELEMENTS, *,
             seed: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Gaussian element weights with the given fractional standard deviation.

    sigma is a fraction, so 0.001 is 0.1 percent. Real thin film arrays are
    specified by ratio tolerance, which this approximates.
    """
    rng = np.random.default_rng(seed)
    return (1.0 + sigma * rng.standard_normal(n),
            1.0 + sigma * rng.standard_normal(n))


def normalise(x: np.ndarray, n: int = N_ELEMENTS) -> np.ndarray:
    """Scale a differential element sum to full scale of plus/minus one."""
    return np.asarray(x, float) / n


__all__ = ["select_fixed", "select_rotated", "differential", "loading",
           "analog", "mismatch", "normalise", "N_ELEMENTS", "N_LEVELS"]

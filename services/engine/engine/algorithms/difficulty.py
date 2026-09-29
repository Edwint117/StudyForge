"""Question difficulty calibration (DIAG-01): 1–5 difficulty from real attempts.

Each difficulty level has an expected failure rate. A question starts at its authored/generated difficulty; its
observed failure rate is smoothed toward that prior with ``PRIOR_WEIGHT`` pseudo-attempts (Beta-style shrinkage),
then mapped back to the nearest level (fractional levels are kept for blueprint matching). One or two attempts
barely move it; dozens dominate.
"""

from __future__ import annotations

from itertools import pairwise

VERSION = "difficulty-1"

FAIL_RATE_BY_LEVEL = {1: 0.10, 2: 0.25, 3: 0.40, 4: 0.55, 5: 0.70}
PRIOR_WEIGHT = 5.0


def _rate_for(level: float) -> float:
    """Expected failure rate for a (possibly fractional) level, by linear interpolation."""
    lv = min(5.0, max(1.0, level))
    lo = int(lv)
    hi = min(5, lo + 1)
    frac = lv - lo
    return FAIL_RATE_BY_LEVEL[lo] * (1 - frac) + FAIL_RATE_BY_LEVEL[hi] * frac


def _level_for(rate: float) -> float:
    """Inverse of ``_rate_for`` (clamped to [1, 5])."""
    pts = sorted(FAIL_RATE_BY_LEVEL.items())
    if rate <= pts[0][1]:
        return 1.0
    if rate >= pts[-1][1]:
        return 5.0
    for (l1, r1), (l2, r2) in pairwise(pts):
        if r1 <= rate <= r2:
            return l1 + (rate - r1) / (r2 - r1) * (l2 - l1)
    return 3.0  # unreachable with monotone rates


def calibrated_difficulty(prior_level: float, attempts: int, failures: int) -> float:
    if attempts < 0 or not 0 <= failures <= attempts:
        raise ValueError("need 0 <= failures <= attempts")
    smoothed = (failures + PRIOR_WEIGHT * _rate_for(prior_level)) / (attempts + PRIOR_WEIGHT)
    return round(_level_for(smoothed), 2)

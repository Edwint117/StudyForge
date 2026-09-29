"""FSRS-6 forgetting-curve math (doc 05 §1).

Only the closed-form formulas live here: retrievability and interval. Scheduling state transitions stay in
the pinned FSRS libraries (ts-fsrs online, py-fsrs for the optimizer); the parity test (M7-01) must confirm
``DEFAULT_DECAY`` matches the pinned library's default ``w[20]``.
"""

from __future__ import annotations

import math

VERSION = "fsrs6-math-1"

# FSRS-6 default decay parameter w[20]. Verify against the pinned py-fsrs / ts-fsrs defaults in M7-01.
DEFAULT_DECAY = 0.1542


def _factor(decay: float) -> float:
    if decay <= 0:
        raise ValueError("decay must be positive")
    return float(0.9 ** (-1.0 / decay) - 1.0)


def retrievability(elapsed_days: float, stability: float, decay: float = DEFAULT_DECAY) -> float:
    """R(t, S) = (1 + F·t/S)^(−decay), with F = 0.9^(−1/decay) − 1. R(0)=1 and R(S)=0.9."""
    if stability <= 0:
        raise ValueError("stability must be positive")
    if elapsed_days < 0:
        raise ValueError("elapsed_days must be >= 0")
    return float((1.0 + _factor(decay) * elapsed_days / stability) ** (-decay))


def interval_days(desired_retention: float, stability: float, decay: float = DEFAULT_DECAY) -> float:
    """I(r, S) = (S/F)·(r^(−1/decay) − 1): days until retrievability falls to ``desired_retention``."""
    if not 0.0 < desired_retention < 1.0:
        raise ValueError("desired_retention must be in (0, 1)")
    if stability <= 0:
        raise ValueError("stability must be positive")
    return float(stability / _factor(decay) * (desired_retention ** (-1.0 / decay) - 1.0))


def review_interval_days(desired_retention: float, stability: float, decay: float = DEFAULT_DECAY) -> int:
    """Interval rounded to whole days (>= 1), as used for review-state cards."""
    return max(1, round(interval_days(desired_retention, stability, decay)))


def log_loss(predictions: list[tuple[float, bool]], eps: float = 1e-9) -> float:
    """Mean binary cross-entropy of (predicted recall probability, actually recalled) pairs."""
    if not predictions:
        raise ValueError("no predictions")
    total = 0.0
    for p, recalled in predictions:
        q = min(max(p, eps), 1.0 - eps)
        total += -math.log(q) if recalled else -math.log(1.0 - q)
    return total / len(predictions)

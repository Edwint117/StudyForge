"""Mastery model ``mastery-1`` and readiness forecast (doc 05 §5; DIAG-06/07, COMP-03).

Concept mastery combines three evidence sources, each in [0, 1]:

* retention: mean FSRS retrievability *now* over the concept's active, already-reviewed cards;
* performance: recency-weighted mean score of question attempts and verified card reviews (half-life 14 days);
* feynman: the latest Feynman coverage score, decayed with the same half-life.

Weights 0.35 / 0.50 / 0.15 are renormalized over the components that exist; no evidence → ``None`` ("not started").
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from engine.algorithms.fsrs_math import DEFAULT_DECAY, retrievability

VERSION = "mastery-1"
HALF_LIFE_DAYS = 14.0
WEIGHTS = {"retention": 0.35, "perf": 0.50, "feynman": 0.15}
CONFIDENCE_EVIDENCE = 8
ERROR_MIX_WINDOW_DAYS = 30
# Unstarted units in the readiness forecast: counted as 0 mastery with maximal Bernoulli variance.
UNSTARTED_VARIANCE = 0.25


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CardEvidence(_Frozen):
    """An active card linked to the concept. ``last_review``/``stability`` are None for never-reviewed cards."""

    stability: float | None = Field(default=None, gt=0)
    last_review: datetime | None = None


class ScoredEvidence(_Frozen):
    """A question attempt or verified card review touching the concept; ``score`` in [0, 1]."""

    score: float = Field(ge=0, le=1)
    at: datetime


class FeynmanEvidence(_Frozen):
    coverage: float = Field(ge=0, le=1)
    at: datetime


class ConceptMastery(_Frozen):
    mastery: float | None
    confidence: float
    components: dict[str, float]
    n_evidence: int


def decay_weight(age_days: float, half_life_days: float = HALF_LIFE_DAYS) -> float:
    return float(0.5 ** (max(age_days, 0.0) / half_life_days))


def _age_days(now: datetime, at: datetime) -> float:
    return (now - at) / timedelta(days=1)


def concept_mastery(
    now: datetime,
    cards: Sequence[CardEvidence] = (),
    scored: Sequence[ScoredEvidence] = (),
    feynman: Sequence[FeynmanEvidence] = (),
    decay: float = DEFAULT_DECAY,
) -> ConceptMastery:
    components: dict[str, float] = {}

    reviewed = [(c.stability, c.last_review) for c in cards if c.stability is not None and c.last_review is not None]
    if reviewed:
        r_values = [retrievability(_age_days(now, last), stability, decay) for stability, last in reviewed]
        components["retention"] = sum(r_values) / len(r_values)

    if scored:
        weights = [decay_weight(_age_days(now, e.at)) for e in scored]
        components["perf"] = sum(w * e.score for w, e in zip(weights, scored, strict=True)) / sum(weights)

    if feynman:
        latest = max(feynman, key=lambda f: f.at)
        components["feynman"] = latest.coverage * decay_weight(_age_days(now, latest.at))

    total_w = sum(WEIGHTS[k] for k in components)
    mastery = sum(WEIGHTS[k] * v for k, v in components.items()) / total_w if components else None
    n_evidence = len(reviewed) + len(scored) + len(feynman)
    return ConceptMastery(
        mastery=mastery,
        confidence=min(1.0, n_evidence / CONFIDENCE_EVIDENCE),
        components=components,
        n_evidence=n_evidence,
    )


def weighted_mastery(items: Iterable[tuple[float | None, float]]) -> float | None:
    """Weighted mean over (mastery, weight) pairs, skipping unstarted (None) items and non-positive weights.

    Used for unit mastery (concept importance weights) and course/exam mastery (unit weights).
    """
    pairs = [(m, w) for m, w in items if m is not None and w > 0]
    if not pairs:
        return None
    return sum(m * w for m, w in pairs) / sum(w for _, w in pairs)


def error_mix(deductions: Iterable[tuple[str, datetime]], now: datetime) -> dict[str, int]:
    """Counts of ``error_class`` over deductions in the last 30 days (heatmap side bars)."""
    cutoff = now - timedelta(days=ERROR_MIX_WINDOW_DAYS)
    return dict(Counter(cls for cls, at in deductions if cutoff <= at <= now))


# ---------------------------------------------------------------- readiness forecast (DIAG-07)
class UnitReadinessInput(_Frozen):
    unit_id: str
    weight: float = Field(ge=0)  # syllabus weight (any scale; normalized internally)
    mastery: float | None = Field(default=None, ge=0, le=1)
    n_evidence: int = Field(default=0, ge=0)


class ReadinessForecast(_Frozen):
    predicted: float
    low: float
    high: float
    calibrated: bool


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def fit_calibration(history: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    """Least-squares ``actual ≈ a·predicted + b`` from (predicted, actual) pairs of past real exams.

    Returns None with fewer than 3 exams or no spread in predictions (the fit would be undefined).
    """
    if len(history) < 3:
        return None
    n = len(history)
    mx = sum(p for p, _ in history) / n
    my = sum(a for _, a in history) / n
    sxx = sum((p - mx) ** 2 for p, _ in history)
    if sxx < 1e-12:
        return None
    a = sum((p - mx) * (y - my) for p, y in history) / sxx
    return a, my - a * mx


def readiness_forecast(
    units: Sequence[UnitReadinessInput], calibration_history: Sequence[tuple[float, float]] = ()
) -> ReadinessForecast:
    total = sum(u.weight for u in units)
    if total <= 0:
        raise ValueError("exam units must have positive total weight")
    pred = 0.0
    var = 0.0
    for u in units:
        w = u.weight / total
        if u.mastery is None:
            var += w * w * UNSTARTED_VARIANCE
            continue
        pred += w * u.mastery
        var += w * w * u.mastery * (1.0 - u.mastery) / max(1, u.n_evidence)
    half = 1.96 * math.sqrt(var)
    low, high = pred - half, pred + half

    fit = fit_calibration(calibration_history)
    if fit is not None:
        a, b = fit
        pred, low, high = a * pred + b, a * low + b, a * high + b
        if a < 0:  # a negative slope would invert the band
            low, high = high, low
    return ReadinessForecast(
        predicted=_clamp01(pred), low=_clamp01(low), high=_clamp01(high), calibrated=fit is not None
    )


def mastery_by_unit(
    concept_mastery_by_id: Mapping[str, float | None],
    unit_concepts: Mapping[str, Sequence[tuple[str, float]]],
) -> dict[str, float | None]:
    """Unit mastery = importance-weighted mean of its concepts.

    ``unit_concepts`` maps unit → [(concept_id, importance)].
    """
    return {
        unit: weighted_mastery((concept_mastery_by_id.get(cid), imp) for cid, imp in members)
        for unit, members in unit_concepts.items()
    }

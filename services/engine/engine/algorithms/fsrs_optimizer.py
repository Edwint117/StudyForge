"""FSRS parameter adoption rule (doc 05 §1; SRS-02).

The optimizer itself (py-fsrs) is injected as ``trainer`` and ``predictor`` callables, so this module stays pure
and testable. It is wired to the pinned py-fsrs optimizer in M7.

Rule: need ≥ 400 reviews; split chronologically into the oldest 80% (train) and newest 20% (holdout); adopt the
candidate only if its holdout log-loss is at least 1% better than the currently active parameters'. Keep the
last 3 parameter sets for rollback.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from engine.algorithms.fsrs_math import log_loss

VERSION = "fsrs-adopt-1"
MIN_REVIEWS = 400
HOLDOUT_FRACTION = 0.20
MIN_IMPROVEMENT = 0.01
KEEP_PARAMETER_SETS = 3


class TimedReview(Protocol):
    @property
    def reviewed_at(self) -> datetime: ...


class AdoptionDecision[P](BaseModel):
    model_config = ConfigDict(frozen=True)
    adopt: bool
    reason: str
    train_size: int
    holdout_size: int
    current_logloss: float | None = None
    candidate_logloss: float | None = None
    candidate_params: P | None = None


def evaluate_candidate[R: TimedReview, P](
    reviews: Sequence[R],
    current_params: P,
    trainer: Callable[[Sequence[R]], P],
    predictor: Callable[[P, Sequence[R]], list[tuple[float, bool]]],
) -> AdoptionDecision[P]:
    if len(reviews) < MIN_REVIEWS:
        return AdoptionDecision[P](adopt=False, reason="insufficient_reviews", train_size=0, holdout_size=0)
    ordered = sorted(reviews, key=lambda r: r.reviewed_at)
    split = int(len(ordered) * (1 - HOLDOUT_FRACTION))
    train, holdout = ordered[:split], ordered[split:]

    candidate = trainer(train)
    current_ll = log_loss(predictor(current_params, holdout))
    candidate_ll = log_loss(predictor(candidate, holdout))
    adopt = candidate_ll <= current_ll * (1 - MIN_IMPROVEMENT)
    return AdoptionDecision[P](
        adopt=adopt,
        reason="improved" if adopt else "not_enough_improvement",
        train_size=len(train),
        holdout_size=len(holdout),
        current_logloss=current_ll,
        candidate_logloss=candidate_ll,
        candidate_params=candidate,
    )


def keep_recent[T](history: Sequence[T], new: T, keep: int = KEEP_PARAMETER_SETS) -> list[T]:
    """Append the newly adopted set and keep only the most recent ``keep`` (oldest dropped first)."""
    return [*history, new][-keep:]

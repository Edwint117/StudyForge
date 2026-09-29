from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from engine.algorithms.fsrs_optimizer import MIN_REVIEWS, evaluate_candidate, keep_recent

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Review:
    reviewed_at: datetime
    recalled: bool


def _reviews(train: dict[str, int], holdout: dict[str, int]) -> list[Review]:
    outcomes = (
        [True] * train["recalled"]
        + [False] * train["forgot"]
        + [True] * holdout["recalled"]
        + [False] * holdout["forgot"]
    )
    reviews = [Review(T0 + timedelta(hours=i), r) for i, r in enumerate(outcomes)]
    return list(reversed(reviews))  # unsorted input: the rule must sort chronologically itself


def trainer(train: Sequence[Review]) -> float:
    return sum(r.recalled for r in train) / len(train)


def predictor(p: float, reviews: Sequence[Review]) -> list[tuple[float, bool]]:
    return [(p, r.recalled) for r in reviews]


@pytest.mark.parametrize("name", ["optimizer_adopt.json", "optimizer_reject.json"])
def test_fixture_adoption(fixture: Any, name: str) -> None:
    fx = fixture(name)
    decision = evaluate_candidate(_reviews(fx["train"], fx["holdout"]), fx["current_p"], trainer, predictor)
    exp = fx["expected"]
    assert decision.adopt is exp["adopt"]
    assert decision.candidate_params == pytest.approx(exp["candidate_p"])
    assert decision.current_logloss == pytest.approx(exp["current_logloss"], abs=1e-6)
    assert decision.candidate_logloss == pytest.approx(exp["candidate_logloss"], abs=1e-6)
    assert (decision.train_size, decision.holdout_size) == (exp["train_size"], exp["holdout_size"])


def test_insufficient_reviews() -> None:
    few = _reviews({"recalled": MIN_REVIEWS - 1, "forgot": 0}, {"recalled": 0, "forgot": 0})
    decision = evaluate_candidate(few, 0.5, trainer, predictor)
    assert not decision.adopt and decision.reason == "insufficient_reviews"


def test_marginal_improvement_below_one_percent_is_rejected() -> None:
    # current p = 0.9 is nearly optimal for a 90% holdout; candidate 0.9 gives identical loss -> no 1% gain
    reviews = _reviews({"recalled": 360, "forgot": 40}, {"recalled": 90, "forgot": 10})
    assert not evaluate_candidate(reviews, 0.9, trainer, predictor).adopt


def test_keep_recent_parameter_sets() -> None:
    assert keep_recent([], "a") == ["a"]
    assert keep_recent(["a", "b", "c"], "d") == ["b", "c", "d"]

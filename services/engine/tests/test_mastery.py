from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.algorithms.mastery import (
    CardEvidence,
    FeynmanEvidence,
    ScoredEvidence,
    UnitReadinessInput,
    concept_mastery,
    error_mix,
    fit_calibration,
    mastery_by_unit,
    readiness_forecast,
    weighted_mastery,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _parse(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "cards": [CardEvidence.model_validate(c) for c in d["cards"]],
        "scored": [ScoredEvidence.model_validate(s) for s in d["scored"]],
        "feynman": [FeynmanEvidence.model_validate(f) for f in d["feynman"]],
    }


def test_fixture_mastery_components(fixture: Any) -> None:
    fx = fixture("mastery_components.json")
    result = concept_mastery(datetime.fromisoformat(fx["now"]), **_parse(fx))
    exp = fx["expected"]
    assert result.mastery == pytest.approx(exp["mastery"], abs=1e-6)
    assert result.confidence == pytest.approx(exp["confidence"])
    for key in ("retention", "perf", "feynman"):
        assert result.components[key] == pytest.approx(exp[key], abs=1e-6)


def test_fixture_mastery_missing_components(fixture: Any) -> None:
    fx = fixture("mastery_missing_components.json")
    for case in fx["cases"]:
        result = concept_mastery(datetime.fromisoformat(fx["now"]), **_parse(case))
        exp = case["expected"]
        if exp["mastery"] is None:
            assert result.mastery is None
        else:
            assert result.mastery == pytest.approx(exp["mastery"])
        assert result.confidence == pytest.approx(exp["confidence"])
        assert sorted(result.components) == sorted(exp["components"])


def test_fixture_readiness_band(fixture: Any) -> None:
    fx = fixture("readiness_band.json")
    units = [UnitReadinessInput.model_validate(u) for u in fx["units"]]
    for history, key in (([], "expected"), (fx["calibration_history"], "expected_calibrated")):
        out = readiness_forecast(units, [tuple(h) for h in history])
        exp = fx[key]
        assert out.predicted == pytest.approx(exp["predicted"], abs=1e-6)
        assert out.low == pytest.approx(exp["low"], abs=1e-6)
        assert out.high == pytest.approx(exp["high"], abs=1e-6)
        assert out.calibrated is exp["calibrated"]


@given(
    st.lists(st.tuples(st.floats(0, 1), st.floats(0, 60)), max_size=6),
    st.lists(st.tuples(st.floats(0.5, 400), st.floats(0, 400)), max_size=6),
)
def test_mastery_always_in_unit_interval(scores: list[tuple[float, float]], cards: list[tuple[float, float]]) -> None:
    result = concept_mastery(
        NOW,
        cards=[CardEvidence(stability=s, last_review=NOW - timedelta(days=age)) for s, age in cards],
        scored=[ScoredEvidence(score=sc, at=NOW - timedelta(days=age)) for sc, age in scores],
    )
    if result.mastery is not None:
        assert 0.0 <= result.mastery <= 1.0
    assert 0.0 <= result.confidence <= 1.0


def test_older_evidence_counts_less() -> None:
    fresh_good = concept_mastery(
        NOW,
        scored=[ScoredEvidence(score=1, at=NOW), ScoredEvidence(score=0, at=NOW - timedelta(days=60))],
    )
    fresh_bad = concept_mastery(
        NOW,
        scored=[ScoredEvidence(score=0, at=NOW), ScoredEvidence(score=1, at=NOW - timedelta(days=60))],
    )
    assert fresh_good.mastery is not None and fresh_bad.mastery is not None
    assert fresh_good.mastery > 0.9 > 0.1 > fresh_bad.mastery


def test_weighted_mastery_and_units() -> None:
    assert weighted_mastery([]) is None
    assert weighted_mastery([(None, 3.0), (0.5, 1.0)]) == pytest.approx(0.5)
    assert weighted_mastery([(1.0, 3.0), (0.0, 1.0)]) == pytest.approx(0.75)
    units = mastery_by_unit({"k1": 1.0, "k2": 0.0, "k3": None}, {"u1": [("k1", 3), ("k2", 1)], "u2": [("k3", 1)]})
    assert units == {"u1": pytest.approx(0.75), "u2": None}


def test_error_mix_window() -> None:
    deductions = [
        ("calculation_slip", NOW - timedelta(days=1)),
        ("calculation_slip", NOW - timedelta(days=5)),
        ("conceptual", NOW - timedelta(days=29)),
        ("conceptual", NOW - timedelta(days=31)),  # outside the 30-day window
    ]
    assert error_mix(deductions, NOW) == {"calculation_slip": 2, "conceptual": 1}


def test_calibration_needs_three_exams_and_spread() -> None:
    assert fit_calibration([(0.5, 0.6), (0.7, 0.8)]) is None
    assert fit_calibration([(0.5, 0.6), (0.5, 0.7), (0.5, 0.8)]) is None
    a, b = fit_calibration([(0.5, 0.6), (0.7, 0.8), (0.9, 1.0)])  # type: ignore[misc]
    assert a == pytest.approx(1.0) and b == pytest.approx(0.1)


def test_readiness_requires_positive_weight() -> None:
    with pytest.raises(ValueError):
        readiness_forecast([UnitReadinessInput(unit_id="a", weight=0, mastery=0.5)])

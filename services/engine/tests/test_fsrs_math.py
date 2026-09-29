import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.algorithms.fsrs_math import interval_days, log_loss, retrievability, review_interval_days


def test_retrievability_anchor_points() -> None:
    assert retrievability(0, 10) == pytest.approx(1.0)
    # By definition of FSRS stability, R(S) = 0.9 for any decay.
    for decay in (0.1542, 0.5, 1.0):
        assert retrievability(10, 10, decay) == pytest.approx(0.9)


@given(st.floats(0.5, 0.99), st.floats(0.1, 3650), st.floats(0.05, 1.0))
def test_interval_inverts_retrievability(r: float, s: float, decay: float) -> None:
    assert retrievability(interval_days(r, s, decay), s, decay) == pytest.approx(r, rel=1e-9)


@given(st.floats(0, 1000), st.floats(0, 1000), st.floats(0.1, 500))
def test_retrievability_monotone_decreasing(t1: float, t2: float, s: float) -> None:
    lo, hi = sorted((t1, t2))
    assert retrievability(hi, s) <= retrievability(lo, s) + 1e-15


def test_review_interval_rounds_and_floors_at_one_day() -> None:
    assert review_interval_days(0.9, 0.2) == 1
    assert review_interval_days(0.9, 30) == 30


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        retrievability(1, 0)
    with pytest.raises(ValueError):
        interval_days(1.0, 10)
    with pytest.raises(ValueError):
        retrievability(-1, 10)


def test_log_loss() -> None:
    assert log_loss([(0.9, True)]) == pytest.approx(-math.log(0.9))
    assert log_loss([(0.9, False)]) == pytest.approx(-math.log(0.1))
    assert log_loss([(1.0, True), (0.0, False)]) < 1e-6
    with pytest.raises(ValueError):
        log_loss([])

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.algorithms.difficulty import calibrated_difficulty


def test_no_attempts_keeps_prior() -> None:
    for level in (1, 2, 3, 4, 5):
        assert calibrated_difficulty(level, 0, 0) == level


def test_few_attempts_move_little_many_move_a_lot() -> None:
    # (1 + 5*0.40) / (1 + 5) = 0.50 failure rate, 2/3 of the way from level 3 (0.40) to 4 (0.55)
    assert calibrated_difficulty(3, 1, 1) == pytest.approx(3.67)
    assert calibrated_difficulty(3, 100, 95) >= 4.9  # overwhelming evidence: very hard
    assert calibrated_difficulty(3, 100, 2) <= 1.2  # almost everyone gets it: very easy


def test_invalid_counts() -> None:
    with pytest.raises(ValueError):
        calibrated_difficulty(3, 2, 3)


@given(st.floats(1, 5), st.integers(0, 200), st.data())
def test_bounded_and_monotone_in_failures(prior: float, attempts: int, data: st.DataObject) -> None:
    f1 = data.draw(st.integers(0, attempts))
    f2 = data.draw(st.integers(f1, attempts))
    d1, d2 = calibrated_difficulty(prior, attempts, f1), calibrated_difficulty(prior, attempts, f2)
    assert 1 <= d1 <= d2 <= 5

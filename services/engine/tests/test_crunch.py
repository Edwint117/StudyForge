from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.algorithms.crunch import (
    CrunchCard,
    CrunchExam,
    ScopeUnit,
    applicable_exam,
    build_crunch_queue,
    card_weight,
    crunch_interval,
    schedule_review,
)
from engine.algorithms.fsrs_math import interval_days


def _single_exam_case(fx: dict[str, Any]) -> None:
    exam = CrunchExam.model_validate(fx["exam"])
    reviewed_at = datetime.fromisoformat(fx["reviewed_at"])
    sched = schedule_review(fx["concept_ids"], fx["stability_after"], reviewed_at, [exam], fx["desired_retention"])
    assert sched is not None
    exp = fx["expected"]
    assert sched.exam_id == exam.exam_id
    assert sched.interval.kind == exp["kind"]
    assert sched.interval.r_exam == pytest.approx(exp["r_exam"])
    assert sched.interval.r_at_exam == pytest.approx(exp["r_at_exam"], abs=1e-6)
    assert sched.interval.i_fsrs == pytest.approx(exp["i_fsrs"], abs=1e-3)
    assert sched.interval.i_cap == pytest.approx(exp["i_cap"])
    assert sched.interval.interval_days == pytest.approx(exp["interval_days"])
    assert sched.due_at == datetime.fromisoformat(exp["due_at"])
    assert sched.window_start is None and sched.window_end is None


def test_fixture_crunch_interval_cap(fixture: Any) -> None:
    _single_exam_case(fixture("crunch_interval_cap.json"))


def test_fixture_crunch_single_touch(fixture: Any) -> None:
    _single_exam_case(fixture("crunch_single_touch.json"))


def test_fixture_crunch_multi_exam(fixture: Any) -> None:
    fx = fixture("crunch_multi_exam.json")
    exams = [CrunchExam.model_validate(e) for e in fx["exams"]]
    reviewed_at = datetime.fromisoformat(fx["reviewed_at"])
    exp = fx["expected"]

    sched = schedule_review(fx["concept_ids"], fx["stability_after"], reviewed_at, exams)
    assert sched is not None
    assert sched.exam_id == exp["exam_id"]
    assert sched.interval.kind == exp["kind"]
    assert sched.interval.interval_days == pytest.approx(exp["interval_days"])
    assert sched.due_at == datetime.fromisoformat(exp["due_at"])

    early = next(e for e in exams if e.exam_id == exp["exam_id"])
    card = CrunchCard(card_id="c", unit_id="U1", concept_ids=tuple(fx["concept_ids"]))
    assert card_weight(card, early) == pytest.approx(exp["card_weight"])

    late = [e for e in exams if e.exam_id == "E_late"]
    alt = schedule_review(fx["concept_ids"], fx["stability_after"], reviewed_at, late)
    assert alt is not None
    assert alt.interval.kind == exp["if_late_exam"]["kind"]
    assert alt.interval.interval_days == pytest.approx(exp["if_late_exam"]["interval_days"])


def test_fixture_crunch_priority_order(fixture: Any) -> None:
    fx = fixture("crunch_priority_order.json")
    exam = CrunchExam.model_validate(fx["exam"])
    cards = [CrunchCard.model_validate(c) for c in fx["cards"]]
    now = datetime.fromisoformat(fx["now"])
    for case in fx["cases"]:
        q = build_crunch_queue(now, cards, [exam], case["capacity_minutes"], fx["median_response_ms"])
        assert list(q.review_card_ids) == case["review"]
        assert list(q.deferred_card_ids) == case["deferred"]
        assert list(q.new_card_ids) == case["new"]
        assert q.deficit_minutes == pytest.approx(case["deficit_minutes"], abs=1e-6)
        assert q.not_in_crunch_ids == ()
        for cid, p in fx["expected_priorities"].items():
            # Hand-chained logs carry ~5e-6 rounding; orders are separated by > 1e-3.
            assert q.priorities[cid] == pytest.approx(p, abs=1e-5)


NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _exam(days: float, concepts: tuple[str, ...] = ("k1",), exam_id: str = "E") -> CrunchExam:
    return CrunchExam(
        exam_id=exam_id,
        starts_at=NOW + timedelta(days=days),
        units=(ScopeUnit(unit_id="U", weight=100, concept_ids=concepts),),
    )


def test_cram_window_when_exam_is_close() -> None:
    exam = _exam(1.0)
    sched = schedule_review(["k1"], 3.0, NOW, [exam])
    assert sched is not None
    assert sched.interval.kind == "cram_window"
    assert sched.interval.interval_days is None and sched.due_at is None
    # T-36h is already past, so the window opens now and closes at T-6h.
    assert sched.window_start == NOW
    assert sched.window_end == exam.starts_at - timedelta(hours=6)


def test_cram_window_starts_at_t_minus_36h_when_still_ahead() -> None:
    # T = 1.5 days exactly: 36 h ahead, so the window starts now (== T-36h).
    exam = _exam(1.5)
    sched = schedule_review(["k1"], 3.0, NOW, [exam])
    assert sched is not None and sched.interval.kind == "cram_window"
    assert sched.window_start == exam.starts_at - timedelta(hours=36)


def test_normal_fsrs_outside_crunch_range_and_out_of_scope() -> None:
    assert schedule_review(["k1"], 5.0, NOW, [_exam(7.5)]) is None
    assert schedule_review(["k2"], 5.0, NOW, [_exam(3)]) is None
    assert schedule_review(["k1"], 5.0, NOW, []) is None
    # Exactly crunch_days away still triggers (≤).
    assert schedule_review(["k1"], 5.0, NOW, [_exam(7)]) is not None


def test_desired_retention_above_floor_is_used() -> None:
    iv = crunch_interval(10.0, 5.0, desired_retention=0.95)
    assert iv.r_exam == 0.95
    assert iv.i_fsrs == pytest.approx(interval_days(0.95, 10.0))


def test_min_cap_is_half_a_day() -> None:
    # T = 1.6: (1.6 - 0.75)/2 = 0.425 < 0.5 -> cap 0.5.
    iv = crunch_interval(1.0, 1.6)
    assert iv.i_cap == pytest.approx(0.5)
    assert iv.kind == "capped" and iv.interval_days == pytest.approx(0.5)


def test_validation_errors() -> None:
    with pytest.raises(ValueError):
        crunch_interval(5.0, 0.0)
    with pytest.raises(ValueError):
        CrunchExam(exam_id="e", starts_at=datetime(2026, 10, 1), units=())
    with pytest.raises(ValueError):
        applicable_exam(["k1"], [], datetime(2026, 10, 1))
    with pytest.raises(ValueError):
        build_crunch_queue(NOW, [], [], -1)
    with pytest.raises(ValueError):
        build_crunch_queue(NOW, [], [], 10, median_response_ms=0)


def test_new_cards_not_introduced_within_two_days() -> None:
    exam = _exam(1.9)
    new = CrunchCard(card_id="n", unit_id="U", concept_ids=("k1",))
    q = build_crunch_queue(NOW, [new], [exam], capacity_minutes=60)
    assert q.new_card_ids == ()
    q2 = build_crunch_queue(NOW, [new], [_exam(2)], capacity_minutes=60)
    assert q2.new_card_ids == ("n",)


def test_cards_outside_crunch_reported() -> None:
    card = CrunchCard(card_id="x", unit_id="U", concept_ids=("k9",), stability=3, last_review=NOW)
    q = build_crunch_queue(NOW, [card], [_exam(3)], capacity_minutes=10)
    assert q.not_in_crunch_ids == ("x",)
    assert q.review_card_ids == () and q.priorities == {}


@given(
    stability=st.floats(min_value=0.1, max_value=36500),
    days=st.floats(min_value=0.01, max_value=7),
    retention=st.floats(min_value=0.7, max_value=0.99),
)
def test_crunch_interval_properties(stability: float, days: float, retention: float) -> None:
    iv = crunch_interval(stability, days, retention)
    assert iv.r_exam >= 0.93
    if days <= 1.5:
        assert iv.kind == "cram_window" and iv.interval_days is None
        return
    assert iv.interval_days is not None
    # Every crunch review lands before the exam and never lengthens the FSRS interval.
    assert 0 < iv.interval_days < days
    assert iv.interval_days <= iv.i_fsrs + 1e-9
    if iv.kind == "capped":
        assert iv.interval_days <= (iv.i_cap or 0) + 1e-12


card_strategy = st.builds(
    CrunchCard,
    card_id=st.text("abcdef0123456789", min_size=3, max_size=6),
    unit_id=st.just("U"),
    concept_ids=st.lists(st.sampled_from(["k1", "k2", "k3", "k9"]), min_size=1, max_size=3, unique=True).map(tuple),
    kind=st.sampled_from(["definition", "formula", "text"]),
    stability=st.one_of(st.none(), st.floats(min_value=0.1, max_value=500)),
    last_review=st.just(NOW - timedelta(days=1)),
    recent_lapses=st.integers(min_value=0, max_value=4),
    topo_rank=st.integers(min_value=0, max_value=5),
)


@given(
    cards=st.lists(card_strategy, max_size=25, unique_by=lambda c: c.card_id),
    capacity=st.floats(min_value=0, max_value=10),
    days=st.floats(min_value=0.5, max_value=10),
)
def test_crunch_queue_properties(cards: list[CrunchCard], capacity: float, days: float) -> None:
    exam = CrunchExam(
        exam_id="E",
        starts_at=NOW + timedelta(days=days),
        units=(
            ScopeUnit(unit_id="A", weight=70, concept_ids=("k1", "k2")),
            ScopeUnit(unit_id="B", weight=30, concept_ids=("k3",)),
        ),
    )
    q = build_crunch_queue(NOW, cards, [exam], capacity, median_response_ms=12_000)
    slots = int(capacity / 0.2 + 1e-9)
    assert len(q.review_card_ids) + len(q.new_card_ids) <= slots
    ids = [c.card_id for c in cards]
    placed = [*q.review_card_ids, *q.deferred_card_ids, *q.new_card_ids, *q.not_in_crunch_ids]
    assert len(placed) == len(set(placed))
    assert set(placed) <= set(ids)
    pr = [q.priorities[c] for c in q.review_card_ids]
    assert pr == sorted(pr, reverse=True)
    if q.deferred_card_ids:
        assert q.new_card_ids == ()
        if pr:
            assert min(pr) >= max(q.priorities[c] for c in q.deferred_card_ids)
    for c in cards:
        assert 0.0 <= card_weight(c, exam) <= 1.0 + 1e-12

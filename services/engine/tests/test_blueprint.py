from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.algorithms.blueprint import (
    TYPE_POINTS,
    BankItem,
    BlueprintUnit,
    build_blueprint,
    drop_slot,
    select_questions,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _units() -> list[BlueprintUnit]:
    return [
        BlueprintUnit(unit_id="U1", weight=40, mastery=0.9),
        BlueprintUnit(unit_id="U2", weight=40, mastery=0.2),
        BlueprintUnit(unit_id="U3", weight=20, mastery=None),
    ]


def test_blueprint_points_units_and_weakness() -> None:
    bp = build_blueprint(_units(), total_points=100)
    assert sum(s.points for s in bp.slots) == 100
    assert {s.unit_id for s in bp.slots} == {"U1", "U2", "U3"}
    pts = {u: sum(s.points for s in bp.slots if s.unit_id == u) for u in ("U1", "U2", "U3")}
    # same weight, weaker unit gets more points: 40*1.05=42 vs 40*1.4=56 vs 20*1.5=30 (of 128) -> 33/44/23
    assert pts["U2"] > pts["U1"]
    assert pts == {"U1": 33, "U2": 44, "U3": 23}


def test_blueprint_difficulty_mean_and_high_weight_hard_question() -> None:
    bp = build_blueprint(_units(), total_points=100)
    diffs = [s.difficulty for s in bp.slots]
    assert sum(diffs) / len(diffs) == pytest.approx(3.0)
    for unit in ("U1", "U2"):  # weight >= median
        assert any(s.difficulty >= 4 for s in bp.slots if s.unit_id == unit)


def test_default_type_mix_uses_code_only_when_course_has_code() -> None:
    assert "proof" in build_blueprint(_units()).type_mix
    assert "code" in build_blueprint(_units(), course_has_code=True).type_mix


def test_type_mix_is_respected_roughly() -> None:
    bp = build_blueprint(_units(), total_points=100)
    by_type = {t: sum(s.points for s in bp.slots if s.type == t) for t in bp.type_mix}
    for t, share in bp.type_mix.items():
        assert abs(by_type[t] / 100 - share) <= 0.15


@settings(max_examples=60)
@given(
    st.lists(st.tuples(st.floats(1, 100), st.one_of(st.none(), st.floats(0, 1))), min_size=1, max_size=8),
    st.integers(40, 200),
)
def test_blueprint_invariants(rows: list[tuple[float, float | None]], total: int) -> None:
    units = [BlueprintUnit(unit_id=f"U{i}", weight=w, mastery=m) for i, (w, m) in enumerate(rows)]
    bp = build_blueprint(units, total_points=total)
    assert sum(s.points for s in bp.slots) == total
    assert {s.unit_id for s in bp.slots} == {u.unit_id for u in units}
    assert all(1 <= s.difficulty <= 5 for s in bp.slots)


def test_too_few_points_for_units() -> None:
    with pytest.raises(ValueError):
        build_blueprint([BlueprintUnit(unit_id=f"U{i}", weight=1) for i in range(10)], total_points=10)


def test_select_questions_prefers_unseen_then_reseen_then_generate() -> None:
    bp = build_blueprint([BlueprintUnit(unit_id="U1", weight=1)], total_points=4, type_mix={"mcq": 1.0})
    assert [s.points for s in bp.slots] == [2, 2]
    bank = [
        BankItem(
            question_id="recent",
            unit_id="U1",
            type="mcq",
            difficulty=3,
            is_verified=True,
            last_seen_at=NOW - timedelta(days=5),
        ),
        BankItem(
            question_id="old",
            unit_id="U1",
            type="mcq",
            difficulty=3,
            is_verified=True,
            last_seen_at=NOW - timedelta(days=45),
        ),
        BankItem(question_id="fresh", unit_id="U1", type="mcq", difficulty=5, is_verified=True),
        BankItem(question_id="unverified", unit_id="U1", type="mcq", difficulty=3, is_verified=False),
    ]
    picks = select_questions(bp, bank, NOW)
    assert [(a.question_id, a.source) for a in picks] == [("fresh", "unseen"), ("old", "reseen")]
    assert select_questions(bp, [], NOW)[0].source == "generate"


def test_drop_slot_keeps_total() -> None:
    bp = build_blueprint(_units(), total_points=100)
    smaller = drop_slot(bp, 0)
    assert len(smaller.slots) == len(bp.slots) - 1
    assert sum(s.points for s in smaller.slots) == 100
    assert set(TYPE_POINTS) >= {s.type for s in smaller.slots}

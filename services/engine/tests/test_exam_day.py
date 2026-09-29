from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.algorithms.exam_day import (
    BankQuestion,
    ExamCard,
    ExamUnit,
    cram_queue,
    select_cram_units,
    warmup_selection,
)


def test_fixture_cram_queue_order(fixture: Any) -> None:
    fx = fixture("cram_queue_order.json")
    items = cram_queue(
        datetime.fromisoformat(fx["exam_start"]),
        [ExamUnit.model_validate(u) for u in fx["units"]],
        [ExamCard.model_validate(c) for c in fx["cards"]],
        [BankQuestion.model_validate(q) for q in fx["questions"]],
    )
    assert [i.unit_id for i in items] == [e["unit_id"] for e in fx["expected"]]
    for item, exp in zip(items, fx["expected"], strict=True):
        assert item.priority == pytest.approx(exp["priority"])
        assert list(item.card_ids) == exp["card_ids"]
        assert list(item.question_ids) == exp["question_ids"]
        assert item.cheat_sheet_unit_id == item.unit_id


def test_fixture_warmup_selection(fixture: Any) -> None:
    fx = fixture("warmup_selection.json")
    cards = [ExamCard.model_validate(c) for c in fx["cards"]]
    for case in fx["cases"]:
        assert warmup_selection(datetime.fromisoformat(fx["now"]), cards, count=case["count"]) == case["expected"]


def test_cram_units_empty_and_all_mastered() -> None:
    assert select_cram_units([]) == []
    assert select_cram_units([ExamUnit(unit_id="a", weight=1, mastery=0.95)]) == []


NOW = datetime(2026, 10, 1, tzinfo=UTC)
unit_ids = st.sampled_from(["U1", "U2", "U3", "U4"])
card_strategy = st.builds(
    ExamCard,
    card_id=st.text("abcdef0123456789", min_size=4, max_size=8),
    unit_id=unit_ids,
    kind=st.sampled_from(["definition", "formula", "text"]),
    stability=st.floats(0.5, 200),
    last_review=st.floats(0, 120).map(lambda d: NOW - timedelta(days=d)),
)


@given(st.lists(card_strategy, max_size=40, unique_by=lambda c: c.card_id), st.integers(1, 30))
def test_warmup_properties(cards: list[ExamCard], count: int) -> None:
    out = warmup_selection(NOW, cards, count=count)
    by_id = {c.card_id: c for c in cards}
    assert len(out) == len(set(out)) <= count
    assert all(by_id[cid].kind in {"definition", "formula"} for cid in out)
    eligible = [c for c in cards if c.kind in {"definition", "formula"}]
    assert len(out) == min(count, len(eligible))  # fills up to count when enough eligible cards exist


@given(st.lists(st.tuples(unit_ids, st.floats(1, 100), st.one_of(st.none(), st.floats(0, 1))), min_size=1, max_size=4))
def test_cram_units_cover_high_weight_and_skip_mastered(rows: list[tuple[str, float, float | None]]) -> None:
    units = list({u: ExamUnit(unit_id=u, weight=w, mastery=m) for u, w, m in rows}.values())
    selected = select_cram_units(units)
    assert all((u.mastery or 0.0) < 0.8 for u, _ in selected)
    priorities = [p for _, p in selected]
    assert priorities == sorted(priorities, reverse=True)

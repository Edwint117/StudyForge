from collections import Counter
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.algorithms.interleave import (
    SessionItem,
    adjacency_violations,
    embedding_confusables,
    interleave,
    mixed_type_slots,
    place_confusables,
    round_robin,
)


def _items(raw: list[dict[str, Any]]) -> list[SessionItem]:
    return [SessionItem.model_validate(r) for r in raw]


def test_fixture_interleave_basic(fixture: Any) -> None:
    fx = fixture("interleave_basic.json")
    session = interleave(_items(fx["cards"]))
    assert [i.item_id for i in session.items] == fx["expected"]
    assert adjacency_violations(session.items) == fx["expected_violations"]
    assert session.displaced_card_ids == ()


def test_fixture_interleave_single_unit(fixture: Any) -> None:
    fx = fixture("interleave_single_unit.json")
    session = interleave(_items(fx["cards"]))
    assert [i.item_id for i in session.items] == fx["expected"]
    assert adjacency_violations(session.items) == fx["expected_violations"]


def test_fixture_interleave_confusables(fixture: Any) -> None:
    fx = fixture("interleave_confusables.json")
    pairs = [(a, b) for a, b in fx["confusable_pairs"]]
    session = interleave(_items(fx["cards"]), confusable_pairs=pairs)
    assert [i.item_id for i in session.items] == fx["expected"]
    assert [list(p) for p in session.unsatisfied_pairs] == fx["expected_unsatisfied"]


def test_mixed_type_questions_replace_lowest_priority_cards() -> None:
    # 10 cards -> round(1.5) = 2 question slots (3 available); a5, b5 (lowest priority) are displaced.
    cards = [SessionItem(item_id=f"{u}{n}", unit_id=u.upper()) for n in range(1, 6) for u in ("a", "b")]
    questions = [
        SessionItem(item_id="q1", unit_id="A", kind="question"),
        SessionItem(item_id="q2", unit_id="B", kind="question"),
        SessionItem(item_id="q3", unit_id="A", kind="question"),
    ]
    session = interleave(cards, questions)
    assert session.displaced_card_ids == ("a5", "b5")
    assert [i.item_id for i in session.items] == ["a1", "b1", "a2", "b2", "a3", "b3", "a4", "b4", "q1", "q2"]


def test_mixed_type_slot_rounding() -> None:
    assert mixed_type_slots(0, 5) == 0
    assert mixed_type_slots(20, 0) == 0
    assert mixed_type_slots(10, 5) == 2  # 1.5 rounds half up
    assert mixed_type_slots(9, 5) == 1  # 1.35
    assert mixed_type_slots(100, 4) == 4  # capped by availability


def test_duplicate_ids_rejected() -> None:
    a = SessionItem(item_id="x", unit_id="A")
    with pytest.raises(ValueError):
        interleave([a, a])


def test_confusable_move_never_breaks_a_satisfied_pair() -> None:
    # A1(x) B1(y) A2 B2 A3 B3 C1(z): pair (x,y) is satisfied; (y,z) is 5 apart. Moving C1 must keep (x,y).
    items = [
        SessionItem(item_id="A1", unit_id="A", concept_ids=("x",)),
        SessionItem(item_id="B1", unit_id="B", concept_ids=("y",)),
        SessionItem(item_id="A2", unit_id="A"),
        SessionItem(item_id="B2", unit_id="B"),
        SessionItem(item_id="A3", unit_id="A"),
        SessionItem(item_id="B3", unit_id="B"),
        SessionItem(item_id="C1", unit_id="C", concept_ids=("z",)),
    ]
    out, unsatisfied = place_confusables(items, [("x", "y"), ("y", "z")])
    assert unsatisfied == []
    pos = {it.item_id: i for i, it in enumerate(out)}
    assert abs(pos["A1"] - pos["B1"]) <= 3
    assert abs(pos["B1"] - pos["C1"]) <= 3


def test_embedding_confusables() -> None:
    emb = {"k1": [1.0, 0.0], "k2": [0.99, 0.1], "k3": [0.0, 1.0], "k4": [1.0, 0.01]}
    units = {"k1": "U1", "k2": "U2", "k3": "U2", "k4": "U1"}
    # k1~k2 (cos 0.995, different units) and k2~k4 qualify; k1~k4 share a unit; k3 is orthogonal.
    assert embedding_confusables(emb, units) == [("k1", "k2"), ("k2", "k4")]


item_strategy = st.lists(
    st.tuples(st.sampled_from(["U1", "U2", "U3", "U4"]), st.sampled_from(["", "a", "b", "c", "d"])),
    max_size=40,
)


def _build(raw: list[tuple[str, str]]) -> list[SessionItem]:
    return [SessionItem(item_id=f"i{n}", unit_id=u, concept_ids=(k,) if k else ()) for n, (u, k) in enumerate(raw)]


@given(raw=item_strategy)
def test_round_robin_is_optimal_and_stable(raw: list[tuple[str, str]]) -> None:
    items = _build(raw)
    out = round_robin(items)
    assert sorted(i.item_id for i in out) == sorted(i.item_id for i in items)
    assert adjacency_violations(out) == 0
    # Fewest possible same-unit adjacencies: max(0, largest group - rest - 1).
    counts = Counter(i.unit_id for i in items)
    biggest = max(counts.values(), default=0)
    lower_bound = max(0, biggest - (len(items) - biggest) - 1)
    same = sum(1 for a, b in pairwise(out) if a.unit_id == b.unit_id)
    assert same == lower_bound
    # Within each unit, candidate (priority) order is preserved.
    for unit in counts:
        assert [i.item_id for i in out if i.unit_id == unit] == [i.item_id for i in items if i.unit_id == unit]


@given(
    raw=item_strategy,
    pairs=st.lists(st.tuples(st.sampled_from("abcdz"), st.sampled_from("abcdz")), max_size=4),
)
def test_confusables_satisfied_or_reported(raw: list[tuple[str, str]], pairs: list[tuple[str, str]]) -> None:
    items = round_robin(_build(raw))
    out, unsatisfied = place_confusables(items, pairs)
    assert sorted(i.item_id for i in out) == sorted(i.item_id for i in items)
    concepts = {k for i in items for k in i.concept_ids}
    for a, b in pairs:
        if a == b or a not in concepts or b not in concepts:
            continue
        pa = [n for n, i in enumerate(out) if a in i.concept_ids]
        pb = [n for n, i in enumerate(out) if b in i.concept_ids]
        within = min(abs(x - y) for x in pa for y in pb) <= 3
        assert within or tuple(sorted((a, b))) in unsatisfied

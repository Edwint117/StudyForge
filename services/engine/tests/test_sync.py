from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.srs.sync import (
    MAX_BATCH,
    CardSnapshot,
    IncomingReview,
    StoredReview,
    merge_logs,
    reconcile_batch,
)


def toy_step(s: CardSnapshot, rating: int, at: datetime) -> CardSnapshot:
    """Order-sensitive stand-in for FSRS (see the fixture's _doc)."""
    stability = (2 * (s.stability or 0) + rating) % 1000  # wraps so long histories stay within datetime range
    return CardSnapshot(
        state="review", stability=stability, due=at + timedelta(days=stability), last_review=at, reps=s.reps + 1
    )


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_fixture_offline_sync(fixture: Any) -> None:
    fx = fixture("offline_sync.json")
    existing = [StoredReview.model_validate(r) for r in fx["existing"]]
    states = {k: CardSnapshot.model_validate(v) for k, v in fx["card_states"].items()}
    batch = [IncomingReview.model_validate(r) for r in fx["batch"]]
    res = reconcile_batch(batch, existing, states, fx["card_status"], _dt(fx["now"]), toy_step)
    exp = fx["expected"]
    assert list(res.accepted) == exp["accepted"]
    assert list(res.duplicates) == exp["duplicates"]
    assert [[r.client_review_id, r.reason] for r in res.rejected] == exp["rejected"]
    assert list(res.replayed_cards) == exp["replayed_cards"]
    rewritten = {r.client_review_id: r for r in res.rewritten_logs}
    assert set(rewritten) == set(exp["rewritten"])
    for rid, e in exp["rewritten"].items():
        r = rewritten[rid]
        assert (r.state_before.stability, r.state_before.reps) == (e["before_stability"], e["before_reps"])
        assert (r.state_after.stability, r.state_after.reps) == (e["after_stability"], e["after_reps"])
        assert r.state_after.due == _dt(e["after_due"])
    logs = {r.client_review_id: r for r in res.new_logs}
    for rid, e in exp["new_logs"].items():
        assert logs[rid].state_before.stability == e["before_stability"]
        assert logs[rid].state_after.stability == e["after_stability"]
        assert logs[rid].state_after.due == _dt(e["after_due"])
    for cid, e in exp["card_states"].items():
        s = res.card_states[cid]
        assert (s.stability, s.reps, s.due, s.last_review) == (
            e["stability"],
            e["reps"],
            _dt(e["due"]),
            _dt(e["last_review"]),
        )

    # Re-sending the same batch after it was stored is a no-op.
    again = reconcile_batch(
        batch, merge_logs(existing, res), res.card_states, fx["card_status"], _dt(fx["now"]), toy_step
    )
    assert again.accepted == () and again.new_logs == () and again.card_states == {}
    assert set(again.duplicates) == {"b1", "b2", "b3", "a1"}


def test_validation() -> None:
    now = datetime(2026, 10, 5, tzinfo=UTC)
    with pytest.raises(ValueError):
        reconcile_batch([], [], {}, {}, datetime(2026, 10, 5), toy_step)
    too_many = [
        IncomingReview(client_review_id=str(i), card_id="c", rating=3, response_ms=0, reviewed_at=now)
        for i in range(MAX_BATCH + 1)
    ]
    with pytest.raises(ValueError):
        reconcile_batch(too_many, [], {}, {"c": "active"}, now, toy_step)
    naive = IncomingReview(
        client_review_id="x", card_id="c", rating=3, response_ms=0, reviewed_at=datetime(2026, 10, 4)
    )
    with pytest.raises(ValueError):
        reconcile_batch([naive], [], {}, {"c": "active"}, now, toy_step)


NOW = datetime(2026, 10, 10, tzinfo=UTC)


@st.composite
def review_sets(draw: st.DrawFn) -> list[IncomingReview]:
    n = draw(st.integers(min_value=1, max_value=25))
    minutes = draw(st.lists(st.integers(min_value=0, max_value=5000), min_size=n, max_size=n))
    return [
        IncomingReview(
            client_review_id=f"r{i:03d}",
            card_id=draw(st.sampled_from(["c1", "c2", "c3"])),
            rating=draw(st.integers(min_value=1, max_value=4)),
            response_ms=1000,
            reviewed_at=NOW - timedelta(minutes=m),
            mode=draw(st.sampled_from(["normal", "normal", "crunch", "warmup"])),
        )
        for i, m in enumerate(minutes)
    ]


def _sync_in_batches(
    reviews: list[IncomingReview], cuts: list[int]
) -> tuple[list[StoredReview], dict[str, CardSnapshot]]:
    status = {"c1": "active", "c2": "active", "c3": "active"}
    logs: list[StoredReview] = []
    states: dict[str, CardSnapshot] = {}
    bounds = [0, *sorted(set(c % (len(reviews) + 1) for c in cuts)), len(reviews)]
    for lo, hi in pairwise(bounds):
        res = reconcile_batch(reviews[lo:hi], logs, states, status, NOW, toy_step)  # type: ignore[arg-type]
        logs = merge_logs(logs, res)
        states = {**states, **res.card_states}
    return logs, states


@settings(max_examples=80, deadline=None)
@given(reviews=review_sets(), data=st.data())
def test_any_arrival_order_and_batching_gives_the_in_order_history(
    reviews: list[IncomingReview], data: st.DataObject
) -> None:
    in_order = sorted(reviews, key=lambda r: (r.reviewed_at, r.client_review_id))
    ref_logs, ref_states = _sync_in_batches(in_order, [])
    arrival = data.draw(st.permutations(reviews))
    cuts = data.draw(st.lists(st.integers(min_value=0, max_value=30), max_size=4))
    dupes = data.draw(st.lists(st.sampled_from(reviews), max_size=5))
    logs, states = _sync_in_batches([*arrival, *dupes], cuts)
    assert logs == ref_logs
    assert states == ref_states
    # Warm-up reviews never change state.
    for log in logs:
        if log.mode == "warmup":
            assert log.state_before == log.state_after

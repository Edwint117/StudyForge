import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.billing.events import (
    BillingState,
    apply_all,
    apply_event,
    downgrade_impact,
    dunning_reminders,
    effective_plan,
    reconcile,
)
from engine.billing.ledger import (
    Checkout,
    Ledger,
    LedgerError,
    ProviderEvent,
    cancel,
    change_plan,
    confirm_checkout,
    resume,
    simulate_payment_failure,
    simulate_recovery,
    start_trial,
    tick,
)
from tests.conftest import FIXTURES


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _run_step(
    ledger: Ledger, checkouts: dict[str, Checkout], step: dict[str, Any]
) -> tuple[Ledger, list[ProviderEvent]]:
    at = _dt(step["at"])
    op = step["op"]
    if op == "confirm_checkout":
        co = checkouts.setdefault(
            step["checkout_id"], Checkout(id=step["checkout_id"], user_id=ledger.user_id, price_id=step["price_id"])
        )
        ledger, co, events = confirm_checkout(ledger, co, step["subscription_id"], at)
        checkouts[co.id] = co
        return ledger, events
    if op == "change_plan":
        return change_plan(ledger, step["price_id"], at)
    if op == "cancel":
        return cancel(ledger, at, at_period_end=step["at_period_end"])
    if op == "resume":
        return resume(ledger, at)
    if op == "tick":
        return tick(ledger, at)
    if op == "fail":
        return simulate_payment_failure(ledger, at, step["kind"])
    if op == "recover":
        return simulate_recovery(ledger, at)
    if op == "start_trial":
        return start_trial(ledger, step["price_id"], step["subscription_id"], at, step["days"])
    raise AssertionError(op)


def _run(scenario: dict[str, Any]) -> tuple[Ledger, BillingState, list[ProviderEvent], list[BillingState]]:
    ledger, state, checkouts = Ledger(user_id=scenario["user_id"]), BillingState(), {}
    all_events: list[ProviderEvent] = []
    states: list[BillingState] = []
    for i, step in enumerate(scenario["steps"]):
        ledger, events = _run_step(ledger, checkouts, step)
        assert [e.type for e in events] == step["events"], (scenario["name"], i)
        state, results = apply_all(state, events)
        assert all(r.outcome == "applied" for r in results)
        effects = [eff for r in results for eff in r.effects]
        assert [e.kind for e in effects] == step["effects"], (scenario["name"], i)
        sub = state.subscription
        assert sub == ledger.subscription  # the app mirrors the provider after in-order delivery
        exp = step["expect"]
        assert sub is not None
        for key, value in exp.items():
            if key == "period":
                assert [sub.current_period_start, sub.current_period_end] == [_dt(v) for v in value], (
                    scenario["name"],
                    i,
                )
            elif key == "plan":
                assert effective_plan(state, _dt(step["at"])) == value, (scenario["name"], i)
            elif key == "invoice_lines":
                assert [line.amount_cents for line in ledger.invoices[-1].lines] == value, (scenario["name"], i)
            elif key == "cancel_detail":
                assert effects[-1].detail == value
            elif key == "grace_ends_at":
                assert sub.grace_ends_at == (_dt(value) if value else None)
            else:
                assert getattr(sub, key) == value, (scenario["name"], i, key)
        all_events += events
        states.append(state)
    return ledger, state, all_events, states


def test_fixture_lifecycle(fixture: Any) -> None:
    fx = fixture("billing_lifecycle.json")
    for scenario in fx["scenarios"]:
        _, _, _, states = _run(scenario)
        for check in scenario.get("plan_at", []):
            assert effective_plan(states[check["after_step"]], _dt(check["at"])) == check["plan"]
        fail_state = next((s for s in states if s.subscription and s.subscription.status == "past_due"), None)
        for d in scenario.get("dunning", []):
            assert fail_state is not None and fail_state.subscription is not None
            assert dunning_reminders(fail_state.subscription, d["sent"], _dt(d["at"])) == d["due"]


SCENARIO_A: dict[str, Any] = json.loads((FIXTURES / "billing_lifecycle.json").read_text(encoding="utf-8"))["scenarios"][
    0
]


@settings(max_examples=60, deadline=None)
@given(data=st.data())
def test_any_delivery_order_with_duplicates_converges(data: st.DataObject) -> None:
    ledger, in_order, events, _ = _run(SCENARIO_A)
    extra = data.draw(st.lists(st.sampled_from(events), max_size=10))
    shuffled = data.draw(st.permutations(events + extra))
    state, results = apply_all(BillingState(), shuffled)
    assert state.subscription == in_order.subscription == ledger.subscription
    assert state.invoices == in_order.invoices
    assert sum(r.outcome == "duplicate" for r in results) == len(extra)
    emails = Counter(e.email_template for r in results for e in r.effects if e.email_template)
    assert emails["billing_welcome"] <= 1
    assert emails["billing_canceled"] <= 1
    assert emails["billing_receipt"] == sum(1 for s in in_order.invoices.values() if s == "paid")
    assert reconcile([state.subscription], [ledger.subscription]) == []  # type: ignore[list-item]


T0 = datetime(2026, 4, 1, tzinfo=UTC)


def _subscribed(price_id: str = "pro_month") -> Ledger:
    ledger, _, _ = confirm_checkout(Ledger(user_id="u"), Checkout(id="co", user_id="u", price_id=price_id), "sub", T0)
    return ledger


def test_invalid_commands() -> None:
    ledger = _subscribed()
    with pytest.raises(LedgerError):
        confirm_checkout(ledger, Checkout(id="co2", user_id="u", price_id="pro_year"), "sub2", T0)
    with pytest.raises(LedgerError):
        confirm_checkout(Ledger(user_id="u"), Checkout(id="co3", user_id="other", price_id="pro_year"), "s", T0)
    with pytest.raises(LedgerError):
        change_plan(ledger, "pro_month", T0)
    with pytest.raises(LedgerError):
        resume(ledger, T0)
    with pytest.raises(LedgerError):
        simulate_recovery(ledger, T0)
    with pytest.raises(LedgerError):
        change_plan(Ledger(user_id="u"), "pro_year", T0)
    failed, _ = simulate_payment_failure(ledger, T0 + timedelta(days=1))
    with pytest.raises(LedgerError):
        change_plan(failed, "pro_plus_month", T0 + timedelta(days=2))
    with pytest.raises(LedgerError):
        cancel(failed, T0 + timedelta(days=2), at_period_end=True)
    with pytest.raises(LedgerError):
        start_trial(ledger, "pro_month", "t", T0, 7)
    canceled, _ = cancel(ledger, T0 + timedelta(days=3), at_period_end=True)
    with pytest.raises(LedgerError):
        resume(canceled, T0 + timedelta(days=40))


def test_upgrade_clears_pending_downgrade_and_cancellation() -> None:
    ledger, _ = change_plan(_subscribed("pro_plus_month"), "pro_month", T0 + timedelta(days=1))
    assert ledger.subscription is not None and ledger.subscription.scheduled_price_id == "pro_month"
    ledger, events = change_plan(ledger, "pro_plus_month", T0 + timedelta(days=2))  # back to current price
    assert [e.type for e in events] == ["subscription.updated"]
    assert ledger.subscription is not None and ledger.subscription.scheduled_price_id is None
    ledger, _ = cancel(ledger, T0 + timedelta(days=3))
    ledger, _ = change_plan(ledger, "pro_plus_year", T0 + timedelta(days=4))
    sub = ledger.subscription
    assert sub is not None and not sub.cancel_at_period_end and sub.price_id == "pro_plus_year"
    assert sub.anchor == T0 + timedelta(days=4)  # interval change resets the anchor


def test_immediate_cancel_and_effects() -> None:
    ledger = _subscribed()

    ledger2, events = cancel(ledger, T0 + timedelta(days=2), at_period_end=False)
    assert [e.type for e in events] == ["subscription.deleted"]
    assert ledger2.subscription is not None and ledger2.subscription.canceled_at == T0 + timedelta(days=2)
    assert effective_plan(BillingState(), T0) == "free"


def test_tick_catches_up_missed_periods_in_order() -> None:
    ledger, events = tick(_subscribed(), datetime(2026, 7, 1, tzinfo=UTC))
    renewals = [e for e in events if e.type == "subscription.updated"]
    assert [e.subscription.current_period_start.month for e in renewals if e.subscription] == [5, 6, 7]
    assert len({i.id for i in ledger.invoices}) == len(ledger.invoices) == 4
    _, again = tick(ledger, datetime(2026, 7, 1, tzinfo=UTC))
    assert again == []


def test_late_event_of_an_old_subscription_is_ignored() -> None:
    ledger = _subscribed()
    ledger, deleted = cancel(ledger, T0 + timedelta(days=1), at_period_end=False)
    ledger, _, created = confirm_checkout(
        ledger, Checkout(id="co9", user_id="u", price_id="pro_year"), "sub9", T0 + timedelta(days=2)
    )
    state, _ = apply_all(BillingState(), created)  # the new subscription arrives first
    result = apply_event(state, deleted[0])  # the old deletion arrives late
    assert result.outcome == "stale"
    assert result.state.subscription is not None and result.state.subscription.id == "sub9"
    assert effective_plan(result.state, T0 + timedelta(days=3)) == "pro"


def test_payment_failed_after_paid_is_stale() -> None:
    ledger = _subscribed()
    failed, events = simulate_payment_failure(ledger, T0 + timedelta(days=1))
    _, recovered = simulate_recovery(failed, T0 + timedelta(days=2))
    invoice_paid = recovered[0]
    payment_failed = next(e for e in events if e.type == "invoice.payment_failed")
    state, _ = apply_all(BillingState(), [invoice_paid])
    assert apply_event(state, payment_failed).outcome == "stale"


def test_reconcile_reports_drift() -> None:
    ledger = _subscribed()
    sub = ledger.subscription
    assert sub is not None
    behind = sub.model_copy(update={"status": "past_due", "version": 0 + 1})
    other = sub.model_copy(update={"id": "ghost"})
    drift = reconcile([behind, other], [sub])
    assert {(d.subscription_id, d.field) for d in drift} == {("sub", "status"), ("ghost", "*")}
    assert reconcile([], [sub])[0].app_value == "missing"


def test_downgrade_impact_marks_excess_read_only() -> None:
    assert downgrade_impact({"courses_active": 5, "storage_mb": 800}, "free") == {
        "courses_active": 3,
        "storage_mb": 300,
    }
    assert downgrade_impact({"courses_active": 5, "storage_mb": 800}, "pro") == {}
    assert downgrade_impact({}, "free") == {}


def test_events_without_payload_are_rejected() -> None:
    with pytest.raises(ValueError):
        apply_event(BillingState(), ProviderEvent(event_id="e1", type="subscription.updated", created=T0))
    with pytest.raises(ValueError):
        apply_event(BillingState(), ProviderEvent(event_id="e2", type="invoice.paid", created=T0))
    with pytest.raises(ValueError):
        apply_event(BillingState(), ProviderEvent(event_id="e3", type="checkout.completed", created=T0))
    ok = apply_event(BillingState(), ProviderEvent(event_id="e4", type="customer.updated", created=T0))
    assert ok.outcome == "applied" and ok.effects == ()

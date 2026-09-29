"""Mock billing provider: the subscription state machine (doc 07 §5–6).

The provider owns subscription state (as Stripe would) and emits ``ProviderEvent``s carrying **full versioned
snapshots**. The app never mutates subscriptions itself: ``events.apply_event`` (``handleBillingEvent``) applies
them. Every command is pure: ``(ledger, …) → (new ledger, events)``. Event and invoice ids are deterministic, so
replays and double clicks are no-ops.

State machine (doc 07 §6):
``none → active`` (checkout) · ``trialing → active`` (trial end) · ``active → past_due → active`` (recovery) or
``→ canceled`` (7-day grace expired → Free) · ``active[cancel_at_period_end] → canceled`` at period end ·
``active → active[new plan]`` (upgrade, immediate) · ``active[scheduled_change] → active[new plan]`` at period end.

Interpretations: an upgrade clears a pending cancellation or scheduled downgrade (the student chose to pay for
more). Soft and hard failures behave the same in the mock (7-day grace; no automatic retries); ``failure_kind``
only selects the email wording. Renewals pause while ``past_due`` and catch up after recovery.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.billing.pricing import (
    InvoiceLine,
    amount_due,
    change_kind,
    period_bounds,
    period_index,
    period_invoice_lines,
    preview_change,
    price,
)

VERSION = "billing-ledger-1"
GRACE_PERIOD = timedelta(days=7)

Status = Literal["trialing", "active", "past_due", "canceled"]
EventType = Literal[
    "checkout.completed",
    "subscription.created",
    "subscription.updated",
    "subscription.deleted",
    "invoice.created",
    "invoice.paid",
    "invoice.payment_failed",
    "customer.updated",
]
FailureKind = Literal["soft", "hard"]
InvoiceStatus = Literal["open", "failed", "paid"]
InvoiceReason = Literal["subscription_create", "subscription_cycle", "subscription_update"]
LIVE_STATUSES = frozenset({"trialing", "active", "past_due"})


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SubscriptionSnapshot(_Frozen):
    id: str
    user_id: str
    status: Status
    created_at: datetime  # orders different subscriptions of one customer (newest wins)
    price_id: str
    anchor: datetime
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool = False
    scheduled_price_id: str | None = None
    trial_end: datetime | None = None
    grace_ends_at: datetime | None = None
    failure_kind: FailureKind | None = None
    canceled_at: datetime | None = None
    version: int = Field(ge=1)


class InvoiceSnapshot(_Frozen):
    id: str
    subscription_id: str
    user_id: str
    reason: InvoiceReason
    period_start: datetime
    period_end: datetime
    lines: tuple[InvoiceLine, ...]
    subtotal_cents: int
    total_cents: int
    amount_due_cents: int
    status: InvoiceStatus
    failure_kind: FailureKind | None = None


class ProviderEvent(_Frozen):
    event_id: str
    type: EventType
    created: datetime
    subscription: SubscriptionSnapshot | None = None
    invoice: InvoiceSnapshot | None = None
    checkout_id: str | None = None


class Checkout(_Frozen):
    id: str
    user_id: str
    price_id: str
    status: Literal["open", "completed"] = "open"


class Ledger(_Frozen):
    """The mock provider's record for one customer (``billing.mock_ledger``)."""

    user_id: str
    subscription: SubscriptionSnapshot | None = None
    invoices: tuple[InvoiceSnapshot, ...] = ()
    event_seq: int = 0


class LedgerError(ValueError):
    """The command isn't valid in the current state (the API maps it to 409)."""


class _Tx:
    """Accumulates the changes and events of one command."""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        self.events: list[ProviderEvent] = []

    def emit(self, type_: EventType, at: datetime, **payload: object) -> None:
        seq = self.ledger.event_seq + 1
        self.ledger = self.ledger.model_copy(update={"event_seq": seq})
        self.events.append(
            ProviderEvent.model_validate(
                {"event_id": f"evt_{self.ledger.user_id}_{seq:06d}", "type": type_, "created": at, **payload}
            )
        )

    def set_sub(self, sub: SubscriptionSnapshot, type_: EventType, at: datetime) -> None:
        self.ledger = self.ledger.model_copy(update={"subscription": sub})
        self.emit(type_, at, subscription=sub)

    def put_invoice(self, inv: InvoiceSnapshot) -> None:
        others = tuple(i for i in self.ledger.invoices if i.id != inv.id)
        self.ledger = self.ledger.model_copy(update={"invoices": (*others, inv)})

    def invoice(
        self,
        sub: SubscriptionSnapshot,
        invoice_id: str,
        reason: InvoiceReason,
        lines: tuple[InvoiceLine, ...],
        subtotal: int,
        total: int,
        at: datetime,
        paid: bool = True,
    ) -> InvoiceSnapshot:
        inv = InvoiceSnapshot(
            id=invoice_id,
            subscription_id=sub.id,
            user_id=sub.user_id,
            reason=reason,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
            lines=lines,
            subtotal_cents=subtotal,
            total_cents=total,
            amount_due_cents=amount_due(total),
            status="open",
        )
        self.put_invoice(inv)
        self.emit("invoice.created", at, invoice=inv)
        if paid:
            inv = inv.model_copy(update={"status": "paid"})
            self.put_invoice(inv)
            self.emit("invoice.paid", at, invoice=inv)
        return inv

    def done(self) -> tuple[Ledger, list[ProviderEvent]]:
        return self.ledger, self.events


def _bump(sub: SubscriptionSnapshot, **changes: object) -> SubscriptionSnapshot:
    return sub.model_copy(update={**changes, "version": sub.version + 1})


def _live(ledger: Ledger) -> SubscriptionSnapshot:
    sub = ledger.subscription
    if sub is None or sub.status not in LIVE_STATUSES:
        raise LedgerError("no live subscription")
    return sub


def _cycle_invoice_id(sub: SubscriptionSnapshot) -> str:
    return f"in_{sub.id}_{int(sub.current_period_start.timestamp())}"


# ---------------------------------------------------------------- checkout / trial
def confirm_checkout(
    ledger: Ledger, checkout: Checkout, subscription_id: str, now: datetime
) -> tuple[Ledger, Checkout, list[ProviderEvent]]:
    """``POST /billing/checkout/{id}/confirm``. A second confirm of the same checkout returns no events."""
    if checkout.status == "completed":
        return ledger, checkout, []
    if checkout.user_id != ledger.user_id:
        raise LedgerError("checkout belongs to another customer")
    if ledger.subscription is not None and ledger.subscription.status in LIVE_STATUSES:
        raise LedgerError("already subscribed: change the plan instead")
    p = price(checkout.price_id)
    start, end = period_bounds(now, p.interval, 0)
    sub = SubscriptionSnapshot(
        id=subscription_id,
        user_id=ledger.user_id,
        status="active",
        price_id=p.id,
        anchor=now,
        created_at=now,
        current_period_start=start,
        current_period_end=end,
        version=1,
    )
    tx = _Tx(ledger)
    tx.emit("checkout.completed", now, checkout_id=checkout.id)
    tx.set_sub(sub, "subscription.created", now)
    lines, subtotal, total = period_invoice_lines(p)
    tx.invoice(sub, _cycle_invoice_id(sub), "subscription_create", lines, subtotal, total, now)
    new_ledger, events = tx.done()
    return new_ledger, checkout.model_copy(update={"status": "completed"}), events


def start_trial(
    ledger: Ledger, price_id: str, subscription_id: str, now: datetime, trial_days: int
) -> tuple[Ledger, list[ProviderEvent]]:
    """Trials are supported and tested but not exposed during beta (doc 07 §5.8)."""
    if ledger.subscription is not None and ledger.subscription.status in LIVE_STATUSES:
        raise LedgerError("already subscribed")
    if trial_days < 1:
        raise LedgerError("trial_days must be >= 1")
    trial_end = now + timedelta(days=trial_days)
    sub = SubscriptionSnapshot(
        id=subscription_id,
        user_id=ledger.user_id,
        status="trialing",
        price_id=price(price_id).id,
        anchor=now,
        created_at=now,
        current_period_start=now,
        current_period_end=trial_end,
        trial_end=trial_end,
        version=1,
    )
    tx = _Tx(ledger)
    tx.set_sub(sub, "subscription.created", now)
    return tx.done()


# ---------------------------------------------------------------- plan changes
def change_plan(ledger: Ledger, new_price_id: str, now: datetime) -> tuple[Ledger, list[ProviderEvent]]:
    """Upgrade now (prorated, $0 invoice) or schedule a downgrade for the period end. Choosing the current price
    while a downgrade is scheduled cancels the scheduled downgrade."""
    sub = _live(ledger)
    if sub.status != "active":
        raise LedgerError(f"can't change plan while {sub.status}")
    tx = _Tx(ledger)
    if new_price_id == sub.price_id:
        if sub.scheduled_price_id is None:
            raise LedgerError("already on this price")
        tx.set_sub(_bump(sub, scheduled_price_id=None), "subscription.updated", now)
        return tx.done()
    new = price(new_price_id)
    if change_kind(price(sub.price_id), new) == "downgrade":
        tx.set_sub(_bump(sub, scheduled_price_id=new.id, cancel_at_period_end=False), "subscription.updated", now)
        return tx.done()
    preview = preview_change(sub.price_id, new.id, sub.current_period_start, sub.current_period_end, now)
    upgraded = _bump(
        sub,
        price_id=new.id,
        anchor=now if preview.anchor_reset else sub.anchor,
        current_period_start=preview.new_period_start,
        current_period_end=preview.new_period_end,
        scheduled_price_id=None,
        cancel_at_period_end=False,
    )
    tx.set_sub(upgraded, "subscription.updated", now)
    tx.invoice(
        upgraded,
        f"in_{sub.id}_v{upgraded.version}",
        "subscription_update",
        preview.lines,
        preview.subtotal_cents,
        preview.total_cents,
        now,
    )
    return tx.done()


def cancel(ledger: Ledger, now: datetime, at_period_end: bool = True) -> tuple[Ledger, list[ProviderEvent]]:
    sub = _live(ledger)
    tx = _Tx(ledger)
    if at_period_end:
        if sub.status != "active":
            raise LedgerError(f"can't schedule a cancellation while {sub.status}")
        if sub.cancel_at_period_end:
            return ledger, []
        tx.set_sub(_bump(sub, cancel_at_period_end=True, scheduled_price_id=None), "subscription.updated", now)
    else:
        tx.set_sub(_bump(sub, status="canceled", canceled_at=now), "subscription.deleted", now)
    return tx.done()


def resume(ledger: Ledger, now: datetime) -> tuple[Ledger, list[ProviderEvent]]:
    """Undo a period-end cancellation (only before the period ends)."""
    sub = _live(ledger)
    if not sub.cancel_at_period_end:
        raise LedgerError("nothing to resume")
    if now >= sub.current_period_end:
        raise LedgerError("the period has already ended")
    tx = _Tx(ledger)
    tx.set_sub(_bump(sub, cancel_at_period_end=False), "subscription.updated", now)
    return tx.done()


# ---------------------------------------------------------------- time passes (hourly pg_cron)
def tick(ledger: Ledger, now: datetime) -> tuple[Ledger, list[ProviderEvent]]:
    """Renewals, period-end changes/cancellations, trial conversion and grace expiry up to ``now``.

    Idempotent: a second tick at the same instant emits nothing. Missed periods are caught up in order.
    """
    tx = _Tx(ledger)
    while True:
        sub = tx.ledger.subscription
        if sub is None or sub.status == "canceled":
            break
        if sub.status == "past_due":
            if sub.grace_ends_at is not None and sub.grace_ends_at <= now:
                tx.set_sub(
                    _bump(sub, status="canceled", canceled_at=sub.grace_ends_at),
                    "subscription.deleted",
                    sub.grace_ends_at,
                )
            break
        if sub.current_period_end > now:
            break
        boundary = sub.current_period_end
        if sub.status == "trialing":
            p = price(sub.price_id)
            start, end = period_bounds(boundary, p.interval, 0)
            renewed = _bump(sub, status="active", anchor=boundary, current_period_start=start, current_period_end=end)
            reason: InvoiceReason = "subscription_create"
        elif sub.cancel_at_period_end:
            tx.set_sub(_bump(sub, status="canceled", canceled_at=boundary), "subscription.deleted", boundary)
            break
        elif sub.scheduled_price_id is not None:
            new, old = price(sub.scheduled_price_id), price(sub.price_id)
            anchor = boundary if new.interval != old.interval else sub.anchor
            idx = period_index(anchor, new.interval, boundary)
            start, end = period_bounds(anchor, new.interval, idx)
            renewed = _bump(
                sub,
                price_id=new.id,
                scheduled_price_id=None,
                anchor=anchor,
                current_period_start=start,
                current_period_end=end,
            )
            reason = "subscription_cycle"
        else:
            p = price(sub.price_id)
            start, end = period_bounds(sub.anchor, p.interval, period_index(sub.anchor, p.interval, boundary))
            renewed = _bump(sub, current_period_start=start, current_period_end=end)
            reason = "subscription_cycle"
        tx.set_sub(renewed, "subscription.updated", boundary)
        lines, subtotal, total = period_invoice_lines(price(renewed.price_id))
        tx.invoice(renewed, _cycle_invoice_id(renewed), reason, lines, subtotal, total, boundary)
    return tx.done()


# ---------------------------------------------------------------- dunning simulation (admin, ADM-02)
def simulate_payment_failure(
    ledger: Ledger, now: datetime, kind: FailureKind = "soft"
) -> tuple[Ledger, list[ProviderEvent]]:
    """A renewal payment fails: ``past_due`` with the full plan for a 7-day grace period."""
    sub = _live(ledger)
    if sub.status != "active":
        raise LedgerError(f"can't fail a payment while {sub.status}")
    tx = _Tx(ledger)
    lines, subtotal, total = period_invoice_lines(price(sub.price_id))
    inv = tx.invoice(
        sub, f"in_{sub.id}_fail_v{sub.version}", "subscription_cycle", lines, subtotal, total, now, paid=False
    )
    failed = inv.model_copy(update={"status": "failed", "failure_kind": kind})
    tx.put_invoice(failed)
    tx.emit("invoice.payment_failed", now, invoice=failed)
    tx.set_sub(
        _bump(sub, status="past_due", grace_ends_at=now + GRACE_PERIOD, failure_kind=kind),
        "subscription.updated",
        now,
    )
    return tx.done()


def simulate_recovery(ledger: Ledger, now: datetime) -> tuple[Ledger, list[ProviderEvent]]:
    """The failed invoice is paid within the grace period: back to ``active``."""
    sub = _live(ledger)
    if sub.status != "past_due":
        raise LedgerError("subscription isn't past due")
    failed = [i for i in ledger.invoices if i.subscription_id == sub.id and i.status == "failed"]
    if not failed:
        raise LedgerError("no failed invoice to recover")
    tx = _Tx(ledger)
    paid = failed[-1].model_copy(update={"status": "paid"})
    tx.put_invoice(paid)
    tx.emit("invoice.paid", now, invoice=paid)
    tx.set_sub(_bump(sub, status="active", grace_ends_at=None, failure_kind=None), "subscription.updated", now)
    return tx.done()

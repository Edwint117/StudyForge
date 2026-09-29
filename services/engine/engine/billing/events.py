"""``handleBillingEvent`` reference (doc 07 §4–6): apply provider events to the app's billing state.

- **Idempotent:** an ``event_id`` already processed is a no-op (``UNIQUE(provider, event_id)``).
- **Order-tolerant:** subscription events carry full snapshots with a ``version``; a snapshot not newer than the
  stored one is stale and ignored, so any delivery order converges on the newest state. Invoice status only moves
  forward (open → failed → paid; paid is terminal).
- **Effects:** every subscription transition yields an audit action (``billing.*``), a user email and an
  entitlement sync; invoices yield number assignment + receipt. The caller performs them after committing.

Also here: ``effective_plan`` (what entitlements resolve to), the dunning reminder schedule (days 0/3/6),
``downgrade_impact`` (over-limit items become read-only, never deleted) and ``reconcile`` (daily drift check
against the provider's ledger).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

from engine.billing.ledger import InvoiceStatus, ProviderEvent, SubscriptionSnapshot
from engine.billing.pricing import Plan, price

VERSION = "billing-events-1"

DUNNING_REMINDER_DAYS = (0, 3, 6)
INVOICE_RANK: dict[InvoiceStatus, int] = {"open": 0, "failed": 1, "paid": 2}

EffectKind = Literal[
    "trial_started",
    "subscription_activated",
    "plan_upgraded",
    "plan_changed_at_renewal",
    "downgrade_scheduled",
    "downgrade_canceled",
    "cancel_scheduled",
    "resumed",
    "renewed",
    "payment_failed",
    "payment_recovered",
    "subscription_canceled",
    "invoice_recorded",
    "invoice_paid",
]
# kind → email template (None = audit only). Every subscription transition emails the user (doc 07 §6).
EMAIL_TEMPLATES: dict[EffectKind, str | None] = {
    "trial_started": "billing_trial_started",
    "subscription_activated": "billing_welcome",
    "plan_upgraded": "billing_plan_changed",
    "plan_changed_at_renewal": "billing_plan_changed",
    "downgrade_scheduled": "billing_downgrade_scheduled",
    "downgrade_canceled": "billing_downgrade_canceled",
    "cancel_scheduled": "billing_cancel_scheduled",
    "resumed": "billing_resumed",
    "renewed": None,  # the receipt (invoice_paid) covers it
    "payment_failed": "billing_payment_failed",
    "payment_recovered": "billing_payment_recovered",
    "subscription_canceled": "billing_canceled",
    "invoice_recorded": None,
    "invoice_paid": "billing_receipt",
}
SYNC_KINDS = frozenset(
    {
        "trial_started",
        "subscription_activated",
        "plan_upgraded",
        "plan_changed_at_renewal",
        "payment_failed",
        "payment_recovered",
        "subscription_canceled",
    }
)

# Non-renewable capacity limits: exceeding them after a downgrade makes the excess read-only (never deleted).
# Monthly/daily quotas simply apply from the next reset. None = unlimited.
CAPACITY_LIMITS: dict[str, dict[Plan, int | None]] = {
    "courses_active": {"free": 2, "pro": None, "pro_plus": None},
    "storage_mb": {"free": 500, "pro": 10_240, "pro_plus": 51_200},
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Effect(_Frozen):
    kind: EffectKind
    audit_action: str
    email_template: str | None
    sync_entitlements: bool
    at: datetime
    subscription_id: str | None = None
    invoice_id: str | None = None
    detail: str = ""


class BillingState(_Frozen):
    subscription: SubscriptionSnapshot | None = None
    invoices: dict[str, InvoiceStatus] = {}
    completed_checkouts: frozenset[str] = frozenset()
    processed_event_ids: frozenset[str] = frozenset()


Outcome = Literal["applied", "duplicate", "stale"]


class EventResult(_Frozen):
    state: BillingState
    outcome: Outcome
    effects: tuple[Effect, ...]


def _effect(kind: EffectKind, at: datetime, **kw: str | None) -> Effect:
    return Effect(
        kind=kind,
        audit_action=f"billing.{kind}",
        email_template=EMAIL_TEMPLATES[kind],
        sync_entitlements=kind in SYNC_KINDS,
        at=at,
        **kw,
    )


def _subscription_effects(old: SubscriptionSnapshot | None, new: SubscriptionSnapshot, at: datetime) -> list[Effect]:
    sid = new.id
    if new.status == "canceled":
        if old is not None and old.id == sid and old.status == "canceled":
            return []
        reason = "grace_expired" if old is not None and old.status == "past_due" else "canceled"
        return [_effect("subscription_canceled", at, subscription_id=sid, detail=reason)]
    if old is None or old.id != sid:
        kind: EffectKind = "trial_started" if new.status == "trialing" else "subscription_activated"
        return [_effect(kind, at, subscription_id=sid)]

    out: list[Effect] = []
    if old.status == "trialing" and new.status == "active":
        out.append(_effect("subscription_activated", at, subscription_id=sid))
    if old.status != "past_due" and new.status == "past_due":
        out.append(_effect("payment_failed", at, subscription_id=sid, detail=new.failure_kind or "soft"))
    if old.status == "past_due" and new.status == "active":
        out.append(_effect("payment_recovered", at, subscription_id=sid))
    if new.price_id != old.price_id:
        at_renewal = old.scheduled_price_id == new.price_id and new.current_period_start >= old.current_period_end
        kind = "plan_changed_at_renewal" if at_renewal else "plan_upgraded"
        out.append(_effect(kind, at, subscription_id=sid, detail=f"{old.price_id}->{new.price_id}"))
    elif new.current_period_start > old.current_period_start and old.status != "trialing":
        out.append(_effect("renewed", at, subscription_id=sid))
    if old.scheduled_price_id is None and new.scheduled_price_id is not None:
        out.append(_effect("downgrade_scheduled", at, subscription_id=sid, detail=new.scheduled_price_id))
    if old.scheduled_price_id is not None and new.scheduled_price_id is None and new.price_id == old.price_id:
        out.append(_effect("downgrade_canceled", at, subscription_id=sid))
    if not old.cancel_at_period_end and new.cancel_at_period_end:
        out.append(_effect("cancel_scheduled", at, subscription_id=sid))
    if old.cancel_at_period_end and not new.cancel_at_period_end and new.price_id == old.price_id:
        out.append(_effect("resumed", at, subscription_id=sid))
    return out


def apply_event(state: BillingState, event: ProviderEvent) -> EventResult:
    """Apply one provider event (``handleBillingEvent``)."""
    if event.event_id in state.processed_event_ids:
        return EventResult(state=state, outcome="duplicate", effects=())
    seen = state.processed_event_ids | {event.event_id}
    stale = EventResult(state=state.model_copy(update={"processed_event_ids": seen}), outcome="stale", effects=())

    if event.type.startswith("subscription."):
        new = event.subscription
        if new is None:
            raise ValueError(f"{event.type} without a subscription snapshot")
        old = state.subscription
        if old is not None and old.id == new.id and new.version <= old.version:
            return stale
        if old is not None and old.id != new.id and new.created_at <= old.created_at:
            return stale  # a late event of an older subscription (e.g. its deletion) must not replace the current one
        sub_effects = _subscription_effects(old, new, event.created)
        next_state = state.model_copy(update={"subscription": new, "processed_event_ids": seen})
        return EventResult(state=next_state, outcome="applied", effects=tuple(sub_effects))

    if event.type.startswith("invoice."):
        inv = event.invoice
        if inv is None:
            raise ValueError(f"{event.type} without an invoice snapshot")
        target: InvoiceStatus = {"invoice.created": "open", "invoice.paid": "paid"}.get(event.type, "failed")  # type: ignore[assignment]
        current = state.invoices.get(inv.id)
        is_new = current is None
        if current is not None and INVOICE_RANK[target] <= INVOICE_RANK[current]:
            return stale
        invoices = {**state.invoices, inv.id: target}
        effects: list[Effect] = []
        if is_new:
            effects.append(_effect("invoice_recorded", event.created, invoice_id=inv.id))
        if target == "paid":
            effects.append(_effect("invoice_paid", event.created, invoice_id=inv.id))
        next_state = state.model_copy(update={"invoices": invoices, "processed_event_ids": seen})
        return EventResult(state=next_state, outcome="applied", effects=tuple(effects))

    if event.type == "checkout.completed":
        if event.checkout_id is None:
            raise ValueError("checkout.completed without checkout_id")
        next_state = state.model_copy(
            update={"completed_checkouts": state.completed_checkouts | {event.checkout_id}, "processed_event_ids": seen}
        )
        return EventResult(state=next_state, outcome="applied", effects=())

    # customer.updated: nothing subscription-related to change.
    return EventResult(state=state.model_copy(update={"processed_event_ids": seen}), outcome="applied", effects=())


def apply_all(state: BillingState, events: Iterable[ProviderEvent]) -> tuple[BillingState, list[EventResult]]:
    results: list[EventResult] = []
    for event in events:
        result = apply_event(state, event)
        state = result.state
        results.append(result)
    return state, results


# ---------------------------------------------------------------- entitlement resolution and dunning
def effective_plan(state: BillingState, now: datetime) -> Plan:
    """The plan entitlements resolve to (before admin overrides). Past-due keeps the plan during the grace period."""
    sub = state.subscription
    if sub is None or sub.status == "canceled":
        return "free"
    if sub.status == "past_due" and (sub.grace_ends_at is None or now >= sub.grace_ends_at):
        return "free"
    return price(sub.price_id).plan


def dunning_reminders(sub: SubscriptionSnapshot, sent_days: Iterable[int], now: datetime) -> list[int]:
    """Reminder days (0, 3, 6 after the failure) that are due and unsent while the subscription is still past due.
    The failure instant is ``grace_ends_at − 7 days``. The banner shows for the whole ``past_due`` period."""
    if sub.status != "past_due" or sub.grace_ends_at is None:
        return []
    failed_at = sub.grace_ends_at - timedelta(days=7)
    sent = set(sent_days)
    return [d for d in DUNNING_REMINDER_DAYS if d not in sent and failed_at + timedelta(days=d) <= now]


def downgrade_impact(usage: Mapping[str, float], plan: Plan) -> dict[str, float]:
    """Excess per capacity limit on ``plan`` (items beyond the limit become read-only; nothing is deleted)."""
    out: dict[str, float] = {}
    for meter, limits in CAPACITY_LIMITS.items():
        limit = limits[plan]
        used = usage.get(meter, 0)
        if limit is not None and used > limit:
            out[meter] = used - limit
    return out


# ---------------------------------------------------------------- daily reconciliation (doc 07 §5.7)
class Drift(_Frozen):
    subscription_id: str
    field: str
    app_value: str
    provider_value: str


RECONCILED_FIELDS = (
    "status",
    "price_id",
    "current_period_start",
    "current_period_end",
    "cancel_at_period_end",
    "scheduled_price_id",
    "version",
)


def reconcile(app: Sequence[SubscriptionSnapshot], provider: Sequence[SubscriptionSnapshot]) -> list[Drift]:
    """Compare the app's ``subscriptions`` with the provider ledger; any difference is alerted on."""
    a = {s.id: s for s in app}
    p = {s.id: s for s in provider}
    drift: list[Drift] = []
    for sid in sorted(a.keys() | p.keys()):
        if sid not in a:
            drift.append(Drift(subscription_id=sid, field="*", app_value="missing", provider_value="present"))
            continue
        if sid not in p:
            drift.append(Drift(subscription_id=sid, field="*", app_value="present", provider_value="missing"))
            continue
        for name in RECONCILED_FIELDS:
            av, pv = getattr(a[sid], name), getattr(p[sid], name)
            if av != pv:
                drift.append(Drift(subscription_id=sid, field=name, app_value=str(av), provider_value=str(pv)))
    return drift

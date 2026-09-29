"""Prices, billing periods, proration previews and invoice numbering (doc 07 §2, §5.3–5.4, §6).

- Periods are anchored to the subscription's anchor instant (UTC). Month-end anchors keep their day where it
  exists: an anchor on Jan 31 gives periods starting Feb 28 (29 in leap years), Mar 31, Apr 30, … Every boundary
  is computed from the original anchor, never chained from the previous boundary.
- Proration is by the second over the current period, on **list prices**, rounded half-up to the cent per line;
  the "StudyForge Beta — 100% off" line then discounts any positive subtotal to $0.00. Tax is always 0.
- Upgrades apply immediately. A change within the same interval keeps the period; a change to a different
  interval (monthly ↔ yearly) starts a new period and resets the anchor to the change instant. Downgrades
  (lower plan, or the same plan yearly → monthly) apply at the period end with no proration.
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict

VERSION = "billing-pricing-1"

Plan = Literal["free", "pro", "pro_plus"]
Interval = Literal["month", "year"]
LineKind = Literal["plan", "proration_credit", "proration_charge", "discount", "tax"]
ChangeKind = Literal["upgrade", "downgrade"]

PLAN_RANK: dict[Plan, int] = {"free": 0, "pro": 1, "pro_plus": 2}
PLAN_NAMES: dict[Plan, str] = {"free": "Free", "pro": "Pro", "pro_plus": "Pro+ (Exam Season)"}
BETA_DISCOUNT_LABEL = "StudyForge Beta — 100% off"
INVOICE_PREFIX = "SF"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Price(_Frozen):
    id: str
    plan: Plan
    interval: Interval
    amount_cents: int  # list price


PRICES: dict[str, Price] = {
    p.id: p
    for p in (
        Price(id="pro_month", plan="pro", interval="month", amount_cents=1200),
        Price(id="pro_year", plan="pro", interval="year", amount_cents=9600),
        Price(id="pro_plus_month", plan="pro_plus", interval="month", amount_cents=2400),
        Price(id="pro_plus_year", plan="pro_plus", interval="year", amount_cents=19200),
    )
}


class InvoiceLine(_Frozen):
    kind: LineKind
    description: str
    amount_cents: int


class ProrationPreview(_Frozen):
    kind: ChangeKind
    effective_at: datetime
    lines: tuple[InvoiceLine, ...]
    subtotal_cents: int
    total_cents: int  # 0 during beta, or negative when the change leaves a credit (see account_credit)
    amount_due_cents: int  # always 0 during beta
    account_credit_cents: int
    new_period_start: datetime
    new_period_end: datetime
    anchor_reset: bool


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a UTC datetime")
    return value


def price(price_id: str) -> Price:
    try:
        return PRICES[price_id]
    except KeyError:
        raise ValueError(f"unknown price {price_id!r}") from None


def add_months(anchor: datetime, months: int) -> datetime:
    """``anchor`` + ``months`` calendar months, clamping the day to the target month's length."""
    _utc(anchor, "anchor")
    total = anchor.year * 12 + (anchor.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def _months(interval: Interval) -> int:
    return 1 if interval == "month" else 12


def period_bounds(anchor: datetime, interval: Interval, index: int) -> tuple[datetime, datetime]:
    """[start, end) of period ``index`` (0 = the period starting at the anchor)."""
    n = _months(interval)
    return add_months(anchor, index * n), add_months(anchor, (index + 1) * n)


def period_index(anchor: datetime, interval: Interval, at: datetime) -> int:
    """Index of the period containing ``at`` (``at`` >= anchor)."""
    _utc(at, "at")
    if at < anchor:
        raise ValueError("at is before the anchor")
    n = _months(interval)
    guess = ((at.year - anchor.year) * 12 + (at.month - anchor.month)) // n
    idx = max(0, guess - 1)
    while period_bounds(anchor, interval, idx)[1] <= at:
        idx += 1
    return idx


def change_kind(old: Price, new: Price) -> ChangeKind:
    if old.id == new.id:
        raise ValueError("new price equals the current price")
    if PLAN_RANK[new.plan] != PLAN_RANK[old.plan]:
        return "upgrade" if PLAN_RANK[new.plan] > PLAN_RANK[old.plan] else "downgrade"
    return "upgrade" if new.interval == "year" else "downgrade"


def _round_half_up(value: Fraction) -> int:
    sign = -1 if value < 0 else 1
    return sign * int(abs(value) + Fraction(1, 2))


def with_beta_discount(lines: list[InvoiceLine]) -> tuple[tuple[InvoiceLine, ...], int, int]:
    """Append the beta discount (cancels a positive subtotal) and the $0 tax line → (lines, subtotal, total).

    A negative subtotal (e.g. Pro yearly → Pro+ monthly: the unused yearly credit exceeds the new month) is not
    discounted; ``total`` is then negative and ``amount_due()`` / ``account_credit()`` split it Stripe-style into
    $0 due plus a credit to the customer balance.
    """
    subtotal = sum(line.amount_cents for line in lines)
    out = list(lines)
    discount = -subtotal if subtotal > 0 else 0
    out.append(InvoiceLine(kind="discount", description=BETA_DISCOUNT_LABEL, amount_cents=discount))
    out.append(InvoiceLine(kind="tax", description="Tax", amount_cents=0))
    return tuple(out), subtotal, subtotal + discount


def amount_due(total_cents: int) -> int:
    return max(0, total_cents)


def account_credit(total_cents: int) -> int:
    """Credit carried to the customer balance (list-price value; worth $0 while every charge is discounted)."""
    return max(0, -total_cents)


def period_invoice_lines(p: Price) -> tuple[tuple[InvoiceLine, ...], int, int]:
    """Lines of a regular (checkout or renewal) invoice."""
    base = InvoiceLine(kind="plan", description=f"{PLAN_NAMES[p.plan]} ({p.interval}ly)", amount_cents=p.amount_cents)
    return with_beta_discount([base])


def preview_change(
    old_price_id: str,
    new_price_id: str,
    period_start: datetime,
    period_end: datetime,
    at: datetime,
) -> ProrationPreview:
    """The proration preview shown before a plan change (``POST /billing/subscription/change?preview=true``)."""
    old, new = price(old_price_id), price(new_price_id)
    _utc(period_start, "period_start")
    _utc(period_end, "period_end")
    _utc(at, "at")
    if not period_start <= at < period_end:
        raise ValueError("at must fall inside the current period")
    kind = change_kind(old, new)

    if kind == "downgrade":
        start = period_end
        end = add_months(period_end, _months(new.interval))
        lines, subtotal, total = period_invoice_lines(new)
        return ProrationPreview(
            kind=kind,
            effective_at=period_end,
            lines=lines,
            subtotal_cents=subtotal,
            total_cents=total,
            amount_due_cents=amount_due(total),
            account_credit_cents=account_credit(total),
            new_period_start=start,
            new_period_end=end,
            anchor_reset=new.interval != old.interval,
        )

    remaining = Fraction(int((period_end - at).total_seconds()), int((period_end - period_start).total_seconds()))
    credit = InvoiceLine(
        kind="proration_credit",
        description=f"Unused time on {PLAN_NAMES[old.plan]} ({old.interval}ly)",
        amount_cents=-_round_half_up(old.amount_cents * remaining),
    )
    if new.interval == old.interval:
        charge = InvoiceLine(
            kind="proration_charge",
            description=f"Remaining time on {PLAN_NAMES[new.plan]} ({new.interval}ly)",
            amount_cents=_round_half_up(new.amount_cents * remaining),
        )
        start, end, reset = period_start, period_end, False
    else:
        charge = InvoiceLine(
            kind="plan", description=f"{PLAN_NAMES[new.plan]} ({new.interval}ly)", amount_cents=new.amount_cents
        )
        start, end, reset = at, add_months(at, _months(new.interval)), True
    lines, subtotal, total = with_beta_discount([credit, charge])
    return ProrationPreview(
        kind=kind,
        effective_at=at,
        lines=lines,
        subtotal_cents=subtotal,
        total_cents=total,
        amount_due_cents=amount_due(total),
        account_credit_cents=account_credit(total),
        new_period_start=start,
        new_period_end=end,
        anchor_reset=reset,
    )


_INVOICE_RE = re.compile(rf"^{INVOICE_PREFIX}-(\d{{4}})-(\d{{6}})$")


def format_invoice_number(year: int, seq: int) -> str:
    if not 1 <= seq <= 999_999:
        raise ValueError("invoice sequence out of range")
    return f"{INVOICE_PREFIX}-{year:04d}-{seq:06d}"


def next_invoice_number(previous: str | None, year: int) -> str:
    """Gapless per-year numbering: SF-2026-000001, SF-2026-000002, …; restarts at 000001 each calendar year.
    The database assigns it inside the insert transaction (a counter row per year), so there are no gaps."""
    if previous is None:
        return format_invoice_number(year, 1)
    match = _INVOICE_RE.match(previous)
    if not match:
        raise ValueError(f"malformed invoice number {previous!r}")
    prev_year, prev_seq = int(match.group(1)), int(match.group(2))
    if year < prev_year:
        raise ValueError("invoice year went backwards")
    return format_invoice_number(year, prev_seq + 1 if year == prev_year else 1)

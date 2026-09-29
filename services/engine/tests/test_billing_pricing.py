from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.billing.pricing import (
    PRICES,
    add_months,
    change_kind,
    next_invoice_number,
    period_bounds,
    period_index,
    period_invoice_lines,
    preview_change,
    price,
)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_fixture_month_end_anchors(fixture: Any) -> None:
    fx = fixture("billing_month_end_anchors.json")
    for series in fx["series"]:
        anchor = _dt(series["anchor"])
        starts = [period_bounds(anchor, series["interval"], k)[0] for k in range(len(series["starts"]))]
        assert starts == [_dt(s) for s in series["starts"]]
    for case in fx["index_cases"]:
        assert period_index(_dt(case["anchor"]), case["interval"], _dt(case["at"])) == case["index"]


def test_fixture_proration(fixture: Any) -> None:
    fx = fixture("billing_proration.json")
    for case in fx["cases"]:
        p = preview_change(
            case["old"], case["new"], _dt(case["period_start"]), _dt(case["period_end"]), _dt(case["at"])
        )
        assert p.kind == case["kind"], case["name"]
        assert p.effective_at == _dt(case["effective_at"])
        assert [line.amount_cents for line in p.lines] == case["line_amounts"], case["name"]
        assert [line.kind for line in p.lines] == case["line_kinds"]
        assert p.subtotal_cents == case["subtotal"] and p.total_cents == case["total"]
        assert (p.new_period_start, p.new_period_end) == tuple(_dt(s) for s in case["new_period"])
        assert p.anchor_reset == case["anchor_reset"]
        assert p.amount_due_cents == case.get("amount_due", 0)
        assert p.account_credit_cents == case.get("account_credit", 0)
    for case in fx["invoice_numbers"]:
        assert next_invoice_number(case["previous"], case["year"]) == case["next"]


def test_change_kind_rules() -> None:
    assert change_kind(price("pro_month"), price("pro_plus_year")) == "upgrade"
    assert change_kind(price("pro_plus_month"), price("pro_year")) == "downgrade"  # lower plan wins over interval
    assert change_kind(price("pro_month"), price("pro_year")) == "upgrade"
    assert change_kind(price("pro_year"), price("pro_month")) == "downgrade"
    with pytest.raises(ValueError):
        change_kind(price("pro_month"), price("pro_month"))


def test_validation() -> None:
    naive = datetime(2026, 1, 1)
    with pytest.raises(ValueError):
        add_months(naive, 1)
    start, end = datetime(2026, 4, 1, tzinfo=UTC), datetime(2026, 5, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        preview_change("pro_month", "pro_plus_month", start, end, end)  # at must be inside the period
    with pytest.raises(ValueError):
        price("enterprise")
    with pytest.raises(ValueError):
        next_invoice_number("INV-1", 2026)
    with pytest.raises(ValueError):
        next_invoice_number("SF-2027-000001", 2026)
    with pytest.raises(ValueError):
        period_index(start, "month", start - timedelta(seconds=1))


def test_regular_invoice_is_zero() -> None:
    for p in PRICES.values():
        lines, subtotal, total = period_invoice_lines(p)
        assert subtotal == p.amount_cents and total == 0
        assert [line.kind for line in lines] == ["plan", "discount", "tax"]


anchors = st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2040, 12, 31), timezones=st.just(UTC)).map(
    lambda d: d.replace(microsecond=0)
)


@given(anchor=anchors, interval=st.sampled_from(["month", "year"]), k=st.integers(min_value=0, max_value=40))
def test_periods_tile_time_and_keep_the_anchor_day(anchor: datetime, interval: str, k: int) -> None:
    start, end = period_bounds(anchor, interval, k)  # type: ignore[arg-type]
    assert start < end
    assert period_bounds(anchor, interval, k + 1)[0] == end  # contiguous, no gaps or overlaps
    assert period_index(anchor, interval, start) == k  # type: ignore[arg-type]
    assert period_index(anchor, interval, end - timedelta(seconds=1)) == k  # type: ignore[arg-type]
    assert start.day == anchor.day or start.day < anchor.day  # clamped only in shorter months
    assert (start.hour, start.minute, start.second) == (anchor.hour, anchor.minute, anchor.second)


@given(
    old=st.sampled_from(sorted(PRICES)),
    new=st.sampled_from(sorted(PRICES)),
    anchor=anchors,
    frac=st.floats(min_value=0, max_value=0.999),
)
def test_every_preview_is_free_and_upgrades_never_credit_more_than_paid(
    old: str, new: str, anchor: datetime, frac: float
) -> None:
    if old == new:
        return
    start, end = period_bounds(anchor, price(old).interval, 0)
    at = start + timedelta(seconds=int((end - start).total_seconds() * frac))
    p = preview_change(old, new, start, end, at)
    assert p.amount_due_cents == 0
    assert p.total_cents == -p.account_credit_cents
    assert sum(line.amount_cents for line in p.lines) == p.total_cents
    if p.kind == "upgrade":
        credit = next(line for line in p.lines if line.kind == "proration_credit")
        assert -price(old).amount_cents <= credit.amount_cents <= 0
        if price(old).interval == price(new).interval:
            assert p.subtotal_cents >= 0
    else:
        assert p.effective_at == end

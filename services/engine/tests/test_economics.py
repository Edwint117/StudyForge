import pytest

from engine.adapters.budget import DAILY_CAP_MICROS
from engine.adapters.economics import (
    CARD_CALL,
    DAYS,
    QUOTAS,
    TUTOR,
    USAGE_FRACTION,
    per_action_micros,
    plan_cost,
    quota_cap_conflicts,
)


def test_per_action_costs_from_catalog_prices() -> None:
    unit = per_action_micros()
    # tutor: 6000 input (80% cached at 10%) at $2/MTok + 400 output at $10/MTok
    expected_tutor = 6000 * 0.2 * 2 + 6000 * 0.8 * 2 * 0.1 + 400 * 10
    assert unit["tutor_messages"] == pytest.approx(expected_tutor)
    assert TUTOR.model == "llm.claude_sonnet" and CARD_CALL.model == "llm.claude_haiku"
    # cards: one Haiku batch call (50% off) per 10 cards
    assert unit["cards"] == pytest.approx((2500 * 1 + 700 * 5) * 0.5 / 10)


def test_ai_spend_never_exceeds_daily_cap_times_days() -> None:
    for plan in ("free", "pro", "pro_plus"):
        for pct in ("p50", "p90"):
            c = plan_cost(plan, pct)  # type: ignore[arg-type]
            mock = per_action_micros(plan)["mock_exams"] * QUOTAS[plan]["mock_exams"] * USAGE_FRACTION[pct]  # type: ignore[index]
            assert c.ai_micros <= DAILY_CAP_MICROS[plan] * DAYS + mock + 1  # type: ignore[index]  # mocks are cap-exempt
            assert c.total_micros == c.ai_micros + c.compute_micros + c.infra_micros
    assert plan_cost("free").gross_margin is None


def test_default_quotas_fit_the_caps_and_conflicts_are_detected() -> None:
    assert quota_cap_conflicts() == []  # doc 07 quotas were aligned with the daily caps
    inflated = {plan: dict(q) for plan, q in QUOTAS.items()}
    inflated["free"]["tutor_messages"] = 20 * DAYS
    assert quota_cap_conflicts(inflated) == ["free: tutor_messages quota is 20/day but the daily cap allows ~14/day"]


def test_free_tutor_uses_haiku_and_targets_hold() -> None:
    assert per_action_micros("free")["tutor_messages"] == pytest.approx(3680)  # 1200*1 + 4800*1*0.1 + 400*5
    assert plan_cost("free").total_micros < 400_000  # doc 01: < $0.40 per typical free user
    assert plan_cost("pro").gross_margin is not None and plan_cost("pro").gross_margin > 0.7

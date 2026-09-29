"""Unit economics per plan (doc 07 §8; doc 01 cost NFR). Produces the numbers for ``docs/costs.md``.

All per-action token counts and compute costs below are **assumptions** (editable constants) until M4–M8
measure real values from Langfuse and Cloud Run billing; replace them then. Prices come from the adapter catalog.
The daily AI cost cap per plan is applied (mock exams are exempt, limited by their monthly quota), and
:func:`quota_cap_conflicts` reports quotas that the cap would silently cut short.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from engine.adapters.budget import DAILY_CAP_MICROS
from engine.adapters.catalog import CATALOG, Plan

VERSION = "economics-1"

DAYS = 30
CACHE_READ_FACTOR = 0.10  # cached input tokens cost ~10% of normal input (verify current pricing)
CLOUD_RUN_MICROS_PER_VCPU_S = 18.0  # ≈ $0.0648 per vCPU-hour, above the free allowance

# Monthly quotas (doc 07 §2); daily quotas are converted with DAYS.
QUOTAS: dict[Plan, dict[str, float]] = {
    "free": {
        "tutor_messages": 13 * DAYS,
        "cards": 300,
        "feynman": 10,
        "mock_exams": 1,
        "audio_seconds": 3600,
        "ocr_pages": 30,
    },
    "pro": {
        "tutor_messages": 60 * DAYS,
        "cards": 5000,
        "feynman": 200,
        "mock_exams": 8,
        "audio_seconds": 20 * 3600,
        "ocr_pages": 500,
    },
    "pro_plus": {
        "tutor_messages": 200 * DAYS,
        "cards": 20000,
        "feynman": 1000,
        "mock_exams": 30,
        "audio_seconds": 60 * 3600,
        "ocr_pages": 2000,
    },
}
LIST_PRICE_MICROS: dict[Plan, int] = {"free": 0, "pro": 12_000_000, "pro_plus": 24_000_000}
USAGE_FRACTION = {"p50": 0.15, "p90": 0.60}  # share of each quota a typical / heavy user consumes


class LlmAction(BaseModel):
    """Per-action LLM usage assumption."""

    model_config = ConfigDict(frozen=True)
    model: str
    input: int
    output: int
    cached_share: float = 0.0
    discount: float = 1.0  # e.g. 0.5 for the Batch API


TUTOR = LlmAction(model="llm.claude_sonnet", input=6000, output=400, cached_share=0.8)
TUTOR_FREE = TUTOR.model_copy(update={"model": "llm.claude_haiku"})  # Free plan tutor runs on Haiku
CARDS_PER_CALL = 10
CARD_CALL = LlmAction(model="llm.claude_haiku", input=2500, output=700, discount=0.5)
FEYNMAN = LlmAction(model="llm.claude_sonnet", input=3000, output=700)
MOCK_EXAM = LlmAction(model="llm.claude_sonnet", input=60_000, output=15_000)  # generate + 2x verify + grade
STT_VCPU_S_PER_AUDIO_S = 1.2  # faster-whisper small.en int8 on CPU
OCR_VCPU_S_PER_PAGE = 2.0
PAID_OCR_ESCALATION_SHARE = {"free": 0.0, "pro": 0.3, "pro_plus": 1.0}  # pages sent to Claude vision
INFRA_MICROS_PER_USER = 50_000  # DB/storage/egress/observability share per active user per month


class PlanCost(BaseModel):
    model_config = ConfigDict(frozen=True)
    plan: Plan
    percentile: str
    ai_micros: int
    ai_micros_uncapped: int
    compute_micros: int
    infra_micros: int
    total_micros: int
    list_price_micros: int
    gross_margin: float | None  # None for the free plan


def _llm_cost(a: LlmAction) -> float:
    rates = CATALOG[a.model].cost.micros_per_unit
    fresh = a.input * (1 - a.cached_share) * rates.get("input_token", 0)
    cached = a.input * a.cached_share * rates.get("input_token", 0) * CACHE_READ_FACTOR
    return (fresh + cached + a.output * rates.get("output_token", 0)) * a.discount


def per_action_micros(plan: Plan = "pro") -> dict[str, float]:
    return {
        "tutor_messages": _llm_cost(TUTOR_FREE if plan == "free" else TUTOR),
        "cards": _llm_cost(CARD_CALL) / CARDS_PER_CALL,
        "feynman": _llm_cost(FEYNMAN),
        "mock_exams": _llm_cost(MOCK_EXAM),
    }


def plan_cost(plan: Plan, percentile: str = "p50", quotas: Mapping[Plan, Mapping[str, float]] = QUOTAS) -> PlanCost:
    f = USAGE_FRACTION[percentile]
    q = quotas[plan]
    unit = per_action_micros(plan)
    mock = unit["mock_exams"] * q["mock_exams"] * f  # cap-exempt (limited by the monthly mock quota)
    ai = sum(unit[k] * q[k] * f for k in unit if k != "mock_exams")
    ocr_pages = q["ocr_pages"] * f
    ai += ocr_pages * PAID_OCR_ESCALATION_SHARE[plan] * CATALOG["ocr.claude_vision"].cost.micros_per_unit["page"]
    capped = min(ai, DAILY_CAP_MICROS[plan] * DAYS) + mock
    ai += mock
    compute = (
        q["audio_seconds"] * f * STT_VCPU_S_PER_AUDIO_S
        + ocr_pages * (1 - PAID_OCR_ESCALATION_SHARE[plan]) * OCR_VCPU_S_PER_PAGE
    ) * CLOUD_RUN_MICROS_PER_VCPU_S
    total = capped + compute + INFRA_MICROS_PER_USER
    price = LIST_PRICE_MICROS[plan]
    return PlanCost(
        plan=plan,
        percentile=percentile,
        ai_micros=round(capped),
        ai_micros_uncapped=round(ai),
        compute_micros=round(compute),
        infra_micros=INFRA_MICROS_PER_USER,
        total_micros=round(total),
        list_price_micros=price,
        gross_margin=round(1 - total / price, 4) if price else None,
    )


def quota_cap_conflicts(quotas: Mapping[Plan, Mapping[str, float]] = QUOTAS) -> list[str]:
    """Quotas a user could never reach because the daily AI cost cap runs out first (using one feature only).
    Mock exams are cap-exempt (limited by their monthly quota), so they're not checked."""
    out = []
    for plan, q in quotas.items():
        unit = per_action_micros(plan)
        cap = DAILY_CAP_MICROS[plan]
        for feature, monthly in q.items():
            if feature not in unit or feature == "mock_exams":
                continue
            per_day = monthly / DAYS
            reachable = cap / unit[feature]
            if per_day > reachable:
                out.append(f"{plan}: {feature} quota is {per_day:g}/day but the daily cap allows ~{reachable:.0f}/day")
    return out

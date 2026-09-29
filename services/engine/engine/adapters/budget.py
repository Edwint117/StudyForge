"""AI cost controls (doc 06 §6): per-user daily caps with reservations, and the global monthly budget state.

Amounts are integer micros (1 USD = 1_000_000). The atomic counter update happens in Postgres
(``usage_counters``); these functions are the policy the SQL implements and the engine checks before calling.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from engine.adapters.catalog import Plan

VERSION = "budget-1"

DAILY_CAP_MICROS: dict[Plan, int] = {"free": 50_000, "pro": 500_000, "pro_plus": 1_500_000}
ALERT_LEVELS = (0.50, 0.80, 1.00)
DEGRADE_AT = 1.00
KILL_AT = 1.20


# Jobs whose AI calls are limited by their own monthly quota instead of the daily cap: one mock exam
# (generate + verify + grade) costs more than a Free user's whole daily cap (doc 07 §3).
CAP_EXEMPT_JOBS = frozenset({"mock.build", "attempt.grade", "attempt.regrade"})


def can_reserve(
    plan: Plan,
    spent_today: int,
    open_reservations: int,
    estimate: int,
    caps: dict[Plan, int] = DAILY_CAP_MICROS,
    job_type: str | None = None,
) -> bool:
    """Reserve the estimated cost before calling a provider; refuse if it would exceed today's cap.
    Calls made by cap-exempt jobs are always allowed here (their spend still counts toward the day)."""
    if estimate < 0 or spent_today < 0 or open_reservations < 0:
        raise ValueError("amounts must be non-negative")
    if job_type in CAP_EXEMPT_JOBS:
        return True
    return spent_today + open_reservations + estimate <= caps[plan]


def reconcile(spent_today: int, open_reservations: int, estimate: int, actual: int) -> tuple[int, int]:
    """After the call: release the reservation and record the actual cost (which may exceed the estimate)."""
    return spent_today + max(0, actual), max(0, open_reservations - estimate)


Profile = Literal["normal", "degraded", "killed"]


class GlobalBudgetState(BaseModel):
    model_config = ConfigDict(frozen=True)
    fraction_used: float
    profile: Profile
    alerts: tuple[float, ...]  # thresholds crossed (for alert dedupe: send each once per month)


def global_budget_state(spent_micros: int, budget_micros: int) -> GlobalBudgetState:
    if budget_micros <= 0:
        raise ValueError("budget must be positive")
    used = spent_micros / budget_micros
    profile: Profile = "killed" if used >= KILL_AT else "degraded" if used >= DEGRADE_AT else "normal"
    return GlobalBudgetState(
        fraction_used=round(used, 6), profile=profile, alerts=tuple(a for a in ALERT_LEVELS if used >= a)
    )

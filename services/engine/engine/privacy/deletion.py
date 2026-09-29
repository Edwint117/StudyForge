"""Account deletion planning (DATA-02; GDPR erasure).

Deletion is scheduled with a 7-day grace period (cancellable), then executed as an ordered list of idempotent
steps. Order matters: steps that need the user's tokens or ids (revoking Google access, deleting calendar events we
created, third-party erasure by id) run **before** the database rows disappear; the auth user is deleted last but
one (its ``on delete cascade`` removes every ``user_id`` table), and a PII-free audit event closes the job.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

VERSION = "deletion-1"
GRACE_PERIOD = timedelta(days=7)
BUCKETS = ("uploads", "derived", "exports", "avatars")

StepKind = Literal[
    "revoke_sessions",
    "revoke_calendar_tokens",
    "delete_calendar_events",
    "delete_storage_prefix",
    "delete_vault_secrets",
    "posthog_delete_person",
    "langfuse_delete_traces",
    "suppress_email",
    "delete_auth_user",
    "audit_completed",
]


class Step(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: StepKind
    target: str = ""
    idempotency_key: str


class Footprint(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: str
    calendar_connected: bool = False
    delete_calendar_events: bool = False  # the user chose to remove the events we created in their calendar
    buckets_with_objects: tuple[str, ...] = BUCKETS
    analytics_person: bool = True  # PostHog person exists (consented at some point)
    llm_traces: bool = True


def deletion_due(requested_at: datetime, now: datetime) -> bool:
    return now >= requested_at + GRACE_PERIOD


def can_cancel(requested_at: datetime, now: datetime, executed: bool) -> bool:
    return not executed and now < requested_at + GRACE_PERIOD


def plan_deletion(fp: Footprint) -> list[Step]:
    uid = fp.user_id

    def step(kind: StepKind, target: str = "") -> Step:
        return Step(kind=kind, target=target, idempotency_key=f"delete:{uid}:{kind}:{target}")

    steps = [step("revoke_sessions")]
    if fp.calendar_connected:
        if fp.delete_calendar_events:
            steps.append(step("delete_calendar_events"))  # needs the OAuth token, so before revoking it
        steps.append(step("revoke_calendar_tokens"))
    steps += [step("delete_storage_prefix", f"{b}/{uid}/") for b in BUCKETS if b in fp.buckets_with_objects]
    steps.append(step("delete_vault_secrets"))
    if fp.analytics_person:
        steps.append(step("posthog_delete_person"))
    if fp.llm_traces:
        steps.append(step("langfuse_delete_traces"))
    steps += [step("suppress_email"), step("delete_auth_user"), step("audit_completed")]
    return steps


def remaining_steps(plan: Iterable[Step], completed_keys: Iterable[str]) -> list[Step]:
    """Resume after a crash or retry: skip steps already recorded as done (each step is idempotent anyway)."""
    done = set(completed_keys)
    return [s for s in plan if s.idempotency_key not in done]


class Residual(BaseModel):
    model_config = ConfigDict(frozen=True)
    store: str
    count: int


def verify_erasure(residuals: Iterable[Residual]) -> list[Residual]:
    """Post-deletion check (M10 gate): every store must report zero rows/objects for the user."""
    return [r for r in residuals if r.count > 0]

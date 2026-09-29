"""Who gets which notification, on which channel, and when (NOT-01..04, EXAM-03/04).

* Preference matrix: category × channel with defaults; **security** and **transactional** email can't be turned off.
* Quiet hours (user's local time, may cross midnight): email/push for non-urgent categories are deferred to the
  end of quiet hours; in-app notifications are always delivered (silently).
* Exam-day mode: on an exam's local calendar day, non-essential categories are suppressed entirely.
* Timing helpers: exam reminders at T-24h / T-2h (elapsed time), "exam in 7/3/1 days" notices at 09:00 local, and
  the hourly digest fan-out (07:00 local, idempotent per local date). All times are computed in the user's IANA time
  zone, so they're correct across daylight-saving changes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

VERSION = "notify-policy-1"

Category = Literal[
    "security",
    "transactional",
    "job_status",
    "plan_changes",
    "session_reminder",
    "exam_reminder",
    "exam_countdown",
    "cram_ready",
    "daily_digest",
    "marketing",
]
Channel = Literal["in_app", "email", "push"]

DEFAULTS: dict[str, dict[str, bool]] = {
    "security": {"in_app": True, "email": True, "push": False},
    "transactional": {"in_app": True, "email": True, "push": False},
    "job_status": {"in_app": True, "email": False, "push": False},
    "plan_changes": {"in_app": True, "email": False, "push": False},
    "session_reminder": {"in_app": True, "email": False, "push": False},  # push is opt-in (NOT-03)
    "exam_reminder": {"in_app": True, "email": True, "push": False},
    "exam_countdown": {"in_app": True, "email": False, "push": False},
    "cram_ready": {"in_app": True, "email": False, "push": False},
    "daily_digest": {"in_app": False, "email": True, "push": False},
    "marketing": {"in_app": False, "email": False, "push": False},  # opt-in only
}
LOCKED: frozenset[tuple[str, str]] = frozenset({("security", "email"), ("transactional", "email")})
URGENT: frozenset[str] = frozenset({"security", "transactional", "exam_reminder"})  # ignore quiet hours
EXAM_DAY_ALLOWED: frozenset[str] = frozenset({"security", "transactional", "exam_reminder"})

REMINDER_OFFSETS = (timedelta(hours=24), timedelta(hours=2))
COUNTDOWN_DAYS = (7, 3, 1)
COUNTDOWN_LOCAL_TIME = time(9, 0)
DIGEST_LOCAL_HOUR = 7


class QuietHours(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    start: time  # e.g. 22:00
    end: time  # e.g. 07:00 (may be "earlier" than start → crosses midnight)


class UserPrefs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    tz: str
    overrides: dict[str, dict[str, bool]] = {}  # category → channel → enabled
    quiet_hours: QuietHours | None = None
    exam_days: tuple[date, ...] = ()  # local dates with an exam (exam-day mode)


class Delivery(BaseModel):
    model_config = ConfigDict(frozen=True)
    channel: Channel
    send_at: datetime  # UTC
    deferred: bool = False


def enabled_channels(category: Category, overrides: Mapping[str, Mapping[str, bool]]) -> list[Channel]:
    out: list[Channel] = []
    for channel in ("in_app", "email", "push"):
        on = DEFAULTS[category][channel]
        if (category, channel) not in LOCKED:
            on = overrides.get(category, {}).get(channel, on)
        if on:
            out.append(channel)
    return out


def in_quiet_hours(local: time, q: QuietHours) -> bool:
    if q.start == q.end:
        return False
    if q.start < q.end:
        return q.start <= local < q.end
    return local >= q.start or local < q.end  # crosses midnight


def _quiet_end_after(local_dt: datetime, q: QuietHours) -> datetime:
    """Next local datetime when quiet hours end, strictly after ``local_dt`` (DST-safe via fold-aware combine)."""
    candidate = datetime.combine(local_dt.date(), q.end, tzinfo=local_dt.tzinfo)
    if candidate <= local_dt:
        candidate = datetime.combine(local_dt.date() + timedelta(days=1), q.end, tzinfo=local_dt.tzinfo)
    return candidate


def route(category: Category, created_at: datetime, prefs: UserPrefs) -> list[Delivery]:
    """Deliveries for one notification; empty list = suppressed (preferences or exam-day mode)."""
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    zone = ZoneInfo(prefs.tz)
    local = created_at.astimezone(zone)
    if local.date() in prefs.exam_days and category not in EXAM_DAY_ALLOWED:
        return []
    out: list[Delivery] = []
    for channel in enabled_channels(category, prefs.overrides):
        q = prefs.quiet_hours
        if channel != "in_app" and category not in URGENT and q is not None and in_quiet_hours(local.time(), q):
            send_local = _quiet_end_after(local, q)
            out.append(Delivery(channel=channel, send_at=send_local.astimezone(ZoneInfo("UTC")), deferred=True))
        else:
            out.append(Delivery(channel=channel, send_at=created_at.astimezone(ZoneInfo("UTC"))))
    return out


# ---------------------------------------------------------------- timing
def exam_reminder_times(exam_start: datetime, now: datetime) -> list[datetime]:
    """T-24h and T-2h in elapsed time (UTC arithmetic), skipping any already in the past."""
    return [exam_start - off for off in REMINDER_OFFSETS if exam_start - off > now]


def countdown_times(exam_start: datetime, tz: str, now: datetime) -> list[tuple[int, datetime]]:
    """'Exam in N days' notices at 09:00 local on the calendar day N days before the exam's local date."""
    zone = ZoneInfo(tz)
    exam_day = exam_start.astimezone(zone).date()
    out = []
    for n in COUNTDOWN_DAYS:
        at = datetime.combine(exam_day - timedelta(days=n), COUNTDOWN_LOCAL_TIME, tzinfo=zone)
        if at > now:
            out.append((n, at.astimezone(ZoneInfo("UTC"))))
    return out


def digest_due(now: datetime, tzs: Iterable[tuple[str, str]], hour: int = DIGEST_LOCAL_HOUR) -> list[tuple[str, date]]:
    """For the hourly cron: (user_id, local_date) pairs whose local clock reads ``hour`` now. The local date is the
    idempotency key, so a repeated hour (DST fall-back) can't send twice."""
    out = []
    for user_id, tz in tzs:
        local = now.astimezone(ZoneInfo(tz))
        if local.hour == hour:
            out.append((user_id, local.date()))
    return out

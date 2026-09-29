from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.notify.policy import (
    QuietHours,
    UserPrefs,
    countdown_times,
    digest_due,
    enabled_channels,
    exam_reminder_times,
    in_quiet_hours,
    route,
)

NY = ZoneInfo("America/New_York")
QUIET = QuietHours(start=time(22, 0), end=time(7, 0))


def test_defaults_and_locked_channels() -> None:
    assert enabled_channels("exam_reminder", {}) == ["in_app", "email"]
    assert enabled_channels("marketing", {}) == []
    assert enabled_channels("marketing", {"marketing": {"email": True}}) == ["email"]
    # security email can't be switched off; in-app can
    assert enabled_channels("security", {"security": {"email": False, "in_app": False}}) == ["email"]
    assert enabled_channels("session_reminder", {"session_reminder": {"push": True}}) == ["in_app", "push"]


@pytest.mark.parametrize(
    ("t", "quiet"),
    [(time(23, 0), True), (time(2, 0), True), (time(6, 59), True), (time(7, 0), False), (time(12, 0), False)],
)
def test_quiet_hours_cross_midnight(t: time, quiet: bool) -> None:
    assert in_quiet_hours(t, QUIET) is quiet
    assert not in_quiet_hours(t, QuietHours(start=time(9), end=time(9)))


def test_quiet_hours_defer_email_and_push_but_not_in_app_or_urgent() -> None:
    prefs = UserPrefs(
        tz="America/New_York", quiet_hours=QUIET, overrides={"plan_changes": {"email": True, "push": True}}
    )
    created = datetime(2026, 10, 14, 23, 30, tzinfo=NY)  # 11:30 pm local
    by_channel = {d.channel: d for d in route("plan_changes", created, prefs)}
    assert not by_channel["in_app"].deferred
    assert by_channel["email"].deferred and by_channel["email"].send_at == datetime(2026, 10, 15, 7, 0, tzinfo=NY)
    urgent = route("security", created, prefs)
    assert all(not d.deferred for d in urgent)


def test_deferral_across_dst_fall_back() -> None:
    # DST ends Nov 1 2026 in New York: 7:00 local that morning is EST (UTC-5), not EDT
    prefs = UserPrefs(tz="America/New_York", quiet_hours=QUIET, overrides={"job_status": {"email": True}})
    created = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)  # Oct 31, 11 pm EDT
    email = next(d for d in route("job_status", created, prefs) if d.channel == "email")
    assert email.send_at == datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def test_exam_day_mode_suppresses_non_essential() -> None:
    prefs = UserPrefs(tz="America/New_York", exam_days=(date(2026, 10, 14),))
    during = datetime(2026, 10, 14, 10, 0, tzinfo=NY)
    assert route("job_status", during, prefs) == []
    assert route("daily_digest", during, prefs) == []
    assert [d.channel for d in route("exam_reminder", during, prefs)] == ["in_app", "email"]
    assert route("job_status", during + timedelta(days=1), prefs)  # the next day is normal again


def test_route_requires_aware_datetimes() -> None:
    with pytest.raises(ValueError):
        route("security", datetime(2026, 1, 1), UserPrefs(tz="UTC"))


def test_exam_reminders_and_countdowns() -> None:
    exam = datetime(2026, 11, 2, 18, 0, tzinfo=NY)  # the day after DST ends
    now = datetime(2026, 10, 20, tzinfo=UTC)
    t24, t2 = exam_reminder_times(exam, now)
    assert exam - t24 == timedelta(hours=24) and exam - t2 == timedelta(hours=2)
    assert exam_reminder_times(exam, exam - timedelta(hours=3)) == [exam - timedelta(hours=2)]
    counts = countdown_times(exam, "America/New_York", now)
    assert [(n, at.astimezone(NY).isoformat()) for n, at in counts] == [
        (7, "2026-10-26T09:00:00-04:00"),
        (3, "2026-10-30T09:00:00-04:00"),
        (1, "2026-11-01T09:00:00-05:00"),  # 09:00 local on the fall-back day
    ]


def test_digest_due_by_local_hour() -> None:
    now = datetime(2026, 10, 14, 11, 30, tzinfo=UTC)  # 07:30 in New York (EDT), 20:30 in Tokyo
    due = digest_due(now, [("u1", "America/New_York"), ("u2", "Asia/Tokyo"), ("u3", "America/Chicago")])
    assert due == [("u1", date(2026, 10, 14))]

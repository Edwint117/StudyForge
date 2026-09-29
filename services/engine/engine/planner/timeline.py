"""Free-time windows for the planner, built in the student's time zone and stored as UTC instants.

* Weekly availability rules (local wall-clock) are expanded per local date, clipped to earliest/latest preferences.
* Busy blocks (calendar), locked/frozen sessions, and rest days are removed.
* **DST safety:** on a fall-back day the repeated local hour is removed from the windows (a session there would
  have an ambiguous clock time). On a spring-forward day the missing local hour has no instants, so nothing can
  be placed there.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start) / MINUTE)

    def overlaps(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end


def subtract(intervals: Sequence[Interval], cut: Interval) -> list[Interval]:
    out: list[Interval] = []
    for iv in intervals:
        if not iv.overlaps(cut):
            out.append(iv)
            continue
        if iv.start < cut.start:
            out.append(Interval(iv.start, cut.start))
        if cut.end < iv.end:
            out.append(Interval(cut.end, iv.end))
    return out


def to_utc(d: date, t: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=zone).astimezone(UTC)


def local_date(instant: datetime, zone: ZoneInfo) -> date:
    return instant.astimezone(zone).date()


def ambiguous_ranges(start: datetime, end: datetime, zone: ZoneInfo) -> list[Interval]:
    """UTC ranges whose local clock time occurs twice (DST fall-back), within [start, end)."""
    out: list[Interval] = []
    step = timedelta(minutes=30)
    t = start
    prev = t.astimezone(zone).utcoffset()
    while t < end:
        nxt = t + step
        off = nxt.astimezone(zone).utcoffset()
        if prev is not None and off is not None and off < prev:
            # locate the transition instant T to the minute, then block [T − Δ, T + Δ)
            lo, hi = t, nxt
            while hi - lo > MINUTE:
                mid = lo + (hi - lo) / 2
                if mid.astimezone(zone).utcoffset() == prev:
                    lo = mid
                else:
                    hi = mid
            delta = prev - off
            out.append(Interval(hi - delta, hi + delta))
        prev = off
        t = nxt
    return out


@dataclass(frozen=True)
class AvailabilityRule:
    weekday: int  # 0 = Monday
    start: time
    end: time


def build_windows(
    tz: str,
    now: datetime,
    horizon_end: datetime,
    rules: Iterable[AvailabilityRule],
    busy: Iterable[Interval] = (),
    rest_dates: Iterable[date] = (),
    earliest: time | None = None,
    latest: time | None = None,
    min_block: int = 25,
) -> list[Interval]:
    zone = ZoneInfo(tz)
    rules = list(rules)
    rest = set(rest_dates)
    windows: list[Interval] = []
    d = local_date(now, zone)
    last = local_date(horizon_end, zone)
    while d <= last:
        if d not in rest:
            for r in rules:
                if r.weekday != d.weekday():
                    continue
                s = max(r.start, earliest) if earliest else r.start
                e = min(r.end, latest) if latest else r.end
                if s >= e:
                    continue
                iv = Interval(max(to_utc(d, s, zone), now), min(to_utc(d, e, zone), horizon_end))
                if iv.start < iv.end:
                    windows.append(iv)
        d += timedelta(days=1)
    windows.sort()
    for cut in [*busy, *ambiguous_ranges(now, horizon_end, zone)]:
        windows = subtract(windows, cut)
    return [w for w in windows if w.minutes >= min_block]

"""Backward scheduler ``planner-1`` and rebalancer ``rebalance-1`` (doc 05 §4; PLAN-04..07).

Greedy, deterministic placement over free windows (see ``timeline``). Order of work:
1. reservations: D−1 consolidation (60–120 min), D−2 mock exam (exam length + 15) plus a 30-min consolidation;
2. learn (and remediation) blocks: every exam keeps a cursor so a unit starts only after the previous unit in
   prerequisite order; at each step the earliest usable slot goes to the most urgent exam
   (urgency = remaining minutes / free minutes before its deadline × weight %); deadline = end of day D−3;
3. spaced reviews at +1/+3/+7 days after a unit's last learn block (merged per exam per day), then practice blocks
   for units weighted at or above the median;
4. a 45-min buffer after every 6th study day;
5. feasibility: any unplaced learn/practice minutes become a deficit with options.
Rebalancing freezes done / in-progress / locked / starting-within-60-min sessions, carries missed minutes forward,
adds remediation for weak units, and re-plans with a stability preference (the old slot if free, else the nearest).
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from engine.planner.timeline import MINUTE, AvailabilityRule, Interval, build_windows, local_date, subtract, to_utc

VERSION = "planner-1"
REBALANCE_VERSION = "rebalance-1"

SessionKind = Literal["learn", "review", "practice", "mock", "buffer", "consolidation"]
GRID = 5  # minutes
REVIEW_OFFSETS = (1, 3, 7)
FREEZE_WINDOW = timedelta(minutes=60)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExamSpec(_Frozen):
    exam_id: str
    title: str
    starts_at: datetime
    duration_min: int = Field(gt=0)
    weight_pct: float = Field(gt=0)


class UnitSpec(_Frozen):
    unit_id: str
    exam_id: str
    title: str
    weight: float = Field(gt=0)
    tokens: int = Field(ge=0)
    syllabus_order: int
    dense: bool = False  # formula/proof-heavy → difficulty factor 1.3
    mastery: float | None = Field(default=None, ge=0, le=1)


class Prefs(_Frozen):
    tz: str
    daily_max_min: int = Field(default=180, gt=0)
    min_block: int = Field(default=25, gt=0)
    max_block: int = Field(default=120, gt=0)
    rest_weekdays: tuple[int, ...] = ()
    earliest: time | None = None
    latest: time | None = None


class PlannedSession(_Frozen):
    key: str
    exam_id: str
    kind: SessionKind
    unit_ids: tuple[str, ...]
    start: datetime
    end: datetime
    rationale: str
    frozen: bool = False

    @property
    def minutes(self) -> int:
        return int((self.end - self.start) / MINUTE)


class Feasibility(_Frozen):
    status: Literal["ok", "deficit"]
    deficit_min: int = 0
    per_exam: dict[str, int] = {}
    extend_daily_max_to: int | None = None
    skim_units: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class Plan(_Frozen):
    sessions: tuple[PlannedSession, ...]
    feasibility: Feasibility
    algorithm_version: str = VERSION


# ---------------------------------------------------------------- effort + ordering
def _round_up(m: float) -> int:
    return int(math.ceil(m / GRID) * GRID)


def learn_minutes(u: UnitSpec, min_block: int) -> int:
    base = min(240.0, max(20.0, 0.9 * u.tokens / 1000 * (1.3 if u.dense else 1.0)))
    if u.mastery is not None:
        base *= 1 - u.mastery
    if base < min_block / 2:
        return 0
    return max(min_block, _round_up(base))


def practice_minutes(u: UnitSpec, learn: int, median_weight: float) -> int:
    if u.weight < median_weight:
        return 0
    return 30 if learn <= 60 else 45


def topo_order(units: Sequence[UnitSpec], prereqs: Sequence[tuple[str, str]]) -> list[UnitSpec]:
    """Kahn's algorithm with ties by syllabus order then weight desc. Cycles: drop edges that go backwards in
    syllabus order, then any remaining edge in a cycle."""
    by_id = {u.unit_id: u for u in units}
    edges = [(a, b) for a, b in prereqs if a in by_id and b in by_id and a != b]

    def attempt(es: Sequence[tuple[str, str]]) -> list[UnitSpec] | None:
        indeg = {u: 0 for u in by_id}
        out: dict[str, list[str]] = defaultdict(list)
        for a, b in es:
            out[a].append(b)
            indeg[b] += 1
        ready = sorted(
            (u for u, d in indeg.items() if d == 0), key=lambda u: (by_id[u].syllabus_order, -by_id[u].weight, u)
        )
        order: list[UnitSpec] = []
        while ready:
            u = ready.pop(0)
            order.append(by_id[u])
            for v in out[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    ready.append(v)
            ready.sort(key=lambda x: (by_id[x].syllabus_order, -by_id[x].weight, x))
        return order if len(order) == len(by_id) else None

    return (
        attempt(edges)
        or attempt([(a, b) for a, b in edges if by_id[a].syllabus_order < by_id[b].syllabus_order])
        or attempt([])
        or []
    )


# ---------------------------------------------------------------- board (free time)
@dataclass
class Board:
    zone: ZoneInfo
    windows: list[Interval]
    daily_max: int
    day_used: dict[date, int] = field(default_factory=lambda: defaultdict(int))

    def day_left(self, instant: datetime) -> int:
        return self.daily_max - self.day_used[local_date(instant, self.zone)]

    @staticmethod
    def _align(t: datetime) -> datetime:
        extra = (t.minute % GRID) * 60 + t.second
        return (
            t
            if extra == 0 and t.microsecond == 0
            else (t + timedelta(seconds=GRID * 60 - extra)).replace(microsecond=0)
        )

    def earliest(
        self, after: datetime, before: datetime, min_len: int, max_len: int, respect_daily: bool = True
    ) -> Interval | None:
        for w in self.windows:
            if w.end <= after:
                continue
            if w.start >= before:
                break
            start = self._align(max(w.start, after))
            room = int((min(w.end, before) - start) / MINUTE)
            if respect_daily:
                room = min(room, self.day_left(start))
            length = min(max_len, room)
            length -= length % GRID
            if length >= min_len:
                return Interval(start, start + length * MINUTE)
        return None

    def nearest(
        self, target: datetime, minutes: int, after: datetime, before: datetime, respect_daily: bool = True
    ) -> Interval | None:
        best: tuple[float, Interval] | None = None
        for w in self.windows:
            lo, hi = self._align(max(w.start, after)), min(w.end, before) - minutes * MINUTE
            if hi < lo:
                continue
            start = self._align(min(max(target, lo), hi)) if target > lo else lo
            if start > hi:
                continue
            if respect_daily and self.day_left(start) < minutes:
                continue
            cost = abs((start - target).total_seconds())
            if best is None or cost < best[0]:
                best = (cost, Interval(start, start + minutes * MINUTE))
        return best[1] if best else None

    def contains(self, iv: Interval) -> bool:
        return any(w.start <= iv.start and iv.end <= w.end for w in self.windows)

    def take(self, iv: Interval, count_daily: bool = True) -> None:
        self.windows = [w for w in subtract(self.windows, iv) if w.minutes > 0]
        if count_daily:
            self.day_used[local_date(iv.start, self.zone)] += iv.minutes

    def free_minutes(self, after: datetime, before: datetime) -> int:
        return sum(max(0, int((min(w.end, before) - max(w.start, after)) / MINUTE)) for w in self.windows)


# ---------------------------------------------------------------- plan generation
def _local_midnight(d: date, zone: ZoneInfo) -> datetime:
    return to_utc(d, time(0, 0), zone)


def forced_rest_dates(
    start: date, end: date, rules: Sequence[AvailabilityRule], rest_weekdays: Sequence[int], reserved: set[date]
) -> set[date]:
    """Break any run of 7 consecutive study days with a rest day (never on a reserved exam-prep day)."""
    study_weekdays = {r.weekday for r in rules} - set(rest_weekdays)
    forced: set[date] = set()
    run: list[date] = []
    d = start
    while d <= end:
        if d.weekday() in study_weekdays:
            run.append(d)
            if len(run) == 7:
                pick = next((x for x in reversed(run) if x not in reserved), None)
                if pick is not None:
                    forced.add(pick)
                    run = [x for x in run if x > pick]
        else:
            run = []
        d += timedelta(days=1)
    return forced


@dataclass
class _Work:
    unit: UnitSpec
    kind: SessionKind
    remaining: int


def generate_plan(
    now: datetime,
    exams: Sequence[ExamSpec],
    units: Sequence[UnitSpec],
    prereqs: Sequence[tuple[str, str]],
    prefs: Prefs,
    rules: Sequence[AvailabilityRule],
    busy: Sequence[Interval] = (),
    *,
    frozen: Sequence[PlannedSession] = (),
    completed_learn: Mapping[str, int] | None = None,
    remediation: Mapping[str, int] | None = None,
    previous: Sequence[PlannedSession] = (),
) -> Plan:
    zone = ZoneInfo(prefs.tz)
    completed_learn = completed_learn or {}
    remediation = remediation or {}
    exams = sorted(exams, key=lambda e: e.starts_at)
    exam_by_id = {e.exam_id: e for e in exams}
    horizon_end = max(e.starts_at for e in exams)
    exam_days = {e.exam_id: local_date(e.starts_at, zone) for e in exams}
    reserved = {d - timedelta(days=k) for d in exam_days.values() for k in (0, 1, 2)}
    rest = set(
        forced_rest_dates(local_date(now, zone), local_date(horizon_end, zone), rules, prefs.rest_weekdays, reserved)
    )
    d = local_date(now, zone)
    while d <= local_date(horizon_end, zone):
        if d.weekday() in prefs.rest_weekdays or d in exam_days.values():
            rest.add(d)
        d += timedelta(days=1)
    rest -= reserved - set(exam_days.values())  # reservation days are never rest days

    frozen_ivs = [Interval(s.start, s.end) for s in frozen]
    windows = build_windows(
        prefs.tz, now, horizon_end, rules, [*busy, *frozen_ivs], rest, prefs.earliest, prefs.latest, prefs.min_block
    )
    board = Board(zone=zone, windows=windows, daily_max=prefs.daily_max_min)
    for s in frozen:
        board.day_used[local_date(s.start, zone)] += s.minutes

    prev_by_key = {s.key: s for s in previous if not s.frozen}
    frozen_keys = {s.key for s in frozen}
    sessions: list[PlannedSession] = list(frozen)
    warnings: list[str] = []
    title = {u.unit_id: u.title for u in units}

    def place(
        key: str,
        exam_id: str,
        kind: SessionKind,
        unit_ids: tuple[str, ...],
        after: datetime,
        before: datetime,
        min_len: int,
        max_len: int,
        rationale: str,
        respect_daily: bool = True,
    ) -> Interval | None:
        if key in frozen_keys:
            return None
        iv: Interval | None = None
        old = prev_by_key.get(key)
        if old is not None and min_len <= old.minutes <= max_len:
            iv = board.nearest(old.start, old.minutes, after, before, respect_daily)
        if iv is None:
            iv = board.earliest(after, before, min_len, max_len, respect_daily)
        if iv is not None:
            board.take(iv, count_daily=respect_daily)
            sessions.append(
                PlannedSession(
                    key=key,
                    exam_id=exam_id,
                    kind=kind,
                    unit_ids=unit_ids,
                    start=iv.start,
                    end=iv.end,
                    rationale=rationale,
                )
            )
        return iv

    # 1) reservations
    for e in exams:
        dd = exam_days[e.exam_id]
        d1, d2 = dd - timedelta(days=1), dd - timedelta(days=2)
        day1 = (_local_midnight(d1, zone), min(_local_midnight(dd, zone), e.starts_at))
        day2 = (_local_midnight(d2, zone), _local_midnight(d1, zone))
        mock_len = e.duration_min + 15
        if (
            not place(
                f"{e.exam_id}:mock",
                e.exam_id,
                "mock",
                (),
                max(now, day2[0]),
                day2[1],
                mock_len,
                mock_len,
                f"Timed mock of {e.title} two days before, same length as the real exam plus review",
                respect_daily=False,
            )
            and f"{e.exam_id}:mock" not in frozen_keys
        ):
            warnings.append(f"{e.exam_id}: no {mock_len}-minute window two days before the exam for the mock")
        place(
            f"{e.exam_id}:consolidation:d2",
            e.exam_id,
            "consolidation",
            (),
            max(now, day2[0]),
            day2[1],
            min(prefs.min_block, 30),
            30,
            "Consolidation review after the mock",
        )
        if not (
            place(
                f"{e.exam_id}:consolidation:d1",
                e.exam_id,
                "consolidation",
                (),
                max(now, day1[0]),
                day1[1],
                60,
                120,
                f"Cumulative review and warm-up the day before {e.title}",
            )
            or place(
                f"{e.exam_id}:consolidation:d1",
                e.exam_id,
                "consolidation",
                (),
                max(now, day1[0]),
                day1[1],
                prefs.min_block,
                120,
                f"Cumulative review the day before {e.title} (short: limited time)",
            )
        ):
            if f"{e.exam_id}:consolidation:d1" not in frozen_keys:
                warnings.append(f"{e.exam_id}: no time the day before the exam for consolidation")

    # 2) learn + remediation, urgency-interleaved across exams
    queues: dict[str, list[_Work]] = {}
    unit_minutes: dict[str, int] = {}
    practice_of: dict[str, int] = {}
    for e in exams:
        eu = [u for u in units if u.exam_id == e.exam_id]
        if not eu:
            continue
        median_w = statistics.median(u.weight for u in eu)
        q: list[_Work] = []
        for u in topo_order(eu, prereqs):
            learn = max(0, learn_minutes(u, prefs.min_block) - completed_learn.get(u.unit_id, 0))
            if 0 < learn < prefs.min_block:
                learn = prefs.min_block
            practice = practice_minutes(u, learn_minutes(u, prefs.min_block), median_w)
            practice_of[u.unit_id] = practice
            unit_minutes[u.unit_id] = learn_minutes(u, prefs.min_block) + practice
            if remediation.get(u.unit_id, 0) > 0:
                q.insert(0, _Work(u, "practice", max(prefs.min_block, _round_up(remediation[u.unit_id]))))
            if learn > 0:
                q.append(_Work(u, "learn", learn))
        queues[e.exam_id] = q

    deadline = {e.exam_id: _local_midnight(exam_days[e.exam_id] - timedelta(days=2), zone) for e in exams}
    unit_prereqs: dict[str, set[str]] = defaultdict(set)
    for a, b in prereqs:
        unit_prereqs[b].add(a)
    all_work = [w for q in queues.values() for w in q]
    unit_end: dict[str, datetime] = {}
    last_learn_end: dict[str, datetime] = {}
    used_keys: set[str] = {s.key for s in sessions}
    stuck: set[tuple[str, str]] = set()

    def ready_at(w: _Work) -> datetime | None:
        """Earliest start for the next block of ``w``: after its prerequisites are fully placed (and after the
        unit's own previous block). None while a prerequisite still has unplaced learning."""
        t = max(now, unit_end.get(w.unit.unit_id, now))
        if w.kind == "learn":
            for p in unit_prereqs[w.unit.unit_id]:
                if any(x.unit.unit_id == p and x.kind == "learn" and x.remaining > 0 for x in all_work):
                    return None
                t = max(t, unit_end.get(p, now))
        return t

    def next_key(ex_id: str, uid: str, kind: str) -> str:
        n = 0
        while f"{ex_id}:{uid}:{kind}:{n}" in used_keys:
            n += 1
        return f"{ex_id}:{uid}:{kind}:{n}"

    def record(w: _Work, iv: Interval, key: str) -> None:
        board.take(iv)
        uid = w.unit.unit_id
        prereq_names = [title[a] for a in sorted(unit_prereqs[uid]) if a in title]
        why = (
            f"Learn {w.unit.title}" + (f" after its prerequisite {', '.join(prereq_names)}" if prereq_names else "")
            if w.kind == "learn"
            else f"Remediation practice for {w.unit.title} after a low score"
        )
        sessions.append(
            PlannedSession(
                key=key, exam_id=w.unit.exam_id, kind=w.kind, unit_ids=(uid,), start=iv.start, end=iv.end, rationale=why
            )
        )
        used_keys.add(key)
        w.remaining -= iv.minutes
        unit_end[uid] = max(unit_end.get(uid, iv.end), iv.end)
        if w.kind == "learn":
            last_learn_end[uid] = max(last_learn_end.get(uid, iv.end), iv.end)

    # 2a) stability: keep previous learn/remediation blocks whose slot is still free and still consistent
    work_by = {(w.unit.unit_id, w.kind): w for w in all_work}
    for old in sorted(
        (x for x in previous if not x.frozen and x.kind in ("learn", "practice") and not x.key.endswith(":main")),
        key=lambda x: (x.start, x.key),
    ):
        w = work_by.get((old.unit_ids[0], old.kind))
        if w is None or old.key in used_keys or old.start < now or w.remaining < old.minutes:
            continue
        r = ready_at(w)
        iv = Interval(old.start, old.end)
        if (
            r is None
            or old.start < r
            or old.end > deadline[old.exam_id]
            or not board.contains(iv)
            or board.day_left(old.start) < old.minutes
        ):
            continue
        record(w, iv, old.key)

    def chunk(remaining: int, room: int) -> int | None:
        cap = min(room, prefs.max_block)
        if remaining <= cap:
            return remaining
        c = cap
        if remaining - c < prefs.min_block:
            c = remaining - prefs.min_block
        c -= c % GRID
        return c if c >= prefs.min_block else None

    # 2b) place the rest: earliest usable slot, most urgent exam first; displaced blocks land nearest their old slot
    while True:
        options: list[tuple[datetime, float, str, int, Interval, _Work]] = []
        for ex_id, q in queues.items():
            pending = [w for w in q if w.remaining > 0 and (w.unit.unit_id, w.kind) not in stuck]
            ready = [(w, r) for w in pending if (r := ready_at(w)) is not None]
            if not ready:
                continue
            w, r = ready[0]
            slot = board.earliest(
                r, deadline[ex_id], min(prefs.min_block, w.remaining), min(prefs.max_block, w.remaining)
            )
            size = chunk(w.remaining, slot.minutes) if slot is not None else None
            if slot is not None and size is None:  # slot too small to split well; look past it
                slot = board.earliest(
                    slot.end,
                    deadline[ex_id],
                    min(w.remaining, prefs.max_block, prefs.min_block * 2),
                    min(prefs.max_block, w.remaining),
                )
                size = chunk(w.remaining, slot.minutes) if slot is not None else None
            if slot is None or size is None:
                stuck.add((w.unit.unit_id, w.kind))
                options.append((datetime.max.replace(tzinfo=UTC), 0.0, ex_id, -1, Interval(now, now), w))
                continue
            free = max(1, board.free_minutes(r, deadline[ex_id]))
            urgency = sum(x.remaining for x in pending) / free * exam_by_id[ex_id].weight_pct
            options.append(
                (slot.start, -urgency, ex_id, q.index(w), Interval(slot.start, slot.start + size * MINUTE), w)
            )
        real = [o for o in options if o[3] >= 0]
        if not real:
            if any(o[3] < 0 for o in options):
                continue  # something just got stuck; other items may now be the first ready ones
            break
        _, _, ex_id, _, chosen, w = min(real, key=lambda o: (o[0], o[1], o[2], o[3]))
        key = next_key(ex_id, w.unit.unit_id, w.kind)
        before = prev_by_key.get(key)
        if before is not None and before.minutes == chosen.minutes:
            r = ready_at(w)
            near = board.nearest(before.start, before.minutes, r, deadline[ex_id]) if r is not None else None
            if near is not None:
                chosen = near
        record(w, chosen, key)

    # 3) spaced reviews (merged per exam per day) and practice
    unit_by_id = {u.unit_id: u for u in units}
    review_need: dict[tuple[str, date], list[tuple[str, int, int]]] = defaultdict(list)
    for uid, end in last_learn_end.items():
        u = unit_by_id[uid]
        mins = max(prefs.min_block, _round_up(0.2 * unit_minutes.get(uid, 0)))
        for off in REVIEW_OFFSETS:
            target = local_date(end, zone) + timedelta(days=off)
            if target < exam_days[u.exam_id] - timedelta(days=2):
                review_need[(u.exam_id, target)].append((uid, off, mins))
    review_day_of: dict[tuple[str, int], date] = {}
    for (ex_id, target), items in sorted(review_need.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        uids = tuple(dict.fromkeys(uid for uid, _, _ in items))
        total = min(prefs.max_block, sum(m for _, _, m in items))
        names = ", ".join(title[u] for u in uids)
        offsets = sorted({o for _, o, _ in items})
        placed = place(
            f"{ex_id}:review:{target.isoformat()}",
            ex_id,
            "review",
            uids,
            max(now, _local_midnight(target, zone)),
            deadline[ex_id],
            prefs.min_block,
            total,
            f"Spaced review (+{'/+'.join(map(str, offsets))} days) of {names}",
        )
        if placed is not None:
            for uid, off, _ in items:
                review_day_of[(uid, off)] = local_date(placed.start, zone)
    for u in units:
        if u.unit_id not in last_learn_end:
            continue
        practice = practice_of.get(u.unit_id, 0)
        if practice <= 0:
            continue
        after_day = review_day_of.get((u.unit_id, 3), local_date(last_learn_end[u.unit_id], zone))
        place(
            f"{u.exam_id}:{u.unit_id}:practice:main",
            u.exam_id,
            "practice",
            (u.unit_id,),
            max(now, _local_midnight(after_day, zone), last_learn_end[u.unit_id]),
            deadline[u.exam_id],
            min(practice, prefs.min_block),
            practice,
            f"Practice questions on {u.title} (high-weight unit)",
        )

    # 4) buffers after every 6th study day
    study_days = sorted({local_date(s.start, zone) for s in sessions})
    for i, sd in enumerate(study_days, start=1):
        if i % 6 != 0:
            continue
        ex = next((e for e in exams if exam_days[e.exam_id] > sd), None)
        if ex is None:
            continue
        place(
            f"buffer:{sd.isoformat()}",
            ex.exam_id,
            "buffer",
            (),
            max(now, _local_midnight(sd, zone)),
            _local_midnight(sd + timedelta(days=1), zone),
            45,
            45,
            "Catch-up buffer after six study days",
        )

    # 5) feasibility
    per_exam = {ex_id: sum(w.remaining for w in q) for ex_id, q in queues.items() if sum(w.remaining for w in q) > 0}
    deficit = sum(per_exam.values())
    feas: Feasibility
    if deficit:
        days_left = max(
            1,
            len(
                {
                    d
                    for d in (
                        local_date(w.start, zone)
                        for w in build_windows(
                            prefs.tz, now, horizon_end, rules, busy, rest, prefs.earliest, prefs.latest, prefs.min_block
                        )
                    )
                }
            ),
        )
        skim: list[str] = []
        acc = 0
        for u in sorted((u for u in units if u.exam_id in per_exam), key=lambda u: (u.weight, u.unit_id)):
            if acc >= deficit:
                break
            skim.append(u.unit_id)
            acc += unit_minutes.get(u.unit_id, 0)
        feas = Feasibility(
            status="deficit",
            deficit_min=deficit,
            per_exam=per_exam,
            extend_daily_max_to=prefs.daily_max_min + math.ceil(deficit / days_left),
            skim_units=tuple(skim),
            warnings=tuple(warnings),
        )
    else:
        feas = Feasibility(status="ok", warnings=tuple(warnings))
    return Plan(sessions=tuple(sorted(sessions, key=lambda s: (s.start, s.key))), feasibility=feas)


# ---------------------------------------------------------------- rebalancing
class ExistingSession(_Frozen):
    session: PlannedSession
    status: Literal["planned", "in_progress", "done", "missed", "skipped"]
    locked: bool = False


class ChangeSummary(_Frozen):
    moved: tuple[str, ...]
    added: tuple[str, ...]
    removed: tuple[str, ...]
    deficit_change: int
    changes_within_48h: bool


def rebalance(
    now: datetime,
    existing: Sequence[ExistingSession],
    previous_feasibility: Feasibility,
    exams: Sequence[ExamSpec],
    units: Sequence[UnitSpec],
    prereqs: Sequence[tuple[str, str]],
    prefs: Prefs,
    rules: Sequence[AvailabilityRule],
    busy: Sequence[Interval] = (),
    unit_scores: Mapping[str, float] | None = None,
) -> tuple[Plan, ChangeSummary]:
    frozen: list[PlannedSession] = []
    completed: dict[str, int] = defaultdict(int)
    for es in existing:
        s = es.session
        keep = (
            es.status in ("done", "in_progress")
            or es.locked
            or (es.status == "planned" and s.start < now + FREEZE_WINDOW)
        )
        if keep:
            frozen.append(s.model_copy(update={"frozen": True}))
            if s.kind == "learn" and es.status != "missed":
                for uid in s.unit_ids:
                    completed[uid] += s.minutes
    unit_by_id = {u.unit_id: u for u in units}
    remediation: dict[str, int] = {}
    for uid, score in (unit_scores or {}).items():
        if score < 0.7 and uid in unit_by_id:
            u = unit_by_id[uid]
            median_w = statistics.median(x.weight for x in units if x.exam_id == u.exam_id)
            learn = learn_minutes(u, prefs.min_block)
            m_u = learn + practice_minutes(u, learn, median_w)
            remediation[uid] = int(m_u * (0.7 - score) * 1.5)
    previous = [es.session for es in existing]
    plan = generate_plan(
        now,
        exams,
        units,
        prereqs,
        prefs,
        rules,
        busy,
        frozen=frozen,
        completed_learn=completed,
        remediation=remediation,
        previous=previous,
    )
    plan = plan.model_copy(update={"algorithm_version": REBALANCE_VERSION})

    old = {s.key: s for s in previous if s.start >= now or s.key in {f.key for f in frozen}}
    new = {s.key: s for s in plan.sessions}
    moved = tuple(
        sorted(k for k in old.keys() & new.keys() if (old[k].start, old[k].end) != (new[k].start, new[k].end))
    )
    added = tuple(sorted(new.keys() - old.keys()))
    removed = tuple(sorted(k for k in old.keys() - new.keys() if old[k].start >= now))
    soon = now + timedelta(hours=48)
    touched = [new[k] for k in (*moved, *added)] + [old[k] for k in (*moved, *removed)]
    summary = ChangeSummary(
        moved=moved,
        added=added,
        removed=removed,
        deficit_change=plan.feasibility.deficit_min - previous_feasibility.deficit_min,
        changes_within_48h=any(s.start < soon for s in touched),
    )
    return plan, summary

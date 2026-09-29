from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.planner.planner import (
    ExamSpec,
    ExistingSession,
    Plan,
    PlannedSession,
    Prefs,
    UnitSpec,
    generate_plan,
    learn_minutes,
    rebalance,
    topo_order,
)
from engine.planner.timeline import AvailabilityRule, Interval, ambiguous_ranges, build_windows

NY = ZoneInfo("America/New_York")
PREFS = Prefs(tz="America/New_York", daily_max_min=180, min_block=25, max_block=90)
WEEKDAY_EVENINGS = [AvailabilityRule(d, time(18, 0), time(21, 0)) for d in range(5)]
WEEKENDS = [AvailabilityRule(d, time(10, 0), time(14, 0)) for d in (5, 6)]
RULES = WEEKDAY_EVENINGS + WEEKENDS
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=NY)  # Thursday
MIDTERM = ExamSpec(
    exam_id="E1", title="Midterm", starts_at=datetime(2026, 10, 15, 18, 0, tzinfo=NY), duration_min=90, weight_pct=30
)


def units_for(exam: str, n: int, tokens: int = 40_000, prefix: str = "U") -> list[UnitSpec]:
    return [
        UnitSpec(
            unit_id=f"{prefix}{i}", exam_id=exam, title=f"Unit {i}", weight=10 + i, tokens=tokens, syllabus_order=i
        )
        for i in range(1, n + 1)
    ]


UNITS = units_for("E1", 5)  # learn_minutes: 0.9*40 = 36 -> 40 min each
DAG = [("U1", "U2"), ("U2", "U3"), ("U1", "U4")]


def windows_for(
    prefs: Prefs = PREFS, rules=RULES, now: datetime = NOW, end: datetime = MIDTERM.starts_at, busy=()
) -> list[Interval]:  # type: ignore[no-untyped-def]
    return build_windows(prefs.tz, now, end, rules, busy, (), prefs.earliest, prefs.latest, prefs.min_block)


def assert_invariants(plan: Plan, prefs: Prefs, allowed: list[Interval], now: datetime) -> None:
    sess = sorted(plan.sessions, key=lambda s: s.start)
    for a, b in pairwise(sess):
        assert a.end <= b.start, f"overlap {a.key} / {b.key}"
    for s in sess:
        if s.frozen:
            continue
        assert s.start >= now
        assert any(w.start <= s.start and s.end <= w.end for w in allowed), f"{s.key} outside free windows"
        if s.kind != "mock":
            assert prefs.min_block <= s.minutes <= max(prefs.max_block, 120), f"{s.key} has {s.minutes} min"
    per_day: dict[date, int] = defaultdict(int)
    for s in sess:
        if s.kind != "mock":
            per_day[s.start.astimezone(ZoneInfo(prefs.tz)).date()] += s.minutes
    assert all(v <= prefs.daily_max_min for v in per_day.values())


def learn_blocks(plan: Plan, unit: str) -> list[PlannedSession]:
    return sorted((s for s in plan.sessions if s.kind == "learn" and unit in s.unit_ids), key=lambda s: s.start)


# ---------------------------------------------------------------- building blocks
def test_learn_minutes_clamp_and_mastery() -> None:
    u = UnitSpec(unit_id="a", exam_id="e", title="A", weight=1, tokens=500_000, syllabus_order=1)
    assert learn_minutes(u, 25) == 240
    assert learn_minutes(u.model_copy(update={"tokens": 1000}), 25) == 25  # 20-min floor → min block
    assert learn_minutes(u.model_copy(update={"tokens": 100_000, "dense": True}), 25) == 120  # 0.9*100*1.3 = 117
    assert learn_minutes(u.model_copy(update={"mastery": 0.95}), 25) == 0  # 12 min → below half a block


def test_topo_order_prereqs_ties_and_cycles() -> None:
    order = [u.unit_id for u in topo_order(UNITS, DAG)]
    assert order.index("U1") < order.index("U2") < order.index("U3") and order.index("U1") < order.index("U4")
    cyc = [u.unit_id for u in topo_order(UNITS[:3], [("U1", "U2"), ("U2", "U3"), ("U3", "U1")])]
    assert cyc == ["U1", "U2", "U3"]  # backward (U3→U1) edge dropped by syllabus order


def test_ambiguous_fall_back_hour_is_found() -> None:
    (r,) = ambiguous_ranges(datetime(2026, 10, 31, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC), NY)
    assert (r.start, r.end) == (datetime(2026, 11, 1, 5, 0, tzinfo=UTC), datetime(2026, 11, 1, 7, 0, tzinfo=UTC))


# ---------------------------------------------------------------- fixtures (doc 05 §4)
def test_single_exam_feasible() -> None:
    plan = generate_plan(NOW, [MIDTERM], UNITS, DAG, PREFS, RULES)
    assert plan.feasibility.status == "ok"
    assert_invariants(plan, PREFS, windows_for(), NOW)
    kinds = [s.kind for s in plan.sessions]
    assert kinds.count("mock") == 1 and kinds.count("consolidation") == 2
    mock = next(s for s in plan.sessions if s.kind == "mock")
    assert mock.minutes == 105 and mock.start.astimezone(NY).date() == date(2026, 10, 13)
    d1 = next(s for s in plan.sessions if s.key == "E1:consolidation:d1")
    assert d1.start.astimezone(NY).date() == date(2026, 10, 14) and 60 <= d1.minutes <= 120
    deadline = datetime(2026, 10, 13, 0, 0, tzinfo=NY)  # learning finishes by the end of D-3
    for u in UNITS:
        blocks = learn_blocks(plan, u.unit_id)
        assert sum(b.minutes for b in blocks) == 40 and blocks[-1].end <= deadline
    assert any(s.kind == "review" for s in plan.sessions)
    assert all(s.rationale for s in plan.sessions)
    # deterministic: same inputs → identical plan
    assert generate_plan(NOW, [MIDTERM], UNITS, DAG, PREFS, RULES) == plan


def test_prereq_order() -> None:
    plan = generate_plan(NOW, [MIDTERM], UNITS, DAG, PREFS, RULES)
    for a, b in DAG:
        assert learn_blocks(plan, a)[-1].end <= learn_blocks(plan, b)[0].start


def test_infeasible_deficit() -> None:
    tight = [AvailabilityRule(d, time(19, 0), time(19, 30)) for d in range(7)]
    big = units_for("E1", 4, tokens=200_000)  # 180 min each
    plan = generate_plan(NOW, [MIDTERM], big, [], PREFS, tight)
    f = plan.feasibility
    assert f.status == "deficit" and f.deficit_min > 0 and f.per_exam["E1"] == f.deficit_min
    assert f.skim_units and f.skim_units[0] == "U1"  # lowest weight first
    assert f.extend_daily_max_to is not None and f.extend_daily_max_to > PREFS.daily_max_min
    assert_invariants(plan, PREFS, windows_for(rules=tight), NOW)


def test_two_exams_overlap_urgency() -> None:
    quiz = ExamSpec(
        exam_id="E0", title="Quiz", starts_at=datetime(2026, 10, 9, 18, 0, tzinfo=NY), duration_min=30, weight_pct=10
    )
    later = MIDTERM.model_copy(update={"starts_at": datetime(2026, 10, 20, 18, 0, tzinfo=NY)})
    units = units_for("E0", 2, prefix="Q") + units_for("E1", 4)
    plan = generate_plan(NOW, [quiz, later], units, [], PREFS, RULES)
    assert {s.key for s in plan.sessions} >= {"E0:mock", "E0:consolidation:d1", "E1:mock", "E1:consolidation:d1"}
    # urgency = remaining / free-before-deadline × weight: the 30% midterm can outrank a roomy 10% quiz,
    # but both finish learning before their own deadlines (end of D-3)
    assert plan.feasibility.status == "ok"
    assert learn_blocks(plan, "Q2")[-1].end <= datetime(2026, 10, 7, 0, 0, tzinfo=NY)
    assert learn_blocks(plan, "U4")[-1].end <= datetime(2026, 10, 18, 0, 0, tzinfo=NY)
    exams_in_learning = {
        s.exam_id for s in plan.sessions if s.kind == "learn" and s.start < datetime(2026, 10, 7, tzinfo=NY)
    }
    assert exams_in_learning == {"E0", "E1"}  # interleaved, not one exam after the other
    assert_invariants(plan, PREFS, windows_for(end=later.starts_at), NOW)


def test_equal_weight_sooner_exam_goes_first() -> None:
    a = ExamSpec(
        exam_id="A", title="A", starts_at=datetime(2026, 10, 9, 18, 0, tzinfo=NY), duration_min=30, weight_pct=20
    )
    b = ExamSpec(
        exam_id="B", title="B", starts_at=datetime(2026, 10, 25, 18, 0, tzinfo=NY), duration_min=30, weight_pct=20
    )
    plan = generate_plan(NOW, [a, b], units_for("A", 2, prefix="A") + units_for("B", 2, prefix="B"), [], PREFS, RULES)
    first_learn = min((s for s in plan.sessions if s.kind == "learn"), key=lambda s: s.start)
    assert first_learn.exam_id == "A"


def test_dst_transition_has_no_ambiguous_local_times() -> None:
    night = [AvailabilityRule(d, time(0, 30), time(3, 0)) for d in range(7)]
    now = datetime(2026, 10, 30, 12, 0, tzinfo=NY)
    exam = ExamSpec(
        exam_id="E", title="Final", starts_at=datetime(2026, 11, 7, 12, 0, tzinfo=NY), duration_min=60, weight_pct=40
    )
    plan = generate_plan(now, [exam], units_for("E", 3), [], PREFS.model_copy(update={"max_block": 60}), night)
    fall_back_hour = Interval(datetime(2026, 11, 1, 5, 0, tzinfo=UTC), datetime(2026, 11, 1, 7, 0, tzinfo=UTC))
    for s in plan.sessions:
        assert not Interval(s.start, s.end).overlaps(fall_back_hour), s.key
        local = s.start.astimezone(NY).replace(tzinfo=None)
        assert local.replace(tzinfo=NY).astimezone(UTC) == local.replace(tzinfo=NY, fold=1).astimezone(UTC)


# ---------------------------------------------------------------- rebalancing
def as_existing(plan: Plan, status_of: dict[str, str] | None = None) -> list[ExistingSession]:
    status_of = status_of or {}
    return [ExistingSession(session=s, status=status_of.get(s.key, "planned")) for s in plan.sessions]  # type: ignore[arg-type]


def test_rebalance_missed_session_minimal_moves() -> None:
    plan = generate_plan(NOW, [MIDTERM], UNITS, DAG, PREFS, RULES)
    first = learn_blocks(plan, "U1")[0]
    later_now = first.end + timedelta(hours=2)
    existing = as_existing(plan, {first.key: "missed"})
    new_plan, summary = rebalance(later_now, existing, plan.feasibility, [MIDTERM], UNITS, DAG, PREFS, RULES)
    assert new_plan.algorithm_version == "rebalance-1"
    assert new_plan.feasibility.status == "ok"
    assert sum(b.minutes for b in learn_blocks(new_plan, "U1") if b.start >= later_now) == 40  # carried forward
    assert len(summary.moved) + len(summary.added) <= 3 + 1  # U1's block reappears; few others shift
    assert_invariants(new_plan, PREFS, windows_for(now=later_now), later_now)


def test_rebalance_low_score_adds_remediation() -> None:
    plan = generate_plan(NOW, [MIDTERM], UNITS, DAG, PREFS, RULES)
    later = NOW + timedelta(days=2)
    new_plan, summary = rebalance(
        later, as_existing(plan), plan.feasibility, [MIDTERM], UNITS, DAG, PREFS, RULES, unit_scores={"U2": 0.4}
    )
    remediation = [
        s
        for s in new_plan.sessions
        if s.kind == "practice" and s.key.startswith("E1:U2:practice:") and not s.key.endswith(":main")
    ]
    # m_u = 40 learn + 0 practice (U2 below median weight) → 40 * 0.3 * 1.5 = 18 → one 25-min block
    assert sum(s.minutes for s in remediation) == 25
    assert summary.added


def test_calendar_busy_change_moves_conflict_to_nearest_slot() -> None:
    plan = generate_plan(NOW, [MIDTERM], UNITS, DAG, PREFS, RULES)
    target = sorted((s for s in plan.sessions if s.kind == "learn"), key=lambda s: s.start)[1]
    busy = [Interval(target.start, target.end)]
    new_plan, summary = rebalance(
        NOW, as_existing(plan), plan.feasibility, [MIDTERM], UNITS, DAG, PREFS, RULES, busy=busy
    )
    assert all(not Interval(s.start, s.end).overlaps(busy[0]) for s in new_plan.sessions)
    old = {s.key: s for s in plan.sessions}
    new = {s.key: s for s in new_plan.sessions}
    # the conflicting block (U2) moves to the nearest free slot after its prerequisite U1 (right after the busy block)
    assert target.key == "E1:U2:learn:0" and target.key in summary.moved
    assert new[target.key].start == target.end
    # U3 depends on U2, so it must follow; units that don't depend on U2 keep their slots, as do the reservations
    for key in (
        "E1:U1:learn:0",
        "E1:U4:learn:0",
        "E1:U5:learn:0",
        "E1:mock",
        "E1:consolidation:d1",
        "E1:consolidation:d2",
    ):
        assert (new[key].start, new[key].end) == (old[key].start, old[key].end), key
    assert new["E1:U3:learn:0"].start >= new[target.key].end


# ---------------------------------------------------------------- properties
rule_strategy = st.lists(
    st.tuples(st.integers(0, 6), st.integers(6, 20), st.integers(1, 4)).map(
        lambda t: AvailabilityRule(t[0], time(t[1], 0), time(min(23, t[1] + t[2]), 0))
    ),
    min_size=1,
    max_size=8,
)


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rule_strategy, st.integers(1, 6), st.integers(10_000, 150_000), st.integers(8, 30), st.integers(60, 300))
def test_planner_invariants(
    rules: list[AvailabilityRule], n_units: int, tokens: int, days: int, daily_max: int
) -> None:
    prefs = PREFS.model_copy(update={"daily_max_min": daily_max})
    exam = MIDTERM.model_copy(update={"starts_at": NOW + timedelta(days=days)})
    units = units_for("E1", n_units, tokens=tokens)
    plan = generate_plan(NOW, [exam], units, [], prefs, rules)
    assert_invariants(plan, prefs, windows_for(prefs, rules, NOW, exam.starts_at), NOW)
    placed = sum(s.minutes for s in plan.sessions if s.kind == "learn")
    required = sum(learn_minutes(u, prefs.min_block) for u in units)
    assert placed + plan.feasibility.deficit_min >= required  # everything is either placed or reported
    if plan.feasibility.status == "ok":
        assert placed >= required

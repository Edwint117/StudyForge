"""Syllabus extraction schema, validation and escalation (PLAN-01, EXAM-03; doc 06 §2 ``syllabus.extract``).

The LLM (Haiku first) returns a ``SyllabusExtraction`` in which **every field carries a confidence and a source
span** (character offsets into the syllabus text). This module:

* checks spans are in range and actually *support* the value (the digits of a weight or date appear in the span);
* flags ambiguous dates ("03/04": is that March 4 or April 3?), grading weights that don't add up to 100, exam
  weights that contradict the grading breakdown, dates outside the term, and duplicate exams;
* decides whether to escalate to Sonnet (any *required* field below 0.7 confidence);
* after the student confirms, turns the extraction into exam drafts and pre-exam checklist items.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date as Date
from datetime import datetime
from datetime import time as Time
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "syllabus-1"
ESCALATE_BELOW = 0.70
WEIGHT_TOLERANCE = 1.0  # percentage points

ExamKind = Literal["quiz", "midterm", "final", "other"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Sourced[T](_Model):
    value: T | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    span: tuple[int, int] | None = None  # [start, end) character offsets into the syllabus text

    @model_validator(mode="after")
    def _span_order(self) -> Sourced[T]:
        if self.span is not None and not 0 <= self.span[0] < self.span[1]:
            raise ValueError("span must satisfy 0 <= start < end")
        return self


class ExtractedExam(_Model):
    kind: Sourced[ExamKind] = Sourced[ExamKind]()
    title: Sourced[str] = Sourced[str]()
    date: Sourced[Date] = Sourced[Date]()
    start_time: Sourced[Time] = Sourced[Time]()
    duration_min: Sourced[int] = Sourced[int]()
    location: Sourced[str] = Sourced[str]()
    weight_pct: Sourced[float] = Sourced[float]()
    topics: Sourced[list[str]] = Sourced[list[str]]()


class GradeComponent(_Model):
    name: Sourced[str]
    weight_pct: Sourced[float]


class WeekTopics(_Model):
    week: int = Field(ge=1, le=30)
    start_date: Sourced[Date] = Sourced[Date]()
    topics: Sourced[list[str]] = Sourced[list[str]]()


class Policies(_Model):
    calculator: Sourced[str] = Sourced[str]()
    formula_sheet: Sourced[str] = Sourced[str]()
    id_required: Sourced[bool] = Sourced[bool]()
    scratch_paper: Sourced[str] = Sourced[str]()
    arrival: Sourced[str] = Sourced[str]()


class SyllabusExtraction(_Model):
    course_code: Sourced[str] = Sourced[str]()
    course_title: Sourced[str] = Sourced[str]()
    term: Sourced[str] = Sourced[str]()
    exams: tuple[ExtractedExam, ...] = ()
    grading: tuple[GradeComponent, ...] = ()
    schedule: tuple[WeekTopics, ...] = ()
    policies: Policies = Policies()


class Issue(_Model):
    path: str
    severity: Literal["error", "warning"]
    code: str
    message: str


class ValidationReport(_Model):
    issues: tuple[Issue, ...]
    highlight: tuple[str, ...]  # field paths the review UI should highlight
    needs_escalation: bool


# ---------------------------------------------------------------- helpers
def _iter_fields(ex: SyllabusExtraction) -> Iterator[tuple[str, Sourced[Any], bool]]:
    """(path, field, required). Required = exam kind/date/weight and every grading weight."""
    yield "course_code", ex.course_code, False
    yield "course_title", ex.course_title, False
    yield "term", ex.term, False
    for i, e in enumerate(ex.exams):
        for name in ("kind", "title", "date", "start_time", "duration_min", "location", "weight_pct", "topics"):
            yield f"exams[{i}].{name}", getattr(e, name), name in ("kind", "date", "weight_pct")
    for i, g in enumerate(ex.grading):
        yield f"grading[{i}].name", g.name, False
        yield f"grading[{i}].weight_pct", g.weight_pct, True
    for i, w in enumerate(ex.schedule):
        yield f"schedule[{i}].start_date", w.start_date, False
        yield f"schedule[{i}].topics", w.topics, False
    for name in ("calculator", "formula_sheet", "id_required", "scratch_paper", "arrival"):
        yield f"policies.{name}", getattr(ex.policies, name), False


_AMBIGUOUS_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-]\d{2,4})?\b")


def _digits(value: Any) -> list[str]:
    if isinstance(value, float):
        return [str(int(value)) if value == int(value) else f"{value:g}"]
    if isinstance(value, int) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, Date):
        return [str(value.day)]  # the day number must appear (month may be written as a word)
    if isinstance(value, Time):
        return [str(value.hour % 12 or 12)]
    return []


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ---------------------------------------------------------------- validation
def validate_extraction(
    ex: SyllabusExtraction, text: str, term_start: Date | None = None, term_end: Date | None = None
) -> ValidationReport:
    issues: list[Issue] = []
    highlight: list[str] = []
    escalate = False

    for path, f, required in _iter_fields(ex):
        low = f.confidence < ESCALATE_BELOW
        if f.value is None:
            if required:
                issues.append(
                    Issue(path=path, severity="error", code="missing_required", message="required field not found")
                )
                escalate = True
                highlight.append(path)
            continue
        if f.span is None or f.span[1] > len(text):
            issues.append(Issue(path=path, severity="warning", code="bad_span", message="no valid source span"))
            low = True
        else:
            quote = text[f.span[0] : f.span[1]]
            digits = _digits(f.value)
            if digits and not any(d in quote for d in digits):
                issues.append(
                    Issue(
                        path=path,
                        severity="warning",
                        code="unsupported_by_source",
                        message=f"value not found in quoted source {quote!r}",
                    )
                )
                low = True
            if isinstance(f.value, Date):
                for m in _AMBIGUOUS_DATE.finditer(quote):
                    a, b = int(m.group(1)), int(m.group(2))
                    if a != b and a <= 12 and b <= 12:
                        issues.append(
                            Issue(
                                path=path,
                                severity="warning",
                                code="ambiguous_date",
                                message=f"{m.group(0)!r} could be month/day or day/month",
                            )
                        )
                        low = True
                        break
        if low:
            highlight.append(path)
            if required:
                escalate = True

    # grading breakdown adds up to 100
    weights = [g.weight_pct.value for g in ex.grading if g.weight_pct.value is not None]
    if weights and abs(sum(weights) - 100) > WEIGHT_TOLERANCE:
        issues.append(
            Issue(
                path="grading",
                severity="warning",
                code="weights_not_100",
                message=f"grading weights add up to {sum(weights):g}%",
            )
        )
        highlight.append("grading")

    # each exam's weight should match a same-named grading component, if there is one
    components = {_norm(g.name.value): g.weight_pct.value for g in ex.grading if g.name.value}
    seen: set[tuple[str | None, Date | None]] = set()
    for i, e in enumerate(ex.exams):
        name = _norm(e.title.value or e.kind.value or "")
        comp = components.get(name)
        if comp is not None and e.weight_pct.value is not None and abs(comp - e.weight_pct.value) > WEIGHT_TOLERANCE:
            issues.append(
                Issue(
                    path=f"exams[{i}].weight_pct",
                    severity="warning",
                    code="weight_mismatch",
                    message=f"exam says {e.weight_pct.value:g}% but grading breakdown says {comp:g}%",
                )
            )
            highlight.append(f"exams[{i}].weight_pct")
        d = e.date.value
        if d is not None:
            if (term_start and d < term_start) or (term_end and d > term_end):
                issues.append(
                    Issue(
                        path=f"exams[{i}].date",
                        severity="warning",
                        code="outside_term",
                        message=f"{d.isoformat()} is outside the term",
                    )
                )
                highlight.append(f"exams[{i}].date")
            elif d.weekday() >= 5:
                issues.append(
                    Issue(
                        path=f"exams[{i}].date",
                        severity="warning",
                        code="weekend",
                        message=f"{d.isoformat()} is a weekend",
                    )
                )
        key = (e.kind.value, d)
        if d is not None and key in seen:
            issues.append(
                Issue(
                    path=f"exams[{i}]",
                    severity="warning",
                    code="duplicate_exam",
                    message="same kind and date as another exam",
                )
            )
            highlight.append(f"exams[{i}]")
        seen.add(key)

    return ValidationReport(issues=tuple(issues), highlight=tuple(dict.fromkeys(highlight)), needs_escalation=escalate)


# ---------------------------------------------------------------- after confirmation
class ExamDraft(_Model):
    title: str
    kind: ExamKind
    starts_at: datetime | None  # None when the syllabus gives no time: the student must set it
    duration_min: int | None
    weight_pct: float | None
    location: str | None
    policies: dict[str, str | bool]


class ChecklistSeed(_Model):
    label: str
    kind: Literal["calculator", "formula_sheet", "id", "scratch_paper", "arrival", "location"]


def to_exam_drafts(ex: SyllabusExtraction, tz: str) -> list[ExamDraft]:
    zone = ZoneInfo(tz)
    policies = {name: getattr(ex.policies, name).value for name in Policies.model_fields}
    clean_policies = {k: v for k, v in policies.items() if v is not None}
    drafts = []
    for e in ex.exams:
        kind: ExamKind = e.kind.value or "other"
        starts = (
            datetime.combine(e.date.value, e.start_time.value, tzinfo=zone)
            if e.date.value and e.start_time.value
            else None
        )
        drafts.append(
            ExamDraft(
                title=e.title.value or kind.title(),
                kind=kind,
                starts_at=starts,
                duration_min=e.duration_min.value,
                weight_pct=e.weight_pct.value,
                location=e.location.value,
                policies=clean_policies,
            )
        )
    return drafts


def checklist_seeds(ex: SyllabusExtraction, exam: ExtractedExam | None = None) -> list[ChecklistSeed]:
    """EXAM-03: pre-exam checklist items seeded from the syllabus policies (editable by the student)."""
    p = ex.policies
    seeds: list[ChecklistSeed] = []
    if p.calculator.value:
        seeds.append(ChecklistSeed(label=f"Calculator: {p.calculator.value}", kind="calculator"))
    if p.formula_sheet.value:
        seeds.append(ChecklistSeed(label=f"Formula sheet: {p.formula_sheet.value}", kind="formula_sheet"))
    if p.id_required.value:
        seeds.append(ChecklistSeed(label="Bring your student ID", kind="id"))
    if p.scratch_paper.value:
        seeds.append(ChecklistSeed(label=f"Scratch paper: {p.scratch_paper.value}", kind="scratch_paper"))
    if p.arrival.value:
        seeds.append(ChecklistSeed(label=f"Arrival: {p.arrival.value}", kind="arrival"))
    if exam is not None and exam.location.value:
        seeds.append(ChecklistSeed(label=f"Room: {exam.location.value}", kind="location"))
    return seeds


# ---------------------------------------------------------------- units + exam scope (PLAN-02 / PLAN-04 input)
class UnitDraft(_Model):
    ordinal: int
    title: str
    week: int
    week_start: Date | None
    topics: tuple[str, ...]


class ExamScope(_Model):
    exam_index: int
    unit_ordinals: tuple[int, ...]
    unit_weights: dict[int, float]  # ordinal → weight within this exam (sums to the exam's weight %, or 100)


def _topic_key(s: str) -> set[str]:
    return {w for w in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if len(w) > 2}


def to_units_and_scopes(ex: SyllabusExtraction) -> tuple[list[UnitDraft], list[ExamScope]]:
    """One unit per scheduled week that has topics. Exam scope: weeks whose topics overlap the exam's listed
    topics; if the exam lists none, a final covers every week and other exams cover the weeks since the previous
    exam (by week start date, else by week order). Units in scope share the exam's weight equally."""
    weeks = sorted((w for w in ex.schedule if w.topics.value), key=lambda w: w.week)
    units = [
        UnitDraft(
            ordinal=i,
            title=f"Week {w.week}: " + "; ".join(w.topics.value or []),
            week=w.week,
            week_start=w.start_date.value,
            topics=tuple(w.topics.value or ()),
        )
        for i, w in enumerate(weeks, start=1)
    ]
    exams = sorted(enumerate(ex.exams), key=lambda ie: (ie[1].date.value or Date.max, ie[0]))
    scopes: list[ExamScope] = []
    prev_date: Date | None = None
    prev_week = 0
    for idx, e in exams:
        wanted: set[str] = set().union(*(_topic_key(t) for t in (e.topics.value or [])))
        if wanted:
            chosen = [u for u in units if any(_topic_key(t) & wanted for t in u.topics)]
        elif e.kind.value == "final":
            chosen = list(units)
        elif e.date.value and any(u.week_start for u in units):
            chosen = [
                u
                for u in units
                if u.week_start and (prev_date is None or u.week_start >= prev_date) and u.week_start < e.date.value
            ]
        else:
            chosen = [u for u in units if u.week > prev_week]
            chosen = chosen[: max(1, len(chosen) // max(1, len(exams) - len(scopes)))]
        total = e.weight_pct.value or 100.0
        weights = {u.ordinal: round(total / len(chosen), 4) for u in chosen} if chosen else {}
        scopes.append(ExamScope(exam_index=idx, unit_ordinals=tuple(u.ordinal for u in chosen), unit_weights=weights))
        prev_date = e.date.value or prev_date
        prev_week = max((u.week for u in chosen), default=prev_week)
    return units, scopes

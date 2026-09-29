from datetime import date, time
from typing import Any

import pytest
from pydantic import ValidationError

from engine.ingest.syllabus import (
    ExtractedExam,
    GradeComponent,
    Policies,
    Sourced,
    SyllabusExtraction,
    WeekTopics,
    checklist_seeds,
    to_exam_drafts,
    to_units_and_scopes,
    validate_extraction,
)

TEXT = (
    "STAT 1450 - Intro to Statistics, Autumn 2026.\n"
    "Grading: Homework 20%, Midterm 30%, Final 50%.\n"
    "Midterm: Wednesday, October 14, 2026 at 6:00 pm in Hitchcock Hall 131 (90 minutes).\n"
    "Final: 12/09/2026, 8:00 am.\n"
    "One double-sided formula sheet allowed. TI-84 or simpler calculators only. Bring your BuckID.\n"
)


def span(snippet: str) -> tuple[int, int]:
    start = TEXT.index(snippet)
    return (start, start + len(snippet))


def s(value: Any, snippet: str, conf: float = 0.95) -> Sourced[Any]:
    return Sourced[Any](value=value, confidence=conf, span=span(snippet))


def extraction(**overrides: Any) -> SyllabusExtraction:
    midterm = ExtractedExam(
        kind=s("midterm", "Midterm: Wednesday"),
        title=s("Midterm", "Midterm: Wednesday"),
        date=s(date(2026, 10, 14), "October 14, 2026"),
        start_time=s(time(18, 0), "6:00 pm"),
        duration_min=s(90, "90 minutes"),
        location=s("Hitchcock Hall 131", "Hitchcock Hall 131"),
        weight_pct=s(30.0, "Midterm 30%"),
    )
    final = ExtractedExam(
        kind=s("final", "Final: 12/09/2026"),
        title=s("Final", "Final: 12/09/2026"),
        date=s(date(2026, 12, 9), "12/09/2026"),
        start_time=s(time(8, 0), "8:00 am"),
        weight_pct=s(50.0, "Final 50%"),
    )
    base: dict[str, Any] = {
        "course_code": s("STAT 1450", "STAT 1450"),
        "exams": (midterm, final),
        "grading": (
            GradeComponent(name=s("Homework", "Homework"), weight_pct=s(20.0, "Homework 20%")),
            GradeComponent(name=s("Midterm", "Midterm 30%"), weight_pct=s(30.0, "Midterm 30%")),
            GradeComponent(name=s("Final", "Final 50%"), weight_pct=s(50.0, "Final 50%")),
        ),
        "policies": Policies(
            calculator=s("TI-84 or simpler", "TI-84 or simpler calculators only"),
            formula_sheet=s("one double-sided sheet", "One double-sided formula sheet allowed"),
            id_required=s(True, "Bring your BuckID"),
        ),
    }
    base.update(overrides)
    return SyllabusExtraction(**base)


def codes(report: Any) -> set[str]:
    return {i.code for i in report.issues}


def test_clean_extraction_only_flags_the_ambiguous_final_date() -> None:
    report = validate_extraction(extraction(), TEXT, date(2026, 8, 25), date(2026, 12, 18))
    assert codes(report) == {"ambiguous_date"}  # 12/09 could be Dec 9 or Sep 12
    assert report.highlight == ("exams[1].date",)
    assert report.needs_escalation  # the final's date is required and now low confidence


def test_weights_must_add_up_and_match_exams() -> None:
    ex = extraction()
    bad_grading = (
        ex.grading[0],
        GradeComponent(name=ex.grading[1].name, weight_pct=s(25.0, "Midterm 30%")),  # contradicts exam + source
        ex.grading[2],
    )
    report = validate_extraction(ex.model_copy(update={"grading": bad_grading}), TEXT)
    assert {"weights_not_100", "weight_mismatch", "unsupported_by_source"} <= codes(report)


def test_low_confidence_required_field_triggers_escalation() -> None:
    ex = extraction()
    exams = (ex.exams[0].model_copy(update={"weight_pct": s(30.0, "Midterm 30%", conf=0.5)}), ex.exams[1])
    report = validate_extraction(ex.model_copy(update={"exams": exams}), TEXT)
    assert report.needs_escalation and "exams[0].weight_pct" in report.highlight


def test_low_confidence_optional_field_is_highlighted_but_not_escalated() -> None:
    ex = extraction(course_code=s("STAT 1450", "STAT 1450", conf=0.4))
    exams = (ex.exams[0], ex.exams[1].model_copy(update={"date": s(date(2026, 12, 9), "12/09/2026", conf=0.95)}))
    report = validate_extraction(ex.model_copy(update={"exams": exams}), TEXT)
    assert "course_code" in report.highlight


def test_missing_required_and_bad_span_and_term() -> None:
    ex = extraction()
    broken = ex.exams[0].model_copy(
        update={"date": Sourced[date](), "weight_pct": Sourced[float](value=30, confidence=0.9, span=(0, 10_000))}
    )
    outside = ex.exams[1].model_copy(update={"date": s(date(2027, 1, 20), "12/09/2026")})
    report = validate_extraction(
        ex.model_copy(update={"exams": (broken, outside)}), TEXT, date(2026, 8, 25), date(2026, 12, 18)
    )
    assert {"missing_required", "bad_span", "outside_term"} <= codes(report)
    assert report.needs_escalation


def test_duplicate_exam() -> None:
    ex = extraction()
    report = validate_extraction(ex.model_copy(update={"exams": (ex.exams[0], ex.exams[0])}), TEXT)
    assert "duplicate_exam" in codes(report)


def test_span_validation() -> None:
    with pytest.raises(ValidationError):
        Sourced[str](value="x", confidence=0.9, span=(5, 5))


def test_exam_drafts_and_checklist() -> None:
    drafts = to_exam_drafts(extraction(), "America/New_York")
    assert drafts[0].title == "Midterm" and drafts[0].duration_min == 90
    assert drafts[0].starts_at is not None and drafts[0].starts_at.isoformat() == "2026-10-14T18:00:00-04:00"
    assert drafts[1].starts_at is not None and drafts[1].starts_at.utcoffset().total_seconds() == -5 * 3600  # type: ignore[union-attr]
    assert drafts[0].policies["id_required"] is True

    no_time = extraction()
    exams = (no_time.exams[0].model_copy(update={"start_time": Sourced[time]()}),)
    assert to_exam_drafts(no_time.model_copy(update={"exams": exams}), "America/New_York")[0].starts_at is None

    seeds = checklist_seeds(extraction(), extraction().exams[0])
    assert [x.kind for x in seeds] == ["calculator", "formula_sheet", "id", "location"]


def _week(n: int, start: date | None, *topics: str) -> WeekTopics:
    return WeekTopics(
        week=n,
        start_date=Sourced[date](value=start, confidence=0.9) if start else Sourced[date](),
        topics=Sourced[list[str]](value=list(topics), confidence=0.9),
    )


def test_units_and_exam_scopes() -> None:
    schedule = (
        _week(1, date(2026, 8, 25), "Probability axioms"),
        _week(2, date(2026, 9, 1), "Conditional probability", "Bayes theorem"),
        _week(3, date(2026, 9, 8)),  # no topics -> no unit
        _week(4, date(2026, 10, 5), "Random variables"),
        _week(5, date(2026, 10, 19), "Expectation"),
    )
    ex = extraction(schedule=schedule)
    units, scopes = to_units_and_scopes(ex)
    assert [u.title for u in units] == [
        "Week 1: Probability axioms",
        "Week 2: Conditional probability; Bayes theorem",
        "Week 4: Random variables",
        "Week 5: Expectation",
    ]
    midterm, final = scopes
    assert midterm.unit_ordinals == (1, 2, 3)  # weeks starting before Oct 14
    assert midterm.unit_weights == {1: 10.0, 2: 10.0, 3: 10.0}  # 30% split equally
    assert final.unit_ordinals == (1, 2, 3, 4)  # finals are cumulative

    with_topics = ex.model_copy(
        update={
            "exams": (
                ex.exams[0].model_copy(update={"topics": Sourced[list[str]](value=["Bayes' theorem"], confidence=0.9)}),
            )
        }
    )
    _, (only,) = to_units_and_scopes(with_topics)
    assert only.unit_ordinals == (2,)

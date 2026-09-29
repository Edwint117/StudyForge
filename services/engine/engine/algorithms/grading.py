"""Mock-exam grading (DIAG-04; doc 05 §8).

Deterministic grading runs first (MCQ, numeric, SymPy, multi-step). Free-response and proof answers are
graded by the LLM rubric grader (M8-07); this module **validates** that grader's structured output against the
rubric and turns it into the same ``AnswerGrade`` shape, so everything downstream (results page, mastery,
error-mix heatmap, disputes) is grader-agnostic.

Error classes: conceptual, formula_recall, calculation_slip, incomplete, misread_question, notation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.algorithms.verification import (
    NumericSpec,
    SympySpec,
    TextSpec,
    Verdict,
    check_numeric,
    verify,
)

VERSION = "grading-1"

ErrorClass = Literal["conceptual", "formula_recall", "calculation_slip", "incomplete", "misread_question", "notation"]
GradedBy = Literal["deterministic", "llm", "hybrid", "user_dispute"]

LOW_CONFIDENCE = 0.70  # below this, the grade is flagged for the student's self-review
REGRADE_SHIFT_FLAG = 0.20  # a regrade moving the score by more than 20% of max is logged for evals
CALC_SLIP_REL = 0.05  # numeric answer within 5% (right units) → likely a calculation slip


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Deduction(_Frozen):
    points: float = Field(ge=0)
    reason: str
    error_class: ErrorClass | None = None
    criterion_id: str | None = None
    step_index: int | None = None


class AnswerGrade(_Frozen):
    awarded: float = Field(ge=0)
    max_points: float = Field(gt=0)
    deductions: tuple[Deduction, ...] = ()
    graded_by: GradedBy
    confidence: float = Field(ge=0, le=1)
    flagged_for_review: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> AnswerGrade:
        if self.awarded > self.max_points + 1e-9:
            raise ValueError("awarded exceeds max points")
        return self


def _grade(
    awarded: float, max_points: float, deductions: Sequence[Deduction], by: GradedBy, confidence: float
) -> AnswerGrade:
    return AnswerGrade(
        awarded=round(max(0.0, min(awarded, max_points)), 4),
        max_points=max_points,
        deductions=tuple(deductions),
        graded_by=by,
        confidence=confidence,
        flagged_for_review=confidence < LOW_CONFIDENCE,
    )


# ---------------------------------------------------------------- MCQ
def grade_mcq(selected: Sequence[str], correct: Sequence[str], points: float) -> AnswerGrade:
    """Single-answer: all or nothing. Multi-select: (right picks − wrong picks) / #correct, floored at 0."""
    sel, cor = set(selected), set(correct)
    if not cor:
        raise ValueError("an MCQ needs at least one correct choice")
    if len(cor) == 1:
        fraction = 1.0 if sel == cor else 0.0
    else:
        fraction = max(0.0, (len(sel & cor) - len(sel - cor)) / len(cor))
    awarded = points * fraction
    deductions = []
    if awarded < points:
        cls: ErrorClass = "incomplete" if not sel else "conceptual"
        deductions.append(Deduction(points=points - awarded, reason="incorrect or missing choices", error_class=cls))
    return _grade(awarded, points, deductions, "deterministic", 1.0)


# ---------------------------------------------------------------- single typed answer
def classify_numeric_miss(answer: str, spec: NumericSpec) -> ErrorClass:
    """Heuristic class for a wrong numeric answer: wrong dimension → conceptual; within 5% → calculation slip."""
    result = check_numeric(answer, spec.expected, rel_tol=CALC_SLIP_REL)
    if result.detail == "wrong units/dimension":
        return "conceptual"
    if result.detail.startswith("unparseable"):
        return "notation"
    return "calculation_slip" if result.verdict is Verdict.CORRECT else "conceptual"


def grade_typed(answer: str, spec: TextSpec | NumericSpec | SympySpec, points: float) -> AnswerGrade:
    if not answer.strip():
        return _grade(
            0, points, [Deduction(points=points, reason="no answer", error_class="incomplete")], "deterministic", 1.0
        )
    result = verify(answer, spec)
    if result.verdict is Verdict.CORRECT:
        return _grade(points, points, [], "deterministic", 1.0)
    if result.verdict is Verdict.UNDETERMINED:
        # can't decide automatically: award nothing provisionally and ask the student to self-review
        return _grade(
            0,
            points,
            [Deduction(points=points, reason=f"could not verify automatically ({result.detail})")],
            "deterministic",
            0.0,
        )
    if result.verdict is Verdict.CLOSE:
        # a near-miss spelling earns half credit and is classified as notation
        return _grade(
            points / 2,
            points,
            [Deduction(points=points / 2, reason="close but not exact", error_class="notation")],
            "deterministic",
            0.8,
        )
    cls: ErrorClass = classify_numeric_miss(answer, spec) if isinstance(spec, NumericSpec) else "conceptual"
    return _grade(
        0,
        points,
        [Deduction(points=points, reason=result.detail or "incorrect", error_class=cls)],
        "deterministic",
        1.0,
    )


# ---------------------------------------------------------------- multi-step
class Step(_Frozen):
    spec: TextSpec | NumericSpec | SympySpec = Field(discriminator="check")
    points: float = Field(gt=0)


def grade_multi_step(answers: Sequence[str], steps: Sequence[Step]) -> AnswerGrade:
    """Each step is checked independently, so an early slip doesn't zero out later correct work."""
    if len(answers) > len(steps):
        raise ValueError("more answers than steps")
    padded = list(answers) + [""] * (len(steps) - len(answers))
    awarded = 0.0
    deductions: list[Deduction] = []
    confidence = 1.0
    for i, (ans, step) in enumerate(zip(padded, steps, strict=True)):
        g = grade_typed(ans, step.spec, step.points)
        awarded += g.awarded
        confidence = min(confidence, g.confidence)
        deductions.extend(d.model_copy(update={"step_index": i}) for d in g.deductions)
    total = sum(s.points for s in steps)
    return _grade(awarded, total, deductions, "deterministic", confidence)


# ---------------------------------------------------------------- rubric (LLM output validation)
class RubricCriterion(_Frozen):
    id: str
    description: str
    points: float = Field(gt=0)
    common_errors: tuple[str, ...] = ()


class Rubric(_Frozen):
    criteria: tuple[RubricCriterion, ...] = Field(min_length=1)

    @property
    def total_points(self) -> float:
        return sum(c.points for c in self.criteria)


class CriterionScore(_Frozen):
    criterion_id: str
    awarded: float = Field(ge=0)
    reason: str = ""
    error_class: ErrorClass | None = None
    citation: str | None = None


class LlmRubricOutput(_Frozen):
    """The structured output the rubric grader must return (validated with the model's JSON schema too)."""

    scores: tuple[CriterionScore, ...]
    confidence: float = Field(ge=0, le=1)


class RubricOutputError(ValueError):
    """The grader's output doesn't match the rubric; the caller retries once, then flags for review."""


def grade_with_rubric(output: LlmRubricOutput, rubric: Rubric, by: GradedBy = "llm") -> AnswerGrade:
    by_id = {c.id: c for c in rubric.criteria}
    seen = [s.criterion_id for s in output.scores]
    unknown = set(seen) - set(by_id)
    if unknown:
        raise RubricOutputError(f"unknown criteria: {sorted(unknown)}")
    if len(seen) != len(set(seen)):
        raise RubricOutputError("duplicate criteria in output")
    missing = set(by_id) - set(seen)
    if missing:
        raise RubricOutputError(f"missing criteria: {sorted(missing)}")

    awarded = 0.0
    deductions: list[Deduction] = []
    for s in output.scores:
        crit = by_id[s.criterion_id]
        if s.awarded > crit.points + 1e-9:
            raise RubricOutputError(f"criterion {crit.id} awarded {s.awarded} > {crit.points}")
        awarded += s.awarded
        lost = crit.points - s.awarded
        if lost > 1e-9:
            if s.error_class is None:
                raise RubricOutputError(f"criterion {crit.id} lost points without an error_class")
            deductions.append(
                Deduction(
                    points=round(lost, 4),
                    reason=s.reason or crit.description,
                    error_class=s.error_class,
                    criterion_id=crit.id,
                )
            )
    return _grade(awarded, rubric.total_points, deductions, by, output.confidence)


# ---------------------------------------------------------------- attempt totals + disputes
class AttemptScore(_Frozen):
    score: float
    max_score: float
    percent: float
    flagged_answers: int


def attempt_score(grades: Sequence[AnswerGrade]) -> AttemptScore:
    score = sum(g.awarded for g in grades)
    max_score = sum(g.max_points for g in grades)
    return AttemptScore(
        score=round(score, 4),
        max_score=max_score,
        percent=round(score / max_score, 6) if max_score else 0.0,
        flagged_answers=sum(g.flagged_for_review for g in grades),
    )


class RegradeOutcome(_Frozen):
    grade: AnswerGrade
    shift: float  # new − old, in points
    log_for_evals: bool


def apply_regrade(old: AnswerGrade, new: AnswerGrade) -> RegradeOutcome:
    """A dispute regrade replaces the old grade (marked user_dispute). Big swings are logged for grader evals."""
    if abs(new.max_points - old.max_points) > 1e-9:
        raise ValueError("regrade must be for the same question")
    final = new.model_copy(update={"graded_by": "user_dispute"})
    shift = new.awarded - old.awarded
    return RegradeOutcome(
        grade=final, shift=round(shift, 4), log_for_evals=abs(shift) > REGRADE_SHIFT_FLAG * old.max_points
    )

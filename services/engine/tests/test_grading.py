import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from engine.algorithms.grading import (
    AnswerGrade,
    CriterionScore,
    LlmRubricOutput,
    Rubric,
    RubricCriterion,
    RubricOutputError,
    Step,
    apply_regrade,
    attempt_score,
    grade_mcq,
    grade_multi_step,
    grade_typed,
    grade_with_rubric,
)
from engine.algorithms.verification import NumericSpec, SympySpec, TextSpec


# ---------------------------------------------------------------- MCQ
def test_mcq_single_answer_all_or_nothing() -> None:
    assert grade_mcq(["b"], ["b"], 2).awarded == 2
    wrong = grade_mcq(["a"], ["b"], 2)
    assert wrong.awarded == 0 and wrong.deductions[0].error_class == "conceptual"
    blank = grade_mcq([], ["b"], 2)
    assert blank.deductions[0].error_class == "incomplete"


def test_mcq_multi_select_partial_credit() -> None:
    assert grade_mcq(["a", "b"], ["a", "b", "c"], 3).awarded == pytest.approx(2)
    assert grade_mcq(["a", "b", "d"], ["a", "b", "c"], 3).awarded == pytest.approx(1)  # 2 right − 1 wrong
    assert grade_mcq(["d", "e"], ["a", "b"], 2).awarded == 0  # floored, never negative


@given(st.sets(st.sampled_from("abcdef")), st.sets(st.sampled_from("abcdef"), min_size=1))
def test_mcq_bounds(selected: set[str], correct: set[str]) -> None:
    g = grade_mcq(sorted(selected), sorted(correct), 4)
    assert 0 <= g.awarded <= 4


# ---------------------------------------------------------------- typed answers
def test_numeric_error_classification() -> None:
    spec = NumericSpec(expected="9.81 m/s^2")
    assert grade_typed("9.81 m/s^2", spec, 5).awarded == 5
    slip = grade_typed("9.5 m/s^2", spec, 5)  # 3% off, right units
    assert slip.awarded == 0 and slip.deductions[0].error_class == "calculation_slip"
    concept = grade_typed("9.81 m", spec, 5)
    assert concept.deductions[0].error_class == "conceptual"
    assert grade_typed("   ", spec, 5).deductions[0].error_class == "incomplete"


def test_close_text_gets_half_credit_and_undetermined_is_flagged() -> None:
    close = grade_typed("mitocondria", TextSpec(expected="mitochondria"), 4)
    assert close.awarded == 2 and close.deductions[0].error_class == "notation"
    undetermined = grade_typed(r"\frac{", SympySpec(expected_latex="1"), 4)
    assert undetermined.awarded == 0 and undetermined.flagged_for_review


def test_multi_step_independent_steps() -> None:
    steps = [
        Step(spec=SympySpec(expected_latex=r"2x"), points=3),
        Step(spec=NumericSpec(expected="6"), points=3),
        Step(spec=TextSpec(expected="minimum"), points=2),
    ]
    g = grade_multi_step([r"2x", "7", "minimum"], steps)
    assert g.awarded == 5 and g.max_points == 8
    assert [d.step_index for d in g.deductions] == [1]
    assert g.deductions[0].error_class == "conceptual"  # 7 vs 6 is > 5% off
    partial = grade_multi_step([r"2x"], steps)  # unanswered later steps count as incomplete
    assert partial.awarded == 3
    assert {d.error_class for d in partial.deductions} == {"incomplete"}


# ---------------------------------------------------------------- rubric validation
RUBRIC = Rubric(
    criteria=(
        RubricCriterion(id="setup", description="Sets up the integral", points=4),
        RubricCriterion(id="compute", description="Evaluates correctly", points=4),
        RubricCriterion(id="units", description="States units", points=2),
    )
)


def _output(*scores: tuple[str, float, str | None], confidence: float = 0.9) -> LlmRubricOutput:
    return LlmRubricOutput(
        scores=tuple(CriterionScore(criterion_id=c, awarded=a, error_class=e, reason="r") for c, a, e in scores),
        confidence=confidence,
    )


def test_rubric_partial_credit_and_deductions() -> None:
    g = grade_with_rubric(
        _output(("setup", 4, None), ("compute", 2.5, "calculation_slip"), ("units", 0, "incomplete")), RUBRIC
    )
    assert g.awarded == pytest.approx(6.5) and g.max_points == 10
    assert [(d.criterion_id, d.points, d.error_class) for d in g.deductions] == [
        ("compute", 1.5, "calculation_slip"),
        ("units", 2.0, "incomplete"),
    ]
    assert not g.flagged_for_review


def test_rubric_low_confidence_is_flagged() -> None:
    g = grade_with_rubric(_output(("setup", 4, None), ("compute", 4, None), ("units", 2, None), confidence=0.5), RUBRIC)
    assert g.flagged_for_review


@pytest.mark.parametrize(
    "scores",
    [
        (("setup", 5, None), ("compute", 4, None), ("units", 2, None)),  # over criterion max
        (("setup", 4, None), ("compute", 4, None)),  # missing criterion
        (("setup", 4, None), ("compute", 4, None), ("units", 2, None), ("bonus", 1, None)),  # unknown
        (("setup", 4, None), ("setup", 4, None), ("units", 2, None)),  # duplicate
        (("setup", 3, None), ("compute", 4, None), ("units", 2, None)),  # lost points without error class
    ],
)
def test_rubric_rejects_invalid_grader_output(scores: tuple[tuple[str, float, str | None], ...]) -> None:
    with pytest.raises(RubricOutputError):
        grade_with_rubric(_output(*scores), RUBRIC)


def test_llm_output_schema_rejects_bad_error_class() -> None:
    with pytest.raises(ValidationError):
        CriterionScore(criterion_id="x", awarded=1, error_class="typo")  # type: ignore[arg-type]


# ---------------------------------------------------------------- totals + disputes
def test_attempt_score_and_regrade() -> None:
    a = AnswerGrade(awarded=5, max_points=10, graded_by="llm", confidence=0.9)
    b = AnswerGrade(awarded=2, max_points=2, graded_by="deterministic", confidence=0.4, flagged_for_review=True)
    total = attempt_score([a, b])
    assert (total.score, total.max_score, total.flagged_answers) == (7, 12, 1)
    assert total.percent == pytest.approx(7 / 12)

    small = apply_regrade(a, AnswerGrade(awarded=6, max_points=10, graded_by="llm", confidence=0.9))
    assert small.grade.graded_by == "user_dispute" and small.shift == 1 and not small.log_for_evals
    big = apply_regrade(a, AnswerGrade(awarded=9, max_points=10, graded_by="llm", confidence=0.9))
    assert big.log_for_evals
    with pytest.raises(ValueError):
        apply_regrade(a, AnswerGrade(awarded=1, max_points=5, graded_by="llm", confidence=0.9))


def test_answer_grade_rejects_overflow() -> None:
    with pytest.raises(ValidationError):
        AnswerGrade(awarded=11, max_points=10, graded_by="llm", confidence=1)

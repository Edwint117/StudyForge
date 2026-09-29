import pytest
from pydantic import TypeAdapter, ValidationError

from engine.algorithms.verification import (
    AnswerSpec,
    NumericSpec,
    Rating,
    TextSpec,
    Verdict,
    check_numeric,
    check_sympy,
    check_text,
    levenshtein_ratio,
    normalize_text,
    propose_rating,
    verify,
)


# ---------------------------------------------------------------- text
def test_normalize_text() -> None:
    assert normalize_text("  The  Mitochondria! ") == "mitochondria"
    assert normalize_text("ﬁnite") == "finite"  # NFKC ligature


@pytest.mark.parametrize(
    ("answer", "expected", "alternates", "verdict"),
    [
        ("The mitochondria", "mitochondria", (), Verdict.CORRECT),
        ("mitocondria", "mitochondria", (), Verdict.CLOSE),
        ("ribosome", "mitochondria", (), Verdict.INCORRECT),
        ("powerhouse", "mitochondria", ("powerhouse of the cell", "powerhouse"), Verdict.CORRECT),
        ("   ", "mitochondria", (), Verdict.INCORRECT),
    ],
)
def test_check_text(answer: str, expected: str, alternates: tuple[str, ...], verdict: Verdict) -> None:
    assert check_text(answer, expected, alternates).verdict is verdict


def test_levenshtein_ratio() -> None:
    assert levenshtein_ratio("abc", "abc") == 1.0
    assert levenshtein_ratio("", "abc") == 0.0
    assert levenshtein_ratio("kitten", "sitting") == pytest.approx(1 - 3 / 7)


# ---------------------------------------------------------------- numeric
@pytest.mark.parametrize(
    ("answer", "expected", "verdict"),
    [
        ("9.81 m/s^2", "981 cm/s^2", Verdict.CORRECT),
        ("9.81 m", "9.81 s", Verdict.INCORRECT),  # wrong dimension
        ("3.14159", "3.1416", Verdict.CORRECT),  # within 1e-3 relative
        ("3.2", "3.1416", Verdict.INCORRECT),
        ("1,000 J", "1 kJ", Verdict.CORRECT),
        ("banana", "3", Verdict.INCORRECT),
    ],
)
def test_check_numeric(answer: str, expected: str, verdict: Verdict) -> None:
    assert check_numeric(answer, expected).verdict is verdict


def test_check_numeric_absolute_tolerance() -> None:
    assert check_numeric("10.4", "10", abs_tol=0.5).verdict is Verdict.CORRECT
    assert check_numeric("10.6", "10", abs_tol=0.5).verdict is Verdict.INCORRECT


# ---------------------------------------------------------------- sympy
@pytest.mark.parametrize(
    ("answer", "expected", "verdict"),
    [
        (r"\sin^2(x)+\cos^2(x)", "1", Verdict.CORRECT),
        (r"(x+1)^2", r"x^2+2x+1", Verdict.CORRECT),
        (r"(x+1)^2", r"x^2+1", Verdict.INCORRECT),
        (r"\frac{1}{x}", r"x^{-1}", Verdict.CORRECT),
        (r"\sqrt{x^2}", "x", Verdict.INCORRECT),  # |x|, not x
        (r"y=2x+1", r"2x+1=y", Verdict.CORRECT),
        (r"\frac{a}{b}+\frac{c}{b}", r"\frac{a+c}{b}", Verdict.CORRECT),
        (r"\frac{", "1", Verdict.UNDETERMINED),  # unparseable
    ],
)
def test_check_sympy(answer: str, expected: str, verdict: Verdict) -> None:
    assert check_sympy(answer, expected).verdict is verdict


def test_check_sympy_constants_without_symbols() -> None:
    assert check_sympy(r"\frac{6}{4}", r"1.5").verdict is Verdict.CORRECT
    assert check_sympy(r"\frac{6}{4}", r"1.6").verdict is Verdict.INCORRECT


# ---------------------------------------------------------------- specs + dispatch
def test_answer_spec_discriminated_union() -> None:
    adapter: TypeAdapter[TextSpec | NumericSpec] = TypeAdapter(AnswerSpec)
    spec = adapter.validate_python({"check": "numeric", "expected": "5 m"})
    assert isinstance(spec, NumericSpec)
    assert verify("500 cm", spec).verdict is Verdict.CORRECT
    with pytest.raises(ValidationError):
        adapter.validate_python({"check": "numeric", "expected": "5", "surprise": 1})  # extra fields rejected


# ---------------------------------------------------------------- proposed rating
@pytest.mark.parametrize(
    ("verdict", "ms", "median", "reps", "rating"),
    [
        (Verdict.INCORRECT, 1000, 10000, 5, Rating.AGAIN),
        (Verdict.CLOSE, 1000, 10000, 5, Rating.HARD),
        (Verdict.CORRECT, 25000, 10000, 5, Rating.HARD),
        (Verdict.CORRECT, 8000, 10000, 5, Rating.GOOD),
        (Verdict.CORRECT, 4000, 10000, 2, Rating.EASY),
        (Verdict.CORRECT, 4000, 10000, 1, Rating.GOOD),  # too few reps for Easy
        (Verdict.UNDETERMINED, 4000, 10000, 5, Rating.GOOD),
    ],
)
def test_propose_rating(verdict: Verdict, ms: int, median: int, reps: int, rating: Rating) -> None:
    assert propose_rating(verdict, ms, median, reps) is rating

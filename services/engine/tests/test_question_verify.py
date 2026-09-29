import pytest

from engine.algorithms.question_verify import QuestionVerification, next_action, verify_generated_question


@pytest.mark.parametrize(
    ("kind", "key", "a", "b", "verified"),
    [
        ("sympy", r"x^2+2x+1", r"(x+1)^2", r"(1+x)^2", True),  # equivalent forms all agree
        ("sympy", r"x^2+1", r"(x+1)^2", r"(x+1)^2", False),  # solvers agree, key is wrong -> flawed question
        ("numeric", "12 m", "1200 cm", "12 m", True),
        ("numeric", "12 m", "12 m", "13 m", False),  # solvers disagree
        ("text", "mitochondria", "the mitochondria", "Mitochondria", True),
        ("text", "mitochondria", "ribosome", "ribosome", False),
        ("numeric", "  ", "3", "3", False),  # empty key
    ],
)
def test_verify_generated_question(kind: str, key: str, a: str, b: str, verified: bool) -> None:
    assert verify_generated_question(kind, key, a, b).verified is verified  # type: ignore[arg-type]


def test_reasons_explain_failure() -> None:
    r = verify_generated_question("numeric", "12 m", "12 m", "13 m")
    assert "independent solves disagree" in r.reasons
    assert "solve B disagrees with the answer key" in r.reasons
    assert "solve A disagrees with the answer key" not in r.reasons


def test_code_questions_use_reference_run() -> None:
    assert verify_generated_question("code", "", "", "", code_reference_passed=True).verified
    assert not verify_generated_question("code", "", "", "", code_reference_passed=False).verified
    assert verify_generated_question("code", "", "", "").reasons == ("reference solution was not run",)


def test_retry_policy() -> None:
    ok = QuestionVerification(verified=True, reasons=())
    bad = QuestionVerification(verified=False, reasons=("x",))
    assert next_action(1, ok) == "accept"
    assert [next_action(n, bad) for n in (1, 2, 3)] == ["retry", "retry", "drop_slot"]

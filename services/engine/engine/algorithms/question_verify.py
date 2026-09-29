"""Verification gate for generated questions (DIAG-02; doc 05 §6; M8-03).

A generated question may only enter a mock exam when:
1. two **independent** solves (separate model contexts) agree with each other;
2. both agree with the generated answer key, checked with the same verifier students are graded by
   (text / unit-aware numeric / SymPy);
3. for code questions, the reference solution passes its tests in the sandbox.

The engine retries generation up to 3 times per slot; after that, the slot is dropped (``blueprint.drop_slot``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from engine.algorithms.verification import NumericSpec, SympySpec, TextSpec, Verdict, verify

VERSION = "qverify-1"
MAX_GENERATION_ATTEMPTS = 3

AnswerKind = Literal["text", "numeric", "sympy", "code"]


class QuestionVerification(BaseModel):
    model_config = ConfigDict(frozen=True)
    verified: bool
    reasons: tuple[str, ...]


def _spec(kind: AnswerKind, expected: str) -> TextSpec | NumericSpec | SympySpec:
    if kind == "numeric":
        return NumericSpec(expected=expected)
    if kind == "sympy":
        return SympySpec(expected_latex=expected)
    return TextSpec(expected=expected)


def _agrees(answer: str, expected: str, kind: AnswerKind) -> bool:
    return verify(answer, _spec(kind, expected)).verdict is Verdict.CORRECT


def verify_generated_question(
    kind: AnswerKind,
    answer_key: str,
    solve_a: str,
    solve_b: str,
    code_reference_passed: bool | None = None,
) -> QuestionVerification:
    reasons: list[str] = []
    if kind == "code":
        # code questions are verified by running the reference solution, not by comparing text answers
        if code_reference_passed is not True:
            reasons.append(
                "reference solution did not pass its tests"
                if code_reference_passed is False
                else "reference solution was not run"
            )
        return QuestionVerification(verified=not reasons, reasons=tuple(reasons))

    if not answer_key.strip():
        reasons.append("empty answer key")
    else:
        if not _agrees(solve_a, solve_b, kind):
            reasons.append("independent solves disagree")
        if not _agrees(solve_a, answer_key, kind):
            reasons.append("solve A disagrees with the answer key")
        if not _agrees(solve_b, answer_key, kind):
            reasons.append("solve B disagrees with the answer key")
    return QuestionVerification(verified=not reasons, reasons=tuple(reasons))


def next_action(attempt: int, result: QuestionVerification) -> Literal["accept", "retry", "drop_slot"]:
    """``attempt`` is 1-based. Accept verified questions; retry up to 3 attempts in total; then drop the slot."""
    if result.verified:
        return "accept"
    return "retry" if attempt < MAX_GENERATION_ATTEMPTS else "drop_slot"

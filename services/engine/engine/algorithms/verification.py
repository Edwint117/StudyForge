"""Answer verification (doc 05 §8) and the proposed self-grade.

Checks implemented here: ``text``, ``numeric`` (unit-aware) and ``sympy`` (math equivalence).
``code_tests`` (sandbox) and ``llm_keypoints`` (LLM gateway) are dispatched by the engine service to their own
adapters, and aren't handled in this pure module.

Math equivalence order (same verdicts as the spec, cheaper): parse both LaTeX answers → evaluate the difference at
up to 20 random points (fast and bounded). Any disagreement is definitively *incorrect*; full agreement is
*correct*. Only when too few sample points are usable (domain problems) does a symbolic ``simplify`` run, in a
killable worker process with a hard timeout (default 2 s). On timeout the verdict is ``undetermined``.
"""

from __future__ import annotations

import random
import re
import string
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from enum import StrEnum
from functools import lru_cache
from multiprocessing import get_context
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = "verify-1"


class Verdict(StrEnum):
    CORRECT = "correct"
    CLOSE = "close"
    INCORRECT = "incorrect"
    UNDETERMINED = "undetermined"


class Rating(StrEnum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class VerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    method: Literal["text", "numeric", "sympy", "numeric_sampling"]
    verdict: Verdict
    detail: str = ""


# ---------------------------------------------------------------- answer specs (cards.answer_spec)
class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextSpec(_Spec):
    check: Literal["text"] = "text"
    expected: str
    alternates: tuple[str, ...] = ()


class NumericSpec(_Spec):
    check: Literal["numeric"] = "numeric"
    expected: str  # e.g. "9.81 m/s^2" or "42"
    rel_tol: float = Field(default=1e-3, ge=0)
    abs_tol: float | None = Field(default=None, ge=0)


class SympySpec(_Spec):
    check: Literal["sympy"] = "sympy"
    expected_latex: str
    timeout_s: float = Field(default=2.0, gt=0, le=10)


AnswerSpec = Annotated[TextSpec | NumericSpec | SympySpec, Field(discriminator="check")]


def verify(answer: str, spec: TextSpec | NumericSpec | SympySpec) -> VerificationResult:
    if isinstance(spec, TextSpec):
        return check_text(answer, spec.expected, spec.alternates)
    if isinstance(spec, NumericSpec):
        return check_numeric(answer, spec.expected, spec.rel_tol, spec.abs_tol)
    return check_sympy(answer, spec.expected_latex, spec.timeout_s)


# ---------------------------------------------------------------- text
_ARTICLES = re.compile(r"\b(a|an|the)\b")
_PUNCT = str.maketrans({c: " " for c in string.punctuation})


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold().translate(_PUNCT)
    s = _ARTICLES.sub(" ", s)
    return " ".join(s.split())


def levenshtein_ratio(a: str, b: str) -> float:
    """1 − distance / max(len). 1.0 for identical strings (including two empty ones)."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))


def check_text(answer: str, expected: str, alternates: tuple[str, ...] = ()) -> VerificationResult:
    got = normalize_text(answer)
    if not got:
        return VerificationResult(method="text", verdict=Verdict.INCORRECT, detail="empty answer")
    targets = [normalize_text(t) for t in (expected, *alternates)]
    if got in targets:
        return VerificationResult(method="text", verdict=Verdict.CORRECT)
    best = max(levenshtein_ratio(got, t) for t in targets)
    if best >= 0.9:
        return VerificationResult(method="text", verdict=Verdict.CLOSE, detail=f"similarity {best:.2f}")
    return VerificationResult(method="text", verdict=Verdict.INCORRECT, detail=f"similarity {best:.2f}")


# ---------------------------------------------------------------- numeric (pint)
@lru_cache(maxsize=1)
def _ureg() -> Any:
    import pint

    return pint.UnitRegistry(autoconvert_offset_to_baseunit=True)


def _parse_quantity(s: str) -> Any:
    cleaned = s.strip().replace("×", "*").replace("·", "*").replace("^", "**").replace(",", "")
    q = _ureg().Quantity(cleaned)
    return q if hasattr(q, "magnitude") else _ureg().Quantity(float(q))


def check_numeric(
    answer: str, expected: str, rel_tol: float = 1e-3, abs_tol: float | None = None
) -> VerificationResult:
    try:
        got, want = _parse_quantity(answer), _parse_quantity(expected)
    except Exception as exc:  # pint raises many error types for bad input
        return VerificationResult(
            method="numeric", verdict=Verdict.INCORRECT, detail=f"unparseable: {type(exc).__name__}"
        )
    if got.dimensionality != want.dimensionality:
        return VerificationResult(method="numeric", verdict=Verdict.INCORRECT, detail="wrong units/dimension")
    g = float(got.to(want.units).magnitude)
    w = float(want.magnitude)
    diff = abs(g - w)
    ok = diff <= abs_tol if abs_tol is not None else diff <= rel_tol * max(abs(w), 1e-12)
    return VerificationResult(
        method="numeric", verdict=Verdict.CORRECT if ok else Verdict.INCORRECT, detail=f"abs diff={diff:.6g}"
    )


# ---------------------------------------------------------------- sympy
def _parse_latex(src: str) -> Any:
    """SymPy's ANTLR LaTeX parser (mature), falling back to the Lark backend. Must yield a SymPy expression."""
    from sympy import Basic
    from sympy.parsing.latex import parse_latex

    last: Exception | None = None
    for backend in ("antlr", "lark"):
        try:
            expr = parse_latex(src, backend=backend)
        except Exception as exc:  # parser-specific error types
            last = exc
            continue
        if isinstance(expr, Basic):
            return expr
    raise ValueError(f"not a parseable math expression ({type(last).__name__ if last else 'ambiguous'})")


def _as_difference(a: Any, b: Any) -> list[Any]:
    """Expressions whose vanishing means a ≡ b. Equations compare lhs−rhs up to sign."""
    from sympy import Eq

    if isinstance(a, Eq) and isinstance(b, Eq):
        da, db = a.lhs - a.rhs, b.lhs - b.rhs
        return [da - db, da + db]
    return [a - b]


def _sample_values(expr: Any, symbols: list[Any], rng: random.Random, n: int = 20) -> list[complex]:
    out: list[complex] = []
    for _ in range(n * 3):
        if len(out) >= n:
            break
        point = {s: rng.choice((-1, 1)) * rng.uniform(0.1, 3.0) for s in symbols}
        try:
            v = complex(expr.subs(point).evalf())
        except (TypeError, ValueError, ZeroDivisionError, OverflowError):
            continue
        if v != v or abs(v) == float("inf"):  # NaN / inf
            continue
        out.append(v)
    return out


def _symbolic_zero(srepr_expr: str) -> bool:
    """Runs in a worker process. True if simplify proves the expression is zero."""
    import sympy

    return bool(sympy.simplify(sympy.sympify(srepr_expr)) == 0)


_pool: ProcessPoolExecutor | None = None


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn"))
    return _pool


def _kill_pool() -> None:
    global _pool
    if _pool is not None:
        for proc in list(getattr(_pool, "_processes", {}).values()):
            proc.terminate()
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def _symbolic_zero_with_timeout(expr: Any, timeout_s: float) -> bool | None:
    import sympy

    future = _get_pool().submit(_symbolic_zero, sympy.srepr(expr))
    try:
        return future.result(timeout=timeout_s)
    except FutureTimeout:
        _kill_pool()
        return None
    except Exception:
        return None


def check_sympy(answer_latex: str, expected_latex: str, timeout_s: float = 2.0) -> VerificationResult:
    try:
        a, b = _parse_latex(answer_latex), _parse_latex(expected_latex)
    except Exception as exc:
        return VerificationResult(
            method="sympy", verdict=Verdict.UNDETERMINED, detail=f"parse error: {type(exc).__name__}"
        )

    candidates = _as_difference(a, b)
    rng = random.Random(1729)  # deterministic sampling  # noqa: S311 - not security sensitive
    inconclusive: list[Any] = []
    for diff in candidates:
        symbols = sorted(diff.free_symbols, key=lambda s: s.name)
        values = _sample_values(diff, symbols, rng)
        if len(values) >= 5:
            if all(abs(v) <= 1e-9 * max(1.0, abs(v)) for v in values):
                return VerificationResult(
                    method="numeric_sampling", verdict=Verdict.CORRECT, detail=f"{len(values)} points agree"
                )
            continue  # this candidate definitely differs; try the next (e.g. sign-flipped equation)
        inconclusive.append(diff)

    for diff in inconclusive:
        proved = _symbolic_zero_with_timeout(diff, timeout_s)
        if proved:
            return VerificationResult(method="sympy", verdict=Verdict.CORRECT, detail="simplify proved equality")
        if proved is None:
            return VerificationResult(method="sympy", verdict=Verdict.UNDETERMINED, detail="timeout or error")
    if inconclusive:
        return VerificationResult(method="sympy", verdict=Verdict.UNDETERMINED, detail="could not prove or refute")
    return VerificationResult(method="numeric_sampling", verdict=Verdict.INCORRECT, detail="values differ")


# ---------------------------------------------------------------- proposed rating (SRS-03)
def propose_rating(verdict: Verdict, response_ms: int, median_ms: int, reps: int) -> Rating:
    """incorrect → Again; correct but slow (>2× median) or 'close' → Hard; correct → Good;
    correct, fast (<0.5× median) and reps ≥ 2 → Easy. Undetermined falls back to Good (student self-grades)."""
    median = max(median_ms, 1)
    if verdict is Verdict.INCORRECT:
        return Rating.AGAIN
    if verdict is Verdict.CLOSE or (verdict is Verdict.CORRECT and response_ms > 2 * median):
        return Rating.HARD
    if verdict is Verdict.CORRECT and response_ms < 0.5 * median and reps >= 2:
        return Rating.EASY
    return Rating.GOOD

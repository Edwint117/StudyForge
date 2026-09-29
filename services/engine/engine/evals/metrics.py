"""Eval metrics and the doc 06 §7 gates. Suites produce these numbers; ``check_gates`` decides pass/fail for CI.

Every metric is deterministic and dependency-free so the fast subset can run in ``pnpm verify``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from engine.ingest.graph import normalize_name

VERSION = "evals-1"


class PRF(BaseModel):
    model_config = ConfigDict(frozen=True)
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


def prf(predicted: Iterable[Hashable], gold: Iterable[Hashable]) -> PRF:
    p, g = set(predicted), set(gold)
    tp, fp, fn = len(p & g), len(p - g), len(g - p)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not g else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return PRF(precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn)


# ---------------------------------------------------------------- syllabus_extract
def syllabus_field_f1(
    predicted: Sequence[Mapping[str, object]], gold: Sequence[Mapping[str, object]], field: str
) -> PRF:
    """F1 over (exam kind, field value) facts, e.g. field="date" or "weight_pct". Exams are matched by kind+value,
    so order doesn't matter and a wrong date counts as both a false positive and a false negative."""

    def facts(items: Sequence[Mapping[str, object]]) -> set[tuple[str, str]]:
        out = set()
        for e in items:
            v = e.get(field)
            if v is not None:
                out.add((str(e.get("kind", "")), f"{float(v):g}" if isinstance(v, int | float) else str(v)))
        return out

    return prf(facts(predicted), facts(gold))


# ---------------------------------------------------------------- concept_extract
def concept_prf(predicted_names: Iterable[str], gold_names: Iterable[str]) -> PRF:
    return prf({normalize_name(n) for n in predicted_names}, {normalize_name(n) for n in gold_names})


# ---------------------------------------------------------------- grading
def grading_mae_fraction(pairs: Sequence[tuple[float, float, float]]) -> float:
    """Mean |predicted − human| / max_points over (predicted, human, max_points) triples."""
    if not pairs:
        raise ValueError("no graded answers")
    return sum(abs(p - h) / m for p, h, m in pairs) / len(pairs)


def error_class_accuracy(pairs: Sequence[tuple[str | None, str | None]]) -> float:
    if not pairs:
        raise ValueError("no labelled deductions")
    return sum(p == g for p, g in pairs) / len(pairs)


# ---------------------------------------------------------------- tutor_socratic
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return " ".join(re.findall(r"[\w.]+", s))


def leaks_answer(response: str, final_answer: str) -> bool:
    """True if the tutor's response states the final answer it should have withheld (whole-token match)."""
    ans = _norm(final_answer)
    # boundaries: not inside a longer word/number ("3" in "13" or "3.5"), but a sentence period after is fine
    pattern = rf"(?<!\w)(?<!\d\.){re.escape(ans)}(?!\w)(?!\.\d)"
    return bool(ans) and re.search(pattern, _norm(response)) is not None


def leak_rate(cases: Sequence[tuple[str, str]]) -> float:
    return sum(leaks_answer(r, a) for r, a in cases) / len(cases) if cases else 0.0


def citation_validity(valid: int, invalid: int) -> float:
    total = valid + invalid
    return valid / total if total else 1.0


# ---------------------------------------------------------------- ocr / stt
def _edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def cer(hypothesis: str, reference: str) -> float:
    ref = list(" ".join(reference.split()))
    return _edit_distance(list(" ".join(hypothesis.split())), ref) / max(1, len(ref))


def wer(hypothesis: str, reference: str) -> float:
    ref = _norm(reference).split()
    return _edit_distance(_norm(hypothesis).split(), ref) / max(1, len(ref))


# ---------------------------------------------------------------- gates (doc 06 §7)
Op = Literal[">=", "<=", "=="]


class Gate(BaseModel):
    model_config = ConfigDict(frozen=True)
    suite: str
    metric: str
    op: Op
    threshold: float


GATES: tuple[Gate, ...] = (
    Gate(suite="syllabus_extract", metric="date_f1", op=">=", threshold=0.95),
    Gate(suite="syllabus_extract", metric="weight_f1", op=">=", threshold=0.90),
    Gate(suite="concept_extract", metric="precision", op=">=", threshold=0.80),
    Gate(suite="concept_extract", metric="recall", op=">=", threshold=0.70),
    Gate(suite="cards_quality", metric="pass_rate", op=">=", threshold=0.90),
    Gate(suite="tutor_socratic", metric="leak_rate", op="==", threshold=0.0),
    Gate(suite="tutor_socratic", metric="citation_validity", op=">=", threshold=0.95),
    Gate(suite="grading", metric="mae_fraction", op="<=", threshold=0.10),
    Gate(suite="grading", metric="error_class_accuracy", op=">=", threshold=0.80),
    Gate(suite="feynman", metric="gap_recall", op=">=", threshold=0.75),
    Gate(suite="question_verify", metric="flawed_catch_rate", op=">=", threshold=0.90),
    Gate(suite="injection", metric="pass_rate", op="==", threshold=1.0),
)


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    gate: Gate
    value: float | None
    passed: bool


def check_gates(results: Mapping[str, Mapping[str, float]], suites: Iterable[str] | None = None) -> list[GateResult]:
    """Evaluate the gates for the given suites (default: every suite present in ``results``). A gate whose metric is
    missing fails, so a suite can't pass by forgetting to report something."""
    wanted = set(suites) if suites is not None else set(results)
    out = []
    for g in GATES:
        if g.suite not in wanted:
            continue
        v = results.get(g.suite, {}).get(g.metric)
        ok = v is not None and (
            (g.op == ">=" and v >= g.threshold)
            or (g.op == "<=" and v <= g.threshold)
            or (g.op == "==" and abs(v - g.threshold) < 1e-12)
        )
        out.append(GateResult(gate=g, value=v, passed=ok))
    return out

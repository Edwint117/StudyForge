"""Deterministic flashcard quality lint and near-duplicate detection (COMP-02).

Runs on every generated or edited card before it's shown in the draft queue. Errors block acceptance until fixed;
warnings are shown next to the card. The cheap LLM lint pass (``cards.lint``) handles fuzzier issues. Duplicates:
a cheap word-shingle check before embeddings, then cosine similarity > 0.92 on embeddings.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

VERSION = "card-lint-1"

CardType = Literal["basic", "reversed", "cloze", "concept_map", "math_step", "code", "free_explain"]

MAX_FRONT_CHARS = 350
MAX_BACK_CHARS = 500
MAX_CLOZE_COVERAGE = 0.5
EMBEDDING_DUP_THRESHOLD = 0.92
SHINGLE_DUP_THRESHOLD = 0.8

_CLOZE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.DOTALL)
_YES_NO_START = re.compile(r"^\s*(is|are|was|were|does|do|did|can|could|will|would|should|has|have)\b", re.I)
_VAGUE_START = re.compile(r"^\s*(it|this|that|they|these|those|he|she)\b", re.I)
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.M)
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


class Card(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: CardType
    front_md: str = ""
    back_md: str = ""
    cloze_md: str = ""


class LintIssue(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    severity: Literal["error", "warning"]
    message: str


class LintResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    issues: tuple[LintIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"[`*_#>$\\{}()\[\]]", " ", s)
    return " ".join(re.findall(r"[\w']+", s))


def _latex_balanced(s: str) -> bool:
    text = s.replace(r"\$", "")
    if text.count("$") % 2:
        return False
    if text.count(r"\(") != text.count(r"\)") or text.count(r"\[") != text.count(r"\]"):
        return False
    depth = 0
    for ch in re.sub(r"\\[{}]", "", text):
        depth += (ch == "{") - (ch == "}")
        if depth < 0:
            return False
    return depth == 0


def _lint_cloze(text: str, out: list[LintIssue]) -> None:
    matches = list(_CLOZE.finditer(text))
    if not matches:
        out.append(
            LintIssue(code="cloze_missing_marker", severity="error", message="cloze card has no {{c1::...}} deletion")
        )
        return
    stripped = _CLOZE.sub("", text)
    if "{{" in stripped or "}}" in stripped:
        out.append(LintIssue(code="cloze_malformed", severity="error", message="unbalanced or nested cloze markers"))
    numbers = sorted({int(m.group(1)) for m in matches})
    if numbers != list(range(1, numbers[-1] + 1)):
        out.append(
            LintIssue(code="cloze_numbering_gap", severity="warning", message=f"cloze numbers {numbers} skip values")
        )
    hidden = sum(len(m.group(2)) for m in matches)
    visible = len(_CLOZE.sub(lambda m: m.group(2), text))
    if visible and hidden / visible > MAX_CLOZE_COVERAGE:
        out.append(LintIssue(code="cloze_too_much", severity="warning", message="more than half the text is hidden"))
    rest = _norm(_CLOZE.sub(" ", text))
    for m in matches:
        answer = _norm(m.group(2))
        if len(answer) >= 3 and re.search(rf"\b{re.escape(answer)}\b", rest):
            out.append(
                LintIssue(
                    code="answer_leak", severity="error", message=f"deleted text {m.group(2)!r} appears elsewhere"
                )
            )
            break


def lint_card(card: Card) -> LintResult:
    issues: list[LintIssue] = []

    if card.type == "cloze":
        if not card.cloze_md.strip():
            issues.append(LintIssue(code="empty_front", severity="error", message="cloze text is empty"))
        else:
            _lint_cloze(card.cloze_md, issues)
    else:
        if not card.front_md.strip():
            issues.append(LintIssue(code="empty_front", severity="error", message="front is empty"))
        if not card.back_md.strip():
            issues.append(LintIssue(code="empty_back", severity="error", message="back is empty"))
        front, back = _norm(card.front_md), _norm(card.back_md)
        if (
            len(back) >= 3
            and back not in {"yes", "no", "true", "false"}
            and re.search(rf"\b{re.escape(back)}\b", front)
        ):
            issues.append(LintIssue(code="answer_leak", severity="error", message="the answer appears in the prompt"))
        if len(card.front_md) > MAX_FRONT_CHARS:
            issues.append(
                LintIssue(
                    code="front_too_long", severity="warning", message=f"prompt over {MAX_FRONT_CHARS} characters"
                )
            )
        if len(card.back_md) > MAX_BACK_CHARS:
            issues.append(
                LintIssue(code="back_too_long", severity="warning", message="answer is long; aim for one fact per card")
            )
        facts = max(len(_LIST_ITEM.findall(card.back_md)), len(_SENTENCE_END.findall(card.back_md)))
        if facts >= 3:
            issues.append(
                LintIssue(
                    code="multiple_facts", severity="warning", message="answer holds several facts; consider splitting"
                )
            )
        if _YES_NO_START.match(card.front_md) and back in {"yes", "no", "true", "false"}:
            issues.append(LintIssue(code="yes_no", severity="warning", message="yes/no cards have low retrieval value"))
        if _VAGUE_START.match(card.front_md):
            issues.append(
                LintIssue(code="ambiguous_prompt", severity="warning", message="prompt starts with a vague pronoun")
            )
        if card.type == "code" and "```" not in card.front_md + card.back_md:
            issues.append(
                LintIssue(code="code_missing_block", severity="warning", message="code card has no code block")
            )

    for side, text in (("front", card.front_md), ("back", card.back_md), ("cloze", card.cloze_md)):
        if text and not _latex_balanced(text):
            issues.append(
                LintIssue(code="latex_unbalanced", severity="error", message=f"unbalanced LaTeX delimiters in {side}")
            )
    return LintResult(issues=tuple(issues))


# ---------------------------------------------------------------- near-duplicates
def shingles(text: str, k: int = 3) -> set[tuple[str, ...]]:
    words = _norm(text).split()
    if len(words) < k:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vectors differ in dimension")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def text_duplicates(prompt: str, existing: Iterable[tuple[str, str]]) -> list[str]:
    """Cheap pre-check before embeddings: ids of existing cards whose prompt shares ≥ 80% of word 3-grams."""
    mine = shingles(prompt)
    return [cid for cid, other in existing if jaccard(mine, shingles(other)) >= SHINGLE_DUP_THRESHOLD]


def embedding_duplicates(
    vector: Sequence[float], existing: Iterable[tuple[str, Sequence[float]]], threshold: float = EMBEDDING_DUP_THRESHOLD
) -> list[tuple[str, float]]:
    """Existing cards with cosine similarity above the threshold, most similar first (flag ``duplicate_suspect``)."""
    hits = [(cid, cosine(vector, v)) for cid, v in existing]
    return sorted(((cid, s) for cid, s in hits if s > threshold), key=lambda h: (-h[1], h[0]))

"""Feynman-mode analysis: validate the model's structured output and score it deterministically (COMP-03).

The engine sends the student's explanation plus the concept's source-grounded key points (with ids and weights)
to Sonnet. The model returns which points are covered, missing steps, jargon used without explanation, incorrect
statements (with citations) and follow-up questions. This module:

* rejects outputs that don't match the key-point set or cite chunks that weren't provided;
* **downgrades** any "covered" claim whose evidence quote isn't actually in the student's text (no hallucinated
  credit);
* computes the score in code: weighted coverage − 0.10 per incorrect statement − 0.05 per unexplained term
  (term penalty capped at 0.20), clamped to [0, 1];
* turns missed key points into draft ``free_explain`` cards.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

VERSION = "feynman-1"
ERROR_PENALTY = 0.10
TERM_PENALTY = 0.05
TERM_PENALTY_CAP = 0.20


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class KeyPoint(_Frozen):
    id: str
    prompt: str  # question form, used for cards ("Why does Bayes' theorem need P(B) > 0?")
    text: str  # the fact itself
    weight: float = Field(default=1.0, gt=0)
    source_chunk_ids: tuple[str, ...] = ()


class PointJudgement(_Frozen):
    key_point_id: str
    covered: bool
    evidence_quote: str | None = None  # the student's words showing coverage


class TermUse(_Frozen):
    term: str
    explained: bool


class IncorrectStatement(_Frozen):
    claim: str
    correction: str
    citation: str  # chunk id


class FeynmanOutput(_Frozen):
    judgements: tuple[PointJudgement, ...]
    missing_steps: tuple[str, ...] = ()
    terms: tuple[TermUse, ...] = ()
    errors: tuple[IncorrectStatement, ...] = ()
    followups: tuple[str, ...] = ()


class FeynmanOutputError(ValueError):
    """Output doesn't match the request; retry once, then show 'analysis unavailable'."""


class FeynmanResult(_Frozen):
    score: float
    coverage: float
    covered: tuple[str, ...]
    missing: tuple[str, ...]
    unexplained_terms: tuple[str, ...]
    errors: tuple[IncorrectStatement, ...]
    missing_steps: tuple[str, ...]
    followups: tuple[str, ...]
    downgraded: int  # "covered" claims rejected because the quote wasn't in the explanation


class CardDraft(_Frozen):
    type: str = "free_explain"
    front_md: str
    back_md: str
    answer_keypoints: tuple[str, ...]
    source_chunk_ids: tuple[str, ...]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return " ".join(re.findall(r"[\w']+", s))


def analyze(
    explanation: str, key_points: Sequence[KeyPoint], output: FeynmanOutput, provided_chunk_ids: Iterable[str]
) -> FeynmanResult:
    by_id = {k.id: k for k in key_points}
    ids = [j.key_point_id for j in output.judgements]
    if len(ids) != len(set(ids)) or set(ids) != set(by_id):
        raise FeynmanOutputError("judgements must cover each key point exactly once")
    allowed = set(provided_chunk_ids)
    bad = [e.citation for e in output.errors if e.citation not in allowed]
    if bad:
        raise FeynmanOutputError(f"citations not in the provided sources: {bad}")

    text = _norm(explanation)
    covered: list[str] = []
    downgraded = 0
    for j in output.judgements:
        if not j.covered:
            continue
        quote = _norm(j.evidence_quote or "")
        if quote and quote in text:
            covered.append(j.key_point_id)
        else:
            downgraded += 1

    total_w = sum(k.weight for k in key_points)
    coverage = sum(by_id[c].weight for c in covered) / total_w if total_w else 0.0
    unexplained = tuple(dict.fromkeys(t.term for t in output.terms if not t.explained))
    penalty = ERROR_PENALTY * len(output.errors) + min(TERM_PENALTY_CAP, TERM_PENALTY * len(unexplained))
    order = [k.id for k in key_points]
    return FeynmanResult(
        score=round(max(0.0, min(1.0, coverage - penalty)), 4),
        coverage=round(coverage, 4),
        covered=tuple(i for i in order if i in covered),
        missing=tuple(i for i in order if i not in covered),
        unexplained_terms=unexplained,
        errors=output.errors,
        missing_steps=output.missing_steps,
        followups=output.followups,
        downgraded=downgraded,
    )


def gaps_to_cards(result: FeynmanResult, key_points: Sequence[KeyPoint]) -> list[CardDraft]:
    """One draft card per missed key point (student clicks 'make cards from gaps'); they go through card lint."""
    by_id = {k.id: k for k in key_points}
    return [
        CardDraft(
            front_md=by_id[i].prompt,
            back_md=by_id[i].text,
            answer_keypoints=(by_id[i].text,),
            source_chunk_ids=by_id[i].source_chunk_ids,
        )
        for i in result.missing
    ]

"""Exam-day triage: high-yield cram queue and rapid-fire warm-up (doc 05 §7; EXAM-01/02).

Pure selection logic. Callers pass the exam's units, cards and bank questions; persistence, the T-48h / T-6h
availability windows and "warm-up never updates FSRS state" are enforced by the service/database layer.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.algorithms.fsrs_math import DEFAULT_DECAY, retrievability

VERSION = "examday-1"

CRAM_WEIGHT_COVERAGE = 0.80
CRAM_MASTERY_THRESHOLD = 0.80
CRAM_R_EXAM_THRESHOLD = 0.90
CRAM_QUESTIONS_PER_UNIT = 2
HIGH_YIELD_KINDS = frozenset({"definition", "formula"})
HIGH_YIELD_MULTIPLIER = 1.2

WARMUP_ITEMS = 25
WARMUP_MINUTES = 15
WARMUP_R_BAND = (0.75, 0.97)
WARMUP_EASY_FIRST = 3

CardKind = Literal["definition", "formula", "theorem", "example", "code", "text", "other"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExamUnit(_Frozen):
    unit_id: str
    weight: float = Field(ge=0)  # syllabus weight, any scale
    mastery: float | None = Field(default=None, ge=0, le=1)  # None = not started (treated as 0)


class ExamCard(_Frozen):
    card_id: str
    unit_id: str
    kind: CardKind = "other"
    stability: float | None = Field(default=None, gt=0)  # None = never reviewed
    last_review: datetime | None = None
    recent_lapses: int = Field(default=0, ge=0)


class BankQuestion(_Frozen):
    question_id: str
    unit_id: str
    attempts: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)


class CramItem(_Frozen):
    unit_id: str
    priority: float
    card_ids: tuple[str, ...]
    question_ids: tuple[str, ...]
    cheat_sheet_unit_id: str


def _days(delta: timedelta) -> float:
    return delta / timedelta(days=1)


def retrievability_at(card: ExamCard, when: datetime, decay: float = DEFAULT_DECAY) -> float:
    """R at ``when``; never-reviewed cards count as 0 (nothing to retrieve yet)."""
    if card.stability is None or card.last_review is None:
        return 0.0
    return retrievability(max(0.0, _days(when - card.last_review)), card.stability, decay)


def crunch_priority(card: ExamCard, card_weight: float, r_exam: float) -> float:
    """w_c · (1 − R_exam) · (1 + 0.5·recent_lapses) · yield.

    Must stay in sync with the TS crunch scheduler (doc 05 §2); covered by the M7 parity test.
    """
    yield_factor = HIGH_YIELD_MULTIPLIER if card.kind in HIGH_YIELD_KINDS else 1.0
    return card_weight * (1.0 - r_exam) * (1.0 + 0.5 * card.recent_lapses) * yield_factor


def select_cram_units(units: Sequence[ExamUnit]) -> list[tuple[ExamUnit, float]]:
    """Top units covering ≥80% of exam weight, keeping mastery < 0.8, ordered by w_u·(0.8 − mastery_u)."""
    total = sum(u.weight for u in units)
    if total <= 0:
        return []
    covered: list[ExamUnit] = []
    cumulative = 0.0
    for u in sorted(units, key=lambda u: (-u.weight, u.unit_id)):
        if cumulative >= CRAM_WEIGHT_COVERAGE:
            break
        covered.append(u)
        cumulative += u.weight / total
    scored = [
        (u, (u.weight / total) * (CRAM_MASTERY_THRESHOLD - (u.mastery or 0.0)))
        for u in covered
        if (u.mastery or 0.0) < CRAM_MASTERY_THRESHOLD
    ]
    return sorted(scored, key=lambda pair: (-pair[1], pair[0].unit_id))


def _hardest_questions(questions: Sequence[BankQuestion]) -> tuple[str, ...]:
    attempted = [q for q in questions if q.attempts > 0]
    pool = attempted or list(questions)
    ranked = sorted(
        pool,
        key=lambda q: (-(q.failures / q.attempts) if q.attempts else 0.0, -q.attempts, q.question_id),
    )
    return tuple(q.question_id for q in ranked[:CRAM_QUESTIONS_PER_UNIT])


def cram_queue(
    exam_start: datetime,
    units: Sequence[ExamUnit],
    cards: Sequence[ExamCard],
    questions: Sequence[BankQuestion] = (),
    decay: float = DEFAULT_DECAY,
) -> list[CramItem]:
    """High-yield cram queue (EXAM-01). Cards per unit: R at exam time < 0.9, ordered by crunch priority."""
    total = sum(u.weight for u in units) or 1.0
    cards_by_unit: dict[str, list[ExamCard]] = defaultdict(list)
    for c in cards:
        cards_by_unit[c.unit_id].append(c)
    questions_by_unit: dict[str, list[BankQuestion]] = defaultdict(list)
    for q in questions:
        questions_by_unit[q.unit_id].append(q)

    items: list[CramItem] = []
    for unit, priority in select_cram_units(units):
        unit_cards = cards_by_unit.get(unit.unit_id, [])
        card_weight = (unit.weight / total) / max(1, len(unit_cards))
        ranked: list[tuple[float, str]] = []
        for c in unit_cards:
            r_exam = retrievability_at(c, exam_start, decay)
            if r_exam < CRAM_R_EXAM_THRESHOLD:
                ranked.append((crunch_priority(c, card_weight, r_exam), c.card_id))
        ranked.sort(key=lambda pc: (-pc[0], pc[1]))
        items.append(
            CramItem(
                unit_id=unit.unit_id,
                priority=priority,
                card_ids=tuple(cid for _, cid in ranked),
                question_ids=_hardest_questions(questions_by_unit.get(unit.unit_id, [])),
                cheat_sheet_unit_id=unit.unit_id,
            )
        )
    return items


# ---------------------------------------------------------------- warm-up
def _interleave(items: list[tuple[ExamCard, float]], previous_unit: str | None) -> list[tuple[ExamCard, float]]:
    """Greedy interleave: never repeat the previous unit when another unit has items; prefer the unit with the
    most remaining items (keeps later steps interleavable). Within a unit: highest R first, then card id."""
    groups: dict[str, list[tuple[ExamCard, float]]] = defaultdict(list)
    for card, r in sorted(items, key=lambda cr: (-cr[1], cr[0].card_id)):
        groups[card.unit_id].append((card, r))
    out: list[tuple[ExamCard, float]] = []
    prev = previous_unit
    while any(groups.values()):
        options = [u for u, g in groups.items() if g and u != prev] or [u for u, g in groups.items() if g]
        unit = min(options, key=lambda u: (-len(groups[u]), u))
        out.append(groups[unit].pop(0))
        prev = unit
    return out


def warmup_selection(
    now: datetime,
    cards: Sequence[ExamCard],
    count: int = WARMUP_ITEMS,
    decay: float = DEFAULT_DECAY,
) -> list[str]:
    """Rapid-fire warm-up (EXAM-02): definition/formula cards with 0.75 ≤ R(now) ≤ 0.97, the 3 easiest first,
    the rest interleaved by unit. If fewer than ``count`` qualify, it fills with reviewed definition/formula cards
    closest to the band. Never-reviewed cards are never used (a warm-up should be successful retrieval)."""
    lo, hi = WARMUP_R_BAND
    eligible = [
        (c, retrievability_at(c, now, decay))
        for c in cards
        if c.kind in HIGH_YIELD_KINDS and c.stability is not None and c.last_review is not None
    ]
    in_band = [(c, r) for c, r in eligible if lo <= r <= hi]
    out_band = sorted(
        ((c, r) for c, r in eligible if not lo <= r <= hi),
        key=lambda cr: (min(abs(cr[1] - lo), abs(cr[1] - hi)), cr[0].card_id),
    )

    in_band.sort(key=lambda cr: (-cr[1], cr[0].card_id))
    chosen_in_band = in_band[:count]
    fill = out_band[: max(0, count - len(chosen_in_band))]

    easy = chosen_in_band[:WARMUP_EASY_FIRST]
    rest = chosen_in_band[WARMUP_EASY_FIRST:] + fill
    ordered = easy + _interleave(rest, easy[-1][0].unit_id if easy else None)
    return [c.card_id for c, _ in ordered]

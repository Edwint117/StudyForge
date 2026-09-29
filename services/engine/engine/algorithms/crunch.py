"""Exam-crunch mode (doc 05 §2; SRS-04): reference implementation for the TypeScript online review path.

``packages/core`` owns the live scheduler. This module is the exact reference it must match (M7 parity test):
crunch applicability, the capped next interval, the single pre-exam confidence touch, the cram-window hand-off
and the daily priority queue. It reuses ``fsrs_math`` for the forgetting curve and
``exam_day.crunch_priority()`` for the priority formula, so the two exam-time paths can't drift.

Interpretations (recorded in the hand-off doc):
- ``days_to_exam`` is fractional days from the review/queue time to the exam start.
- ``w_c`` = Σ over the card's in-scope concepts of (unit weight ÷ concepts in the unit), divided by the exam's
  total unit weight. Concept shares then sum to 1 over the exam, so ``w_c`` is already in [0, 1].
- With ``T ≤ 1.5`` the card goes to the cram window even if the single-touch condition holds: the touch at
  ``T − 1`` would fall inside the same window (or in the past).
- Fuzz is never applied to crunch intervals (doc 05 §1).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.algorithms.exam_day import CardKind, ExamCard, crunch_priority, retrievability_at
from engine.algorithms.fsrs_math import DEFAULT_DECAY, interval_days, retrievability

VERSION = "crunch-1"

CRUNCH_DAYS = 7.0
CRUNCH_MIN_RETENTION = 0.93
CRAM_WINDOW_THRESHOLD_DAYS = 1.5
CRAM_WINDOW_START = timedelta(hours=36)
CRAM_WINDOW_END = timedelta(hours=6)
FINAL_REVIEW_OFFSET_DAYS = 0.75
MIN_CAP_DAYS = 0.5
SINGLE_TOUCH_OFFSET_DAYS = 1.0
NEW_CARD_MIN_DAYS = 2.0
DEFAULT_MEDIAN_RESPONSE_MS = 12_000

IntervalKind = Literal["single_touch", "capped", "cram_window"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


class ScopeUnit(_Frozen):
    unit_id: str
    weight: float = Field(ge=0)  # syllabus weight %, any scale
    concept_ids: tuple[str, ...]


class CrunchExam(_Frozen):
    exam_id: str
    starts_at: datetime
    units: tuple[ScopeUnit, ...]

    @model_validator(mode="after")
    def _check(self) -> CrunchExam:
        _aware(self.starts_at, "starts_at")
        return self

    @property
    def concept_ids(self) -> frozenset[str]:
        return frozenset(k for u in self.units for k in u.concept_ids)


class CrunchCard(_Frozen):
    card_id: str
    unit_id: str
    concept_ids: tuple[str, ...]
    kind: CardKind = "other"
    stability: float | None = Field(default=None, gt=0)  # None = new card (never reviewed)
    last_review: datetime | None = None
    recent_lapses: int = Field(default=0, ge=0)
    topo_rank: int = 0  # prerequisite order of the card's concepts (lower = earlier); orders new cards

    @property
    def is_new(self) -> bool:
        return self.stability is None or self.last_review is None


class CrunchInterval(_Frozen):
    kind: IntervalKind
    interval_days: float | None  # None for the cram window (the window is the schedule)
    r_exam: float  # target retention at exam time
    r_at_exam: float  # R(T, S_after)
    i_fsrs: float
    i_cap: float | None  # None when T ≤ 1.5


class CrunchSchedule(_Frozen):
    exam_id: str
    interval: CrunchInterval
    due_at: datetime | None  # single touch / capped
    window_start: datetime | None  # cram window
    window_end: datetime | None


class CrunchQueue(_Frozen):
    review_card_ids: tuple[str, ...]  # priority order, fits capacity
    new_card_ids: tuple[str, ...]  # introduced after reviews, only while capacity remains
    deferred_card_ids: tuple[str, ...]  # review cards that didn't fit (planner is told)
    deficit_minutes: float
    not_in_crunch_ids: tuple[str, ...]  # no exam in scope within crunch_days: normal FSRS applies
    priorities: dict[str, float]


def days_until(now: datetime, when: datetime) -> float:
    return (when - now) / timedelta(days=1)


def card_weight(card: CrunchCard, exam: CrunchExam) -> float:
    """w_c: the card's share of the exam, summing each in-scope concept's (unit weight ÷ unit concept count)."""
    total = sum(u.weight for u in exam.units)
    if total <= 0:
        return 0.0
    concepts = set(card.concept_ids)
    share = 0.0
    for unit in exam.units:
        if unit.concept_ids:
            per_concept = unit.weight / len(unit.concept_ids)
            share += per_concept * sum(1 for k in unit.concept_ids if k in concepts)
    return share / total


def applicable_exam(
    concept_ids: Sequence[str],
    exams: Sequence[CrunchExam],
    now: datetime,
    crunch_days: float = CRUNCH_DAYS,
) -> CrunchExam | None:
    """The earliest upcoming exam whose scope shares a concept with the card, if it is within ``crunch_days``."""
    _aware(now, "now")
    concepts = set(concept_ids)
    upcoming = [e for e in exams if e.starts_at > now and concepts & e.concept_ids]
    if not upcoming:
        return None
    earliest = min(upcoming, key=lambda e: (e.starts_at, e.exam_id))
    return earliest if days_until(now, earliest.starts_at) <= crunch_days else None


def crunch_interval(
    stability_after: float,
    days_to_exam: float,
    desired_retention: float = 0.9,
    decay: float = DEFAULT_DECAY,
) -> CrunchInterval:
    """Next interval after a review in crunch mode (doc 05 §2 step 2)."""
    if days_to_exam <= 0:
        raise ValueError("crunch mode needs an upcoming exam (days_to_exam > 0)")
    r_exam = max(desired_retention, CRUNCH_MIN_RETENTION)
    i_fsrs = interval_days(r_exam, stability_after, decay)
    r_at_exam = retrievability(days_to_exam, stability_after, decay)
    if days_to_exam <= CRAM_WINDOW_THRESHOLD_DAYS:
        return CrunchInterval(
            kind="cram_window", interval_days=None, r_exam=r_exam, r_at_exam=r_at_exam, i_fsrs=i_fsrs, i_cap=None
        )
    i_cap = max(MIN_CAP_DAYS, (days_to_exam - FINAL_REVIEW_OFFSET_DAYS) / 2)
    if r_at_exam >= r_exam and i_fsrs >= days_to_exam:
        return CrunchInterval(
            kind="single_touch",
            interval_days=days_to_exam - SINGLE_TOUCH_OFFSET_DAYS,
            r_exam=r_exam,
            r_at_exam=r_at_exam,
            i_fsrs=i_fsrs,
            i_cap=i_cap,
        )
    return CrunchInterval(
        kind="capped",
        interval_days=min(i_fsrs, i_cap),
        r_exam=r_exam,
        r_at_exam=r_at_exam,
        i_fsrs=i_fsrs,
        i_cap=i_cap,
    )


def schedule_review(
    concept_ids: Sequence[str],
    stability_after: float,
    reviewed_at: datetime,
    exams: Sequence[CrunchExam],
    desired_retention: float = 0.9,
    crunch_days: float = CRUNCH_DAYS,
    decay: float = DEFAULT_DECAY,
) -> CrunchSchedule | None:
    """Crunch schedule for a just-reviewed card, or None when normal FSRS applies (no exam in crunch range)."""
    exam = applicable_exam(concept_ids, exams, reviewed_at, crunch_days)
    if exam is None:
        return None
    interval = crunch_interval(stability_after, days_until(reviewed_at, exam.starts_at), desired_retention, decay)
    if interval.interval_days is None:
        return CrunchSchedule(
            exam_id=exam.exam_id,
            interval=interval,
            due_at=None,
            window_start=max(reviewed_at, exam.starts_at - CRAM_WINDOW_START),
            window_end=exam.starts_at - CRAM_WINDOW_END,
        )
    return CrunchSchedule(
        exam_id=exam.exam_id,
        interval=interval,
        due_at=reviewed_at + timedelta(days=interval.interval_days),
        window_start=None,
        window_end=None,
    )


def _as_exam_card(card: CrunchCard) -> ExamCard:
    return ExamCard(
        card_id=card.card_id,
        unit_id=card.unit_id,
        kind=card.kind,
        stability=card.stability,
        last_review=card.last_review,
        recent_lapses=card.recent_lapses,
    )


def build_crunch_queue(
    now: datetime,
    cards: Sequence[CrunchCard],
    exams: Sequence[CrunchExam],
    capacity_minutes: float,
    median_response_ms: int = DEFAULT_MEDIAN_RESPONSE_MS,
    crunch_days: float = CRUNCH_DAYS,
    decay: float = DEFAULT_DECAY,
) -> CrunchQueue:
    """Daily crunch queue (doc 05 §2 steps 3–4).

    Review cards are ranked by ``crunch_priority`` against their earliest in-crunch exam and fill
    ``capacity_minutes`` at ``median_response_ms`` per card; the rest are deferred and reported as a deficit.
    New in-scope cards are introduced only while capacity remains and their exam is ≥ 2 days away, ordered by
    ``w_c`` descending, then prerequisite order.
    """
    if capacity_minutes < 0:
        raise ValueError("capacity_minutes must be >= 0")
    if median_response_ms <= 0:
        raise ValueError("median_response_ms must be positive")
    minutes_per_card = median_response_ms / 60_000
    slots = math.floor(capacity_minutes / minutes_per_card + 1e-9)

    ranked: list[tuple[float, str]] = []
    new_ranked: list[tuple[float, int, str]] = []
    not_in_crunch: list[str] = []
    priorities: dict[str, float] = {}
    for card in cards:
        exam = applicable_exam(card.concept_ids, exams, now, crunch_days)
        if exam is None:
            not_in_crunch.append(card.card_id)
            continue
        weight = card_weight(card, exam)
        if card.is_new:
            if days_until(now, exam.starts_at) >= NEW_CARD_MIN_DAYS:
                new_ranked.append((weight, card.topo_rank, card.card_id))
            continue
        r_exam = retrievability_at(_as_exam_card(card), exam.starts_at, decay)
        priority = crunch_priority(_as_exam_card(card), weight, r_exam)
        priorities[card.card_id] = priority
        ranked.append((priority, card.card_id))

    ranked.sort(key=lambda pc: (-pc[0], pc[1]))
    review = [cid for _, cid in ranked[:slots]]
    deferred = [cid for _, cid in ranked[slots:]]
    new_ranked.sort(key=lambda w: (-w[0], w[1], w[2]))
    new = [cid for _, _, cid in new_ranked[: max(0, slots - len(review))]]
    return CrunchQueue(
        review_card_ids=tuple(review),
        new_card_ids=tuple(new),
        deferred_card_ids=tuple(deferred),
        deficit_minutes=len(deferred) * minutes_per_card,
        not_in_crunch_ids=tuple(not_in_crunch),
        priorities=priorities,
    )

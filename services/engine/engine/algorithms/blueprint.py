"""Mock exam blueprint and bank selection (doc 05 §6; DIAG-02).

Produces slots (unit, question type, points, target difficulty) that sum exactly to the exam's total points, then
fills them from the question bank: unseen verified questions first, then ones last seen > 30 days ago. Slots
that can't be filled are marked for generation; a slot that still fails after 3 generation attempts is dropped
with :func:`drop_slot`, which rebalances its points.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = "blueprint-1"

QuestionType = Literal["mcq", "short", "numeric", "multi_step", "code", "proof"]
TYPE_POINTS: dict[str, int] = {"mcq": 2, "short": 5, "numeric": 5, "multi_step": 10, "code": 10, "proof": 10}
MIN_SLOT_POINTS = min(TYPE_POINTS.values())
RESEEN_AFTER = timedelta(days=30)
TARGET_MEAN_DIFFICULTY = 3


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


@dataclass
class _Draft:
    unit_id: str
    type: QuestionType
    points: int


class BlueprintUnit(_Frozen):
    unit_id: str
    weight: float = Field(gt=0)
    mastery: float | None = Field(default=None, ge=0, le=1)


class Slot(_Frozen):
    unit_id: str
    type: QuestionType
    points: int = Field(ge=1)
    difficulty: int = Field(ge=1, le=5)


class Blueprint(_Frozen):
    slots: tuple[Slot, ...]
    total_points: int
    duration_min: int
    type_mix: dict[str, float]


def default_type_mix(course_has_code: bool) -> dict[str, float]:
    return {"mcq": 0.30, "short": 0.25, "multi_step": 0.35, ("code" if course_has_code else "proof"): 0.10}


def _normalize(mix: Mapping[str, float]) -> dict[str, float]:
    clean = {t: v for t, v in mix.items() if v > 0 and t in TYPE_POINTS}
    total = sum(clean.values())
    if total <= 0:
        raise ValueError("type mix must contain at least one known type with positive share")
    return {t: v / total for t, v in clean.items()}


def _apportion(shares: Mapping[str, float], total: int, minimum: int) -> dict[str, int]:
    """Largest-remainder integer apportionment with a per-key minimum."""
    if minimum * len(shares) > total:
        raise ValueError("total points too small for the number of units")
    raw = {k: s * total for k, s in shares.items()}
    alloc = {k: max(minimum, math.floor(v)) for k, v in raw.items()}
    diff = total - sum(alloc.values())
    order = sorted(shares, key=lambda k: (-(raw[k] - math.floor(raw[k])), k))
    i = 0
    while diff > 0:
        alloc[order[i % len(order)]] += 1
        diff -= 1
        i += 1
    while diff < 0:  # minimum bumps overshot: take from the largest allocations above the minimum
        k = max((k for k in alloc if alloc[k] > minimum), key=lambda k: (alloc[k], k))
        alloc[k] -= 1
        diff += 1
    return alloc


def build_blueprint(
    units: Sequence[BlueprintUnit],
    total_points: int = 100,
    duration_min: int = 60,
    type_mix: Mapping[str, float] | None = None,
    course_has_code: bool = False,
) -> Blueprint:
    if not units:
        raise ValueError("an exam needs at least one covered unit")
    mix = _normalize(type_mix if type_mix else default_type_mix(course_has_code))

    # Unit allocation: points_u ∝ w_u · (1 + 0.5·(1 − mastery_u)); unstarted counts as mastery 0.
    raw = {u.unit_id: u.weight * (1 + 0.5 * (1 - (u.mastery or 0.0))) for u in units}
    total_raw = sum(raw.values())
    targets = _apportion({k: v / total_raw for k, v in raw.items()}, total_points, MIN_SLOT_POINTS)

    type_points_used = dict.fromkeys(mix, 0)
    drafts: list[_Draft] = []
    for u in sorted(units, key=lambda u: (-targets[u.unit_id], u.unit_id)):
        remaining = targets[u.unit_id]
        unit_drafts: list[_Draft] = []
        while remaining >= MIN_SLOT_POINTS:
            fitting = [t for t in mix if TYPE_POINTS[t] <= remaining]
            # the type furthest below its target share of all points so far (ties → larger type, then name)
            t = min(
                fitting,
                key=lambda t: ((type_points_used[t] + TYPE_POINTS[t]) / total_points - mix[t], -TYPE_POINTS[t], t),
            )
            unit_drafts.append(_Draft(unit_id=u.unit_id, type=_as_type(t), points=TYPE_POINTS[t]))
            type_points_used[t] += TYPE_POINTS[t]
            remaining -= TYPE_POINTS[t]
        if not unit_drafts:  # cannot happen with the MIN_SLOT_POINTS minimum; kept for safety
            smallest = min(mix, key=lambda t: TYPE_POINTS[t])
            unit_drafts.append(_Draft(unit_id=u.unit_id, type=_as_type(smallest), points=0))
        unit_drafts[-1].points += remaining
        drafts.extend(unit_drafts)

    difficulties = _assign_difficulties(drafts, {u.unit_id: u.weight for u in units})
    final = tuple(
        Slot(unit_id=d.unit_id, type=d.type, points=d.points, difficulty=diff)
        for d, diff in zip(drafts, difficulties, strict=True)
    )
    return Blueprint(slots=final, total_points=total_points, duration_min=duration_min, type_mix=mix)


def _as_type(name: str) -> QuestionType:
    if name not in TYPE_POINTS:
        raise ValueError(f"unknown question type {name!r}")
    return name  # type: ignore[return-value]  # validated against TYPE_POINTS keys (== QuestionType)


def _assign_difficulties(slots: Sequence[_Draft], weights: Mapping[str, float]) -> list[int]:
    """Mean 3; every high-weight unit (weight ≥ median) gets one slot at 4, balanced by a 2 elsewhere."""
    diffs = [TARGET_MEAN_DIFFICULTY] * len(slots)
    median = statistics.median(weights.values())
    high_units = sorted((u for u, w in weights.items() if w >= median), key=lambda u: (-weights[u], u))
    for unit in high_units:
        idx = next((i for i, s in enumerate(slots) if s.unit_id == unit and diffs[i] == 3), None)
        if idx is None:
            continue
        diffs[idx] = 4
        # balance with an easier question: prefer low-weight units, then small-point slots
        candidates = [i for i, s in enumerate(slots) if diffs[i] == 3 and i != idx]
        if candidates:
            j = min(candidates, key=lambda i: (weights[slots[i].unit_id], slots[i].points, i))
            diffs[j] = 2
    return diffs


# ---------------------------------------------------------------- selection + rebalancing
class BankItem(_Frozen):
    question_id: str
    unit_id: str
    type: QuestionType
    difficulty: float = Field(ge=1, le=5)
    is_verified: bool
    last_seen_at: datetime | None = None


class Assignment(_Frozen):
    slot: Slot
    question_id: str | None  # None → generate (then verify) for this slot
    source: Literal["unseen", "reseen", "generate"]


def select_questions(blueprint: Blueprint, bank: Sequence[BankItem], now: datetime) -> list[Assignment]:
    used: set[str] = set()
    out: list[Assignment] = []
    for slot in blueprint.slots:
        pool = [
            q
            for q in bank
            if q.is_verified and q.unit_id == slot.unit_id and q.type == slot.type and q.question_id not in used
        ]
        unseen = [q for q in pool if q.last_seen_at is None]
        reseen = [q for q in pool if q.last_seen_at is not None and now - q.last_seen_at > RESEEN_AFTER]
        group = unseen or reseen
        if group:
            best = min(group, key=lambda q: (abs(q.difficulty - slot.difficulty), q.question_id))
            used.add(best.question_id)
            out.append(Assignment(slot=slot, question_id=best.question_id, source="unseen" if unseen else "reseen"))
        else:
            out.append(Assignment(slot=slot, question_id=None, source="generate"))
    return out


def drop_slot(blueprint: Blueprint, index: int) -> Blueprint:
    """Remove a slot that couldn't be generated and give its points to the largest remaining slot of the same
    unit (or the largest slot overall if the unit has no other slots), so the total stays exact."""
    if len(blueprint.slots) <= 1:
        raise ValueError("cannot drop the only slot")
    dropped = blueprint.slots[index]
    rest = list(blueprint.slots[:index] + blueprint.slots[index + 1 :])
    same_unit = [i for i, s in enumerate(rest) if s.unit_id == dropped.unit_id]
    target = max(same_unit or range(len(rest)), key=lambda i: (rest[i].points, -i))
    rest[target] = rest[target].model_copy(update={"points": rest[target].points + dropped.points})
    return blueprint.model_copy(update={"slots": tuple(rest)})

"""Session interleaving (doc 05 §3; SRS-05): reference implementation for the TypeScript session builder.

Orders an already-selected candidate list:
1. Group by unit; walk with a weighted round-robin where each step takes the unit with the largest remaining
   share, never the previous unit while another unit still has items. Ties go to the unit that appears first in
   the candidate list (its best-priority item). Within a unit, candidate order (priority) is kept.
2. Confusable concept pairs present in the session are placed within 3 positions of each other at least once:
   the later item of an unsatisfied pair moves next to the earlier one, at the reachable position that adds the
   fewest same-unit adjacencies and breaks no already-satisfied pair, nearest its old position.
3. When practice questions exist in scope, ~15% of the slots (rounded half up) hold questions in place of the
   lowest-priority cards; the displaced cards are returned so the caller can keep them due.

The algorithm has no randomness, so the result is deterministic for a given input (the spec's "deterministic
given a seed" holds trivially; ``session_id`` is not needed).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, ConfigDict

VERSION = "interleave-1"

CONFUSABLE_MAX_DISTANCE = 3
MIXED_TYPE_SHARE = 0.15
EMBEDDING_CONFUSABLE_THRESHOLD = 0.85

ItemKind = Literal["card", "question"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SessionItem(_Frozen):
    item_id: str
    unit_id: str
    concept_ids: tuple[str, ...] = ()
    kind: ItemKind = "card"


class InterleavedSession(_Frozen):
    items: tuple[SessionItem, ...]
    displaced_card_ids: tuple[str, ...]  # cards replaced by mixed-type questions (still due)
    unsatisfied_pairs: tuple[tuple[str, str], ...]  # confusable pairs that couldn't be placed within 3


def adjacency_violations(items: Sequence[SessionItem]) -> int:
    """Consecutive same-unit pairs that were avoidable (another unit still had items later in the session)."""
    count = 0
    for i in range(1, len(items)):
        if items[i].unit_id == items[i - 1].unit_id and any(x.unit_id != items[i].unit_id for x in items[i + 1 :]):
            count += 1
    return count


def round_robin(candidates: Sequence[SessionItem]) -> list[SessionItem]:
    """Weighted round-robin by remaining share with the no-consecutive-unit rule (doc 05 §3 steps 1–2)."""
    groups: dict[str, list[SessionItem]] = defaultdict(list)
    first_seen: dict[str, int] = {}
    for idx, item in enumerate(candidates):
        groups[item.unit_id].append(item)
        first_seen.setdefault(item.unit_id, idx)
    out: list[SessionItem] = []
    prev: str | None = None
    while len(out) < len(candidates):
        live = [u for u, g in groups.items() if g]
        options = [u for u in live if u != prev] or live
        unit = min(options, key=lambda u: (-len(groups[u]), first_seen[u]))
        out.append(groups[unit].pop(0))
        prev = unit
    return out


def _positions(items: Sequence[SessionItem], concept: str) -> list[int]:
    return [i for i, it in enumerate(items) if concept in it.concept_ids]


def _pair_distance(items: Sequence[SessionItem], a: str, b: str) -> int | None:
    pa, pb = _positions(items, a), _positions(items, b)
    if not pa or not pb:
        return None
    return min(abs(i - j) for i in pa for j in pb)


def _satisfied(items: Sequence[SessionItem], pair: tuple[str, str]) -> bool:
    d = _pair_distance(items, *pair)
    return d is not None and d <= CONFUSABLE_MAX_DISTANCE


def place_confusables(
    items: Sequence[SessionItem], pairs: Iterable[tuple[str, str]]
) -> tuple[list[SessionItem], list[tuple[str, str]]]:
    """Move items so each present confusable pair is within 3 positions at least once (doc 05 §3 step 3)."""
    order = list(items)
    present = sorted(
        {(min(p), max(p)) for p in pairs if p[0] != p[1] and _pair_distance(order, p[0], p[1]) is not None}
    )
    unsatisfied: list[tuple[str, str]] = []
    for a, b in present:
        pair = (a, b)
        if _satisfied(order, pair):
            continue
        pa, pb = _positions(order, a), _positions(order, b)
        # Move the later item of the closest occurrence pair toward the earlier one.
        i, j = min(((i, j) for i in pa for j in pb), key=lambda ij: (abs(ij[0] - ij[1]), min(ij)))
        anchor_idx, mover_idx = (i, j) if i < j else (j, i)
        mover = order[mover_idx]
        rest = order[:mover_idx] + order[mover_idx + 1 :]
        anchor = order[anchor_idx]  # anchor_idx < mover_idx, so its index is unchanged in ``rest``
        kept = [p for p in present if p != pair and _satisfied(order, p)]
        best: tuple[tuple[int, int, int], list[SessionItem]] | None = None
        for pos in range(len(rest) + 1):
            candidate = [*rest[:pos], mover, *rest[pos:]]
            anchor_pos = candidate.index(anchor)
            if abs(anchor_pos - pos) > CONFUSABLE_MAX_DISTANCE:
                continue
            broken = sum(1 for p in kept if not _satisfied(candidate, p))
            score = (broken, adjacency_violations(candidate), abs(pos - mover_idx))
            if best is None or score < best[0]:
                best = (score, candidate)
        if best is None or best[0][0] > 0:
            unsatisfied.append(pair)
            continue
        order = best[1]
    return order, unsatisfied


def mixed_type_slots(session_size: int, questions_available: int) -> int:
    """~15% of slots (rounded half up), never more than the questions in scope."""
    if session_size <= 0 or questions_available <= 0:
        return 0
    return min(questions_available, math.floor(session_size * MIXED_TYPE_SHARE + 0.5))


def interleave(
    cards: Sequence[SessionItem],
    questions: Sequence[SessionItem] = (),
    confusable_pairs: Iterable[tuple[str, str]] = (),
) -> InterleavedSession:
    """Build the session order. ``cards`` come in priority order (highest first); ``questions`` are the in-scope
    practice items in the order they should be used."""
    ids = [c.item_id for c in [*cards, *questions]]
    if len(ids) != len(set(ids)):
        raise ValueError("item ids must be unique")
    n_questions = mixed_type_slots(len(cards), len(questions))
    kept_cards = list(cards[: len(cards) - n_questions])
    displaced = [c.item_id for c in cards[len(cards) - n_questions :]]
    # Questions sit just below the cards in priority, so they only win round-robin ties they're entitled to.
    pool = kept_cards + list(questions[:n_questions])
    ordered, unsatisfied = place_confusables(round_robin(pool), confusable_pairs)
    return InterleavedSession(
        items=tuple(ordered),
        displaced_card_ids=tuple(displaced),
        unsatisfied_pairs=tuple(unsatisfied),
    )


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def embedding_confusables(
    embeddings: Mapping[str, Sequence[float]],
    concept_unit: Mapping[str, str],
    threshold: float = EMBEDDING_CONFUSABLE_THRESHOLD,
) -> list[tuple[str, str]]:
    """Concept pairs in different units with cosine similarity > ``threshold`` (doc 05 §3 step 3)."""
    out: list[tuple[str, str]] = []
    for a, b in combinations(sorted(embeddings), 2):
        if concept_unit.get(a) is None or concept_unit.get(a) == concept_unit.get(b):
            continue
        if _cosine(embeddings[a], embeddings[b]) > threshold:
            out.append((a, b))
    return out

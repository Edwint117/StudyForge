"""Cheat-sheet page fitting (COMP-05): choose layout + item variants to fit the exam's formula-sheet rules.

Each item (formula, definition, theorem) has a full and a short variant (e.g. the formula without its
explanation). Layouts go from most to least readable (bigger font, then fewer columns; 7 pt floor). Choice order:
1. the most readable layout where every item fits in **full** (full content beats a bigger font);
2. otherwise the most readable layout where every item fits, some in short form;
3. otherwise the layout keeping the most priority, always including pinned items, reporting what was shortened or
   dropped. The user's order is preserved.

Heights are *estimates* from character counts (average glyph ≈ 0.5 em). The server-side PDF render (KaTeX) is the
source of truth, and the live preview re-runs the fitter with measured heights when available.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = "cheatsheet-fit-1"

PAPER_IN: dict[str, tuple[float, float]] = {"letter": (8.5, 11.0), "a4": (8.27, 11.69)}
MARGIN_IN = 0.4
GUTTER_IN = 0.2
LINE_SPACING = 1.2
AVG_CHAR_EM = 0.5
MATH_BLOCK_LINES = 2.2
ITEM_GAP_LINES = 0.5
FONT_SIZES = (10.0, 9.0, 8.0, 7.0)  # 7pt is the readability floor
COLUMN_OPTIONS = (2, 3, 4)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SheetItem(_Frozen):
    id: str
    title: str
    full_md: str
    short_md: str | None = None  # None → can't be shortened
    math_blocks_full: int = Field(default=0, ge=0)
    math_blocks_short: int = Field(default=0, ge=0)
    priority: float = Field(default=1.0, ge=0)
    pinned: bool = False


class PageRules(_Frozen):
    paper: Literal["letter", "a4"] = "letter"
    sides: int = Field(default=1, ge=1, le=2)


class Layout(_Frozen):
    font_pt: float
    columns: int


class Placement(_Frozen):
    id: str
    variant: Literal["full", "short"]


class FitResult(_Frozen):
    layout: Layout
    placements: tuple[Placement, ...]  # in the user's order
    dropped: tuple[str, ...]
    shortened: tuple[str, ...]
    utilization: float  # estimated fraction of the page budget used
    pinned_overflow: bool  # pinned items alone don't fit even at the smallest layout


def capacity_lines(rules: PageRules, layout: Layout) -> tuple[float, int]:
    """(total line capacity, characters per line) for a layout."""
    w, h = PAPER_IN[rules.paper]
    col_w_pt = ((w - 2 * MARGIN_IN - (layout.columns - 1) * GUTTER_IN) / layout.columns) * 72
    usable_h_pt = (h - 2 * MARGIN_IN) * 72
    chars_per_line = max(10, int(col_w_pt / (layout.font_pt * AVG_CHAR_EM)))
    lines_per_col = usable_h_pt / (layout.font_pt * LINE_SPACING)
    return lines_per_col * layout.columns * rules.sides, chars_per_line


def item_lines(item: SheetItem, variant: Literal["full", "short"], chars_per_line: int) -> float:
    text = item.full_md if variant == "full" else (item.short_md or item.full_md)
    blocks = item.math_blocks_full if variant == "full" else item.math_blocks_short
    body = sum(max(1, math.ceil(len(par) / chars_per_line)) for par in text.split("\n") if par.strip())
    title = max(1, math.ceil(len(item.title) / chars_per_line))
    return title + body + blocks * MATH_BLOCK_LINES + ITEM_GAP_LINES


def _try(items: Sequence[SheetItem], capacity: float, cpl: int) -> tuple[dict[str, str], float, bool]:
    """Maximize what fits first, then readability:
    1. place every item in its smallest form, pinned first, then by priority (drop what doesn't fit);
    2. upgrade placed items to their full form in the same order while space remains."""
    order = sorted(items, key=lambda i: (not i.pinned, -i.priority, i.id))
    chosen: dict[str, str] = {}
    used = 0.0
    pinned_ok = True
    for it in order:
        smallest = min(item_lines(it, "full", cpl), item_lines(it, "short", cpl) if it.short_md else math.inf)
        if used + smallest <= capacity:
            chosen[it.id] = "short" if it.short_md and smallest < item_lines(it, "full", cpl) else "full"
            used += smallest
        elif it.pinned:
            pinned_ok = False
    for it in order:
        if chosen.get(it.id) == "short":
            extra = item_lines(it, "full", cpl) - item_lines(it, "short", cpl)
            if used + extra <= capacity:
                chosen[it.id] = "full"
                used += extra
    return chosen, used, pinned_ok


def fit_sheet(items: Sequence[SheetItem], rules: PageRules) -> FitResult:
    layouts = [Layout(font_pt=f, columns=c) for f in FONT_SIZES for c in COLUMN_OPTIONS]
    attempts = []
    for layout in layouts:
        capacity, cpl = capacity_lines(rules, layout)
        attempts.append((layout, capacity, *_try(items, capacity, cpl)))
    # 1) most readable layout with everything in full; 2) with everything placed (some short); 3) best partial
    for need_full in (True, False):
        for layout, capacity, chosen, used, pinned_ok in attempts:
            complete = pinned_ok and len(chosen) == len(items)
            if complete and (not need_full or all(v == "full" for v in chosen.values())):
                return _result(items, layout, chosen, used / capacity, pinned_overflow=False)
    best: tuple[float, int, Layout, dict[str, str], float, bool] | None = None
    for rank, (layout, capacity, chosen, used, pinned_ok) in enumerate(attempts):
        kept = sum(i.priority * (1.0 if chosen.get(i.id) == "full" else 0.7) for i in items if i.id in chosen)
        score = (float(pinned_ok), kept)
        if best is None or score > (best[5], best[0]) or (score == (best[5], best[0]) and rank < best[1]):
            best = (kept, rank, layout, chosen, used / capacity, pinned_ok)
    assert best is not None
    _, _, layout, chosen, utilization, pinned_ok = best
    return _result(items, layout, chosen, utilization, pinned_overflow=not pinned_ok)


def _result(
    items: Sequence[SheetItem], layout: Layout, chosen: dict[str, str], utilization: float, pinned_overflow: bool
) -> FitResult:
    placements = tuple(
        Placement(id=i.id, variant="full" if chosen[i.id] == "full" else "short") for i in items if i.id in chosen
    )
    return FitResult(
        layout=layout,
        placements=placements,
        dropped=tuple(i.id for i in items if i.id not in chosen),
        shortened=tuple(p.id for p in placements if p.variant == "short"),
        utilization=round(min(utilization, 1.0), 4),
        pinned_overflow=pinned_overflow,
    )

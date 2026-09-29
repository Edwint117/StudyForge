from hypothesis import given, settings
from hypothesis import strategies as st

from engine.algorithms.cheatsheet import (
    FONT_SIZES,
    Layout,
    PageRules,
    SheetItem,
    capacity_lines,
    fit_sheet,
    item_lines,
)


def formula(i: int, words: int = 30, pinned: bool = False, priority: float = 1.0) -> SheetItem:
    return SheetItem(
        id=f"f{i}",
        title=f"Formula {i}",
        full_md=("explanation " * words).strip(),
        short_md="short form",
        math_blocks_full=1,
        math_blocks_short=1,
        priority=priority,
        pinned=pinned,
    )


def test_capacity_grows_with_smaller_font_and_two_sides() -> None:
    one = PageRules()
    big, _ = capacity_lines(one, Layout(font_pt=10, columns=2))
    small, _ = capacity_lines(one, Layout(font_pt=7, columns=2))
    two_sided, _ = capacity_lines(PageRules(sides=2), Layout(font_pt=10, columns=2))
    assert small > big and two_sided == 2 * big


def test_few_items_fit_in_full_at_the_most_readable_layout() -> None:
    result = fit_sheet([formula(i) for i in range(5)], PageRules())
    assert result.layout == Layout(font_pt=FONT_SIZES[0], columns=2)
    assert not result.dropped and not result.shortened and not result.pinned_overflow
    assert [p.id for p in result.placements] == [f"f{i}" for i in range(5)]  # user order kept


def test_prefers_smaller_font_over_shortening_when_full_fits() -> None:
    # 30 medium items: too big in full at 10pt/9pt, but fit in full at 8pt (4 columns)
    result = fit_sheet([formula(i, words=15) for i in range(30)], PageRules())
    assert result.layout.font_pt < FONT_SIZES[0]
    assert not result.shortened and not result.dropped


def test_shortens_when_nothing_fits_in_full() -> None:
    # 40 long items don't fit in full even at 7pt, so keep the most readable font and use short forms
    result = fit_sheet([formula(i, words=60) for i in range(40)], PageRules())
    assert result.layout.font_pt == FONT_SIZES[0]
    assert result.shortened and not result.dropped
    assert result.utilization <= 1.0


def test_overflow_drops_lowest_priority_but_keeps_pinned() -> None:
    items = [formula(i, words=200, priority=float(i)) for i in range(200)]
    items[0] = formula(0, words=200, priority=0.0, pinned=True)  # lowest priority but pinned
    result = fit_sheet(items, PageRules())
    kept = {p.id for p in result.placements}
    assert "f0" in kept and not result.pinned_overflow
    assert result.dropped
    assert min(int(d[1:]) for d in result.dropped) < max(int(k[1:]) for k in kept if k != "f0")
    # everything dropped has lower priority than everything kept (except the pinned item)
    lowest_kept = min(items[int(k[1:])].priority for k in kept if k != "f0")
    assert all(items[int(d[1:])].priority <= lowest_kept for d in result.dropped)


def test_pinned_overflow_is_reported() -> None:
    huge = [formula(i, words=5000, pinned=True) for i in range(10)]
    huge = [h.model_copy(update={"short_md": None}) for h in huge]
    assert fit_sheet(huge, PageRules()).pinned_overflow


def test_item_lines_counts_math_blocks() -> None:
    plain = SheetItem(id="a", title="t", full_md="x")
    with_math = plain.model_copy(update={"math_blocks_full": 2})
    assert item_lines(with_math, "full", 40) - item_lines(plain, "full", 40) == 4.4


@settings(max_examples=40, deadline=None)
@given(
    st.lists(st.tuples(st.integers(1, 300), st.floats(0, 10), st.booleans()), min_size=1, max_size=60),
    st.integers(1, 2),
)
def test_fit_invariants(rows: list[tuple[int, float, bool]], sides: int) -> None:
    items = [formula(i, words=w, priority=p) for i, (w, p, _) in enumerate(rows)]
    result = fit_sheet(items, PageRules(sides=sides))
    placed = [p.id for p in result.placements]
    assert len(placed) + len(result.dropped) == len(items)
    assert placed == [i.id for i in items if i.id in set(placed)]  # order preserved
    assert set(result.shortened) <= set(placed)
    assert 0 <= result.utilization <= 1

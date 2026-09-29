import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.interop.anki import (
    ExportCard,
    UnsupportedAnkiFormat,
    anki_html_to_md,
    export_apkg,
    import_apkg,
    md_to_anki_html,
)

CARDS = [
    ExportCard(
        id="card-basic",
        type="basic",
        front_md="What is $e^{i\\pi}$?",
        back_md="$-1$",
        tags=("euler", "complex numbers"),
    ),
    ExportCard(id="card-rev", type="reversed", front_md="Mitochondria", back_md="Powerhouse of the cell"),
    ExportCard(
        id="card-cloze",
        type="cloze",
        cloze_md="{{c1::Bayes}} relates {{c2::conditional}} probabilities",
        back_md="See ch. 2",
    ),
    ExportCard(id="card-code", type="code", front_md='What prints?\n```c\nprintf("%d", 1<2);\n```', back_md="1"),
]


def test_markdown_html_conversion_round_trip() -> None:
    html = md_to_anki_html("Area: $\\pi r^2$ and\n$$\\int_0^1 x\\,dx$$ with <b>tags</b>")
    assert "\\(\\pi r^2\\)" in html and "\\[\\int_0^1 x\\,dx\\]" in html
    assert "&lt;b&gt;" in html  # user text is escaped, never injected as HTML
    md, media = anki_html_to_md(html)
    assert "$\\pi r^2$" in md and "$$\\int_0^1 x\\,dx$$" in md and "<b>tags</b>" in md
    assert media == []


def test_anki_html_to_md_handles_legacy_latex_and_images() -> None:
    md, media = anki_html_to_md('<div>[$]x^2[/$] and [latex]y[/latex]</div><img src="graph.png"><br>done &amp; dusted')
    assert md.startswith("$x^2$ and $$y$$")
    assert "![](media:graph.png)" in md and "done & dusted" in md
    assert media == ["graph.png"]


def test_export_then_import_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "deck.apkg"
    assert export_apkg("Stats", "course-123", CARDS, out) == 4
    deck = import_apkg(out)
    # the reversed note yields 2 Anki cards and the cloze note yields 2 (one per deletion) -> 6 cards
    assert len(deck.cards) == 6
    by_type: dict[str, list] = {}
    for c in deck.cards:
        by_type.setdefault(c.type, []).append(c)
    basic_fronts = {c.front_md for c in by_type["basic"]}
    assert "What is $e^{i\\pi}$?" in basic_fronts
    assert any("```" in f and "1<2" in f for f in basic_fronts)  # code survived escaping round trip
    rev = sorted(by_type["reversed"], key=lambda c: c.front_md)
    assert [(c.front_md, c.back_md) for c in rev] == [
        ("Mitochondria", "Powerhouse of the cell"),
        ("Powerhouse of the cell", "Mitochondria"),
    ]
    clozes = sorted(by_type["cloze"], key=lambda c: c.cloze_index or 0)
    assert [c.cloze_index for c in clozes] == [1, 2]
    assert clozes[0].cloze_md == "{{c1::Bayes}} relates {{c2::conditional}} probabilities"
    euler = next(c for c in by_type["basic"] if "e^" in c.front_md)
    assert euler.tags == ("euler", "complex_numbers")


def test_stable_ids_make_reexport_idempotent(tmp_path: Path) -> None:
    a, b = tmp_path / "a.apkg", tmp_path / "b.apkg"
    export_apkg("Stats", "course-123", CARDS, a)
    export_apkg("Stats", "course-123", CARDS, b)

    def guids(p: Path) -> set[str]:
        with zipfile.ZipFile(p) as zf:
            (tmp_path / "x.db").write_bytes(zf.read("collection.anki2"))
        with closing(sqlite3.connect(tmp_path / "x.db")) as db:
            return {g for (g,) in db.execute("SELECT guid FROM notes")}

    assert guids(a) == guids(b)


def _add_review_history(apkg: Path, tmp_path: Path) -> None:
    """Simulate a user's Anki history: inject revlog rows (+ a suspended card) into the exported collection."""
    with zipfile.ZipFile(apkg) as zf:
        members = {n: zf.read(n) for n in zf.namelist()}
    db_path = tmp_path / "col.db"
    db_path.write_bytes(members["collection.anki2"])
    with closing(sqlite3.connect(db_path)) as db:
        card_ids = [cid for (cid,) in db.execute("SELECT id FROM cards ORDER BY id")]
        t0 = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000)
        rows = [
            (t0, card_ids[0], 1, 1, 0, 2500, 8000, 0),  # learn, Again
            (t0 + 60_000, card_ids[0], 3, 1, 0, 2500, 5000, 0),  # learn, Good
            (t0 + 86_400_000, card_ids[0], 4, 4, 1, 2500, 3000, 1),  # review, Easy
            (t0 + 90_000_000, card_ids[0], 0, 0, 0, 0, 0, 4),  # manual reschedule: must be skipped
            (t0 + 30_000, card_ids[1], 2, 1, 0, 2500, 12000, 0),
        ]
        db.executemany(
            "INSERT INTO revlog (id, cid, ease, ivl, lastIvl, factor, time, type, usn) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, -1)",
            rows,
        )
        db.execute("UPDATE cards SET queue = -1 WHERE id = ?", (card_ids[1],))
        db.commit()
    members["collection.anki2"] = db_path.read_bytes()
    with zipfile.ZipFile(apkg, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_import_review_history_and_suspension(tmp_path: Path) -> None:
    out = tmp_path / "deck.apkg"
    export_apkg("Stats", "course-123", CARDS, out)
    _add_review_history(out, tmp_path)
    deck = import_apkg(out)
    assert [r.rating for r in deck.reviews] == [1, 2, 3, 4]  # chronological; manual reschedule dropped
    assert [r.kind for r in deck.reviews] == ["learn", "learn", "learn", "review"]
    assert deck.reviews[0].reviewed_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert deck.reviews[0].response_ms == 8000
    assert sum(c.suspended for c in deck.cards) == 1


def test_new_format_only_is_rejected_with_instructions(tmp_path: Path) -> None:
    p = tmp_path / "new.apkg"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("collection.anki21b", b"zstd...")
        zf.writestr("media", json.dumps({}))
    with pytest.raises(UnsupportedAnkiFormat, match="Support older Anki versions"):
        import_apkg(p)
    junk = tmp_path / "junk.apkg"
    with zipfile.ZipFile(junk, "w") as zf:
        zf.writestr("readme.txt", "hi")
    with pytest.raises(UnsupportedAnkiFormat):
        import_apkg(junk)

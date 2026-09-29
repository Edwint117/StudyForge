"""Anki ``.apkg`` export and import (SRS-08).

Export: genanki with stable model/deck IDs and card GUIDs derived from StudyForge ids, so re-exporting updates
the same notes in Anki instead of duplicating them. Markdown/LaTeX become Anki HTML + MathJax (``\\(…\\)``,
``\\[…\\]``).

Import: reads the legacy SQLite collection inside the zip (``collection.anki21``, else ``collection.anki2``):
notes, cards (incl. suspended state and the cloze deletion number), media names, and the **review log** that M7
replays to initialize FSRS. New-format-only exports (``collection.anki21b``, zstd-compressed) raise
:class:`UnsupportedAnkiFormat` with instructions to re-export with "Support older Anki versions".
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import tempfile
import zipfile
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import genanki
from pydantic import BaseModel, ConfigDict

VERSION = "anki-io-1"

CARD_CSS = ".card { font-family: system-ui, sans-serif; font-size: 20px; text-align: left; } pre { text-align: left; }"


def _stable_id(name: str) -> int:
    """Deterministic 31-bit id (Anki model/deck ids must stay the same across exports)."""
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "big") & 0x7FFFFFFF


# ---------------------------------------------------------------- markdown ⇄ Anki HTML
_FENCE = re.compile(r"```[\w+-]*\n(.*?)\n```", re.DOTALL)
_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH = re.compile(r"(?<![\\$])\$(?!\$)(.+?)(?<![\\$])\$")


def md_to_anki_html(md: str) -> str:
    """Minimal, safe conversion: escape HTML, keep code blocks, LaTeX → MathJax delimiters, newlines → <br>."""
    placeholders: list[str] = []

    def keep(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    text = _FENCE.sub(lambda m: keep(f"<pre><code>{html.escape(m.group(1))}</code></pre>"), md)
    text = _DISPLAY_MATH.sub(lambda m: keep(r"\[" + html.escape(m.group(1).strip()) + r"\]"), text)
    text = _INLINE_MATH.sub(lambda m: keep(r"\(" + html.escape(m.group(1)) + r"\)"), text)
    text = html.escape(text).replace("\n", "<br>")
    return re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)


_BLOCK_TAGS = re.compile(r"<\s*(br|/p|/div|/li|/h\d)\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_IMG = re.compile(r"<img[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.I)


def anki_html_to_md(field: str) -> tuple[str, list[str]]:
    """Anki field HTML → Markdown text + referenced media filenames. Tags are stripped (never rendered as HTML)."""
    media = _IMG.findall(field)
    text = _IMG.sub(lambda m: f"![](media:{m.group(1)})", field)
    text = re.sub(
        r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>",
        lambda m: "\n```\n" + m.group(1) + "\n```\n",
        text,
        flags=re.S | re.I,
    )
    text = _BLOCK_TAGS.sub("\n", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    for pattern, repl in (
        (r"\[\$\$\](.*?)\[/\$\$\]", r"$$\1$$"),
        (r"\[\$\](.*?)\[/\$\]", r"$\1$"),
        (r"\[latex\](.*?)\[/latex\]", r"$$\1$$"),
        (r"\\\[(.*?)\\\]", r"$$\1$$"),
        (r"\\\((.*?)\\\)", r"$\1$"),
    ):
        text = re.sub(pattern, repl, text, flags=re.S | re.I)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, media


# ---------------------------------------------------------------- export
class ExportCard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    type: Literal["basic", "reversed", "cloze", "concept_map", "math_step", "code", "free_explain"]
    front_md: str = ""
    back_md: str = ""
    cloze_md: str = ""
    tags: tuple[str, ...] = ()


def _models() -> dict[str, genanki.Model]:
    basic_tmpl = {"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}
    reverse_tmpl = {"name": "Card 2", "qfmt": "{{Back}}", "afmt": "{{FrontSide}}<hr id=answer>{{Front}}"}
    fields = [{"name": "Front"}, {"name": "Back"}]
    return {
        "basic": genanki.Model(
            _stable_id("studyforge-basic-v1"), "StudyForge Basic", fields=fields, templates=[basic_tmpl], css=CARD_CSS
        ),
        "reversed": genanki.Model(
            _stable_id("studyforge-reversed-v1"),
            "StudyForge Basic (and reversed)",
            fields=fields,
            templates=[basic_tmpl, reverse_tmpl],
            css=CARD_CSS,
        ),
        "cloze": genanki.Model(
            _stable_id("studyforge-cloze-v1"),
            "StudyForge Cloze",
            fields=[{"name": "Text"}, {"name": "Extra"}],
            templates=[{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"}],
            css=CARD_CSS,
            model_type=genanki.Model.CLOZE,
        ),
    }


def export_apkg(
    deck_name: str, deck_key: str, cards: Sequence[ExportCard], path: Path, media_files: Sequence[Path] = ()
) -> int:
    """Write an .apkg. ``deck_key`` (e.g. the course id) makes the deck id stable. Returns notes written.
    Card types Anki has no template for (concept_map, math_step, code, free_explain) export as Basic."""
    models = _models()
    deck = genanki.Deck(_stable_id(f"studyforge-deck:{deck_key}"), deck_name)
    for c in cards:
        tags = [re.sub(r"\s+", "_", t) for t in c.tags]
        guid = genanki.guid_for("studyforge", c.id)
        if c.type == "cloze":
            note = genanki.Note(
                model=models["cloze"],
                fields=[md_to_anki_html(c.cloze_md), md_to_anki_html(c.back_md)],
                tags=tags,
                guid=guid,
            )
        else:
            model = models["reversed" if c.type == "reversed" else "basic"]
            note = genanki.Note(
                model=model, fields=[md_to_anki_html(c.front_md), md_to_anki_html(c.back_md)], tags=tags, guid=guid
            )
        deck.add_note(note)
    package = genanki.Package(deck)
    package.media_files = [str(p) for p in media_files]
    package.write_to_file(str(path))
    return len(cards)


# ---------------------------------------------------------------- import
class UnsupportedAnkiFormat(ValueError):
    pass


class ImportedCard(BaseModel):
    model_config = ConfigDict(frozen=True)
    anki_card_id: int
    anki_note_id: int
    type: Literal["basic", "reversed", "cloze"]
    front_md: str
    back_md: str
    cloze_md: str
    cloze_index: int | None  # which {{cN::…}} this Anki card tests (Anki makes one card per deletion)
    tags: tuple[str, ...]
    suspended: bool
    media: tuple[str, ...]


class ImportedReview(BaseModel):
    model_config = ConfigDict(frozen=True)
    anki_card_id: int
    reviewed_at: datetime
    rating: int  # 1 Again, 2 Hard, 3 Good, 4 Easy
    response_ms: int
    kind: Literal["learn", "review", "relearn", "filtered"]


class ImportedDeck(BaseModel):
    model_config = ConfigDict(frozen=True)
    cards: tuple[ImportedCard, ...]
    reviews: tuple[ImportedReview, ...]  # chronological; manual reschedules excluded
    media_map: dict[str, str]  # zip member name → original filename


_REVLOG_KIND: dict[int, Literal["learn", "review", "relearn", "filtered"]] = {
    0: "learn",
    1: "review",
    2: "relearn",
    3: "filtered",
}


def import_apkg(path: Path) -> ImportedDeck:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        member = (
            "collection.anki21"
            if "collection.anki21" in names
            else "collection.anki2"
            if "collection.anki2" in names
            else None
        )
        if member is None:
            if "collection.anki21b" in names:
                raise UnsupportedAnkiFormat(
                    "This deck uses Anki's newest export format. In Anki, re-export it with "
                    "'Support older Anki versions' checked, then import that file."
                )
            raise UnsupportedAnkiFormat("not an Anki package (no collection database found)")
        media_map: dict[str, str] = json.loads(zf.read("media")) if "media" in names else {}
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "collection.sqlite"
            db_path.write_bytes(zf.read(member))
            # closing(): `with sqlite3.connect()` only commits; the file must be closed before the temp dir is removed
            with closing(sqlite3.connect(db_path)) as db:
                return _read_collection(db, media_map)


def _read_collection(db: sqlite3.Connection, media_map: dict[str, str]) -> ImportedDeck:
    (models_json,) = db.execute("SELECT models FROM col").fetchone()
    models = {int(k): v for k, v in json.loads(models_json).items()}
    notes = {nid: (mid, flds, tags) for nid, mid, flds, tags in db.execute("SELECT id, mid, flds, tags FROM notes")}

    cards: list[ImportedCard] = []
    for cid, nid, ord_, queue in db.execute("SELECT id, nid, ord, queue FROM cards ORDER BY id"):
        mid, flds, tags = notes[nid]
        model = models.get(mid, {})
        fields = flds.split("\x1f")
        converted = [anki_html_to_md(f) for f in fields]
        media = tuple(m for _, ms in converted for m in ms)
        texts = [t for t, _ in converted] + ["", ""]
        tag_list = tuple(t for t in tags.split() if t)
        if model.get("type") == 1:
            cards.append(
                ImportedCard(
                    anki_card_id=cid,
                    anki_note_id=nid,
                    type="cloze",
                    front_md="",
                    back_md=texts[1],
                    cloze_md=texts[0],
                    cloze_index=ord_ + 1,
                    tags=tag_list,
                    suspended=queue == -1,
                    media=media,
                )
            )
        else:
            front, back = (texts[1], texts[0]) if ord_ == 1 else (texts[0], texts[1])
            kind: Literal["basic", "reversed"] = "reversed" if len(model.get("tmpls", [])) > 1 else "basic"
            cards.append(
                ImportedCard(
                    anki_card_id=cid,
                    anki_note_id=nid,
                    type=kind,
                    front_md=front,
                    back_md=back,
                    cloze_md="",
                    cloze_index=None,
                    tags=tag_list,
                    suspended=queue == -1,
                    media=media,
                )
            )

    reviews = [
        ImportedReview(
            anki_card_id=cid,
            reviewed_at=datetime.fromtimestamp(rid / 1000, tz=UTC),
            rating=min(4, max(1, ease)),
            response_ms=max(0, int(time_ms)),
            kind=_REVLOG_KIND[rtype],
        )
        for rid, cid, ease, time_ms, rtype in db.execute("SELECT id, cid, ease, time, type FROM revlog ORDER BY id")
        if rtype in _REVLOG_KIND and ease > 0  # type 4 = manual reschedule, ease 0 = not a real answer
    ]
    return ImportedDeck(cards=tuple(cards), reviews=tuple(reviews), media_map=media_map)

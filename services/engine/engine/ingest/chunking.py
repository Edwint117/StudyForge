"""Semantic chunking (ING-06): ``NormalizedDoc`` → typed, size-bounded chunks with provenance.

Boundaries: headings (level ≤ 3), slide changes, labelled blocks ("Definition", "Theorem", "Proof", "Example",
"Question 3", …), code blocks, and size. Transcripts are grouped into ~90 s windows. Chunks stay under
``MAX_TOKENS`` so they fit the embedding model's 512-token window (bge-small), counting the heading path that is
prepended for embedding. Tokens are *estimated* (≈ 4 characters per token), with no tokenizer download, and the
limit leaves headroom for estimation error.

Content types: definition, theorem, proof, formula, example, code, question, text.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from engine.ingest.normalized import Block, NormalizedDoc

VERSION = "chunking-1"

ContentType = Literal["definition", "theorem", "proof", "formula", "example", "code", "question", "text"]

MAX_TOKENS = 400  # hard limit incl. heading path; ~20% headroom under 512 for estimation error
TARGET_TOKENS = 250  # start a new chunk at the next block boundary after this size
MIN_TOKENS = 40  # tiny trailing pieces are merged into the previous chunk of the same section
TRANSCRIPT_WINDOW_MS = 90_000
CHARS_PER_TOKEN = 4

_LABEL = re.compile(
    r"^\s*(?:\*\*|__)?\s*(?P<label>definition|def\.|theorem|lemma|corollary|proposition|proof|example|ex\.|"
    r"exercise|problem|question|q\.)\s*(?:\d+(?:\.\d+)*)?\s*[.:)]?",
    re.IGNORECASE,
)
_LABEL_TYPE: dict[str, ContentType] = {
    "definition": "definition", "def.": "definition",
    "theorem": "theorem", "lemma": "theorem", "corollary": "theorem", "proposition": "theorem",
    "proof": "proof",
    "example": "example", "ex.": "example",
    "exercise": "question", "problem": "question", "question": "question", "q.": "question",
}  # fmt: skip
_QED = re.compile(r"(∎|□|\\qed|\bQ\.?E\.?D\.?)\s*$", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\\$])")


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN)) if text else 0


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int
    content_md: str
    content_type: ContentType
    heading_path: tuple[str, ...]
    page_start: int | None = None
    page_end: int | None = None
    slide: int | None = None
    t_start_ms: int | None = None
    t_end_ms: int | None = None
    token_estimate: int
    content_hash: str
    min_ocr_confidence: float | None = None

    def embedding_text(self) -> str:
        """What gets embedded: the heading path gives short chunks their context."""
        prefix = " > ".join(self.heading_path)
        return f"{prefix}\n\n{self.content_md}" if prefix else self.content_md


def content_hash(text: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", text).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class _Acc:
    blocks: list[Block] = field(default_factory=list)
    label: ContentType | None = None
    heading_path: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return "\n\n".join(_render(b) for b in self.blocks)

    def tokens(self) -> int:
        return estimate_tokens(self.text)


def _render(b: Block) -> str:
    if b.kind == "code":
        return f"```{b.language or ''}\n{b.text}\n```"
    if b.kind == "math":
        return f"$$\n{b.text}\n$$"
    if b.kind == "speaker_notes":
        return f"> Speaker notes: {b.text}"
    return b.text


def _label_of(b: Block) -> ContentType | None:
    if b.kind not in ("paragraph", "list"):
        return None
    m = _LABEL.match(b.text)
    return _LABEL_TYPE[m.group("label").lower()] if m else None


def _classify(acc: _Acc) -> ContentType:
    if acc.label:
        return acc.label
    kinds = [b.kind for b in acc.blocks]
    if kinds and all(k == "code" for k in kinds):
        return "code"
    math_chars = sum(len(b.text) for b in acc.blocks if b.kind == "math")
    total_chars = sum(len(b.text) for b in acc.blocks) or 1
    if math_chars / total_chars >= 0.5:
        return "formula"
    return "text"


def _split_oversized(b: Block, budget: int) -> list[Block]:
    """Split a single block that alone exceeds the budget: by sentences (prose) or lines (code/math/tables)."""
    if estimate_tokens(_render(b)) <= budget:
        return [b]
    pieces = b.text.split("\n") if b.kind in ("code", "math", "table", "list") else _SENTENCE.split(b.text)
    out: list[Block] = []
    current: list[str] = []
    joiner = "\n" if b.kind in ("code", "math", "table", "list") else " "
    for piece in pieces:
        candidate = joiner.join([*current, piece])
        if current and estimate_tokens(_render(b.model_copy(update={"text": candidate}))) > budget:
            out.append(b.model_copy(update={"text": joiner.join(current)}))
            current = [piece]
        else:
            current.append(piece)
    if current:
        out.append(b.model_copy(update={"text": joiner.join(current)}))
    # a single sentence/line longer than the budget gets hard-cut by characters as a last resort
    final: list[Block] = []
    for piece_block in out:
        text = piece_block.text
        limit = budget * CHARS_PER_TOKEN - 16
        while estimate_tokens(_render(piece_block.model_copy(update={"text": text}))) > budget:
            final.append(piece_block.model_copy(update={"text": text[:limit]}))
            text = text[limit:]
        final.append(piece_block.model_copy(update={"text": text}))
    return final


def _chunk(acc: _Acc, ordinal: int) -> Chunk:
    text = acc.text
    pages = [b.page for b in acc.blocks if b.page is not None]
    slides = [b.slide for b in acc.blocks if b.slide is not None]
    starts = [b.t_start_ms for b in acc.blocks if b.t_start_ms is not None]
    ends = [b.t_end_ms for b in acc.blocks if b.t_end_ms is not None]
    confs = [b.ocr_confidence for b in acc.blocks if b.ocr_confidence is not None]
    return Chunk(
        ordinal=ordinal,
        content_md=text,
        content_type=_classify(acc),
        heading_path=acc.heading_path,
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        slide=slides[0] if slides else None,
        t_start_ms=min(starts) if starts else None,
        t_end_ms=max(ends) if ends else None,
        token_estimate=estimate_tokens(text),
        content_hash=content_hash(text),
        min_ocr_confidence=min(confs) if confs else None,
    )


def _body_budget(heading_path: Sequence[str]) -> int:
    return MAX_TOKENS - estimate_tokens(" > ".join(heading_path) + "\n\n")


def chunk_document(doc: NormalizedDoc) -> list[Chunk]:
    if doc.source_kind in ("audio", "video"):
        return _chunk_transcript(doc.blocks)

    chunks: list[Chunk] = []
    headings: list[tuple[int, str]] = []
    acc = _Acc()

    def flush() -> None:
        nonlocal acc
        if acc.blocks:
            chunks.append(_chunk(acc, len(chunks)))
        acc = _Acc(heading_path=tuple(h for _, h in headings))

    for block in doc.blocks:
        if block.kind == "heading" and block.level is not None:
            flush()
            if block.level <= 3:
                headings[:] = [h for h in headings if h[0] < block.level]
                headings.append((block.level, block.text.strip()))
                acc.heading_path = tuple(h for _, h in headings)
            else:
                acc.blocks.append(block.model_copy(update={"kind": "paragraph", "text": f"**{block.text}**"}))
            continue

        label = _label_of(block)
        slide_changed = bool(acc.blocks) and block.slide is not None and acc.blocks[-1].slide not in (None, block.slide)
        closes_proof = acc.label == "proof" and bool(acc.blocks) and _QED.search(acc.blocks[-1].text) is not None
        starts_code_chunk = block.kind == "code" and bool(acc.blocks) and acc.label not in ("example", "question")
        if (
            label
            or slide_changed
            or closes_proof
            or starts_code_chunk
            or (acc.blocks and acc.blocks[-1].kind == "code" and acc.label is None and block.kind != "code")
        ):
            flush()
        if label:
            acc.label = label

        budget = _body_budget(acc.heading_path)
        for piece in _split_oversized(block, budget):
            projected = estimate_tokens((acc.text + "\n\n" + _render(piece)) if acc.blocks else _render(piece))
            if acc.blocks and (projected > budget or acc.tokens() >= TARGET_TOKENS):
                keep_label = acc.label
                flush()
                acc.label = keep_label  # a long proof/example continues as the same type
            acc.blocks.append(piece)
    flush()
    return _merge_tiny(chunks)


def _merge_tiny(chunks: list[Chunk]) -> list[Chunk]:
    """Merge a tiny untyped chunk into its predecessor in the same section when it still fits."""
    out: list[Chunk] = []
    for c in chunks:
        prev = out[-1] if out else None
        if (
            prev is not None
            and c.token_estimate < MIN_TOKENS
            and c.content_type == "text"
            and prev.content_type == "text"
            and c.heading_path == prev.heading_path
            and c.slide == prev.slide
        ):
            merged_text = prev.content_md + "\n\n" + c.content_md
            if estimate_tokens(merged_text) <= _body_budget(prev.heading_path):
                out[-1] = prev.model_copy(
                    update={
                        "content_md": merged_text,
                        "token_estimate": estimate_tokens(merged_text),
                        "content_hash": content_hash(merged_text),
                        "page_end": max(p for p in (prev.page_end, c.page_end) if p is not None)
                        if (prev.page_end or c.page_end)
                        else None,
                    }
                )
                continue
        out.append(c)
    return [c.model_copy(update={"ordinal": i}) for i, c in enumerate(out)]


def _chunk_transcript(blocks: Iterable[Block]) -> list[Chunk]:
    chunks: list[Chunk] = []
    acc = _Acc()
    for b in blocks:
        if b.kind == "heading":
            continue
        window_full = (
            acc.blocks
            and acc.blocks[0].t_start_ms is not None
            and b.t_end_ms is not None
            and b.t_end_ms - acc.blocks[0].t_start_ms > TRANSCRIPT_WINDOW_MS
        )
        for piece in _split_oversized(b, MAX_TOKENS):
            too_big = acc.blocks and estimate_tokens(acc.text + " " + piece.text) > MAX_TOKENS
            if window_full or too_big:
                chunks.append(_chunk(acc, len(chunks)))
                acc = _Acc()
                window_full = False
            acc.blocks.append(piece)
    if acc.blocks:
        chunks.append(_chunk(acc, len(chunks)))
    return chunks

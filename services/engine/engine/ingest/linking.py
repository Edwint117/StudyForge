"""Cross-reference suggestions between course assets (ING-08): slide ↔ textbook page ↔ lab ↔ past-exam question.

Candidates come from a per-user vector search (similar chunks in *other* documents of the same course). A link's
confidence blends embedding similarity with shared concepts. Links the user rejected are never re-suggested, and
confirmed links are left alone.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = "linking-1"

SIM_WEIGHT = 0.7
CONCEPT_WEIGHT = 0.3
CONCEPTS_FOR_FULL_CREDIT = 3
SUGGEST_THRESHOLD = 0.75
MAX_LINKS_PER_CHUNK = 3

DocKind = Literal["material", "syllabus", "past_exam", "lab", "textbook", "lecture_audio", "notes_handwritten"]
LinkKind = Literal["slide_textbook", "lecture_lab", "material_past_exam", "transcript_slide"]


class ChunkRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    chunk_id: str
    document_id: str
    doc_kind: DocKind
    source_kind: str  # pdf / pptx / audio / …
    concept_ids: tuple[str, ...] = ()
    content_type: str = "text"


class LinkSuggestion(BaseModel):
    model_config = ConfigDict(frozen=True)
    from_chunk_id: str
    to_chunk_id: str
    kind: LinkKind
    confidence: float = Field(ge=0, le=1)


def link_kind(a: ChunkRef, b: ChunkRef) -> LinkKind | None:
    """Which relationship two chunks from different documents represent; None = not a link we track."""
    kinds = {a.doc_kind, b.doc_kind}
    if "past_exam" in kinds and kinds != {"past_exam"}:
        return "material_past_exam"
    if "lecture_audio" in kinds and ("pptx" in {a.source_kind, b.source_kind} or "material" in kinds):
        return "transcript_slide"
    if "lab" in kinds and kinds & {"material", "lecture_audio", "textbook"}:
        return "lecture_lab"
    if "textbook" in kinds and "material" in kinds:
        return "slide_textbook"
    return None


def link_confidence(similarity: float, a: ChunkRef, b: ChunkRef) -> float:
    shared = len(set(a.concept_ids) & set(b.concept_ids))
    concept_score = min(1.0, shared / CONCEPTS_FOR_FULL_CREDIT)
    return round(max(0.0, min(1.0, SIM_WEIGHT * similarity + CONCEPT_WEIGHT * concept_score)), 4)


def suggest_links(
    chunk: ChunkRef,
    candidates: Sequence[tuple[ChunkRef, float]],
    decided_pairs: Iterable[tuple[str, str]] = (),
) -> list[LinkSuggestion]:
    """``candidates``: (other chunk, cosine similarity). ``decided_pairs``: (from, to) pairs the user already
    confirmed or rejected, in either direction, which are skipped."""
    decided = {frozenset(p) for p in decided_pairs}
    out: list[LinkSuggestion] = []
    for other, sim in candidates:
        if other.document_id == chunk.document_id or frozenset((chunk.chunk_id, other.chunk_id)) in decided:
            continue
        kind = link_kind(chunk, other)
        if kind is None:
            continue
        conf = link_confidence(sim, chunk, other)
        if conf >= SUGGEST_THRESHOLD:
            out.append(
                LinkSuggestion(from_chunk_id=chunk.chunk_id, to_chunk_id=other.chunk_id, kind=kind, confidence=conf)
            )
    out.sort(key=lambda s: (-s.confidence, s.to_chunk_id))
    return out[:MAX_LINKS_PER_CHUNK]

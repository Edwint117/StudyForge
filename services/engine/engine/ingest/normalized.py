"""``NormalizedDoc``: the common format every parser adapter produces (doc 06 §3, ING-03/05).

Parsers (Docling/PyMuPDF/python-pptx/python-docx, OCR, speech-to-text) all emit an ordered list of blocks with
provenance (page, slide, or audio timestamps). Everything downstream (chunking, concept extraction, the viewer's
deep links) only reads this format, so adding a parser never changes the rest of the pipeline.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "normalized-doc-1"

BlockKind = Literal["heading", "paragraph", "list", "code", "math", "table", "caption", "transcript", "speaker_notes"]


class Block(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: BlockKind
    text: str  # Markdown; math as LaTeX ($...$ inline, display blocks use kind="math" with raw LaTeX)
    level: int | None = Field(default=None, ge=1, le=6)  # headings only
    language: str | None = None  # code only
    page: int | None = Field(default=None, ge=1)
    slide: int | None = Field(default=None, ge=1)
    t_start_ms: int | None = Field(default=None, ge=0)
    t_end_ms: int | None = Field(default=None, ge=0)
    speaker: str | None = None
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _check(self) -> Block:
        if self.kind == "heading" and self.level is None:
            raise ValueError("headings need a level")
        if (self.t_start_ms is None) != (self.t_end_ms is None):
            raise ValueError("t_start_ms and t_end_ms go together")
        if self.t_start_ms is not None and self.t_end_ms is not None and self.t_end_ms < self.t_start_ms:
            raise ValueError("t_end_ms before t_start_ms")
        return self


class NormalizedDoc(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: Literal["pdf", "pptx", "docx", "markdown", "text", "image", "audio", "video"]
    doc_kind: Literal["material", "syllabus", "past_exam", "lab", "textbook", "lecture_audio", "notes_handwritten"] = (
        "material"
    )
    title: str | None = None
    blocks: tuple[Block, ...]
    parser: str  # adapter id, e.g. "parse.docling"
    parser_version: str

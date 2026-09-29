"""Retrieval post-processing for RAG (doc 06 §4; ING-11) and citation validation.

The database does the user- and course-scoped candidate search (``search_chunks`` RPC: FTS + pgvector). This
module fuses and reranks the candidates, packs a context within a token budget, decides whether anything is
relevant enough to answer from, and validates the ``[[chunk:<id>]]`` citation markers in model output.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

VERSION = "retrieval-1"

RRF_K = 60
CANDIDATES = 24
FINAL_K = 8
CONTEXT_TOKEN_BUDGET = 6000
# Chunk-type priority for grounding (definitions/theorems answer "what is" questions best).
TYPE_BOOST: dict[str, float] = {
    "definition": 1.15,
    "theorem": 1.12,
    "formula": 1.08,
    "example": 1.0,
    "proof": 1.0,
    "code": 1.0,
    "question": 0.9,
    "text": 1.0,
}
CONCEPT_OVERLAP_WEIGHT = 0.25
# Tuned by the tutor_socratic eval (doc 06 §7); below this best vector similarity → "not in your materials".
RELEVANCE_THRESHOLD = 0.35

_MARKER = re.compile(r"\[\[chunk:([A-Za-z0-9_-]+)\]\]")


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    chunk_id: str
    content_type: str = "text"
    concept_ids: tuple[str, ...] = ()
    token_estimate: int = Field(ge=0)
    vector_similarity: float | None = None  # cosine similarity, when the chunk came from the vector search


def rrf_fuse(*rankings: Sequence[str], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal rank fusion: score(d) = Σ 1 / (k + rank_i(d)), with ranks 1-based per list."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def rerank(candidates: Iterable[Candidate], fused: dict[str, float], query_concepts: Iterable[str]) -> list[Candidate]:
    """Fused score × type boost × (1 + weight × concept overlap). Ties broken by chunk id for determinism."""
    wanted = set(query_concepts)

    def score(c: Candidate) -> float:
        overlap = len(wanted & set(c.concept_ids)) / len(wanted) if wanted else 0.0
        return fused.get(c.chunk_id, 0.0) * TYPE_BOOST.get(c.content_type, 1.0) * (1 + CONCEPT_OVERLAP_WEIGHT * overlap)

    return sorted(candidates, key=lambda c: (-score(c), c.chunk_id))


def pack_context(ranked: Sequence[Candidate], k: int = FINAL_K, budget: int = CONTEXT_TOKEN_BUDGET) -> list[Candidate]:
    """Top ``k`` chunks that fit the token budget (skips a too-large chunk and keeps trying smaller ones)."""
    out: list[Candidate] = []
    used = 0
    for c in ranked:
        if len(out) >= k:
            break
        if used + c.token_estimate <= budget:
            out.append(c)
            used += c.token_estimate
    return out


def has_relevant_material(candidates: Iterable[Candidate], threshold: float = RELEVANCE_THRESHOLD) -> bool:
    best = max((c.vector_similarity for c in candidates if c.vector_similarity is not None), default=None)
    return best is not None and best >= threshold


def retrieve(
    fts_ranking: Sequence[str],
    vector_ranking: Sequence[str],
    candidates: Sequence[Candidate],
    query_concepts: Iterable[str] = (),
) -> tuple[list[Candidate], bool]:
    """Full post-processing: fuse → keep the top 24 → rerank → pack. Returns (context, relevant_enough)."""
    fused = rrf_fuse(fts_ranking, vector_ranking)
    by_id = {c.chunk_id: c for c in candidates}
    top = sorted((cid for cid in fused if cid in by_id), key=lambda cid: (-fused[cid], cid))[:CANDIDATES]
    ranked = rerank((by_id[cid] for cid in top), fused, query_concepts)
    return pack_context(ranked), has_relevant_material(by_id[cid] for cid in top)


class CitationCheck(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str  # output with invalid markers removed
    cited: tuple[str, ...]  # valid cited chunk ids, in first-seen order
    invalid: int  # count of removed markers (metric: tutor.invalid_citation)


def validate_citations(output: str, retrieved_ids: Iterable[str]) -> CitationCheck:
    allowed = set(retrieved_ids)
    cited: list[str] = []
    invalid = 0

    def replace(m: re.Match[str]) -> str:
        nonlocal invalid
        cid = m.group(1)
        if cid in allowed:
            if cid not in cited:
                cited.append(cid)
            return m.group(0)
        invalid += 1
        return ""

    text = _MARKER.sub(replace, output)
    text = re.sub(r"[ \t]{2,}", " ", text).replace(" .", ".").replace(" ,", ",")
    return CitationCheck(text=text, cited=tuple(cited), invalid=invalid)

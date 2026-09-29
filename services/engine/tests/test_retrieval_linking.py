import pytest

from engine.ingest.linking import ChunkRef, link_confidence, link_kind, suggest_links
from engine.ingest.retrieval import (
    Candidate,
    has_relevant_material,
    pack_context,
    rerank,
    retrieve,
    rrf_fuse,
    validate_citations,
)


# ---------------------------------------------------------------- RRF + rerank + packing
def test_rrf_rewards_agreement_between_lists() -> None:
    scores = rrf_fuse(["a", "b", "c"], ["c", "a", "d"])
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert max(scores, key=scores.__getitem__) == "a"
    assert scores["d"] == pytest.approx(1 / 63)


def test_rerank_boosts_definitions_and_concept_overlap() -> None:
    fused = {"x": 0.030, "y": 0.029, "z": 0.029}
    cands = [
        Candidate(chunk_id="x", content_type="text", token_estimate=10),
        Candidate(chunk_id="y", content_type="definition", token_estimate=10),
        Candidate(chunk_id="z", content_type="text", concept_ids=("bayes",), token_estimate=10),
    ]
    order = [c.chunk_id for c in rerank(cands, fused, ["bayes"])]
    # full concept match (x1.25) outranks the definition boost (x1.15); both beat a plain higher-fused chunk
    assert order == ["z", "y", "x"]


def test_pack_context_respects_k_and_budget() -> None:
    ranked = [Candidate(chunk_id=str(i), token_estimate=t) for i, t in enumerate([4000, 3000, 1500, 400, 100])]
    packed = [c.chunk_id for c in pack_context(ranked, k=3, budget=6000)]
    assert packed == ["0", "2", "3"]  # 3000 doesn't fit after 4000; smaller ones still do


def test_relevance_threshold_and_full_retrieve() -> None:
    cands = [
        Candidate(chunk_id="a", token_estimate=50, vector_similarity=0.2),
        Candidate(chunk_id="b", token_estimate=50, vector_similarity=0.3),
    ]
    assert not has_relevant_material(cands)
    context, relevant = retrieve(["a"], ["b", "a"], cands)
    assert [c.chunk_id for c in context] == ["a", "b"] and relevant is False
    fts_only = [Candidate(chunk_id="a", token_estimate=5)]
    assert not has_relevant_material(fts_only)  # keyword-only hits don't prove semantic relevance


def test_citation_validation_strips_hallucinated_ids() -> None:
    out = validate_citations(
        "Bayes relates priors [[chunk:c1]] and likelihoods [[chunk:zzz]]. See also [[chunk:c2]] [[chunk:c1]].",
        ["c1", "c2"],
    )
    assert out.cited == ("c1", "c2") and out.invalid == 1
    assert "zzz" not in out.text and "likelihoods." in out.text


# ---------------------------------------------------------------- asset links
def ref(cid: str, doc: str, doc_kind: str, source: str = "pdf", concepts: tuple[str, ...] = ()) -> ChunkRef:
    return ChunkRef(chunk_id=cid, document_id=doc, doc_kind=doc_kind, source_kind=source, concept_ids=concepts)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("a", "b", "kind"),
    [
        (ref("s", "d1", "material", "pptx"), ref("t", "d2", "textbook"), "slide_textbook"),
        (ref("s", "d1", "material"), ref("q", "d2", "past_exam"), "material_past_exam"),
        (ref("s", "d1", "material", "pptx"), ref("l", "d2", "lecture_audio", "audio"), "transcript_slide"),
        (ref("l", "d1", "lab"), ref("m", "d2", "material"), "lecture_lab"),
        (ref("x", "d1", "syllabus"), ref("y", "d2", "material"), None),
    ],
)
def test_link_kind(a: ChunkRef, b: ChunkRef, kind: str | None) -> None:
    assert link_kind(a, b) == kind


def test_suggest_links_threshold_rejections_and_cap() -> None:
    slide = ref("s1", "slides", "material", "pptx", ("bayes", "prior", "posterior"))
    cands = [
        (ref("t1", "book", "textbook", concepts=("bayes", "prior", "posterior")), 0.80),  # .56 + .3 = .86
        (ref("t2", "book", "textbook"), 0.95),  # .665, no shared concepts -> below threshold
        (ref("t3", "book", "textbook", concepts=("bayes",)), 0.95),  # .665 + .1 = .765
        (ref("q1", "exam", "past_exam", concepts=("bayes", "prior")), 0.90),  # .63 + .2 = .83
        (ref("s2", "slides", "material", "pptx", ("bayes",)), 0.99),  # same document: skipped
        (ref("t4", "book", "textbook", concepts=("bayes", "prior", "posterior")), 0.99),  # user rejected before
    ]
    out = suggest_links(slide, cands, decided_pairs=[("t4", "s1")])
    assert [(s.to_chunk_id, s.kind) for s in out] == [
        ("t1", "slide_textbook"),
        ("q1", "material_past_exam"),
        ("t3", "slide_textbook"),
    ]
    assert out[0].confidence == pytest.approx(0.86)
    assert link_confidence(2.0, slide, slide) == 1.0  # clamped

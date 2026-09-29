from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from engine.ingest.chunking import MAX_TOKENS, chunk_document, content_hash, estimate_tokens
from engine.ingest.normalized import Block, NormalizedDoc


def doc(*blocks: Block, source: Any = "pdf", kind: Any = "material") -> NormalizedDoc:
    return NormalizedDoc(source_kind=source, doc_kind=kind, blocks=blocks, parser="parse.test", parser_version="1")


def h(text: str, level: int = 1, page: int = 1) -> Block:
    return Block(kind="heading", text=text, level=level, page=page)


def p(text: str, page: int = 1, **kw: Any) -> Block:
    return Block(kind="paragraph", text=text, page=page, **kw)


def test_headings_define_sections_and_paths() -> None:
    chunks = chunk_document(
        doc(
            h("Probability"),
            p("Intro to probability spaces and events."),
            h("Conditional probability", level=2),
            p("P(A|B) is the probability of A given B."),
            h("Tiny detail", level=4),
            p("A level-4 heading stays inside its section."),
        )
    )
    assert [c.heading_path for c in chunks] == [("Probability",), ("Probability", "Conditional probability")]
    assert "**Tiny detail**" in chunks[1].content_md


def test_labelled_blocks_are_typed_and_split() -> None:
    chunks = chunk_document(
        doc(
            h("Bayes"),
            p("**Definition 2.1.** A partition of S is a set of disjoint events whose union is S."),
            p("Theorem 2.2 (Bayes). P(A|B) = P(B|A)P(A)/P(B)."),
            p("Proof. By the definition of conditional probability, both sides equal P(A∩B)/P(B). ∎"),
            p("This result underpins spam filters."),
            p("Example 2.3: A test is 99% accurate..."),
        )
    )
    assert [c.content_type for c in chunks] == ["definition", "theorem", "proof", "text", "example"]


def test_code_blocks_are_their_own_chunks_but_stay_inside_examples() -> None:
    code = Block(kind="code", text="int main(void) { return 0; }", language="c", page=2)
    chunks = chunk_document(
        doc(h("C basics"), p("Every program has a main function.", page=2), code, p("Next topic.", page=2))
    )
    assert [c.content_type for c in chunks] == ["text", "code", "text"]
    assert chunks[1].content_md.startswith("```c")

    in_example = chunk_document(doc(p("Example 1: the smallest C program."), code))
    assert len(in_example) == 1 and in_example[0].content_type == "example"


def test_formula_heavy_chunk() -> None:
    chunks = chunk_document(
        doc(
            p("Normal pdf:"),
            Block(kind="math", text=r"f(x)=\frac{1}{\sigma\sqrt{2\pi}}e^{-\frac{(x-\mu)^2}{2\sigma^2}}"),
        )
    )
    assert chunks[0].content_type == "formula"
    assert "$$" in chunks[0].content_md


def test_slides_split_per_slide_with_speaker_notes() -> None:
    chunks = chunk_document(
        doc(
            Block(kind="paragraph", text="Slide one content", slide=1),
            Block(kind="speaker_notes", text="Mention the history.", slide=1),
            Block(kind="paragraph", text="Slide two content", slide=2),
            source="pptx",
        )
    )
    assert [c.slide for c in chunks] == [1, 2]
    assert "Speaker notes: Mention the history." in chunks[0].content_md


def test_past_exam_questions_split() -> None:
    chunks = chunk_document(doc(p("Question 1. Compute P(A∪B)."), p("Question 2. Prove that ..."), kind="past_exam"))
    assert [c.content_type for c in chunks] == ["question", "question"]


def test_long_paragraph_is_split_by_sentences_and_pages_tracked() -> None:
    sentence = "The quick brown fox jumps over the lazy dog near the riverbank today. "
    long_text = sentence * 120  # ~2,100 tokens
    chunks = chunk_document(doc(h("Long"), p(long_text, page=3), p("Tail on the next page.", page=4)))
    assert len(chunks) >= 5
    assert all(c.token_estimate <= MAX_TOKENS for c in chunks)
    assert chunks[0].page_start == 3 and chunks[-1].page_end == 4


def test_transcript_windows() -> None:
    segs = [
        Block(
            kind="transcript", text=f"Segment {i} talks about limits.", t_start_ms=i * 20_000, t_end_ms=(i + 1) * 20_000
        )
        for i in range(10)
    ]
    chunks = chunk_document(doc(*segs, source="audio", kind="lecture_audio"))
    assert len(chunks) == 3
    assert chunks[0].t_start_ms == 0 and chunks[0].t_end_ms == 80_000
    assert all((c.t_end_ms or 0) - (c.t_start_ms or 0) <= 90_000 for c in chunks)
    assert chunks[-1].t_end_ms == 200_000


def test_content_hash_ignores_whitespace() -> None:
    assert content_hash("a  b\n c") == content_hash("a b c")
    assert content_hash("a b") != content_hash("a c")


def test_ocr_confidence_is_carried() -> None:
    chunks = chunk_document(doc(p("scanned text", ocr_confidence=0.55), p("more", ocr_confidence=0.9), source="image"))
    assert chunks[0].min_ocr_confidence == 0.55


def test_block_validation() -> None:
    with pytest.raises(ValidationError):
        Block(kind="heading", text="no level")
    with pytest.raises(ValidationError):
        Block(kind="transcript", text="x", t_start_ms=5)
    with pytest.raises(ValidationError):
        Block(kind="transcript", text="x", t_start_ms=5, t_end_ms=1)


words = st.text(alphabet=st.characters(categories=("Ll", "Lu", "Nd")), min_size=1, max_size=12)
paragraph = st.lists(words, min_size=1, max_size=300).map(lambda ws: " ".join(ws) + ".")
block_strategy = st.one_of(
    paragraph.map(lambda t: Block(kind="paragraph", text=t, page=1)),
    words.map(lambda t: Block(kind="heading", text=t, level=2)),
    paragraph.map(lambda t: Block(kind="code", text=t.replace(" ", "\n"), language="py")),
)


@settings(max_examples=60, deadline=None)
@given(st.lists(block_strategy, min_size=1, max_size=25))
def test_chunking_invariants(blocks: list[Block]) -> None:
    chunks = chunk_document(doc(*blocks))
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert estimate_tokens(c.embedding_text()) <= MAX_TOKENS + 2
        assert c.content_md.strip()
    # no content is lost: every word of every non-heading block appears in some chunk
    all_text = " ".join(c.content_md for c in chunks).replace("\n", " ")
    for b in blocks:
        if b.kind != "heading":
            for w in b.text.replace("\n", " ").split():
                assert w in all_text

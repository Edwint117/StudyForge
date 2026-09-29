"""Structured-output models for the LLM tasks that had no engine model yet (doc 06 §2).

Tasks already modelled elsewhere keep their model: ``grade.rubric`` → ``grading.LlmRubricOutput``,
``feynman.analyze`` → ``feynman.FeynmanOutput``, ``syllabus.extract`` → ``syllabus.SyllabusExtraction``.
Each model here converts into the engine type its consumer already takes (``Card`` for the linter,
``ExtractedConcept`` / ``ExtractedEdge`` for the graph merge, the answer specs for verification).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.algorithms.card_quality import Card, CardType
from engine.algorithms.question_verify import AnswerKind
from engine.algorithms.verification import NumericSpec, SympySpec, TextSpec
from engine.ingest.chunking import ContentType
from engine.ingest.graph import ConceptKind, ExtractedConcept, ExtractedEdge
from engine.ingest.linking import LinkKind

VERSION = "llm-outputs-1"

QuestionType = Literal["mcq", "short", "numeric", "multi_step", "code", "proof"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------- cards.generate
class KeypointsSpec(_Frozen):
    """``llm_keypoints`` answer check (doc 05 §8): judged by ``answer.keypoints`` against these points."""

    check: Literal["llm_keypoints"] = "llm_keypoints"
    keypoints: tuple[str, ...] = Field(min_length=1)


CardAnswerSpec = Annotated[TextSpec | NumericSpec | SympySpec | KeypointsSpec, Field(discriminator="check")]


class LlmCard(_Frozen):
    type: CardType
    front_md: str = ""
    back_md: str = ""
    cloze_md: str = ""
    answer_spec: CardAnswerSpec
    source_chunk_ids: tuple[str, ...] = Field(min_length=1)  # every card cites its source (COMP-01)
    concept_names: tuple[str, ...] = ()

    def to_card(self) -> Card:
        return Card(type=self.type, front_md=self.front_md, back_md=self.back_md, cloze_md=self.cloze_md)


class CardsGenerateOutput(_Frozen):
    cards: tuple[LlmCard, ...]


# ---------------------------------------------------------------- cards.lint
LintCode = Literal["multiple_facts", "ambiguous", "answer_leak", "unsupported_by_source", "too_long", "other"]


class LlmLintIssue(_Frozen):
    code: LintCode
    message: str


class CardLintVerdict(_Frozen):
    index: int = Field(ge=0)  # position of the card in the request
    passed: bool
    issues: tuple[LlmLintIssue, ...] = ()

    @model_validator(mode="after")
    def _issues_when_failed(self) -> CardLintVerdict:
        if not self.passed and not self.issues:
            raise ValueError("a failed card needs at least one issue")
        return self


class CardsLintOutput(_Frozen):
    results: tuple[CardLintVerdict, ...]


# ---------------------------------------------------------------- ingest.tag_chunks
class ChunkTag(_Frozen):
    chunk_id: str
    content_type: ContentType
    concept_names: tuple[str, ...] = ()


class ChunkTagsOutput(_Frozen):
    tags: tuple[ChunkTag, ...]


# ---------------------------------------------------------------- ingest.extract_concepts
class LlmConcept(_Frozen):
    temp_id: str
    name: str
    kind: ConceptKind
    summary_md: str = ""
    latex: str | None = None
    importance: float = Field(default=0.5, ge=0, le=1)
    aliases: tuple[str, ...] = ()
    chunk_ids: tuple[str, ...] = ()
    role: Literal["defines", "uses", "example_of"] = "uses"


class ConceptExtractionOutput(_Frozen):
    concepts: tuple[LlmConcept, ...]
    edges: tuple[ExtractedEdge, ...] = ()

    @model_validator(mode="after")
    def _edges_reference_concepts(self) -> ConceptExtractionOutput:
        ids = [c.temp_id for c in self.concepts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate temp_id")
        known = set(ids)
        for e in self.edges:
            if e.from_temp not in known or e.to_temp not in known:
                raise ValueError(f"edge {e.from_temp}->{e.to_temp} references an unknown concept")
        return self

    def to_extracted(self) -> list[ExtractedConcept]:
        """Input for ``graph.merge_concepts`` (embeddings are added by the caller)."""
        return [ExtractedConcept(**c.model_dump()) for c in self.concepts]


# ---------------------------------------------------------------- ingest.link_assets (tie-break)
class LinkTiebreakOutput(_Frozen):
    decision: Literal["link", "no_link"]
    kind: LinkKind | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str = ""

    @model_validator(mode="after")
    def _kind_iff_link(self) -> LinkTiebreakOutput:
        if (self.decision == "link") != (self.kind is not None):
            raise ValueError("kind is required for a link and must be null otherwise")
        return self


# ---------------------------------------------------------------- question.generate / question.solve
class Choice(_Frozen):
    id: str
    text_md: str
    correct: bool


class QuestionStep(_Frozen):
    prompt_md: str
    expected: str
    answer_kind: Literal["text", "numeric", "sympy"]
    points: float = Field(gt=0)


class CodeTest(_Frozen):
    stdin: str = ""
    expected_stdout: str


class GeneratedQuestion(_Frozen):
    type: QuestionType
    stem_md: str = Field(min_length=1)
    choices: tuple[Choice, ...] = ()
    answer_kind: AnswerKind
    answer_key: str
    steps: tuple[QuestionStep, ...] = ()
    points: float = Field(gt=0)
    difficulty: int = Field(ge=1, le=5)
    concept_names: tuple[str, ...] = ()
    source_chunk_ids: tuple[str, ...] = Field(min_length=1)
    reference_solution: str | None = None
    tests: tuple[CodeTest, ...] = ()

    @model_validator(mode="after")
    def _shape(self) -> GeneratedQuestion:
        if self.type == "mcq":
            if len(self.choices) < 2 or not any(c.correct for c in self.choices):
                raise ValueError("mcq needs >= 2 choices with at least one correct")
        elif self.choices:
            raise ValueError("only mcq questions have choices")
        if self.type == "code" and (self.answer_kind != "code" or not self.reference_solution or not self.tests):
            raise ValueError("code questions need answer_kind 'code', a reference solution and tests")
        if self.type == "multi_step" and not self.steps:
            raise ValueError("multi_step questions need steps")
        if self.type != "code" and not self.answer_key.strip():
            raise ValueError("answer_key is required")
        return self


class QuestionSolveOutput(_Frozen):
    """One independent solve (``question.solve``). ``issues`` lets the solver reject a flawed question outright."""

    final_answer: str
    work_md: str = ""
    confidence: float = Field(ge=0, le=1)
    issues: tuple[Literal["ambiguous", "unsolvable", "multiple_valid_answers", "missing_information"], ...] = ()


# ---------------------------------------------------------------- answer.keypoints
class KeypointsJudgement(_Frozen):
    """doc 05 §8 ``llm_keypoints``: key-point ids the answer covers, misses, or states incorrectly."""

    covered: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    incorrect: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _disjoint(self) -> KeypointsJudgement:
        seen: set[str] = set()
        for kp in (*self.covered, *self.missing, *self.incorrect):
            if kp in seen:
                raise ValueError(f"key point {kp!r} appears in more than one list")
            seen.add(kp)
        return self


# ---------------------------------------------------------------- cheatsheet.compress
class ShortVariant(_Frozen):
    item_id: str
    short_md: str = Field(min_length=1)


class CheatsheetCompressOutput(_Frozen):
    items: tuple[ShortVariant, ...]


# ---------------------------------------------------------------- ocr.vision (paid OCR option)
class OcrVisionOutput(_Frozen):
    """Matches the ``OcrEngine.recognize`` contract (doc 06 §3)."""

    text_md: str
    latex: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)


# ---------------------------------------------------------------- tutor post-check (doc 06 §5.5)
class TutorGuardOutput(_Frozen):
    states_final_answer: bool
    evidence: str | None = None  # the sentence that gives the answer away

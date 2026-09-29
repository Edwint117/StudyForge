"""Adapter catalog, task list and the default per-plan routing (seed for ``app_config.providers``).

Tiers:
* ``free``      self-hosted in the engine; available to every plan.
* ``core_llm``  the Claude models behind core AI features; every plan (usage limited by quotas, doc 07).
* ``paid``      optional paid services; **never** used for the Free plan, and only when their API key is set.

Prices are defaults for cost *estimates* only (verify against current vendor pricing; editable in app_config).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = "routing-catalog-1"

Plan = Literal["free", "pro", "pro_plus"]
PLANS: tuple[Plan, ...] = ("free", "pro", "pro_plus")
Tier = Literal["free", "core_llm", "paid"]
Unit = Literal["input_token", "output_token", "second", "page", "none"]


class CostModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    micros_per_unit: dict[Unit, float] = Field(default_factory=dict)  # 1 USD = 1_000_000 micros

    def estimate(self, quantities: dict[Unit, float]) -> int:
        return round(sum(self.micros_per_unit.get(u, 0.0) * q for u, q in quantities.items()))


class AdapterInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    capability: Literal["parse", "ocr", "stt", "embed", "llm"]
    tier: Tier
    required_env: tuple[str, ...] = ()
    cost: CostModel = CostModel()


FREE = CostModel()


def _llm(input_usd_per_mtok: float, output_usd_per_mtok: float) -> CostModel:
    return CostModel(micros_per_unit={"input_token": input_usd_per_mtok, "output_token": output_usd_per_mtok})


CATALOG: dict[str, AdapterInfo] = {
    a.id: a
    for a in (
        # free, self-hosted
        AdapterInfo(id="parse.docling", capability="parse", tier="free"),
        AdapterInfo(id="parse.pymupdf", capability="parse", tier="free"),
        AdapterInfo(id="ocr.paddle", capability="ocr", tier="free"),
        AdapterInfo(id="ocr.trocr", capability="ocr", tier="free"),
        AdapterInfo(id="stt.faster_whisper", capability="stt", tier="free"),
        AdapterInfo(id="embed.bge_small", capability="embed", tier="free"),
        # core LLMs (Claude)
        AdapterInfo(
            id="llm.claude_sonnet",
            capability="llm",
            tier="core_llm",
            required_env=("ANTHROPIC_API_KEY",),
            cost=_llm(2.0, 10.0),
        ),
        AdapterInfo(
            id="llm.claude_haiku",
            capability="llm",
            tier="core_llm",
            required_env=("ANTHROPIC_API_KEY",),
            cost=_llm(1.0, 5.0),
        ),
        # optional paid
        AdapterInfo(
            id="ocr.claude_vision",
            capability="ocr",
            tier="paid",
            required_env=("ANTHROPIC_API_KEY",),
            cost=CostModel(micros_per_unit={"page": 4000}),
        ),
        AdapterInfo(
            id="ocr.mistral",
            capability="ocr",
            tier="paid",
            required_env=("MISTRAL_API_KEY",),
            cost=CostModel(micros_per_unit={"page": 1000}),
        ),
        AdapterInfo(
            id="stt.deepgram",
            capability="stt",
            tier="paid",
            required_env=("DEEPGRAM_API_KEY",),
            cost=CostModel(micros_per_unit={"second": 120}),
        ),
        AdapterInfo(
            id="stt.assemblyai",
            capability="stt",
            tier="paid",
            required_env=("ASSEMBLYAI_API_KEY",),
            cost=CostModel(micros_per_unit={"second": 100}),
        ),
        AdapterInfo(
            id="stt.openai",
            capability="stt",
            tier="paid",
            required_env=("OPENAI_API_KEY",),
            cost=CostModel(micros_per_unit={"second": 100}),
        ),
        AdapterInfo(
            id="embed.voyage", capability="embed", tier="paid", required_env=("VOYAGE_API_KEY",), cost=_llm(0.02, 0.0)
        ),
        AdapterInfo(
            id="embed.openai", capability="embed", tier="paid", required_env=("OPENAI_API_KEY",), cost=_llm(0.02, 0.0)
        ),
    )
}

# Task → capability. LLM tasks are grouped by the model tier they need.
SONNET_TASKS = (
    "tutor.socratic",
    "grade.rubric",
    "feynman.analyze",
    "question.generate",
    "question.solve",
    "syllabus.extract_escalate",
)
HAIKU_TASKS = (
    "cards.generate",
    "cards.lint",
    "ingest.tag_chunks",
    "ingest.extract_concepts",
    "ingest.link_assets",
    "syllabus.extract",
    "answer.keypoints",
    "cheatsheet.compress",
)
# Quality-critical tasks never silently fall back to a weaker model; they fail over to "try again later".
NO_MODEL_FALLBACK = frozenset({"grade.rubric", "question.solve"})
# Tasks whose provider must be identical for every plan (a per-plan choice would corrupt shared data).
GLOBAL_TASKS = frozenset({"embed.text"})

TASK_CAPABILITY: dict[str, str] = {
    "parse.document": "parse",
    "ocr.page": "ocr",
    "ocr.escalate": "ocr",  # second attempt for pages the first OCR read with confidence < 0.6
    "stt.transcribe": "stt",
    "embed.text": "embed",
    **dict.fromkeys(SONNET_TASKS, "llm"),
    **dict.fromkeys(HAIKU_TASKS, "llm"),
}

RoutingConfig = dict[str, dict[Plan, tuple[str, ...]]]  # task → plan → ordered adapter ids


def default_routing() -> RoutingConfig:
    paid_stt = ("stt.deepgram", "stt.assemblyai", "stt.openai", "stt.faster_whisper")
    cfg: RoutingConfig = {
        "parse.document": dict.fromkeys(PLANS, ("parse.docling", "parse.pymupdf")),
        "ocr.page": {
            "free": ("ocr.paddle", "ocr.trocr"),
            "pro": ("ocr.paddle", "ocr.trocr"),
            "pro_plus": ("ocr.claude_vision", "ocr.mistral", "ocr.paddle", "ocr.trocr"),
        },
        # Free: no escalation (low-confidence pages are flagged for the user); Pro/Pro+: Claude vision first.
        "ocr.escalate": {
            "free": (),
            "pro": ("ocr.claude_vision", "ocr.mistral"),
            "pro_plus": ("ocr.claude_vision", "ocr.mistral"),
        },
        "stt.transcribe": {"free": ("stt.faster_whisper",), "pro": paid_stt, "pro_plus": paid_stt},
        "embed.text": dict.fromkeys(PLANS, ("embed.bge_small",)),
    }
    for task in SONNET_TASKS:
        chain = ("llm.claude_sonnet",) if task in NO_MODEL_FALLBACK else ("llm.claude_sonnet", "llm.claude_haiku")
        cfg[task] = dict.fromkeys(PLANS, chain)
    # Free-plan tutor runs on Haiku so the $0.05/day cap covers ~13 messages (doc 07 §2)
    cfg["tutor.socratic"]["free"] = ("llm.claude_haiku",)
    for task in HAIKU_TASKS:
        cfg[task] = dict.fromkeys(PLANS, ("llm.claude_haiku",))
    return cfg

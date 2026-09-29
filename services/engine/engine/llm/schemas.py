"""Structured-output JSON schemas (doc 06 §2 "structured outputs ... and validate again with zod/pydantic").

``api_schema(model)`` turns a pydantic output model into the JSON-Schema subset the Claude API accepts for
``output_config.format``: every object ``additionalProperties: false``; no numeric/string-length/array-size
constraints, ``pattern``, ``default`` or recursion; ``oneOf`` → ``anyOf``; fixed tuples (``prefixItems``) →
``items``. The dropped constraints are enforced when the reply is validated with the pydantic model.

Committed files: ``services/engine/prompts/schemas/<task>.v<N>.json``. Regenerate with
``uv run python -m engine.llm.schemas --write``; a test fails when a committed schema drifts from its model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine.algorithms.feynman import FeynmanOutput
from engine.algorithms.grading import LlmRubricOutput
from engine.ingest.syllabus import SyllabusExtraction
from engine.llm.outputs import (
    CardsGenerateOutput,
    CardsLintOutput,
    CheatsheetCompressOutput,
    ChunkTagsOutput,
    ConceptExtractionOutput,
    GeneratedQuestion,
    KeypointsJudgement,
    LinkTiebreakOutput,
    OcrVisionOutput,
    QuestionSolveOutput,
    TutorGuardOutput,
)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
SCHEMAS_DIR = PROMPTS_DIR / "schemas"

# task id → output model (schema version follows the prompt version that introduced it).
TASK_OUTPUTS: dict[str, type[BaseModel]] = {
    "grade.rubric": LlmRubricOutput,
    "feynman.analyze": FeynmanOutput,
    "syllabus.extract": SyllabusExtraction,  # also used by syllabus.extract_escalate (same prompt on Sonnet)
    "question.generate": GeneratedQuestion,
    "question.solve": QuestionSolveOutput,
    "cards.generate": CardsGenerateOutput,
    "cards.lint": CardsLintOutput,
    "ingest.tag_chunks": ChunkTagsOutput,
    "ingest.extract_concepts": ConceptExtractionOutput,
    "ingest.link_assets": LinkTiebreakOutput,
    "answer.keypoints": KeypointsJudgement,
    "cheatsheet.compress": CheatsheetCompressOutput,
    "ocr.vision": OcrVisionOutput,
    "tutor.guard": TutorGuardOutput,
}
SCHEMA_VERSION = 1

_DROP = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        "default",
        "title",
        "discriminator",
        "examples",
    }
)
SUPPORTED_KEYS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "anyOf",
        "allOf",
        "$ref",
        "$defs",
        "format",
        "description",
    }
)
SUPPORTED_FORMATS = frozenset(
    {"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"}
)


def _dedupe(schemas: list[Any]) -> list[Any]:
    out: list[Any] = []
    for s in schemas:
        if s not in out:
            out.append(s)
    return out


def _transform(node: Any) -> Any:
    if isinstance(node, list):
        return [_transform(n) for n in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROP:
            continue
        if key == "oneOf":
            out["anyOf"] = _transform(value)
        elif key == "prefixItems":
            variants = _dedupe(_transform(value))
            out["items"] = variants[0] if len(variants) == 1 else {"anyOf": variants}
        elif key in ("properties", "$defs"):
            out[key] = {name: _transform(sub) for name, sub in value.items()}
        else:
            out[key] = _transform(value)
    if out.get("type") == "object" or "properties" in out:
        extra = node.get("additionalProperties")
        if isinstance(extra, dict) or extra is True:
            raise ValueError("free-form objects (dict fields) are not supported in structured outputs")
        out["additionalProperties"] = False
        out.setdefault("properties", {})
    return out


def api_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The ``output_config.format`` JSON schema for ``model`` (supported subset only)."""
    schema: dict[str, Any] = _transform(model.model_json_schema(mode="validation"))
    violations = api_subset_violations(schema)
    if violations:
        raise ValueError("; ".join(violations))
    return schema


def _refs(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            found.add(ref.removeprefix("#/$defs/"))
        for v in node.values():
            found |= _refs(v)
    elif isinstance(node, list):
        for v in node:
            found |= _refs(v)
    return found


def api_subset_violations(schema: dict[str, Any]) -> list[str]:
    """Everything in ``schema`` outside the structured-output subset (empty list = acceptable)."""
    problems: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, list):
            for i, n in enumerate(node):
                walk(n, f"{path}[{i}]")
            return
        if not isinstance(node, dict):
            return
        for key in node:
            if key not in SUPPORTED_KEYS:
                problems.append(f"{path}: unsupported keyword {key!r}")
        if node.get("type") == "object" or "properties" in node:
            if node.get("additionalProperties") is not False:
                problems.append(f"{path}: objects need additionalProperties: false")
        fmt = node.get("format")
        if fmt is not None and fmt not in SUPPORTED_FORMATS:
            problems.append(f"{path}: unsupported format {fmt!r}")
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for name, sub in value.items():
                    walk(sub, f"{path}.{key}.{name}")
            elif key not in ("enum", "const", "required"):
                walk(value, f"{path}.{key}")

    walk(schema, "$")
    defs: dict[str, Any] = schema.get("$defs", {})
    graph = {name: _refs(body) for name, body in defs.items()}

    def cyclic(start: str) -> bool:
        stack, seen = list(graph.get(start, ())), set()
        while stack:
            cur = stack.pop()
            if cur == start:
                return True
            if cur not in seen:
                seen.add(cur)
                stack.extend(graph.get(cur, ()))
        return False

    problems.extend(f"$defs.{name}: recursive schema" for name in graph if cyclic(name))
    return problems


def parse_output(task: str, raw_json: str | bytes) -> BaseModel:
    """Validate a model reply for ``task`` (the second validation doc 06 §2 requires).

    Strict JSON mode: no lax coercions (``"yes"`` is not a bool, ``"3"`` is not a number), matching the API schema,
    while ISO date/time strings still parse. Raises ``pydantic.ValidationError``; the caller retries once.
    """
    return TASK_OUTPUTS[task].model_validate_json(raw_json, strict=True)


def schema_path(task: str, version: int = SCHEMA_VERSION) -> Path:
    return SCHEMAS_DIR / f"{task}.v{version}.json"


def render_schema(task: str) -> str:
    return json.dumps(api_schema(TASK_OUTPUTS[task]), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def load_schema(task: str, version: int = SCHEMA_VERSION) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(schema_path(task, version).read_text(encoding="utf-8"))
    return data


def main(argv: list[str]) -> int:
    write = "--write" in argv
    stale = []
    for task in TASK_OUTPUTS:
        path, text = schema_path(task), render_schema(task)
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        elif not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(path.name)
    if stale:
        print("stale schemas (run with --write):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

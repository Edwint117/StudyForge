"""Versioned prompt templates (doc 06 §2/§5): loading, rendering and injection-safe delimiting.

File format (``services/engine/prompts/<task>.v<N>.md``)::

    ---
    task: grade.rubric
    version: 1
    tier: sonnet                  # adapter tier (llm.claude_sonnet / llm.claude_haiku); model IDs live in app_config
    output: json_schema           # or: text (tutor streaming)
    max_tokens: 4000
    effort: high                  # optional; Sonnet 5 adaptive-thinking effort
    inputs: question_md, rubric, student_answer
    untrusted: student_answer     # wrapped in delimited blocks by render(); subset of inputs
    ---
    # system
    ...static text, no placeholders (keeps the cached prefix byte-stable)...
    # context                     # optional; cached after the system prompt (course "context pack")
    ...{{placeholders}}...
    # user
    ...{{placeholders}}...

``prompt_version`` recorded on every call is ``<task>@<version>``. ``prompts/versions.lock.json`` pins each file's
SHA-256: editing a prompt without bumping ``version`` (and re-locking with
``uv run python -m engine.llm.prompts --lock``) fails the test suite, so prompt changes are always versioned.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.llm.schemas import PROMPTS_DIR

LOCK_PATH = PROMPTS_DIR / "versions.lock.json"

# Delimiter tags reserved for the system. Any occurrence inside untrusted text is neutralized so a document can't
# close its own block or forge a server directive (doc 06 §5.1).
RESERVED_TAGS = (
    "course_material",
    "student_answer",
    "student_explanation",
    "user_message",
    "syllabus_text",
    "untrusted",
    "turn_directive",
)
_RESERVED_RE = re.compile(r"<(\s*/?\s*)(" + "|".join(RESERVED_TAGS) + r")\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
_ATTR_SAFE_RE = re.compile(r"[^A-Za-z0-9_.:/\- ]")


class PromptError(ValueError):
    pass


class MaterialChunk(BaseModel):
    """One retrieved chunk for a ``<course_material>`` block."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    source: str  # human-readable location, e.g. "Lecture 3.pdf p.4"
    text: str


class PromptTemplate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    task: str
    version: int = Field(ge=1)
    tier: Literal["sonnet", "haiku"]
    output: Literal["json_schema", "text"]
    max_tokens: int = Field(gt=0)
    effort: Literal["low", "medium", "high"] | None = None
    inputs: tuple[str, ...]
    untrusted: tuple[str, ...] = ()
    system: str
    context: str | None = None
    user: str
    path: Path

    @property
    def prompt_version(self) -> str:
        return f"{self.task}@{self.version}"


class RenderedPrompt(BaseModel):
    """What the gateway sends: ``system`` then ``context`` as two cached system blocks, then the user turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    prompt_version: str
    system: str
    context: str | None
    user: str


def neutralize(text: str) -> str:
    """Escape reserved delimiter tags in untrusted text (``<course_material`` → ``&lt;course_material``)."""
    return _RESERVED_RE.sub(lambda m: "&lt;" + m.group(1) + m.group(2), text)


def _attr(value: str) -> str:
    return _ATTR_SAFE_RE.sub("_", value)[:200]


def course_material(chunks: Sequence[MaterialChunk]) -> str:
    """doc 06 §5.1: each retrieved chunk in its own delimited block; the content is data, never instructions."""
    if not chunks:
        return '<course_material id="none" source="none">No relevant material was retrieved.</course_material>'
    return "\n".join(
        f'<course_material id="{_attr(c.id)}" source="{_attr(c.source)}">\n{neutralize(c.text)}\n</course_material>'
        for c in chunks
    )


def wrap_untrusted(tag: str, text: str) -> str:
    if tag not in RESERVED_TAGS:
        raise PromptError(f"{tag!r} is not a reserved delimiter tag")
    return f"<{tag}>\n{neutralize(text)}\n</{tag}>"


TutorMode = Literal["explain", "hint", "worked_solution"]


def turn_directive(
    mode: TutorMode, hint_level: int = 1, worked_solution_allowed: bool = False, has_material: bool = True
) -> str:
    """Server-built tutor directive (doc 06 §5.5, COMP-04). Only this function may emit the tag: students and
    documents can't forge it because ``neutralize()`` escapes ``<turn_directive`` in untrusted text.

    ``mode="hint"`` is forced by the Socratic pre-check (question-bank/card match > 0.9); ``worked_solution`` needs
    the server's eligibility check (attempted, not in an exam scope within 24 h); otherwise it degrades to hints.
    """
    if not 1 <= hint_level <= 3:
        raise PromptError("hint_level must be 1..3")
    if mode == "worked_solution" and not worked_solution_allowed:
        mode = "hint"
    ws = "allowed" if worked_solution_allowed else "denied"
    material = "retrieved" if has_material else "none"
    return f'<turn_directive mode="{mode}" hint_level="{hint_level}" worked_solution="{ws}" material="{material}"/>'


def _parse(path: Path) -> PromptTemplate:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise PromptError(f"{path.name}: missing front matter")
    header, _, body = raw[4:].partition("\n---\n")
    meta: dict[str, object] = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            raise PromptError(f"{path.name}: bad front-matter line {line!r}")
        value = value.split("#", 1)[0].strip()
        key = key.strip()
        if key in ("inputs", "untrusted"):
            meta[key] = tuple(v.strip() for v in value.split(",") if v.strip())
        else:
            meta[key] = value
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in body.splitlines():
        match = re.fullmatch(r"# (system|context|user)\s*", line)
        if match:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current, lines = match.group(1), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    if "system" not in sections or "user" not in sections:
        raise PromptError(f"{path.name}: needs '# system' and '# user' sections")
    tpl = PromptTemplate.model_validate(
        {
            **meta,
            "system": sections["system"],
            "context": sections.get("context"),
            "user": sections["user"],
            "path": path,
        }
    )
    _check(tpl)
    return tpl


def placeholders(text: str | None) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(text or ""))


def _check(tpl: PromptTemplate) -> None:
    name = tpl.path.name
    if name != f"{tpl.task}.v{tpl.version}.md":
        raise PromptError(f"{name}: file name must be {tpl.task}.v{tpl.version}.md")
    if placeholders(tpl.system):
        raise PromptError(f"{name}: the system section must be static (it is the cached prefix)")
    used = placeholders(tpl.context) | placeholders(tpl.user)
    declared = set(tpl.inputs)
    if used != declared:
        raise PromptError(f"{name}: placeholders {sorted(used)} != inputs {sorted(declared)}")
    if not set(tpl.untrusted) <= declared:
        raise PromptError(f"{name}: untrusted inputs must be declared inputs")


def prompt_files() -> list[Path]:
    return sorted(PROMPTS_DIR.glob("*.v*.md"))


def load(task: str, version: int | None = None) -> PromptTemplate:
    """Load a prompt; ``version=None`` picks the highest version on disk."""
    candidates = [_parse(p) for p in PROMPTS_DIR.glob(f"{task}.v*.md")]
    candidates = [c for c in candidates if c.task == task and (version is None or c.version == version)]
    if not candidates:
        raise PromptError(f"no prompt for {task!r} (version {version})")
    return max(candidates, key=lambda c: c.version)


def render(tpl: PromptTemplate, values: Mapping[str, str | Sequence[MaterialChunk]]) -> RenderedPrompt:
    """Fill placeholders. Untrusted inputs are always delimited here, never by callers: chunk lists become
    ``<course_material>`` blocks and strings are wrapped in a block named after a reserved tag (the input's own
    name when it is one, else ``untrusted``)."""
    missing = set(tpl.inputs) - set(values)
    extra = set(values) - set(tpl.inputs)
    if missing or extra:
        raise PromptError(f"{tpl.prompt_version}: missing {sorted(missing)}, unexpected {sorted(extra)}")
    filled: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, str):
            if key in tpl.untrusted:
                filled[key] = wrap_untrusted(key if key in RESERVED_TAGS else "untrusted", value)
            else:
                filled[key] = value
        else:
            if key not in tpl.untrusted:
                raise PromptError(f"{key}: course material is untrusted and must be declared so")
            filled[key] = course_material(list(value))

    def sub(text: str | None) -> str | None:
        if text is None:
            return None
        return _PLACEHOLDER_RE.sub(lambda m: filled[m.group(1)], text)

    return RenderedPrompt(
        prompt_version=tpl.prompt_version,
        system=tpl.system,
        context=sub(tpl.context),
        user=sub(tpl.user) or "",
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def lock_entries() -> dict[str, dict[str, object]]:
    entries: dict[str, dict[str, object]] = {}
    for path in prompt_files():
        tpl = _parse(path)
        entries[path.name] = {"prompt_version": tpl.prompt_version, "sha256": file_sha256(path)}
    return entries


def read_lock() -> dict[str, dict[str, object]]:
    if not LOCK_PATH.exists():
        return {}
    data: dict[str, dict[str, object]] = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    return data


def lock_violations() -> list[str]:
    """Locked prompt files that changed or disappeared, and prompt files not yet locked."""
    locked, current = read_lock(), lock_entries()
    problems = [
        f"{name}: changed after it was locked; copy it to the next version instead"
        if name in current
        else f"{name}: locked but missing (old versions stay on disk for reproducibility)"
        for name, entry in locked.items()
        if current.get(name) != entry
    ]
    problems += [
        f"{name}: not locked (run python -m engine.llm.prompts --lock)" for name in current if name not in locked
    ]
    return problems


def main(argv: list[str]) -> int:
    if "--lock" in argv:
        # Append-only: new files are added; a changed locked file is refused (bump the version instead).
        changed = [p for p in lock_violations() if "not locked" not in p]
        if changed:
            print("\n".join(changed))
            return 1
        LOCK_PATH.write_text(
            json.dumps(lock_entries(), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        return 0
    problems = lock_violations()
    print("\n".join(problems) or "prompts match the lock")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

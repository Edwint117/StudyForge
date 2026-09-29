"""Concept-graph merge (ING-07): fold newly extracted concepts and edges into a course's existing graph.

Rules:
* **Canonical merge:** an extracted concept matches an existing one by normalized name or alias ("Bayes' theorem"
  = "bayes theorem"), else by embedding similarity ≥ 0.92 within a compatible kind; merged-away concepts resolve
  to their canonical target. Duplicates inside the same batch collapse too.
* **User edits win:** a concept the user edited keeps its name/summary; re-ingestion only attaches new chunks and
  aliases. Edges the user added are never touched; edges the user removed stay removed (they're kept with
  ``status='removed_by_user'`` instead of deleted, so re-ingestion can't resurrect them).
* **DAG safety:** AI ``prerequisite_of`` edges are added in descending confidence and skipped if they would create
  a cycle; self-loops are dropped.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.algorithms.card_quality import cosine

VERSION = "graph-merge-1"

EMBED_MATCH = 0.92
ConceptKind = Literal["concept", "definition", "formula", "theorem", "algorithm", "procedure"]
EdgeKind = Literal["prerequisite_of", "part_of", "related_to", "confusable_with"]
# kinds that may refer to the same idea (a definition of X and the concept X are the same node)
_KIND_FAMILY: dict[str, str] = {
    "concept": "idea",
    "definition": "idea",
    "formula": "math",
    "theorem": "math",
    "algorithm": "method",
    "procedure": "method",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExistingConcept(_Frozen):
    id: str
    name: str
    kind: ConceptKind
    aliases: tuple[str, ...] = ()
    embedding: tuple[float, ...] | None = None
    is_user_edited: bool = False
    merged_into_id: str | None = None


class ExtractedConcept(_Frozen):
    temp_id: str
    name: str
    kind: ConceptKind
    summary_md: str = ""
    latex: str | None = None
    importance: float = Field(default=0.5, ge=0, le=1)
    aliases: tuple[str, ...] = ()
    embedding: tuple[float, ...] | None = None
    chunk_ids: tuple[str, ...] = ()
    role: Literal["defines", "uses", "example_of"] = "uses"


class ExistingEdge(_Frozen):
    from_id: str
    to_id: str
    kind: EdgeKind
    source: Literal["ai", "user"]
    status: Literal["active", "removed_by_user"] = "active"
    confidence: float = 1.0


class ExtractedEdge(_Frozen):
    from_temp: str
    to_temp: str
    kind: EdgeKind
    confidence: float = Field(ge=0, le=1)


class NewConcept(_Frozen):
    key: str  # "new:<temp_id>" placeholder until inserted
    name: str
    kind: ConceptKind
    summary_md: str
    latex: str | None
    importance: float
    aliases: tuple[str, ...]


class MergePlan(_Frozen):
    create: tuple[NewConcept, ...]
    mapping: dict[str, str]  # temp_id → existing concept id or new key
    add_aliases: dict[str, tuple[str, ...]]  # existing concept id → aliases to add
    attach_chunks: tuple[tuple[str, str, str], ...]  # (concept id/key, chunk_id, role)


class EdgePlan(_Frozen):
    add: tuple[ExistingEdge, ...]
    update_confidence: tuple[ExistingEdge, ...]
    skipped_cycles: tuple[tuple[str, str], ...]


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"['’]s\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(_singular(w) for w in s.split() if w not in {"the", "a", "an"})


def _singular(word: str) -> str:
    """Light plural folding for matching only (not display): probabilities→probability, chains→chain,
    but keep analysis / radius / class."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _canonical(cid: str, by_id: Mapping[str, ExistingConcept]) -> str:
    seen: set[str] = set()
    while (nxt := by_id[cid].merged_into_id) is not None and cid not in seen:
        seen.add(cid)
        cid = nxt
    return cid


def merge_concepts(existing: Sequence[ExistingConcept], extracted: Sequence[ExtractedConcept]) -> MergePlan:
    by_id = {c.id: c for c in existing}
    name_index: dict[str, str] = {}
    for c in existing:
        canon = _canonical(c.id, by_id)
        for n in (c.name, *c.aliases):
            name_index.setdefault(normalize_name(n), canon)
    live = [c for c in existing if c.merged_into_id is None]

    mapping: dict[str, str] = {}
    creates: dict[str, NewConcept] = {}
    new_by_name: dict[str, str] = {}
    add_aliases: dict[str, set[str]] = defaultdict(set)

    for ex in extracted:
        names = [normalize_name(n) for n in (ex.name, *ex.aliases)]
        target = next((name_index[n] for n in names if n in name_index), None)
        if target is None and ex.embedding is not None:
            fam = _KIND_FAMILY[ex.kind]
            scored = [
                (cosine(ex.embedding, c.embedding), c.id)
                for c in live
                if c.embedding is not None and _KIND_FAMILY[c.kind] == fam
            ]
            best = max(scored, default=None)
            if best is not None and best[0] >= EMBED_MATCH:
                target = best[1]
        if target is not None:
            mapping[ex.temp_id] = target
            known = {n for n, canon in name_index.items() if canon == target}  # incl. merged-away names
            for n in (ex.name, *ex.aliases):
                norm = normalize_name(n)
                if norm not in known:
                    add_aliases[target].add(n.strip())
                    known.add(norm)
                    name_index[norm] = target
            continue
        dup = next((new_by_name[n] for n in names if n in new_by_name), None)
        if dup is not None:  # duplicate within this batch
            mapping[ex.temp_id] = dup
            prev = creates[dup]
            creates[dup] = prev.model_copy(
                update={
                    "importance": max(prev.importance, ex.importance),
                    "summary_md": prev.summary_md or ex.summary_md,
                    "latex": prev.latex or ex.latex,
                    "aliases": tuple(dict.fromkeys((*prev.aliases, ex.name, *ex.aliases))),
                }
            )
            continue
        key = f"new:{ex.temp_id}"
        creates[key] = NewConcept(
            key=key,
            name=ex.name.strip(),
            kind=ex.kind,
            summary_md=ex.summary_md,
            latex=ex.latex,
            importance=ex.importance,
            aliases=ex.aliases,
        )
        mapping[ex.temp_id] = key
        for n in names:
            new_by_name.setdefault(n, key)

    # user-edited concepts keep their fields; alias additions are harmless metadata, applied to all
    attach = tuple(dict.fromkeys((mapping[ex.temp_id], chunk, ex.role) for ex in extracted for chunk in ex.chunk_ids))
    return MergePlan(
        create=tuple(creates.values()),
        mapping=mapping,
        add_aliases={k: tuple(sorted(v)) for k, v in add_aliases.items() if v},
        attach_chunks=attach,
    )


def _reaches(adj: Mapping[str, set[str]], start: str, goal: str) -> bool:
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adj.get(node, ()))
    return False


def plan_edges(
    mapping: Mapping[str, str], extracted: Iterable[ExtractedEdge], existing: Sequence[ExistingEdge]
) -> EdgePlan:
    existing_by_key: dict[tuple[str, str, EdgeKind], ExistingEdge] = {(e.from_id, e.to_id, e.kind): e for e in existing}
    prereq_adj: dict[str, set[str]] = defaultdict(set)
    for old in existing:
        if old.kind == "prerequisite_of" and old.status == "active":
            prereq_adj[old.from_id].add(old.to_id)

    best: dict[tuple[str, str, EdgeKind], float] = {}
    for new in extracted:
        if new.from_temp not in mapping or new.to_temp not in mapping:
            continue
        a, b = mapping[new.from_temp], mapping[new.to_temp]
        if a == b:
            continue
        key = (a, b, new.kind)
        best[key] = max(best.get(key, 0.0), new.confidence)

    add: list[ExistingEdge] = []
    update: list[ExistingEdge] = []
    skipped: list[tuple[str, str]] = []
    for (a, b, kind), conf in sorted(best.items(), key=lambda kv: (-kv[1], kv[0])):
        current = existing_by_key.get((a, b, kind))
        if current is not None:
            if current.source == "ai" and current.status == "active" and conf > current.confidence:
                update.append(current.model_copy(update={"confidence": conf}))
            continue  # user-added or user-removed edges are never changed by AI
        if kind == "prerequisite_of":
            if _reaches(prereq_adj, b, a):  # a → b would close a cycle
                skipped.append((a, b))
                continue
            prereq_adj[a].add(b)
        add.append(ExistingEdge(from_id=a, to_id=b, kind=kind, source="ai", confidence=conf))
    return EdgePlan(add=tuple(add), update_confidence=tuple(update), skipped_cycles=tuple(skipped))

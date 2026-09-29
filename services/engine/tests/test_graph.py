from engine.ingest.graph import (
    ExistingConcept,
    ExistingEdge,
    ExtractedConcept,
    ExtractedEdge,
    merge_concepts,
    normalize_name,
    plan_edges,
)


def test_normalize_name() -> None:
    # internal matching key only (never displayed); what matters is that spellings collide
    assert normalize_name("Bayes' Theorem") == normalize_name("bayes theorem") == normalize_name("Bayes Theorems")
    assert normalize_name("The Law of Large Numbers") == "law of large number"
    assert normalize_name("Probabilities") == "probability"
    assert normalize_name("Analysis of Variance") == "analysis of variance"
    assert normalize_name("Poincaré") == "poincare"


def test_merge_by_name_alias_and_merged_chain() -> None:
    existing = [
        ExistingConcept(id="c1", name="Bayes' theorem", kind="theorem", aliases=("Bayes rule",)),
        ExistingConcept(id="old", name="Conditional prob.", kind="concept", merged_into_id="c2"),
        ExistingConcept(id="c2", name="Conditional probability", kind="concept"),
    ]
    extracted = [
        ExtractedConcept(temp_id="t1", name="Bayes Theorem", kind="theorem", chunk_ids=("k1",), role="defines"),
        ExtractedConcept(temp_id="t2", name="Bayes rule", kind="theorem", chunk_ids=("k2",)),
        ExtractedConcept(temp_id="t3", name="conditional prob", kind="concept", aliases=("Conditional prob.",)),
        ExtractedConcept(temp_id="t4", name="Prior", kind="concept", chunk_ids=("k3",)),
    ]
    plan = merge_concepts(existing, extracted)
    assert plan.mapping["t1"] == plan.mapping["t2"] == "c1"
    assert plan.mapping["t3"] == "c2"  # resolved through the merged-away concept
    assert plan.mapping["t4"] == "new:t4"
    assert [c.name for c in plan.create] == ["Prior"]
    assert ("c1", "k1", "defines") in plan.attach_chunks
    assert "c2" not in plan.add_aliases  # already findable through the merged-away name
    assert "c1" not in plan.add_aliases  # "Bayes Theorem" / "Bayes rule" were already known


def test_merge_by_embedding_respects_kind_family() -> None:
    existing = [ExistingConcept(id="c1", name="Variance", kind="concept", embedding=(1.0, 0.0))]
    same = ExtractedConcept(temp_id="a", name="Spread of a distribution", kind="definition", embedding=(0.99, 0.1))
    other_family = ExtractedConcept(temp_id="b", name="Var formula", kind="formula", embedding=(0.99, 0.1))
    far = ExtractedConcept(temp_id="c", name="Median", kind="concept", embedding=(0.5, 0.86))
    plan = merge_concepts(existing, [same, other_family, far])
    assert plan.mapping == {"a": "c1", "b": "new:b", "c": "new:c"}


def test_duplicates_within_batch_collapse() -> None:
    plan = merge_concepts(
        [],
        [
            ExtractedConcept(temp_id="a", name="Markov chain", kind="concept", importance=0.3),
            ExtractedConcept(
                temp_id="b", name="Markov Chains'", kind="concept", importance=0.8, summary_md="memoryless"
            ),
        ],
    )
    assert plan.mapping["a"] == plan.mapping["b"] == "new:a"
    (created,) = plan.create
    assert created.importance == 0.8 and created.summary_md == "memoryless"


def test_user_edited_concept_only_gets_aliases_and_chunks() -> None:
    existing = [
        ExistingConcept(id="c1", name="My custom name", kind="concept", aliases=("entropy",), is_user_edited=True)
    ]
    plan = merge_concepts(
        existing,
        [ExtractedConcept(temp_id="t", name="Entropy", kind="concept", summary_md="new AI text", chunk_ids=("k9",))],
    )
    assert plan.mapping["t"] == "c1" and not plan.create
    assert ("c1", "k9", "uses") in plan.attach_chunks


def test_edges_cycles_self_loops_and_user_decisions() -> None:
    mapping = {"a": "A", "b": "B", "c": "C", "a2": "A"}
    existing = [
        ExistingEdge(from_id="A", to_id="B", kind="prerequisite_of", source="ai", confidence=0.5),
        ExistingEdge(from_id="B", to_id="C", kind="related_to", source="user"),
        ExistingEdge(from_id="C", to_id="A", kind="related_to", source="ai", status="removed_by_user"),
    ]
    extracted = [
        ExtractedEdge(from_temp="a", to_temp="b", kind="prerequisite_of", confidence=0.9),  # raises confidence
        ExtractedEdge(from_temp="b", to_temp="c", kind="prerequisite_of", confidence=0.8),  # new, fine
        ExtractedEdge(from_temp="c", to_temp="a", kind="prerequisite_of", confidence=0.7),  # would close A→B→C→A
        ExtractedEdge(from_temp="a", to_temp="a2", kind="related_to", confidence=0.9),  # self-loop after merge
        ExtractedEdge(from_temp="b", to_temp="c", kind="related_to", confidence=0.9),  # user edge: untouched
        ExtractedEdge(from_temp="c", to_temp="a", kind="related_to", confidence=0.9),  # user removed: stays removed
    ]
    plan = plan_edges(mapping, extracted, existing)
    assert [(e.from_id, e.to_id, e.kind) for e in plan.add] == [("B", "C", "prerequisite_of")]
    assert [(e.from_id, e.to_id, e.confidence) for e in plan.update_confidence] == [("A", "B", 0.9)]
    assert plan.skipped_cycles == (("C", "A"),)


def test_higher_confidence_edge_wins_cycle_contest() -> None:
    mapping = {"x": "X", "y": "Y"}
    plan = plan_edges(
        mapping,
        [
            ExtractedEdge(from_temp="y", to_temp="x", kind="prerequisite_of", confidence=0.4),
            ExtractedEdge(from_temp="x", to_temp="y", kind="prerequisite_of", confidence=0.9),
        ],
        [],
    )
    assert [(e.from_id, e.to_id) for e in plan.add] == [("X", "Y")]
    assert plan.skipped_cycles == (("Y", "X"),)

import pytest

from engine.algorithms.card_quality import Card, lint_card
from engine.algorithms.feynman import (
    FeynmanOutput,
    FeynmanOutputError,
    IncorrectStatement,
    KeyPoint,
    PointJudgement,
    TermUse,
    analyze,
    gaps_to_cards,
)

KEY_POINTS = [
    KeyPoint(
        id="k1",
        prompt="What does Bayes' theorem let you compute?",
        text="P(A|B) from P(B|A), P(A) and P(B)",
        weight=2,
        source_chunk_ids=("c1",),
    ),
    KeyPoint(
        id="k2",
        prompt="Why must P(B) be positive in Bayes' theorem?",
        text="You divide by P(B)",
        source_chunk_ids=("c1",),
    ),
    KeyPoint(
        id="k3",
        prompt="What is the prior in Bayes' theorem?",
        text="P(A), the belief before seeing B",
        source_chunk_ids=("c2",),
    ),
]
EXPLANATION = (
    "Bayes' theorem lets you flip a conditional probability: you get P(A|B) using P(B|A), P(A) and P(B). "
    "The posterior is basically the likelihood times stuff."
)


def output(**kw: object) -> FeynmanOutput:
    base: dict[str, object] = {
        "judgements": (
            PointJudgement(
                key_point_id="k1", covered=True, evidence_quote="you get P(A|B) using P(B|A), P(A) and P(B)"
            ),
            PointJudgement(key_point_id="k2", covered=False),
            PointJudgement(key_point_id="k3", covered=False),
        ),
        "terms": (TermUse(term="posterior", explained=False), TermUse(term="likelihood", explained=False)),
        "missing_steps": ("Divide by the total probability P(B)",),
        "followups": ("What happens if P(B) = 0?",),
    }
    base.update(kw)
    return FeynmanOutput(**base)  # type: ignore[arg-type]


def test_score_is_weighted_coverage_minus_penalties() -> None:
    r = analyze(EXPLANATION, KEY_POINTS, output(), ["c1", "c2"])
    assert r.coverage == pytest.approx(0.5)  # k1 has weight 2 of total 4
    assert r.score == pytest.approx(0.5 - 2 * 0.05)
    assert r.covered == ("k1",) and r.missing == ("k2", "k3")
    assert r.unexplained_terms == ("posterior", "likelihood")
    assert r.downgraded == 0


def test_hallucinated_coverage_is_downgraded() -> None:
    judgements = (
        PointJudgement(key_point_id="k1", covered=True, evidence_quote="you get P(A|B) using P(B|A), P(A) and P(B)"),
        PointJudgement(key_point_id="k2", covered=True, evidence_quote="you must divide by P(B)"),  # not in text
        PointJudgement(key_point_id="k3", covered=True),  # no quote at all
    )
    r = analyze(EXPLANATION, KEY_POINTS, output(judgements=judgements, terms=()), ["c1", "c2"])
    assert r.covered == ("k1",) and r.downgraded == 2
    assert r.score == pytest.approx(0.5)


def test_errors_reduce_score_and_are_floored() -> None:
    errors = tuple(IncorrectStatement(claim="x", correction="y", citation="c1") for _ in range(8))
    r = analyze(EXPLANATION, KEY_POINTS, output(errors=errors), ["c1", "c2"])
    assert r.score == 0.0


def test_term_penalty_is_capped() -> None:
    terms = tuple(TermUse(term=f"t{i}", explained=False) for i in range(10))
    r = analyze(EXPLANATION, KEY_POINTS, output(terms=terms), ["c1", "c2"])
    assert r.score == pytest.approx(0.5 - 0.20)


@pytest.mark.parametrize(
    "bad",
    [
        {"judgements": (PointJudgement(key_point_id="k1", covered=False),)},  # missing k2, k3
        {"judgements": tuple(PointJudgement(key_point_id=k, covered=False) for k in ("k1", "k2", "k3", "k9"))},
        {"errors": (IncorrectStatement(claim="x", correction="y", citation="not-provided"),)},
    ],
)
def test_invalid_outputs_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(FeynmanOutputError):
        analyze(EXPLANATION, KEY_POINTS, output(**bad), ["c1", "c2"])


def test_gaps_become_lint_clean_cards() -> None:
    r = analyze(EXPLANATION, KEY_POINTS, output(), ["c1", "c2"])
    drafts = gaps_to_cards(r, KEY_POINTS)
    assert [d.front_md for d in drafts] == [KEY_POINTS[1].prompt, KEY_POINTS[2].prompt]
    assert drafts[0].source_chunk_ids == ("c1",)
    for d in drafts:
        assert lint_card(Card(type="free_explain", front_md=d.front_md, back_md=d.back_md)).passed

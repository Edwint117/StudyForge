import pytest

from engine.algorithms.card_quality import (
    Card,
    cosine,
    embedding_duplicates,
    lint_card,
    text_duplicates,
)


def codes(card: Card) -> set[str]:
    return {i.code for i in lint_card(card).issues}


def test_good_basic_card_passes_cleanly() -> None:
    card = Card(
        type="basic",
        front_md="What does the variance of a random variable measure?",
        back_md="How far values spread from the mean.",
    )
    result = lint_card(card)
    assert result.passed and not result.issues


@pytest.mark.parametrize(
    ("card", "code"),
    [
        (Card(type="basic", front_md="", back_md="x"), "empty_front"),
        (Card(type="basic", front_md="What is the powerhouse of the cell?", back_md=""), "empty_back"),
        (
            Card(
                type="basic",
                front_md="The mitochondria is the powerhouse. What is the powerhouse?",
                back_md="Mitochondria",
            ),
            "answer_leak",
        ),
        (Card(type="basic", front_md="Solve $x^2 = 4", back_md="x = ±2"), "latex_unbalanced"),
        (Card(type="cloze", cloze_md="The derivative of sin x is cos x."), "cloze_missing_marker"),
        (Card(type="cloze", cloze_md="{{c1::Paris}} is the capital of France; Paris is large."), "answer_leak"),
        (Card(type="cloze", cloze_md="{{c1::Paris is the capital {{c2::of France}}}} yes"), "cloze_malformed"),
    ],
)
def test_errors(card: Card, code: str) -> None:
    assert code in codes(card)
    assert not lint_card(card).passed


@pytest.mark.parametrize(
    ("card", "code"),
    [
        (Card(type="basic", front_md="Is 2 prime?", back_md="Yes"), "yes_no"),
        (Card(type="basic", front_md="It is used for what?", back_md="Sorting."), "ambiguous_prompt"),
        (
            Card(
                type="basic",
                front_md="List the ACID properties.",
                back_md="- Atomicity\n- Consistency\n- Isolation\n- Durability",
            ),
            "multiple_facts",
        ),
        (Card(type="basic", front_md="Q" * 400 + "?", back_md="A"), "front_too_long"),
        (
            Card(type="code", front_md="What does printf return?", back_md="The number of characters printed."),
            "code_missing_block",
        ),
        (Card(type="cloze", cloze_md="{{c1::The quick brown fox jumps over}} the dog"), "cloze_too_much"),
        (
            Card(type="cloze", cloze_md="{{c1::Bayes}} theorem relates {{c3::conditional}} probabilities"),
            "cloze_numbering_gap",
        ),
    ],
)
def test_warnings(card: Card, code: str) -> None:
    assert code in codes(card)
    assert lint_card(card).passed  # warnings don't block


def test_valid_cloze_and_latex() -> None:
    card = Card(type="cloze", cloze_md=r"The derivative of $\sin x$ is {{c1::$\cos x$}}.")
    assert lint_card(card).passed and not lint_card(card).issues


def test_text_duplicates() -> None:
    existing = [("c1", "What does the variance of a random variable measure?"), ("c2", "Define a Markov chain.")]
    assert text_duplicates("What does the variance of a random variable measure", existing) == ["c1"]
    assert text_duplicates("Explain the central limit theorem.", existing) == []


def test_embedding_duplicates() -> None:
    assert cosine([1, 0], [1, 0]) == pytest.approx(1)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0)
    hits = embedding_duplicates([1.0, 0.0], [("a", [0.99, 0.05]), ("b", [0.5, 0.5]), ("c", [1.0, 0.0])])
    assert [h[0] for h in hits] == ["c", "a"]
    with pytest.raises(ValueError):
        cosine([1, 2], [1])

import pytest

from engine.evals.metrics import (
    cer,
    check_gates,
    citation_validity,
    concept_prf,
    error_class_accuracy,
    grading_mae_fraction,
    leak_rate,
    leaks_answer,
    prf,
    syllabus_field_f1,
    wer,
)


def test_prf_edge_cases() -> None:
    r = prf({"a", "b", "c"}, {"b", "c", "d"})
    assert (r.tp, r.fp, r.fn) == (2, 1, 1) and r.f1 == pytest.approx(2 / 3)
    assert prf(set(), set()).f1 == 1.0  # nothing to find, nothing found
    assert prf({"x"}, set()).precision == 0.0


def test_syllabus_field_f1() -> None:
    gold = [
        {"kind": "midterm", "date": "2026-10-14", "weight_pct": 30},
        {"kind": "final", "date": "2026-12-09", "weight_pct": 50},
    ]
    pred = [
        {"kind": "midterm", "date": "2026-10-14", "weight_pct": 30.0},
        {"kind": "final", "date": "2026-09-12", "weight_pct": 50},
    ]
    assert syllabus_field_f1(pred, gold, "weight_pct").f1 == 1.0  # 30 == 30.0
    assert syllabus_field_f1(pred, gold, "date").f1 == pytest.approx(0.5)  # the day/month swap is caught


def test_concept_prf_uses_graph_normalization() -> None:
    assert concept_prf(["Bayes' Theorem", "Priors"], ["bayes theorem", "prior", "likelihood"]).recall == pytest.approx(
        2 / 3
    )


def test_grading_metrics() -> None:
    assert grading_mae_fraction([(8, 10, 10), (5, 5, 10)]) == pytest.approx(0.1)
    assert error_class_accuracy([("conceptual", "conceptual"), ("calculation_slip", "conceptual")]) == 0.5
    with pytest.raises(ValueError):
        grading_mae_fraction([])


@pytest.mark.parametrize(
    ("response", "answer", "leak"),
    [
        ("What do you get if you divide both sides by 2?", "x = 3", False),
        ("So the answer is x = 3.", "x = 3", True),
        ("Try plugging in 13 and see what happens.", "3", False),  # "3" inside "13" is not a leak
        ("It equals 0.5 exactly", "0.5", True),
        ("Consider 0.55 instead", "0.5", False),
    ],
)
def test_leak_detection(response: str, answer: str, leak: bool) -> None:
    assert leaks_answer(response, answer) is leak


def test_rates() -> None:
    assert leak_rate([("answer is 42", "42"), ("think about it", "42")]) == 0.5
    assert citation_validity(19, 1) == 0.95 and citation_validity(0, 0) == 1.0


def test_cer_wer() -> None:
    assert cer("hello world", "hello world") == 0.0
    assert cer("helo world", "hello world") == pytest.approx(1 / 11)
    assert wer("the cat sat", "the cat sat on the mat") == pytest.approx(3 / 6)
    assert wer("The  Cat", "the cat") == 0.0


def test_gates() -> None:
    results = {
        "tutor_socratic": {"leak_rate": 0.0, "citation_validity": 0.94},
        "grading": {"mae_fraction": 0.08},  # error_class_accuracy missing -> fails
    }
    out = {(r.gate.suite, r.gate.metric): r.passed for r in check_gates(results)}
    assert out == {
        ("tutor_socratic", "leak_rate"): True,
        ("tutor_socratic", "citation_validity"): False,
        ("grading", "mae_fraction"): True,
        ("grading", "error_class_accuracy"): False,
    }
    assert all(r.gate.suite == "injection" for r in check_gates({}, suites=["injection"]))

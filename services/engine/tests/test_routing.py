import copy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.adapters.breaker import CircuitBreaker
from engine.adapters.budget import CAP_EXEMPT_JOBS, can_reserve, global_budget_state, reconcile
from engine.adapters.catalog import CATALOG, PLANS, TASK_CAPABILITY, CostModel, default_routing
from engine.adapters.routing import AIUnavailable, RoutingConfigError, require, resolve, validate_config

ALL_KEYS = {
    "ANTHROPIC_API_KEY",
    "MISTRAL_API_KEY",
    "DEEPGRAM_API_KEY",
    "ASSEMBLYAI_API_KEY",
    "OPENAI_API_KEY",
    "VOYAGE_API_KEY",
}
ONLY_ANTHROPIC = {"ANTHROPIC_API_KEY"}


# ---------------------------------------------------------------- config
def test_default_routing_is_valid_and_covers_every_task() -> None:
    cfg = default_routing()
    validate_config(cfg)
    assert set(cfg) == set(TASK_CAPABILITY)


def test_free_plan_never_gets_paid_adapters_even_with_all_keys() -> None:
    cfg = default_routing()
    for task in cfg:
        for adapter_id in resolve(task, "free", cfg, ALL_KEYS):
            assert CATALOG[adapter_id].tier != "paid", (task, adapter_id)


def test_free_plan_ocr_escalation_is_empty_so_page_is_flagged() -> None:
    assert resolve("ocr.escalate", "free", default_routing(), ALL_KEYS) == []
    with pytest.raises(AIUnavailable):
        require("ocr.escalate", "free", default_routing(), ALL_KEYS)


def test_paid_adapters_need_their_key_and_fall_back_to_free() -> None:
    cfg = default_routing()
    assert resolve("stt.transcribe", "pro", cfg, ONLY_ANTHROPIC) == ["stt.faster_whisper"]
    assert resolve("stt.transcribe", "pro", cfg, ALL_KEYS)[0] == "stt.deepgram"
    # Claude vision uses the Anthropic key the app already has, so Pro escalation works out of the box
    assert resolve("ocr.escalate", "pro", cfg, ONLY_ANTHROPIC) == ["ocr.claude_vision"]


def test_breaker_skips_open_adapters() -> None:
    cfg = default_routing()
    assert resolve("tutor.socratic", "pro", cfg, ALL_KEYS, breaker_allows=lambda a: a != "llm.claude_sonnet") == [
        "llm.claude_haiku"
    ]
    # quality-critical grading has no weaker-model fallback
    assert resolve("grade.rubric", "pro", cfg, ALL_KEYS, breaker_allows=lambda a: a != "llm.claude_sonnet") == []


def test_degraded_profile_uses_haiku_and_drops_paid() -> None:
    cfg = default_routing()
    assert resolve("tutor.socratic", "pro", cfg, ALL_KEYS, profile="degraded") == ["llm.claude_haiku"]
    assert resolve("grade.rubric", "pro", cfg, ALL_KEYS, profile="degraded") == ["llm.claude_sonnet"]
    assert resolve("stt.transcribe", "pro_plus", cfg, ALL_KEYS, profile="degraded") == ["stt.faster_whisper"]


def test_kill_switch_blocks_llms_but_free_ingestion_continues() -> None:
    cfg = default_routing()
    with pytest.raises(AIUnavailable):
        resolve("tutor.socratic", "pro", cfg, ALL_KEYS, profile="killed")
    assert resolve("ocr.page", "pro_plus", cfg, ALL_KEYS, profile="killed") == ["ocr.paddle", "ocr.trocr"]
    assert resolve("ocr.escalate", "pro", cfg, ALL_KEYS, profile="killed") == []


def test_missing_anthropic_key_makes_llm_tasks_unavailable() -> None:
    with pytest.raises(AIUnavailable):
        require("cards.generate", "pro", default_routing(), set())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda c: c["stt.transcribe"].__setitem__("free", ("stt.deepgram",)), "not allowed on the Free plan"),
        (lambda c: c["embed.text"].__setitem__("pro", ("embed.voyage",)), "same provider for every plan"),
        (lambda c: c["ocr.page"].__setitem__("pro", ("stt.deepgram",)), "can't do ocr"),
        (lambda c: c["ocr.page"].__setitem__("pro", ("ocr.nonexistent",)), "unknown adapter"),
        (lambda c: c.__setitem__("made.up", dict.fromkeys(PLANS, ())), "unknown task"),
        (lambda c: c["ocr.page"].pop("pro"), "every plan needs an entry"),
    ],
)
def test_validate_config_rejects_bad_admin_changes(mutate, message: str) -> None:  # type: ignore[no-untyped-def]
    cfg = copy.deepcopy(default_routing())
    mutate(cfg)
    with pytest.raises(RoutingConfigError, match=message):
        validate_config(cfg)


def test_cost_estimates() -> None:
    sonnet = CATALOG["llm.claude_sonnet"].cost
    # 10k input + 2k output tokens at $2/$10 per MTok = $0.02 + $0.02 = 40,000 micros
    assert sonnet.estimate({"input_token": 10_000, "output_token": 2_000}) == 40_000
    assert CATALOG["ocr.claude_vision"].cost.estimate({"page": 10}) == 40_000
    assert CostModel().estimate({"page": 5}) == 0


# ---------------------------------------------------------------- circuit breaker
def test_breaker_opens_after_five_consecutive_failures_then_half_opens() -> None:
    b = CircuitBreaker(error_rate_threshold=1.1)  # disable the rate rule to isolate the consecutive rule
    for i in range(4):
        b.record(float(i), ok=False)
    assert b.current_state(4) == "closed"
    b.record(4.0, ok=False)
    assert b.current_state(5) == "open" and not b.allow(5)
    assert b.current_state(4 + 120) == "half_open"
    assert b.allow(124) and not b.allow(124)  # exactly one probe at a time
    b.record(125, ok=True)
    assert b.current_state(125) == "closed" and b.allow(125)


def test_breaker_rate_rule_and_min_calls() -> None:
    b = CircuitBreaker()
    b.record(0, ok=False)  # 1/1 failed, but below min calls in window
    assert b.current_state(0) == "closed"
    b.record(1, ok=True)
    b.record(2, ok=False)
    b.record(3, ok=False)  # 3 of 4 failed in 60 s > 50%
    assert b.current_state(3) == "open"


def test_breaker_window_forgets_old_failures() -> None:
    b = CircuitBreaker()
    b.record(0, ok=False)
    b.record(1, ok=False)
    b.record(100, ok=True)
    b.record(101, ok=True)  # the two failures fell out of the 60 s window
    assert b.current_state(101) == "closed"


def test_failed_probe_reopens() -> None:
    b = CircuitBreaker(error_rate_threshold=1.1)
    for i in range(5):
        b.record(float(i), ok=False)
    assert b.allow(200)
    b.record(200, ok=False)
    assert b.current_state(201) == "open" and not b.allow(201)


# ---------------------------------------------------------------- budget
def test_daily_cap_reservation_and_reconcile() -> None:
    assert can_reserve("free", 30_000, 10_000, 10_000)  # exactly at the $0.05 cap
    assert not can_reserve("free", 30_000, 10_000, 10_001)
    assert can_reserve("pro", 30_000, 10_000, 400_000)
    assert reconcile(30_000, 10_000, 10_000, 12_500) == (42_500, 0)


@given(st.integers(0, 10**9), st.integers(1, 10**9))
def test_global_budget_profiles(spent: int, budget: int) -> None:
    state = global_budget_state(spent, budget)
    used = spent / budget
    expected = "killed" if used >= 1.2 else "degraded" if used >= 1.0 else "normal"
    assert state.profile == expected
    assert state.alerts == tuple(a for a in (0.5, 0.8, 1.0) if used >= a)


def test_free_tutor_runs_on_haiku_and_mock_jobs_are_cap_exempt() -> None:
    cfg = default_routing()
    assert resolve("tutor.socratic", "free", cfg, ALL_KEYS) == ["llm.claude_haiku"]
    assert resolve("tutor.socratic", "pro", cfg, ALL_KEYS)[0] == "llm.claude_sonnet"
    assert not can_reserve("free", 50_000, 0, 270_000)  # a mock-sized call blows the free daily cap...
    assert can_reserve("free", 50_000, 0, 270_000, job_type="mock.build")  # ...unless it's the mock exam job
    assert "attempt.grade" in CAP_EXEMPT_JOBS

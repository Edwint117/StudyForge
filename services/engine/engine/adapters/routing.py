"""Resolve which adapters handle a task for a user's plan (doc 06 §3 "Registry").

``resolve(task, plan, ...) → [primary, *fallbacks]`` filters the configured chain by:
1. the plan rule: the Free plan never gets ``paid`` adapters;
2. the adapter's API key being configured (a paid adapter without a key is silently unavailable);
3. circuit breakers (open → skipped);
4. the global budget profile: ``degraded`` drops paid adapters and swaps Sonnet for Haiku (except
   quality-critical tasks, which keep Sonnet), ``killed`` removes every LLM and paid adapter (AI unavailable).

An empty result is legitimate (e.g. Free-plan OCR escalation → flag for the user). Use :func:`require` when the
task must run.
"""

from __future__ import annotations

from collections.abc import Callable, Collection

from engine.adapters.budget import Profile
from engine.adapters.catalog import (
    CATALOG,
    GLOBAL_TASKS,
    NO_MODEL_FALLBACK,
    PLANS,
    TASK_CAPABILITY,
    Plan,
    RoutingConfig,
)

VERSION = "routing-1"


class RoutingConfigError(ValueError):
    pass


class AIUnavailable(RuntimeError):
    """Maps to HTTP 503 ``ai_temporarily_unavailable``."""


def validate_config(config: RoutingConfig) -> None:
    """Reject admin changes that would break invariants (run on every Provider Settings save)."""
    for task, per_plan in config.items():
        if task not in TASK_CAPABILITY:
            raise RoutingConfigError(f"unknown task {task!r}")
        if set(per_plan) != set(PLANS):
            raise RoutingConfigError(f"{task}: every plan needs an entry")
        for plan, chain in per_plan.items():
            for adapter_id in chain:
                info = CATALOG.get(adapter_id)
                if info is None:
                    raise RoutingConfigError(f"{task}/{plan}: unknown adapter {adapter_id!r}")
                if info.capability != TASK_CAPABILITY[task]:
                    raise RoutingConfigError(f"{task}/{plan}: {adapter_id} can't do {TASK_CAPABILITY[task]}")
                if plan == "free" and info.tier == "paid":
                    raise RoutingConfigError(f"{task}/free: paid adapter {adapter_id} not allowed on the Free plan")
        if task in GLOBAL_TASKS and len({per_plan[p] for p in PLANS}) != 1:
            raise RoutingConfigError(
                f"{task} must use the same provider for every plan (mixing embedding models breaks search; "
                "change it globally with a re-embed job)"
            )


def resolve(
    task: str,
    plan: Plan,
    config: RoutingConfig,
    env_present: Collection[str],
    breaker_allows: Callable[[str], bool] = lambda _id: True,
    profile: Profile = "normal",
) -> list[str]:
    if task not in config:
        raise RoutingConfigError(f"no routing for task {task!r}")
    chain = list(config[task][plan])

    if profile == "killed":
        chain = [a for a in chain if CATALOG[a].tier == "free"]
        if not chain and TASK_CAPABILITY[task] == "llm":
            raise AIUnavailable(f"AI kill switch active ({task})")
    elif profile == "degraded":
        chain = [a for a in chain if CATALOG[a].tier != "paid"]
        if task not in NO_MODEL_FALLBACK:
            chain = ["llm.claude_haiku" if a == "llm.claude_sonnet" else a for a in chain]
            chain = list(dict.fromkeys(chain))  # de-duplicate, keep order

    out: list[str] = []
    for adapter_id in chain:
        info = CATALOG[adapter_id]
        if plan == "free" and info.tier == "paid":
            continue  # defense in depth: validate_config already forbids this
        if any(env not in env_present for env in info.required_env):
            continue
        if not breaker_allows(adapter_id):
            continue
        out.append(adapter_id)
    return out


def require(
    task: str,
    plan: Plan,
    config: RoutingConfig,
    env_present: Collection[str],
    breaker_allows: Callable[[str], bool] = lambda _id: True,
    profile: Profile = "normal",
) -> list[str]:
    chain = resolve(task, plan, config, env_present, breaker_allows, profile)
    if not chain:
        raise AIUnavailable(f"no available provider for {task} on plan {plan}")
    return chain

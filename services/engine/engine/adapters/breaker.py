"""Per-provider circuit breaker (doc 06 §1.4).

Opens after 5 consecutive failures, or when more than 50% of calls in the last 60 s failed (with at least
4 calls in the window, so a single failure can't trip it). Stays open 120 s, then lets one probe through
(half-open): success closes it, failure re-opens it. Time is injected, so it's deterministic in tests.
The shared state lives in the database/cache in production; this class is the policy.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

VERSION = "breaker-1"

State = Literal["closed", "open", "half_open"]


@dataclass
class CircuitBreaker:
    consecutive_threshold: int = 5
    window_s: float = 60.0
    error_rate_threshold: float = 0.5
    min_calls_in_window: int = 4
    open_duration_s: float = 120.0

    state: State = "closed"
    opened_at: float = 0.0
    consecutive_failures: int = 0
    probe_in_flight: bool = False
    _calls: deque[tuple[float, bool]] = field(default_factory=deque)  # (time, ok)

    def _trim(self, now: float) -> None:
        while self._calls and now - self._calls[0][0] > self.window_s:
            self._calls.popleft()

    def current_state(self, now: float) -> State:
        if self.state == "open" and now - self.opened_at >= self.open_duration_s:
            self.state = "half_open"
            self.probe_in_flight = False
        return self.state

    def allow(self, now: float) -> bool:
        """Should a call be attempted now? In half-open, only one probe at a time."""
        state = self.current_state(now)
        if state == "closed":
            return True
        if state == "half_open" and not self.probe_in_flight:
            self.probe_in_flight = True
            return True
        return False

    def _open(self, now: float) -> None:
        self.state = "open"
        self.opened_at = now
        self.probe_in_flight = False

    def record(self, now: float, ok: bool) -> None:
        state = self.current_state(now)
        if state == "half_open":
            if ok:
                self.state = "closed"
                self.consecutive_failures = 0
                self._calls.clear()
            else:
                self._open(now)
            self.probe_in_flight = False
            return

        self._calls.append((now, ok))
        self._trim(now)
        self.consecutive_failures = 0 if ok else self.consecutive_failures + 1
        if state != "closed":
            return
        failures = sum(1 for _, good in self._calls if not good)
        rate_tripped = (
            len(self._calls) >= self.min_calls_in_window and failures / len(self._calls) > self.error_rate_threshold
        )
        if self.consecutive_failures >= self.consecutive_threshold or rate_tripped:
            self._open(now)

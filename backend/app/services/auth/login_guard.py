from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol


class LoginFailureGuard(Protocol):
    def is_blocked(self, username: str, client_ip: str) -> bool: ...

    def record_failure(self, username: str, client_ip: str) -> None: ...

    def clear(self, username: str, client_ip: str) -> None: ...


@dataclass
class _FailureState:
    failures: list[float]
    blocked_until: float = 0.0


class InMemoryLoginFailureGuard:
    """Small single-process guard with an interface that can be replaced by Redis."""

    def __init__(
        self,
        *,
        window_seconds: int,
        max_failures: int,
        lockout_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.window_seconds = window_seconds
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self.clock = clock
        self._states: dict[tuple[str, str], _FailureState] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(username: str, client_ip: str) -> tuple[str, str]:
        return username.strip().casefold(), client_ip

    def is_blocked(self, username: str, client_ip: str) -> bool:
        now = self.clock()
        key = self._key(username, client_ip)
        with self._lock:
            state = self._states.get(key)
            if state is None:
                return False
            if state.blocked_until > now:
                return True
            if state.blocked_until:
                self._states.pop(key, None)
            return False

    def record_failure(self, username: str, client_ip: str) -> None:
        now = self.clock()
        key = self._key(username, client_ip)
        with self._lock:
            state = self._states.setdefault(key, _FailureState(failures=[]))
            state.failures = [
                timestamp
                for timestamp in state.failures
                if now - timestamp <= self.window_seconds
            ]
            state.failures.append(now)
            if len(state.failures) >= self.max_failures:
                state.blocked_until = now + self.lockout_seconds

    def clear(self, username: str, client_ip: str) -> None:
        with self._lock:
            self._states.pop(self._key(username, client_ip), None)

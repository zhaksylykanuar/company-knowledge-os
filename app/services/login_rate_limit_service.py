"""Process-local admission control for the expensive public login path.

The durable per-email throttle protects credentials. This controller protects
private-beta availability before Argon2 runs: bounded attempts per client,
bounded global burst, and bounded concurrent login work. Production currently
runs one Uvicorn process; multi-process deployments must add an edge/shared
limiter as documented in the deploy runbook.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from app.core.config import settings


@dataclass
class LoginAdmissionLease:
    _controller: "LoginAdmissionController"
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._controller.release()


class LoginAdmissionController:
    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts_by_client: dict[str, deque[float]] = defaultdict(deque)
        self._global_attempts: deque[float] = deque()
        self._in_flight = 0

    def acquire(self, client_key: str | None) -> LoginAdmissionLease | None:
        now = monotonic()
        window_start = now - settings.login_rate_limit_window_seconds
        key = client_key or "unknown-client"

        with self._lock:
            self._prune(self._global_attempts, window_start)
            for stale_key in tuple(self._attempts_by_client):
                stale_attempts = self._attempts_by_client[stale_key]
                self._prune(stale_attempts, window_start)
                if not stale_attempts:
                    del self._attempts_by_client[stale_key]
            client_attempts = self._attempts_by_client[key]
            self._prune(client_attempts, window_start)

            if (
                len(client_attempts) >= settings.login_rate_limit_per_ip
                or len(self._global_attempts) >= settings.login_rate_limit_global
                or self._in_flight >= settings.login_max_concurrent_attempts
            ):
                return None

            client_attempts.append(now)
            self._global_attempts.append(now)
            self._in_flight += 1
            return LoginAdmissionLease(self)

    def release(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    def reset(self) -> None:
        """Clear process-local state for deterministic tests only."""

        with self._lock:
            self._attempts_by_client.clear()
            self._global_attempts.clear()
            self._in_flight = 0

    @staticmethod
    def _prune(attempts: deque[float], window_start: float) -> None:
        while attempts and attempts[0] <= window_start:
            attempts.popleft()


login_admission_controller = LoginAdmissionController()


def acquire_login_admission(client_key: str | None) -> LoginAdmissionLease | None:
    return login_admission_controller.acquire(client_key)

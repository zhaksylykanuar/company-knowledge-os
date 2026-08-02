"""Admission control for expensive public authentication paths.

The durable per-email throttle protects credentials. This controller protects
availability before Argon2 runs: bounded attempts per client, bounded global
burst, and bounded concurrent work. The process backend supports the local
single-process runtime. The Redis backend uses one atomic script and is the
shared option for approved multi-worker deployments.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

_LOGGER = logging.getLogger("founderos.auth_admission")
_REDIS_KEY_PREFIX = "{founderos-auth-admission}"
_ACQUIRE_SCRIPT = """
local global_count = tonumber(redis.call('GET', KEYS[1]) or '0')
local client_count = tonumber(redis.call('GET', KEYS[2]) or '0')
local in_flight = tonumber(redis.call('GET', KEYS[3]) or '0')
if global_count >= tonumber(ARGV[1])
  or client_count >= tonumber(ARGV[2])
  or in_flight >= tonumber(ARGV[3]) then
  return 0
end
global_count = redis.call('INCR', KEYS[1])
if global_count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[4]) end
client_count = redis.call('INCR', KEYS[2])
if client_count == 1 then redis.call('EXPIRE', KEYS[2], ARGV[4]) end
in_flight = redis.call('INCR', KEYS[3])
if in_flight == 1 then redis.call('EXPIRE', KEYS[3], ARGV[5]) end
return 1
"""
_RELEASE_SCRIPT = """
local in_flight = tonumber(redis.call('GET', KEYS[1]) or '0')
if in_flight <= 1 then
  redis.call('DEL', KEYS[1])
  return 0
end
return redis.call('DECR', KEYS[1])
"""


class LoginAdmissionUnavailable(RuntimeError):
    """The configured shared admission store cannot fail closed safely."""


class AdmissionLease(Protocol):
    def release(self) -> object: ...


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


@dataclass
class RedisLoginAdmissionLease:
    _client: Redis
    _released: bool = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            await self._client.eval(
                _RELEASE_SCRIPT,
                1,
                f"{_REDIS_KEY_PREFIX}:in-flight",
            )
        except RedisError:
            # The in-flight key has a short TTL, so a failed release remains
            # fail-closed temporarily and self-recovers without a duplicate.
            _LOGGER.error("auth_admission_release_failed")
        finally:
            await self._client.aclose()


def _client_bucket_key(client_key: str | None) -> str:
    normalized = (client_key or "unknown-client").strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def _acquire_redis_admission(
    client_key: str | None,
) -> RedisLoginAdmissionLease | None:
    client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.login_rate_limit_redis_timeout_seconds,
        socket_timeout=settings.login_rate_limit_redis_timeout_seconds,
    )
    window_seconds = settings.login_rate_limit_window_seconds
    lease_ttl_seconds = max(window_seconds, 60)
    try:
        accepted = await client.eval(
            _ACQUIRE_SCRIPT,
            3,
            f"{_REDIS_KEY_PREFIX}:global",
            f"{_REDIS_KEY_PREFIX}:client:{_client_bucket_key(client_key)}",
            f"{_REDIS_KEY_PREFIX}:in-flight",
            settings.login_rate_limit_global,
            settings.login_rate_limit_per_ip,
            settings.login_max_concurrent_attempts,
            window_seconds,
            lease_ttl_seconds,
        )
    except RedisError as exc:
        await client.aclose()
        raise LoginAdmissionUnavailable(
            "shared authentication admission is unavailable"
        ) from exc
    if int(accepted) != 1:
        await client.aclose()
        return None
    return RedisLoginAdmissionLease(client)


async def acquire_login_admission(
    client_key: str | None,
) -> AdmissionLease | None:
    if settings.login_rate_limit_backend == "redis":
        return await _acquire_redis_admission(client_key)
    return login_admission_controller.acquire(client_key)


async def release_login_admission(admission: AdmissionLease | None) -> None:
    if admission is None:
        return
    result = admission.release()
    if inspect.isawaitable(result):
        await result

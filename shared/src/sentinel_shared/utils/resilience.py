from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when the circuit breaker is open."""


class AsyncCircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.opened_at: float | None = None
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            if self.opened_at is not None and monotonic() - self.opened_at < self.recovery_timeout:
                raise CircuitOpenError("Circuit breaker is open")
            if self.opened_at is not None and monotonic() - self.opened_at >= self.recovery_timeout:
                self.opened_at = None
                self.failures = 0
        try:
            result = await func()
        except Exception:
            async with self._lock:
                self.failures += 1
                if self.failures >= self.failure_threshold:
                    self.opened_at = monotonic()
            raise
        async with self._lock:
            self.failures = 0
            self.opened_at = None
        return result


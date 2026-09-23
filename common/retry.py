"""Retry helpers with exponential backoff and jitter.

Used by any outbound HTTP call that can legitimately fail with transient
5xx/429 errors. Intentionally dependency-free so that all projects in the
monorepo can adopt the same semantics.

Example
-------
>>> from common.retry import retry
>>> @retry(max_attempts=3, base_delay=0.01, jitter=False)
... def call() -> int:
...     return 42
>>> call()
42
"""

from __future__ import annotations

import functools
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryError(RuntimeError):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, attempts: int, last_error: BaseException):
        super().__init__(f"giving up after {attempts} attempt(s): {last_error!r}")
        self.attempts = attempts
        self.last_error = last_error


@dataclass
class RetryAttempt:
    """Diagnostic record for a single retry attempt."""

    attempt: int
    exception: str
    delay: float = 0.0
    elapsed: float = 0.0


@dataclass
class RetryLog:
    """Accumulated audit trail of retry attempts."""

    attempts: list[RetryAttempt] = field(default_factory=list)
    succeeded: bool = False

    def record(self, attempt: int, exc: BaseException, delay: float, elapsed: float) -> None:
        self.attempts.append(
            RetryAttempt(
                attempt=attempt,
                exception=f"{type(exc).__name__}: {exc}",
                delay=delay,
                elapsed=elapsed,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "succeeded": self.succeeded,
            "attempts": [a.__dict__ for a in self.attempts],
        }


def compute_backoff(
    attempt: int,
    *,
    base_delay: float,
    max_delay: float,
    multiplier: float = 2.0,
    jitter: bool = True,
    rand: Callable[[], float] = random.random,
) -> float:
    """Return delay in seconds for a 1-indexed ``attempt``.

    Shape: ``base_delay * multiplier ** (attempt-1)``, capped at ``max_delay``.
    When ``jitter`` is True a uniform ``[0, delay]`` full-jitter is applied
    (AWS Architecture blog style), which empirically spreads thundering herds.
    """
    if attempt < 1:
        attempt = 1
    expo = base_delay * (multiplier ** (attempt - 1))
    capped = min(max_delay, expo)
    if jitter:
        return capped * rand()
    return capped


def should_retry(
    exc: BaseException,
    retry_on: tuple[Type[BaseException], ...],
    predicate: Callable[[BaseException], bool] | None,
) -> bool:
    if not isinstance(exc, retry_on):
        return False
    if predicate is None:
        return True
    try:
        return bool(predicate(exc))
    except Exception:  # pragma: no cover - defensive
        logger.debug("retry predicate raised; defaulting to True", exc_info=True)
        return True


def retry(
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    multiplier: float = 2.0,
    jitter: bool = True,
    retry_on: Iterable[Type[BaseException]] = (Exception,),
    predicate: Callable[[BaseException], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    audit: RetryLog | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator factory that retries a callable with exponential backoff.

    Parameters are kw-only. If ``audit`` is provided each attempt is recorded.
    """
    retry_tuple = tuple(retry_on)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            started = time.monotonic()
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if audit is not None:
                        audit.succeeded = True
                    return result
                except BaseException as exc:  # noqa: BLE001
                    last_exc = exc
                    if not should_retry(exc, retry_tuple, predicate):
                        raise
                    if attempt >= max_attempts:
                        if audit is not None:
                            audit.record(attempt, exc, 0.0, time.monotonic() - started)
                        raise RetryError(max_attempts, exc) from exc
                    delay = compute_backoff(
                        attempt,
                        base_delay=base_delay,
                        max_delay=max_delay,
                        multiplier=multiplier,
                        jitter=jitter,
                    )
                    if audit is not None:
                        audit.record(attempt, exc, delay, time.monotonic() - started)
                    logger.debug(
                        "retry %s/%s after %.3fs (%s)",
                        attempt, max_attempts, delay, exc,
                    )
                    sleep(delay)
            # Should never reach here, but make mypy happy:
            raise RetryError(max_attempts, last_exc or RuntimeError("unknown"))

        return wrapper

    return decorator


__all__ = [
    "RetryError",
    "RetryAttempt",
    "RetryLog",
    "compute_backoff",
    "should_retry",
    "retry",
]

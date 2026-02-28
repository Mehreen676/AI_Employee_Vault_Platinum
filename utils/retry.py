"""
utils/retry.py — Exponential backoff retry decorator.

Usage
-----
Decorator style (wraps a function permanently):

    from utils.retry import with_retry

    @with_retry(max_attempts=3, base_delay=1.0, backoff=2.0)
    def flaky_api_call(x):
        ...

Inline style (one-off wrapping at call site):

    result = with_retry(max_attempts=3)(flaky_api_call)(x)

Parameters
----------
max_attempts : int
    Total number of attempts (1 = no retries).
base_delay : float
    Seconds to wait before the first retry.
backoff : float
    Multiplier applied to delay on each successive retry.
    E.g. base_delay=1, backoff=2 → delays 1s, 2s, 4s …
max_delay : float
    Upper cap on the computed delay (default 60s).
jitter : bool
    If True, adds a small random fraction to each delay to avoid
    thundering-herd on shared resources (default False).
exceptions : tuple[type[Exception], ...]
    Only retry when one of these exception types is raised.
    Default: (Exception,) — retry on any exception.
on_retry : callable | None
    Optional callback(attempt, exc, delay) called before each sleep.
    Useful for custom logging.

Raises
------
Re-raises the last exception after all attempts are exhausted.
"""

from __future__ import annotations

import functools
import random
import time
from typing import Any, Callable, Tuple, Type


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = False,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> Callable:
    """Return a decorator that retries the wrapped function with exponential backoff."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        # All attempts exhausted — re-raise
                        raise

                    # Compute sleep time
                    sleep_for = min(delay, max_delay)
                    if jitter:
                        sleep_for *= 1 + random.uniform(0, 0.2)

                    if on_retry is not None:
                        on_retry(attempt, exc, sleep_for)
                    else:
                        _default_log(fn.__name__, attempt, max_attempts, exc, sleep_for)

                    time.sleep(sleep_for)
                    delay *= backoff

            # Should never reach here, but satisfy type checker
            raise last_exc  # type: ignore[misc]

        # Attach config metadata for introspection / testing
        wrapper._retry_config = {  # type: ignore[attr-defined]
            "max_attempts": max_attempts,
            "base_delay": base_delay,
            "backoff": backoff,
            "max_delay": max_delay,
            "jitter": jitter,
            "exceptions": [e.__name__ for e in exceptions],
        }
        return wrapper

    return decorator


def _default_log(
    fn_name: str, attempt: int, max_attempts: int, exc: Exception, delay: float
) -> None:
    print(
        f"  [retry] {fn_name}: attempt {attempt}/{max_attempts} failed "
        f"({type(exc).__name__}: {exc}) — retrying in {delay:.1f}s"
    )

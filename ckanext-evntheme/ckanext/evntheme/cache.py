"""Per-process TTL cache for expensive lookups that do not depend on the user.

Only cache *public* data (anonymous package_search, organisation lists...), and
treat returned values as read-only: every caller gets the same object.
"""
from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_registry: list[dict[Any, tuple[float, Any]]] = []


def ttl_cache(seconds: Callable[[], int]) -> Callable[[F], F]:
    """Memoize by positional args for `seconds()` seconds (read at call time, so config changes apply)."""

    def decorator(fn: F) -> F:
        store: dict[Any, tuple[float, Any]] = {}
        lock = threading.Lock()
        _registry.append(store)

        @functools.wraps(fn)
        def wrapper(*args: Any) -> Any:
            ttl = seconds()
            if ttl <= 0:
                return fn(*args)
            now = time.monotonic()
            with lock:
                hit = store.get(args)
            if hit and now - hit[0] < ttl:
                return hit[1]
            value = fn(*args)
            with lock:
                store[args] = (now, value)
            return value

        return wrapper  # type: ignore[return-value]

    return decorator


def clear_all() -> None:
    """Drop every cached value (tests, and after the demo seed changes data)."""
    for store in _registry:
        store.clear()

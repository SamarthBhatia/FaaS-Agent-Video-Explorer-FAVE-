"""Utility helpers for timing and resource metrics."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def get_memory_limit_mb(default: int = 512) -> int:
    """
    Best-effort detection of the container memory limit.
    Falls back to the provided default if it cannot be determined.
    """
    env_limit = os.getenv("MEMORY_LIMIT_MB")
    if env_limit:
        try:
            return int(env_limit)
        except ValueError:
            pass

    cgroup_path = "/sys/fs/cgroup/memory.max"
    if os.path.exists(cgroup_path):
        raw = Path(cgroup_path).read_text().strip()
        if raw.isdigit():
            bytes_limit = int(raw)
            if bytes_limit < 1 << 60:  # guard against "max"
                return max(1, bytes_limit // (1024 * 1024))

    return default


def compute_cost_unit(duration_ms: int, memory_limit_mb: int) -> float:
    """Return the cost proxy defined as duration (s) * memory (GB)."""
    return (duration_ms / 1000.0) * (memory_limit_mb / 1024.0)


@contextmanager
def stage_timer() -> Iterator[callable]:
    """
    Context manager that yields a function returning elapsed duration in ms.

    Example:
        with stage_timer() as elapsed:
            do_work()
        duration = elapsed()
    """
    start = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - start) * 1000)

    yield elapsed_ms

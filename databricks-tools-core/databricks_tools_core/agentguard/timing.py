"""
AgentGuard timing

Per-phase timing for the checkpoint pipeline.
"""

from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

from databricks_tools_core.agentguard.models import TimingRecord

T = TypeVar("T")


class Timer:
    """Timing measurements for one action’s checkpoint run."""

    def __init__(self) -> None:
        self.records: list[TimingRecord] = []
        self._start: float = time.perf_counter()

    def measure(self, name: str, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.records.append(TimingRecord(name=name, duration_ms=round(elapsed_ms, 3)))
        return result

    async def measure_async(self, name: str, coro: Any) -> Any:
        start = time.perf_counter()
        result = await coro
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.records.append(TimingRecord(name=name, duration_ms=round(elapsed_ms, 3)))
        return result

    @property
    def total_ms(self) -> float:
        return sum(r.duration_ms for r in self.records)

    def summary(self) -> str:
        parts = [f"{r.name}: {r.duration_ms:.1f}ms" for r in self.records]
        parts.append(f"TOTAL: {self.total_ms:.1f}ms")
        return " | ".join(parts)

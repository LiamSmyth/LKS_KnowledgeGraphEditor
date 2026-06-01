"""Performance budget declaration for profiling stages."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerfBudget:
    """Declares acceptable latency thresholds for a named profiling stage.

    Used alongside ``BUDGETS: dict[str, PerfBudget]`` in perf test files.
    The ``verdict`` logic in perf test reports compares measured p95 against
    ``p95_ms`` to determine ok / warn / fail.

    Attributes:
        p95_ms: p95 latency budget in milliseconds (required).
        p99_ms: p99 latency budget in milliseconds. Defaults to 2×p95.
    """

    p95_ms: float
    p99_ms: float | None = None

    def __post_init__(self) -> None:
        if self.p95_ms <= 0.0:
            raise ValueError("p95_ms must be > 0")
        if self.p99_ms is not None and self.p99_ms < self.p95_ms:
            raise ValueError("p99_ms must be >= p95_ms")

    @property
    def p99_ms_resolved(self) -> float:
        """Return p99 budget; defaults to 2× p95 when not specified."""
        return self.p99_ms if self.p99_ms is not None else self.p95_ms * 2.0

    def verdict(self, measured_p95_ms: float) -> str:
        """Return 'ok', 'warn', or 'fail' for a measured p95 value."""
        if measured_p95_ms > self.p95_ms:
            return "fail"
        if measured_p95_ms > self.p95_ms * 0.8:
            return "warn"
        return "ok"

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "PerfBudget":
        """Construct from a plain dict with ``p95_ms`` (required) and ``p99_ms`` (optional)."""
        return cls(
            p95_ms=float(data["p95_ms"]),
            p99_ms=float(data["p99_ms"]) if "p99_ms" in data else None,
        )


__all__ = ["PerfBudget"]

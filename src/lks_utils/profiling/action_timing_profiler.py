"""Action-level timing profiler for important user and system operations.

This module complements frame/stage profiling by tracking semantically named
operations (for example, inspector commit, repository reload, or validation
passes) with lightweight context metadata.
"""
from __future__ import annotations

import statistics
import threading
import time
from collections import Counter
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator


@dataclass(frozen=True)
class ActionTimingEvent:
    """One completed action timing sample."""

    action_id: str
    phase: str
    started_at_s: float
    ended_at_s: float
    duration_ms: float
    outcome: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionTimingStats:
    """Aggregate statistics for one action+phase group."""

    action_id: str
    phase: str
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    max_ms: float
    last_ms: float
    outcomes: dict[str, int] = field(default_factory=dict)


class _ActionTimingScope:
    """Context scope object returned by ActionTimingProfiler.action()."""

    def __init__(
        self,
        profiler: ActionTimingProfiler,
        *,
        action_id: str,
        phase: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        self._profiler = profiler
        self._action_id = action_id
        self._phase = phase
        self._metadata: dict[str, Any] = dict(metadata or {})
        self._start_s = time.perf_counter()
        self._outcome = "ok"

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata fields while an action is in progress."""
        self._metadata[key] = value

    def set_outcome(self, outcome: str) -> None:
        """Override outcome label recorded for this action."""
        cleaned = str(outcome).strip()
        if cleaned:
            self._outcome = cleaned

    def finish(self) -> None:
        end_s = time.perf_counter()
        self._profiler.record_event(
            action_id=self._action_id,
            phase=self._phase,
            started_at_s=self._start_s,
            ended_at_s=end_s,
            outcome=self._outcome,
            metadata=self._metadata,
        )


class ActionTimingProfiler:
    """Thread-safe in-memory action timing recorder with ring-buffer retention."""

    def __init__(self, max_events: int = 2048) -> None:
        self._max_events = max(64, int(max_events))
        self._events: deque[ActionTimingEvent] = deque(maxlen=self._max_events)
        self._lock = threading.Lock()
        self._enabled = True
        self._revision = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def revision(self) -> int:
        return self._revision

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._revision += 1

    def events(self) -> list[ActionTimingEvent]:
        with self._lock:
            return list(self._events)

    def record_event(
        self,
        *,
        action_id: str,
        phase: str,
        started_at_s: float,
        ended_at_s: float,
        outcome: str = "ok",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return
        duration_ms = max(0.0, (ended_at_s - started_at_s) * 1000.0)
        event = ActionTimingEvent(
            action_id=str(action_id),
            phase=str(phase),
            started_at_s=float(started_at_s),
            ended_at_s=float(ended_at_s),
            duration_ms=duration_ms,
            outcome=str(outcome),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._events.append(event)
            self._revision += 1

    @contextmanager
    def action(
        self,
        action_id: str,
        *,
        phase: str = "run",
        metadata: dict[str, Any] | None = None,
    ) -> Generator[_ActionTimingScope, None, None]:
        if not self._enabled:
            scope = _ActionTimingScope(
                self,
                action_id=action_id,
                phase=phase,
                metadata=metadata,
            )
            yield scope
            return

        scope = _ActionTimingScope(
            self,
            action_id=action_id,
            phase=phase,
            metadata=metadata,
        )
        try:
            yield scope
        except Exception:
            scope.set_outcome("error")
            raise
        finally:
            scope.finish()

    def stats(self) -> list[ActionTimingStats]:
        events = self.events()
        grouped: dict[tuple[str, str], list[ActionTimingEvent]] = {}
        for event in events:
            key = (event.action_id, event.phase)
            grouped.setdefault(key, []).append(event)

        results: list[ActionTimingStats] = []
        for (action_id, phase), action_events in grouped.items():
            durations = sorted(event.duration_ms for event in action_events)
            count = len(durations)
            p50_idx = min(count - 1, int(count * 0.50))
            p95_idx = min(count - 1, int(count * 0.95))
            p99_idx = min(count - 1, int(count * 0.99))
            outcome_counts = Counter(event.outcome for event in action_events)
            results.append(
                ActionTimingStats(
                    action_id=action_id,
                    phase=phase,
                    count=count,
                    p50_ms=durations[p50_idx],
                    p95_ms=durations[p95_idx],
                    p99_ms=durations[p99_idx],
                    mean_ms=statistics.mean(durations),
                    max_ms=durations[-1],
                    last_ms=action_events[-1].duration_ms,
                    outcomes=dict(outcome_counts),
                )
            )

        results.sort(key=lambda row: row.p95_ms, reverse=True)
        return results


_DEFAULT_ACTION_TIMING_PROFILER = ActionTimingProfiler()


def get_default_action_timing_profiler() -> ActionTimingProfiler:
    """Return the process-global action timing profiler."""
    return _DEFAULT_ACTION_TIMING_PROFILER


@contextmanager
def profile_action(
    action_id: str,
    *,
    phase: str = "run",
    metadata: dict[str, Any] | None = None,
) -> Generator[_ActionTimingScope, None, None]:
    """Convenience context manager that records into the global profiler."""
    profiler = get_default_action_timing_profiler()
    with profiler.action(action_id, phase=phase, metadata=metadata) as scope:
        yield scope


def format_action_timing_summary(max_rows: int = 10) -> str:
    """Return a compact text summary of action timing aggregates."""
    rows = get_default_action_timing_profiler().stats()[: max(1, max_rows)]
    if not rows:
        return "No action timing samples recorded."
    lines = ["Action Timing Summary"]
    for row in rows:
        lines.append(
            f"- {row.action_id}:{row.phase} count={row.count} p95={row.p95_ms:.3f}ms "
            f"p99={row.p99_ms:.3f}ms mean={row.mean_ms:.3f}ms"
        )
    return "\n".join(lines)


__all__ = [
    "ActionTimingEvent",
    "ActionTimingStats",
    "ActionTimingProfiler",
    "get_default_action_timing_profiler",
    "profile_action",
    "format_action_timing_summary",
]

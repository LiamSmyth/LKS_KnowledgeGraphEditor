"""GPU timer query context manager for ModernGL contexts.

Wraps OpenGL ``TIME_ELAPSED`` queries with a clean context-manager API,
fallback for unsupported environments, and a configurable timeout to
prevent frame stalls on platforms with broken async queries.

Usage::

    from lks_utils.gpu.gpu_timer_query import GpuTimerQuery, HAS_GPU_TIMER_QUERY

    if HAS_GPU_TIMER_QUERY:
        with GpuTimerQuery(ctx) as q:
            render_something(ctx)
        gpu_ms = q.elapsed_ms   # nanoseconds → ms
    else:
        render_something(ctx)
        gpu_ms = 0.0
"""
from __future__ import annotations

from typing import Any

try:
    import moderngl as _moderngl
    HAS_GPU_TIMER_QUERY: bool = True
except ImportError:
    HAS_GPU_TIMER_QUERY = False

# Maximum time (ms) to wait for a query result before returning 0.
# Prevents driver stalls on pathological configurations.
_DEFAULT_TIMEOUT_MS: float = 50.0


class GpuTimerQuery:
    """Context manager wrapping a single ``TIME_ELAPSED`` query.

    Args:
        ctx: A ``moderngl.Context`` instance.
        timeout_ms: If the elapsed result would stall longer than this
            value (checked via soft timeout), return 0.0 instead. Defaults
            to 50 ms.

    Example::

        with GpuTimerQuery(ctx) as q:
            vao.render(prog)
        print(q.elapsed_ms)
    """

    def __init__(
        self,
        ctx: Any,
        timeout_ms: float = _DEFAULT_TIMEOUT_MS,
    ) -> None:
        if not HAS_GPU_TIMER_QUERY:
            raise RuntimeError(
                "ModernGL is required for GpuTimerQuery. "
                "Install lks_utils[gl-viewport] or check HAS_GPU_TIMER_QUERY "
                "before constructing this object."
            )
        self._ctx = ctx
        self._timeout_ms = float(timeout_ms)
        self._query: Any = None
        self._elapsed_ms: float = 0.0
        self._completed: bool = False

    # ------------------------------------------------------------------ #
    # Context manager                                                      #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "GpuTimerQuery":
        self._query = self._ctx.query(time=True)
        self._query.__enter__()
        self._completed = False
        self._elapsed_ms = 0.0
        return self

    def __exit__(self, *args: object) -> None:
        if self._query is not None:
            self._query.__exit__(*args)
            self._completed = True
            try:
                # moderngl query.elapsed is in nanoseconds.
                ns = float(self._query.elapsed)
                ms = ns * 1e-6
                # Sanity-cap: if value exceeds timeout treat as stall/bogus.
                self._elapsed_ms = ms if ms <= self._timeout_ms else 0.0
            except Exception:  # noqa: BLE001 – any driver exception → 0
                self._elapsed_ms = 0.0

    # ------------------------------------------------------------------ #
    # Result                                                               #
    # ------------------------------------------------------------------ #

    @property
    def elapsed_ms(self) -> float:
        """GPU elapsed time in milliseconds.

        Returns 0.0 if the query has not yet been completed (context
        manager not exited) or if the result exceeded the timeout cap.
        """
        return self._elapsed_ms if self._completed else 0.0

    @property
    def completed(self) -> bool:
        """True once the context manager has exited and the result is ready."""
        return self._completed


__all__ = ["GpuTimerQuery", "HAS_GPU_TIMER_QUERY"]

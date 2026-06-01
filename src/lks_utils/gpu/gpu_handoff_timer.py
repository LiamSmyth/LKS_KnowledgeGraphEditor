"""GPU handoff timer context manager for CPU/GPU synchronization tracking."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType

    from lks_utils.profiling.profiler import Profiler


class GpuHandoffTimer:
    """Context manager that records GPU↔CPU synchronization time to a :class:`Profiler`.

    Wrap any fence/sync/readback/upload block with this context manager to emit
    a ``gpu_handoff.<reason>`` stage with :class:`~lks_utils.profiling.device.Device.HANDOFF`
    device attribution.  The ``CanvasFrameTimingsAdapter`` (A6) is extended to
    recognise these stage names and classify them as ``Device.HANDOFF`` in the
    call tree.

    Usage::

        from lks_utils.gpu.gpu_handoff_timer import GpuHandoffTimer

        with GpuHandoffTimer(profiler, "readback"):
            data = ctx.buffer.read()

    Args:
        profiler: Active :class:`~lks_utils.profiling.profiler.Profiler` instance.
            If the profiler is disabled, this context manager is a no-op.
        reason: One of ``readback``, ``upload``, ``fence_wait``, ``flush``.
            Custom reasons are accepted but should be documented if added.
    """

    def __init__(self, profiler: "Profiler", reason: str) -> None:
        self._profiler = profiler
        self._reason = reason
        self._stage_name = f"gpu_handoff.{reason}"
        self._start: float = 0.0
        self._active = False

    def __enter__(self) -> "GpuHandoffTimer":
        self._start = time.perf_counter()
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: "TracebackType | None",
    ) -> None:
        if not self._active:
            return
        elapsed_s = time.perf_counter() - self._start
        self._active = False
        if self._profiler.enabled:
            self._profiler.record_stage(
                self._stage_name,
                duration_seconds=elapsed_s,
                metadata={"reason": self._reason, "device": "handoff"},
            )

    @property
    def stage_name(self) -> str:
        """The stage name emitted to the profiler (``gpu_handoff.<reason>``)."""
        return self._stage_name

    @property
    def reason(self) -> str:
        """The handoff reason token passed at construction."""
        return self._reason


__all__ = ["GpuHandoffTimer"]

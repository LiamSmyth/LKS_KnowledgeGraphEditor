"""Pass-through adapter for prebuilt generic profiling call trees."""
from __future__ import annotations

from lks_utils.profiling.call_node import CallNode
from lks_utils.profiling.frame_sample import FrameSample


class ManualCallTreeAdapter:
    """Wrap an existing ``CallNode`` tree in a ``FrameSample``."""

    @staticmethod
    def adapt(
        call_tree: CallNode,
        *,
        frame_index: int = 0,
        wall_ms: float | None = None,
        counters: dict[str, float] | None = None,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> FrameSample:
        return FrameSample(
            frame_index=max(0, int(frame_index)),
            wall_ms=call_tree.total_ms_value if wall_ms is None else max(
                0.0, float(wall_ms)),
            call_tree=call_tree,
            counters={} if counters is None else dict(counters),
            metadata={} if metadata is None else dict(metadata),
        )


__all__ = ["ManualCallTreeAdapter"]

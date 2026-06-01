"""Adapter from ``ProfileReport`` stage lists into generic frame samples."""
from __future__ import annotations

from lks_utils.profiling.call_node import CallNode
from lks_utils.profiling.device import Device
from lks_utils.profiling.frame_sample import FrameSample


class ProfilerStageAdapter:
    """Build a ``FrameSample`` tree from a ``ProfileReport`` stage list."""

    def __init__(self, stage_devices: dict[str, Device] | None = None) -> None:
        self._stage_devices = {} if stage_devices is None else dict(
            stage_devices)

    def adapt(self, report, *, frame_index: int = 0) -> FrameSample:  # noqa: ANN001
        stage_children: dict[str | None, list[object]] = {}
        for stage in report.stages:
            stage_children.setdefault(stage.parent, []).append(stage)

        top_level_nodes = tuple(
            self._build_node(stage, stage_children)
            for stage in stage_children.get(None, [])
        )
        child_total_ms = sum(node.total_ms_value for node in top_level_nodes)
        root = CallNode(
            name=report.name,
            category="profile_report",
            device=Device.UNKNOWN,
            self_ms=max(0.0, float(report.total_duration_seconds)
                        * 1000.0 - child_total_ms),
            total_ms=max(float(report.total_duration_seconds)
                         * 1000.0, child_total_ms),
            children=top_level_nodes,
            metadata={"stage_count": report.stage_count},
        )
        return FrameSample(
            frame_index=max(0, int(frame_index)),
            wall_ms=root.total_ms_value,
            call_tree=root,
            metadata={"source": "profile_report"},
        )

    def _build_node(self, stage, stage_children: dict[str | None, list[object]]) -> CallNode:  # noqa: ANN001
        children = tuple(
            self._build_node(child, stage_children)
            for child in stage_children.get(stage.name, [])
        )
        duration_ms = max(0.0, float(stage.duration_ms))
        child_total_ms = sum(child.total_ms_value for child in children)
        self_ms = max(0.0, duration_ms - child_total_ms)
        device = self._stage_devices.get(stage.name, Device.UNKNOWN)
        return CallNode(
            name=stage.name,
            category="stage",
            device=device,
            self_ms=self_ms,
            total_ms=max(duration_ms, self_ms + child_total_ms),
            children=children,
            metadata=dict(stage.metadata),
        )


__all__ = ["ProfilerStageAdapter"]

"""Adapter that converts a pyinstrument session JSON to :class:`FrameSample` objects."""
from __future__ import annotations

from typing import Any

from lks_utils.profiling.call_node import CallNode
from lks_utils.profiling.device import Device
from lks_utils.profiling.frame_sample import FrameSample


class PyinstrumentAdapter:
    """Convert a pyinstrument JSON profile into :class:`FrameSample` objects.

    pyinstrument captures the entire profiling session as a single call-tree.
    This adapter treats the session as **one FrameSample** (``frame_index=0``).
    For multi-frame decomposition use :class:`ViztracerAdapter` instead.

    Usage::

        import json
        import pyinstrument

        profiler = pyinstrument.Profiler()
        with profiler:
            ...
        session_json = profiler.output(renderer=pyinstrument.renderers.JSONRenderer())
        parsed = json.loads(session_json)
        samples = PyinstrumentAdapter.adapt(parsed)

    The top-level call-tree root is the entry-point function.  All nodes are
    attributed to :attr:`~lks_utils.profiling.device.Device.CPU` because
    pyinstrument captures wall-clock sampling on the CPU thread only.
    """

    @staticmethod
    def adapt(session_json: dict[str, Any]) -> list[FrameSample]:
        """Convert a parsed pyinstrument session dict to one :class:`FrameSample`.

        Args:
            session_json: Parsed result of
                ``profiler.output(renderer=pyinstrument.renderers.JSONRenderer())``.

        Returns:
            A single-element list containing one :class:`FrameSample`.
            Returns an empty list when *session_json* contains no frame data.
        """
        root_frame = session_json.get("root_frame")
        if root_frame is None:
            return []

        duration_s: float = float(session_json.get("duration", 0.0))
        call_tree = _build_call_node(root_frame)
        wall_ms = duration_s * 1000.0

        sample = FrameSample(
            frame_index=0,
            wall_ms=wall_ms,
            call_tree=call_tree,
            metadata={"source": "pyinstrument", "cpu_time_s": str(duration_s)},
        )
        return [sample]


def _build_call_node(frame: dict[str, Any]) -> CallNode:
    """Recursively convert a pyinstrument frame dict to a :class:`CallNode`."""
    # pyinstrument JSON keys: function, filename, lineno, time, children
    function_name: str = str(frame.get("function", "<unknown>"))
    file_name: str = str(
        frame.get("file_path_short", frame.get("filename", "")))
    line_no: int = int(frame.get("line_no", frame.get("lineno", 0)))
    time_s: float = float(frame.get("time", 0.0))

    raw_children: list[dict[str, Any]] = frame.get("children") or []
    child_nodes = tuple(_build_call_node(child) for child in raw_children)

    child_total_s = sum(c.total_ms_value / 1000.0 for c in child_nodes)
    self_s = max(0.0, time_s - child_total_s)

    label = function_name
    if file_name:
        label = f"{function_name} ({file_name}:{line_no})" if line_no else f"{function_name} ({file_name})"

    return CallNode(
        name=label,
        self_ms=self_s * 1000.0,
        total_ms=time_s * 1000.0,
        category="cpu",
        device=Device.CPU,
        children=child_nodes,
    )


__all__ = ["PyinstrumentAdapter"]

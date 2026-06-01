"""Adapter that converts a VizTracer trace JSON to :class:`FrameSample` objects."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lks_utils.profiling.call_node import CallNode
from lks_utils.profiling.device import Device
from lks_utils.profiling.frame_sample import FrameSample


# VizTracer uses Perfetto/Trace-Event format.
# Event phases: B=begin, E=end, X=complete, M=metadata.
_PHASE_BEGIN = "B"
_PHASE_END = "E"
_PHASE_COMPLETE = "X"
_PHASE_METADATA = "M"

# Thread / process names that indicate GPU work in VizTracer traces.
_GPU_THREAD_PREFIXES = ("gpu", "GPU", "render", "Render")

# Fence/sync categories that map to Device.HANDOFF.
_HANDOFF_CATEGORIES = frozenset(
    {"gpu_handoff", "fence", "sync", "readback", "upload"}
)

# Default frame duration to use when no frame markers are present (16.6 ms).
_DEFAULT_FRAME_MS = 16.6


class ViztracerAdapter:
    """Convert a VizTracer JSON trace file to :class:`FrameSample` objects.

    VizTracer records all events in Perfetto Trace-Event format.  This adapter:

    1. Groups events into frames using ``CustomEvent`` markers named ``frame_*``
       (emitted by :class:`~lks_utils.profiling.profiler.Profiler` when tracing).
    2. Within each frame, builds a per-thread call-forest and flattens it to a
       single :class:`CallNode` tree rooted at a synthetic ``"frame"`` node.
    3. Classifies nodes as CPU / GPU / HANDOFF based on thread name and category.

    Usage::

        samples = ViztracerAdapter.adapt("path/to/trace.json")

    If no frame markers are found, the entire trace is treated as one frame.
    """

    @staticmethod
    def adapt(trace_path: str | Path) -> list[FrameSample]:
        """Load *trace_path* and return one :class:`FrameSample` per captured frame.

        Args:
            trace_path: Path to the VizTracer ``result.json`` (or any
                trace-event JSON with a ``traceEvents`` key).

        Returns:
            Ordered list of :class:`FrameSample`, one per frame found.
        """
        trace_path = Path(trace_path)
        with trace_path.open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = json.load(fh)

        events: list[dict[str, Any]] = raw.get("traceEvents") or []
        if not events:
            return []

        # Build thread-name lookup from metadata events.
        thread_names: dict[tuple[int, int], str] = {}
        for ev in events:
            if ev.get("ph") == _PHASE_METADATA and ev.get("name") == "thread_name":
                tid = int(ev.get("tid", 0))
                pid = int(ev.get("pid", 0))
                name = ev.get("args", {}).get("name", "")
                thread_names[(pid, tid)] = str(name)

        # Collect complete/duration events only.
        complete_events: list[dict[str, Any]] = [
            ev for ev in events
            if ev.get("ph") in (_PHASE_COMPLETE, "FEF")
            or (ev.get("ph") == _PHASE_BEGIN)
        ]

        # Normalise to X (complete) events with ts and dur.
        normalised: list[dict[str, Any]] = _normalise_events(events)
        if not normalised:
            return []

        # Attempt to split into frames via frame markers.
        frame_groups = _split_into_frames(normalised)

        samples: list[FrameSample] = []
        for idx, (frame_start_us, frame_end_us, frame_events) in enumerate(frame_groups):
            wall_us = frame_end_us - frame_start_us
            wall_ms = wall_us / 1000.0

            tree = _build_frame_tree(frame_events, thread_names, wall_ms)
            sample = FrameSample(
                frame_index=idx,
                wall_ms=wall_ms,
                call_tree=tree,
                metadata={"source": "viztracer",
                          "frame_count": str(len(frame_groups))},
            )
            samples.append(sample)

        return samples


def _normalise_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert B/E pairs and X events into a unified list of complete events."""
    complete: list[dict[str, Any]] = []
    # Stack per thread for B/E matching.
    stacks: dict[tuple[int, int], list[dict[str, Any]]] = {}

    for ev in events:
        phase = ev.get("ph", "")
        pid = int(ev.get("pid", 0))
        tid = int(ev.get("tid", 0))
        key = (pid, tid)

        if phase == _PHASE_COMPLETE:
            complete.append(ev)
        elif phase == _PHASE_BEGIN:
            stacks.setdefault(key, []).append(ev)
        elif phase == _PHASE_END:
            if key in stacks and stacks[key]:
                begin_ev = stacks[key].pop()
                dur = float(ev.get("ts", 0)) - float(begin_ev.get("ts", 0))
                complete.append({**begin_ev, "ph": "X", "dur": max(0.0, dur)})

    return sorted(complete, key=lambda e: float(e.get("ts", 0)))


def _split_into_frames(
    events: list[dict[str, Any]],
) -> list[tuple[float, float, list[dict[str, Any]]]]:
    """Group events by frame boundary markers or fall back to one frame."""
    # Frame markers: events whose 'name' starts with 'frame' and cat == 'Renderer'
    frame_starts: list[float] = []
    for ev in events:
        cat = str(ev.get("cat", ""))
        name = str(ev.get("name", ""))
        if cat in ("Renderer", "frame") and name.startswith("frame"):
            frame_starts.append(float(ev.get("ts", 0)))

    if not frame_starts:
        # Single frame: entire trace.
        ts_list = [float(e.get("ts", 0)) for e in events]
        dur_list = [float(e.get("dur", 0)) for e in events]
        start = min(ts_list) if ts_list else 0.0
        end = max(ts + dur for ts, dur in zip(ts_list, dur_list)
                  ) if ts_list else 0.0
        return [(start, max(end, start + _DEFAULT_FRAME_MS * 1000.0), events)]

    frame_starts_sorted = sorted(set(frame_starts))
    # Add a synthetic end frame boundary.
    last_event_end = max(
        float(e.get("ts", 0)) + float(e.get("dur", 0)) for e in events
    )
    boundaries = frame_starts_sorted + [last_event_end]

    groups: list[tuple[float, float, list[dict[str, Any]]]] = []
    for i in range(len(boundaries) - 1):
        f_start = boundaries[i]
        f_end = boundaries[i + 1]
        frame_events = [
            e for e in events
            if f_start <= float(e.get("ts", 0)) < f_end
        ]
        groups.append((f_start, f_end, frame_events))
    return groups


def _build_frame_tree(
    events: list[dict[str, Any]],
    thread_names: dict[tuple[int, int], str],
    wall_ms: float,
) -> CallNode:
    """Build a synthetic root :class:`CallNode` for one frame's events."""
    if not events:
        return CallNode(name="frame", self_ms=wall_ms, device=Device.CPU)

    # Group events by thread.
    per_thread: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for ev in events:
        pid = int(ev.get("pid", 0))
        tid = int(ev.get("tid", 0))
        per_thread.setdefault((pid, tid), []).append(ev)

    thread_nodes: list[CallNode] = []
    for (pid, tid), thread_events in per_thread.items():
        tname = thread_names.get((pid, tid), f"thread-{tid}")
        thread_total_ms = sum(float(e.get("dur", 0)) /
                              1000.0 for e in thread_events)
        leaves = tuple(_event_to_call_node(
            e, thread_names.get((pid, tid), "")) for e in thread_events)
        thread_nodes.append(
            CallNode(
                name=tname,
                self_ms=0.0,
                total_ms=thread_total_ms,
                category="thread",
                device=Device.CPU,
                children=leaves,
            )
        )

    # Root frame node encapsulates all threads.
    total_ms = sum(n.total_ms_value for n in thread_nodes)
    root_self_ms = max(0.0, wall_ms - total_ms)
    return CallNode(
        name="frame",
        self_ms=root_self_ms,
        total_ms=wall_ms,
        device=Device.CPU,
        children=tuple(thread_nodes),
    )


def _event_to_call_node(
    ev: dict[str, Any],
    thread_name: str,
) -> CallNode:
    """Convert one complete event to a leaf :class:`CallNode`."""
    name = str(ev.get("name", "<unknown>"))
    dur_us = float(ev.get("dur", 0.0))
    dur_ms = dur_us / 1000.0
    cat = str(ev.get("cat", ""))
    device = _device_for_event(ev, thread_name)
    return CallNode(
        name=name,
        self_ms=dur_ms,
        total_ms=dur_ms,
        category=cat or "cpu",
        device=device,
    )


def _device_for_event(ev: dict[str, Any], thread_name: str) -> Device:
    """Classify an event as CPU, GPU, or HANDOFF."""
    cat = str(ev.get("cat", ""))
    if cat in _HANDOFF_CATEGORIES:
        return Device.HANDOFF
    if any(thread_name.startswith(p) for p in _GPU_THREAD_PREFIXES):
        return Device.GPU
    if cat.startswith("gpu") or cat.startswith("GPU"):
        return Device.GPU
    return Device.CPU


__all__ = ["ViztracerAdapter"]

"""Profiling utilities for timing and performance measurement.

This module provides tools for profiling code execution, measuring
timing of individual stages, and generating reports to identify bottlenecks.

Also provides BatchProfiler for aggregating results from parallel/batch
operations with statistical analysis and outlier detection.

Usage:
    from lks_utils.profiling import Profiler, ProfileReport

    # Single operation profiling
    profiler = Profiler("image_compression")
    with profiler.stage("load_image"):
        img = load_image(path)
    with profiler.stage("encode"):
        encode(img, output_path)
    
    report = profiler.get_report()
    print(report.summary())
    
    # Batch operation profiling
    from lks_utils.profiling import BatchProfiler
    
    batch = BatchProfiler("compress_images_batch")
    for path in image_paths:
        profiler = Profiler(f"compress_{path.name}")
        # ... do work with profiler.stage() ...
        batch.add_report(profiler.get_report(), item_id=str(path))
    
    print(batch.summary())  # Shows mean, p95, outliers, bottlenecks
"""

from __future__ import annotations

from lks_utils.profiling.frame_capture_controller import FrameCaptureController, FrameCaptureState
from lks_utils.profiling.frame_profile_details_builder import FrameProfileDetailsBuilder
from lks_utils.profiling.action_timing_profiler import (
    ActionTimingEvent,
    ActionTimingProfiler,
    ActionTimingStats,
    format_action_timing_summary,
    get_default_action_timing_profiler,
    profile_action,
)
from lks_utils.profiling.profiler import Profiler, ProfileReport, ProfileStage, StageTimer, BatchProfiler, BatchProfileReport, StageStatistics, get_global_profiler, set_global_profiler, profile_stage, format_profile_summary
from lks_utils.profiling.profiler_query import ProfilerQueryHelper
from lks_utils.profiling.device import Device
from lks_utils.profiling.call_node import CallNode
from lks_utils.profiling.frame_sample import FrameSample
from lks_utils.profiling.counter_track import CounterTrack
from lks_utils.profiling.profile_filter import ProfileFilter
from lks_utils.profiling.session_io import export_session, load_session
from lks_utils.profiling.perf_budget import PerfBudget
from lks_utils.profiling.surface_kind import SurfaceKind
from lks_utils.profiling.perf_target import PerfTarget, discover_targets
from lks_utils.profiling.adapters import (
    CanvasFrameTimingsAdapter,
    ManualCallTreeAdapter,
    ProfilerStageAdapter,
)
from lks_utils.profiling.adapters.pyinstrument_adapter import PyinstrumentAdapter
from lks_utils.profiling.adapters.viztracer_adapter import ViztracerAdapter

__all__ = [
    # Core profiling
    "Profiler",
    "ProfileReport",
    "ProfileStage",
    "StageTimer",
    "format_profile_summary",
    # Batch profiling
    "BatchProfiler",
    "BatchProfileReport",
    "StageStatistics",
    # Global profiler utilities
    "get_global_profiler",
    "set_global_profiler",
    "profile_stage",
    # Frame profiling utilities
    "FrameCaptureController",
    "FrameCaptureState",
    "FrameProfileDetailsBuilder",
    "ActionTimingEvent",
    "ActionTimingProfiler",
    "ActionTimingStats",
    "get_default_action_timing_profiler",
    "profile_action",
    "format_action_timing_summary",
    "ProfilerQueryHelper",
    # Domain model
    "Device",
    "CallNode",
    "FrameSample",
    "CounterTrack",
    "ProfileFilter",
    # Adapters
    "CanvasFrameTimingsAdapter",
    "ManualCallTreeAdapter",
    "ProfilerStageAdapter",
    "PyinstrumentAdapter",
    "ViztracerAdapter",
    # Perf target system
    "PerfBudget",
    "SurfaceKind",
    "PerfTarget",
    "discover_targets",
    # Session I/O
    "export_session",
    "load_session",
]

"""Core profiling implementation with stage timing and reporting.

Provides a Profiler class that can be used to time individual stages
of a process and generate detailed reports for bottleneck analysis.

Also provides BatchProfiler for aggregating results from parallel operations.
"""

from __future__ import annotations

import statistics
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Generator

# Thread-local storage for global profiler
_thread_local = threading.local()

# Try to import console colors (optional)
try:
    from ..console.colors import (
        SemanticColor,
        style_text,
        get_color_enabled,
        colorize_by_duration,
    )
    from ..console.formatters import (
        Table,
        Panel,
        format_duration,
        format_percentage,
        create_progress_bar,
    )
    HAS_CONSOLE: bool = True
except ImportError:
    HAS_CONSOLE = False

    def style_text(text: str, style, **kwargs) -> str:  # type: ignore
        return text

    def get_color_enabled() -> bool:
        return False

    def format_duration(seconds: float, **kwargs) -> str:  # type: ignore
        if seconds < 1:
            return f"{seconds * 1000:.1f}ms"
        return f"{seconds:.2f}s"

    def format_percentage(value: float, **kwargs) -> str:  # type: ignore
        return f"{value:.1f}%"


@dataclass
class ProfileStage:
    """A single timed stage within a profiling session.

    Attributes:
        name: Name of the stage (e.g., "load_image", "encode_avif")
        start_time: Unix timestamp when stage started
        end_time: Unix timestamp when stage ended (None if still running)
        metadata: Optional dict of additional info (file size, dimensions, etc.)
        parent: Parent stage name if nested
    """
    name: str
    start_time: float
    end_time: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    parent: str | None = None

    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds. Returns 0 if not yet ended."""
        if self.end_time is None:
            return 0.0
        return self.end_time - self.start_time

    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        return self.duration_seconds * 1000.0

    @property
    def is_complete(self) -> bool:
        """Check if this stage has finished."""
        return self.end_time is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "name": self.name,
            "duration_seconds": self.duration_seconds,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "parent": self.parent,
        }


@dataclass
class ProfileReport:
    """A complete profiling report for a session.

    Attributes:
        name: Name of the profiling session
        stages: List of all recorded stages
        total_duration_seconds: Total time from first stage start to last stage end
        metadata: Session-level metadata
    """
    name: str
    stages: list[ProfileStage]
    total_duration_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def stage_count(self) -> int:
        """Get number of stages recorded."""
        return len(self.stages)

    def get_stage(self, name: str) -> ProfileStage | None:
        """Get a specific stage by name. Returns last occurrence if duplicates."""
        for stage in reversed(self.stages):
            if stage.name == name:
                return stage
        return None

    def get_stages_by_parent(self, parent: str | None = None) -> list[ProfileStage]:
        """Get all stages with a specific parent (None for top-level stages)."""
        return [s for s in self.stages if s.parent == parent]

    def get_top_stages(self, n: int = 5) -> list[ProfileStage]:
        """Get the N slowest stages, sorted by duration descending."""
        sorted_stages: list[ProfileStage] = sorted(
            [s for s in self.stages if s.is_complete],
            key=lambda s: s.duration_seconds,
            reverse=True
        )
        return sorted_stages[:n]

    def get_stage_breakdown(self) -> dict[str, float]:
        """Get a dict mapping stage names to cumulative duration in seconds.

        If a stage name appears multiple times, durations are summed.
        """
        breakdown: dict[str, float] = {}
        for stage in self.stages:
            if stage.is_complete:
                breakdown[stage.name] = breakdown.get(
                    stage.name, 0.0) + stage.duration_seconds
        return breakdown

    def summary(self, colorize: bool = True, top_n: int = 10) -> str:
        """Generate a human-readable summary of the profiling results.

        Args:
            colorize: Whether to use ANSI colors
            top_n: Number of top stages to show in breakdown

        Returns:
            Formatted string with timing breakdown
        """
        use_color: bool = colorize and HAS_CONSOLE and get_color_enabled()
        lines: list[str] = []

        header: str = f"=== Profile Report: {self.name} ==="
        if use_color:
            header = style_text(header, SemanticColor.HIGHLIGHT, bold=True)
        lines.append(header)

        dur_str: str = format_duration(
            self.total_duration_seconds, colorize=use_color)
        lines.append(f"Total duration: {dur_str}")
        lines.append(f"Stages recorded: {self.stage_count}")

        if self.metadata:
            lines.append(f"Session metadata: {self.metadata}")

        lines.append("")
        section_header: str = "--- Stage Breakdown (cumulative) ---"
        if use_color:
            section_header = style_text(section_header, SemanticColor.MUTED)
        lines.append(section_header)

        breakdown: dict[str, float] = self.get_stage_breakdown()
        sorted_breakdown: list[tuple[str, float]] = sorted(
            breakdown.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]

        for name, duration in sorted_breakdown:
            pct: float = (duration / self.total_duration_seconds *
                          100) if self.total_duration_seconds > 0 else 0
            dur_display: str = format_duration(duration, colorize=use_color)
            lines.append(f"  {name}: {dur_display} ({pct:.1f}%)")

        if len(breakdown) > top_n:
            remaining: float = sum(d for n, d in breakdown.items() if (
                n, d) not in sorted_breakdown)
            lines.append(
                f"  ... and {len(breakdown) - top_n} more stages: {remaining:.3f}s")

        lines.append("")
        top_header: str = "--- Top 5 Slowest Individual Stages ---"
        if use_color:
            top_header = style_text(top_header, SemanticColor.MUTED)
        lines.append(top_header)

        for stage in self.get_top_stages(5):
            meta_str: str = f" ({stage.metadata})" if stage.metadata else ""
            dur_display: str = format_duration(
                stage.duration_seconds, colorize=use_color)
            lines.append(
                f"  {stage.name}: {dur_display}{meta_str}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "name": self.name,
            "total_duration_seconds": self.total_duration_seconds,
            "stage_count": self.stage_count,
            "metadata": self.metadata,
            "stages": [s.to_dict() for s in self.stages],
            "breakdown": self.get_stage_breakdown(),
        }


class StageTimer:
    """Context manager for timing a single stage.

    Usage:
        with StageTimer("encode") as timer:
            encode_image(...)
            timer.add_metadata("format", "avif")
        print(timer.duration_seconds)
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None):
        """Initialize the timer.

        Args:
            name: Name of the stage
            metadata: Optional initial metadata
        """
        self.name: str = name
        self._start_time: float = 0.0
        self._end_time: float = 0.0
        self._metadata: dict[str, Any] = metadata or {}

    def __enter__(self) -> StageTimer:
        """Start timing."""
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop timing."""
        self._end_time = time.perf_counter()

    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        return self._end_time - self._start_time

    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        return self.duration_seconds * 1000.0

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to this stage."""
        self._metadata[key] = value

    @property
    def metadata(self) -> dict[str, Any]:
        """Get the metadata dict."""
        return self._metadata

    def to_stage(self) -> ProfileStage:
        """Convert to a ProfileStage object."""
        return ProfileStage(
            name=self.name,
            start_time=self._start_time,
            end_time=self._end_time,
            metadata=self._metadata.copy(),
        )


class Profiler:
    """Main profiler class for timing multiple stages of a process.

    Thread-safe: each profiler instance uses a lock for concurrent access.

    Usage:
        profiler = Profiler("image_compression")

        with profiler.stage("load"):
            img = load_image(path)

        with profiler.stage("resize"):
            img = resize(img)

        with profiler.stage("encode", metadata={"format": "avif"}):
            encode(img, output)

        report = profiler.get_report()
        print(report.summary())
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None):
        """Initialize the profiler.

        Args:
            name: Name for this profiling session
            metadata: Optional session-level metadata
        """
        self.name: str = name
        self._metadata: dict[str, Any] = metadata or {}
        self._stages: list[ProfileStage] = []
        self._start_time: float | None = None
        self._end_time: float | None = None
        self._current_stage: str | None = None
        self._lock: threading.Lock = threading.Lock()
        self._enabled: bool = True

    @property
    def enabled(self) -> bool:
        """Check if profiling is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable profiling."""
        self._enabled = value

    def add_metadata(self, key: str, value: Any) -> None:
        """Add session-level metadata."""
        with self._lock:
            self._metadata[key] = value

    @contextmanager
    def stage(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[StageTimer, None, None]:
        """Context manager for timing a stage.

        Args:
            name: Name of the stage
            metadata: Optional metadata for this stage

        Yields:
            StageTimer that can be used to add metadata during execution
        """
        if not self._enabled:
            # Return a no-op timer
            timer: StageTimer = StageTimer(name, metadata)
            yield timer
            return

        timer = StageTimer(name, metadata)
        parent: str | None = self._current_stage

        with self._lock:
            self._current_stage = name
            if self._start_time is None:
                self._start_time = time.perf_counter()

        try:
            with timer:
                yield timer
        finally:
            with self._lock:
                stage: ProfileStage = timer.to_stage()
                stage.parent = parent
                self._stages.append(stage)
                self._current_stage = parent
                self._end_time = time.perf_counter()

    def record_stage(
        self,
        name: str,
        duration_seconds: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Manually record a stage with a known duration.

        Useful for recording stages that were timed externally.

        Args:
            name: Name of the stage
            duration_seconds: Duration in seconds
            metadata: Optional metadata
        """
        if not self._enabled:
            return

        with self._lock:
            now: float = time.perf_counter()
            stage: ProfileStage = ProfileStage(
                name=name,
                start_time=now - duration_seconds,
                end_time=now,
                metadata=metadata or {},
                parent=self._current_stage,
            )
            self._stages.append(stage)

            if self._start_time is None:
                self._start_time = stage.start_time
            self._end_time = now

    def reset(self) -> None:
        """Clear all recorded stages and reset timing."""
        with self._lock:
            self._stages.clear()
            self._start_time = None
            self._end_time = None
            self._current_stage = None

    def get_report(self) -> ProfileReport:
        """Generate a ProfileReport from the recorded stages.

        Returns:
            ProfileReport with all recorded stages and computed totals
        """
        with self._lock:
            total: float = 0.0
            if self._start_time is not None and self._end_time is not None:
                total = self._end_time - self._start_time

            return ProfileReport(
                name=self.name,
                stages=self._stages.copy(),
                total_duration_seconds=total,
                metadata=self._metadata.copy(),
            )

    def get_stage_count(self) -> int:
        """Get the number of recorded stages."""
        with self._lock:
            return len(self._stages)

    def merge(self, other: Profiler) -> None:
        """Merge stages from another profiler into this one.

        Useful for combining profiling data from parallel workers.

        Args:
            other: Another Profiler instance to merge from
        """
        with self._lock:
            other_report: ProfileReport = other.get_report()
            self._stages.extend(other_report.stages)

            # Update timing bounds
            for stage in other_report.stages:
                if self._start_time is None or stage.start_time < self._start_time:
                    self._start_time = stage.start_time
                if stage.end_time is not None:
                    if self._end_time is None or stage.end_time > self._end_time:
                        self._end_time = stage.end_time


# Global profiler management
def get_global_profiler() -> Profiler | None:
    """Get the thread-local global profiler, if set."""
    return getattr(_thread_local, "profiler", None)


def set_global_profiler(profiler: Profiler | None) -> None:
    """Set the thread-local global profiler."""
    _thread_local.profiler = profiler


@contextmanager
def profile_stage(
    name: str,
    metadata: dict[str, Any] | None = None,
) -> Generator[StageTimer, None, None]:
    """Context manager that uses the global profiler if available.

    If no global profiler is set, this is a no-op that still yields
    a StageTimer for API consistency.

    Usage:
        set_global_profiler(Profiler("my_session"))

        with profile_stage("load_image"):
            img = load(path)

        report = get_global_profiler().get_report()

    Args:
        name: Name of the stage
        metadata: Optional metadata

    Yields:
        StageTimer for adding metadata
    """
    profiler: Profiler | None = get_global_profiler()

    if profiler is not None:
        with profiler.stage(name, metadata) as timer:
            yield timer
    else:
        # No global profiler, just yield a standalone timer
        timer = StageTimer(name, metadata)
        with timer:
            yield timer


@dataclass
class StageStatistics:
    """Statistics for a single stage type across a batch.

    Attributes:
        name: Stage name
        count: Number of times this stage was recorded
        total_seconds: Sum of all durations
        mean_seconds: Average duration
        median_seconds: Median duration (p50)
        min_seconds: Fastest occurrence
        max_seconds: Slowest occurrence
        p95_seconds: 95th percentile duration
        p99_seconds: 99th percentile duration
        std_dev_seconds: Standard deviation
    """
    name: str
    count: int
    total_seconds: float
    mean_seconds: float
    median_seconds: float
    min_seconds: float
    max_seconds: float
    p95_seconds: float
    p99_seconds: float
    std_dev_seconds: float

    @property
    def is_outlier_prone(self) -> bool:
        """Check if this stage has high variance (potential outliers)."""
        if self.mean_seconds == 0:
            return False
        # Coefficient of variation > 50% indicates high variance
        return (self.std_dev_seconds / self.mean_seconds) > 0.5

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "name": self.name,
            "count": self.count,
            "total_seconds": self.total_seconds,
            "mean_seconds": self.mean_seconds,
            "median_seconds": self.median_seconds,
            "min_seconds": self.min_seconds,
            "max_seconds": self.max_seconds,
            "p95_seconds": self.p95_seconds,
            "p99_seconds": self.p99_seconds,
            "std_dev_seconds": self.std_dev_seconds,
            "is_outlier_prone": self.is_outlier_prone,
        }


@dataclass
class BatchProfileReport:
    """Aggregated profiling report from multiple individual reports.

    Attributes:
        name: Name of the batch profiling session
        item_count: Number of items processed
        total_duration_seconds: Total wall-clock time
        stage_stats: Statistics for each stage type
        outliers: List of (item_identifier, stage_name, duration) for slow items
        metadata: Session-level metadata
    """
    name: str
    item_count: int
    total_duration_seconds: float
    stage_stats: dict[str, StageStatistics]
    outliers: list[tuple[str, str, float]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_bottleneck(self) -> str | None:
        """Get the stage that takes the most cumulative time."""
        if not self.stage_stats:
            return None
        return max(
            self.stage_stats.items(),
            key=lambda x: x[1].total_seconds
        )[0]

    def summary(self, colorize: bool = True, top_n: int = 10) -> str:
        """Generate a beautified summary of the batch profiling results.

        Args:
            colorize: Whether to use ANSI colors
            top_n: Number of stages to show in breakdown

        Returns:
            Formatted summary string
        """
        use_color: bool = colorize and HAS_CONSOLE and get_color_enabled()
        lines: list[str] = []

        # Header
        header: str = f"═══ Batch Profile: {self.name} ═══"
        if use_color:
            header = style_text(header, SemanticColor.HIGHLIGHT, bold=True)
        lines.append(header)
        lines.append("")

        # Overview stats
        dur_str: str = format_duration(
            self.total_duration_seconds, colorize=use_color)
        throughput: float = self.item_count / \
            self.total_duration_seconds if self.total_duration_seconds > 0 else 0

        lines.append(f"Items processed: {self.item_count}")
        lines.append(f"Total duration:  {dur_str}")
        lines.append(f"Throughput:      {throughput:.2f} items/sec")

        if self.metadata:
            lines.append(f"Metadata:        {self.metadata}")

        lines.append("")

        # Stage breakdown table
        section_header: str = "─── Stage Statistics ───"
        if use_color:
            section_header = style_text(section_header, SemanticColor.MUTED)
        lines.append(section_header)

        # Sort by total time descending
        sorted_stats: list[tuple[str, StageStatistics]] = sorted(
            self.stage_stats.items(),
            key=lambda x: x[1].total_seconds,
            reverse=True
        )[:top_n]

        for stage_name, stats in sorted_stats:
            pct: float = (stats.total_seconds / self.total_duration_seconds *
                          100) if self.total_duration_seconds > 0 else 0

            # Format each stat with appropriate coloring
            mean_str: str = format_duration(
                stats.mean_seconds, colorize=use_color)
            p95_str: str = format_duration(
                stats.p95_seconds, colorize=use_color)
            total_str: str = format_duration(
                stats.total_seconds, colorize=False)
            pct_str: str = f"{pct:.1f}%"

            # Highlight outlier-prone stages
            name_display: str = stage_name
            if use_color and stats.is_outlier_prone:
                name_display = style_text(stage_name, SemanticColor.WARNING)

            lines.append(f"  {name_display}:")
            lines.append(
                f"    Count: {stats.count}, Total: {total_str} ({pct_str})")
            lines.append(f"    Mean: {mean_str}, p95: {p95_str}")

        # Bottleneck identification
        bottleneck: str | None = self.get_bottleneck()
        if bottleneck:
            lines.append("")
            bottleneck_label: str = "Bottleneck: "
            if use_color:
                bottleneck_label = style_text(
                    "Bottleneck: ", SemanticColor.ERROR, bold=True)
                bottleneck = style_text(bottleneck, SemanticColor.ERROR)
            lines.append(f"{bottleneck_label}{bottleneck}")

        # Outliers
        if self.outliers:
            lines.append("")
            outlier_header: str = "─── Outliers (>2σ from mean) ───"
            if use_color:
                outlier_header = style_text(
                    outlier_header, SemanticColor.WARNING)
            lines.append(outlier_header)

            for item_id, stage_name, duration in self.outliers[:5]:
                dur_str = format_duration(duration, colorize=use_color)
                lines.append(f"  {item_id}: {stage_name} = {dur_str}")

            if len(self.outliers) > 5:
                lines.append(f"  ... and {len(self.outliers) - 5} more")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "name": self.name,
            "item_count": self.item_count,
            "total_duration_seconds": self.total_duration_seconds,
            "stage_stats": {k: v.to_dict() for k, v in self.stage_stats.items()},
            "outliers": [
                {"item": item, "stage": stage, "duration": dur}
                for item, stage, dur in self.outliers
            ],
            "bottleneck": self.get_bottleneck(),
            "metadata": self.metadata,
        }


class BatchProfiler:
    """Aggregates profiling results from multiple individual operations.

    Useful for batch processing where you want to see aggregate statistics
    across many items rather than individual timing data.

    Usage:
        batch_profiler = BatchProfiler("image_compression_batch")

        for image_path in images:
            profiler = Profiler(f"compress_{image_path.name}")
            # ... do work with profiler.stage() ...
            batch_profiler.add_report(profiler.get_report(), item_id=str(image_path))

        report = batch_profiler.get_report()
        print(report.summary())
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None):
        """Initialize the batch profiler.

        Args:
            name: Name for this batch profiling session
            metadata: Optional session-level metadata
        """
        self.name: str = name
        self._metadata: dict[str, Any] = metadata or {}
        # (item_id, report)
        self._reports: list[tuple[str, ProfileReport]] = []
        self._start_time: float | None = None
        self._end_time: float | None = None
        self._lock: threading.Lock = threading.Lock()

    def add_report(
        self,
        report: ProfileReport,
        item_id: str | None = None,
    ) -> None:
        """Add an individual profiling report to the batch.

        Args:
            report: The ProfileReport from an individual operation
            item_id: Optional identifier for the item (for outlier tracking)
        """
        with self._lock:
            if self._start_time is None:
                self._start_time = time.perf_counter()

            self._end_time = time.perf_counter()
            actual_id: str = item_id or f"item_{len(self._reports)}"
            self._reports.append((actual_id, report))

    def add_metadata(self, key: str, value: Any) -> None:
        """Add session-level metadata."""
        with self._lock:
            self._metadata[key] = value

    @property
    def item_count(self) -> int:
        """Get number of items added."""
        return len(self._reports)

    def get_report(self) -> BatchProfileReport:
        """Generate aggregated statistics from all added reports.

        Returns:
            BatchProfileReport with aggregate statistics
        """
        with self._lock:
            # Calculate total duration
            total_duration: float = 0.0
            if self._start_time is not None and self._end_time is not None:
                total_duration = self._end_time - self._start_time

            # Collect all durations by stage name
            stage_durations: dict[str, list[tuple[str, float]]] = {}

            for item_id, report in self._reports:
                breakdown: dict[str, float] = report.get_stage_breakdown()
                for stage_name, duration in breakdown.items():
                    if stage_name not in stage_durations:
                        stage_durations[stage_name] = []
                    stage_durations[stage_name].append((item_id, duration))

            # Compute statistics for each stage
            stage_stats: dict[str, StageStatistics] = {}
            outliers: list[tuple[str, str, float]] = []

            for stage_name, durations_with_ids in stage_durations.items():
                durations: list[float] = [d for _, d in durations_with_ids]

                if len(durations) < 2:
                    # Not enough data for statistics
                    dur: float = durations[0] if durations else 0.0
                    stage_stats[stage_name] = StageStatistics(
                        name=stage_name,
                        count=len(durations),
                        total_seconds=sum(durations),
                        mean_seconds=dur,
                        median_seconds=dur,
                        min_seconds=dur,
                        max_seconds=dur,
                        p95_seconds=dur,
                        p99_seconds=dur,
                        std_dev_seconds=0.0,
                    )
                    continue

                sorted_durations: list[float] = sorted(durations)
                count: int = len(durations)
                total: float = sum(durations)
                mean: float = statistics.mean(durations)
                median: float = statistics.median(durations)
                std_dev: float = statistics.stdev(
                    durations) if count > 1 else 0.0

                # Percentiles
                p95_idx: int = int(count * 0.95)
                p99_idx: int = int(count * 0.99)
                p95: float = sorted_durations[min(p95_idx, count - 1)]
                p99: float = sorted_durations[min(p99_idx, count - 1)]

                stage_stats[stage_name] = StageStatistics(
                    name=stage_name,
                    count=count,
                    total_seconds=total,
                    mean_seconds=mean,
                    median_seconds=median,
                    min_seconds=min(durations),
                    max_seconds=max(durations),
                    p95_seconds=p95,
                    p99_seconds=p99,
                    std_dev_seconds=std_dev,
                )

                # Identify outliers (>2 standard deviations from mean)
                if std_dev > 0:
                    threshold: float = mean + 2 * std_dev
                    for item_id, dur in durations_with_ids:
                        if dur > threshold:
                            outliers.append((item_id, stage_name, dur))

            # Sort outliers by duration descending
            outliers.sort(key=lambda x: x[2], reverse=True)

            return BatchProfileReport(
                name=self.name,
                item_count=len(self._reports),
                total_duration_seconds=total_duration,
                stage_stats=stage_stats,
                outliers=outliers,
                metadata=self._metadata.copy(),
            )

    def summary(self, colorize: bool = True, top_n: int = 10) -> str:
        """Generate a beautified summary of the batch profiling results.

        Args:
            colorize: Whether to use ANSI colors
            top_n: Number of stages to show

        Returns:
            Formatted summary string
        """
        return self.get_report().summary(colorize=colorize, top_n=top_n)

    def reset(self) -> None:
        """Clear all added reports."""
        with self._lock:
            self._reports.clear()
            self._start_time = None
            self._end_time = None


def format_profile_summary(
    report: ProfileReport | BatchProfileReport | list[ProfileReport],
    colorize: bool = True,
    top_n: int = 10,
) -> str:
    """Format a profiling report or list of reports into a human-readable summary.

    Args:
        report: A ProfileReport, BatchProfileReport, or list of ProfileReports to summarize
        colorize: Whether to use ANSI colors (if supported)
        top_n: Number of top stages to show in breakdown

    Returns:
        Formatted summary string
    """
    if isinstance(report, BatchProfileReport):
        return report.summary(colorize=colorize, top_n=top_n)

    if isinstance(report, ProfileReport):
        return report.summary(colorize=colorize, top_n=top_n)

    if isinstance(report, list):
        if not report:
            return "No profiling data available."

        # Create a temporary BatchProfiler to aggregate the reports
        batch = BatchProfiler("Aggregated Summary")
        for r in report:
            batch.add_report(r)
        return batch.summary(colorize=colorize, top_n=top_n)

    raise TypeError(f"Unsupported report type: {type(report)}")

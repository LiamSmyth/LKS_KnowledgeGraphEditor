"""Live profiler query helpers for automated test inspection.

Provides :class:`ProfilerQueryHelper` — a thin wrapper around
:class:`~lks_utils.gui_qt.widgets.QFrameProfilerWidget` that exposes
structured profiling data and assertion helpers for use in pytest
live-UI tests.

Typical usage in a ``@pytest.mark.gui`` test::

    from lks_utils.profiling.profiler_query import ProfilerQueryHelper

    def test_canvas_profile_coverage(qapp):
        canvas = MyCanvas()
        widget = QFrameProfilerWidget()
        widget.attach(canvas)
        # … render a few frames …
        helper = ProfilerQueryHelper(widget)
        helper.assert_coverage(min_coverage=0.90)
        helper.assert_no_untracked_majority()

The helpers are intentionally synchronous and stateless — each call reads
the *current* selected frame at the moment of the call.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_utils.gui_qt.widgets.frame_profiler_widget import QFrameProfilerWidget


class ProfilerQueryHelper:
    """Query and assert against live :class:`QFrameProfilerWidget` data.

    Designed for use in pytest GUI tests.  Pass the profiler widget after
    the canvas has rendered some frames::

        helper = ProfilerQueryHelper(widget)
        report = helper.get_report()
        helper.assert_coverage(min_coverage=0.90)
    """

    def __init__(self, widget: QFrameProfilerWidget) -> None:
        self._widget = widget

    # ── Data access ────────────────────────────────────────────────────────

    def get_report(self) -> dict[str, object]:
        """Return the structured report dict for the selected frame.

        Returns an empty dict when no frame is selected.
        See :meth:`QFrameProfilerWidget.get_perf_report_dict` for field docs.
        """
        return self._widget.get_perf_report_dict()

    def get_report_text(self) -> str:
        """Return the plain-text profile report for LLM paste-back.

        Returns an empty string when no frame is available.
        """
        return self._widget.format_profile_report()

    def residual_pct(self) -> float:
        """Unaccounted frame time as a percentage [0, 100]."""
        report = self.get_report()
        return float(report.get("residual_pct", 0.0))

    def coverage_pct(self) -> float:
        """Fraction of frame time accounted for by timed stages [0, 100]."""
        return 100.0 - self.residual_pct()

    def largest_stage(self) -> dict[str, object]:
        """Return the stage row dict with the highest ``ms`` value."""
        report = self.get_report()
        stages: list[dict[str, object]] = list(report.get("stages", []))
        if not stages:
            return {}
        return max(stages, key=lambda s: float(s.get("ms", 0.0)))

    # ── Assertions ─────────────────────────────────────────────────────────

    def assert_has_data(self) -> None:
        """Assert that the profiler has at least one frame to inspect."""
        report = self.get_report()
        assert report, (
            "ProfilerQueryHelper: no frame data available. "
            "Ensure the widget has received at least one frame via push() "
            "and that capture is paused (set_capture_enabled(False)) so a "
            "frame is selected."
        )

    def assert_coverage(self, min_coverage: float = 0.85) -> None:
        """Assert that at least *min_coverage* fraction of frame time is timed.

        Args:
            min_coverage: Required coverage as a fraction [0, 1].  Default 0.85
                (15% residual tolerance).

        Raises:
            AssertionError: When unaccounted time exceeds ``1 - min_coverage``.
        """
        self.assert_has_data()
        cov = self.coverage_pct() / 100.0
        report = self.get_report()
        assert cov >= min_coverage, (
            f"ProfilerQueryHelper: coverage {cov * 100:.1f}% < required {min_coverage * 100:.1f}%\n"
            f"  total_ms={report.get('total_ms', '?'):.3f}  "
            f"residual_ms={report.get('residual_ms', '?'):.3f}\n"
            f"  Add profiling hooks to identify the unaccounted time.\n"
            f"\n{self.get_report_text()}"
        )

    def assert_no_untracked_majority(self) -> None:
        """Assert that ``untracked`` is not the single largest stage.

        A profile where the biggest slice is ``untracked`` means the
        instrumentation is covering less than half the frame — a critical
        quality failure that warrants adding more hooks.
        """
        self.assert_has_data()
        stage = self.largest_stage()
        assert stage.get("kind") not in ("residual", "residual_warn"), (
            f"ProfilerQueryHelper: the largest stage is 'untracked' "
            f"({float(stage.get('ms', 0)):.3f} ms, {float(stage.get('pct', 0)):.1f}%). "
            f"Add profiling hooks to cover this time.\n"
            f"\n{self.get_report_text()}"
        )

    def assert_budget(self, budget_ms: float | None = None) -> None:
        """Assert that the selected frame is within *budget_ms*.

        If *budget_ms* is ``None``, uses the widget's current budget.
        """
        self.assert_has_data()
        report = self.get_report()
        if budget_ms is None:
            budget_ms = float(report.get("budget_ms", 16.6))
        total_ms = float(report.get("total_ms", 0.0))
        assert total_ms <= budget_ms, (
            f"ProfilerQueryHelper: frame {total_ms:.3f} ms exceeds budget {budget_ms:.1f} ms "
            f"(delta {total_ms - budget_ms:+.3f} ms)\n"
            f"\n{self.get_report_text()}"
        )


__all__ = ["ProfilerQueryHelper"]

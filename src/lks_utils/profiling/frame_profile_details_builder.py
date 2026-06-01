"""Frame-profile detail row builder for inspection UIs."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas2d_renderer import FrameTimings

# If the unaccounted remainder exceeds this fraction of total frame time the
# residual row is flagged as a warning by the builder (kind="residual_warn").
_RESIDUAL_WARN_FRACTION: float = 0.10
# Absolute floor (ms) below which residual is suppressed — sub-ms noise.
_RESIDUAL_MIN_MS: float = 0.5


class FrameProfileDetailsBuilder:
    """Build sortable detail rows from a ``FrameTimings`` sample.

    Row tuple: ``(name, kind, z_str, ms, pct)``

    ``kind`` values:
    * ``"core"``           — background / items / overlay-sum pseudo rows
    * ``"overlay"``        — individual timed overlay
    * ``"residual"``       — unaccounted render time
    * ``"residual_warn"``  — unaccounted render time over warn threshold
    * ``"cadence_gap"``    — pacing gap (effective total − measured paint)
    """

    @staticmethod
    def build_rows(
        frame: FrameTimings,
        *,
        frame_total_ms: float | None = None,
        cadence_wait_ms: float | None = None,
    ) -> list[tuple[str, str, str, float, float]]:
        measured_ms = float(frame.total_ms)
        total_ms = measured_ms if frame_total_ms is None else float(
            frame_total_ms)
        total = max(total_ms, 1e-6)
        rows: list[tuple[str, str, str, float, float]] = []

        def add(name: str, kind: str, z_str: str, ms: float) -> None:
            rows.append((name, kind, z_str, ms, ms / total * 100.0))

        add("background", "core", "-", frame.background_ms)
        if frame.qpainter_init_ms > 0.0:
            add("QPainter init", "core", "-", frame.qpainter_init_ms)
        add("items (all)", "core", "-", frame.items_ms)
        add("overlays (sum)", "core", "-", frame.overlays_ms)
        if frame.qpainter_flush_ms > 0.0:
            add("QPainter flush", "core", "-", frame.qpainter_flush_ms)
        for overlay in frame.overlay_timings:
            add(overlay.name, "overlay", str(
                overlay.z_order), overlay.duration_ms)

        # ── Unknown render residual + cadence gap ───────────────────────────
        # Unknown render residual is measured against the measured paint scope.
        # Cadence gap captures pacing cost beyond measured paint work.
        residual_ms = FrameProfileDetailsBuilder.residual_ms(frame)
        cadence_gap_ms = FrameProfileDetailsBuilder.cadence_gap_ms(
            frame,
            frame_total_ms=frame_total_ms,
        )
        sched_wait_ms, present_wait_ms = FrameProfileDetailsBuilder.cadence_breakdown_ms(
            frame,
            frame_total_ms=frame_total_ms,
            cadence_wait_ms=cadence_wait_ms,
        )
        if residual_ms >= _RESIDUAL_MIN_MS:
            frac = residual_ms / total
            kind = "residual_warn" if frac >= _RESIDUAL_WARN_FRACTION else "residual"
            add("untracked", kind, "-", residual_ms)
        if sched_wait_ms >= _RESIDUAL_MIN_MS:
            add("frame scheduler wait", "cadence_wait", "-", sched_wait_ms)
        if present_wait_ms >= _RESIDUAL_MIN_MS:
            add("frame present/wait", "cadence_present", "-", present_wait_ms)
        if cadence_gap_ms >= _RESIDUAL_MIN_MS and (sched_wait_ms + present_wait_ms) < _RESIDUAL_MIN_MS:
            add("frame pacing gap", "cadence_gap", "-", cadence_gap_ms)

        rows.sort(key=lambda row: row[3], reverse=True)
        return rows

    @staticmethod
    def timed_sum_ms(frame: FrameTimings) -> float:
        """Return the sum of all explicitly timed stage buckets in *ms*."""
        return (
            frame.background_ms
            + frame.qpainter_init_ms
            + frame.items_ms
            + frame.overlays_ms
            + frame.qpainter_flush_ms
        )

    @staticmethod
    def residual_ms(
        frame: FrameTimings,
    ) -> float:
        """Return unknown render time in *ms* for *frame*.

        This is strictly ``measured_total_ms - timed_sum_ms``.
        """
        total_ms = float(frame.total_ms)
        return max(0.0, total_ms - FrameProfileDetailsBuilder.timed_sum_ms(frame))

    @staticmethod
    def cadence_gap_ms(
        frame: FrameTimings,
        *,
        frame_total_ms: float | None = None,
    ) -> float:
        """Return pacing gap in *ms* when effective frame total is supplied."""
        if frame_total_ms is None:
            return 0.0
        return max(0.0, float(frame_total_ms) - float(frame.total_ms))

    @staticmethod
    def cadence_breakdown_ms(
        frame: FrameTimings,
        *,
        frame_total_ms: float | None = None,
        cadence_wait_ms: float | None = None,
    ) -> tuple[float, float]:
        """Split cadence gap into scheduler-wait and present/wait buckets."""
        gap_ms = FrameProfileDetailsBuilder.cadence_gap_ms(
            frame,
            frame_total_ms=frame_total_ms,
        )
        if gap_ms <= 0.0:
            return 0.0, 0.0
        if cadence_wait_ms is None:
            return 0.0, gap_ms
        sched = max(0.0, min(float(cadence_wait_ms), gap_ms))
        return sched, max(0.0, gap_ms - sched)

    @staticmethod
    def residual_fraction(
        frame: FrameTimings,
        *,
        frame_total_ms: float | None = None,
    ) -> float:
        """Return unknown-render residual fraction [0, 1]."""
        total_ms = float(frame.total_ms) if frame_total_ms is None else float(
            frame_total_ms)
        total = max(total_ms, 1e-6)
        return FrameProfileDetailsBuilder.residual_ms(frame) / total

    @staticmethod
    def format_report(
        frame: FrameTimings,
        *,
        budget_ms: float = 16.6,
        frame_total_ms: float | None = None,
        cadence_wait_ms: float | None = None,
    ) -> str:
        """Return a plain-text profile report suitable for LLM review.

        Includes a ``WARNING`` prefix when unaccounted time exceeds the warn
        threshold, making it unambiguous to an automated reviewer.
        """
        measured_total = float(frame.total_ms)
        total = measured_total if frame_total_ms is None else float(
            frame_total_ms)
        residual = FrameProfileDetailsBuilder.residual_ms(frame)
        cadence_gap = FrameProfileDetailsBuilder.cadence_gap_ms(
            frame,
            frame_total_ms=frame_total_ms,
        )
        sched_wait_ms, present_wait_ms = FrameProfileDetailsBuilder.cadence_breakdown_ms(
            frame,
            frame_total_ms=frame_total_ms,
            cadence_wait_ms=cadence_wait_ms,
        )
        res_pct = (residual / max(total, 1e-6)) * 100.0
        cadence_gap_pct = (cadence_gap / max(total, 1e-6)) * 100.0
        # Budget verdict compares render work (paint_total) to budget, not the
        # cadence-inflated frame_total.  Scheduler wait is a delivery concern,
        # not a render-performance concern.
        render_delta = measured_total - budget_ms

        lines: list[str] = []
        lines.append(
            f"paint_total: {measured_total:.3f} ms  budget: {budget_ms:.1f} ms  render_delta: {render_delta:+.3f} ms"
        )
        if cadence_gap > 0.0:
            lines.append(
                f"frame_total: {total:.3f} ms  cadence_gap: {cadence_gap:.3f} ms  (scheduling overhead, not render work)"
            )
        else:
            lines.append(
                f"frame_total: {total:.3f} ms  cadence_gap: {cadence_gap:.3f} ms"
            )
        if cadence_gap > 0.0:
            lines.append(
                f"cadence_wait: {sched_wait_ms:.3f} ms  cadence_present: {present_wait_ms:.3f} ms"
            )
        lines.append(
            f"{'Stage':<22} {'Kind':<14} {'Z':>3}  {'ms':>8}  {'%':>6}")
        lines.append("-" * 58)

        rows = FrameProfileDetailsBuilder.build_rows(
            frame,
            frame_total_ms=frame_total_ms,
            cadence_wait_ms=cadence_wait_ms,
        )
        for name, kind, z_str, ms, pct in rows:
            lines.append(
                f"  {name:<20} {kind:<14} {z_str:>3}  {ms:>8.3f}  {pct:>5.1f}%")

        lines.append("-" * 58)
        timed_sum = FrameProfileDetailsBuilder.timed_sum_ms(frame)
        lines.append(
            f"  {'timed sum':<20} {'':14} {'':>3}  {timed_sum:>8.3f}  {(timed_sum / max(total, 1e-6)) * 100.0:>5.1f}%")
        lines.append(
            f"  {'untracked':<20} {'residual':<14} {'':>3}  {residual:>8.3f}  {res_pct:>5.1f}%")
        if cadence_gap > 0.0:
            lines.append(
                f"  {'frame pacing gap':<20} {'cadence_gap':<14} {'':>3}  {cadence_gap:>8.3f}  {cadence_gap_pct:>5.1f}%")
            lines.append(
                f"  {'frame scheduler wait':<20} {'cadence_wait':<14} {'':>3}  {sched_wait_ms:>8.3f}  {(sched_wait_ms / max(total, 1e-6)) * 100.0:>5.1f}%")
            lines.append(
                f"  {'frame present/wait':<20} {'cadence_present':<14} {'':>3}  {present_wait_ms:>8.3f}  {(present_wait_ms / max(total, 1e-6)) * 100.0:>5.1f}%")

        if res_pct >= _RESIDUAL_WARN_FRACTION * 100:
            lines.insert(
                0, f"WARNING: {res_pct:.1f}% of frame time is unaccounted — add profiling hooks to identify the missing stages.")

        return "\n".join(lines)


__all__ = ["FrameProfileDetailsBuilder"]

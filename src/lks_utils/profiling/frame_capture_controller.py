"""Frame profiling capture state controller.

Owns ring-buffer capture state, pause/resume semantics, and frame selection
for preview/detail inspection workflows.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from lks_utils.profiling.frame_sample import FrameSample

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_renderer import FrameTimings


@dataclass(frozen=True)
class FrameCaptureState:
    """Immutable snapshot of capture-selection state."""

    capture_enabled: bool
    selected_index: int
    live_index: int
    frame_count: int


class FrameCaptureController:
    """Ring-buffer capture controller for profile preview and details views.

    The controller stores recent frame timings, supports pausing capture while
    the host app keeps rendering, and lets consumers scrub/select historical
    frames for detailed inspection.

    **Replay mode**: after calling :meth:`load_session` the controller enters
    replay mode.  :attr:`replay_mode` returns ``True``, :meth:`replay_samples`
    returns the loaded :class:`FrameSample` list, and live capture is paused.
    Calling :meth:`set_capture_enabled` with ``True`` exits replay mode and
    resumes live capture.
    """

    def __init__(self, max_frames: int = 240) -> None:
        self._ring: deque[FrameTimings] = deque(
            maxlen=max(16, int(max_frames)))
        self._capture_enabled: bool = True
        self._selected_index: int = -1
        self._revision: int = 0
        self._replay_samples: list[FrameSample] = []

    @property
    def capture_enabled(self) -> bool:
        return self._capture_enabled

    @property
    def revision(self) -> int:
        """Monotonic change counter for efficient view refresh checks."""
        return self._revision

    def set_capture_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled:
            # Exiting replay mode unconditionally when resuming live capture
            self._replay_samples = []
        if self._capture_enabled == enabled:
            return
        self._capture_enabled = enabled
        if enabled:
            self._selected_index = -1
        self._revision += 1

    def clear(self) -> None:
        if not self._ring and self._selected_index < 0:
            return
        self._ring.clear()
        self._selected_index = -1
        self._revision += 1

    def push(self, timings: FrameTimings | None) -> None:
        """Append one frame timings sample when capture is enabled."""
        if timings is None or not self._capture_enabled:
            return
        self._ring.append(timings)
        self._revision += 1

    def select_frame(self, idx: int) -> None:
        if not self._ring:
            return
        n = len(self._ring)
        clamped = max(0, min(int(idx), n - 1))
        if self._selected_index == clamped and not self._capture_enabled:
            return
        self._selected_index = clamped
        if self._capture_enabled:
            self._capture_enabled = False
        self._revision += 1

    def select_live(self) -> None:
        if self._selected_index < 0 and self._capture_enabled:
            return
        self._selected_index = -1
        self._capture_enabled = True
        self._revision += 1

    def frames(self) -> list[FrameTimings]:
        return list(self._ring)

    def state(self) -> FrameCaptureState:
        n = len(self._ring)
        live_idx = n - 1 if n else -1
        display_idx = live_idx if (self._capture_enabled or self._selected_index < 0) else min(
            self._selected_index,
            live_idx,
        )
        return FrameCaptureState(
            capture_enabled=self._capture_enabled,
            selected_index=display_idx,
            live_index=live_idx,
            frame_count=n,
        )

    def selected_frame(self) -> FrameTimings | None:
        if not self._ring:
            return None
        st = self.state()
        if st.selected_index < 0:
            return None
        return list(self._ring)[st.selected_index]

    # ── Replay mode ────────────────────────────────────────────────────────

    @property
    def replay_mode(self) -> bool:
        """``True`` while a loaded session is being replayed."""
        return bool(self._replay_samples)

    def replay_samples(self) -> list[FrameSample]:
        """Return the loaded frame samples when in replay mode."""
        return list(self._replay_samples)

    # ── Session export / import ────────────────────────────────────────────

    def export_session(
        self,
        path: Path | str,
        adapter_fn: Callable[[FrameTimings, int], FrameSample],
    ) -> int:
        """Serialize all buffered frames to a ``.lksprof`` gzip JSONL file.

        Args:
            path: Destination file path.
            adapter_fn: Callable mapping ``(FrameTimings, frame_index) ->
                FrameSample`` — typically
                ``CanvasFrameTimingsAdapter.adapt``.

        Returns:
            Number of frames written.
        """
        from lks_utils.profiling.session_io import export_session as _io_export

        frames_list = list(self._ring)
        samples = [
            adapter_fn(frame, idx)
            for idx, frame in enumerate(frames_list)
        ]
        _io_export(path, samples)
        return len(samples)

    def load_session(self, path: Path | str) -> int:
        """Load a ``.lksprof`` file into replay mode.

        Pauses live capture and stores the loaded samples.  Call
        :meth:`set_capture_enabled(True)` to exit replay mode.

        Args:
            path: Path to a ``.lksprof`` gzip JSONL file.

        Returns:
            Number of frames loaded.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If the file is malformed.
        """
        from lks_utils.profiling.session_io import load_session as _io_load

        samples = _io_load(path)
        self._replay_samples = samples
        self._capture_enabled = False
        self._selected_index = 0 if samples else -1
        self._revision += 1
        return len(samples)


__all__ = ["FrameCaptureController", "FrameCaptureState"]

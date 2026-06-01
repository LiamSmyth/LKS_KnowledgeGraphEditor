"""Reusable helper to mount a PerfHudWidget in any Qt demo window.

The controller wires a ``PerfHudWidget`` into a ``QMainWindow`` dock and
feeds FPS samples by listening to ``QEvent.Paint`` on a target widget.
This avoids requiring target widgets to expose custom profiling signals.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

from lks_utils.gui_qt.widgets.dock_host import DockSpec, QDockHost
from lks_utils.gui_qt.widgets.perf_hud_widget import PerfHudWidget


class PerfHudDockController(QObject):
    """Attach a live ``PerfHudWidget`` dock to a ``QMainWindow``.

    Args:
        window: Main window that will host the dock.
        frame_source: Widget whose paint events should feed FPS ticks.
        title: Dock title.
        area: Dock area used when adding the perf dock.
        history_seconds: Initial rolling graph window in seconds.
    """

    def __init__(
        self,
        window: QMainWindow,
        frame_source: QWidget,
        *,
        title: str = "Perf HUD",
        area: Qt.DockWidgetArea = Qt.DockWidgetArea.RightDockWidgetArea,
        history_seconds: int = 12,
        dock_host: QDockHost | None = None,
        dock_id: str = "perf_hud",
    ) -> None:
        super().__init__(window)
        self._window = window
        self._frame_source = frame_source
        self._dock_host = dock_host or QDockHost(window)

        self._hud = PerfHudWidget(history_seconds=history_seconds)
        self._dock = self._dock_host.create_or_replace(
            dock_id=dock_id,
            widget=self._hud,
            spec=DockSpec(title=title, area=area),
        )
        self._dock.resize(220, self._dock.height())

        self._frame_source.installEventFilter(self)

    @property
    def hud(self) -> PerfHudWidget:
        """Return the managed perf HUD widget."""
        return self._hud

    @property
    def dock(self) -> QDockWidget:
        """Return the managed dock widget."""
        return self._dock

    def mark_event(self, label: str, color: str = "#3cf") -> None:
        """Forward a timeline marker to the managed HUD."""
        self._hud.mark_event(label, color)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._frame_source and event.type() == QEvent.Type.Paint:
            self._hud.tick_frame()
        return super().eventFilter(watched, event)

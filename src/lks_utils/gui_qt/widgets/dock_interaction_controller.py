"""Grip-driven dock interaction controller with preview and rollback."""
from __future__ import annotations

from dataclasses import dataclass
import os

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QEvent
from PySide6.QtGui import QColor, QCursor, QMouseEvent, QPaintEvent, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget

from lks_utils.gui_qt.widgets.dock_drop_region import DockDropRegion, diagonal_region, region_diagonal_polygon, region_rect


@dataclass(slots=True)
class _DockDragOrigin:
    area: Qt.DockWidgetArea
    was_floating: bool
    geometry: QRect


class _DockPreviewOverlay(QWidget):
    """Semi-transparent overlay used to preview split docking targets."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        palette = self.palette()
        fill = QColor(palette.color(QPalette.ColorRole.Highlight))
        fill.setAlpha(58)
        border = QColor(palette.color(QPalette.ColorRole.Highlight))
        border.setAlpha(180)
        painter.fillRect(self.rect(), fill)
        painter.setPen(border)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


class _DockRegionDebugOverlay(QWidget):
    """Overlay that visualizes all four diagonal triangular regions and the active one."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._active: DockDropRegion | None = None
        self.hide()

    # bands arg kept for compat
    def set_regions(self, bands: object, active: DockDropRegion | None) -> None:
        self._active = active
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        palette = self.palette()
        passive_fill = QColor(palette.color(QPalette.ColorRole.Highlight))
        passive_fill.setAlpha(24)
        active_fill = QColor(palette.color(QPalette.ColorRole.Highlight))
        active_fill.setAlpha(90)
        border = QColor(palette.color(QPalette.ColorRole.Highlight))
        border.setAlpha(165)

        rect = self.rect()
        painter.setPen(border)
        for region in DockDropRegion:
            poly = region_diagonal_polygon(rect, region)
            painter.setBrush(active_fill if region ==
                             self._active else passive_fill)
            painter.drawPolygon(poly)


class QDockInteractionController(QObject):
    """Provides grip-only drag, region preview, and invalid-drop rollback."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._active_dock: QDockWidget | None = None
        self._origin: _DockDragOrigin | None = None
        self._target_dock: QDockWidget | None = None
        self._target_region: DockDropRegion | None = None
        self._preview = _DockPreviewOverlay(window)
        self._region_debug = _DockRegionDebugOverlay(window)
        self._app_filter_installed = False
        self._debug_hover_regions_enabled = os.environ.get(
            "LKS_DOCK_DEBUG_REGIONS") == "1"

    def set_debug_hover_regions_enabled(self, enabled: bool) -> None:
        """Enable or disable hover-band debug rendering."""
        self._debug_hover_regions_enabled = enabled
        if not enabled:
            self._region_debug.hide()

    def begin_grip_drag(self, dock: QDockWidget, global_pos: QPoint) -> None:
        """Start tracking a dock drag initiated from a grip widget."""
        if self._active_dock is not None:
            return
        origin_area = self._window.dockWidgetArea(dock)
        self._active_dock = dock
        self._origin = _DockDragOrigin(
            area=origin_area,
            was_floating=dock.isFloating(),
            geometry=dock.geometry(),
        )
        dock.raise_()
        if not dock.isFloating():
            dock.setFloating(True)
        self._move_active_dock(global_pos)
        self._handle_drag_move(global_pos)
        self._install_app_filter()

    def update_drag(self, global_pos: QPoint) -> None:
        """Update an in-progress drag to a new global pointer position."""
        self._handle_drag_move(global_pos)

    def release_drag(self, global_pos: QPoint) -> None:
        """Release an in-progress drag at the provided global position."""
        self._handle_drag_release(global_pos)

    def end_drag(self) -> None:
        """Force-end any in-progress drag and rollback if needed."""
        if self._active_dock is None:
            return
        self._rollback_active_dock()
        self._clear_drag_state()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self._active_dock is None:
            return False
        if event.type() == QEvent.Type.MouseMove:
            mouse_event = event  # type: ignore[assignment]
            if isinstance(mouse_event, QMouseEvent):
                self.update_drag(mouse_event.globalPosition().toPoint())
            return False
        if event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event = event  # type: ignore[assignment]
            if isinstance(mouse_event, QMouseEvent):
                self.release_drag(mouse_event.globalPosition().toPoint())
            return False
        return False

    def _install_app_filter(self) -> None:
        app = QApplication.instance()
        if app is None or self._app_filter_installed:
            return
        app.installEventFilter(self)
        self._app_filter_installed = True

    def _remove_app_filter(self) -> None:
        app = QApplication.instance()
        if app is None or not self._app_filter_installed:
            return
        app.removeEventFilter(self)
        self._app_filter_installed = False

    def _handle_drag_move(self, global_pos: QPoint) -> None:
        if self._active_dock is None:
            return
        self._move_active_dock(global_pos)
        target_dock = self._find_target_dock(global_pos)
        if target_dock is None:
            self._clear_preview()
            return

        local = target_dock.mapFromGlobal(global_pos)
        region = diagonal_region(target_dock.rect(), local)
        if region is None:
            self._clear_preview()
            return

        preview_local = region_rect(target_dock.rect(), region)
        self._preview.setParent(target_dock)
        self._preview.setGeometry(preview_local)
        self._preview.show()
        self._preview.raise_()
        self._update_region_debug_overlay(target_dock, None, region)
        self._target_dock = target_dock
        self._target_region = region
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.DragMoveCursor))

    def _handle_drag_release(self, global_pos: QPoint) -> None:
        if self._active_dock is None:
            return
        self._handle_drag_move(global_pos)
        if self._target_dock is not None and self._target_region is not None:
            self._commit_drop(self._target_dock, self._target_region)
        else:
            self._rollback_active_dock()
        self._clear_drag_state()

    def _move_active_dock(self, global_pos: QPoint) -> None:
        if self._active_dock is None:
            return
        self._active_dock.move(global_pos - QPoint(18, 12))

    def _find_target_dock(self, global_pos: QPoint) -> QDockWidget | None:
        active = self._active_dock
        if active is None:
            return None

        candidates: list[tuple[int, QDockWidget]] = []
        for dock in self._window.findChildren(QDockWidget):
            if dock is active or not dock.isVisible() or dock.isFloating():
                continue
            if dock.window() is not self._window and not self._window.isAncestorOf(dock):
                continue

            top_left = dock.mapToGlobal(QPoint(0, 0))
            global_rect = QRect(top_left, dock.size())
            if not global_rect.contains(global_pos):
                continue

            candidates.append(
                (global_rect.width() * global_rect.height(), dock))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _commit_drop(self, target: QDockWidget, region: DockDropRegion) -> None:
        active = self._active_dock
        if active is None or active is target:
            return

        target_area = self._window.dockWidgetArea(target)
        if target_area == Qt.DockWidgetArea.NoDockWidgetArea:
            target_area = Qt.DockWidgetArea.RightDockWidgetArea

        # Step 1 — stage active into the layout via a *different* area than
        # target's.  Using target's own area would cause Qt to tabify active
        # with target; splitDockWidget on a tabified pair either silently
        # no-ops or crashes.  Staging in a different area keeps active and
        # target in separate tab groups so the split always works.
        _STAGING_PREFERENCE = [
            Qt.DockWidgetArea.BottomDockWidgetArea,
            Qt.DockWidgetArea.TopDockWidgetArea,
            Qt.DockWidgetArea.LeftDockWidgetArea,
            Qt.DockWidgetArea.RightDockWidgetArea,
        ]
        staging_area = next(
            (a for a in _STAGING_PREFERENCE if a != target_area),
            Qt.DockWidgetArea.BottomDockWidgetArea,
        )
        # Temporarily allow all areas so addDockWidget does not fail silently
        # if staging_area is outside the dock's declared allowedAreas.
        original_allowed = active.allowedAreas()
        active.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        active.setFloating(False)
        self._window.addDockWidget(staging_area, active)
        active.setAllowedAreas(original_allowed)

        # Step 2 — split with target.  Both docks are now in the layout (in
        # different areas) so splitDockWidget relocates active cleanly.
        # For RIGHT/BOTTOM one pass suffices.  For LEFT/TOP we do a two-pass
        # swap: the first split places active on the wrong side; the second
        # swap corrects it.

        orient_h = Qt.Orientation.Horizontal
        orient_v = Qt.Orientation.Vertical

        if region == DockDropRegion.RIGHT:
            self._window.splitDockWidget(target, active, orient_h)
            return

        if region == DockDropRegion.BOTTOM:
            self._window.splitDockWidget(target, active, orient_v)
            return

        if region == DockDropRegion.LEFT:
            # Pass 1: active enters layout to the right of target.
            self._window.splitDockWidget(target, active, orient_h)
            # Pass 2: active owns a real slot now; swap so it goes left.
            self._window.splitDockWidget(active, target, orient_h)
            return

        # TOP — same two-pass swap, vertical.
        self._window.splitDockWidget(target, active, orient_v)
        self._window.splitDockWidget(active, target, orient_v)

    def _rollback_active_dock(self) -> None:
        active = self._active_dock
        origin = self._origin
        if active is None or origin is None:
            return

        if origin.was_floating:
            active.setFloating(True)
            active.setGeometry(origin.geometry)
            return

        active.setFloating(False)
        area = origin.area
        if area == Qt.DockWidgetArea.NoDockWidgetArea:
            area = Qt.DockWidgetArea.RightDockWidgetArea
        self._window.addDockWidget(area, active)
        active.show()

    def _clear_preview(self) -> None:
        self._target_dock = None
        self._target_region = None
        self._preview.hide()
        self._region_debug.hide()
        QApplication.restoreOverrideCursor()

    def _update_region_debug_overlay(
        self,
        target_dock: QDockWidget,
        bands: object,  # unused; kept for call-site compat
        active_region: DockDropRegion,
    ) -> None:
        if not self._debug_hover_regions_enabled:
            self._region_debug.hide()
            return

        self._region_debug.setParent(target_dock)
        self._region_debug.setGeometry(target_dock.rect())
        self._region_debug.set_regions(bands, active_region)
        self._region_debug.show()
        self._region_debug.raise_()

    def _clear_drag_state(self) -> None:
        self._remove_app_filter()
        self._clear_preview()
        self._active_dock = None
        self._origin = None

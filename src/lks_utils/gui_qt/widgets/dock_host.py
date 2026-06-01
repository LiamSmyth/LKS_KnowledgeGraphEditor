"""Reusable dock host helpers for Qt main windows.

Provides a tiny v1 abstraction over ``QMainWindow`` dock management so
apps can register and control docks without re-implementing the same
setup logic in every window class.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

from lks_utils.gui_qt.widgets.dock_grip_bar import QDockGripBar
from lks_utils.gui_qt.widgets.dock_interaction_controller import QDockInteractionController

DEFAULT_DOCK_FEATURES = (
    QDockWidget.DockWidgetFeature.DockWidgetClosable
    | QDockWidget.DockWidgetFeature.DockWidgetMovable
    | QDockWidget.DockWidgetFeature.DockWidgetFloatable
)

DEFAULT_DOCK_ALLOWED_AREAS = (
    Qt.DockWidgetArea.LeftDockWidgetArea
    | Qt.DockWidgetArea.RightDockWidgetArea
)


@dataclass(frozen=True, slots=True)
class DockSpec:
    """Declarative dock configuration used by :class:`QDockHost`."""

    title: str
    area: Qt.DockWidgetArea = Qt.DockWidgetArea.RightDockWidgetArea
    allowed_areas: Qt.DockWidgetArea = DEFAULT_DOCK_ALLOWED_AREAS
    features: QDockWidget.DockWidgetFeature = DEFAULT_DOCK_FEATURES
    visible: bool = True
    floating: bool = False
    grip_only: bool = False


class QDockHost(QObject):
    """Manage named ``QDockWidget`` instances for a ``QMainWindow``."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._docks: dict[str, QDockWidget] = {}
        self._interaction_controller: QDockInteractionController | None = None
        self._separator_affordance_enabled = False

    def dock(self, dock_id: str) -> QDockWidget | None:
        """Return a managed dock by id, if it exists."""
        return self._docks.get(dock_id)

    def create_or_replace(
        self,
        dock_id: str,
        widget: QWidget,
        spec: DockSpec,
    ) -> QDockWidget:
        """Create a dock or replace the dock widget content for an id."""
        dock = self._docks.get(dock_id)
        if dock is None:
            dock = QDockWidget(spec.title, self._window)
            self._docks[dock_id] = dock
            self._window.addDockWidget(spec.area, dock)

        features = spec.features
        if spec.grip_only:
            features &= ~QDockWidget.DockWidgetFeature.DockWidgetClosable
        dock.setFeatures(features)
        dock.setAllowedAreas(spec.allowed_areas)
        dock.setWidget(widget)
        # Apply (or refresh) the grip title bar.
        grip_bar = QDockGripBar(spec.title, dock)
        dock.setTitleBarWidget(grip_bar)
        dock.setWindowTitle(spec.title)
        dock.setFloating(spec.floating)
        dock.setVisible(spec.visible)

        if self._interaction_controller is not None:
            self._wire_grip_interaction(dock, grip_bar)
        return dock

    def enable_grip_docking_interactions(self) -> QDockInteractionController:
        """Enable grip-driven docking preview/rollback interactions for docks."""
        if self._interaction_controller is None:
            self._interaction_controller = QDockInteractionController(
                self._window)
            for dock in self._docks.values():
                title_widget = dock.titleBarWidget()
                if isinstance(title_widget, QDockGripBar):
                    self._wire_grip_interaction(dock, title_widget)
        self._enable_separator_affordance()
        return self._interaction_controller

    def ensure_visible(self, dock_id: str) -> bool:
        """Show and raise a dock if present."""
        dock = self._docks.get(dock_id)
        if dock is None:
            return False
        if not dock.isVisible():
            dock.show()
        dock.raise_()
        return True

    def redock(self, dock_id: str, area: Qt.DockWidgetArea) -> bool:
        """Dock an existing widget into the requested area."""
        dock = self._docks.get(dock_id)
        if dock is None:
            return False
        if dock.isFloating():
            dock.setFloating(False)
        self._window.addDockWidget(area, dock)
        dock.raise_()
        return True

    def _wire_grip_interaction(self, dock: QDockWidget, grip_bar: QDockGripBar) -> None:
        controller = self._interaction_controller
        if controller is None:
            return
        if grip_bar.property("_lks_grip_wired") is True:
            return

        grip_bar.grip_mouse_pressed.connect(
            lambda global_pos, dock=dock: controller.begin_grip_drag(
                dock, global_pos)
        )
        grip_bar.grip_mouse_moved.connect(controller.update_drag)
        grip_bar.grip_mouse_released.connect(controller.release_drag)
        grip_bar.setProperty("_lks_grip_wired", True)

    def _enable_separator_affordance(self) -> None:
        if self._separator_affordance_enabled:
            return
        self._separator_affordance_enabled = True

        palette = self._window.palette()
        idle = palette.color(palette.ColorRole.Mid).name()
        hover = palette.color(palette.ColorRole.Highlight).name()
        separator_qss = (
            "QMainWindow::separator {"
            f"background: {idle};"
            "width: 4px;"
            "height: 4px;"
            "}"
            "QMainWindow::separator:hover {"
            f"background: {hover};"
            "}"
        )
        existing = self._window.styleSheet()
        if "QMainWindow::separator" not in existing:
            self._window.setStyleSheet(
                (existing + "\n" + separator_qss).strip())

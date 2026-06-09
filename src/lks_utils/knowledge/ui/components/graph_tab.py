"""Graph-view tab assembly for the knowledge workbench."""
from __future__ import annotations
from lks_utils.knowledge.ui.components._graph_tab.link_router import install_link_router_helpers
from lks_utils.knowledge.ui.components._graph_tab.layout_engine import install_layout_engine_helpers
from lks_utils.knowledge.ui.components._graph_tab.hit_test import install_hit_test_helpers
from lks_utils.knowledge.ui.components._graph_tab.drag_controller import install_drag_controller_helpers
from lks_utils.knowledge.ui.components._graph_tab.canvas_object_factory import install_canvas_object_factory_helpers

import dataclasses
import logging
import time
from dataclasses import dataclass
from contextlib import contextmanager
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QEvent, QFileSystemWatcher, QObject, QSettings, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from ulid import ULID

from lks_utils.events import EventBus
from lks_utils.knowledge.default_theme import (
    FIELD_BUTTON_BG,
    FIELD_BUTTON_BORDER,
    FIELD_BUTTON_DISABLED_BORDER,
    FIELD_BUTTON_DISABLED_TEXT,
    FIELD_BUTTON_HOVER_BORDER,
    FIELD_BUTTON_PRESSED_BG,
    FIELD_BUTTON_PRESSED_BORDER,
    FIELD_BUTTON_TEXT,
    FIELD_MONO_FONT_FAMILY,
    REF_VALID_COLOR,
    SCENE_BACKGROUND_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.ui.live_reload_coordinator import LiveReloadCoordinator
from lks_utils.knowledge.link_type_view_state import LinkTypeViewState
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID, LinkType
from lks_utils.knowledge.instance_validator import (
    PROPERTY_VERSIONS_PROP,
    VALIDATION_ERRORS_PROP,
    VALIDATION_STATUS_CANNOT_COMPILE,
    VALIDATION_STATUS_PROP,
    TYPE_VERSION_PROP,
    InstanceValidator,
)
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.graph_view_node_proxy import GraphViewNodeProxy
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.operations.delete_safety_analyzer import analyze_delete_impact
from lks_utils.knowledge.data_interface.link_mutation_bridge import LinkMutationBridge
from lks_utils.knowledge.ui.graph_link_creation_state_machine import (
    GraphLinkCreationEvent,
    GraphLinkCreationState,
    transition_graph_link_creation_state,
)
from lks_utils.knowledge.ui.components.context_library_panel import QKnowledgeContextLibraryPanel
from lks_utils.knowledge.ui.components.connections_panel import QKnowledgeConnectionsPanel
from lks_utils.knowledge.ui.components.graph_instance_palette_panel import QGraphInstancePalettePanel
from lks_utils.knowledge.ui.components.graph_layout_ribbon_component import QGraphLayoutRibbonComponent
from lks_utils.knowledge.ui.components.graph_link_type_palette_panel import QGraphLinkTypePalettePanel
from lks_utils.knowledge.ui.components.graph_perf_window import QKnowledgeGraphPerfWindow
from lks_utils.knowledge.ui.components.graph_type_palette_panel import QGraphTypePalettePanel
from lks_utils.knowledge.ui.components.properties_panel import QKnowledgeInspectorPanel
from lks_utils.knowledge.ui.components.ref_aware_delete_dialog import QKnowledgeRefAwareDeleteDialog
from lks_utils.knowledge.ui.editor_tab_base import QKnowledgeEditorTabBase
from lks_utils.knowledge.ui.graph_layout_ops import layout_positions
from lks_utils.graph2d_layout.algorithms.networkx_spread_node_layout_algorithm2d import (
    NetworkXSpreadNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D
from lks_utils.knowledge.ui.widgets.graph_canvas import (
    BatchPlacementPayload,
    QKnowledgeGraphCanvasWidget,
    estimate_graph_node_size_for_proxy,
)
from lks_utils.knowledge.ui.widgets.graph_node_canvas_object import QKnowledgeGraphNodeCanvasObject
from lks_utils.knowledge.ui.widgets.validation_log import QKnowledgeValidationLogWidget
from lks_utils.gui_qt.base.async_task_runner import WorkerThread

_EMPTY_GRAPH_VIEW = GraphView(
    id="graph_empty", name="Empty Graph", nodes={}, edges={})
_OWN_FS_WRITE_SUPPRESSION_SECONDS = 1.0
_DEFAULT_LIVE_RELOAD_ENABLED = True
_DEFAULT_LIVE_RELOAD_DEBOUNCE_MS = 400
_DEFAULT_LIVE_RELOAD_POLL_MS = 2000
_DEFAULT_LIVE_RELOAD_MIN_GAP_MS = 1000
_DEFAULT_LIVE_RELOAD_ON_FOCUS = True


@dataclass(frozen=True, slots=True)
class _ExternalReloadScanResult:
    revision: int
    scanned_roots: tuple[str, ...]
    changed_files: set[str]
    new_state: dict[str, tuple[int, int]]


class QKnowledgeGraphTabWidget(QKnowledgeEditorTabBase):
    """Workbench tab: library + palettes | graph canvas | inspector + connections."""

    _SETTINGS_ORG = "lks_utils"
    _SETTINGS_APP = "KnowledgeWorkbench"

    # global_id of the already-placed node
    duplicate_drop_rejected = Signal(str)
    external_repo_change_detected = Signal(str)

    def __init__(
        self,
        session: EditorSession,
        parent: QWidget | None = None,
        *,
        ui_event_bus: EventBus | None = None,
    ) -> None:
        super().__init__(session, parent)
        self._session = session
        self._ui_event_bus = ui_event_bus
        self._current_graph_view_id: str | None = None
        self._current_graph_view: GraphView | None = None

        self._library = QKnowledgeContextLibraryPanel(
            session, "graph_view", self)
        self._type_palette = QGraphTypePalettePanel(session, self)
        self._instance_palette = QGraphInstancePalettePanel(session, self)
        self._link_type_palette = QGraphLinkTypePalettePanel(session, self)
        self._palette_tabs = QTabWidget(self)
        self._palette_tabs.addTab(self._type_palette, "Types")
        self._palette_tabs.addTab(self._instance_palette, "Instances")

        self._validation_log = QKnowledgeValidationLogWidget(self)
        self._properties = QKnowledgeInspectorPanel(
            session, draft_edits=True, parent=self)
        self._properties.node_selection_requested.connect(
            self._on_inspector_node_selection_requested
        )
        self._properties.mutation_applied.connect(
            self._on_inspector_mutation_applied
        )
        self._connections_panel = QKnowledgeConnectionsPanel(session, self)

        self._canvas = QKnowledgeGraphCanvasWidget(self)
        self._canvas.instance_dropped.connect(self._on_instance_dropped)
        self._canvas.instances_dropped.connect(self._on_instances_dropped)
        self._canvas.type_dropped.connect(self._on_type_dropped)
        self._canvas.objects_moved.connect(self._on_canvas_objects_moved)
        self._canvas.clear_selection_requested.connect(
            self._on_clear_selected_proxies)
        self._canvas.delete_selection_requested.connect(
            self._on_delete_selected_nodes)
        self._canvas.selection_changed.connect(
            self._on_canvas_selection_changed)
        self._canvas.selection_model_changed.connect(
            self._on_canvas_selection_model_changed)
        self._canvas.node_selected.connect(self._on_canvas_node_selected)
        self._canvas.pointer_gesture_finished.connect(
            self._on_canvas_pointer_gesture_finished)
        self._canvas.link_selected.connect(self._on_canvas_link_selected)
        self._canvas.link_source_drag_started.connect(
            self._on_link_source_drag_started)
        self._canvas.link_source_drag_hovered.connect(
            self._on_link_source_drag_hovered)
        self._canvas.link_source_drop_finished.connect(
            self._on_link_source_drop_finished)
        self._canvas.link_target_hovered.connect(self._on_link_target_hovered)
        self._canvas.link_target_clicked.connect(self._on_link_target_clicked)
        self._canvas.link_creation_cancel_requested.connect(
            self._on_link_creation_cancel_requested)
        self._canvas.view_changed.connect(self._on_canvas_view_changed)

        self._library.node_load_requested.connect(self.load_graph_view_by_id)
        self._library.node_renamed.connect(self._on_graph_view_renamed)
        self._library.node_deleted.connect(self._on_graph_view_deleted)
        self._validation_log.focus_node_requested.connect(
            self._on_validation_focus_requested)
        self._session.validation_index.validation_changed.connect(
            self._on_validation_changed)
        self._link_type_palette.link_type_drag_started.connect(
            self._on_link_source_drag_started)
        self._link_type_palette.link_type_view_state_changed.connect(
            self._on_link_type_view_state_changed
        )

        self._link_creation_state: GraphLinkCreationState = GraphLinkCreationState.IDLE
        self._link_creation_link_type_id: str | None = None
        self._link_creation_source_node_id: str | None = None
        self._link_creation_hover_node_id: str | None = None
        self._link_creation_hover_world: tuple[float, float] | None = None
        self._selected_canvas_ids: set[str] = set()
        self._active_canvas_id: str | None = None
        self._pending_targeted_node_refresh_ids: set[str] | None = None
        self._pending_selection_side_panel_node_id: str | None = None
        self._selection_side_panel_flush_scheduled: bool = False
        self._link_type_view_state = LinkTypeViewState()
        self._traversal_direction: Literal["forward", "back", "both"] = "both"
        self._repo_watcher = QFileSystemWatcher(self)
        self._watched_repo_root: Path | None = None
        self._watched_repo_paths: set[Path] = set()
        self._own_repo_write_depth: int = 0
        self._suppress_external_reload_until: float = 0.0
        self._external_reload_enabled: bool = _DEFAULT_LIVE_RELOAD_ENABLED
        self._external_reload_debounce_ms: int = _DEFAULT_LIVE_RELOAD_DEBOUNCE_MS
        self._external_reload_poll_ms: int = _DEFAULT_LIVE_RELOAD_POLL_MS
        self._external_reload_min_gap_ms: int = _DEFAULT_LIVE_RELOAD_MIN_GAP_MS
        self._external_reload_on_focus: bool = _DEFAULT_LIVE_RELOAD_ON_FOCUS
        self._pending_external_paths: set[str] = set()
        self._known_repo_file_state: dict[str, tuple[int, int]] = {}
        self._external_reload_pending_path: str | None = None
        self._external_reload_in_progress: bool = False
        self._external_reload_requested_again: bool = False
        self._external_event_journal_offset: int = 0
        self._last_external_reload_finished_at: float = 0.0
        self._window_activation_source: QObject | None = None
        self._known_repo_file_state_revision: int = 0
        self._external_reload_scan_worker: WorkerThread | None = None
        self._external_reload_timer = QTimer(self)
        self._external_reload_timer.setSingleShot(True)
        self._external_reload_timer.timeout.connect(
            self._flush_external_reload_queue)
        self._external_reload_poll_timer = QTimer(self)
        self._external_reload_poll_timer.setSingleShot(False)
        self._external_reload_poll_timer.timeout.connect(
            self._on_external_reload_poll_tick)
        self._viewport_sidecar_write_timer = QTimer(self)
        self._viewport_sidecar_write_timer.setSingleShot(True)
        self._viewport_sidecar_write_timer.setInterval(180)
        self._viewport_sidecar_write_timer.timeout.connect(
            self._flush_canvas_viewport_sidecar_write)
        self._load_live_reload_settings()
        self._live_reload_coordinator = LiveReloadCoordinator(self._session)
        self._live_reload_coordinator.journal_offset = (
            self._external_event_journal_offset
        )
        self._perf_button: QPushButton | None = None
        self._perf_window: QKnowledgeGraphPerfWindow | None = None

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self.refresh_palettes()
        self.set_graph_view(None)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._install_window_activation_filter()

    def current_graph_view_id(self) -> str | None:
        """Return the currently loaded graph view id, if any."""
        return self._current_graph_view_id

    def _build_ribbon(self) -> QWidget:
        """Build the top ribbon and append graph utility controls."""
        ribbon = super()._build_ribbon()
        row = ribbon.layout()
        if not isinstance(row, QHBoxLayout):
            return ribbon

        section = QWidget(ribbon)
        section.setObjectName("graph_controls_section")
        section_layout = QHBoxLayout(section)
        section_layout.setContentsMargins(8, 0, 8, 0)
        section_layout.setSpacing(6)

        self._perf_button = QPushButton("Perf", section)
        self._perf_button.setObjectName("graph_perf_button")
        self._perf_button.setToolTip(
            "Open the floating graph performance window")
        self._perf_button.clicked.connect(self._open_perf_window)
        section_layout.addWidget(self._perf_button)

        row.insertWidget(1, section)
        return ribbon

    def _open_perf_window(self) -> None:
        if self._perf_window is None:
            self._perf_window = QKnowledgeGraphPerfWindow(
                self._canvas, self.window())
            self._perf_window.destroyed.connect(self._on_perf_window_destroyed)
        self._perf_window.show()
        self._perf_window.raise_()
        self._perf_window.activateWindow()

    def _on_perf_window_destroyed(self) -> None:
        self._perf_window = None

    def reload_live_reload_settings(self) -> None:
        self._load_live_reload_settings()

    def refresh_palettes(self) -> None:
        """Refresh all left-dock palette panels from session state."""
        self._type_palette.refresh()
        self._instance_palette.refresh()
        self._link_type_palette.refresh()
        self._link_type_palette.set_view_state(self._link_type_view_state)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.remove_listener(self._on_session_change)
        try:
            self._session.validation_index.validation_changed.disconnect(
                self._on_validation_changed)
        except (TypeError, RuntimeError):
            pass
        self._remove_window_activation_filter()
        self._repo_watcher.directoryChanged.disconnect(
            self._on_repo_fs_changed)
        self._repo_watcher.fileChanged.disconnect(self._on_repo_fs_changed)
        if self._perf_window is not None:
            self._perf_window.close()
        super().closeEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self._window_activation_source
            and event.type() == QEvent.Type.WindowActivate
            and self._external_reload_on_focus
        ):
            self._request_external_reload(immediate=True)
        return super().eventFilter(watched, event)

    def set_graph_view(
        self,
        graph_view: GraphView | None,
        *,
        nodes_by_id: Mapping[str, Node] | None = None,
        preserve_view: bool = False,
    ) -> None:
        """Load ``graph_view`` into the canvas or clear to an empty view."""
        if graph_view is None:
            self._current_graph_view_id = None
            self._current_graph_view = None
            self._canvas.load_graph_view(
                _EMPTY_GRAPH_VIEW,
                nodes_by_id={},
                links_by_id={},
                link_types_by_id={},
            )
            self._properties.clear()
            self._connections_panel.set_node(None)
            self._library.set_current_open_node(None)
            self._canvas_title.setText("No graph loaded")
            self._revert_btn.setEnabled(False)
            return
        self._current_graph_view_id = str(graph_view.id)
        self._current_graph_view = graph_view
        resolved_nodes = nodes_by_id
        if resolved_nodes is None:
            resolved_nodes = {
                str(node.id): node for node in self._session.list_nodes()}
        links_by_id = self._collect_links_by_id()
        link_types_by_id = self._collect_link_types_by_id()
        if preserve_view:
            self._reload_canvas_preserving_view(
                graph_view,
                resolved_nodes,
                links_by_id,
                link_types_by_id,
            )
        else:
            self._canvas.load_graph_view(
                graph_view,
                nodes_by_id=resolved_nodes,
                links_by_id=links_by_id,
                link_types_by_id=link_types_by_id,
                preserve_view=False,
            )
            # Ensure framing happens after the tab/canvas has settled to its
            # final layout size; immediate framing can be computed against a
            # transient size and leave cards clipped at top/left edges.
            QTimer.singleShot(
                0,
                lambda: self._canvas.frame_all_graph_nodes(
                    buffer_world_px=180.0,
                    animate=False,
                ),
            )
        self._library.set_current_open_node(str(graph_view.id))
        self._canvas_title.setText(graph_view.name)
        self._revert_btn.setEnabled(True)
        self._properties.clear()
        self._connections_panel.set_node(None)
        self._wire_node_card_actions()
        self._refresh_graph_validation_badges()
        self._canvas.apply_link_type_view_state(self._link_type_view_state)


# Install extracted private helpers onto QKnowledgeGraphTabWidget.

install_layout_engine_helpers(QKnowledgeGraphTabWidget)
install_hit_test_helpers(QKnowledgeGraphTabWidget)
install_link_router_helpers(QKnowledgeGraphTabWidget)
install_canvas_object_factory_helpers(QKnowledgeGraphTabWidget)
install_drag_controller_helpers(QKnowledgeGraphTabWidget)

__all__ = ["QKnowledgeGraphTabWidget"]

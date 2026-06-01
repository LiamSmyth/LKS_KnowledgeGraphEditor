"""Private helper methods extracted from graph_tab.py."""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from ulid import ULID

from lks_utils.events import EventEnvelope
from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    NODE_TEXT_COLOR,
    REF_VALID_COLOR,
    SCENE_BACKGROUND_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.canvas.canvas_io import CanvasIO
from lks_utils.knowledge.io.knowledge_change_journal import (
    journal_file_path,
    read_change_events_since,
)
from lks_utils.knowledge.link_type_view_state import LinkTypeViewState
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID, LinkType
from lks_utils.knowledge.instance_validator import (
    VALIDATION_ERRORS_PROP,
    VALIDATION_STATUS_CANNOT_COMPILE,
    VALIDATION_STATUS_PROP,
    InstanceValidator,
)
from lks_utils.knowledge.editor_session_types import SessionChangeEvent
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.graph_view_node_proxy import GraphViewNodeProxy
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.type import is_type
from lks_utils.knowledge.operations.delete_safety_analyzer import analyze_delete_impact
from lks_utils.knowledge.data_interface.link_mutation_bridge import LinkMutationBridge
from lks_utils.knowledge.ui.graph_link_creation_state_machine import (
    GraphLinkCreationEvent,
    GraphLinkCreationState,
    transition_graph_link_creation_state,
)
from lks_utils.knowledge.ui.components.graph_layout_ribbon_component import QGraphLayoutRibbonComponent
from lks_utils.knowledge.ui.components.ref_aware_delete_dialog import QKnowledgeRefAwareDeleteDialog
from lks_utils.knowledge.ui.graph_layout_ops import layout_positions
from lks_utils.graph2d_layout.algorithms.networkx_spread_node_layout_algorithm2d import (
    NetworkXSpreadNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D
from lks_utils.knowledge.ui.widgets.graph_canvas import (
    BatchPlacementPayload,
    estimate_graph_node_size_for_proxy,
)
from lks_utils.knowledge.ui.widgets.graph_node_canvas_item import QKnowledgeGraphNodeCanvasItem
from lks_utils.profiling import profile_action
from lks_utils.gui_qt.base.async_task_runner import WorkerThread

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


def _build_layout(self) -> None:
    self._left_splitter = QSplitter(Qt.Orientation.Vertical, self)
    self._left_splitter.setObjectName("kb_left_splitter")
    self._left_splitter.addWidget(self._library)
    self._left_splitter.addWidget(self._palette_tabs)
    self._left_splitter.addWidget(self._link_type_palette)
    self._left_splitter.addWidget(self._validation_log)
    self._left_splitter.setStretchFactor(0, 3)
    self._left_splitter.setStretchFactor(1, 1)
    self._left_splitter.setStretchFactor(2, 1)
    self._left_splitter.setStretchFactor(3, 1)
    self._left_splitter.setSizes([260, 150, 150, 120])
    self._left_splitter.setHandleWidth(8)
    self._left_splitter.setMinimumWidth(180)

    ribbon = self._build_ribbon()
    self._layout_ribbon = QGraphLayoutRibbonComponent(
        on_apply_layout=self._on_apply_layout_selected,
        on_apply_traversal=self._on_apply_traversal_selected,
        on_set_traversal_direction=self._on_set_traversal_direction,
        parent=self,
    )
    self._layout_ribbon.setObjectName("graph_layout_ribbon")
    self._layout_ribbon.set_selection_count(0)
    center_panel = QWidget(self)
    center_panel.setObjectName("kb_center_panel")
    center_layout = QVBoxLayout(center_panel)
    center_layout.setContentsMargins(0, 0, 0, 0)
    center_layout.setSpacing(0)
    center_layout.addWidget(ribbon)
    center_layout.addWidget(self._layout_ribbon)
    center_layout.addWidget(self._canvas, stretch=1)

    self._properties.setObjectName("kb_inspector_panel")
    self._properties.setSizePolicy(
        QSizePolicy.Policy.Ignored,
        QSizePolicy.Policy.Preferred,
    )
    self._connections_panel.setObjectName("kb_connections_panel")
    self._connections_panel.setSizePolicy(
        QSizePolicy.Policy.Ignored,
        QSizePolicy.Policy.Preferred,
    )
    self._right_splitter = QSplitter(Qt.Orientation.Vertical, self)
    self._right_splitter.setObjectName("kb_right_splitter")
    self._right_splitter.setSizePolicy(
        QSizePolicy.Policy.Ignored,
        QSizePolicy.Policy.Preferred,
    )
    self._right_splitter.addWidget(self._properties)
    self._right_splitter.addWidget(self._connections_panel)
    self._right_splitter.setHandleWidth(8)
    self._right_splitter.setStretchFactor(0, 2)
    self._right_splitter.setStretchFactor(1, 1)
    self._right_splitter.setSizes([520, 260])

    self._splitter = QSplitter(self)
    self._splitter.setObjectName("kb_outer_splitter")
    self._splitter.addWidget(self._left_splitter)
    self._splitter.addWidget(center_panel)
    self._splitter.addWidget(self._right_splitter)
    self._splitter.setHandleWidth(8)
    self._splitter.setStretchFactor(0, 0)
    self._splitter.setStretchFactor(1, 1)
    self._splitter.setStretchFactor(2, 0)
    self._splitter.setSizes([280, 760, 420])

    root = QVBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.addWidget(self._splitter, stretch=1)


def _wire_signals(self) -> None:
    self._session.add_change_listener(self._on_session_change)
    self._repo_watcher.directoryChanged.connect(self._on_repo_fs_changed)
    self._repo_watcher.fileChanged.connect(self._on_repo_fs_changed)
    self._configure_repo_watcher()
    self._revert_btn.clicked.connect(self._on_revert)
    self._library.new_item_requested.connect(
        self._on_new_graph_view_requested)
    self._library.node_load_requested.connect(self.load_graph_view_by_id)
    self._library.node_renamed.connect(self._on_graph_view_renamed)
    self._library.node_deleted.connect(self._on_graph_view_deleted)
    self._validation_log.focus_node_requested.connect(
        self._on_validation_focus_requested)


def _on_canvas_view_changed(self, _view: object) -> None:
    self._queue_canvas_viewport_sidecar_write()


def _queue_canvas_viewport_sidecar_write(self) -> None:
    if self._current_graph_view_id is None:
        return
    timer = getattr(self, "_viewport_sidecar_write_timer", None)
    if timer is None:
        return
    timer.start()


def _flush_canvas_viewport_sidecar_write(self) -> None:
    if self._current_graph_view_id is None:
        return
    if self._external_reload_in_progress:
        return
    repo_root = self._session.repository_root
    if repo_root is None:
        return
    view_path = CanvasIO.graph_view_relpath(self._session._io, self._current_graph_view_id)  # noqa: SLF001
    if view_path is None:
        return
    canvas_io = CanvasIO(view_path=view_path, knowledge_io=self._session._io)  # noqa: SLF001

    view = self._canvas.view()
    viewport_width = max(1.0, float(self._canvas.width()))
    viewport_height = max(1.0, float(self._canvas.height()))
    viewport = (viewport_width, viewport_height)
    corners = (
        view.screen_to_world((0.0, 0.0), viewport),
        view.screen_to_world((viewport_width, 0.0), viewport),
        view.screen_to_world((viewport_width, viewport_height), viewport),
        view.screen_to_world((0.0, viewport_height), viewport),
    )
    xs = [float(x) for x, _ in corners]
    ys = [float(y) for _, y in corners]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    visible_node_ids = sorted(
        local_id
        for local_id, item in self._canvas._local_node_items.items()  # noqa: SLF001
        if not (
            item.bounds().x1 < min_x
            or item.bounds().x0 > max_x
            or item.bounds().y1 < min_y
            or item.bounds().y0 > max_y
        )
    )
    node_world_sizes = {
        local_id: {
            "width": float(item.bounds().width),
            "height": float(item.bounds().height),
        }
        for local_id, item in self._canvas._local_node_items.items()  # noqa: SLF001
    }
    selected_local_ids = sorted(self._selected_graph_node_local_ids())

    with self._own_repo_write_scope():
        canvas_io.update_viewport_sidecar(
            center_x=float(view.center_world[0]),
            center_y=float(view.center_world[1]),
            zoom=float(view.zoom),
            visible_node_ids=visible_node_ids,
            selected_node_ids=selected_local_ids,
            gesture_complete=True,
            rotation_radians=float(view.rotation_radians),
            viewport_world_region={
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
            },
            viewport_resolution={
                "width_px": viewport_width,
                "height_px": viewport_height,
                "device_pixel_ratio": float(self._canvas.devicePixelRatioF()),
            },
            node_world_sizes=node_world_sizes,
        )


def _apply_styles(self) -> None:
    self.setStyleSheet(
        f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
        f"QWidget#canvas_ribbon {{ background: #1e1e1e; border-bottom: 1px solid {EDGE_COLOR}; }}"
        f"QLabel#canvas_title {{ color: {NODE_TEXT_COLOR}; font-weight: 600; }}"
        "QSplitter#kb_outer_splitter::handle:horizontal {"
        " background: #2c2c2c;"
        " border-left: 1px solid #5b5b5b;"
        " border-right: 1px solid #171717;"
        "}"
        "QSplitter#kb_outer_splitter::handle:horizontal:hover {"
        " background: #3a3a3a;"
        " border-left: 1px solid #7b7b7b;"
        "}"
        "QSplitter#kb_left_splitter::handle:vertical {"
        " background: #2c2c2c;"
        " border-top: 1px solid #5b5b5b;"
        " border-bottom: 1px solid #171717;"
        "}"
        "QSplitter#kb_left_splitter::handle:vertical:hover {"
        " background: #3a3a3a;"
        " border-top: 1px solid #7b7b7b;"
        "}"
        "QSplitter#kb_right_splitter::handle:vertical {"
        " background: #2c2c2c;"
        " border-top: 1px solid #5b5b5b;"
        " border-bottom: 1px solid #171717;"
        "}"
        "QSplitter#kb_right_splitter::handle:vertical:hover {"
        " background: #3a3a3a;"
        " border-top: 1px solid #7b7b7b;"
        "}"
        "QSplitter#kb_left_splitter { border: 1px solid #4a4a4a; }"
        "QSplitter#kb_right_splitter { border: 1px solid #4a4a4a; }"
        "QWidget#kb_center_panel { border: 1px solid #4a4a4a; }"
        "QWidget#kb_inspector_panel { border: 1px solid #4a4a4a; }"
        "QWidget#kb_connections_panel { border: 1px solid #4a4a4a; }"
    )


def _on_revert(self) -> None:
    graph_id = self._current_graph_view_id
    if graph_id is None:
        return
    try:
        root = self._session.repository_root
        if root is not None:
            rel_path_path = CanvasIO.graph_view_relpath(self._session._io, graph_id)  # noqa: SLF001
            rel_path = None
            if rel_path_path is not None:
                rel_path = rel_path_path.relative_to(root.resolve()).as_posix()
            if rel_path is None:
                rel_path = f"views/{graph_id}.json"
            git_result = self._confirm_and_revert_file_to_last_commit(
                core_label="graph view",
                rel_path=rel_path,
            )
            if git_result is False:
                return
        if self._session.repository_root is not None:
            self._session.load()
        self.load_graph_view_by_id(graph_id)
    except KeyError:
        self.set_graph_view(None)
    except Exception as exc:  # noqa: BLE001
        QMessageBox.warning(self, "Revert Failed", str(exc))
    self.refresh_palettes()


def _on_dirty_changed(self, _is_dirty: bool) -> None:
    if self._current_graph_view is not None:
        self._refresh_canvas_title(self._current_graph_view)


def _on_session_change(self, event: SessionChangeEvent | str) -> None:
    change_type = event if isinstance(event, str) else event.change_type
    with profile_action(
        "knowledge.graph_tab.session_change",
        phase="apply",
        metadata={"change_type": change_type},
    ) as action_scope:
        if change_type == "repo_saved":
            self._mark_own_fs_write()
            self._configure_repo_watcher(refresh_snapshot=True)
            self._pending_external_paths.clear()
            self._external_reload_pending_path = None
            self._external_reload_requested_again = False
            self._external_reload_timer.stop()
            action_scope.add_metadata("handled", "repo_saved")
            return
        if change_type == "repo_loaded":
            self._configure_repo_watcher()
        if change_type in {"repo_loaded", "graph_view"}:
            self._library.refresh()
            self.refresh_palettes()
        if change_type == "node":
            # Coalesce side-panel refreshes for node edits to avoid synchronous
            # splitter/layout pressure while Enter commits are still settling.
            if getattr(self, "_skip_next_node_side_panel_refresh", False):
                self._skip_next_node_side_panel_refresh = False
            elif not _node_change_affects_graph_side_panels(self):
                pass
            else:
                self._schedule_node_side_panel_refresh_when_idle()
        if change_type == "node" and self._current_graph_view is not None:
            targeted_refresh_ids = self._pending_targeted_node_refresh_ids
            self._pending_targeted_node_refresh_ids = None
            if not targeted_refresh_ids:
                session_touched_ids = getattr(
                    self._session,
                    "current_change_touched_ids",
                    None,
                )
                if session_touched_ids:
                    loaded_node_ids = {
                        proxy.global_id
                        for proxy in self._current_graph_view.nodes.values()
                    }
                    targeted_refresh_ids = loaded_node_ids.intersection(
                        session_touched_ids
                    )
            if targeted_refresh_ids:
                nodes_by_id = {
                    str(node.id): node for node in self._session.list_nodes()
                }
                self._canvas.refresh_loaded_nodes_fast(
                    nodes_by_id=nodes_by_id,
                    links_by_id=self._collect_links_by_id(),
                    only_global_ids=targeted_refresh_ids,
                )
            else:
                loaded_node_ids = {
                    proxy.global_id
                    for proxy in self._current_graph_view.nodes.values()
                }
                if loaded_node_ids:
                    nodes_by_id = {
                        str(node.id): node for node in self._session.list_nodes()
                    }
                    self._canvas.refresh_loaded_nodes_fast(
                        nodes_by_id=nodes_by_id,
                        links_by_id=self._collect_links_by_id(),
                        only_global_ids=loaded_node_ids,
                    )
                else:
                    self._schedule_full_node_canvas_refresh_when_idle()
            action_scope.add_metadata(
                "targeted_refresh_count",
                len(targeted_refresh_ids or set()),
            )
        if change_type in {"node", "repo_loaded", "graph_view", "dirty_changed"} and self._current_graph_view is not None:
            self._refresh_canvas_title(self._current_graph_view)


def _schedule_node_side_panel_refresh_when_idle(self) -> None:
    if getattr(self, "_node_side_panel_refresh_pending", False):
        return
    self._node_side_panel_refresh_pending = True

    def _attempt_refresh(*, remaining: int = 8) -> None:
        if self._is_inspector_editing() and remaining > 0:
            QTimer.singleShot(
                80,
                lambda remaining=remaining - 1: _attempt_refresh(
                    remaining=remaining,
                ),
            )
            return
        self._node_side_panel_refresh_pending = False
        with profile_action(
            "knowledge.graph_tab.side_panels",
            phase="coalesced_refresh",
            metadata={"remaining_attempts": remaining},
        ):
            try:
                self.refresh_palettes()
                if self._current_graph_view is not None:
                    self._refresh_canvas_title(self._current_graph_view)
            except RuntimeError:
                return

    QTimer.singleShot(80, _attempt_refresh)


def _node_change_affects_graph_side_panels(self) -> bool:
    touched_ids = self._session.current_change_touched_ids
    if touched_ids is None:
        return True
    if not touched_ids:
        return False
    loaded_node_ids: set[str] = set()
    if self._current_graph_view is not None:
        loaded_node_ids = {
            proxy.global_id for proxy in self._current_graph_view.nodes.values()
        }
    for object_id in touched_ids:
        try:
            node = self._session.get_node(object_id)
        except KeyError:
            # Deleted nodes can still impact palette composition.
            return True
        if is_type(node):
            return True
        if object_id not in loaded_node_ids:
            return True
    return False


def _schedule_full_node_canvas_refresh_when_idle(self) -> None:
    if getattr(self, "_full_node_canvas_refresh_pending", False):
        return
    self._full_node_canvas_refresh_pending = True

    def _attempt_refresh(*, remaining: int = 8) -> None:
        if self._is_inspector_editing() and remaining > 0:
            QTimer.singleShot(
                80,
                lambda remaining=remaining - 1: _attempt_refresh(
                    remaining=remaining,
                ),
            )
            return
        self._full_node_canvas_refresh_pending = False
        if self._current_graph_view is None:
            return
        with profile_action(
            "knowledge.graph_tab.node_refresh",
            phase="deferred_full_refresh",
            metadata={"remaining_attempts": remaining},
        ):
            try:
                nodes_by_id = {
                    str(node.id): node for node in self._session.list_nodes()
                }
                self._canvas.refresh_loaded_nodes_fast(
                    nodes_by_id=nodes_by_id,
                    links_by_id=self._collect_links_by_id(),
                    only_global_ids=None,
                )
            except RuntimeError:
                return

    QTimer.singleShot(80, _attempt_refresh)


def _on_inspector_mutation_applied(self, payload: object) -> None:
    if not isinstance(payload, dict):
        return
    dirty_reason = payload.get("dirty_reason")
    if isinstance(dirty_reason, str):
        reason = dirty_reason.strip().casefold()
        # Plain property/field value edits do not change side-panel composition.
        if (
            reason.startswith("inspector property updated:")
            or reason.startswith("inspector field updated:")
            or reason.startswith("inspector nested property updated:")
            or reason.startswith("inspector flexible property updated:")
        ):
            self._skip_next_node_side_panel_refresh = True
    raw_touched_ids = payload.get("touched_ids")
    if not isinstance(raw_touched_ids, (set, frozenset, list, tuple)):
        return
    touched_ids = {
        str(object_id)
        for object_id in raw_touched_ids
        if isinstance(object_id, str)
    }
    if not touched_ids:
        return
    if self._current_graph_view is None:
        self._pending_targeted_node_refresh_ids = touched_ids
        return
    loaded_node_ids = {
        proxy.global_id for proxy in self._current_graph_view.nodes.values()
    }
    targeted = loaded_node_ids.intersection(touched_ids)
    self._pending_targeted_node_refresh_ids = targeted or touched_ids


def _configure_repo_watcher(self, *, refresh_snapshot: bool = True) -> None:
    repo_root = self._session.repository_root
    if repo_root is None:
        return
    resolved = repo_root.resolve()
    root_changed = self._watched_repo_root != resolved
    desired_paths = self._discover_watch_directories(resolved)
    paths_changed = desired_paths != self._watched_repo_paths
    for old_path in list(self._watched_repo_paths):
        if old_path not in desired_paths:
            self._repo_watcher.removePath(str(old_path))
            self._watched_repo_paths.discard(old_path)
    for new_path in desired_paths:
        if new_path not in self._watched_repo_paths:
            self._repo_watcher.addPath(str(new_path))
            self._watched_repo_paths.add(new_path)
    self._watched_repo_root = resolved
    if root_changed:
        self._external_event_journal_offset = 0
        try:
            self._seed_external_event_journal_offset(resolved)
        except OSError:
            self._external_event_journal_offset = 0
    if refresh_snapshot and (paths_changed or not self._known_repo_file_state):
        self._refresh_known_repo_file_state()


def _on_repo_fs_changed(self, changed_path: str) -> None:
    if self._is_own_repo_write_active():
        return
    self._configure_repo_watcher(refresh_snapshot=False)
    self._pending_external_paths.add(changed_path)
    self._external_reload_pending_path = changed_path
    self.external_repo_change_detected.emit(changed_path)
    self._publish_workbench_ui_event(
        event_type="graph_tab.external_repo_change_detected",
        payload={
            "path": changed_path,
            "graph_view_id": self._current_graph_view_id,
        },
    )
    self._request_external_reload(immediate=False)


def _load_live_reload_settings(self) -> None:
    settings = QSettings(self._SETTINGS_ORG, self._SETTINGS_APP)
    settings.beginGroup("workbench/graph_tab")
    self._external_reload_enabled = self._coerce_bool(
        settings.value("live_reload_enabled",
                       _DEFAULT_LIVE_RELOAD_ENABLED),
        default=_DEFAULT_LIVE_RELOAD_ENABLED,
    )
    self._external_reload_on_focus = self._coerce_bool(
        settings.value("live_reload_on_focus",
                       _DEFAULT_LIVE_RELOAD_ON_FOCUS),
        default=_DEFAULT_LIVE_RELOAD_ON_FOCUS,
    )
    self._external_reload_debounce_ms = self._coerce_int(
        settings.value("live_reload_debounce_ms",
                       _DEFAULT_LIVE_RELOAD_DEBOUNCE_MS),
        default=_DEFAULT_LIVE_RELOAD_DEBOUNCE_MS,
        minimum=0,
    )
    self._external_reload_poll_ms = self._coerce_int(
        settings.value("live_reload_poll_ms",
                       _DEFAULT_LIVE_RELOAD_POLL_MS),
        default=_DEFAULT_LIVE_RELOAD_POLL_MS,
        minimum=250,
    )
    self._external_reload_min_gap_ms = self._coerce_int(
        settings.value("live_reload_min_gap_ms",
                       _DEFAULT_LIVE_RELOAD_MIN_GAP_MS),
        default=_DEFAULT_LIVE_RELOAD_MIN_GAP_MS,
        minimum=0,
    )
    serialized_view_state = settings.value("link_type_view_state_json", "")
    try:
        if isinstance(serialized_view_state, str) and serialized_view_state.strip():
            parsed_view_state = json.loads(serialized_view_state)
            if isinstance(parsed_view_state, dict):
                self._link_type_view_state = LinkTypeViewState.deserialize(
                    parsed_view_state
                )
    except (TypeError, ValueError, json.JSONDecodeError):
        self._link_type_view_state = LinkTypeViewState()
    settings.endGroup()
    self._external_reload_timer.setInterval(
        self._external_reload_debounce_ms)
    self._external_reload_poll_timer.setInterval(
        self._external_reload_poll_ms)
    if self._external_reload_enabled:
        self._external_reload_poll_timer.start()
    else:
        self._external_reload_poll_timer.stop()
        self._external_reload_timer.stop()


def _save_link_type_view_state_settings(self) -> None:
    settings = QSettings(self._SETTINGS_ORG, self._SETTINGS_APP)
    settings.beginGroup("workbench/graph_tab")
    serialized = json.dumps(
        self._link_type_view_state.serialize(),
        sort_keys=True,
        separators=(",", ":"),
    )
    settings.setValue("link_type_view_state_json", serialized)
    settings.endGroup()


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_int(value: object, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _install_window_activation_filter(self) -> None:
    window = self.window()
    if window is self._window_activation_source or window is None:
        return
    self._remove_window_activation_filter()
    window.installEventFilter(self)
    self._window_activation_source = window


def _remove_window_activation_filter(self) -> None:
    if self._window_activation_source is None:
        return
    self._window_activation_source.removeEventFilter(self)
    self._window_activation_source = None


def _request_external_reload(self, *, immediate: bool) -> None:
    if not self._external_reload_enabled or not self._pending_external_paths:
        return
    if self._external_reload_in_progress:
        self._external_reload_requested_again = True
        return
    delay_ms = 0 if immediate else self._external_reload_debounce_ms
    elapsed_ms = int(
        (time.monotonic() - self._last_external_reload_finished_at) * 1000.0)
    remaining_gap_ms = max(
        0, self._external_reload_min_gap_ms - elapsed_ms)
    start_ms = max(delay_ms, 0 if immediate else remaining_gap_ms)
    self._external_reload_timer.start(start_ms)


def _on_external_reload_poll_tick(self) -> None:
    self._request_external_reload(immediate=False)


def _flush_external_reload_queue(self) -> None:
    if not self._pending_external_paths:
        return
    if self._is_canvas_interacting() or self._is_inspector_editing():
        self._external_reload_timer.start(
            max(125, self._external_reload_debounce_ms))
        return
    self._start_external_reload_scan()


def _start_external_reload_scan(self) -> None:
    if self._external_reload_scan_worker is not None and self._external_reload_scan_worker.isRunning():
        return
    invalidated_paths = tuple(self._pending_external_paths)
    if not invalidated_paths:
        return
    self._pending_external_paths.clear()
    worker = WorkerThread(
        self._scan_external_reload_task,
        args=(invalidated_paths, dict(self._known_repo_file_state),
              self._known_repo_file_state_revision),
    )
    worker.finished.connect(self._on_external_reload_scan_finished)
    worker.error.connect(self._on_external_reload_scan_error)
    self._external_reload_scan_worker = worker
    worker.start()


def _scan_external_reload_task(
    invalidated_paths: tuple[str, ...],
    known_state: dict[str, tuple[int, int]],
    revision: int,
) -> _ExternalReloadScanResult:
    invalidated_roots: list[Path] = []
    for raw_path in invalidated_paths:
        try:
            invalidated_roots.append(Path(raw_path).resolve())
        except OSError:
            continue
    scanned_paths: set[Path] = set(invalidated_roots)
    new_state = _scan_repo_files(scanned_paths)
    old_keys_under_roots = {
        key
        for key in known_state
        if any(_path_is_within(Path(key), root) for root in scanned_paths)
    }
    changed_files: set[str] = set()
    for key in old_keys_under_roots | set(new_state):
        if known_state.get(key) != new_state.get(key):
            changed_files.add(key)
    return _ExternalReloadScanResult(
        revision=revision,
        scanned_roots=tuple(str(path) for path in scanned_paths),
        changed_files=changed_files,
        new_state=new_state,
    )


def _on_external_reload_scan_finished(self, result: object) -> None:
    self._external_reload_scan_worker = None
    if not isinstance(result, _ExternalReloadScanResult):
        return
    if result.revision != self._known_repo_file_state_revision:
        if self._pending_external_paths:
            self._request_external_reload(immediate=False)
        return
    scanned_roots = [Path(path) for path in result.scanned_roots]
    old_keys_under_roots = {
        key
        for key in self._known_repo_file_state
        if any(self._path_is_within(Path(key), root) for root in scanned_roots)
    }
    for key in old_keys_under_roots:
        self._known_repo_file_state.pop(key, None)
    self._known_repo_file_state.update(result.new_state)
    self._external_reload_pending_path = None
    if result.changed_files:
        self._run_external_repo_reload_with_changed_files(
            result.changed_files)
    if self._pending_external_paths:
        self._request_external_reload(immediate=False)


def _on_external_reload_scan_error(self, exc: Exception) -> None:
    self._external_reload_scan_worker = None
    logging.getLogger(__name__).warning(
        "External reload scan failed: %s", exc)
    if self._pending_external_paths:
        self._request_external_reload(immediate=False)


def _is_canvas_interacting(self) -> bool:
    dragging_items = bool(getattr(self._canvas, "_dragging_items", []))
    rubber_band_active = getattr(
        self._canvas, "_rubber_band_overlay", None) is not None
    multi_drag_active = getattr(
        self._canvas, "_active_multi_drag_payload", None) is not None
    link_target_mode = bool(
        getattr(self._canvas, "_link_creation_target_mode", False))
    return dragging_items or rubber_band_active or multi_drag_active or link_target_mode


def _is_inspector_editing(self) -> bool:
    focus_widget = QApplication.focusWidget()
    if focus_widget is None or not self._properties.isAncestorOf(focus_widget):
        return False
    return (
        isinstance(focus_widget, (QLineEdit, QComboBox, QPlainTextEdit))
        or focus_widget.inherits("QAbstractSpinBox")
    )


def _is_own_repo_write_active(self) -> bool:
    return self._own_repo_write_depth > 0 or time.monotonic() < self._suppress_external_reload_until


def _mark_own_fs_write(self) -> None:
    """Suppress watcher-driven reloads for the current burst of self-writes."""
    self._suppress_external_reload_until = max(
        self._suppress_external_reload_until,
        time.monotonic() + _OWN_FS_WRITE_SUPPRESSION_SECONDS,
    )


@contextmanager
def _own_repo_write_scope(self):
    """Mark a graph-tab initiated persistence burst as internal-only for live reload."""
    self._own_repo_write_depth += 1
    self._mark_own_fs_write()
    try:
        yield
    finally:
        self._own_repo_write_depth = max(0, self._own_repo_write_depth - 1)
        self._mark_own_fs_write()


def _apply_graph_repo_mutation(
    self,
    label: str,
    fn,
    *,
    validation_mode: Literal["expanded", "touched_only"] = "expanded",
):
    """Run a graph-originated repo mutation while suppressing self-reload bursts."""
    with self._own_repo_write_scope():
        return self._session.apply_mutation(
            label,
            fn,
            validation_mode=validation_mode,
        )


def _discover_watch_directories(repo_root: Path) -> set[Path]:
    # Watch only the known KB subdirectories rather than rglob-walking the
    # entire tree (which can be extremely slow for large repos on Windows).
    known_subdirs = ["nodes", "link_types",
                     "links", "graph_views", "views"]
    paths: set[Path] = {repo_root}
    for name in known_subdirs:
        candidate = repo_root / name
        if candidate.is_dir():
            paths.add(candidate.resolve())
    return paths


def _refresh_known_repo_file_state(self) -> None:
    self._known_repo_file_state = self._scan_repo_files(
        self._watched_repo_paths)
    self._known_repo_file_state_revision += 1


def _scan_repo_files(paths: Iterable[Path]) -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for path in paths:
        if path.is_file():
            try:
                stat = path.stat()
            except OSError:
                continue
            state[str(path.resolve())] = (
                int(stat.st_mtime_ns), int(stat.st_size))
            continue
        if not path.is_dir():
            continue
        for pattern in ("*.json", "*.jsonl"):
            for candidate in path.rglob(pattern):
                try:
                    stat = candidate.stat()
                except OSError:
                    continue
                state[str(candidate.resolve())] = (
                    int(stat.st_mtime_ns), int(stat.st_size))
    return state


def _collect_changed_files(self, invalidated_paths: Iterable[str]) -> set[str]:
    invalidated_roots: list[Path] = []
    for raw_path in invalidated_paths:
        try:
            invalidated_roots.append(Path(raw_path).resolve())
        except OSError:
            continue
    if not invalidated_roots:
        return set()

    scanned_paths: set[Path] = set()
    for root in invalidated_roots:
        if root.is_dir():
            scanned_paths.add(root)
            continue
        scanned_paths.add(root)

    new_state = self._scan_repo_files(scanned_paths)
    changed_files: set[str] = set()
    old_keys_under_roots = {
        key
        for key in self._known_repo_file_state
        if any(self._path_is_within(Path(key), root) for root in scanned_paths)
    }
    new_keys = set(new_state)
    for key in old_keys_under_roots | new_keys:
        if self._known_repo_file_state.get(key) != new_state.get(key):
            changed_files.add(key)
    for key in old_keys_under_roots:
        self._known_repo_file_state.pop(key, None)
    self._known_repo_file_state.update(new_state)
    return changed_files


def _path_is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return candidate == root


def _graph_view_storage_dirs(self, repo_root: Path) -> tuple[Path, ...]:
    return tuple(
        candidate.resolve()
        for candidate in (repo_root / "views", repo_root / "graph_views")
        if candidate.exists()
    )


def _changed_files_are_graph_view_only(self, changed_files: set[str], repo_root: Path) -> bool:
    if not changed_files:
        return False
    graph_dirs = self._graph_view_storage_dirs(repo_root)
    if not graph_dirs:
        return False
    return all(
        any(self._path_is_within(Path(path), graph_dir)
            for graph_dir in graph_dirs)
        for path in changed_files
    )


def _changed_files_are_viewport_sidecar_only(changed_files: set[str]) -> bool:
    if not changed_files:
        return False
    return all(Path(path).name.endswith("_viewport.json") for path in changed_files)


def _run_external_graph_view_reload(self) -> None:
    if self._current_graph_view_id is None:
        return
    repo_root = self._session.repository_root
    if repo_root is None:
        return
    with profile_action(
        "knowledge.graph_tab.reload",
        phase="graph_view_only",
        metadata={"graph_view_id": self._current_graph_view_id},
    ) as action_scope:
        selected_local_ids = list(self._selected_graph_node_local_ids())
        previous_view = self._current_graph_view
        reloaded_view = CanvasIO.load_graph_view_from_repo_root(
            repo_root,
            self._current_graph_view_id,
        )
        if previous_view is not None:
            reloaded_view = self._merge_preserved_positions(
                previous_view, reloaded_view)
        self._library.refresh()
        nodes_by_id = {
            str(node.id): node for node in self._session.list_nodes()}
        self.set_graph_view(
            reloaded_view, nodes_by_id=nodes_by_id, preserve_view=True)
        if selected_local_ids and hasattr(self, "_select_canvas_nodes_by_local_ids"):
            self._select_canvas_nodes_by_local_ids(selected_local_ids)
        action_scope.add_metadata(
            "selected_local_ids", len(selected_local_ids))


def _run_external_repo_reload(self) -> None:
    if not self._pending_external_paths:
        return
    if self._current_graph_view_id is None:
        return
    repo_root = self._session.repository_root
    if repo_root is None:
        return
    if self._external_reload_in_progress:
        self._external_reload_requested_again = True
        return
    if self._is_own_repo_write_active():
        self._request_external_reload(immediate=False)
        return
    if self._is_canvas_interacting() or self._is_inspector_editing():
        self._request_external_reload(immediate=False)
        return
    self._start_external_reload_scan()


def _run_external_repo_reload_with_changed_files(self, changed_files: set[str]) -> None:
    if self._current_graph_view_id is None:
        return
    repo_root = self._session.repository_root
    if repo_root is None:
        return
    self._external_reload_in_progress = True
    self._external_reload_requested_again = False
    with profile_action(
        "knowledge.graph_tab.reload",
        phase="external_repo",
        metadata={
            "graph_view_id": self._current_graph_view_id,
            "changed_files": len(changed_files),
        },
    ) as action_scope:
        try:
            if not changed_files:
                action_scope.add_metadata("mode", "empty")
                return
            if self._try_apply_intent_reload_from_journal(changed_files):
                action_scope.add_metadata("mode", "journal_intent")
                return
            if self._changed_files_are_viewport_sidecar_only(changed_files):
                action_scope.add_metadata("mode", "viewport_only")
                return
            if self._changed_files_are_graph_view_only(changed_files, repo_root):
                action_scope.add_metadata("mode", "graph_view_only")
                self._run_external_graph_view_reload()
                return
            selected_local_ids = list(self._selected_graph_node_local_ids())
            previous_view = self._current_graph_view
            self._session.load()
            try:
                reloaded_view = CanvasIO.load_graph_view(self._session._io, self._current_graph_view_id)  # noqa: SLF001
            except KeyError:
                action_scope.add_metadata("mode", "graph_missing")
                return
            if previous_view is not None:
                reloaded_view = self._merge_preserved_positions(
                    previous_view, reloaded_view)
            nodes_by_id = {
                str(node.id): node for node in self._session.list_nodes()}
            self.set_graph_view(
                reloaded_view, nodes_by_id=nodes_by_id, preserve_view=True)
            if selected_local_ids and hasattr(self, "_select_canvas_nodes_by_local_ids"):
                self._select_canvas_nodes_by_local_ids(selected_local_ids)
            action_scope.add_metadata("mode", "full_repo")
            action_scope.add_metadata(
                "selected_local_ids", len(selected_local_ids))
            self._publish_workbench_ui_event(
                event_type="graph_tab.external_repo_reload_applied",
                payload={
                    "changed_files": sorted(changed_files),
                    "graph_view_id": self._current_graph_view_id,
                },
            )
        finally:
            self._external_reload_in_progress = False
            self._last_external_reload_finished_at = time.monotonic()
            if self._external_reload_requested_again and self._pending_external_paths:
                self._request_external_reload(immediate=False)


def _publish_workbench_ui_event(
    self,
    *,
    event_type: str,
    payload: dict[str, object],
) -> None:
    bus = getattr(self, "_ui_event_bus", None)
    if bus is None:
        return
    envelope = EventEnvelope(
        stream="knowledge.ui.workbench",
        event_type=event_type,
        payload=payload,
    )
    bus.publish(envelope)


def _seed_external_event_journal_offset(self, repo_root: Path) -> None:
    path = journal_file_path(repo_root)
    if not path.exists():
        self._external_event_journal_offset = 0
        return
    self._external_event_journal_offset = path.stat().st_size


def _journal_changed_in_files(changed_files: set[str], repo_root: Path) -> bool:
    journal = journal_file_path(repo_root).resolve()
    return str(journal) in changed_files


def _read_new_journal_events(self, repo_root: Path) -> list[dict[str, object]]:
    offset = int(getattr(self, "_external_event_journal_offset", 0))
    next_offset, events = read_change_events_since(repo_root, offset=offset)
    self._external_event_journal_offset = next_offset
    return events


def _try_apply_intent_reload_from_journal(self, changed_files: set[str]) -> bool:
    repo_root = self._session.repository_root
    if repo_root is None:
        return False
    if not self._journal_changed_in_files(changed_files, repo_root):
        return False

    events = self._read_new_journal_events(repo_root)
    if not events:
        return False

    external_events = [
        event
        for event in events
        if str(event.get("process_id", "")) != str(os.getpid())
    ]
    if not external_events:
        return False

    event_types = {
        str(event.get("event_type", ""))
        for event in external_events
    }
    # Fast-path intent handling: external node upserts only need a repository
    # refresh, after which existing node-change listeners rebuild card content.
    if event_types and event_types <= {"node_upserted"}:
        self._session.load()
        if self._current_graph_view is not None:
            refreshed_global_ids = {
                str(event.get("entity_id", ""))
                for event in external_events
                if str(event.get("entity_id", ""))
            }
            nodes_by_id = {
                str(node.id): node for node in self._session.list_nodes()}
            self._canvas.refresh_loaded_nodes_fast(
                nodes_by_id=nodes_by_id,
                links_by_id=self._collect_links_by_id(),
                only_global_ids=refreshed_global_ids or None,
            )
        return True
    return False


def _merge_preserved_positions(old_view: GraphView, new_view: GraphView) -> GraphView:
    preserved = {
        local_id: (proxy.x, proxy.y)
        for local_id, proxy in old_view.nodes.items()
    }
    merged_nodes: dict[str, GraphViewNodeProxy] = {}
    for local_id, proxy in new_view.nodes.items():
        if local_id in preserved:
            px, py = preserved[local_id]
            merged_nodes[local_id] = GraphViewNodeProxy(
                global_id=proxy.global_id,
                x=px,
                y=py,
                cached_name=proxy.cached_name,
            )
            continue
        merged_nodes[local_id] = proxy
    return dataclasses.replace(new_view, nodes=merged_nodes)


def _on_new_graph_view_requested(self) -> None:
    graph_name = "New Graph"
    try:
        graph_name = CanvasIO.ensure_unique_graph_view_name(  # noqa: SLF001
            self._session._io,
            graph_name
        )
    except ValueError:
        pass
    new_view = GraphView(
        id=str(ULID()), name=graph_name, nodes={}, edges={})
    with self._own_repo_write_scope():
        CanvasIO.save_graph_view(self._session._io, new_view)  # noqa: SLF001
    self._session.notify_repository_mutated("graph_view")
    self.set_graph_view(new_view, nodes_by_id={str(
        node.id): node for node in self._session.list_nodes()})


def _on_graph_view_renamed(self, view_id: str, _new_name: str) -> None:
    if self._current_graph_view_id == view_id:
        previous_positions: dict[str, tuple[float, float]] = {}
        if self._current_graph_view is not None:
            for local_id, proxy in self._current_graph_view.nodes.items():
                item = self._canvas._local_node_items.get(local_id)  # noqa: SLF001
                if item is not None:
                    b = item.bounds()
                    previous_positions[local_id] = (b.x0, b.y0)
                else:
                    previous_positions[local_id] = (proxy.x, proxy.y)
        self.load_graph_view_by_id(view_id)
        current = self._current_graph_view
        if current is None or not previous_positions:
            return
        updated_nodes = dict(current.nodes)
        changed = False
        for local_id, (prev_x, prev_y) in previous_positions.items():
            proxy = updated_nodes.get(local_id)
            if proxy is None:
                continue
            if proxy.x == prev_x and proxy.y == prev_y:
                continue
            updated_nodes[local_id] = GraphViewNodeProxy(
                global_id=proxy.global_id,
                x=prev_x,
                y=prev_y,
                cached_name=proxy.cached_name,
            )
            changed = True
        if not changed:
            return
        stabilized_view = dataclasses.replace(current, nodes=updated_nodes)
        self._current_graph_view = stabilized_view
        self._current_graph_view_id = str(stabilized_view.id)
        self._persist_graph_view(stabilized_view)
        self._refresh_canvas_nodes_from_repository(preserve_view=True)


def _on_graph_view_deleted(self, view_id: str) -> None:
    if self._current_graph_view_id == view_id:
        self.set_graph_view(None)


def install_drag_controller_helpers(cls) -> None:
    cls._build_layout = _build_layout
    cls._wire_signals = _wire_signals
    cls._on_canvas_view_changed = _on_canvas_view_changed
    cls._queue_canvas_viewport_sidecar_write = _queue_canvas_viewport_sidecar_write
    cls._flush_canvas_viewport_sidecar_write = _flush_canvas_viewport_sidecar_write
    cls._apply_styles = _apply_styles
    cls._on_revert = _on_revert
    cls._on_dirty_changed = _on_dirty_changed
    cls._on_session_change = _on_session_change
    cls._schedule_node_side_panel_refresh_when_idle = _schedule_node_side_panel_refresh_when_idle
    cls._schedule_full_node_canvas_refresh_when_idle = _schedule_full_node_canvas_refresh_when_idle
    cls._on_inspector_mutation_applied = _on_inspector_mutation_applied
    cls._configure_repo_watcher = _configure_repo_watcher
    cls._on_repo_fs_changed = _on_repo_fs_changed
    cls._load_live_reload_settings = _load_live_reload_settings
    cls._save_link_type_view_state_settings = _save_link_type_view_state_settings
    cls._coerce_bool = staticmethod(_coerce_bool)
    cls._coerce_int = staticmethod(_coerce_int)
    cls._install_window_activation_filter = _install_window_activation_filter
    cls._remove_window_activation_filter = _remove_window_activation_filter
    cls._request_external_reload = _request_external_reload
    cls._on_external_reload_poll_tick = _on_external_reload_poll_tick
    cls._flush_external_reload_queue = _flush_external_reload_queue
    cls._start_external_reload_scan = _start_external_reload_scan
    cls._scan_external_reload_task = staticmethod(_scan_external_reload_task)
    cls._on_external_reload_scan_finished = _on_external_reload_scan_finished
    cls._on_external_reload_scan_error = _on_external_reload_scan_error
    cls._is_canvas_interacting = _is_canvas_interacting
    cls._is_inspector_editing = _is_inspector_editing
    cls._is_own_repo_write_active = _is_own_repo_write_active
    cls._mark_own_fs_write = _mark_own_fs_write
    cls._own_repo_write_scope = _own_repo_write_scope
    cls._apply_graph_repo_mutation = _apply_graph_repo_mutation
    cls._discover_watch_directories = staticmethod(_discover_watch_directories)
    cls._refresh_known_repo_file_state = _refresh_known_repo_file_state
    cls._scan_repo_files = staticmethod(_scan_repo_files)
    cls._collect_changed_files = _collect_changed_files
    cls._path_is_within = staticmethod(_path_is_within)
    cls._graph_view_storage_dirs = _graph_view_storage_dirs
    cls._changed_files_are_graph_view_only = _changed_files_are_graph_view_only
    cls._changed_files_are_viewport_sidecar_only = staticmethod(
        _changed_files_are_viewport_sidecar_only)
    cls._run_external_graph_view_reload = _run_external_graph_view_reload
    cls._run_external_repo_reload = _run_external_repo_reload
    cls._run_external_repo_reload_with_changed_files = _run_external_repo_reload_with_changed_files
    cls._publish_workbench_ui_event = _publish_workbench_ui_event
    cls._seed_external_event_journal_offset = _seed_external_event_journal_offset
    cls._journal_changed_in_files = staticmethod(_journal_changed_in_files)
    cls._read_new_journal_events = _read_new_journal_events
    cls._try_apply_intent_reload_from_journal = _try_apply_intent_reload_from_journal
    cls._merge_preserved_positions = staticmethod(_merge_preserved_positions)
    cls._on_new_graph_view_requested = _on_new_graph_view_requested
    cls._on_graph_view_renamed = _on_graph_view_renamed
    cls._on_graph_view_deleted = _on_graph_view_deleted


__all__ = ["install_drag_controller_helpers"]

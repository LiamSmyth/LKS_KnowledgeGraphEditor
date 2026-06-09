"""Canvas2D-based graph canvas for GraphView rendering."""
from __future__ import annotations
import json
from dataclasses import dataclass, replace

from lks_utils.knowledge.ui.actions import (
    GRAPH_VIEW_DRAG_CANCEL,
    GRAPH_VIEW_SELECTION_CLEAR_CANVAS,
    KNOWLEDGE_REPO_DELETE_SELECTION,
)
from lks_utils.knowledge.display_color import effective_link_type_display_color
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.link_type_view_state import LinkTypeViewState
from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.ui.widgets.graph_link_canvas_object import (
    QKnowledgeGraphLinkCanvasObject,
)
from lks_utils.knowledge.ui.widgets.graph_node_canvas_object import (
    QKnowledgeGraphNodeCanvasObject,
)
from lks_utils.knowledge.ui.widgets.graph_node_factory import make_graph_node_object
from lks_utils.knowledge.ui.widgets._link_gestures import (
    LINK_TYPE_MIME,
    GraphLinkGestures,
    link_type_id_from_event,
)
from lks_utils.knowledge.ui.widgets._placement import (
    GRAPH_VIEW_FRAME_BUFFER_WORLD,
    BatchPlacementPayload,
    build_graph_render_model,
    estimate_graph_node_size_for_proxy,
)

from collections.abc import Mapping

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QContextMenuEvent, QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QKeyEvent, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QMenu

from lks_utils.input import GestureKind, Modifier
from lks_utils.input.qt_adapter import qt_button_to_logical, qt_modifiers_to_logical

from lks_utils.gui_qt.canvas2d.widgets.canvas_widget_policies import CanvasWidgetPolicies
from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.interaction.actions import CANVAS_PRIMARY
from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform
from lks_utils.input import get_default_bindings
from lks_utils.knowledge.ui.widgets.knowledge_edit_canvas import QKnowledgeEditCanvasWidget


@dataclass(frozen=True)
class MultiNodeDragPayload:
    """Captures state of a multi-node drag operation."""
    node_ids: tuple[str, ...]  # All selected node IDs being dragged
    anchor_node_id: str  # Primary node for cursor offset calculation
    cursor_offset_in_anchor: QPointF  # Cursor position relative to anchor
    start_positions: dict[str, QPointF]  # Original positions of all nodes


class QKnowledgeGraphCanvasWidget(QKnowledgeEditCanvasWidget):
    """GraphView renderer with drop support for instance proxy placement."""

    node_selected = Signal(str)           # global node id
    link_selected = Signal(str)           # global link id
    # (global_id, world_x, world_y)
    instance_dropped = Signal(str, float, float)
    # (BatchPlacementPayload)
    instances_dropped = Signal(object)
    # (type_id, world_x, world_y)
    type_dropped = Signal(str, float, float)
    clear_selection_requested = Signal()
    # (delete_knowledge_objects)
    delete_selection_requested = Signal(bool)
    link_source_drag_started = Signal(str)
    # (link_type_id, candidate_source_node_id|None)
    link_source_drag_hovered = Signal(str, object)
    # (link_type_id, source_node_id|None)
    link_source_drop_finished = Signal(str, object)
    # (candidate_target_node_id|None, world_x, world_y)
    link_target_hovered = Signal(object, float, float)
    # (candidate_target_node_id|None, world_x, world_y)
    link_target_clicked = Signal(object, float, float)
    link_creation_cancel_requested = Signal()
    # (selected_ids:set[str], active_id:str|None)
    selection_model_changed = Signal(object, object)
    pointer_gesture_finished = Signal()

    # Multi-node drag signal: emitted when drag completes with (payload, final_positions)
    multi_node_drag_completed = Signal(object, dict)

    _INSTANCE_MIME = "application/x-knowledge-instance-id"
    _INSTANCE_IDS_MIME = "application/x-knowledge-instance-ids"
    _TYPE_MIME = "application/x-knowledge-type-id"
    _LINK_TYPE_MIME = LINK_TYPE_MIME
    _GRAPH_LOAD_TWEEN_MS = 140

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            capabilities=CanvasWidgetPolicies(
                allow_selection=True,
                allow_multi_select=True,
                allow_range_select=True,
                allow_drag=True,
                allow_add_remove=True,
                allow_undo_redo=True,
                allow_clipboard=True,
                bring_selected_to_front=True,
            ),
        )
        self._graph_view: GraphView | None = None
        self._local_node_objects: dict[str, QKnowledgeGraphNodeCanvasObject] = {}
        self._edge_objects: dict[str, QKnowledgeGraphLinkCanvasObject] = {}
        self._incident_edge_ids: dict[str, tuple[str, ...]] = {}
        self._view_state: LinkTypeViewState | None = None
        self._is_loading_graph_view: bool = False
        self._last_active_node_id: str | None = None
        self._last_active_link_id: str | None = None
        self._link_creation_modal_active = False
        self._link_creation_target_mode = False
        self._preview_link_item: QKnowledgeGraphLinkCanvasObject | None = None
        self._active_multi_drag_payload: MultiNodeDragPayload | None = None
        self._selected_ids: set[str] = set()
        self._active_id: str | None = None
        self._link_gestures = GraphLinkGestures(self)
        self.setAcceptDrops(True)
        self.selection_changed.connect(self._sync_graph_selection_visuals)
        # Also sync when only the active item changes (e.g. shift-clicking an
        # already-selected node to promote it to active without changing the
        # selection set â€” selection_changed is not emitted in that case).
        self.active_selection_changed.connect(
            lambda _item: self._sync_graph_selection_visuals()
        )
        # Capability-hosted nodes select via SelectionModel directly (bypassing
        # Canvas2DWidget.select_object), so promote z-order on selection signals.
        self.selection_changed.connect(self._promote_active_selection_z_order)
        self.active_selection_changed.connect(self._promote_active_selection_z_order)

    # ------------------------------------------------------------------ #
    # Drag-and-drop                                                        #
    # ------------------------------------------------------------------ #

    def _instance_id_from_event(
        self,
        event: QDragEnterEvent | QDragMoveEvent | QDropEvent,
    ) -> str | None:
        raw = event.mimeData().data(self._INSTANCE_MIME)
        if raw:
            try:
                return bytes(raw).decode("utf-8")
            except Exception:
                return None
        return None

    def _instance_ids_from_event(
        self,
        event: QDragEnterEvent | QDragMoveEvent | QDropEvent,
    ) -> tuple[str, ...]:
        raw = event.mimeData().data(self._INSTANCE_IDS_MIME)
        if not raw:
            return ()
        try:
            decoded = bytes(raw).decode("utf-8")
            parsed = json.loads(decoded)
        except Exception:
            return ()
        if not isinstance(parsed, list):
            return ()
        instance_ids = [item for item in parsed if isinstance(item, str)]
        if not instance_ids:
            return ()
        return tuple(instance_ids)

    def _type_id_from_event(
        self,
        event: QDragEnterEvent | QDragMoveEvent | QDropEvent,
    ) -> str | None:
        raw = event.mimeData().data(self._TYPE_MIME)
        if raw:
            try:
                return bytes(raw).decode("utf-8")
            except Exception:
                return None
        return None

    def _link_type_id_from_event(
        self,
        event: QDragEnterEvent | QDragMoveEvent | QDropEvent,
    ) -> str | None:
        return link_type_id_from_event(event, mime=self._LINK_TYPE_MIME)

    def _candidate_source_node_id_from_screen(self, sx: float, sy: float) -> str | None:
        return self._link_gestures.candidate_source_node_id_from_screen(sx, sy)

    def set_link_creation_modal_active(self, active: bool) -> None:
        """Toggle whether RMB/Esc should cancel graph link creation modal state."""
        self._link_gestures.set_link_creation_modal_active(active)

    def set_link_creation_target_mode(self, active: bool) -> None:
        """Enable or disable target-pick hover streaming."""
        self._link_gestures.set_link_creation_target_mode(active)

    def set_link_preview(
        self,
        *,
        source_node_id: str | None,
        target_node_id: str | None,
        cursor_world: tuple[float, float] | None = None,
        color: str | None = None,
    ) -> None:
        """Render a transient preview edge for link creation."""
        self._link_gestures.set_link_preview(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            cursor_world=cursor_world,
            color=color,
        )

    def clear_link_preview(self) -> None:
        """Remove the transient link-creation preview edge, if present."""
        self._link_gestures.clear_link_preview()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._link_gestures.handle_drag_enter(event):
            return
        if (
            self._instance_id_from_event(event)
            or self._instance_ids_from_event(event)
            or self._type_id_from_event(event)
        ):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._link_gestures.handle_drag_move(event):
            return
        if (
            self._instance_id_from_event(event)
            or self._instance_ids_from_event(event)
            or self._type_id_from_event(event)
        ):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._link_gestures.handle_drag_leave(event)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self._link_gestures.handle_drop(event):
            return
        wx, wy = self._screen_to_world(
            float(event.position().x()), float(event.position().y())
        )
        instance_ids = self._instance_ids_from_event(event)
        if instance_ids:
            if len(instance_ids) == 1:
                self.instance_dropped.emit(instance_ids[0], wx, wy)
            else:
                self.instances_dropped.emit(
                    BatchPlacementPayload(
                        instance_ids=instance_ids,
                        drop_anchor=QPointF(wx, wy),
                    )
                )
            event.acceptProposedAction()
            return
        instance_id = self._instance_id_from_event(event)
        if instance_id:
            self.instance_dropped.emit(instance_id, wx, wy)
            event.acceptProposedAction()
            return
        type_id = self._type_id_from_event(event)
        if type_id:
            self.type_dropped.emit(type_id, wx, wy)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def load_graph_view(
        self,
        graph_view: GraphView,
        *,
        nodes_by_id: Mapping[str, Node] | None = None,
        links_by_id: Mapping[str, LinkInstance] | None = None,
        link_types_by_id: Mapping[str, LinkType] | None = None,
        preserve_view: bool = False,
    ) -> None:
        """Replace the current scene with content from *graph_view*."""
        prior_view = self.view() if preserve_view else None
        had_existing_graph = self._graph_view is not None or bool(
            self._local_node_objects)
        self._is_loading_graph_view = True
        try:
            self._clear_graph_items()
            self._graph_view = graph_view
            nodes_lookup = nodes_by_id or {}
            links_lookup = links_by_id or {}
            link_types_lookup = link_types_by_id or {}
            type_nodes_by_id: dict[str, Node] = {
                str(node.id): node
                for node in nodes_lookup.values()
                if node.category == "_type"
            }

            for local_id, proxy in graph_view.nodes.items():
                node = nodes_lookup.get(proxy.global_id)
                fallback = proxy.cached_name or proxy.global_id[:12]
                model = build_graph_render_model(
                    node=node,
                    proxy_name=fallback,
                    nodes_by_id=nodes_lookup,
                    links_by_id=links_lookup,
                    type_nodes_by_id=type_nodes_by_id,
                )
                node_item = self._make_graph_node_object(
                    local_id=local_id,
                    proxy=proxy,
                    model=model,
                )
                if proxy.capabilities:
                    node_item.load_capabilities(proxy.capabilities)
                self.add_object(node_item, z_order=1)
                self._local_node_objects[local_id] = node_item

            for edge_local_id, edge in graph_view.edges.items():
                source = self._local_node_objects.get(edge.source_local_id)
                target = self._local_node_objects.get(edge.target_local_id)
                if source is None or target is None:
                    continue
                source_bounds = source.bounds()
                target_bounds = target.bounds()
                source_center = (source_bounds.cx, source_bounds.cy)
                target_center = (target_bounds.cx, target_bounds.cy)
                source_anchor = source.link_anchor_toward(target_center)
                target_anchor = target.link_anchor_toward(source_center)

                link = links_lookup.get(edge.global_link_id)
                link_type = (
                    link_types_lookup.get(link.link_type_id)
                    if link is not None else None
                )
                link_color = (
                    effective_link_type_display_color(link_type)
                    if link_type is not None else None
                )
                edge_item = QKnowledgeGraphLinkCanvasObject(
                    link_id=edge.global_link_id,
                    link_type_id=(
                        str(link.link_type_id)
                        if link is not None else None
                    ),
                    source_anchor=source_anchor,
                    target_anchor=target_anchor,
                    color=link_color,
                    outgoing_label=link_type.name if link_type is not None else None,
                    incoming_label=(
                        link_type.inverse_name
                        if link_type is not None and link_type.inverse_name.strip()
                        else None
                    ),
                    on_select=self._on_link_selected,
                )
                self.add_object(edge_item)
                self._edge_objects[edge_local_id] = edge_item

            self._rebuild_incident_edge_index()

            self._sync_graph_selection_visuals()

            if self._view_state is not None:
                self._apply_link_type_view_state(self._view_state)

            if prior_view is not None:
                self.set_view(prior_view)
            else:
                self.frame_all_graph_nodes(
                    buffer_world_px=GRAPH_VIEW_FRAME_BUFFER_WORLD,
                    animate=had_existing_graph,
                )
        finally:
            self._is_loading_graph_view = False

    def apply_link_type_view_state(self, view_state: LinkTypeViewState) -> None:
        """Apply link-type visibility flags and recompute frontier node hiding.

        Stores the view state so it is automatically re-applied on the next
        ``load_graph_view`` call.

        Args:
            view_state: Current link-type view state.
        """
        self._view_state = view_state
        self._apply_link_type_view_state(view_state)

    def _apply_link_type_view_state(self, view_state: LinkTypeViewState) -> None:
        """Internal: push view state flags to edge objects.

        `filtered_out` is traversal metadata only and does not change current
        canvas node/link visibility.
        """
        links_to_deselect: list[QKnowledgeGraphLinkCanvasObject] = []
        for edge_item in self._edge_objects.values():
            link_type_id = edge_item.link_type_id or ""
            edge_item.update_view_flags(view_state.get_flags(link_type_id))
            if not edge_item.selectable and self.scene.selection().is_selected(edge_item):
                links_to_deselect.append(edge_item)
        for edge_item in links_to_deselect:
            self.deselect_object(edge_item)
        for node_item in self._local_node_objects.values():
            node_item.set_frontier_hidden(False)
        self.update()

    def _compute_frontier_hidden_global_ids(
        self, view_state: LinkTypeViewState
    ) -> set[str]:
        """Return hidden global node IDs for frontier filtering.

        Frontier filtering no longer hides currently rendered nodes.
        `filtered_out` is used only by traversal operations.
        """
        _ = view_state
        return set()

    def add_edge_item_fast(
        self,
        *,
        edge_local_id: str,
        source_local_id: str,
        target_local_id: str,
        link_id: str,
        link: LinkInstance | None,
        link_type: LinkType | None,
    ) -> None:
        """Add a single edge object to the canvas without full rebuild.

        Fast path for adding one edge after link creation without rebuilding
        the entire graph. Assumes source and target nodes are already rendered.
        """
        source = self._local_node_objects.get(source_local_id)
        target = self._local_node_objects.get(target_local_id)
        if source is None or target is None:
            return

        source_bounds = source.bounds()
        target_bounds = target.bounds()
        source_center = (source_bounds.cx, source_bounds.cy)
        target_center = (target_bounds.cx, target_bounds.cy)
        source_anchor = source.link_anchor_toward(target_center)
        target_anchor = target.link_anchor_toward(source_center)

        link_color = (
            effective_link_type_display_color(link_type)
            if link_type is not None else None
        )
        edge_item = QKnowledgeGraphLinkCanvasObject(
            link_id=link_id,
            link_type_id=(
                str(link.link_type_id)
                if link is not None else
                (str(link_type.id) if link_type is not None else None)
            ),
            source_anchor=source_anchor,
            target_anchor=target_anchor,
            color=link_color,
            outgoing_label=link_type.name if link_type is not None else None,
            incoming_label=(
                link_type.inverse_name
                if link_type is not None and link_type.inverse_name.strip()
                else None
            ),
            on_select=self._on_link_selected,
        )
        self.add_object(edge_item)
        self._edge_objects[edge_local_id] = edge_item

        # Keep canvas-local graph model in sync so _on_node_moved can resolve
        # source/target endpoints for fast-added edges without a full reload.
        if self._graph_view is not None:
            updated_edges = dict(self._graph_view.edges)
            updated_edges[edge_local_id] = GraphViewEdgeProxy(
                global_link_id=link_id,
                source_local_id=source_local_id,
                target_local_id=target_local_id,
            )
            self._graph_view = replace(self._graph_view, edges=updated_edges)
            self._register_incident_edge(
                edge_local_id,
                source_local_id=source_local_id,
                target_local_id=target_local_id,
            )

    def add_node_item_fast(
        self,
        *,
        local_id: str,
        proxy: GraphViewNodeProxy,
        node: Node | None,
        nodes_by_id: Mapping[str, Node],
        links_by_id: Mapping[str, LinkInstance],
    ) -> None:
        """Add a single node object without rebuilding the entire scene."""
        type_nodes_by_id: dict[str, Node] = {
            str(candidate.id): candidate
            for candidate in nodes_by_id.values()
            if candidate.category == "_type"
        }
        fallback = proxy.cached_name or proxy.global_id[:12]
        model = build_graph_render_model(
            node=node,
            proxy_name=fallback,
            nodes_by_id=nodes_by_id,
            links_by_id=links_by_id,
            type_nodes_by_id=type_nodes_by_id,
        )
        node_item = self._make_graph_node_object(
            local_id=local_id,
            proxy=proxy,
            model=model,
        )
        if proxy.capabilities:
            node_item.load_capabilities(proxy.capabilities)
        self.add_object(node_item, z_order=1)
        self._local_node_objects[local_id] = node_item
        if self._graph_view is not None:
            updated_nodes = dict(self._graph_view.nodes)
            updated_nodes[local_id] = proxy
            self._graph_view = replace(self._graph_view, nodes=updated_nodes)
        self._sync_graph_selection_visuals()
        if self._view_state is not None:
            self._apply_link_type_view_state(self._view_state)

    def refresh_loaded_nodes_fast(
        self,
        *,
        nodes_by_id: Mapping[str, Node],
        links_by_id: Mapping[str, LinkInstance],
        only_global_ids: set[str] | None = None,
    ) -> None:
        """Refresh rendered node cards in place without rebuilding the scene."""
        if self._graph_view is None:
            return
        target_ids = None if only_global_ids is None else {
            str(node_id) for node_id in only_global_ids
        }
        type_nodes_by_id: dict[str, Node] = {
            str(node.id): node
            for node in nodes_by_id.values()
            if node.category == "_type"
        }
        for local_id, proxy in self._graph_view.nodes.items():
            if target_ids is not None and proxy.global_id not in target_ids:
                continue
            node_item = self._local_node_objects.get(local_id)
            if node_item is None:
                continue
            node = nodes_by_id.get(proxy.global_id)
            fallback = proxy.cached_name or proxy.global_id[:12]
            model = build_graph_render_model(
                node=node,
                proxy_name=fallback,
                nodes_by_id=nodes_by_id,
                links_by_id=links_by_id,
                type_nodes_by_id=type_nodes_by_id,
            )
            node_item.update_render_model(
                title=model.title,
                subtitle=model.subtitle,
                width=model.width,
                height=model.height,
                rows=model.rows,
                max_visible_rows=model.max_visible_rows,
                header_bg_color=model.header_bg,
            )
        if self._view_state is not None:
            self._apply_link_type_view_state(self._view_state)

    def _tween_to_loaded_graph_view(self) -> None:
        union = self.scene.union_bounds()
        if self.width() <= 0 or self.height() <= 0:
            self.fit_to_content()
            return
        if union is None:
            self.go_to(
                ViewTransform(),
                animate=True,
                duration_ms=self._GRAPH_LOAD_TWEEN_MS,
            )
            return
        cx = (union.x0 + union.x1) / 2.0
        cy = (union.y0 + union.y1) / 2.0
        w = max(1e-6, union.width + (2.0 * GRAPH_VIEW_FRAME_BUFFER_WORLD))
        h = max(1e-6, union.height + (2.0 * GRAPH_VIEW_FRAME_BUFFER_WORLD))
        zoom = min(float(self.width()) / w, float(self.height()) / h)
        zoom = max(self.camera._MIN_ZOOM, min(self.camera._MAX_ZOOM, zoom))  # noqa: SLF001
        self.go_to(
            ViewTransform((cx, cy), zoom, 0.0),
            animate=True,
            duration_ms=self._GRAPH_LOAD_TWEEN_MS,
        )

    def graph_object_counts(self) -> tuple[int, int]:
        """Return rendered ``(node_count, edge_count)``."""
        return len(self._local_node_objects), len(self._edge_objects)

    def node_sizes_by_global_id(self) -> dict[str, tuple[float, float]]:
        """Return ``{global_id: (width, height)}`` for all loaded node objects."""
        return {
            item.node_id: (item.bounds().width, item.bounds().height)
            for item in self._local_node_objects.values()
        }

    def node_sizes_by_local_id(self) -> dict[str, tuple[float, float]]:
        """Return ``{local_id: (width, height)}`` for all loaded node objects."""
        return {
            local_id: (item.bounds().width, item.bounds().height)
            for local_id, item in self._local_node_objects.items()
        }

    def frame_all_graph_nodes(
        self,
        buffer_world_px: float = 64.0,
        *,
        animate: bool = False,
    ) -> bool:
        """Frame only graph node cards in view.

        This excludes link items and transient overlays so graph screenshots can
        consistently center on node content.
        """
        union = None
        for item in self._local_node_objects.values():
            bounds = item.bounds()
            union = bounds if union is None else union.union(bounds)
        return self.frame_all(
            buffer_world_px=buffer_world_px,
            animate=animate,
            bounds=union,
        )

    def view(self) -> ViewTransform:
        return super().view()

    def lock_view(self, view: ViewTransform | None) -> None:
        if view is None:
            return
        self.set_view(view)

    def set_view(self, view: ViewTransform) -> None:
        self.cancel_view_animation()
        super().set_view(view)

    def _clear_graph_items(self) -> None:
        self.clear_link_preview()
        for edge_item in self._edge_objects.values():
            self.remove_object(edge_item)
        self._edge_objects = {}
        self._incident_edge_ids = {}
        for node_item in self._local_node_objects.values():
            self.remove_object(node_item)
        self._local_node_objects.clear()

    def _rebuild_incident_edge_index(self) -> None:
        """Map each node local_id to incident edge local_ids for O(degree) drag updates."""
        index: dict[str, list[str]] = {}
        if self._graph_view is None:
            self._incident_edge_ids = {}
            return
        for edge_local_id, edge in self._graph_view.edges.items():
            index.setdefault(edge.source_local_id, []).append(edge_local_id)
            index.setdefault(edge.target_local_id, []).append(edge_local_id)
        self._incident_edge_ids = {
            local_id: tuple(edge_ids) for local_id, edge_ids in index.items()
        }

    def _register_incident_edge(
        self,
        edge_local_id: str,
        *,
        source_local_id: str,
        target_local_id: str,
    ) -> None:
        mutable = {k: list(v) for k, v in self._incident_edge_ids.items()}
        for node_local_id in (source_local_id, target_local_id):
            edge_ids = list(mutable.get(node_local_id, ()))
            if edge_local_id not in edge_ids:
                edge_ids.append(edge_local_id)
            mutable[node_local_id] = edge_ids
        self._incident_edge_ids = {
            local_id: tuple(edge_ids) for local_id, edge_ids in mutable.items()
        }

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._clear_graph_items()
        super().closeEvent(event)

    def _end_pointer_interactions(
        self,
        screen: tuple[float, float] | None,
        mods: frozenset[Modifier],
        *,
        commit_rubber_band: bool,
    ) -> None:
        """Emit ``objects_moved`` after capability-driven graph-node drags."""
        primary = self._primary_object
        drag_delta: tuple[float, float] | None = None
        if primary is not None and isinstance(primary, QKnowledgeGraphNodeCanvasObject):
            drag_cap = primary.capability_by_id("graph_node_drag")
            if drag_cap is not None:
                drag_delta = drag_cap._accumulated_delta  # noqa: SLF001

        super()._end_pointer_interactions(
            screen,
            mods,
            commit_rubber_band=commit_rubber_band,
        )
        self.pointer_gesture_finished.emit()

        if drag_delta is None:
            return
        dx, dy = drag_delta
        if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
            return
        if primary is None or not isinstance(primary, QKnowledgeGraphNodeCanvasObject):
            return
        moved_nodes = [
            item
            for item in self.selected_objects()
            if isinstance(item, QKnowledgeGraphNodeCanvasObject)
        ]
        if primary not in moved_nodes:
            moved_nodes = [primary]
        self.objects_moved.emit(moved_nodes)

    def _make_graph_node_object(
        self,
        *,
        local_id: str,
        proxy,
        model,
    ) -> QKnowledgeGraphNodeCanvasObject:
        """Build one graph node with per-anchor linked multi-drag sync."""
        anchor_holder: list[QKnowledgeGraphNodeCanvasObject] = []

        def _linked_sync(world_delta: tuple[float, float]) -> None:
            anchor = anchor_holder[0] if anchor_holder else None
            if anchor is None:
                return
            for item in self.selected_objects():
                if (
                    isinstance(item, QKnowledgeGraphNodeCanvasObject)
                    and item is not anchor
                ):
                    item.on_drag(world_delta)

        node_item = make_graph_node_object(
            node_id=proxy.global_id,
            model=model,
            x=proxy.x,
            y=proxy.y,
            on_moved=lambda _node_id, lid=local_id: self._on_local_node_moved(lid),
            linked_sync=_linked_sync,
        )
        anchor_holder.append(node_item)
        return node_item

    # type: ignore[override]
    def select_object(self, item: CanvasObject, *, additive: bool = False) -> None:
        """Select *item*, but never bring link items in front of nodes."""
        if hasattr(item, "selectable") and not bool(getattr(item, "selectable")):
            return
        self.scene.select_object(item, additive=additive)
        if self.capabilities.bring_selected_to_front and not isinstance(
            item, QKnowledgeGraphLinkCanvasObject
        ):
            self.scene.bring_object_to_front(item)

    def toggle_object_selection(self, item: CanvasObject) -> None:
        """Toggle selection; deselecting the active node does not auto-promote."""
        selection = self.scene.selection()
        demote_active = (
            selection.is_selected(item)
            and selection.active_object() is item
            and len(selection.selected_objects()) > 1
        )
        super().toggle_object_selection(item)
        if demote_active and selection.selected_objects():
            selection.clear_active()

    def _on_node_selected(self, node_item: QKnowledgeGraphNodeCanvasObject) -> None:
        self.select_object(node_item, additive=False)

    def _on_link_selected(self, link_item: QKnowledgeGraphLinkCanvasObject) -> None:
        self.select_object(link_item, additive=False)

    def _on_local_node_moved(self, local_id: str) -> None:
        """Update connected links for one moved local graph-node instance."""
        moved_node = self._local_node_objects.get(local_id)
        if moved_node is None or self._graph_view is None:
            return

        for edge_local_id in self._incident_edge_ids.get(local_id, ()):
            edge = self._graph_view.edges.get(edge_local_id)
            if edge is None:
                continue
            edge_item = self._edge_objects.get(edge_local_id)
            if edge_item is None or edge_item._preview:  # noqa: SLF001
                continue

            source_node = self._local_node_objects.get(edge.source_local_id)
            target_node = self._local_node_objects.get(edge.target_local_id)
            if source_node is None or target_node is None:
                continue

            old_bounds = edge_item.bounds()
            source_bounds = source_node.bounds()
            target_bounds = target_node.bounds()
            source_center = (source_bounds.cx, source_bounds.cy)
            target_center = (target_bounds.cx, target_bounds.cy)

            edge_item._source_anchor = source_node.link_anchor_toward(target_center)  # noqa: SLF001
            edge_item._target_anchor = target_node.link_anchor_toward(source_center)  # noqa: SLF001

            new_bounds = edge_item.bounds()
            edge_item.request_repaint(old_bounds.union(new_bounds))

    def _promote_active_selection_z_order(self, *_args: object) -> None:
        """Raise the active graph node above peers when selection changes."""
        if not self.capabilities.bring_selected_to_front:
            return
        active = self.active_selected_object()
        if isinstance(active, QKnowledgeGraphNodeCanvasObject):
            self.scene.bring_object_to_front(active)

    def _sync_graph_selection_visuals(self) -> None:
        selected = set(self.selected_objects())
        active = self.active_selected_object()

        selected_nodes = {
            item
            for item in selected
            if isinstance(item, QKnowledgeGraphNodeCanvasObject)
        }
        active_node = active if isinstance(active, QKnowledgeGraphNodeCanvasObject) else None
        for item in self._local_node_objects.values():
            prev = item._cached_selection_visual_state  # noqa: SLF001
            next_state = (item in selected_nodes, item is active_node)
            if prev == next_state:
                continue
            item.sync_selection_visuals()

        for edge_item in self._edge_objects.values():
            edge_item.selected = edge_item in selected
            edge_item.active_selected = edge_item is active

        if isinstance(active, QKnowledgeGraphNodeCanvasObject):
            if self._last_active_node_id != active.node_id:
                self._last_active_node_id = active.node_id
                self._last_active_link_id = None
                self.node_selected.emit(active.node_id)
        elif isinstance(active, QKnowledgeGraphLinkCanvasObject):
            if self._last_active_link_id != active.link_id:
                self._last_active_link_id = active.link_id
                self._last_active_node_id = None
                self.link_selected.emit(active.link_id)
        else:
            self._last_active_node_id = None
            self._last_active_link_id = None

        selected_node_ids = {
            item.node_id
            for item in selected
            if isinstance(item, QKnowledgeGraphNodeCanvasObject)
        }
        active_node_id = active.node_id if isinstance(
            active, QKnowledgeGraphNodeCanvasObject) else None
        if selected_node_ids != self._selected_ids or active_node_id != self._active_id:
            self._selected_ids = selected_node_ids
            self._active_id = active_node_id
            self.selection_model_changed.emit(
                self._selected_ids.copy(), self._active_id)

    def _snapshot_multi_node_drag_payload(self, sx: float, sy: float) -> None:
        if self._active_multi_drag_payload is not None:
            return
        if len(self._dragging_objects) < 2:
            return
        dragged_nodes = [
            item
            for item in self._dragging_objects
            if isinstance(item, QKnowledgeGraphNodeCanvasObject)
        ]
        if len(dragged_nodes) < 2:
            return
        selected_node_ids = {
            item.node_id
            for item in self.selected_objects()
            if isinstance(item, QKnowledgeGraphNodeCanvasObject)
        }
        if len(selected_node_ids) < 2:
            return
        if any(item.node_id not in selected_node_ids for item in dragged_nodes):
            return

        anchor_item = dragged_nodes[0]
        anchor_bounds = anchor_item.bounds()
        wx, wy = self._screen_to_world(sx, sy)
        node_ids = tuple(item.node_id for item in dragged_nodes)
        start_positions = {
            item.node_id: QPointF(item.bounds().x0, item.bounds().y0)
            for item in dragged_nodes
        }
        self._active_multi_drag_payload = MultiNodeDragPayload(
            node_ids=node_ids,
            anchor_node_id=anchor_item.node_id,
            cursor_offset_in_anchor=QPointF(
                wx - anchor_bounds.x0, wy - anchor_bounds.y0),
            start_positions=start_positions,
        )

    def _cancel_multi_node_drag(self) -> None:
        payload = self._active_multi_drag_payload
        if payload is None:
            return

        node_items_by_id = {
            item.node_id: item for item in self._local_node_objects.values()
        }
        for node_id, start_pos in payload.start_positions.items():
            node_item = node_items_by_id.get(node_id)
            if node_item is None:
                continue
            current = node_item.bounds()
            dx = float(start_pos.x()) - current.x0
            dy = float(start_pos.y()) - current.y0
            if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
                continue
            node_item.on_drag((dx, dy))

        if self._dragging_objects:
            for item in self._dragging_objects:
                item.on_drag_end()
            self._dragging_objects = []
            self._object_drag_screen_prev = None
            self._object_drag_world_deltas = {}

        self._active_multi_drag_payload = None
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._link_gestures.handle_key_press(event):
            return
        seq = QKeySequence(event.keyCombination()).toString()
        if self._active_multi_drag_payload is not None and get_default_bindings().matches_key(
            GRAPH_VIEW_DRAG_CANCEL.id,
            seq,
        ):
            self._cancel_multi_node_drag()
            event.accept()
            return
        if get_default_bindings().matches_key(
            KNOWLEDGE_REPO_DELETE_SELECTION.id,
            seq,
        ):
            delete_knowledge = bool(
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.delete_selection_requested.emit(delete_knowledge)
            event.accept()
            return
        if get_default_bindings().matches_key(
            GRAPH_VIEW_SELECTION_CLEAR_CANVAS.id,
            seq,
        ):
            self.clear_selection_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    # type: ignore[override]
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._link_gestures.handle_mouse_press(event):
            return

        button = qt_button_to_logical(event.button())
        if button is not None:
            mods = qt_modifiers_to_logical(event.modifiers())
            if get_default_bindings().matches_mouse(
                CANVAS_PRIMARY.id,
                button,
                mods,
                GestureKind.PRESS,
            ):
                selected_nodes = [
                    item
                    for item in self.selected_objects()
                    if isinstance(item, QKnowledgeGraphNodeCanvasObject)
                ]
                if len(selected_nodes) >= 2:
                    candidate_node_id = self._candidate_source_node_id_from_screen(
                        float(event.position().x()),
                        float(event.position().y()),
                    )
                    selected_node_ids = {
                        item.node_id for item in selected_nodes}
                    if candidate_node_id in selected_node_ids:
                        self._begin_object_drag(
                            selected_nodes,
                            (float(event.position().x()),
                             float(event.position().y())),
                        )
                        self._snapshot_multi_node_drag_payload(
                            float(event.position().x()),
                            float(event.position().y()),
                        )
                        event.accept()
                        return
        super().mousePressEvent(event)

    # type: ignore[override]
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._link_gestures.handle_mouse_move(event)
        self._snapshot_multi_node_drag_payload(
            float(event.position().x()),
            float(event.position().y()),
        )
        super().mouseMoveEvent(event)

    # type: ignore[override]
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        payload = self._active_multi_drag_payload
        super().mouseReleaseEvent(event)
        if payload is None:
            return
        node_items_by_id = {
            item.node_id: item for item in self._local_node_objects.values()
        }
        final_positions = {
            node_id: QPointF(node_items_by_id[node_id].bounds(
            ).x0, node_items_by_id[node_id].bounds().y0)
            for node_id in payload.node_ids
            if node_id in node_items_by_id
        }
        self.multi_node_drag_completed.emit(payload, final_positions)
        self._active_multi_drag_payload = None

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Show a context menu with 'Remove from Graph' when right-clicking a node."""
        wx, wy = self._screen_to_world(
            float(event.pos().x()), float(event.pos().y())
        )
        hit_item: QKnowledgeGraphNodeCanvasObject | None = None
        for item in self._local_node_objects.values():
            if item.hit_test((wx, wy)):
                hit_item = item
                break
        if hit_item is None:
            super().contextMenuEvent(event)
            return
        # Select the hit item as the active selection.
        self.select_object(hit_item, additive=False)
        menu = QMenu(self)
        remove_action = menu.addAction("Remove from Graph")
        chosen = menu.exec(event.globalPos())
        if chosen is remove_action:
            self.clear_selection_requested.emit()

    def flash_node_by_global_id(self, global_id: str, duration_ms: int = 500) -> bool:
        """Briefly select the item whose node_id matches *global_id*.

        Returns True if the item was found, False otherwise.
        """
        for item in reversed(list(self._local_node_objects.values())):
            if item.node_id == global_id:
                self.select_object(item, additive=False)
                QTimer.singleShot(
                    duration_ms,
                    lambda i=item: self.deselect_object(i),
                )
                return True
        return False


__all__ = [
    "QKnowledgeGraphCanvasWidget",
    "BatchPlacementPayload",
    "MultiNodeDragPayload",
    "estimate_graph_node_size_for_proxy",
]

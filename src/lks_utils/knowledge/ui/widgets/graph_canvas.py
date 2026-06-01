"""Canvas2D-based graph canvas for GraphView rendering."""
from __future__ import annotations
import json
from dataclasses import dataclass, replace
from math import ceil

from lks_utils.spatial.aabb import AABB
from lks_utils.knowledge.ui.actions import (
    GRAPH_VIEW_DRAG_CANCEL,
    GRAPH_LINK_CREATE_CANCEL,
    GRAPH_LINK_CREATE_TARGET_COMMIT,
    GRAPH_VIEW_SELECTION_CLEAR_CANVAS,
    KNOWLEDGE_REPO_DELETE_SELECTION,
)
from lks_utils.knowledge.display_color import (
    effective_link_type_display_color,
    effective_node_display_color,
)
from lks_utils.knowledge.links import INSTANCE_OF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType, SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID
from lks_utils.knowledge.link_type_view_state import LinkTypeViewState
from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.node_slot import SlotSource
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.ui.widgets.graph_link_canvas_item import (
    QKnowledgeGraphLinkCanvasItem,
)
from lks_utils.knowledge.ui.widgets.graph_node_canvas_item import (
    GraphNodeFieldRow,
    QKnowledgeGraphNodeCanvasItem,
)

from collections.abc import Mapping

from PySide6.QtCore import QPointF, QTimer, QRect, Qt, Signal
from PySide6.QtGui import QCloseEvent, QContextMenuEvent, QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QFont, QFontMetrics, QKeyEvent, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QMenu

from lks_utils.input import GestureKind
from lks_utils.input.qt_adapter import qt_button_to_logical, qt_modifiers_to_logical

from lks_utils.gui_qt.canvas2d.canvas2d_capabilities import Canvas2DCapabilities
from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.gui_qt.canvas2d.actions import CANVAS_PRIMARY
from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform
from lks_utils.input import get_default_bindings
from lks_utils.knowledge.ui.widgets.knowledge_edit_canvas import QKnowledgeEditCanvasWidget

_MISSING_NODE_HEADER_BG = "#5c1a1a"  # dark red â€” node not found in session
_GRAPH_ROW_HEIGHT_WORLD = 20.0
_GRAPH_STRING_WRAP_TRIGGER_CHARS = 36


@dataclass(frozen=True)
class MultiNodeDragPayload:
    """Captures state of a multi-node drag operation."""
    node_ids: tuple[str, ...]  # All selected node IDs being dragged
    anchor_node_id: str  # Primary node for cursor offset calculation
    cursor_offset_in_anchor: QPointF  # Cursor position relative to anchor
    start_positions: dict[str, QPointF]  # Original positions of all nodes


@dataclass(frozen=True)
class BatchPlacementPayload:
    """Payload for batch placement of instances onto canvas."""
    instance_ids: tuple[str, ...]  # Instance IDs to place
    drop_anchor: QPointF  # World-space anchor where batch drop occurred


_GRAPH_MULTILINE_MIN_LINES = 2
_GRAPH_MULTILINE_MAX_LINES = 3
_GRAPH_MULTILINE_ROW_PADDING_WORLD = 6.0
_GRAPH_NODE_MIN_WIDTH = 152.0
_GRAPH_NODE_MAX_WIDTH = 400.0
_GRAPH_NODE_MIN_HEIGHT = 64.0
_GRAPH_NODE_MAX_HEIGHT = 236.0
_GRAPH_NODE_CHROME_HEIGHT = 64.0
_GRAPH_NODE_WIDTH_SAFETY = 16.0
_GRAPH_NODE_HEIGHT_SAFETY = 8.0
_GRAPH_VIEW_FRAME_BUFFER_WORLD = 180.0


@dataclass(frozen=True, slots=True)
class _GraphNodeRenderModel:
    """Prepared graph-card content derived from one repository node."""

    title: str
    subtitle: str | None
    header_bg: str
    rows: list[GraphNodeFieldRow]
    width: float
    height: float
    max_visible_rows: int


@dataclass(frozen=True, slots=True)
class _GraphValueDisplay:
    """Text plus semantic kind for one rendered graph value."""

    text: str
    kind: str = "plain"


def _slot_type_token(slot) -> str:
    token = str(slot.value_type or "").strip()
    if token and token.lower() != "any":
        return token
    source = str(slot.source.value if hasattr(
        slot.source, "value") else slot.source)
    if "ref" in source:
        return "ref"
    return "value"


def _format_graph_value(value: object, nodes_by_id: Mapping[str, Node]) -> _GraphValueDisplay:
    if isinstance(value, str):
        target = nodes_by_id.get(value)
        if target is not None:
            return _GraphValueDisplay(text=target.name, kind="reference")
        return _GraphValueDisplay(text=value)

    if isinstance(value, (int, float, bool)) or value is None:
        return _GraphValueDisplay(text=str(value))

    if isinstance(value, dict):
        return _GraphValueDisplay(text="<Literal>", kind="literal")

    if isinstance(value, list):
        rendered: list[str] = []
        contains_reference = False
        for item in value:
            if isinstance(item, str):
                target = nodes_by_id.get(item)
                rendered.append(target.name if target is not None else item)
                contains_reference = True
                continue
            if isinstance(item, (str, int, float, bool)) or item is None:
                rendered.append(str(item))
                continue
            return _GraphValueDisplay(text="<Literal>", kind="literal")
        if not rendered:
            return _GraphValueDisplay(text="[]")
        if len(rendered) > 3:
            return _GraphValueDisplay(
                text=", ".join(rendered[:3]) + f", +{len(rendered) - 3}",
                kind="reference" if contains_reference else "plain",
            )
        return _GraphValueDisplay(
            text=", ".join(rendered),
            kind="reference" if contains_reference else "plain",
        )

    return _GraphValueDisplay(text="<Literal>", kind="literal")


def _slot_ref_target_ids_for_slot(
    node_id: str,
    slot_name: str,
    *,
    links_by_id: Mapping[str, LinkInstance],
) -> list[str]:
    return [
        str(link.target_node_id)
        for link in links_by_id.values()
        if (
            str(link.link_type_id) == SLOT_REF_LINK_TYPE_ID
            and str(link.source_node_id) == node_id
            and link.source_slot_name == slot_name
        )
    ]


def _graph_slot_value(
    *,
    node: Node,
    slot,
    links_by_id: Mapping[str, LinkInstance],
) -> object:
    if slot.effective_value_mode().allows_reference:
        target_ids = _slot_ref_target_ids_for_slot(
            str(node.id),
            slot.name,
            links_by_id=links_by_id,
        )
        if target_ids:
            if slot.source == SlotSource.REF_LIST:
                return target_ids
            return target_ids[0]
    if slot.name in node.props:
        return node.props.get(slot.name)
    return slot.default_value()


def _build_graph_rows(
    node: Node,
    *,
    nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance],
    type_nodes_by_id: Mapping[str, Node],
) -> list[GraphNodeFieldRow]:
    if node.type_id is not None:
        type_node = type_nodes_by_id.get(str(node.type_id))
        if type_node is not None:
            slots = _collect_graph_slots(
                type_node, type_nodes_by_id, links_by_id)
            rows: list[GraphNodeFieldRow] = []
            for slot in slots:
                formatted = _format_graph_value(
                    _graph_slot_value(
                        node=node,
                        slot=slot,
                        links_by_id=links_by_id,
                    ),
                    nodes_by_id,
                )
                rows.append(
                    GraphNodeFieldRow(
                        label=slot.name,
                        value_type=_slot_type_token(slot),
                        value=formatted.text,
                        value_kind=formatted.kind,
                    )
                )
            if rows:
                return rows

    rows: list[GraphNodeFieldRow] = []
    for key in sorted(node.props.keys()):
        value = node.props[key]
        formatted = _format_graph_value(value, nodes_by_id)
        rows.append(
            GraphNodeFieldRow(
                label=key,
                value_type=type(value).__name__,
                value=formatted.text,
                value_kind=formatted.kind,
            )
        )
    return rows


def _collect_graph_slots(
    type_node: Node,
    type_nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance],
) -> list:
    """Return merged ancestor+leaf slots for one graph node card."""
    if not is_type(type_node):
        return []

    chain = _graph_type_parent_chain(
        type_node, type_nodes_by_id, links_by_id) + [type_node]
    merged: dict[str, object] = {}
    for candidate in chain:
        if not is_type(candidate):
            continue
        for slot in as_type(candidate).slots:
            merged[slot.name] = slot
    return list(merged.values())


def _graph_type_parent_chain(
    type_node: Node,
    type_nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance],
) -> list[Node]:
    """Return ordered ancestor types for one graph-card type node."""
    chain: list[Node] = []
    current_id = str(type_node.id)
    visited: set[str] = {current_id}

    while True:
        parent_id = _graph_parent_type_id(
            current_id, type_nodes_by_id, links_by_id)
        if parent_id is None or parent_id in visited:
            break
        parent_node = type_nodes_by_id.get(parent_id)
        if parent_node is None:
            break
        chain.append(parent_node)
        visited.add(parent_id)
        current_id = parent_id

    chain.reverse()
    return chain


def _graph_parent_type_id(
    child_type_id: str,
    type_nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance],
) -> str | None:
    for link in links_by_id.values():
        if str(link.link_type_id) != EXTENDS_LINK_TYPE_ID:
            continue
        if str(link.source_node_id) != child_type_id:
            continue
        target_id = str(link.target_node_id)
        if target_id in type_nodes_by_id:
            return target_id

    child_node = type_nodes_by_id.get(child_type_id)
    if child_node is None or child_node.type_id is None:
        return None
    parent_id = str(child_node.type_id)
    if parent_id in type_nodes_by_id:
        return parent_id
    return None


def _fit_node_size(
    *,
    title: str,
    subtitle: str | None,
    rows: list[GraphNodeFieldRow],
) -> tuple[float, float, int]:
    row_font = QFont()
    row_font.setPixelSize(11)
    row_metrics = QFontMetrics(row_font)

    title_font = QFont()
    title_font.setPixelSize(12)
    title_metrics = QFontMetrics(title_font)
    subtitle_font = QFont()
    subtitle_font.setPixelSize(10)
    subtitle_font.setItalic(True)
    subtitle_metrics = QFontMetrics(subtitle_font)

    label_width = min(
        152.0,
        max(64.0, float(max((row_metrics.horizontalAdvance(row.label)
                             for row in rows), default=52)) + 14.0),
    )
    type_width = min(
        116.0,
        max(54.0, float(max((row_metrics.horizontalAdvance(f"({row.value_type})")
                             for row in rows), default=42)) + 12.0),
    )
    max_value_width = max(
        96.0,
        _GRAPH_NODE_MAX_WIDTH - 16.0 - label_width - type_width,
    )
    value_width = min(
        max_value_width,
        max(96.0, float(max((row_metrics.horizontalAdvance(row.value)
                             for row in rows), default=76)) + 20.0),
    )

    width = max(
        _GRAPH_NODE_MIN_WIDTH,
        16.0 + label_width + type_width + value_width + _GRAPH_NODE_WIDTH_SAFETY,
    )
    header_required = 24.0 + float(title_metrics.horizontalAdvance(title))
    if subtitle:
        header_required += 10.0 + \
            float(subtitle_metrics.horizontalAdvance(subtitle))
    width = max(width, min(_GRAPH_NODE_MAX_WIDTH, header_required))
    width = min(_GRAPH_NODE_MAX_WIDTH, width)

    row_heights = [_graph_row_display_height(row, width) for row in rows]
    available_rows_height = max(
        0.0, _GRAPH_NODE_MAX_HEIGHT - _GRAPH_NODE_CHROME_HEIGHT)
    consumed = 0.0
    max_visible_rows = 0
    for row_height in row_heights:
        if max_visible_rows and consumed + row_height > available_rows_height:
            break
        consumed += row_height
        max_visible_rows += 1
    max_visible_rows = min(len(rows), max(1, max_visible_rows)) if rows else 1

    visible_rows_height = sum(row_heights[:max_visible_rows])
    height = _GRAPH_NODE_CHROME_HEIGHT + \
        visible_rows_height + _GRAPH_NODE_HEIGHT_SAFETY
    height = max(_GRAPH_NODE_MIN_HEIGHT, min(_GRAPH_NODE_MAX_HEIGHT, height))

    return (width, height, max_visible_rows)


def _graph_row_display_height(row: GraphNodeFieldRow, node_width: float) -> float:
    label_width = min(152.0, max(64.0, (len(row.label) * 5.2) + 14.0))
    type_width = min(116.0, max(54.0, (len(row.value_type) * 5.0) + 12.0))
    value_width = max(20.0, node_width - 16.0 - label_width - type_width)
    font = QFont()
    font.setPixelSize(11)
    metrics = QFontMetrics(font)
    if metrics.horizontalAdvance(row.value) <= int(max(8.0, value_width - 8.0)):
        return _GRAPH_ROW_HEIGHT_WORLD
    line_height = max(float(metrics.lineSpacing()),
                      _GRAPH_ROW_HEIGHT_WORLD - 4.0)
    wrap_rect = metrics.boundingRect(
        QRect(0, 0, max(1, int(value_width - 8.0)), 4096),
        int(Qt.TextFlag.TextWordWrap),
        row.value,
    )
    estimated_lines = max(1, ceil(wrap_rect.height() / max(1.0, line_height)))
    min_lines = _GRAPH_MULTILINE_MIN_LINES
    if len(row.value) > 80:
        min_lines = max(min_lines, 3)
    visible_lines = max(
        min_lines,
        min(_GRAPH_MULTILINE_MAX_LINES, estimated_lines),
    )
    return max(
        _GRAPH_ROW_HEIGHT_WORLD,
        (line_height * visible_lines) + _GRAPH_MULTILINE_ROW_PADDING_WORLD,
    )


def _build_render_model(
    *,
    node: Node | None,
    proxy_name: str,
    nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance],
    type_nodes_by_id: Mapping[str, Node],
) -> _GraphNodeRenderModel:
    if node is None:
        title = f"\u26a0 {proxy_name}"
        subtitle = "missing"
        rows = [
            GraphNodeFieldRow(
                label="status",
                value_type="missing",
                value="Node not found in repository.",
                value_kind="literal",
            )
        ]
        width, height, max_visible_rows = _fit_node_size(
            title=title,
            subtitle=subtitle,
            rows=rows,
        )
        return _GraphNodeRenderModel(
            title=title,
            subtitle=subtitle,
            header_bg=_MISSING_NODE_HEADER_BG,
            rows=rows,
            width=width,
            height=height,
            max_visible_rows=max_visible_rows,
        )

    type_node: Node | None = None
    if node.type_id is not None:
        type_node = type_nodes_by_id.get(str(node.type_id))
    if type_node is None:
        for link in links_by_id.values():
            if (
                str(link.link_type_id) == INSTANCE_OF_LINK_TYPE_ID
                and str(link.source_node_id) == str(node.id)
            ):
                type_node = type_nodes_by_id.get(str(link.target_node_id))
                if type_node is not None:
                    break

    subtitle = type_node.name if type_node is not None else (
        node.category or None)
    rows = _build_graph_rows(
        node,
        nodes_by_id=nodes_by_id,
        links_by_id=links_by_id,
        type_nodes_by_id=type_nodes_by_id,
    )
    width, height, max_visible_rows = _fit_node_size(
        title=node.name,
        subtitle=subtitle,
        rows=rows,
    )
    return _GraphNodeRenderModel(
        title=node.name,
        subtitle=subtitle,
        header_bg=effective_node_display_color(
            node,
            type_node,
        ),
        rows=rows,
        width=width,
        height=height,
        max_visible_rows=max_visible_rows,
    )


def estimate_graph_node_size_for_proxy(
    *,
    node: Node | None,
    proxy_name: str,
    nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance] | None = None,
    type_nodes_by_id: Mapping[str, Node],
) -> tuple[float, float]:
    """Estimate graph card ``(width, height)`` using production sizing rules."""
    model = _build_render_model(
        node=node,
        proxy_name=proxy_name,
        nodes_by_id=nodes_by_id,
        links_by_id=links_by_id or {},
        type_nodes_by_id=type_nodes_by_id,
    )
    return (model.width, model.height)


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

    # Multi-node drag signal: emitted when drag completes with (payload, final_positions)
    multi_node_drag_completed = Signal(object, dict)

    _INSTANCE_MIME = "application/x-knowledge-instance-id"
    _INSTANCE_IDS_MIME = "application/x-knowledge-instance-ids"
    _TYPE_MIME = "application/x-knowledge-type-id"
    _LINK_TYPE_MIME = "application/x-knowledge-link-type-id"
    _GRAPH_LOAD_TWEEN_MS = 140

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            capabilities=Canvas2DCapabilities(
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
        self._local_node_items: dict[str, QKnowledgeGraphNodeCanvasItem] = {}
        self._edge_items: dict[str, QKnowledgeGraphLinkCanvasItem] = {}
        self._view_state: LinkTypeViewState | None = None
        self._is_loading_graph_view: bool = False
        self._last_active_node_id: str | None = None
        self._last_active_link_id: str | None = None
        self._link_creation_modal_active = False
        self._link_creation_target_mode = False
        self._preview_link_item: QKnowledgeGraphLinkCanvasItem | None = None
        self._active_multi_drag_payload: MultiNodeDragPayload | None = None
        self._selected_ids: set[str] = set()
        self._active_id: str | None = None
        self.setAcceptDrops(True)
        self.selection_changed.connect(self._sync_graph_selection_visuals)
        # Also sync when only the active item changes (e.g. shift-clicking an
        # already-selected node to promote it to active without changing the
        # selection set â€” selection_changed is not emitted in that case).
        self.active_selection_changed.connect(
            lambda _item: self._sync_graph_selection_visuals()
        )

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
        raw = event.mimeData().data(self._LINK_TYPE_MIME)
        if raw:
            try:
                return bytes(raw).decode("utf-8")
            except Exception:
                return None
        return None

    def _candidate_source_node_id_from_screen(self, sx: float, sy: float) -> str | None:
        wx, wy = self._screen_to_world(sx, sy)
        for item in reversed(self.scene.items()):
            if not isinstance(item, QKnowledgeGraphNodeCanvasItem):
                continue
            if not item.hit_test((wx, wy)):
                continue
            return item.node_id
        return None

    def set_link_creation_modal_active(self, active: bool) -> None:
        """Toggle whether RMB/Esc should cancel graph link creation modal state."""
        self._link_creation_modal_active = bool(active)
        if not self._link_creation_modal_active:
            self._link_creation_target_mode = False
            self.clear_link_preview()

    def set_link_creation_target_mode(self, active: bool) -> None:
        """Enable or disable target-pick hover streaming."""
        self._link_creation_target_mode = bool(active)
        if not self._link_creation_target_mode:
            self.clear_link_preview()

    def set_link_preview(
        self,
        *,
        source_node_id: str | None,
        target_node_id: str | None,
        cursor_world: tuple[float, float] | None = None,
        color: str | None = None,
    ) -> None:
        """Render a transient preview edge for link creation.

        ``target_node_id`` takes precedence over ``cursor_world`` when both are provided.
        """
        self.clear_link_preview()
        if source_node_id is None:
            return
        source_item = next(
            (item for item in reversed(list(self._local_node_items.values()))
             if item.node_id == source_node_id),
            None,
        )
        if source_item is None:
            return
        source_bounds = source_item.bounds()
        source_center = (source_bounds.cx, source_bounds.cy)
        target_center: tuple[float, float] | None = None
        if target_node_id is not None:
            target_item = next(
                (item for item in reversed(list(self._local_node_items.values()))
                 if item.node_id == target_node_id),
                None,
            )
            if target_item is not None:
                target_bounds = target_item.bounds()
                target_center = (target_bounds.cx, target_bounds.cy)
        if target_center is None:
            target_center = cursor_world
        if target_center is None:
            return
        source_anchor = source_item.link_anchor_toward(target_center)
        target_anchor = target_center
        if target_node_id is not None:
            target_item = next(
                (item for item in reversed(list(self._local_node_items.values()))
                 if item.node_id == target_node_id),
                None,
            )
            if target_item is not None:
                target_anchor = target_item.link_anchor_toward(source_center)
        preview_item = QKnowledgeGraphLinkCanvasItem(
            link_id="__preview_link__",
            source_anchor=source_anchor,
            target_anchor=target_anchor,
            color=color,
            outgoing_label=None,
            incoming_label=None,
            preview=True,
            on_select=None,
        )
        self.add_item(preview_item)
        self._preview_link_item = preview_item

    def clear_link_preview(self) -> None:
        """Remove the transient link-creation preview edge, if present."""
        if self._preview_link_item is None:
            return
        self.remove_item(self._preview_link_item)
        self._preview_link_item = None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        link_type_id = self._link_type_id_from_event(event)
        if link_type_id:
            self.link_source_drag_started.emit(link_type_id)
            event.acceptProposedAction()
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
        link_type_id = self._link_type_id_from_event(event)
        if link_type_id:
            candidate = self._candidate_source_node_id_from_screen(
                float(event.position().x()),
                float(event.position().y()),
            )
            self.link_source_drag_hovered.emit(link_type_id, candidate)
            event.acceptProposedAction()
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
        self.link_source_drag_hovered.emit("", None)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        link_type_id = self._link_type_id_from_event(event)
        if link_type_id:
            candidate = self._candidate_source_node_id_from_screen(
                float(event.position().x()),
                float(event.position().y()),
            )
            self.link_source_drop_finished.emit(link_type_id, candidate)
            event.acceptProposedAction()
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
            self._local_node_items)
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
                model = _build_render_model(
                    node=node,
                    proxy_name=fallback,
                    nodes_by_id=nodes_lookup,
                    links_by_id=links_lookup,
                    type_nodes_by_id=type_nodes_by_id,
                )
                node_item = QKnowledgeGraphNodeCanvasItem(
                    node_id=proxy.global_id,
                    title=model.title,
                    subtitle=model.subtitle,
                    x=proxy.x,
                    y=proxy.y,
                    width=model.width,
                    height=model.height,
                    rows=model.rows,
                    max_visible_rows=model.max_visible_rows,
                    header_bg_color=model.header_bg,
                    on_select=None,
                    on_clear=None,
                    on_moved=lambda _node_id, lid=local_id: self._on_local_node_moved(
                        lid),
                )
                self.add_item(node_item, z_order=1)
                self._local_node_items[local_id] = node_item

            for edge_local_id, edge in graph_view.edges.items():
                source = self._local_node_items.get(edge.source_local_id)
                target = self._local_node_items.get(edge.target_local_id)
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
                edge_item = QKnowledgeGraphLinkCanvasItem(
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
                self.add_item(edge_item)
                self._edge_items[edge_local_id] = edge_item

            self._sync_graph_selection_visuals()

            if self._view_state is not None:
                self._apply_link_type_view_state(self._view_state)

            if prior_view is not None:
                self.set_view(prior_view)
            else:
                self.frame_all_graph_nodes(
                    buffer_world_px=_GRAPH_VIEW_FRAME_BUFFER_WORLD,
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
        """Internal: push view state flags to edge items.

        `filtered_out` is traversal metadata only and does not change current
        canvas node/link visibility.
        """
        links_to_deselect: list[QKnowledgeGraphLinkCanvasItem] = []
        for edge_item in self._edge_items.values():
            link_type_id = edge_item.link_type_id or ""
            edge_item.update_view_flags(view_state.get_flags(link_type_id))
            if not edge_item.selectable and self.scene.selection().is_selected(edge_item):
                links_to_deselect.append(edge_item)
        for edge_item in links_to_deselect:
            self.deselect_item(edge_item)
        for node_item in self._local_node_items.values():
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
        """Add a single edge item to the canvas without full rebuild.

        Fast path for adding one edge after link creation without rebuilding
        the entire graph. Assumes source and target nodes are already rendered.
        """
        source = self._local_node_items.get(source_local_id)
        target = self._local_node_items.get(target_local_id)
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
        edge_item = QKnowledgeGraphLinkCanvasItem(
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
        self.add_item(edge_item)
        self._edge_items[edge_local_id] = edge_item

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

    def add_node_item_fast(
        self,
        *,
        local_id: str,
        proxy: GraphViewNodeProxy,
        node: Node | None,
        nodes_by_id: Mapping[str, Node],
        links_by_id: Mapping[str, LinkInstance],
    ) -> None:
        """Add a single node item without rebuilding the entire scene."""
        type_nodes_by_id: dict[str, Node] = {
            str(candidate.id): candidate
            for candidate in nodes_by_id.values()
            if candidate.category == "_type"
        }
        fallback = proxy.cached_name or proxy.global_id[:12]
        model = _build_render_model(
            node=node,
            proxy_name=fallback,
            nodes_by_id=nodes_by_id,
            links_by_id=links_by_id,
            type_nodes_by_id=type_nodes_by_id,
        )
        node_item = QKnowledgeGraphNodeCanvasItem(
            node_id=proxy.global_id,
            title=model.title,
            subtitle=model.subtitle,
            x=proxy.x,
            y=proxy.y,
            width=model.width,
            height=model.height,
            rows=model.rows,
            max_visible_rows=model.max_visible_rows,
            header_bg_color=model.header_bg,
            on_select=None,
            on_clear=None,
            on_moved=lambda _node_id, lid=local_id: self._on_local_node_moved(
                lid),
        )
        self.add_item(node_item, z_order=1)
        self._local_node_items[local_id] = node_item
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
            node_item = self._local_node_items.get(local_id)
            if node_item is None:
                continue
            node = nodes_by_id.get(proxy.global_id)
            fallback = proxy.cached_name or proxy.global_id[:12]
            model = _build_render_model(
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
        w = max(1e-6, union.width + (2.0 * _GRAPH_VIEW_FRAME_BUFFER_WORLD))
        h = max(1e-6, union.height + (2.0 * _GRAPH_VIEW_FRAME_BUFFER_WORLD))
        zoom = min(float(self.width()) / w, float(self.height()) / h)
        zoom = max(self.camera._MIN_ZOOM, min(self.camera._MAX_ZOOM, zoom))  # noqa: SLF001
        self.go_to(
            ViewTransform((cx, cy), zoom, 0.0),
            animate=True,
            duration_ms=self._GRAPH_LOAD_TWEEN_MS,
        )

    def graph_item_counts(self) -> tuple[int, int]:
        """Return rendered ``(node_count, edge_count)``."""
        return len(self._local_node_items), len(self._edge_items)

    def node_sizes_by_global_id(self) -> dict[str, tuple[float, float]]:
        """Return ``{global_id: (width, height)}`` for all loaded node items."""
        return {
            item.node_id: (item.bounds().width, item.bounds().height)
            for item in self._local_node_items.values()
        }

    def node_sizes_by_local_id(self) -> dict[str, tuple[float, float]]:
        """Return ``{local_id: (width, height)}`` for all loaded node items."""
        return {
            local_id: (item.bounds().width, item.bounds().height)
            for local_id, item in self._local_node_items.items()
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
        for item in self._local_node_items.values():
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
        for edge_item in self._edge_items.values():
            self.remove_item(edge_item)
        self._edge_items = {}
        for node_item in self._local_node_items.values():
            self.remove_item(node_item)
        self._local_node_items.clear()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._clear_graph_items()
        super().closeEvent(event)

    @staticmethod
    def _clear_flashed_item_selection(item: QKnowledgeGraphNodeCanvasItem) -> None:
        try:
            item.selected = False
        except (AttributeError, RuntimeError):
            # Teardown can race the timer callback; clearing the transient flash
            # is best-effort and should not surface as a later unrelated test
            # failure once the backing scene has already gone away.
            if hasattr(item, "_selected"):
                item._selected = False  # noqa: SLF001

    # type: ignore[override]
    def select_item(self, item: CanvasItem, *, additive: bool = False) -> None:
        """Select *item*, but never bring link items in front of nodes."""
        if hasattr(item, "selectable") and not bool(getattr(item, "selectable")):
            return
        self.scene.select_item(item, additive=additive)
        if self.capabilities.bring_selected_to_front and not isinstance(
            item, QKnowledgeGraphLinkCanvasItem
        ):
            self.scene.bring_item_to_front(item)

    def _on_node_selected(self, node_item: QKnowledgeGraphNodeCanvasItem) -> None:
        self.select_item(node_item, additive=False)

    def _on_link_selected(self, link_item: QKnowledgeGraphLinkCanvasItem) -> None:
        self.select_item(link_item, additive=False)

    def _on_local_node_moved(self, local_id: str) -> None:
        """Update connected links for one moved local graph-node instance."""
        moved_node = self._local_node_items.get(local_id)
        if moved_node is None or self._graph_view is None:
            return

        for edge_local_id, edge in self._graph_view.edges.items():
            if edge.source_local_id != local_id and edge.target_local_id != local_id:
                continue
            edge_item = self._edge_items.get(edge_local_id)
            if edge_item is None or edge_item._preview:  # noqa: SLF001
                continue

            source_node = self._local_node_items.get(edge.source_local_id)
            target_node = self._local_node_items.get(edge.target_local_id)
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

    def _sync_graph_selection_visuals(self) -> None:
        selected = set(self.selected_items())
        active = self.active_selected_item()

        for item in self._local_node_items.values():
            item.selected = item in selected
            item.active_selected = item is active

        for edge_item in self._edge_items.values():
            edge_item.selected = edge_item in selected
            edge_item.active_selected = edge_item is active

        if isinstance(active, QKnowledgeGraphNodeCanvasItem):
            if self._last_active_node_id != active.node_id:
                self._last_active_node_id = active.node_id
                self._last_active_link_id = None
                self.node_selected.emit(active.node_id)
        elif isinstance(active, QKnowledgeGraphLinkCanvasItem):
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
            if isinstance(item, QKnowledgeGraphNodeCanvasItem)
        }
        active_node_id = active.node_id if isinstance(
            active, QKnowledgeGraphNodeCanvasItem) else None
        if selected_node_ids != self._selected_ids or active_node_id != self._active_id:
            self._selected_ids = selected_node_ids
            self._active_id = active_node_id
            self.selection_model_changed.emit(
                self._selected_ids.copy(), self._active_id)

    def _snapshot_multi_node_drag_payload(self, sx: float, sy: float) -> None:
        if self._active_multi_drag_payload is not None:
            return
        if len(self._dragging_items) < 2:
            return
        dragged_nodes = [
            item
            for item in self._dragging_items
            if isinstance(item, QKnowledgeGraphNodeCanvasItem)
        ]
        if len(dragged_nodes) < 2:
            return
        selected_node_ids = {
            item.node_id
            for item in self.selected_items()
            if isinstance(item, QKnowledgeGraphNodeCanvasItem)
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
            item.node_id: item for item in self._local_node_items.values()
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

        if self._dragging_items:
            for item in self._dragging_items:
                item.on_drag_end()
            self._dragging_items = []
            self._item_drag_screen_prev = None
            self._item_drag_world_deltas = {}

        self._active_multi_drag_payload = None
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        seq = QKeySequence(event.keyCombination()).toString()
        if self._link_creation_modal_active and get_default_bindings().matches_key(
            GRAPH_LINK_CREATE_CANCEL.id,
            seq,
        ):
            self.link_creation_cancel_requested.emit()
            event.accept()
            return
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
        if self._link_creation_modal_active and self._link_creation_target_mode:
            button = qt_button_to_logical(event.button())
            if button is not None:
                mods = qt_modifiers_to_logical(event.modifiers())
                if get_default_bindings().matches_mouse(
                    GRAPH_LINK_CREATE_TARGET_COMMIT.id,
                    button,
                    mods,
                    GestureKind.PRESS,
                ):
                    candidate = self._candidate_source_node_id_from_screen(
                        float(event.position().x()),
                        float(event.position().y()),
                    )
                    wx, wy = self._screen_to_world(
                        float(event.position().x()),
                        float(event.position().y()),
                    )
                    self.link_target_clicked.emit(candidate, wx, wy)
                    event.accept()
                    return
        if self._link_creation_modal_active:
            button = qt_button_to_logical(event.button())
            if button is not None:
                mods = qt_modifiers_to_logical(event.modifiers())
                if get_default_bindings().matches_mouse(
                    GRAPH_LINK_CREATE_CANCEL.id,
                    button,
                    mods,
                    GestureKind.PRESS,
                ):
                    self.link_creation_cancel_requested.emit()
                    event.accept()
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
                    for item in self.selected_items()
                    if isinstance(item, QKnowledgeGraphNodeCanvasItem) and item.draggable
                ]
                if len(selected_nodes) >= 2:
                    candidate_node_id = self._candidate_source_node_id_from_screen(
                        float(event.position().x()),
                        float(event.position().y()),
                    )
                    selected_node_ids = {
                        item.node_id for item in selected_nodes}
                    if candidate_node_id in selected_node_ids:
                        self._begin_item_drag(
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
        if self._link_creation_modal_active and self._link_creation_target_mode:
            candidate = self._candidate_source_node_id_from_screen(
                float(event.position().x()),
                float(event.position().y()),
            )
            wx, wy = self._screen_to_world(
                float(event.position().x()),
                float(event.position().y()),
            )
            self.link_target_hovered.emit(candidate, wx, wy)
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
            item.node_id: item for item in self._local_node_items.values()
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
        hit_item: QKnowledgeGraphNodeCanvasItem | None = None
        for item in self._local_node_items.values():
            if item.hit_test((wx, wy)):
                hit_item = item
                break
        if hit_item is None:
            super().contextMenuEvent(event)
            return
        # Select the hit item as the active selection.
        self.select_item(hit_item, additive=False)
        menu = QMenu(self)
        remove_action = menu.addAction("Remove from Graph")
        chosen = menu.exec(event.globalPos())
        if chosen is remove_action:
            self.clear_selection_requested.emit()

    def flash_node_by_global_id(self, global_id: str, duration_ms: int = 500) -> bool:
        """Briefly select the item whose node_id matches *global_id*.

        Returns True if the item was found, False otherwise.
        """
        for item in reversed(list(self._local_node_items.values())):
            if item.node_id == global_id:
                self.select_item(item, additive=False)
                QTimer.singleShot(
                    duration_ms,
                    lambda i=item: self.deselect_item(i),
                )
                return True
        return False


__all__ = [
    "QKnowledgeGraphCanvasWidget",
    "BatchPlacementPayload",
    "MultiNodeDragPayload",
    "estimate_graph_node_size_for_proxy",
]

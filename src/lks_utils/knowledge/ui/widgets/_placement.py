"""Graph node placement sizing and render-model helpers (knowledge-private)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics

from lks_utils.knowledge.display_color import effective_node_display_color
from lks_utils.knowledge.links import INSTANCE_OF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_slot import SlotSource
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.ui.widgets.graph_node_canvas_object import GraphNodeFieldRow

_MISSING_NODE_HEADER_BG = "#5c1a1a"  # dark red — node not found in session
_GRAPH_ROW_HEIGHT_WORLD = 20.0

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
GRAPH_VIEW_FRAME_BUFFER_WORLD = 180.0


@dataclass(frozen=True)
class BatchPlacementPayload:
    """Payload for batch placement of instances onto canvas."""

    instance_ids: tuple[str, ...]
    drop_anchor: QPointF


@dataclass(frozen=True, slots=True)
class GraphNodeRenderModel:
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
    text: str
    kind: str = "plain"


def _slot_type_token(slot) -> str:
    token = str(slot.value_type or "").strip()
    if token and token.lower() != "any":
        return token
    source = str(slot.source.value if hasattr(slot.source, "value") else slot.source)
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
            slots = _collect_graph_slots(type_node, type_nodes_by_id, links_by_id)
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
    if not is_type(type_node):
        return []

    chain = _graph_type_parent_chain(type_node, type_nodes_by_id, links_by_id) + [type_node]
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
    chain: list[Node] = []
    current_id = str(type_node.id)
    visited: set[str] = {current_id}

    while True:
        parent_id = _graph_parent_type_id(current_id, type_nodes_by_id, links_by_id)
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
        max(64.0, float(max((row_metrics.horizontalAdvance(row.label) for row in rows), default=52)) + 14.0),
    )
    type_width = min(
        116.0,
        max(54.0, float(max((row_metrics.horizontalAdvance(f"({row.value_type})") for row in rows), default=42)) + 12.0),
    )
    max_value_width = max(
        96.0,
        _GRAPH_NODE_MAX_WIDTH - 16.0 - label_width - type_width,
    )
    value_width = min(
        max_value_width,
        max(96.0, float(max((row_metrics.horizontalAdvance(row.value) for row in rows), default=76)) + 20.0),
    )

    width = max(
        _GRAPH_NODE_MIN_WIDTH,
        16.0 + label_width + type_width + value_width + _GRAPH_NODE_WIDTH_SAFETY,
    )
    header_required = 24.0 + float(title_metrics.horizontalAdvance(title))
    if subtitle:
        header_required += 10.0 + float(subtitle_metrics.horizontalAdvance(subtitle))
    width = max(width, min(_GRAPH_NODE_MAX_WIDTH, header_required))
    width = min(_GRAPH_NODE_MAX_WIDTH, width)

    row_heights = [_graph_row_display_height(row, width) for row in rows]
    available_rows_height = max(0.0, _GRAPH_NODE_MAX_HEIGHT - _GRAPH_NODE_CHROME_HEIGHT)
    consumed = 0.0
    max_visible_rows = 0
    for row_height in row_heights:
        if max_visible_rows and consumed + row_height > available_rows_height:
            break
        consumed += row_height
        max_visible_rows += 1
    max_visible_rows = min(len(rows), max(1, max_visible_rows)) if rows else 1

    visible_rows_height = sum(row_heights[:max_visible_rows])
    height = _GRAPH_NODE_CHROME_HEIGHT + visible_rows_height + _GRAPH_NODE_HEIGHT_SAFETY
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
    line_height = max(float(metrics.lineSpacing()), _GRAPH_ROW_HEIGHT_WORLD - 4.0)
    wrap_rect = metrics.boundingRect(
        QRect(0, 0, max(1, int(value_width - 8.0)), 4096),
        int(Qt.TextFlag.TextWordWrap),
        row.value,
    )
    estimated_lines = max(1, ceil(wrap_rect.height() / max(1.0, line_height)))
    min_lines = _GRAPH_MULTILINE_MIN_LINES
    if len(row.value) > 80:
        min_lines = max(min_lines, 3)
    visible_lines = max(min_lines, min(_GRAPH_MULTILINE_MAX_LINES, estimated_lines))
    return max(
        _GRAPH_ROW_HEIGHT_WORLD,
        (line_height * visible_lines) + _GRAPH_MULTILINE_ROW_PADDING_WORLD,
    )


def build_graph_render_model(
    *,
    node: Node | None,
    proxy_name: str,
    nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance],
    type_nodes_by_id: Mapping[str, Node],
) -> GraphNodeRenderModel:
    """Build title, rows, and fitted card dimensions for one graph node proxy."""
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
        return GraphNodeRenderModel(
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

    subtitle = type_node.name if type_node is not None else (node.category or None)
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
    return GraphNodeRenderModel(
        title=node.name,
        subtitle=subtitle,
        header_bg=effective_node_display_color(node, type_node),
        rows=rows,
        width=width,
        height=height,
        max_visible_rows=max_visible_rows,
    )


# Back-compat alias for tests that import the private name.
_build_render_model = build_graph_render_model


def estimate_graph_node_size_for_proxy(
    *,
    node: Node | None,
    proxy_name: str,
    nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance] | None = None,
    type_nodes_by_id: Mapping[str, Node],
) -> tuple[float, float]:
    """Estimate graph card ``(width, height)`` using production sizing rules."""
    model = build_graph_render_model(
        node=node,
        proxy_name=proxy_name,
        nodes_by_id=nodes_by_id,
        links_by_id=links_by_id or {},
        type_nodes_by_id=type_nodes_by_id,
    )
    return (model.width, model.height)


__all__ = [
    "BatchPlacementPayload",
    "GRAPH_VIEW_FRAME_BUFFER_WORLD",
    "GraphNodeRenderModel",
    "build_graph_render_model",
    "estimate_graph_node_size_for_proxy",
]

"""Instance palette panel for graph-view drag-and-drop workflows."""
from __future__ import annotations

import json

from PySide6.QtCore import QMimeData, QModelIndex, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QDrag, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from lks_utils.gui_qt.widgets.q_validation_badge import QValidationBadge
from lks_utils.knowledge.default_theme import (
    COLLAPSE_ARROW_COLOR,
    EDGE_COLOR,
    LIBRARY_TREE_INDENT_PX,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.ui.widgets.validation_badge_row_controller import (
    ValidationBadgeRowController,
)

MIME_GRAPH_INSTANCE_ID = "application/x-knowledge-instance-id"
MIME_GRAPH_INSTANCE_IDS = "application/x-knowledge-instance-ids"

_LEAF_FLAGS = (
    Qt.ItemFlag.ItemIsEnabled
    | Qt.ItemFlag.ItemIsSelectable
    | Qt.ItemFlag.ItemIsDragEnabled
)
_HEADER_FLAGS = Qt.ItemFlag.ItemIsEnabled


class _GraphInstancePaletteTreeWidget(QTreeWidget):
    """Drag-enabled tree that emits selected instance ids as MIME payload."""

    def drawBranches(  # type: ignore[override]
        self, painter: QPainter, rect: QRect, index: QModelIndex
    ) -> None:
        item = self.itemFromIndex(index)
        if item is None or item.childCount() == 0:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(COLLAPSE_ARROW_COLOR)))
        half = 4
        inset = 2
        desired_cx = rect.right() - inset - half
        min_cx = rect.left() + inset + half
        max_cx = rect.right() - inset - half
        cx = max(min_cx, min(desired_cx, max_cx))
        desired_cy = rect.top() + rect.height() // 2
        min_cy = rect.top() + inset + half
        max_cy = rect.bottom() - inset - half
        cy = max(min_cy, min(desired_cy, max_cy))
        if self.isExpanded(index):
            points = [
                QPoint(cx - half, cy - half // 2),
                QPoint(cx + half, cy - half // 2),
                QPoint(cx, cy + half),
            ]
        else:
            points = [
                QPoint(cx - half // 2, cy - half),
                QPoint(cx + half, cy),
                QPoint(cx - half // 2, cy + half),
            ]
        painter.drawPolygon(points)
        painter.restore()

    # type: ignore[override]
    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:
        mime = QMimeData()
        instance_ids: list[str] = []
        for item in items:
            instance_id = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(instance_id, str):
                instance_ids.append(instance_id)
        if not instance_ids:
            return mime
        if len(instance_ids) == 1:
            mime.setData(MIME_GRAPH_INSTANCE_ID,
                         instance_ids[0].encode("utf-8"))
        payload = json.dumps(instance_ids).encode("utf-8")
        mime.setData(MIME_GRAPH_INSTANCE_IDS, payload)
        return mime

    def startDrag(self, supported_actions) -> None:  # type: ignore[override]
        selected = self.selectedItems()
        if not selected:
            return
        mime = self.mimeData(selected)
        if not mime.hasFormat(MIME_GRAPH_INSTANCE_IDS):
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)


class QGraphInstancePalettePanel(QWidget):
    """QTreeWidget-based palette listing instances nested by type and instance inheritance."""

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._badge_controller = ValidationBadgeRowController(
            session.validation_index, self)
        self._attached_object_ids: set[str] = set()
        # inst_id -> row widget for styling
        self._row_widgets: dict[str, QWidget] = {}
        self._tree = _GraphInstancePaletteTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.setDragEnabled(True)
        self._tree.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.setColumnCount(1)
        self._tree.setIndentation(max(0, int(LIBRARY_TREE_INDENT_PX)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._tree)

        self._apply_styles()
        self.refresh()

    def refresh(self) -> None:
        """Reload instance tree: grouped by type, instances-of-instances nested."""
        for object_id in self._attached_object_ids:
            self._badge_controller.detach_row(object_id)
        self._attached_object_ids.clear()
        self._row_widgets.clear()
        self._tree.clear()

        type_nodes: dict[str, Node] = {}
        for t in self._session.iter_types():
            type_nodes[str(t.id)] = t

        instance_nodes: dict[str, Node] = {}
        for inst in self._session.iter_instances():
            instance_nodes[str(inst.id)] = inst

        type_ids = set(type_nodes.keys())
        instance_ids = set(instance_nodes.keys())

        # Resolve each instance's parent via its type_id field.
        # type_id may point to a type node → standard grouping.
        # type_id may point to another instance → instance-of-instance nesting.
        instance_parent_type: dict[str, str] = {}  # inst_id → type_id
        instance_parent_inst: dict[str, str] = {}  # inst_id → parent_inst_id
        for inst_id, inst in instance_nodes.items():
            if inst.type_id is None:
                continue
            parent_id = str(inst.type_id)
            if parent_id in type_ids:
                instance_parent_type[inst_id] = parent_id
            elif parent_id in instance_ids:
                instance_parent_inst[inst_id] = parent_id

        # Reverse maps: who are the children of each type / instance?
        instances_of_type: dict[str, list[str]] = {}
        for inst_id, type_id in instance_parent_type.items():
            instances_of_type.setdefault(type_id, []).append(inst_id)

        instances_of_instance: dict[str, list[str]] = {}
        for inst_id, parent_inst_id in instance_parent_inst.items():
            instances_of_instance.setdefault(
                parent_inst_id, []).append(inst_id)

        # Build type inheritance graph for section ordering:
        # root type -> subtype -> ... -> instances.
        children_of_type: dict[str, list[str]] = {}
        parents_of_type: dict[str, list[str]] = {}
        for link in self._session.list_links():
            if str(link.link_type_id) != EXTENDS_LINK_TYPE_ID:
                continue
            child_id = str(link.source_node_id)
            parent_id = str(link.target_node_id)
            if child_id not in type_ids or parent_id not in type_ids:
                continue
            children_of_type.setdefault(parent_id, []).append(child_id)
            parents_of_type.setdefault(child_id, []).append(parent_id)

        # Keep only type branches that have direct instances or are ancestors
        # of types that have direct instances.
        active_type_ids = set(instances_of_type.keys())
        frontier = list(active_type_ids)
        while frontier:
            child_id = frontier.pop()
            for parent_id in parents_of_type.get(child_id, []):
                if parent_id in active_type_ids:
                    continue
                active_type_ids.add(parent_id)
                frontier.append(parent_id)

        ungrouped = [
            inst
            for inst_id, inst in instance_nodes.items()
            if inst_id not in instance_parent_type and inst_id not in instance_parent_inst
        ]

        _header_brush = QBrush(QColor(EDGE_COLOR))

        def _add_instance_children(
            parent_item: QTreeWidgetItem,
            parent_instance_id: str,
            stack: frozenset[str],
        ) -> None:
            child_nodes = [
                instance_nodes[cid]
                for cid in instances_of_instance.get(parent_instance_id, [])
                if cid in instance_nodes
            ]
            if not child_nodes:
                return
            for child in sorted(child_nodes, key=lambda n: n.name.lower()):
                _add_instance(parent_item, child, stack)

        def _add_instance(
            parent_widget: QTreeWidgetItem,
            inst: Node,
            stack: frozenset[str],
        ) -> None:
            inst_id = str(inst.id)
            if inst_id in stack:
                return  # cycle guard
            item = QTreeWidgetItem(parent_widget, [""])
            item.setData(0, Qt.ItemDataRole.UserRole, inst_id)
            item.setFlags(_LEAF_FLAGS)
            row = QWidget(self._tree)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 0, 2, 0)
            row_layout.setSpacing(6)
            badge = QValidationBadge(row)
            text_label = QLabel(inst.name, row)
            row_layout.addWidget(badge, stretch=0)
            row_layout.addWidget(text_label, stretch=1)
            if inst_id in instances_of_instance:
                row.setToolTip(
                    "Instance (draggable). Contains child instances via inheritance."
                )
            else:
                row.setToolTip("Instance (draggable).")
            row_height = max(badge.sizeHint().height(),
                             text_label.sizeHint().height()) + 4
            item.setSizeHint(0, QSize(0, row_height))
            self._tree.setItemWidget(item, 0, row)
            self._row_widgets[inst_id] = row
            self._badge_controller.attach_row(inst_id, row, badge)
            self._attached_object_ids.add(inst_id)
            if inst_id in instances_of_instance:
                new_stack = stack | {inst_id}
                _add_instance_children(item, inst_id, new_stack)
                item.setExpanded(True)

        def _add_type_section(
            parent_widget: QTreeWidget | QTreeWidgetItem,
            type_id: str,
            stack: frozenset[str],
        ) -> None:
            if type_id in stack:
                return
            type_node = type_nodes[type_id]
            header = QTreeWidgetItem(parent_widget, [type_node.name])
            header.setData(0, Qt.ItemDataRole.UserRole, None)
            header.setFlags(_HEADER_FLAGS)
            header.setForeground(0, _header_brush)
            header.setToolTip(0, "Type section (not draggable)")

            direct_insts = [
                instance_nodes[iid]
                for iid in instances_of_type.get(type_id, [])
                if iid in instance_nodes
            ]
            if direct_insts:
                for inst in sorted(direct_insts, key=lambda n: n.name.lower()):
                    _add_instance(header, inst, frozenset())

            new_stack = stack | {type_id}
            child_type_ids = sorted(
                [
                    child_id
                    for child_id in children_of_type.get(type_id, [])
                    if child_id in active_type_ids
                ],
                key=lambda child_id: type_nodes[child_id].name.lower(),
            )
            for child_type_id in child_type_ids:
                _add_type_section(header, child_type_id, new_stack)
            header.setExpanded(True)

        root_type_ids = sorted(
            [
                type_id
                for type_id in active_type_ids
                if not any(parent_id in active_type_ids for parent_id in parents_of_type.get(type_id, []))
            ],
            key=lambda type_id: type_nodes[type_id].name.lower(),
        )
        for root_type_id in root_type_ids:
            _add_type_section(self._tree, root_type_id, frozenset())

        if ungrouped:
            ug_header = QTreeWidgetItem(self._tree, ["Ungrouped"])
            ug_header.setData(0, Qt.ItemDataRole.UserRole, None)
            ug_header.setFlags(_HEADER_FLAGS)
            ug_header.setForeground(0, _header_brush)
            ug_header.setToolTip(0, "Ungrouped section (not draggable)")
            for inst in sorted(ungrouped, key=lambda n: n.name.lower()):
                _add_instance(ug_header, inst, frozenset())
            ug_header.setExpanded(True)

    def set_active_selection(self, active_id: str | None) -> None:
        """Apply outline-only styling to row matching active_id, clear others."""
        from lks_utils.knowledge.default_theme import NODE_ACTIVE_SELECTED_STROKE_COLOR

        # Clear active styling from all rows
        for row_widget in self._row_widgets.values():
            row_widget.setStyleSheet("")

        # Apply active styling to matching row
        if active_id is not None and active_id in self._row_widgets:
            row_widget = self._row_widgets[active_id]
            row_widget.setStyleSheet(
                f"QWidget {{ border: 2px solid {NODE_ACTIVE_SELECTED_STROKE_COLOR}; border-radius: 2px; }}"
            )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QTreeWidget {{ border: 1px solid {EDGE_COLOR}; }}"
            f"QTreeWidget::item:selected {{ background: {EDGE_COLOR}; }}"
        )


__all__ = [
    "MIME_GRAPH_INSTANCE_ID",
    "MIME_GRAPH_INSTANCE_IDS",
    "QGraphInstancePalettePanel",
]

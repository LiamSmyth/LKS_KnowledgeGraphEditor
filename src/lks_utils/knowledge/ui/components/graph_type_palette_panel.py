"""Type palette panel for graph-view drag-and-drop workflows."""
from __future__ import annotations

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
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.ui.widgets.validation_badge_row_controller import (
    ValidationBadgeRowController,
)

MIME_GRAPH_TYPE_ID = "application/x-knowledge-type-id"

_ITEM_FLAGS = (
    Qt.ItemFlag.ItemIsEnabled
    | Qt.ItemFlag.ItemIsSelectable
    | Qt.ItemFlag.ItemIsDragEnabled
)


class _GraphTypePaletteTreeWidget(QTreeWidget):
    """Drag-enabled tree that emits selected type ids as MIME payload."""

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
        if len(items) != 1:
            return mime
        type_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        if isinstance(type_id, str):
            mime.setData(MIME_GRAPH_TYPE_ID, type_id.encode("utf-8"))
        return mime

    def startDrag(self, supported_actions) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None:
            return
        type_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(type_id, str):
            return
        mime = QMimeData()
        mime.setData(MIME_GRAPH_TYPE_ID, type_id.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)


class QGraphTypePalettePanel(QWidget):
    """QTreeWidget-based palette listing type nodes nested by inheritance."""

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._badge_controller = ValidationBadgeRowController(
            session.validation_index, self)
        self._attached_object_ids: set[str] = set()
        self._tree = _GraphTypePaletteTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.setDragEnabled(True)
        self._tree.setColumnCount(1)
        self._tree.setIndentation(max(0, int(LIBRARY_TREE_INDENT_PX)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._tree)

        self._apply_styles()
        self.refresh()

    def refresh(self) -> None:
        """Reload type-node tree from session, nested by extends inheritance."""
        for object_id in self._attached_object_ids:
            self._badge_controller.detach_row(object_id)
        self._attached_object_ids.clear()
        self._tree.clear()

        type_nodes: dict[str, Node] = {}
        for t in self._session.iter_types():
            type_nodes[str(t.id)] = t

        type_ids = set(type_nodes.keys())

        # Build children_of[parent_id] = [child_id, ...] for user-type parents only.
        # Prefer canonical system id, but also accept semantic "extends" ids.
        extends_type_ids: set[str] = {EXTENDS_LINK_TYPE_ID}
        for link_type in self._session.list_link_types():
            if link_type.name.strip().lower() == "extends":
                extends_type_ids.add(str(link_type.id))

        children_of: dict[str, list[str]] = {}
        has_user_parent: set[str] = set()
        for link in self._session.list_links():
            if str(link.link_type_id) in extends_type_ids:
                child_id = str(link.source_node_id)
                parent_id = str(link.target_node_id)
                if child_id in type_ids and parent_id in type_ids:
                    children_of.setdefault(parent_id, []).append(child_id)
                    has_user_parent.add(child_id)

        # Legacy compatibility: some repositories persisted type inheritance
        # via type-node type_id instead of explicit extends edges.
        for child_id, node in type_nodes.items():
            if child_id in has_user_parent:
                continue
            if node.type_id is None:
                continue
            parent_id = str(node.type_id)
            if parent_id not in type_ids or parent_id == child_id:
                continue
            children_of.setdefault(parent_id, []).append(child_id)
            has_user_parent.add(child_id)

        # Name-category fallback: if a type has category matching another type name,
        # treat that as parent when no explicit parent relation exists.
        ids_by_name_key: dict[str, list[str]] = {}
        for tid, node in type_nodes.items():
            ids_by_name_key.setdefault(
                node.name.strip().lower(), []).append(tid)
        for child_id, node in type_nodes.items():
            if child_id in has_user_parent:
                continue
            if is_type(node):
                parent_name_key = as_type(node).category.strip().lower()
            else:
                parent_name_key = node.category.strip().lower()
            if not parent_name_key:
                continue
            parent_ids = ids_by_name_key.get(parent_name_key, [])
            if len(parent_ids) != 1:
                continue
            parent_id = parent_ids[0]
            if parent_id == child_id:
                continue
            children_of.setdefault(parent_id, []).append(child_id)
            has_user_parent.add(child_id)

        for parent_id, child_ids in children_of.items():
            children_of[parent_id] = sorted(set(child_ids))

        root_types = sorted(
            [t for tid, t in type_nodes.items() if tid not in has_user_parent],
            key=lambda n: n.name.lower(),
        )

        def _add(
            parent_widget: QTreeWidget | QTreeWidgetItem,
            node: Node,
            stack: frozenset[str],
        ) -> None:
            tid = str(node.id)
            if tid in stack:
                return  # cycle guard
            item = QTreeWidgetItem(parent_widget, [""])
            item.setData(0, Qt.ItemDataRole.UserRole, tid)
            item.setFlags(_ITEM_FLAGS)
            row = QWidget(self._tree)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 0, 2, 0)
            row_layout.setSpacing(6)
            badge = QValidationBadge(row)
            text_label = QLabel(node.name, row)
            row_layout.addWidget(badge, stretch=0)
            row_layout.addWidget(text_label, stretch=1)
            row_height = max(badge.sizeHint().height(),
                             text_label.sizeHint().height()) + 4
            item.setSizeHint(0, QSize(0, row_height))
            self._tree.setItemWidget(item, 0, row)
            self._badge_controller.attach_row(tid, row, badge)
            self._attached_object_ids.add(tid)
            if tid in children_of:
                new_stack = stack | {tid}
                for child_id in sorted(
                    children_of[tid],
                    key=lambda cid: type_nodes.get(cid).name.lower()
                    if type_nodes.get(cid) is not None
                    else cid,
                ):
                    child = type_nodes.get(child_id)
                    if child is None:
                        continue
                    _add(item, child, new_stack)
                item.setExpanded(True)

        for root in root_types:
            _add(self._tree, root, frozenset())

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QTreeWidget {{ border: 1px solid {EDGE_COLOR}; }}"
            f"QTreeWidget::item:selected {{ background: {EDGE_COLOR}; }}"
        )


__all__ = ["MIME_GRAPH_TYPE_ID", "QGraphTypePalettePanel"]

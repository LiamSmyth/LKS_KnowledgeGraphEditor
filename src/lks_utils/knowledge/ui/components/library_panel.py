"""Searchable library panel for knowledge types and instances."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, QMimeData, QModelIndex, QPoint, QRect, QSize
from PySide6.QtGui import QBrush, QColor, QDrag, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.widgets.q_validation_badge import QValidationBadge
from lks_utils.knowledge.default_theme import (
    COLLAPSE_ARROW_COLOR,
    EDGE_COLOR,
    LIBRARY_TREE_INDENT_PX,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.ui.widgets.validation_badge_row_controller import (
    ValidationBadgeRowController,
)

MIME_KNOWLEDGE_NODE_ID = "application/x-lks-knowledge-node-id"
_TREE_ROW_VERTICAL_PADDING_PX = 4


@dataclass(frozen=True)
class LibraryEntry:
    """One searchable/drag-enabled library row."""

    node_id: str
    name: str
    node_category: str
    role: str


class _KnowledgeDraggableTreeWidget(QTreeWidget):
    """QTreeWidget with drag payload containing node-id and node_category."""

    def drawBranches(  # type: ignore[override]
        self, painter: QPainter, rect: QRect, index: QModelIndex
    ) -> None:
        """Paint expand/collapse arrow using the theme arrow colour."""
        item = self.itemFromIndex(index)
        if item is None or item.childCount() == 0:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(COLLAPSE_ARROW_COLOR)))
        h = 4
        inset = 2
        desired_cx = rect.right() - inset - h
        min_cx = rect.left() + inset + h
        max_cx = rect.right() - inset - h
        cx = max(min_cx, min(desired_cx, max_cx))
        desired_cy = rect.top() + rect.height() // 2
        min_cy = rect.top() + inset + h
        max_cy = rect.bottom() - inset - h
        cy = max(min_cy, min(desired_cy, max_cy))
        if self.isExpanded(index):
            pts = [QPoint(cx - h, cy - h // 2), QPoint(cx +
                                                       h, cy - h // 2), QPoint(cx, cy + h)]
        else:
            pts = [QPoint(cx - h // 2, cy - h), QPoint(cx + h, cy),
                   QPoint(cx - h // 2, cy + h)]
        painter.drawPolygon(pts)
        painter.restore()

    def startDrag(self, supported_actions) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None:
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        node_category = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not isinstance(node_id, str):
            return  # section headers have None data
        mime = QMimeData()
        mime.setData(MIME_KNOWLEDGE_NODE_ID, node_id.encode("utf-8"))
        if isinstance(node_category, str):
            mime.setText(f"{node_id}|{node_category}")
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)


class QKnowledgeLibraryPanel(QWidget):
    """Filterable library with type/instance tabs and drag-source rows."""

    node_open_requested = Signal(str)

    def __init__(
        self,
        session: EditorSession,
        parent: QWidget | None = None,
        tree_indent_px: int = LIBRARY_TREE_INDENT_PX,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._badge_controller = ValidationBadgeRowController(
            session.validation_index, self)
        self._attached_object_ids: set[str] = set()
        self._all_entries: list[LibraryEntry] = []

        self._filter_edit = QLineEdit(self)
        self._filter_edit.setPlaceholderText(
            "Search name / kind / description...")
        self._filter_edit.setToolTip(
            "Filter library entries by name, category, or role."
        )
        self._tabs = QTabWidget(self)
        self._types_list = _KnowledgeDraggableTreeWidget(self)
        self._instances_list = _KnowledgeDraggableTreeWidget(self)
        self._types_list.setHeaderHidden(True)
        self._instances_list.setHeaderHidden(True)
        self._types_list.setColumnCount(1)
        self._instances_list.setColumnCount(1)
        self._types_list.setIndentation(max(0, int(tree_indent_px)))
        self._instances_list.setIndentation(max(0, int(tree_indent_px)))
        self._types_list.setDragEnabled(True)
        self._instances_list.setDragEnabled(True)

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self.refresh()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.remove_listener(self._on_session_change)
        super().closeEvent(event)

    def entries(self) -> list[LibraryEntry]:
        """Return currently visible entries after filter and tab split logic."""
        query = self._filter_edit.text().strip().lower()
        if not query:
            return list(self._all_entries)
        return [
            entry for entry in self._all_entries
            if query in entry.name.lower() or query in entry.node_category.lower() or query in entry.role.lower()
        ]

    def refresh(self) -> None:
        """Refresh entries from the active session."""
        self._all_entries = self._collect_entries()
        self._rebuild_lists()

    def _build_layout(self) -> None:
        self._tabs.addTab(self._types_list, "Types")
        self._tabs.addTab(self._instances_list, "Instances")

        top = QHBoxLayout()
        top.addWidget(QLabel("Filter:", self))
        top.addWidget(self._filter_edit, stretch=1)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        root.addLayout(top)
        root.addWidget(self._tabs, stretch=1)

    def _wire_signals(self) -> None:
        self._filter_edit.textChanged.connect(self._rebuild_lists)
        self._types_list.itemDoubleClicked.connect(
            lambda item, col: self._emit_open_requested(item)
        )
        self._instances_list.itemDoubleClicked.connect(
            lambda item, col: self._emit_open_requested(item)
        )
        self._types_list.itemActivated.connect(
            lambda item, col: self._emit_open_requested(item)
        )
        self._instances_list.itemActivated.connect(
            lambda item, col: self._emit_open_requested(item)
        )
        self._session.add_listener(self._on_session_change)

    def _collect_entries(self) -> list[LibraryEntry]:
        entries: list[LibraryEntry] = []
        for node in self._session.iter_types():
            entries.append(self._entry_from_node(node, role="type"))
        for node in self._session.iter_instances():
            entries.append(self._entry_from_node(node, role="instance"))
        return entries

    def _entry_from_node(self, node: Node, *, role: str) -> LibraryEntry:
        return LibraryEntry(
            node_id=str(node.id),
            name=node.name,
            node_category=node.category,
            role=role,
        )

    def _rebuild_lists(self) -> None:
        from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID

        for object_id in self._attached_object_ids:
            self._badge_controller.detach_row(object_id)
        self._attached_object_ids.clear()

        query = self._filter_edit.text().strip().lower()
        visible = self.entries()
        type_entries = [e for e in visible if e.role == "type"]
        inst_entries = [e for e in visible if e.role == "instance"]

        _leaf_flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        _header_flags = Qt.ItemFlag.ItemIsEnabled
        _header_brush = QBrush(QColor(EDGE_COLOR))

        # --- Types list (hierarchical when no filter, flat when filtered) ---
        self._types_list.clear()
        if query:
            # Flat filtered view.
            for entry in sorted(type_entries, key=lambda e: e.name.lower()):
                item = QTreeWidgetItem(
                    self._types_list,
                    [f"{entry.name} ({entry.node_category})"]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, entry.node_id)
                item.setData(0, Qt.ItemDataRole.UserRole +
                             1, entry.node_category)
                item.setFlags(_leaf_flags)
                self._attach_badge_row(
                    self._types_list, item, entry.node_id, item.text(0))
        else:
            # Hierarchical view by extends inheritance.
            type_map: dict[str, LibraryEntry] = {
                e.node_id: e for e in type_entries}
            all_type_ids = set(type_map.keys())

            type_nodes: dict[str, Node] = {
                str(t.id): t for t in self._session.iter_types()
            }

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
                    if child_id in all_type_ids and parent_id in all_type_ids:
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
                if parent_id not in all_type_ids or parent_id == child_id:
                    continue
                children_of.setdefault(parent_id, []).append(child_id)
                has_user_parent.add(child_id)

            # Name-category fallback: if category matches exactly one type name,
            # treat that type as parent when no explicit parent relation exists.
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

            root_entries = sorted(
                [e for eid, e in type_map.items() if eid not in has_user_parent],
                key=lambda e: e.name.lower(),
            )

            def _add_type(
                parent_widget: QTreeWidget | QTreeWidgetItem,
                entry: LibraryEntry,
                stack: frozenset[str],
            ) -> None:
                if entry.node_id in stack:
                    return
                item = QTreeWidgetItem(
                    parent_widget,
                    [f"{entry.name} ({entry.node_category})"]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, entry.node_id)
                item.setData(0, Qt.ItemDataRole.UserRole +
                             1, entry.node_category)
                item.setFlags(_leaf_flags)
                self._attach_badge_row(
                    self._types_list, item, entry.node_id, item.text(0))
                if entry.node_id in children_of:
                    new_stack = stack | {entry.node_id}
                    children = sorted(
                        [type_map[cid]
                            for cid in children_of[entry.node_id] if cid in type_map],
                        key=lambda e: e.name.lower(),
                    )
                    for child in children:
                        _add_type(item, child, new_stack)
                    item.setExpanded(True)

            for root in root_entries:
                _add_type(self._types_list, root, frozenset())

        # --- Instances list (hierarchical when no filter, flat when filtered) ---
        self._instances_list.clear()
        all_instances = [
            e for e in self._all_entries if e.role == "instance"
        ]
        inst_map: dict[str, LibraryEntry] = {
            e.node_id: e for e in all_instances}
        inst_ids = set(inst_map.keys())

        type_nodes: dict[str, Node] = {
            str(t.id): t for t in self._session.iter_types()}
        type_ids_all = set(type_nodes.keys())

        # Resolve parent relationships using session iter_instances()
        inst_parent_type: dict[str, str] = {}
        inst_parent_inst: dict[str, str] = {}
        for inst in self._session.iter_instances():
            iid = str(inst.id)
            if iid not in inst_map:
                continue
            if inst.type_id is None:
                continue
            pid = str(inst.type_id)
            if pid in type_ids_all:
                inst_parent_type[iid] = pid
            elif pid in inst_ids:
                inst_parent_inst[iid] = pid

        instances_of_type: dict[str, list[str]] = {}
        for iid, tid in inst_parent_type.items():
            instances_of_type.setdefault(tid, []).append(iid)

        instances_of_instance: dict[str, list[str]] = {}
        for iid, piid in inst_parent_inst.items():
            instances_of_instance.setdefault(piid, []).append(iid)

        inst_entry_ids = {e.node_id for e in inst_entries}  # filtered set

        if query:
            # Flat filtered view.
            for entry in sorted(inst_entries, key=lambda e: e.name.lower()):
                item = QTreeWidgetItem(
                    self._instances_list,
                    [f"{entry.name} ({entry.node_category})"]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, entry.node_id)
                item.setData(0, Qt.ItemDataRole.UserRole +
                             1, entry.node_category)
                item.setFlags(_leaf_flags)
                self._attach_badge_row(
                    self._instances_list, item, entry.node_id, item.text(0))
        else:
            ungrouped = [
                e for eid, e in inst_map.items()
                if eid not in inst_parent_type and eid not in inst_parent_inst
            ]

            def _add_inst(
                parent_widget: QTreeWidgetItem,
                entry: LibraryEntry,
                stack: frozenset[str],
            ) -> None:
                if entry.node_id in stack:
                    return
                item = QTreeWidgetItem(
                    parent_widget,
                    [f"{entry.name} ({entry.node_category})"]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, entry.node_id)
                item.setData(0, Qt.ItemDataRole.UserRole +
                             1, entry.node_category)
                item.setFlags(_leaf_flags)
                self._attach_badge_row(
                    self._instances_list, item, entry.node_id, item.text(0))
                if entry.node_id in instances_of_instance:
                    new_stack = stack | {entry.node_id}
                    children = sorted(
                        [inst_map[cid]
                            for cid in instances_of_instance[entry.node_id] if cid in inst_map],
                        key=lambda e: e.name.lower(),
                    )
                    for child in children:
                        _add_inst(item, child, new_stack)
                    item.setExpanded(True)

            def _add_by_category(
                parent_header: QTreeWidgetItem,
                entries: list[LibraryEntry],
            ) -> None:
                """Add entries under parent_header, subdivided by category."""
                by_cat: dict[str, list[LibraryEntry]] = {}
                for e in entries:
                    by_cat.setdefault(e.node_category or "", []).append(e)
                cats = sorted(by_cat.keys(), key=str.lower)
                if len(cats) <= 1:
                    for e in sorted(entries, key=lambda x: x.name.lower()):
                        _add_inst(parent_header, e, frozenset())
                else:
                    for cat in cats:
                        cat_label = cat if cat else "(no category)"
                        cat_hdr = QTreeWidgetItem(parent_header, [cat_label])
                        cat_hdr.setData(0, Qt.ItemDataRole.UserRole, None)
                        cat_hdr.setFlags(_header_flags)
                        cat_hdr.setForeground(0, _header_brush)
                        for e in sorted(by_cat[cat], key=lambda x: x.name.lower()):
                            _add_inst(cat_hdr, e, frozenset())
                        cat_hdr.setExpanded(True)

            for type_id in sorted(
                instances_of_type.keys(),
                key=lambda tid: type_nodes[tid].name.lower(),
            ):
                header = QTreeWidgetItem(self._instances_list, [
                                         type_nodes[type_id].name])
                header.setData(0, Qt.ItemDataRole.UserRole, None)
                header.setFlags(_header_flags)
                header.setForeground(0, _header_brush)
                direct = [
                    inst_map[iid]
                    for iid in instances_of_type[type_id] if iid in inst_map
                ]
                _add_by_category(header, direct)
                header.setExpanded(True)

            if ungrouped:
                ug_header = QTreeWidgetItem(
                    self._instances_list, ["Ungrouped"])
                ug_header.setData(0, Qt.ItemDataRole.UserRole, None)
                ug_header.setFlags(_header_flags)
                ug_header.setForeground(0, _header_brush)
                _add_by_category(ug_header, ungrouped)
                ug_header.setExpanded(True)

    def _emit_open_requested(self, item: QTreeWidgetItem) -> None:
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node_id, str):
            self.node_open_requested.emit(node_id)

    def _on_session_change(self, change_type: str) -> None:
        # "repo_saved" and "dirty_changed" do not change node data, so no
        # tree rebuild is needed for those events.
        if change_type in {"node", "repo_loaded"}:
            self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QTreeWidget {{ border: 1px solid {EDGE_COLOR}; }}"
            f"QTreeWidget::item:selected {{ background: {EDGE_COLOR}; }}"
            # Suppress the Qt "current item" focus rectangle that shows as a
            # border outline on the last-clicked row. This panel is a drag
            # source / browser, not a keyboard-navigated list, so the focus
            # indicator is noise rather than useful affordance.
            f"QTreeWidget::item:focus {{ border: none; outline: 0; }}"
        )

    def _attach_badge_row(
        self,
        tree: QTreeWidget,
        item: QTreeWidgetItem,
        object_id: str,
        text: str,
    ) -> None:
        row = QWidget(tree)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(6)

        badge = QValidationBadge(row)
        label = QLabel(text, row)

        min_row_height = label.fontMetrics().height() + _TREE_ROW_VERTICAL_PADDING_PX
        row.setMinimumHeight(min_row_height)

        row_layout.addWidget(badge, stretch=0)
        row_layout.addWidget(label, stretch=1)
        row_hint = row.sizeHint()
        item.setSizeHint(0, QSize(row_hint.width(), max(
            row_hint.height(), min_row_height)))
        tree.setItemWidget(item, 0, row)
        # Clear built-in item text so it doesn't bleed through behind the row widget.
        item.setText(0, "")

        self._badge_controller.attach_row(object_id, row, badge)
        self._attached_object_ids.add(object_id)


__all__ = [
    "LibraryEntry",
    "MIME_KNOWLEDGE_NODE_ID",
    "QKnowledgeLibraryPanel",
]

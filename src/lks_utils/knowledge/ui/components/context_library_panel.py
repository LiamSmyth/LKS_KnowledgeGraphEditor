"""Context-filtered library panel: types, instances, or link types.

Provides a shared searchable list + CRUD action row so tabs can reuse one
consistent library shell.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, QRect, Qt, Signal, QSize
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.widgets.q_button_bar_base import QButtonBarBase
from lks_utils.gui_qt.widgets.q_validation_badge import QValidationBadge
from lks_utils.gui_qt.widgets import QCollapsibleSection
from lks_utils.knowledge.default_theme import (
    COLLAPSE_ARROW_COLOR,
    EDGE_COLOR,
    LIBRARY_TREE_INDENT_PX,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.operations.delete_safety_analyzer import (
    DeleteImpact,
    IncomingRef,
)
from lks_utils.knowledge.canvas.canvas_io import CanvasIO
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.editor_session_types import SessionChangeEvent
from lks_utils.knowledge.git_service import KnowledgeGitService
from lks_utils.knowledge.links.link_type import LinkType, SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.ui.components.ref_aware_delete_dialog import DeleteResolution, QKnowledgeRefAwareDeleteDialog
from lks_utils.knowledge.ui.widgets.field_widgets import make_square_svg_button


_RESERVED_SYSTEM_LINK_TYPE_IDS: frozenset[str] = frozenset(
    {
        SLOT_REF_LINK_TYPE_ID,
        EXTENDS_LINK_TYPE_ID,
        INSTANCE_OF_LINK_TYPE_ID,
    }
)

_BASE_TEXT_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_TREE_ROW_VERTICAL_PADDING_PX = 8
_TREE_ROW_MIN_HEIGHT_PX = 24


class _ContextLibraryTreeWidget(QTreeWidget):
    """QTreeWidget with theme-colored expand/collapse branch arrows."""

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


def _is_reserved_system_link_type(link_type: LinkType) -> bool:
    return str(link_type.id) in _RESERVED_SYSTEM_LINK_TYPE_IDS


def _analyze_link_type_delete_impact(
    session: EditorSession,
    link_type_ids: list[str] | tuple[str, ...],
) -> DeleteImpact:
    target_ids = tuple(dict.fromkeys(str(link_type_id)
                       for link_type_id in link_type_ids))
    if not target_ids:
        return DeleteImpact(targets=(), incoming_refs=())
    target_id_set = set(target_ids)
    incoming_refs = [
        IncomingRef(
            source_node_id=str(link.id),
            source_slot_path=("link_type_id",),
            target_node_id=str(link.link_type_id),
            is_resolved=True,
        )
        for link in session.list_links()
        if str(link.link_type_id) in target_id_set
    ]
    incoming_refs.sort(
        key=lambda incoming_ref: (
            incoming_ref.target_node_id,
            incoming_ref.source_node_id,
            incoming_ref.source_slot_path,
        )
    )
    return DeleteImpact(targets=target_ids, incoming_refs=tuple(incoming_refs))


def _apply_link_type_delete_resolution(
    repository: Repository,
    impact: DeleteImpact,
    resolution: DeleteResolution,
) -> set[str]:
    _ = resolution
    touched: set[str] = set(impact.targets)
    dependent_link_ids = {
        entry.incoming_ref.source_node_id
        for entry in resolution.entries
    }
    if not dependent_link_ids:
        dependent_link_ids = {
            incoming_ref.source_node_id for incoming_ref in impact.incoming_refs
        }
    for link_id in dependent_link_ids:
        if repository.find_link(link_id) is None:
            continue
        repository.delete_link(link_id)
        touched.add(link_id)
    for link_type_id in impact.targets:
        if repository.find_link_type(link_type_id) is None:
            continue
        repository.delete_link_type(link_type_id)
        touched.add(link_type_id)
    return touched


class QKnowledgeContextLibraryPanel(QWidget):
    """Flat alphabetical list of types, instances, or link types with CRUD.

    Args:
        session: Active editor session.
        context: ``"type"`` to list type-nodes; ``"instance"`` to list
            instance-nodes; ``"link_type"`` to list semantic link types;
            ``"link_instance"`` to list semantic link instances;
            ``"graph_view"`` to list persisted graph views.
    """

    new_item_requested = Signal()  # request to create a new item
    node_load_requested = Signal(str)  # node_id/link_type_id
    node_deleted = Signal(str)  # node_id/link_type_id
    node_renamed = Signal(str, str)  # id, new_name

    def __init__(
        self,
        session: EditorSession,
        context: str,
        parent: QWidget | None = None,
        tree_indent_px: int = LIBRARY_TREE_INDENT_PX,
    ) -> None:
        super().__init__(parent)
        if context not in ("type", "instance", "link_type", "link_instance", "graph_view"):
            raise ValueError(
                f"context must be 'type', 'instance', 'link_type', 'link_instance', or 'graph_view', got {context!r}")
        self._session = session
        self._context = context
        self._nodes: list[Node] = []
        self._link_types: list[LinkType] = []
        self._links: list[LinkInstance] = []
        self._graph_views: list[GraphView] = []
        self._current_open_node_id: str | None = None
        self._node_relpath_by_id: dict[str, str] = {}
        self._git_service_bound: KnowledgeGitService | None = None
        self._git_modified_paths: set[str] = set()
        self._refresh_pending: bool = False
        self._validation_pending: bool = False

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("Search\u2026")
        self._search_edit.setToolTip("Filter items in this library by name.")
        self._tree = _ContextLibraryTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setIndentation(max(0, int(tree_indent_px)))
        if self._context == "link_instance":
            self._tree.setSelectionMode(
                QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self._new_btn = make_square_svg_button(
            "kwb_btn_new.svg",
            tooltip="Create a new item in this context",
            parent=self,
        )
        self._load_btn = make_square_svg_button(
            "kwb_btn_load.svg",
            tooltip="Load the selected item into the editor",
            parent=self,
        )
        self._rename_btn = make_square_svg_button(
            "kwb_btn_rename.svg",
            tooltip="Rename the selected item",
            parent=self,
        )
        self._delete_btn = make_square_svg_button(
            "kwb_btn_delete.svg",
            tooltip="Delete the selected item",
            parent=self,
        )
        self._new_btn.setToolTip("Create a new item in this context")
        self._load_btn.setToolTip("Load the selected item into the editor")
        self._rename_btn.setToolTip("Rename the selected item")
        self._delete_btn.setToolTip("Delete the selected item")
        self._load_btn.setEnabled(False)
        self._rename_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self.refresh()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.remove_change_listener(self._on_session_change)
        self._session.validation_index.validation_changed.disconnect(
            self._on_validation_changed
        )
        if self._git_service_bound is not None:
            self._git_service_bound.git_status_changed.disconnect(
                self._on_git_status_changed
            )
        super().closeEvent(event)

    def selected_node(self) -> Node | None:
        """Return the currently selected node for type/instance contexts."""
        if self._context == "link_type":
            return None
        if self._context == "link_instance":
            return None
        item = self._tree.currentItem()
        if item is None:
            return None
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(node_id, str):
            return None
        try:
            return self._session.get_node(node_id)
        except KeyError:
            return None

    def selected_link_type(self) -> LinkType | None:
        """Return the selected link type for ``link_type`` context."""
        if self._context != "link_type":
            return None
        item = self._tree.currentItem()
        if item is None:
            return None
        link_type_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(link_type_id, str):
            return None
        try:
            return self._session.get_link_type(link_type_id)
        except KeyError:
            return None

    def selected_graph_view(self) -> GraphView | None:
        """Return the selected graph view for ``graph_view`` context."""
        if self._context != "graph_view":
            return None
        item = self._tree.currentItem()
        if item is None:
            return None
        view_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(view_id, str):
            return None
        try:
            return CanvasIO.load_graph_view(self._session._io, view_id)  # noqa: SLF001
        except KeyError:
            return None

    def selected_link_instance(self) -> LinkInstance | None:
        """Return the selected link instance for ``link_instance`` context."""
        if self._context != "link_instance":
            return None
        item = self._tree.currentItem()
        if item is None:
            return None
        link_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(link_id, str):
            return None
        for link in self._session.list_links():
            if str(link.id) == link_id:
                return link
        return None

    def selected_link_instance_ids(self) -> list[str]:
        """Return selected link instance IDs for ``link_instance`` context."""
        if self._context != "link_instance":
            return []
        ids: list[str] = []
        for item in self._tree.selectedItems():
            link_id = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(link_id, str):
                ids.append(link_id)
        return sorted(set(ids))

    def refresh(self) -> None:
        """Reload entries from the session and apply the current filter."""
        self._rebind_git_service()
        self._node_relpath_by_id = self._load_node_relpaths()
        if self._context == "type":
            self._nodes = sorted(self._session.iter_types(),
                                 key=lambda n: n.name.lower())
            self._link_types = []
            self._links = []
            self._graph_views = []
        elif self._context == "instance":
            self._nodes = sorted(
                self._session.iter_instances(), key=lambda n: n.name.lower())
            self._link_types = []
            self._links = []
            self._graph_views = []
        elif self._context == "link_instance":
            self._nodes = []
            self._link_types = []
            self._links = sorted(self._session.list_links(),
                                 key=lambda lk: str(lk.id))
            self._graph_views = []
        elif self._context == "graph_view":
            self._nodes = []
            self._link_types = []
            self._links = []
            try:
                self._graph_views = sorted(
                    CanvasIO.list_graph_views(self._session._io),  # noqa: SLF001
                    key=lambda gv: gv.name.lower(),
                )
            except ValueError:
                self._graph_views = []
        else:
            self._nodes = []
            self._link_types = sorted(
                self._session.list_link_types(),
                key=lambda lt: lt.name.lower(),
            )
            self._links = []
            self._graph_views = []
        self._rebuild_list()

    def set_current_open_node(self, node_id: str | None) -> None:
        """Mark which node is currently open in the editor for bold emphasis."""
        self._current_open_node_id = node_id
        self._rebuild_list()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        btn_bar = QButtonBarBase(alignment="left")
        btn_bar.add_button(self._new_btn)
        btn_bar.add_button(self._load_btn)
        btn_bar.add_button(self._rename_btn)
        btn_bar.add_button(self._delete_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        if self._context == "type":
            label_text = "Types"
        elif self._context == "instance":
            label_text = "Instances"
        elif self._context == "graph_view":
            label_text = "Graph Views"
        elif self._context == "link_instance":
            label_text = "Link Instances"
        else:
            label_text = "Link Types"
        self._section = QCollapsibleSection(
            label_text,
            initially_expanded=True,
            fill_vertical=True,
            parent=self,
        )
        self._section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        content = self._section.content_layout
        content.setContentsMargins(6, 6, 6, 6)
        content.setSpacing(5)
        content.addWidget(self._search_edit)
        content.addWidget(self._tree, stretch=1)
        content.addWidget(btn_bar)
        root.addWidget(self._section, stretch=1)

    def _wire_signals(self) -> None:
        self._search_edit.textChanged.connect(self._rebuild_list)
        self._tree.currentItemChanged.connect(
            lambda curr, prev: self._sync_button_state())
        self._tree.itemDoubleClicked.connect(lambda item, col: self._on_load())
        self._new_btn.clicked.connect(self.new_item_requested.emit)
        self._load_btn.clicked.connect(self._on_load)
        self._rename_btn.clicked.connect(self._on_rename)
        self._delete_btn.clicked.connect(self._on_delete)
        self._session.add_change_listener(self._on_session_change)
        self._session.validation_index.validation_changed.connect(
            self._on_validation_changed
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QLineEdit {{ background: {SCENE_BACKGROUND_COLOR}; border: 1px solid {EDGE_COLOR};"
            f" color: {NODE_TEXT_COLOR}; padding: 3px 6px; min-height: 24px; }}"
            f"QTreeWidget {{ background: {SCENE_BACKGROUND_COLOR}; border: 1px solid {EDGE_COLOR}; }}"
            f"QTreeWidget::item {{ min-height: {_TREE_ROW_MIN_HEIGHT_PX}px; }}"
            f"QTreeWidget::item:selected {{ background: {EDGE_COLOR}; }}"
            f"QPushButton:disabled {{ color: #555; }}"
        )

    def _rebuild_list(self) -> None:
        from lks_utils.knowledge.links.link_types.link_type_system import (
            EXTENDS_LINK_TYPE_ID,
            INSTANCE_OF_LINK_TYPE_ID as _IOLT,
        )

        query = self._search_edit.text().strip().lower()
        # Snapshot current selection for post-rebuild restoration.
        prev_item = self._tree.currentItem()
        prev_selected_id: str | None = (
            prev_item.data(0, Qt.ItemDataRole.UserRole)
            if prev_item is not None
            else None
        )
        expanded_state = _snapshot_tree_expansion(self._tree)
        self._tree.clear()

        _leaf_flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        _header_flags = Qt.ItemFlag.ItemIsEnabled
        _header_brush = QBrush(QColor(EDGE_COLOR))

        if self._context == "link_type":
            # Flat alphabetical list — no hierarchy.
            for link_type in self._link_types:
                dirty_suffix = ""
                is_locked = link_type.is_system or _is_reserved_system_link_type(
                    link_type)
                suffix = " [system]" if is_locked else ""
                display_text = f"{link_type.name}{dirty_suffix}{suffix}"
                if query and query not in display_text.lower():
                    continue
                item = QTreeWidgetItem(self._tree, [display_text])
                item.setData(0, Qt.ItemDataRole.UserRole, str(link_type.id))
                item.setData(0, _BASE_TEXT_ROLE, display_text)
                if is_locked:
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    item.setForeground(0, _header_brush)
                font = item.font(0)
                font.setBold(str(link_type.id) == self._current_open_node_id)
                item.setFont(0, font)
                self._apply_validation_style(item)

        elif self._context == "link_instance":
            # Group link instances by link type (subsections), then alphabetically within each.
            node_names: dict[str, str] = {
                str(node.id): node.name for node in self._session.list_nodes()
            }
            link_type_names: dict[str, str] = {
                str(link_type.id): link_type.name
                for link_type in self._session.list_link_types()
            }
            link_type_map: dict[str, LinkType] = {
                str(lt.id): lt for lt in self._session.list_link_types()
            }

            # Build links grouped by link_type_id
            links_by_type: dict[str, list[LinkInstance]] = {}
            for link in self._links:
                link_type_id = str(link.link_type_id)
                links_by_type.setdefault(link_type_id, []).append(link)

            # Sort link types by name
            sorted_link_type_ids = sorted(
                links_by_type.keys(),
                key=lambda lt_id: link_type_names.get(lt_id, lt_id).lower(),
            )

            for link_type_id in sorted_link_type_ids:
                link_type_name = link_type_names.get(
                    link_type_id, link_type_id)

                # Collect instances for this link type that match the query
                matching_links: list[tuple[LinkInstance, str]] = []
                for link in links_by_type[link_type_id]:
                    link_id = str(link.id)
                    source = node_names.get(
                        str(link.source_node_id), str(link.source_node_id))
                    target = node_names.get(
                        str(link.target_node_id), str(link.target_node_id))
                    display_text = f"{source} -> {target}"
                    full_display = f"{display_text} [{link_type_name}]"

                    if query and query not in full_display.lower() and query not in link_id.lower():
                        continue
                    matching_links.append((link, display_text))

                # Only create section if there are matching links
                if not matching_links:
                    continue

                # Create section header for this link type
                header_text = link_type_name
                header_item = QTreeWidgetItem(self._tree, [header_text])
                header_item.setData(0, Qt.ItemDataRole.UserRole, None)
                header_item.setFlags(_header_flags)
                header_item.setForeground(0, _header_brush)
                font = header_item.font(0)
                font.setBold(True)
                header_item.setFont(0, font)
                header_item.setExpanded(True)

                # Sort matching links alphabetically by display text
                matching_links.sort(key=lambda lk_pair: lk_pair[1].lower())

                # Add link instances under this section
                lt_is_system = link_type_id in _RESERVED_SYSTEM_LINK_TYPE_IDS
                _system_brush = QBrush(QColor(EDGE_COLOR))
                for link, display_text in matching_links:
                    link_id = str(link.id)
                    item = QTreeWidgetItem(header_item, [display_text])
                    item.setData(0, Qt.ItemDataRole.UserRole, link_id)
                    item.setData(0, _BASE_TEXT_ROLE, display_text)
                    item.setFlags(_leaf_flags)
                    font = item.font(0)
                    font.setBold(link_id == self._current_open_node_id)
                    item.setFont(0, font)
                    if lt_is_system:
                        item.setForeground(0, _system_brush)
                        item.setToolTip(
                            0,
                            "This is a backend-managed system link — "
                            "it cannot be deleted from the UI.",
                        )
                    self._apply_validation_style(item)

        elif self._context == "graph_view":
            for graph_view in self._graph_views:
                display_text = graph_view.name
                if query and query not in display_text.lower():
                    continue
                item = QTreeWidgetItem(self._tree, [display_text])
                item.setData(0, Qt.ItemDataRole.UserRole, str(graph_view.id))
                item.setData(0, _BASE_TEXT_ROLE, display_text)
                item.setFlags(_leaf_flags)
                font = item.font(0)
                font.setBold(str(graph_view.id) == self._current_open_node_id)
                item.setFont(0, font)
                self._apply_validation_style(item)

        elif self._context == "type":
            # Inheritance tree: root types at top level, subtypes nested under parent.
            node_map: dict[str, Node] = {str(n.id): n for n in self._nodes}
            type_ids = set(node_map.keys())

            children_of: dict[str, list[str]] = {}
            has_user_parent: set[str] = set()
            for link in self._session.list_links():
                if str(link.link_type_id) == EXTENDS_LINK_TYPE_ID:
                    child_id = str(link.source_node_id)
                    parent_id = str(link.target_node_id)
                    if child_id in type_ids and parent_id in type_ids:
                        children_of.setdefault(parent_id, []).append(child_id)
                        has_user_parent.add(child_id)

            # Legacy compatibility: some repositories persisted type inheritance
            # via type-node type_id instead of explicit extends edges.
            for child_id, node in node_map.items():
                if child_id in has_user_parent:
                    continue
                if node.type_id is None:
                    continue
                parent_id = str(node.type_id)
                if parent_id not in type_ids or parent_id == child_id:
                    continue
                children_of.setdefault(parent_id, []).append(child_id)
                has_user_parent.add(child_id)

            for parent_id, child_ids in children_of.items():
                children_of[parent_id] = sorted(set(child_ids))

            def _type_display(node: Node) -> str:
                dirty_suffix = ""
                if is_type(node):
                    tv = as_type(node)
                    return f"{node.name}{dirty_suffix}  ({tv.category})"
                return f"{node.name}{dirty_suffix}"

            def _add_type(
                parent_widget: QTreeWidget | QTreeWidgetItem,
                node: Node,
                stack: frozenset[str],
            ) -> None:
                tid = str(node.id)
                if tid in stack:
                    return
                display_text = _type_display(node)
                if query and query not in display_text.lower():
                    # Check if any descendent matches before skipping entirely.
                    if not _any_descendant_matches(tid, query, stack | {tid}):
                        return
                item = QTreeWidgetItem(parent_widget, [display_text])
                item.setData(0, Qt.ItemDataRole.UserRole, tid)
                item.setData(0, _BASE_TEXT_ROLE, display_text)
                item.setFlags(_leaf_flags)
                font = item.font(0)
                font.setBold(tid == self._current_open_node_id)
                item.setFont(0, font)
                self._apply_validation_style(item)
                if tid in children_of:
                    new_stack = stack | {tid}
                    for child_id in sorted(
                        children_of[tid],
                        key=lambda cid: node_map.get(cid).name.lower(
                        ) if node_map.get(cid) is not None else cid,
                    ):
                        child_node = node_map.get(child_id)
                        if child_node is None:
                            continue
                        _add_type(item, child_node, new_stack)
                    item.setExpanded(True)

            def _any_descendant_matches(
                tid: str, q: str, stack: frozenset[str]
            ) -> bool:
                for cid in children_of.get(tid, []):
                    if cid in stack:
                        continue
                    node = node_map.get(cid)
                    if node is None:
                        continue
                    if q in _type_display(node).lower():
                        return True
                    if _any_descendant_matches(cid, q, stack | {cid}):
                        return True
                return False

            root_types = sorted(
                [n for tid, n in node_map.items() if tid not in has_user_parent],
                key=lambda n: n.name.lower(),
            )
            for root in root_types:
                _add_type(self._tree, root, frozenset())

        else:  # instance context
            # Group by type (section headers), then nest instances-of-instances.
            instance_ids: set[str] = {str(n.id) for n in self._nodes}
            type_nodes: dict[str, Node] = {}
            for t in self._session.iter_types():
                type_nodes[str(t.id)] = t
            type_ids_all = set(type_nodes.keys())

            instance_parent_type: dict[str, str] = {}
            instance_parent_inst: dict[str, str] = {}
            inst_map: dict[str, Node] = {str(n.id): n for n in self._nodes}
            for inst_id, inst in inst_map.items():
                if inst.type_id is None:
                    continue
                pid = str(inst.type_id)
                if pid in type_ids_all:
                    instance_parent_type[inst_id] = pid
                elif pid in instance_ids:
                    instance_parent_inst[inst_id] = pid

            instances_of_type: dict[str, list[str]] = {}
            for iid, tid in instance_parent_type.items():
                instances_of_type.setdefault(tid, []).append(iid)

            instances_of_instance: dict[str, list[str]] = {}
            for iid, piid in instance_parent_inst.items():
                instances_of_instance.setdefault(piid, []).append(iid)

            ungrouped = [
                n for nid, n in inst_map.items()
                if nid not in instance_parent_type and nid not in instance_parent_inst
            ]

            def _add_inst(
                parent_widget: QTreeWidgetItem,
                inst: Node,
                stack: frozenset[str],
            ) -> None:
                inst_id = str(inst.id)
                if inst_id in stack:
                    return
                if query and query not in inst.name.lower():
                    if not _any_inst_descendant_matches(inst_id, query, stack | {inst_id}):
                        return
                dirty_suffix = ""
                item = QTreeWidgetItem(
                    parent_widget, [f"{inst.name}{dirty_suffix}"])
                item.setData(0, Qt.ItemDataRole.UserRole, inst_id)
                item.setData(0, _BASE_TEXT_ROLE, f"{inst.name}{dirty_suffix}")
                item.setFlags(_leaf_flags)
                font = item.font(0)
                font.setBold(inst_id == self._current_open_node_id)
                item.setFont(0, font)
                self._apply_validation_style(item)
                if inst_id in instances_of_instance:
                    new_stack = stack | {inst_id}
                    for child_id in sorted(
                        instances_of_instance[inst_id],
                        key=lambda cid: inst_map.get(cid).name.lower(
                        ) if inst_map.get(cid) is not None else cid,
                    ):
                        child_node = inst_map.get(child_id)
                        if child_node is None:
                            continue
                        _add_inst(item, child_node, new_stack)

            def _any_inst_descendant_matches(
                inst_id: str, q: str, stack: frozenset[str]
            ) -> bool:
                for cid in instances_of_instance.get(inst_id, []):
                    if cid in stack:
                        continue
                    node = inst_map.get(cid)
                    if node is None:
                        continue
                    if q in node.name.lower():
                        return True
                    if _any_inst_descendant_matches(cid, q, stack | {cid}):
                        return True
                return False

            def _type_header_has_match(type_id: str, q: str) -> bool:
                """Return True if any instance under this type header matches the query."""
                for iid in instances_of_type.get(type_id, []):
                    node = inst_map.get(iid)
                    if node and q in node.name.lower():
                        return True
                    if _any_inst_descendant_matches(iid, q, frozenset()):
                        return True
                return False

            def _instances_have_match(instances: list[Node]) -> bool:
                if not query:
                    return True
                return any(
                    query in n.name.lower()
                    or _any_inst_descendant_matches(str(n.id), query, frozenset())
                    for n in instances
                )

            for type_id in sorted(
                instances_of_type.keys(),
                key=lambda tid: type_nodes[tid].name.lower(),
            ):
                if query and not _type_header_has_match(type_id, query):
                    continue
                type_node = type_nodes[type_id]
                header = QTreeWidgetItem(self._tree, [type_node.name])
                header.setData(0, Qt.ItemDataRole.UserRole, None)
                header.setFlags(_header_flags)
                header.setForeground(0, _header_brush)
                direct_insts = [
                    inst_map[iid]
                    for iid in instances_of_type[type_id] if iid in inst_map
                ]
                for inst in sorted(direct_insts, key=lambda n: n.name.lower()):
                    if not _instances_have_match([inst]):
                        continue
                    _add_inst(header, inst, frozenset())

            if ungrouped:
                ug_visible = [
                    n for n in ungrouped if not query or query in n.name.lower()]
                if ug_visible:
                    ug_header = QTreeWidgetItem(self._tree, ["Ungrouped"])
                    ug_header.setData(0, Qt.ItemDataRole.UserRole, None)
                    ug_header.setFlags(_header_flags)
                    ug_header.setForeground(0, _header_brush)
                    for inst in sorted(ug_visible, key=lambda n: n.name.lower()):
                        _add_inst(ug_header, inst, frozenset())

        _restore_tree_expansion(self._tree, expanded_state)

        # Restore prior selection.
        restore_id = prev_selected_id or self._current_open_node_id
        if restore_id is not None:
            found = _find_tree_item(self._tree, restore_id)
            if found is not None:
                self._tree.setCurrentItem(found)
        self._sync_button_state()

    def _sync_button_state(self) -> None:
        item = self._tree.currentItem()
        has_selection = item is not None and isinstance(
            item.data(0, Qt.ItemDataRole.UserRole), str
        )
        can_load = has_selection
        can_rename = has_selection
        if self._context == "link_type" and has_selection:
            selected = self.selected_link_type()
            has_selection = selected is not None
            can_load = has_selection and not (
                selected.is_system or _is_reserved_system_link_type(selected)
            )
            can_rename = can_load
        elif self._context == "graph_view":
            can_load = has_selection
            can_rename = has_selection
        elif self._context == "link_instance":
            selected_ids = self.selected_link_instance_ids()
            has_selection = bool(selected_ids)
            can_load = len(selected_ids) == 1
            can_rename = False
        self._load_btn.setEnabled(can_load)
        self._rename_btn.setEnabled(can_rename)
        if self._context == "link_type":
            selected = self.selected_link_type()
            can_delete = (
                selected is not None
                and not selected.is_system
                and not _is_reserved_system_link_type(selected)
            )
            self._delete_btn.setEnabled(can_delete)
        elif self._context == "graph_view":
            self._delete_btn.setEnabled(has_selection)
        elif self._context == "link_instance":
            if has_selection:
                links_by_id = {
                    str(link.id): link
                    for link in self._links
                }
                can_delete = not any(
                    str(links_by_id[lid].link_type_id) in _RESERVED_SYSTEM_LINK_TYPE_IDS
                    for lid in selected_ids
                    if lid in links_by_id
                )
                self._delete_btn.setEnabled(can_delete)
            else:
                self._delete_btn.setEnabled(False)
        else:
            self._delete_btn.setEnabled(has_selection)

    def _on_validation_changed(self, changed_ids_obj: object) -> None:
        if not isinstance(changed_ids_obj, set):
            return
        changed_ids = {str(value) for value in changed_ids_obj}
        if not changed_ids:
            return
        if not self.isVisible():
            self._validation_pending = True
            return

        def _walk(parent: QTreeWidget | QTreeWidgetItem) -> None:
            count = (
                parent.topLevelItemCount()
                if isinstance(parent, QTreeWidget)
                else parent.childCount()
            )
            for i in range(count):
                item = (
                    parent.topLevelItem(i)
                    if isinstance(parent, QTreeWidget)
                    else parent.child(i)
                )
                if item is None:
                    continue
                object_id = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(object_id, str) and object_id in changed_ids:
                    self._apply_validation_style(item)
                _walk(item)

        _walk(self._tree)

    def _apply_validation_style(self, item: QTreeWidgetItem) -> None:
        object_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(object_id, str):
            return

        base_text_obj = item.data(0, _BASE_TEXT_ROLE)
        if not isinstance(base_text_obj, str):
            base_text_obj = item.text(0)
            item.setData(0, _BASE_TEXT_ROLE, base_text_obj)

        rel_path = self._node_relpath_by_id.get(object_id)
        is_modified = (
            rel_path is not None
            and self._git_service_bound is not None
            and self._git_service_bound.is_modified(rel_path)
        )

        display_text = f"{base_text_obj} *" if is_modified else base_text_obj
        status = self._session.validation_index.status_for(object_id)
        if status.is_valid:
            item.setText(0, display_text)
            if is_modified:
                item.setToolTip(0, "Modified since HEAD")
            else:
                item.setToolTip(0, "")
            item.setForeground(0, QBrush(QColor(NODE_TEXT_COLOR)))
            self._apply_badge_item_widget(
                item,
                status,
                NODE_TEXT_COLOR,
                display_text=display_text,
            )
            return

        invalid_display_text = f"[!] {display_text}"
        item.setText(0, invalid_display_text)
        item.setForeground(0, QBrush(QColor(VALIDATION_ERROR_TEXT)))
        reasons = "\n".join(status.reasons)
        if is_modified:
            reasons = f"{reasons}\nModified since HEAD"
        item.setToolTip(0, reasons)
        self._apply_badge_item_widget(
            item,
            status,
            VALIDATION_ERROR_TEXT,
            display_text=invalid_display_text,
        )

    def _apply_badge_item_widget(
        self,
        item: QTreeWidgetItem,
        status,
        text_color: str,
        display_text: str,
    ) -> None:
        row = QWidget(self._tree)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 0, 4, 0)
        row_layout.setSpacing(6)

        badge = QValidationBadge(row)
        badge.set_status(status)

        label = QLabel(display_text, row)
        label.setFont(item.font(0))
        label.setStyleSheet(f"color: {text_color};")
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter |
                           Qt.AlignmentFlag.AlignLeft)
        label.setToolTip(item.toolTip(0))
        row.setToolTip(item.toolTip(0))

        # Preserve normal tree-item hit testing: clicking the rendered row still
        # selects the backing QTreeWidgetItem and updates action-button state.
        row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        badge.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        min_row_height = max(
            _TREE_ROW_MIN_HEIGHT_PX,
            label.fontMetrics().height() + _TREE_ROW_VERTICAL_PADDING_PX,
            badge.sizeHint().height() + _TREE_ROW_VERTICAL_PADDING_PX,
        )
        row.setFixedHeight(min_row_height)

        row_layout.addWidget(badge, stretch=0)
        row_layout.addWidget(label, stretch=1)
        row_hint = row.sizeHint()
        item.setSizeHint(0, QSize(row_hint.width(), min_row_height))
        self._tree.setItemWidget(item, 0, row)
        # Clear built-in item text so it doesn't bleed through behind the row widget.
        item.setText(0, "")

    def showEvent(self, event) -> None:  # type: ignore[override]
        if self._refresh_pending or self._validation_pending:
            self._refresh_pending = False
            self._validation_pending = False
            self.refresh()
        super().showEvent(event)

    def _change_affects_context(self, change_type: str) -> bool:
        if self._context == "type":
            return change_type in {"node", "link", "repo_loaded"}
        if self._context == "instance":
            return change_type in {"node", "repo_loaded"}
        if self._context == "link_instance":
            return change_type in {"link", "node", "link_type", "repo_loaded"}
        if self._context == "link_type":
            return change_type in {"link_type", "repo_loaded"}
        return change_type in {"graph_view", "repo_loaded"}

    def _on_session_change(self, event: SessionChangeEvent | str) -> None:
        event_obj = event if isinstance(
            event, SessionChangeEvent) else SessionChangeEvent(change_type=event)
        change_type = event_obj.change_type
        if not self._change_affects_context(change_type):
            return
        if change_type == "node" and not self._node_change_affects_context(event_obj):
            return
        if self.isVisible():
            self._refresh_pending = False
            self.refresh()
            return
        self._refresh_pending = True

    def _node_change_affects_context(self, event: SessionChangeEvent) -> bool:
        touched_ids = event.touched_ids
        if touched_ids is None:
            return True
        if self._context == "type":
            type_ids = {str(node.id) for node in self._session.iter_types()}
            return bool(type_ids.intersection(touched_ids))
        if self._context == "instance":
            instance_ids = {str(node.id)
                            for node in self._session.iter_instances()}
            return bool(instance_ids.intersection(touched_ids))
        if self._context == "link_type":
            link_type_ids = {str(link_type.id)
                             for link_type in self._session.list_link_types()}
            return bool(link_type_ids.intersection(touched_ids))
        # link_instance and graph_view contexts can be impacted indirectly by
        # node payload edits and keep coarse behavior until dedicated ids are emitted.
        return True

    def _on_git_status_changed(self, modified_paths_obj: object) -> None:
        if not isinstance(modified_paths_obj, set):
            return
        self._git_modified_paths = {
            str(path).replace("\\", "/") for path in modified_paths_obj
        }

        def _walk(parent: QTreeWidget | QTreeWidgetItem) -> None:
            count = (
                parent.topLevelItemCount()
                if isinstance(parent, QTreeWidget)
                else parent.childCount()
            )
            for i in range(count):
                item = (
                    parent.topLevelItem(i)
                    if isinstance(parent, QTreeWidget)
                    else parent.child(i)
                )
                if item is None:
                    continue
                self._apply_validation_style(item)
                _walk(item)

        _walk(self._tree)

    def _load_node_relpaths(self) -> dict[str, str]:
        root = self._session.repository_root
        if root is None:
            return {}
        index_path = Path(root) / "index.json"
        if not index_path.exists():
            return {}
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        raw_nodes = payload.get("nodes")
        if not isinstance(raw_nodes, dict):
            return {}

        relpaths: dict[str, str] = {}
        for node_id, node_info in raw_nodes.items():
            if not isinstance(node_id, str) or not isinstance(node_info, dict):
                continue
            raw_path = node_info.get("path")
            if isinstance(raw_path, str) and raw_path:
                relpaths[node_id] = raw_path.replace("\\", "/")
        return relpaths

    def _rebind_git_service(self) -> None:
        service = self._session.git_service
        if service is self._git_service_bound:
            if service is not None:
                self._git_modified_paths = set(
                    service.status().all_modified_paths)
            return
        if self._git_service_bound is not None:
            self._git_service_bound.git_status_changed.disconnect(
                self._on_git_status_changed
            )
        self._git_service_bound = service
        if service is None:
            self._git_modified_paths = set()
            return
        service.git_status_changed.connect(self._on_git_status_changed)
        self._git_modified_paths = set(service.status().all_modified_paths)

    def _on_load(self) -> None:
        if self._context == "link_type":
            link_type = self.selected_link_type()
            if link_type is None:
                return
            if link_type.is_system or _is_reserved_system_link_type(link_type):
                return
            self.node_load_requested.emit(str(link_type.id))
            return
        if self._context == "graph_view":
            graph_view = self.selected_graph_view()
            if graph_view is None:
                return
            self.node_load_requested.emit(str(graph_view.id))
            return
        if self._context == "link_instance":
            selected_ids = self.selected_link_instance_ids()
            if len(selected_ids) != 1:
                return
            self.node_load_requested.emit(selected_ids[0])
            return
        node = self.selected_node()
        if node is None:
            return
        self.node_load_requested.emit(str(node.id))

    def _on_rename(self) -> None:
        if self._context == "link_type":
            link_type = self.selected_link_type()
            if link_type is None:
                return
            if link_type.is_system or _is_reserved_system_link_type(link_type):
                QMessageBox.warning(
                    self,
                    "Cannot Rename",
                    "System link types cannot be renamed.",
                )
                return
            new_name, ok = QInputDialog.getText(
                self,
                "Rename",
                "New name:",
                text=link_type.name,
            )
            if not ok or not new_name.strip() or new_name.strip() == link_type.name:
                return
            new_name = new_name.strip()
            updated = link_type.model_copy(update={"name": new_name})
            result = self._session._io.upsert_link_type(updated)  # noqa: SLF001
            if not result.ok:
                QMessageBox.warning(
                    self,
                    "Rename Failed",
                    result.error_message or "Unable to rename link type.",
                )
                return
            self._session.notify_io_mutation("link_type")
            self.node_renamed.emit(str(link_type.id), new_name)
            return

        if self._context == "graph_view":
            graph_view = self.selected_graph_view()
            if graph_view is None:
                return
            new_name, ok = QInputDialog.getText(
                self,
                "Rename",
                "New name:",
                text=graph_view.name,
            )
            if not ok or not new_name.strip() or new_name.strip() == graph_view.name:
                return
            new_name = new_name.strip()
            unique_name = CanvasIO.ensure_unique_graph_view_name(  # noqa: SLF001
                self._session._io,
                new_name,
                exclude_id=str(graph_view.id),
            )
            if unique_name != new_name:
                QMessageBox.information(
                    self,
                    "Rename",
                    f"A graph view named '{new_name}' already exists. Using '{unique_name}'.",
                )
            new_name = unique_name
            updated = replace(graph_view, name=new_name)
            try:
                CanvasIO.save_graph_view(self._session._io, updated)  # noqa: SLF001
                self._session.notify_repository_mutated("graph_view")
            except ValueError:
                return
            self.node_renamed.emit(str(graph_view.id), new_name)
            return

        node = self.selected_node()
        if node is None:
            return
        new_name, ok = QInputDialog.getText(
            self,
            "Rename",
            "New name:",
            text=node.name,
        )
        if not ok or not new_name.strip() or new_name.strip() == node.name:
            return
        new_name = new_name.strip()
        updated = node.model_copy(
            update={"name": new_name, "rev": node.rev + 1})
        result = self._session._io.upsert_node(updated)  # noqa: SLF001
        if not result.ok:
            QMessageBox.warning(
                self,
                "Rename Failed",
                result.error_message or "Unable to rename node.",
            )
            return
        self._session.notify_io_mutation("node")
        self.node_renamed.emit(str(node.id), new_name)

    def _on_delete(self) -> None:
        if self._context == "link_type":
            link_type = self.selected_link_type()
            if link_type is None:
                return
            if link_type.is_system or _is_reserved_system_link_type(link_type):
                QMessageBox.warning(
                    self,
                    "Cannot Delete",
                    "System link types cannot be deleted.",
                )
                return
            impact = _analyze_link_type_delete_impact(
                self._session, [str(link_type.id)])
            if impact.is_safe:
                result = self._session._io.delete_link_type_cascade(  # noqa: SLF001
                    str(link_type.id)
                )
                if not result.ok:
                    QMessageBox.warning(
                        self,
                        "Delete Failed",
                        result.error_message or "Unable to delete link type.",
                    )
                    return
                self._session.notify_io_mutation("link_type")
                self.node_deleted.emit(str(link_type.id))
                return
            delete_dialog = QKnowledgeRefAwareDeleteDialog(
                impact,
                self._session,
                parent=self,
                entity_kind="link_type",
                allow_replace=False,
                apply_resolution=_apply_link_type_delete_resolution,
            )
            if delete_dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.node_deleted.emit(str(link_type.id))
            return

        if self._context == "graph_view":
            graph_view = self.selected_graph_view()
            if graph_view is None:
                return
            reply = QMessageBox.question(
                self,
                "Delete Graph View",
                f"Delete graph view '{graph_view.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    CanvasIO.delete_graph_view(self._session._io, str(graph_view.id))  # noqa: SLF001
                    self._session.notify_repository_mutated("graph_view")
                except ValueError:
                    return
                self.node_deleted.emit(str(graph_view.id))
            return

        if self._context == "link_instance":
            selected_ids = self.selected_link_instance_ids()
            if not selected_ids:
                return
            reply = QMessageBox.question(
                self,
                "Delete Link Instances",
                f"Delete {len(selected_ids)} selected link instance(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            for link_id in selected_ids:
                result = self._session._io.remove_link(link_id)  # noqa: SLF001
                if not result.ok:
                    QMessageBox.warning(
                        self,
                        "Delete Failed",
                        result.error_message or f"Unable to delete link: {link_id}",
                    )
                    return
            self._session.notify_io_mutation("link")
            for link_id in selected_ids:
                self.node_deleted.emit(link_id)
            return

        node = self.selected_node()
        if node is None:
            return
        impact = self._session._io.preview_delete_nodes([str(node.id)])  # noqa: SLF001
        if impact.is_safe:
            delete_dialog = QKnowledgeRefAwareDeleteDialog(
                impact, self._session, parent=self
            )
            delete_dialog._on_safe_delete()  # noqa: SLF001
            self.node_deleted.emit(str(node.id))
            return

        delete_dialog = QKnowledgeRefAwareDeleteDialog(
            impact, self._session, parent=self
        )
        if delete_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.node_deleted.emit(str(node.id))


def _find_tree_item(
    tree: QTreeWidget, node_id: str
) -> QTreeWidgetItem | None:
    """Recursively find a tree item whose UserRole data matches ``node_id``."""

    def _search(parent: QTreeWidget | QTreeWidgetItem) -> QTreeWidgetItem | None:
        count = (
            parent.topLevelItemCount()
            if isinstance(parent, QTreeWidget)
            else parent.childCount()
        )
        for i in range(count):
            it = (
                parent.topLevelItem(i)
                if isinstance(parent, QTreeWidget)
                else parent.child(i)
            )
            if it is None:
                continue
            if it.data(0, Qt.ItemDataRole.UserRole) == node_id:
                return it
            result = _search(it)
            if result is not None:
                return result
        return None

    return _search(tree)


def _snapshot_tree_expansion(tree: QTreeWidget) -> dict[str, bool]:
    """Return the current expanded/collapsed state for every expandable item."""

    state: dict[str, bool] = {}

    def _walk(parent: QTreeWidget | QTreeWidgetItem, path: tuple[str, ...]) -> None:
        count = (
            parent.topLevelItemCount()
            if isinstance(parent, QTreeWidget)
            else parent.childCount()
        )
        for index in range(count):
            item = (
                parent.topLevelItem(index)
                if isinstance(parent, QTreeWidget)
                else parent.child(index)
            )
            if item is None:
                continue
            key = _tree_item_state_key(item, path, index)
            if item.childCount() > 0:
                state[key] = item.isExpanded()
            _walk(item, path + (key,))

    _walk(tree, ())
    return state


def _restore_tree_expansion(tree: QTreeWidget, state: dict[str, bool]) -> None:
    """Restore expanded/collapsed state after a tree rebuild."""

    def _walk(parent: QTreeWidget | QTreeWidgetItem, path: tuple[str, ...]) -> None:
        count = (
            parent.topLevelItemCount()
            if isinstance(parent, QTreeWidget)
            else parent.childCount()
        )
        for index in range(count):
            item = (
                parent.topLevelItem(index)
                if isinstance(parent, QTreeWidget)
                else parent.child(index)
            )
            if item is None:
                continue
            key = _tree_item_state_key(item, path, index)
            if item.childCount() > 0:
                item.setExpanded(state.get(key, True))
            _walk(item, path + (key,))

    _walk(tree, ())


def _tree_item_state_key(item: QTreeWidgetItem, path: tuple[str, ...], index: int) -> str:
    """Build a stable identity for expansion-state restoration."""

    node_id = item.data(0, Qt.ItemDataRole.UserRole)
    token = str(node_id) if isinstance(
        node_id, str) else f"header:{item.text(0)}:{index}"
    return "/".join((*path, token)) if path else token


def _rename_link_type(repository: Repository, link_type: LinkType) -> set[str]:
    repository.upsert_link_type(link_type)
    return {str(link_type.id)}


def _rename_node(repository: Repository, node: Node) -> set[str]:
    repository.upsert(node)
    return {str(node.id)}


def _delete_link_type(repository: Repository, link_type_id: str) -> set[str]:
    repository.delete_link_type(link_type_id)
    return {link_type_id}


def _delete_link_instances(repository: Repository, link_ids: list[str]) -> set[str]:
    touched: set[str] = set()
    for link_id in link_ids:
        repository.delete_link(link_id)
        touched.add(link_id)
    return touched


__all__ = ["QKnowledgeContextLibraryPanel"]

"""Connections panel for managing ad-hoc node links."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QSize

from lks_utils.gui_qt.widgets.q_button_bar_base import QButtonBarBase
from lks_utils.gui_qt.widgets.q_validation_badge import QValidationBadge
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.editor_session_types import SessionChangeEvent
from lks_utils.knowledge.data_interface.link_mutation_bridge import LinkMutationBridge
from lks_utils.knowledge.io import KnowledgeIO
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.reverse_ref_index import ReverseRefIndex
from lks_utils.knowledge.ui.components.ref_picker_dialog import QKnowledgeRefPickerDialog
from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
    ADHOC_PANEL_SECTION_LABEL_COLOR,
)
from lks_utils.knowledge.ui.widgets.field_widgets import (
    make_add_action_button,
    make_delete_action_button,
    make_pick_action_button,
)
from lks_utils.knowledge.ui.widgets.validation_badge_row_controller import (
    ValidationBadgeRowController,
)


class QKnowledgeConnectionsPanel(QWidget):
    """Panel showing outgoing and incoming ad-hoc links for the open node.

    Outgoing links are editable; incoming links are read-only context.
    """

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._link_bridge = LinkMutationBridge(session._io)  # noqa: SLF001
        self._badge_controller = ValidationBadgeRowController(
            session.validation_index, self)
        self._attached_object_ids: set[str] = set()
        self._current_node: Node | None = None
        self._selected_target_node_id_value: str | None = None

        self._header = QLabel("Connections", self)
        self._header.setStyleSheet("font-weight: 600; font-size: 12px;")

        self._outgoing_header = QLabel("Outgoing", self)
        self._incoming_header = QLabel("Incoming", self)
        section_style = (
            f"font-size: 11px; color: {ADHOC_PANEL_SECTION_LABEL_COLOR};"
        )
        self._outgoing_header.setStyleSheet(section_style)
        self._incoming_header.setStyleSheet(section_style)
        self._outgoing_header.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._incoming_header.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._outgoing_list = QListWidget(self)
        self._outgoing_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._incoming_list = QListWidget(self)
        self._incoming_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._incoming_list.setObjectName("incoming_connections_list")

        self._link_type_label = QLabel("Link Type:", self)
        self._target_label = QLabel("Target Node:", self)
        # Set fixed width for inline labels to keep them compact
        self._link_type_label.setMinimumWidth(80)
        self._target_label.setMinimumWidth(90)

        self._predicate_combo = QComboBox(self)
        self._predicate_combo.setToolTip(
            "Choose which link type to create from the current node."
        )
        self._target_display = QLineEdit(self)
        self._target_display.setReadOnly(True)
        self._target_display.setPlaceholderText("Pick target node...")
        self._target_display.setToolTip(
            "Selected out-of-graph target node for the new outgoing link."
        )
        self._pick_target_button = make_pick_action_button(
            tooltip="Open node picker to choose the outgoing link target.",
            parent=self,
        )
        self._pick_target_button.setToolTip(
            "Open node picker to choose the outgoing link target."
        )
        self._add_button = make_add_action_button(
            tooltip="Create the selected outgoing ad-hoc link.",
            parent=self,
        )
        self._add_button.setToolTip(
            "Create the selected outgoing ad-hoc link.")
        self._remove_button = make_delete_action_button(
            tooltip="Delete the selected outgoing ad-hoc link.",
            parent=self,
        )
        self._remove_button.setToolTip(
            "Delete the selected outgoing ad-hoc link."
        )

        self._build_layout()
        self._wire_signals()
        self._apply_styles()

    def _sync_session_io_if_needed(self) -> None:
        """Keep IO aligned when callers swap session._repository directly."""
        if self._session._io.repository is self._session._repository:  # noqa: SLF001
            return
        reverse_ref_index = ReverseRefIndex()
        reverse_ref_index.rebuild_from(self._session._repository)  # noqa: SLF001
        self._session._io = KnowledgeIO(  # noqa: SLF001
            repository=self._session._repository,  # noqa: SLF001
            reverse_ref_index=reverse_ref_index,
            validation_index=self._session._validation_index,  # noqa: SLF001
            repository_root=self._session._repository_root,  # noqa: SLF001
        )

    def set_node(self, node: Node | None) -> None:
        """Set the active node and populate the connections list."""
        self._sync_session_io_if_needed()
        # Session IO can be rebuilt on load/new_repo.
        self._link_bridge = LinkMutationBridge(self._session._io)  # noqa: SLF001
        self._current_node = node
        self._refresh_list()
        self._refresh_combos()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        root.addWidget(self._header)

        # Incoming/Outgoing lists side-by-side
        list_grid = QGridLayout()
        list_grid.setContentsMargins(0, 0, 0, 0)
        list_grid.setHorizontalSpacing(8)
        list_grid.setVerticalSpacing(4)
        list_grid.addWidget(self._incoming_header, 0, 0)
        list_grid.addWidget(self._outgoing_header, 0, 1)
        list_grid.addWidget(self._incoming_list, 1, 0)

        # Outgoing list with bottom action ribbon
        outgoing_container = QVBoxLayout()
        outgoing_container.setContentsMargins(0, 0, 0, 0)
        outgoing_container.setSpacing(4)
        outgoing_container.addWidget(self._outgoing_list, stretch=1)

        # Bottom action ribbon (similar to library pane)
        action_ribbon = QButtonBarBase(alignment="right")
        action_ribbon.add_button(self._add_button)
        action_ribbon.add_button(self._remove_button)
        outgoing_container.addWidget(action_ribbon)

        outgoing_widget = QWidget()
        outgoing_widget.setLayout(outgoing_container)
        list_grid.addWidget(outgoing_widget, 1, 1)

        list_grid.setColumnStretch(0, 1)
        list_grid.setColumnStretch(1, 1)
        root.addLayout(list_grid)

        # Inline Link Type row
        link_type_row = QHBoxLayout()
        link_type_row.setContentsMargins(0, 0, 0, 0)
        link_type_row.setSpacing(8)
        link_type_row.addWidget(self._link_type_label, stretch=0)
        link_type_row.addWidget(self._predicate_combo, stretch=1)
        root.addLayout(link_type_row)

        # Inline Target Node row
        target_row = QHBoxLayout()
        target_row.setContentsMargins(0, 0, 0, 0)
        target_row.setSpacing(8)
        target_row.addWidget(self._target_label, stretch=0)
        target_row.addWidget(self._target_display, stretch=1)
        target_row.addWidget(self._pick_target_button)
        root.addLayout(target_row)

    def _wire_signals(self) -> None:
        self._add_button.clicked.connect(self._on_add_clicked)
        self._remove_button.clicked.connect(self._on_remove_selected_clicked)
        self._pick_target_button.clicked.connect(self._on_pick_target_clicked)
        self._predicate_combo.currentIndexChanged.connect(
            self._refresh_action_buttons)
        self._outgoing_list.itemSelectionChanged.connect(
            self._refresh_action_buttons)
        self._session.add_change_listener(self._on_session_change)

    @property
    def _selected_target_node_id(self) -> str | None:
        return self._selected_target_node_id_value

    @_selected_target_node_id.setter
    def _selected_target_node_id(self, value: str | None) -> None:
        self._selected_target_node_id_value = value
        if hasattr(self, "_target_display"):
            self._refresh_target_display()
        if hasattr(self, "_add_button"):
            self._refresh_action_buttons()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QListWidget {{ border: 1px solid {EDGE_COLOR}; }}"
            "QListWidget::item { min-height: 22px; padding: 2px 4px; }"
            f"QListWidget#incoming_connections_list {{"
            f" color: {ADHOC_PANEL_SECTION_LABEL_COLOR};"
            f" border: 1px solid {ADHOC_PANEL_SECTION_LABEL_COLOR};"
            f" background: {SCENE_BACKGROUND_COLOR};"
            f" }}"
            f"QListWidget#incoming_connections_list::item {{ color: {ADHOC_PANEL_SECTION_LABEL_COLOR}; }}"
        )

    def _on_session_change(self, event: SessionChangeEvent) -> None:
        self._sync_session_io_if_needed()
        change_type = event.change_type
        if change_type in {"repo_loaded", "node", "link"}:
            # Keep bridge pinned to the current session IO/repository instance.
            self._link_bridge = LinkMutationBridge(self._session._io)  # noqa: SLF001
        if (
            change_type == "node"
            and self._current_node is not None
            and not event.touches_any({str(self._current_node.id)})
        ):
            return
        if change_type in {"node", "repo_loaded", "repo_saved", "link_type", "link"}:
            if self._current_node is not None:
                self._refresh_list()
                self._refresh_combos()

    def _refresh_list(self) -> None:
        for object_id in self._attached_object_ids:
            self._badge_controller.detach_row(object_id)
        self._attached_object_ids.clear()
        self._outgoing_list.clear()
        self._incoming_list.clear()

        if self._current_node is None:
            self._refresh_action_buttons()
            return

        node_id = str(self._current_node.id)
        outgoing = self._link_bridge.list_outgoing_ad_hoc_links(node_id)
        incoming = self._link_bridge.list_incoming_ad_hoc_links(node_id)

        for link in outgoing:
            item, row, badge = self._create_item_for_link(link, editable=True)
            self._outgoing_list.addItem(item)
            self._outgoing_list.setItemWidget(item, row)
            object_id = str(link.id)
            self._badge_controller.attach_row(object_id, row, badge)
            self._attached_object_ids.add(object_id)
        for link in incoming:
            item, row, badge = self._create_item_for_link(link, editable=False)
            self._incoming_list.addItem(item)
            self._incoming_list.setItemWidget(item, row)
            object_id = str(link.id)
            self._badge_controller.attach_row(object_id, row, badge)
            self._attached_object_ids.add(object_id)
        self._refresh_action_buttons()

    def _create_item_for_link(
        self,
        link: LinkInstance,
        *,
        editable: bool,
    ) -> tuple[QListWidgetItem, QWidget, QValidationBadge]:
        try:
            link_type = self._session.get_link_type(link.link_type_id)
            predicate_text = link_type.name
        except KeyError:
            predicate_text = f"<{link.link_type_id}>"

        peer_id = link.target_node_id if editable else link.source_node_id
        try:
            peer_node = self._session.get_node(peer_id)
            peer_text = peer_node.name
        except KeyError:
            peer_text = f"<{peer_id}>"

        text = f"{predicate_text}: {peer_text}"
        item = QListWidgetItem("")
        item.setToolTip(text)
        if editable:
            item.setData(0x0100, str(link.id))

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 2, 2, 2)
        row_layout.setSpacing(6)
        badge = QValidationBadge(row)
        badge.setObjectName("validation_badge")
        label = QLabel(text, row)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter |
                           Qt.AlignmentFlag.AlignLeft)
        label.setToolTip(text)
        row_layout.addWidget(badge, stretch=0)
        row_layout.addWidget(label, stretch=1)

        min_row_height = label.fontMetrics().height() + 8
        row.setMinimumHeight(min_row_height)
        item.setSizeHint(row.sizeHint())
        hint = item.sizeHint()
        item.setSizeHint(
            QSize(hint.width(), max(hint.height(), min_row_height)))
        return item, row, badge

    def _refresh_combos(self) -> None:
        self._predicate_combo.clear()

        link_types = self._session.list_link_types()
        for link_type in link_types:
            if link_type.is_system:
                continue
            self._predicate_combo.addItem(link_type.name, str(link_type.id))

        # Validate that the currently selected target node still exists.
        nodes = self._candidate_target_nodes()
        valid_ids = {str(n.id) for n in nodes}
        if self._selected_target_node_id not in valid_ids:
            self._selected_target_node_id = None

        self._refresh_target_display()
        self._refresh_action_buttons()

    def _candidate_target_nodes(self) -> list[Node]:
        nodes = self._session.list_nodes()
        if self._current_node is None:
            return nodes
        current_id = str(self._current_node.id)
        return [node for node in nodes if str(node.id) != current_id]

    def _refresh_target_display(self) -> None:
        if not self._selected_target_node_id:
            self._target_display.setText("")
            self._refresh_action_buttons()
            return
        try:
            node = self._session.get_node(self._selected_target_node_id)
            self._target_display.setText(node.name)
        except KeyError:
            self._target_display.setText("")
            self._selected_target_node_id = None
            return
        self._refresh_action_buttons()

    def _refresh_action_buttons(self) -> None:
        can_add = (
            self._current_node is not None
            and self._predicate_combo.count() > 0
            and self._selected_target_node_id is not None
        )
        self._add_button.setEnabled(can_add)
        selected = self._outgoing_list.currentItem()
        selected_link_id = selected.data(
            0x0100) if selected is not None else None
        self._remove_button.setEnabled(isinstance(
            selected_link_id, str) and selected_link_id != "")

    def _on_add_clicked(self) -> None:
        if self._current_node is None:
            return

        link_type_id = self._predicate_combo.currentData()
        target_node_id = self._selected_target_node_id

        if not link_type_id or not target_node_id:
            return

        current_link_type_ids = {str(link_type.id)
                                 for link_type in self._session.list_link_types()}
        if str(link_type_id) not in current_link_type_ids:
            self._refresh_combos()
            link_type_id = self._predicate_combo.currentData()
            if not link_type_id:
                return

        try:
            link = self._link_bridge.create_ad_hoc_link(
                link_type_id=link_type_id,
                source_node_id=str(self._current_node.id),
                target_node_id=target_node_id,
            )
        except ValueError as e:
            # Link type may have been deleted or become invalid; refresh combos
            self._refresh_combos()
            import sys
            print(f"Failed to create link: {e}", file=sys.stderr)
            return

        self._session.notify_io_mutation("link")
        self._refresh_list()

    def _on_pick_target_clicked(self) -> None:
        picker = QKnowledgeRefPickerDialog(
            self._session,
            ref_type=None,
            slot_name="ad_hoc_target",
            parent=self,
        )
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        selected = picker.selected_node_id()
        if not selected:
            return
        if self._current_node is not None and selected == str(self._current_node.id):
            return
        self._selected_target_node_id = selected
        self._refresh_target_display()
        self._refresh_action_buttons()

    def _on_remove_selected_clicked(self) -> None:
        selected = self._outgoing_list.currentItem()
        if selected is None:
            return
        link_id = selected.data(0x0100)
        if not isinstance(link_id, str) or not link_id:
            return
        try:
            self._link_bridge.delete_link(link_id)
            self._session.notify_io_mutation("link")
            self._refresh_list()
        except KeyError:
            pass


__all__ = ["QKnowledgeConnectionsPanel"]

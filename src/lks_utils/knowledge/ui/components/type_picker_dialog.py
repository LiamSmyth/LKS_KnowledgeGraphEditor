"""Modal type picker for knowledge inheritance/edit flows."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.q_dialog_scaffold_base import QDialogScaffoldBase

from lks_utils.knowledge.default_theme import EDGE_COLOR, NODE_TEXT_COLOR, SCENE_BACKGROUND_COLOR
from lks_utils.knowledge.models.node import Node


class QKnowledgeTypePickerDialog(QDialogScaffoldBase):
    """Pick one type node from a filtered, searchable list."""

    def __init__(
        self,
        type_nodes: list[Node],
        *,
        title: str = "Pick Base Type",
        slot_name: str = "",
        selected_type_id: str | None = None,
        exclude_type_ids: set[str] | None = None,
        allow_none: bool = False,
        none_label: str = "None (system base)",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent=parent)
        self._slot_name = slot_name
        self._allow_none = allow_none
        self._none_label = none_label
        self._selected_type_id = selected_type_id if selected_type_id is not None else ""
        self._exclude_type_ids = {str(value)
                                  for value in (exclude_type_ids or set())}
        self._all_options = sorted(
            (
                node
                for node in type_nodes
                if str(node.id) not in self._exclude_type_ids
            ),
            key=lambda node: (node.name.casefold(), node.category.casefold()),
        )

        self._title = QLabel(self)
        self._filter_edit = QLineEdit(self)
        self._filter_edit.setPlaceholderText(
            "Filter by name, category, or description...")
        self._filter_edit.setToolTip("Filter available base types.")
        self._list = QListWidget(self)
        self._list.setToolTip("Choose one type node to use as the base type.")

        self._buttons_ok: object  # QPushButton stored after _build_layout

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self._reload_options()

    def selected_node_id(self) -> str | None:
        """Return the selected type ULID string, or None if nothing is selected."""
        current = self._list.currentItem()
        if current is None:
            return None
        data = current.data(Qt.ItemDataRole.UserRole)
        return str(data) if isinstance(data, str) else None

    def selected_node(self) -> Node | None:
        """Return the selected type node, if any."""
        selected_id = self.selected_node_id()
        if selected_id is None:
            return None
        for node in self._all_options:
            if str(node.id) == selected_id:
                return node
        return None

    def _build_layout(self) -> None:
        self._title.setText(
            f"Slot: {self._slot_name or '(unspecified)'}    Base type selection"
        )

        top = QHBoxLayout()
        top.addWidget(QLabel("Filter:", self))
        top.addWidget(self._filter_edit, stretch=1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content_layout.addWidget(self._title)
        content_layout.addLayout(top)
        content_layout.addWidget(self._list, stretch=1)
        self.set_content(content)

        self._ok_btn = self.add_footer_button(
            "OK", QDialogButtonBox.ButtonRole.AcceptRole)
        self._ok_btn.setToolTip("Confirm the selected base type.")
        self._ok_btn.setEnabled(False)
        cancel_btn = self.add_footer_button(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.setToolTip("Close without changing the selection.")

        self.resize(560, 420)

    def _wire_signals(self) -> None:
        self._filter_edit.textChanged.connect(self._apply_filter)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._list.currentRowChanged.connect(
            lambda _row: self._ok_btn.setEnabled(
                self.selected_node_id() is not None
            )
        )

    def _reload_options(self) -> None:
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._filter_edit.text().strip().lower()
        self._list.clear()

        none_item = None
        if self._allow_none:
            none_item = QListWidgetItem(self._none_label)
            none_item.setData(Qt.ItemDataRole.UserRole, "")
            self._list.addItem(none_item)

        matching_options = [
            option
            for option in self._all_options
            if not query
            or query in f"{option.name} {option.category} {option.description}".lower()
        ]
        for option in matching_options:
            text = f"{option.name} ({option.category})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, str(option.id))
            self._list.addItem(item)
            if self._selected_type_id is not None and str(option.id) == self._selected_type_id:
                item.setSelected(True)
        if self._allow_none and self._selected_type_id == "" and none_item is not None:
            none_item.setSelected(True)
        if self._list.count() > 0 and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QListWidget {{ border: 1px solid {EDGE_COLOR}; }}"
        )


__all__ = ["QKnowledgeTypePickerDialog"]

"""Modal ref-target picker for knowledge slot editing."""
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
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.models.node import Node


class QKnowledgeRefPickerDialog(QDialogScaffoldBase):
    """Pick one reference target from session nodes, optionally filtered by category."""

    def __init__(
        self,
        session: EditorSession,
        *,
        ref_type: str | None = None,
        slot_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Pick Reference Target", parent=parent)
        self._session = session
        self._ref_type = ref_type
        self._slot_name = slot_name
        self._all_options: list[Node] = []

        self._title = QLabel(self)
        self._filter_edit = QLineEdit(self)
        self._filter_edit.setPlaceholderText("Filter by name or kind...")
        self._filter_edit.setToolTip("Filter available reference targets.")
        self._list = QListWidget(self)
        self._list.setToolTip(
            "Choose one node to store as the slot reference target.")

        self._buttons_ok: object  # QPushButton stored after _build_layout

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self._reload_options()

    def selected_node_id(self) -> str | None:
        """Return selected node ULID string, or None when no selection exists."""
        current = self._list.currentItem()
        if current is None:
            return None
        data = current.data(Qt.ItemDataRole.UserRole)
        return str(data) if isinstance(data, str) else None

    def _build_layout(self) -> None:
        self._title.setText(
            f"Slot: {self._slot_name or '(unspecified)'}    Type filter: {self._ref_type or 'any'}"
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
        self._ok_btn.setToolTip(
            "Confirm selection and apply the reference target.")
        self._ok_btn.setEnabled(False)
        cancel_btn = self.add_footer_button(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.setToolTip("Close without changing the reference target.")

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
        self._all_options = self._session.reference_options(
            ref_type=self._ref_type)
        self._all_options.sort(
            key=lambda node: (node.name.casefold(), node.category.casefold())
        )
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._filter_edit.text().strip().lower()
        self._list.clear()
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
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QListWidget {{ border: 1px solid {EDGE_COLOR}; }}"
        )


__all__ = ["QKnowledgeRefPickerDialog"]

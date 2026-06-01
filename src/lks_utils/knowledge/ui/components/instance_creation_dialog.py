"""Dialog for creating a new instance in the knowledge workbench."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.q_dialog_scaffold_base import QDialogScaffoldBase

from lks_utils.knowledge.default_theme import REF_VALID_COLOR, VALIDATION_ERROR_TEXT
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.ui.components.type_picker_dialog import QKnowledgeTypePickerDialog


class QInstanceCreationDialog(QDialogScaffoldBase):
    """Collect the source and text fields required to create a new instance."""

    def __init__(
        self,
        source_nodes: list[Node],
        *,
        selected_source_id: str | None = None,
        selected_type_id: str | None = None,
        existing_names: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Create Instance", parent=parent)
        self._source_nodes = list(source_nodes)
        if existing_names is None:
            existing_names = [node.name for node in source_nodes]
        self._existing_names = {name.strip()
                                for name in existing_names if name.strip()}
        initial_source_id = selected_source_id if selected_source_id is not None else selected_type_id
        self._base_type_id: str | None = initial_source_id
        self._base_type_label = QLabel("(none)", self)
        self._base_type_label.setWordWrap(True)
        self._name_edit = QLineEdit(self)
        self._name_edit.setToolTip(
            "Human-readable display name for the new instance.")
        self._name_status_label = QLabel("", self)
        self._name_status_label.setObjectName("new_instance_name_status")
        self._name_status_label.setWordWrap(True)
        self._description_edit = QTextEdit(self)
        self._description_edit.setFixedHeight(84)
        self._description_edit.setToolTip(
            "Optional description for the new instance.")

        form = QFormLayout()
        base_row = QWidget(self)
        base_layout = QHBoxLayout(base_row)
        base_layout.setContentsMargins(0, 0, 0, 0)
        base_layout.setSpacing(4)
        base_layout.addWidget(self._base_type_label, stretch=1)
        base_pick = QPushButton("Pick", self)
        base_pick.setToolTip(
            "Choose a base source for this instance (type or instance).")
        base_pick.clicked.connect(self._pick_base_type)
        base_layout.addWidget(base_pick)
        base_clear = QPushButton("Clear", self)
        base_clear.setToolTip("Remove the selected base source.")
        base_clear.clicked.connect(self._clear_base_type)
        base_layout.addWidget(base_clear)

        base_label = QLabel("Base Source:", self)
        base_label.setToolTip(
            "Choose a base source for this instance. A type creates a new root"
            " instance, and an instance creates a prototype-derived instance."
        )
        form.addRow(base_label, base_row)
        name_row = QWidget(self)
        name_layout = QVBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(2)
        name_layout.addWidget(self._name_edit)
        name_layout.addWidget(self._name_status_label)
        form.addRow("Name:", name_row)
        form.addRow("Description:", self._description_edit)

        self._error_label = QLabel("", self)
        self._error_label.setStyleSheet(
            f"color: {VALIDATION_ERROR_TEXT}; padding: 2px 4px;")
        self._error_label.setVisible(False)
        self._error_label.setWordWrap(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addLayout(form)
        content_layout.addWidget(self._error_label)
        self.set_content(content)
        self._ok_button = self.add_footer_button(
            "OK", QDialogButtonBox.ButtonRole.AcceptRole)
        self._ok_button.setToolTip("Create the instance with these values.")
        cancel_btn = self.add_footer_button(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.setToolTip("Close without creating an instance.")

        self._name_edit.textChanged.connect(self._update_name_status)
        self._update_name_status()

    def accept(self) -> None:  # type: ignore[override]
        type_id, name, _description = self.values()
        if not type_id:
            self._show_error("A base type selection is required.")
            return
        valid, message = self._validate_name(name)
        if not valid:
            self._show_error(message)
            return
        self._error_label.setVisible(False)
        super().accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def values(self) -> tuple[str | None, str, str]:
        return (
            self._base_type_id,
            self._name_edit.text().strip(),
            self._description_edit.toPlainText().strip(),
        )

    def _validate_name(self, name: str) -> tuple[bool, str]:
        if not name:
            return False, "Name is required."
        if name in self._existing_names:
            return False, "Name already exists. Choose a unique name."
        return True, ""

    def _update_name_status(self) -> None:
        name = self._name_edit.text().strip()
        valid, message = self._validate_name(name)
        if valid:
            self._name_status_label.setText("OK Name available")
            self._name_status_label.setStyleSheet(
                f"color: {REF_VALID_COLOR}; padding: 0 2px;")
        else:
            self._name_status_label.setText(f"X {message}")
            self._name_status_label.setStyleSheet(
                f"color: {VALIDATION_ERROR_TEXT}; padding: 0 2px;")
        self._ok_button.setEnabled(valid and bool(self._base_type_id))

    def _pick_base_type(self) -> None:
        dialog = QKnowledgeTypePickerDialog(
            self._source_nodes,
            title="Pick Base Source",
            selected_type_id=self._base_type_id,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        selected = dialog.selected_node()
        if selected is None:
            return
        self._base_type_id = str(selected.id)
        self._base_type_label.setText(f"{selected.name} ({selected.category})")
        self._update_name_status()

    def _clear_base_type(self) -> None:
        self._base_type_id = None
        self._base_type_label.setText("(none)")
        self._update_name_status()


_QNewInstanceDialog = QInstanceCreationDialog


__all__ = ["QInstanceCreationDialog", "_QNewInstanceDialog"]

"""Dialog for creating a new type in the knowledge workbench."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
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
from lks_utils.knowledge.ui.components.workbench_dialog_helpers import combo_value, populate_category_combo


class QTypeCreationDialog(QDialogScaffoldBase):
    """Collect the minimal fields required to create a new type-node."""

    def __init__(
        self,
        type_nodes: list[Node],
        *,
        existing_names: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Create Type", parent=parent)
        self._type_nodes = list(type_nodes)
        if existing_names is None:
            existing_names = [node.name for node in type_nodes]
        self._existing_names = {name.strip()
                                for name in existing_names if name.strip()}
        self._base_type_id: str | None = None
        self._base_type_label = QLabel("None (system base)", self)
        self._base_type_label.setWordWrap(True)
        self._category_combo = QComboBox(self)
        self._category_combo.setEditable(True)
        self._category_combo.setToolTip(
            "The category that instances of this type will belong to.\n"
            "Examples: 'fact', 'rule', 'term'.  Choose an existing category or\n"
            "type a new one. Leave blank for no category. Avoid Python primitive names (str, int, ...) here - "
            "those are slot data-types, not node categories."
        )
        self._name_edit = QLineEdit(self)
        self._name_edit.setToolTip(
            "Human-readable display name for this type (e.g. 'Fact').")
        self._name_status_label = QLabel("", self)
        self._name_status_label.setObjectName("new_type_name_status")
        self._name_status_label.setWordWrap(True)
        self._description_edit = QTextEdit(self)
        self._description_edit.setFixedHeight(84)
        self._description_edit.setToolTip(
            "What instances of this type represent.")

        populate_category_combo(self._category_combo,
                                type_nodes, include_empty_option=True)

        form = QFormLayout()
        base_row = QWidget(self)
        base_layout = QHBoxLayout(base_row)
        base_layout.setContentsMargins(0, 0, 0, 0)
        base_layout.setSpacing(4)
        base_layout.addWidget(self._base_type_label, stretch=1)
        base_pick = QPushButton("Pick", self)
        base_pick.setToolTip(
            "Choose an existing type to extend, or None for a root type.")
        base_pick.clicked.connect(self._pick_base_type)
        base_layout.addWidget(base_pick)
        base_clear = QPushButton("Clear", self)
        base_clear.setToolTip(
            "Remove the selected base type and use the system base.")
        base_clear.clicked.connect(self._clear_base_type)
        base_layout.addWidget(base_clear)

        base_label = QLabel("Base Type:")
        base_label.setToolTip(
            "Choose an existing type to extend, or leave blank for a root type.")
        form.addRow(base_label, base_row)
        instance_category_label = QLabel("Instance Category:")
        instance_category_label.setToolTip(
            "The category that instances of this type will be tagged with.")
        form.addRow(instance_category_label, self._category_combo)
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
        self.add_footer_button(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)

        self._name_edit.textChanged.connect(self._update_name_status)
        self._update_name_status()

    def accept(self) -> None:  # type: ignore[override]
        _base_type_id, _category, name, _description = self.values()
        valid, message = self._validate_name(name)
        if not valid:
            self._show_error(message)
            return
        self._error_label.setVisible(False)
        super().accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def values(self) -> tuple[str, str, str, str]:
        return (
            self._base_type_id or "",
            combo_value(self._category_combo),
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
        self._ok_button.setEnabled(valid)

    def _pick_base_type(self) -> None:
        dialog = QKnowledgeTypePickerDialog(
            self._type_nodes, allow_none=True, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        selected_id = dialog.selected_node_id()
        if selected_id is None:
            return
        if selected_id == "":
            self._clear_base_type()
            return
        selected = dialog.selected_node()
        if selected is None:
            return
        self._base_type_id = str(selected.id)
        self._base_type_label.setText(f"{selected.name} ({selected.category})")

    def _clear_base_type(self) -> None:
        self._base_type_id = None
        self._base_type_label.setText("None (system base)")


_QNewTypeDialog = QTypeCreationDialog


__all__ = ["QTypeCreationDialog", "_QNewTypeDialog"]

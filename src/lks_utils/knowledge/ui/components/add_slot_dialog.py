"""Dialog for adding a slot to a type in the knowledge workbench."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.q_dialog_scaffold_base import QDialogScaffoldBase

from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.default_theme import VALIDATION_ERROR_TEXT
from lks_utils.knowledge.models.node_slot import NodeSlot, SlotSource
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.ui.components.workbench_dialog_helpers import combo_value, populate_category_combo
from lks_utils.knowledge.ui.widgets.field_widgets import TypeComboBox


class _QAddSlotDialog(QDialogScaffoldBase):
    """Collect slot metadata for a type-node."""

    def __init__(self, type_nodes: list[Node], parent: QWidget | None = None) -> None:
        super().__init__("Add Slot", parent=parent)
        self._name_edit = QLineEdit(self)
        self._name_edit.setToolTip(
            "Identifier for this slot (e.g. 'text', 'source').")
        self._slot_type_combo = QComboBox(self)
        for source in SlotSource:
            self._slot_type_combo.addItem(source.value, source)
        self._slot_type_combo.setToolTip(
            "How the slot value is sourced.\n"
            "  literal   - an inline string value.\n"
            "  ref       - a reference to one other node.\n"
            "  ref_list  - a list of references.\n"
            "  file_ref  - a file-system reference.\n"
            "  image_ref - an image reference.\n"
            "  video_ref - a video reference."
        )
        self._required_check = QCheckBox("Required", self)
        self._required_check.setChecked(True)
        self._required_check.setToolTip(
            "Whether this slot must be filled before the instance is valid.")
        self._value_type_combo = TypeComboBox(
            [as_type(type_node).category for type_node in type_nodes if is_type(
                type_node)],
            "any",
            self,
        )
        self._value_type_combo.setToolTip(
            "Primitive or composite value type for this property. In an empty repo, base Python "
            "primitives are always available."
        )
        self._ref_category_combo = QComboBox(self)
        self._ref_category_combo.setEditable(True)
        self._ref_category_combo.setToolTip(
            "The category of nodes this ref slot may point to.\n"
            "Leave blank to allow refs to any node.  Choose an existing category\n"
            "or type a new one (e.g. 'fact', 'rule', 'term')."
        )
        self._description_edit = QLineEdit(self)
        self._description_edit.setToolTip(
            "Optional human-readable description of this slot's purpose.")

        populate_category_combo(self._ref_category_combo, type_nodes)

        form = QFormLayout()
        form.addRow("Slot Name:", self._name_edit)
        slot_type_label = QLabel("Slot Type:")
        slot_type_label.setToolTip("Storage type for this slot's value.")
        form.addRow(slot_type_label, self._slot_type_combo)
        value_type_label = QLabel("Value Type:")
        value_type_label.setToolTip(
            "Primitive or composite type for values stored in this property.")
        form.addRow(value_type_label, self._value_type_combo)
        ref_category_label = QLabel("Ref Category:")
        ref_category_label.setToolTip(
            "Category of nodes this ref slot is allowed to point to.")
        form.addRow(ref_category_label, self._ref_category_combo)
        form.addRow("Description:", self._description_edit)
        form.addRow("", self._required_check)

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
        self.add_footer_button("OK", QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_footer_button(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)

        self._slot_type_combo.currentTextChanged.connect(
            self._sync_enabled_state)
        self._sync_enabled_state()

    def accept(self) -> None:  # type: ignore[override]
        name = self._name_edit.text().strip()
        if not name:
            self._show_error("Slot name is required.")
            return
        self._error_label.setVisible(False)
        super().accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def values(self) -> NodeSlot:
        source_data = self._slot_type_combo.currentData()
        source = source_data if isinstance(source_data, SlotSource) else SlotSource(
            self._slot_type_combo.currentText())
        ref_type = combo_value(self._ref_category_combo) or None
        return NodeSlot(
            name=self._name_edit.text().strip(),
            source=source,
            required=self._required_check.isChecked(),
            value_type=self._value_type_combo.value(),
            target_type=ref_type if source.is_reference else None,
            ref_type=ref_type if source.is_reference else None,
            description=self._description_edit.text().strip() or None,
        )

    def _sync_enabled_state(self, *_args: object) -> None:
        source_data = self._slot_type_combo.currentData()
        source = source_data if isinstance(source_data, SlotSource) else SlotSource(
            self._slot_type_combo.currentText())
        is_ref = source.is_reference
        self._ref_category_combo.setEnabled(is_ref)
        if not is_ref:
            self._ref_category_combo.setCurrentIndex(-1)
            self._ref_category_combo.setEditText("")


__all__ = ["_QAddSlotDialog"]

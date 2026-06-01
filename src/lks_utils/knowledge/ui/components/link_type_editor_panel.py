"""Editor panel for one semantic LinkType."""
from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.fields import QColorField, QFieldOverrideWrapper
from lks_utils.knowledge.default_theme import REF_VALID_COLOR, VALIDATION_ERROR_TEXT
from lks_utils.knowledge.display_color import (
    effective_link_type_display_color,
    normalize_display_color,
    seeded_display_color,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.links.link_type import LinkType, SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
from lks_utils.knowledge.models.type import as_type
from lks_utils.theme.color import Color


_RESERVED_SYSTEM_LINK_TYPE_IDS: frozenset[str] = frozenset(
    {
        SLOT_REF_LINK_TYPE_ID,
        EXTENDS_LINK_TYPE_ID,
        INSTANCE_OF_LINK_TYPE_ID,
    }
)


class QKnowledgeLinkTypeEditorPanel(QWidget):
    """Edit/create panel for one LinkType record."""

    save_requested = Signal(object)
    changed = Signal()
    committed = Signal()

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._editing_id: str | None = None
        self._suspend_changed_signal: bool = False

        self._title = QLabel("Link Type Editor", self)
        self._name_edit = QLineEdit(self)
        self._name_edit.setToolTip(
            "Forward predicate label (for example: related_to)."
        )
        self._name_status_label = QLabel("", self)
        self._name_status_label.setObjectName("link_type_name_status")
        self._name_status_label.setWordWrap(True)
        self._inverse_name_edit = QLineEdit(self)
        self._inverse_name_edit.setToolTip(
            "Inverse display label (for example: related_from)."
        )
        self._description_edit = QLineEdit(self)
        self._description_edit.setToolTip(
            "Optional human-readable description of this relation."
        )

        self._source_constraint_combo = QComboBox(self)
        self._source_constraint_combo.setEditable(True)
        self._source_constraint_combo.setInsertPolicy(
            QComboBox.InsertPolicy.NoInsert
        )
        self._source_constraint_combo.setToolTip(
            "Optional source-node type constraint.\n"
            "Choose a repository type to constrain the source node kind, or leave unset for no constraint."
        )

        self._target_constraint_combo = QComboBox(self)
        self._target_constraint_combo.setEditable(True)
        self._target_constraint_combo.setInsertPolicy(
            QComboBox.InsertPolicy.NoInsert
        )
        self._target_constraint_combo.setToolTip(
            "Optional target-node type constraint.\n"
            "Choose a repository type to constrain the target node kind, or leave unset for no constraint."
        )

        self._cardinality_combo = QComboBox(self)
        self._cardinality_combo.addItems(["many", "one"])
        self._cardinality_combo.setToolTip(
            "Outgoing cardinality from a source node for this relation type."
        )

        self._display_color_field = QColorField(
            default_value=Color.from_hex("#4a708f"),
            show_alpha=False,
            use_compact_picker_dialog=True,
            parent=self,
        )
        self._display_color_override = QFieldOverrideWrapper(
            self._display_color_field,
            overridden=False,
            parent=self,
        )
        self._display_color_override.setObjectName(
            "link_type_display_color_override"
        )
        self._display_color_override.set_override_tooltip(
            "Enable override to persist a custom display color for this link type. "
            "Disable to use deterministic seeded color from link type id."
        )

        self._save_button = QPushButton("Save", self)
        self._save_button.setToolTip("Validate and save this link type.")
        self._error_label = QLabel("", self)

        self._build_layout()
        self._wire_signals()
        self.refresh_constraint_options()

    def refresh_constraint_options(self) -> None:
        """Refresh source/target constraint pickers from current repository types."""
        source_current = self._source_constraint_combo.currentText().strip()
        target_current = self._target_constraint_combo.currentText().strip()

        type_choices: list[tuple[str, str]] = []
        seen_type_ids: set[str] = set()
        for type_node in sorted(
            self._session.iter_types(),
            key=lambda node: (node.name.casefold(), str(node.id)),
        ):
            type_view = as_type(type_node)
            type_id = str(type_node.id)
            if not type_id or type_id in seen_type_ids:
                continue
            seen_type_ids.add(type_id)
            category = type_view.category.strip()
            if type_view.name.strip() and category:
                label = f"{type_view.name} ({category})"
            elif type_view.name.strip():
                label = type_view.name
            else:
                label = type_id
            type_choices.append((label, type_id))

        self._source_constraint_combo.clear()
        self._target_constraint_combo.clear()
        self._source_constraint_combo.addItem("(none)", "")
        self._target_constraint_combo.addItem("(none)", "")
        for label, token in type_choices:
            self._source_constraint_combo.addItem(label, token)
            self._target_constraint_combo.addItem(label, token)

        self._set_combo_text(self._source_constraint_combo, source_current)
        self._set_combo_text(self._target_constraint_combo, target_current)

    def edit_new(self) -> None:
        """Reset the editor for creating a new link type."""
        with self._suspend_changes():
            self._editing_id = None
            self._set_read_only(False)
            self._name_edit.setText("")
            self._inverse_name_edit.setText("")
            self._description_edit.setText("")
            self._set_combo_text(self._source_constraint_combo, "")
            self._set_combo_text(self._target_constraint_combo, "")
            self._cardinality_combo.setCurrentText("many")
            self._display_color_override.set_overridden(False)
            self._display_color_field.set_value(
                Color.from_hex(seeded_display_color("new_link_type"))
            )
            self._error_label.setText("")
            self._update_name_status()

    def clear(self) -> None:
        """Clear the editor without changing state (used when deselecting in library)."""
        with self._suspend_changes():
            self._editing_id = None
            self._set_read_only(True)
            self._name_edit.setText("")
            self._inverse_name_edit.setText("")
            self._description_edit.setText("")
            self._set_combo_text(self._source_constraint_combo, "")
            self._set_combo_text(self._target_constraint_combo, "")
            self._cardinality_combo.setCurrentText("many")
            self._display_color_override.set_overridden(False)
            self._display_color_field.set_value(
                Color.from_hex(seeded_display_color("new_link_type"))
            )
            self._error_label.setText("")
            self._update_name_status()

    def load_link_type(self, link_type: LinkType) -> None:
        """Load an existing link type into the form."""
        with self._suspend_changes():
            self._editing_id = str(link_type.id)
            self._name_edit.setText(link_type.name)
            self._inverse_name_edit.setText(link_type.inverse_name)
            self._description_edit.setText(link_type.description)
            self._name_edit.setCursorPosition(0)
            self._inverse_name_edit.setCursorPosition(0)
            self._description_edit.setCursorPosition(0)
            self._set_combo_text(
                self._source_constraint_combo,
                link_type.source_type_constraint or "",
            )
            self._set_combo_text(
                self._target_constraint_combo,
                link_type.target_type_constraint or "",
            )
            self._cardinality_combo.setCurrentText(link_type.cardinality)

            effective_color = effective_link_type_display_color(link_type)
            self._display_color_override.set_overridden(
                normalize_display_color(link_type.display_color) is not None
            )
            self._display_color_field.set_value(
                Color.from_hex(effective_color))

            self._error_label.setText("")
            self._set_read_only(
                str(link_type.id) in _RESERVED_SYSTEM_LINK_TYPE_IDS
                or link_type.is_system
            )
            self._update_name_status()

    def build_link_type(self) -> LinkType:
        """Build a LinkType from current editor values."""
        link_type_id = self._editing_id
        payload: dict[str, object] = {
            "name": self._name_edit.text().strip(),
            "inverse_name": self._inverse_name_edit.text().strip(),
            "description": self._description_edit.text().strip(),
            "source_type_constraint": self._constraint_value_from_combo(
                self._source_constraint_combo
            ),
            "target_type_constraint": self._constraint_value_from_combo(
                self._target_constraint_combo
            ),
            "cardinality": self._cardinality_combo.currentText().strip() or "many",
            "is_system": False,
            "display_color": None,
        }

        if self._display_color_override.is_overridden():
            payload["display_color"] = normalize_display_color(
                self._display_color_field.value()
            )

        if link_type_id is not None:
            payload["id"] = link_type_id
        return LinkType.model_validate(payload)

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        name_row = QWidget(self)
        name_layout = QVBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(2)
        name_layout.addWidget(self._name_edit)
        name_layout.addWidget(self._name_status_label)
        form.addRow("Name", name_row)
        form.addRow("Inverse Name", self._inverse_name_edit)
        form.addRow("Description", self._description_edit)
        form.addRow("Source Constraint", self._source_constraint_combo)
        form.addRow("Target Constraint", self._target_constraint_combo)
        form.addRow("Cardinality", self._cardinality_combo)
        form.addRow("Display Color", self._display_color_override)

        self._error_label.setObjectName("knowledge_link_type_editor_error")

        root.addWidget(self._title)
        root.addLayout(form)
        root.addWidget(self._save_button)
        root.addWidget(self._error_label)
        root.addStretch(1)

    def _wire_signals(self) -> None:
        self._save_button.clicked.connect(self._on_save_clicked)
        self._name_edit.textChanged.connect(self._update_name_status)
        self._name_edit.textChanged.connect(self._emit_changed)
        self._name_edit.editingFinished.connect(self._emit_committed)
        self._inverse_name_edit.textChanged.connect(self._emit_changed)
        self._inverse_name_edit.editingFinished.connect(self._emit_committed)
        self._description_edit.textChanged.connect(self._emit_changed)
        self._description_edit.editingFinished.connect(self._emit_committed)
        self._source_constraint_combo.currentTextChanged.connect(
            self._emit_changed)
        self._source_constraint_combo.activated.connect(
            self._emit_committed)
        if self._source_constraint_combo.lineEdit() is not None:
            self._source_constraint_combo.lineEdit().editingFinished.connect(
                self._emit_committed
            )
        self._target_constraint_combo.currentTextChanged.connect(
            self._emit_changed)
        self._target_constraint_combo.activated.connect(
            self._emit_committed)
        if self._target_constraint_combo.lineEdit() is not None:
            self._target_constraint_combo.lineEdit().editingFinished.connect(
                self._emit_committed
            )
        self._cardinality_combo.currentTextChanged.connect(self._emit_changed)
        self._cardinality_combo.activated.connect(self._emit_committed)
        self._display_color_override.override_changed.connect(
            self._emit_changed)
        self._display_color_override.override_changed.connect(
            self._emit_committed)
        self._display_color_field.committed.connect(self._emit_changed)
        self._display_color_field.committed.connect(self._emit_committed)
        self._update_name_status()

    def _on_save_clicked(self) -> None:
        valid, message = self._validate_name(self._name_edit.text().strip())
        if not valid:
            self._error_label.setText(message)
            return
        try:
            link_type = self.build_link_type()
        except Exception as exc:
            self._error_label.setText(str(exc))
            return
        self._error_label.setText("")
        self.save_requested.emit(link_type)

    def set_status_message(self, message: str) -> None:
        """Show validation/info message below the editor controls."""
        self._error_label.setText(message)

    def _set_read_only(self, read_only: bool) -> None:
        self._name_edit.setReadOnly(read_only)
        self._inverse_name_edit.setReadOnly(read_only)
        self._description_edit.setReadOnly(read_only)
        self._source_constraint_combo.setEnabled(not read_only)
        self._target_constraint_combo.setEnabled(not read_only)
        self._cardinality_combo.setEnabled(not read_only)
        self._display_color_override.setEnabled(not read_only)
        self._save_button.setEnabled(not read_only)
        self._update_name_status()

    def _clean_optional(self, value: str) -> str | None:
        clean = value.strip()
        if clean.lower() in {"any", "(none)", "none"}:
            return None
        return clean or None

    def _constraint_value_from_combo(self, combo: QComboBox) -> str | None:
        current_text = combo.currentText().strip()
        clean_text = self._clean_optional(current_text)
        if clean_text is None:
            return None
        current_data = combo.currentData()
        if isinstance(current_data, str):
            clean_data = self._clean_optional(current_data)
            if clean_data is not None and combo.findText(current_text) >= 0:
                return clean_data
        return clean_text

    def _set_combo_text(self, combo: QComboBox, value: str) -> None:
        """Set editable combo text while preserving values not currently in options."""
        if value.strip().lower() in {"any", "(none)", "none"}:
            combo.setCurrentIndex(0)
            return
        if not value:
            combo.setCurrentIndex(0)
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
            return
        combo.setEditText(value)

    def _validate_name(self, candidate: str) -> tuple[bool, str]:
        if not candidate:
            return False, "Name is required."
        for link_type in self._session.list_link_types():
            if link_type.name != candidate:
                continue
            if str(link_type.id) == str(self._editing_id):
                continue
            return False, "Name already exists. Choose a unique name."
        return True, ""

    def _update_name_status(self) -> None:
        valid, message = self._validate_name(self._name_edit.text().strip())
        if valid:
            self._name_status_label.setText("OK Name available")
            self._name_status_label.setStyleSheet(
                f"color: {REF_VALID_COLOR}; padding: 0 2px;"
            )
        else:
            self._name_status_label.setText(f"X {message}")
            self._name_status_label.setStyleSheet(
                f"color: {VALIDATION_ERROR_TEXT}; padding: 0 2px;"
            )
        self._save_button.setEnabled(
            valid and not self._name_edit.isReadOnly())

    def _emit_changed(self, *args: object) -> None:
        if self._suspend_changed_signal:
            return
        self.changed.emit()

    def _emit_committed(self, *args: object) -> None:
        if self._suspend_changed_signal:
            return
        self.committed.emit()

    @contextmanager
    def _suspend_changes(self):
        previous = self._suspend_changed_signal
        self._suspend_changed_signal = True
        try:
            yield
        finally:
            self._suspend_changed_signal = previous


__all__ = ["QKnowledgeLinkTypeEditorPanel"]

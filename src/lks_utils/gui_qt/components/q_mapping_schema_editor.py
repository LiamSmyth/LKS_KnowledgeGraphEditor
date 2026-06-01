"""Qt component for editing MappingSchema objects.

Provides a visual editor for creating and modifying MappingSchema instances,
including field definitions, types, validation rules, and enum values.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lks_utils.csv import FieldDefinition, FieldType, MappingSchema
from lks_utils.gui_qt.components.q_csv_preview import QCSVPreviewComponent


class FieldDefinitionDialog(QDialog):
    """Dialog for editing a single field definition."""

    def __init__(self, field_def: FieldDefinition | None = None, parent: QWidget | None = None) -> None:
        """Initialize the field definition dialog.

        Args:
            field_def: Existing field definition to edit, or None for new field
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle(
            "Edit Field Definition" if field_def else "New Field Definition")
        self.resize(500, 600)

        layout = QVBoxLayout()

        # Field name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Field Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Date, Amount, Category")
        name_row.addWidget(self.name_input)
        layout.addLayout(name_row)

        # Field label
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Display Label:"))
        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("Human-readable label for UI")
        label_row.addWidget(self.label_input)
        layout.addLayout(label_row)

        # Field type
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Field Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems([ft.value for ft in FieldType])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        type_row.addWidget(self.type_combo)
        layout.addLayout(type_row)

        # Enum values section
        self.enum_group = QGroupBox("Enum Values")
        enum_layout = QVBoxLayout()

        self.enum_list = QListWidget()
        enum_layout.addWidget(self.enum_list)

        enum_btn_row = QHBoxLayout()
        self.add_enum_btn = QPushButton("Add Value")
        self.add_enum_btn.clicked.connect(self._on_add_enum)
        enum_btn_row.addWidget(self.add_enum_btn)

        self.remove_enum_btn = QPushButton("Remove Selected")
        self.remove_enum_btn.clicked.connect(self._on_remove_enum)
        enum_btn_row.addWidget(self.remove_enum_btn)

        enum_btn_row.addStretch()
        enum_layout.addLayout(enum_btn_row)

        self.enum_group.setLayout(enum_layout)
        layout.addWidget(self.enum_group)

        # Flags
        flags_layout = QHBoxLayout()
        self.required_cb = QCheckBox("Required")
        flags_layout.addWidget(self.required_cb)

        self.use_value_map_cb = QCheckBox("Use Value Map")
        self.use_value_map_cb.setToolTip(
            "Present a value map editor (for mapping many input values to valid output values). "
            "If unchecked and enum values are set, a dropdown editor is used instead."
        )
        flags_layout.addWidget(self.use_value_map_cb)

        flags_layout.addStretch()
        layout.addLayout(flags_layout)

        # Default value
        default_row = QHBoxLayout()
        default_row.addWidget(QLabel("Default Value:"))
        self.default_input = QLineEdit()
        self.default_input.setPlaceholderText("Optional default value")
        default_row.addWidget(self.default_input)
        layout.addLayout(default_row)

        # Description
        layout.addWidget(QLabel("Description:"))
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText(
            "Help text explaining the field's purpose")
        self.description_input.setMaximumHeight(80)
        layout.addWidget(self.description_input)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

        # Load existing field if provided
        if field_def:
            self._load_field(field_def)
        else:
            self._on_type_changed(FieldType.TEXT.value)

    def _on_type_changed(self, type_str: str) -> None:
        """Handle field type change."""
        is_enum = type_str == FieldType.ENUM.value
        self.enum_group.setEnabled(is_enum)
        self.use_value_map_cb.setEnabled(is_enum)

    def _on_add_enum(self) -> None:
        """Add a new enum value."""
        from PySide6.QtWidgets import QInputDialog

        value, ok = QInputDialog.getText(
            self,
            "Add Enum Value",
            "Enter enum value:"
        )

        if ok and value:
            self.enum_list.addItem(value)

    def _on_remove_enum(self) -> None:
        """Remove selected enum value."""
        for item in self.enum_list.selectedItems():
            self.enum_list.takeItem(self.enum_list.row(item))

    def _load_field(self, field_def: FieldDefinition) -> None:
        """Load field definition into form."""
        self.name_input.setText(field_def.name)
        self.label_input.setText(field_def.label)

        index = self.type_combo.findText(field_def.field_type.value)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)

        for value in field_def.enum_values:
            self.enum_list.addItem(value)

        self.required_cb.setChecked(field_def.required)
        self.use_value_map_cb.setChecked(field_def.use_value_map)
        self.default_input.setText(field_def.default_value)
        self.description_input.setPlainText(field_def.description)

    def get_field_definition(self) -> FieldDefinition | None:
        """Get the field definition from form.

        Returns:
            Field definition, or None if validation fails
        """
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error",
                                "Field name is required.")
            return None

        label = self.label_input.text().strip()
        if not label:
            label = name

        field_type = FieldType(self.type_combo.currentText())

        # Collect enum values
        enum_values = []
        for i in range(self.enum_list.count()):
            enum_values.append(self.enum_list.item(i).text())

        # Validate enum type has values if value map is not used
        if field_type == FieldType.ENUM and not enum_values and not self.use_value_map_cb.isChecked():
            QMessageBox.warning(
                self,
                "Validation Error",
                "Enum field must have at least one value (or enable 'Use Value Map')."
            )
            return None

        return FieldDefinition(
            name=name,
            label=label,
            field_type=field_type,
            enum_values=enum_values,
            required=self.required_cb.isChecked(),
            default_value=self.default_input.text().strip(),
            description=self.description_input.toPlainText().strip(),
            use_value_map=self.use_value_map_cb.isChecked(),
        )


class QMappingSchemaEditor(QWidget):
    """Component for editing MappingSchema objects.

    Provides a complete interface for creating and editing schemas, including:
    - Schema metadata (ID, name, version, description)
    - Field list with add/edit/remove/reorder
    - Visual field editor dialog
    """

    schema_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the schema editor component."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout()

        # Schema metadata section
        metadata_group = QGroupBox("Schema Metadata")
        metadata_layout = QVBoxLayout()

        # Schema ID
        id_row = QHBoxLayout()
        id_row.addWidget(QLabel("Schema ID:"))
        self.schema_id_input = QLineEdit()
        self.schema_id_input.setPlaceholderText(
            "Unique identifier (e.g., transaction_v1)")
        self.schema_id_input.textChanged.connect(self.schema_changed.emit)
        id_row.addWidget(self.schema_id_input)
        metadata_layout.addLayout(id_row)

        # Schema name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Schema Name:"))
        self.schema_name_input = QLineEdit()
        self.schema_name_input.setPlaceholderText("Human-readable name")
        self.schema_name_input.textChanged.connect(self.schema_changed.emit)
        name_row.addWidget(self.schema_name_input)
        metadata_layout.addLayout(name_row)

        # Version
        version_row = QHBoxLayout()
        version_row.addWidget(QLabel("Version:"))
        self.version_input = QLineEdit()
        self.version_input.setPlaceholderText("1.0")
        self.version_input.setText("1.0")
        self.version_input.textChanged.connect(self.schema_changed.emit)
        version_row.addWidget(self.version_input)
        metadata_layout.addLayout(version_row)

        # Description
        metadata_layout.addWidget(QLabel("Description:"))
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Schema description...")
        self.description_input.setMaximumHeight(60)
        self.description_input.textChanged.connect(self.schema_changed.emit)
        metadata_layout.addWidget(self.description_input)

        metadata_group.setLayout(metadata_layout)
        layout.addWidget(metadata_group)

        # Fields section
        fields_group = QGroupBox("Fields")
        fields_layout = QVBoxLayout()

        self.fields_list = QListWidget()
        self.fields_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.fields_list.itemDoubleClicked.connect(self._on_edit_field)
        fields_layout.addWidget(self.fields_list)

        # Field buttons
        field_btn_row = QHBoxLayout()

        self.add_field_btn = QPushButton("Add Field")
        self.add_field_btn.clicked.connect(self._on_add_field)
        field_btn_row.addWidget(self.add_field_btn)

        self.edit_field_btn = QPushButton("Edit Selected")
        self.edit_field_btn.clicked.connect(self._on_edit_field)
        field_btn_row.addWidget(self.edit_field_btn)

        self.remove_field_btn = QPushButton("Remove Selected")
        self.remove_field_btn.clicked.connect(self._on_remove_field)
        field_btn_row.addWidget(self.remove_field_btn)

        self.move_up_btn = QPushButton("↑ Move Up")
        self.move_up_btn.clicked.connect(self._on_move_up)
        field_btn_row.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("↓ Move Down")
        self.move_down_btn.clicked.connect(self._on_move_down)
        field_btn_row.addWidget(self.move_down_btn)

        field_btn_row.addStretch()
        fields_layout.addLayout(field_btn_row)

        fields_group.setLayout(fields_layout)
        layout.addWidget(fields_group)

        # Preview section
        self.preview = QCSVPreviewComponent(
            parent=self,
            title="Schema Template Preview",
            show_refresh=True,
            max_preview_rows=5,
            min_height=200,
        )
        self.preview.refresh_requested.connect(self._update_preview)
        layout.addWidget(self.preview)

        self.setLayout(layout)

        # Initial preview update
        self._update_preview()

    def _on_add_field(self) -> None:
        """Add a new field."""
        dialog = FieldDefinitionDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            field_def = dialog.get_field_definition()
            if field_def:
                self._add_field_to_list(field_def)
                self.schema_changed.emit()
                self._update_preview()

    def _on_edit_field(self) -> None:
        """Edit selected field."""
        current = self.fields_list.currentItem()
        if not current:
            return

        field_def = current.data(Qt.ItemDataRole.UserRole)
        dialog = FieldDefinitionDialog(field_def, parent=self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_field_def = dialog.get_field_definition()
            if new_field_def:
                current.setText(self._format_field_item(new_field_def))
                current.setData(Qt.ItemDataRole.UserRole, new_field_def)
                self.schema_changed.emit()
                self._update_preview()

    def _on_remove_field(self) -> None:
        """Remove selected field."""
        current = self.fields_list.currentItem()
        if current:
            self.fields_list.takeItem(self.fields_list.row(current))
            self.schema_changed.emit()
            self._update_preview()

    def _on_move_up(self) -> None:
        """Move selected field up."""
        current_row = self.fields_list.currentRow()
        if current_row > 0:
            item = self.fields_list.takeItem(current_row)
            self.fields_list.insertItem(current_row - 1, item)
            self.fields_list.setCurrentRow(current_row - 1)
            self.schema_changed.emit()
            self._update_preview()

    def _on_move_down(self) -> None:
        """Move selected field down."""
        current_row = self.fields_list.currentRow()
        if current_row < self.fields_list.count() - 1:
            item = self.fields_list.takeItem(current_row)
            self.fields_list.insertItem(current_row + 1, item)
            self.fields_list.setCurrentRow(current_row + 1)
            self.schema_changed.emit()
            self._update_preview()

    def _add_field_to_list(self, field_def: FieldDefinition) -> None:
        """Add a field definition to the list widget."""
        item = QListWidgetItem(self._format_field_item(field_def))
        item.setData(Qt.ItemDataRole.UserRole, field_def)
        self.fields_list.addItem(item)

    def _format_field_item(self, field_def: FieldDefinition) -> str:
        """Format field definition for display in list."""
        flags = []
        if field_def.required:
            flags.append("required")
        if field_def.use_value_map:
            flags.append("value_map")

        flags_str = f" [{', '.join(flags)}]" if flags else ""

        return f"{field_def.name} ({field_def.field_type.value}){flags_str} - {field_def.label}"

    def get_schema(self) -> MappingSchema | None:
        """Get the current schema from the editor.

        Returns:
            MappingSchema object, or None if validation fails
        """
        schema_id = self.schema_id_input.text().strip()
        if not schema_id:
            QMessageBox.warning(self, "Validation Error",
                                "Schema ID is required.")
            return None

        schema_name = self.schema_name_input.text().strip()
        if not schema_name:
            QMessageBox.warning(self, "Validation Error",
                                "Schema name is required.")
            return None

        # Collect fields
        fields = []
        for i in range(self.fields_list.count()):
            item = self.fields_list.item(i)
            field_def = item.data(Qt.ItemDataRole.UserRole)
            fields.append(field_def)

        if not fields:
            QMessageBox.warning(self, "Validation Error",
                                "Schema must have at least one field.")
            return None

        return MappingSchema(
            schema_id=schema_id,
            schema_name=schema_name,
            schema_version=self.version_input.text().strip() or "1.0",
            description=self.description_input.toPlainText().strip(),
            fields=fields,
        )

    def set_schema(self, schema: MappingSchema) -> None:
        """Load a schema into the editor.

        Args:
            schema: MappingSchema to load
        """
        self.schema_id_input.setText(schema.schema_id)
        self.schema_name_input.setText(schema.schema_name)
        self.version_input.setText(schema.schema_version)
        self.description_input.setPlainText(schema.description)

        self.fields_list.clear()
        for field_def in schema.fields:
            self._add_field_to_list(field_def)

        self._update_preview()

    def clear(self) -> None:
        """Clear all fields in the editor."""
        self.schema_id_input.clear()
        self.schema_name_input.clear()
        self.version_input.setText("1.0")
        self.description_input.clear()
        self.fields_list.clear()
        self._update_preview()

    def _update_preview(self) -> None:
        """Update the preview table with current schema fields."""
        # Collect current fields
        fields = []
        for i in range(self.fields_list.count()):
            item = self.fields_list.item(i)
            field_def = item.data(Qt.ItemDataRole.UserRole)
            fields.append(field_def)

        if not fields:
            self.preview.clear()
            return

        # Build headers from field labels (or names as fallback)
        headers = [f.label or f.name for f in fields]

        # Build sample rows showing data types and example values
        type_row = []
        example_row = []
        for field in fields:
            # Type indicator
            type_str = field.field_type.value
            if field.required:
                type_str += " *"
            type_row.append(type_str)

            # Example value based on type
            if field.field_type == FieldType.ENUM:
                if field.enum_values:
                    example = field.enum_values[0]
                elif field.default_value:
                    example = field.default_value
                else:
                    example = "<enum value>"
            elif field.field_type == FieldType.DATE:
                example = field.default_value or "2024-01-15"
            elif field.field_type == FieldType.NUMBER:
                example = field.default_value or "123.45"
            elif field.field_type == FieldType.INTEGER:
                example = field.default_value or "42"
            elif field.field_type == FieldType.BOOLEAN:
                example = field.default_value or "true"
            else:  # TEXT
                example = field.default_value or "example text"

            example_row.append(example)

        rows = [type_row, example_row]
        self.preview.set_data(headers, rows)

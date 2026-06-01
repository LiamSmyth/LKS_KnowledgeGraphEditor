"""None-backed field widget."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLineEdit, QWidget

from lks_utils.gui_qt.components.fields.field_validation_result import FieldValidationResult
from lks_utils.gui_qt.components.fields.q_field_base import QFieldBase


class QNoneField(QFieldBase):
    """Field widget for values that must remain None."""

    def _create_editor(self) -> QWidget:
        editor = QLineEdit(self)
        editor.setPlaceholderText("None")
        return editor

    def _connect_editor_signals(self) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        editor.textEdited.connect(self._on_text_edited)
        editor.returnPressed.connect(self._on_confirm_action)

    def _on_text_edited(self, text: str) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        sanitized = text.strip()
        if sanitized != text:
            editor.setText(sanitized)
        self._on_editor_value_changed(self._read_editor_value())

    def _read_editor_value(self) -> Any:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        return editor.text().strip()

    def _write_editor_value(self, value: Any) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        editor.setText("" if value is None else str(value))

    def _set_editor_editable(self, editable: bool) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        editor.setEnabled(editable)
        editor.setReadOnly(not editable)

    def validate_value(self, value: Any) -> FieldValidationResult:
        if value is None:
            return FieldValidationResult(is_valid=True, normalized_value=None)
        text = str(value).strip().lower()
        if text in {"", "none", "null"}:
            return FieldValidationResult(is_valid=True, normalized_value=None)
        return FieldValidationResult(is_valid=False, message="Value must be None.")

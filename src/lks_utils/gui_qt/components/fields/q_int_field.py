"""Integer-backed field widget."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLineEdit, QWidget

from lks_utils.gui_qt.components.fields.field_validation_result import FieldValidationResult
from lks_utils.gui_qt.components.fields.q_field_base import QFieldBase


class QIntField(QFieldBase):
    """Field widget for single integer values."""

    def _create_editor(self) -> QWidget:
        return QLineEdit(self)

    def _connect_editor_signals(self) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        editor.textEdited.connect(self._on_text_edited)
        editor.returnPressed.connect(self._on_confirm_action)

    def _on_text_edited(self, text: str) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        sanitized = self._sanitize_int_text(text)
        if sanitized != text:
            cursor = editor.cursorPosition()
            editor.setText(sanitized)
            editor.setCursorPosition(min(cursor, len(sanitized)))
        self._on_editor_value_changed(self._read_editor_value())

    def _read_editor_value(self) -> Any:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        return editor.text().strip()

    def _write_editor_value(self, value: Any) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        editor.setText(str(value))

    def _set_editor_editable(self, editable: bool) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        editor.setEnabled(editable)
        editor.setReadOnly(not editable)

    def validate_value(self, value: Any) -> FieldValidationResult:
        text = str(value).strip()
        if text in {"", "-"}:
            return FieldValidationResult(is_valid=False, message="Enter a valid integer.")
        try:
            return FieldValidationResult(is_valid=True, normalized_value=int(text))
        except ValueError:
            return FieldValidationResult(is_valid=False, message="Enter a valid integer.")

    @staticmethod
    def _sanitize_int_text(text: str) -> str:
        cleaned_chars: list[str] = []
        for index, char in enumerate(text):
            if char.isdigit():
                cleaned_chars.append(char)
            elif char == "-" and index == 0:
                cleaned_chars.append(char)
        return "".join(cleaned_chars)

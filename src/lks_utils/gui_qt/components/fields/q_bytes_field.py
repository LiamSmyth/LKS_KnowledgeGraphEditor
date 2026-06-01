"""Bytes-backed field widget."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLineEdit, QWidget

from lks_utils.gui_qt.components.fields.field_validation_result import FieldValidationResult
from lks_utils.gui_qt.components.fields.q_field_base import QFieldBase


class QBytesField(QFieldBase):
    """Field widget for bytes values encoded as hex text."""

    def _create_editor(self) -> QWidget:
        editor = QLineEdit(self)
        editor.setPlaceholderText("Hex bytes, example: deadbeef")
        return editor

    def _connect_editor_signals(self) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        editor.textEdited.connect(self._on_text_edited)
        editor.returnPressed.connect(self._on_confirm_action)

    def _on_text_edited(self, text: str) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        sanitized = self._sanitize_hex_text(text)
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
        if isinstance(value, bytes):
            editor.setText(value.hex())
        else:
            editor.setText(str(value).strip())

    def _set_editor_editable(self, editable: bool) -> None:
        editor = self._editor
        assert isinstance(editor, QLineEdit)
        editor.setEnabled(editable)
        editor.setReadOnly(not editable)

    def validate_value(self, value: Any) -> FieldValidationResult:
        text = self._sanitize_hex_text(str(value))
        if len(text) % 2 != 0:
            return FieldValidationResult(is_valid=False, message="Hex bytes require an even number of characters.")
        try:
            parsed = bytes.fromhex(text)
            return FieldValidationResult(is_valid=True, normalized_value=parsed)
        except ValueError:
            return FieldValidationResult(is_valid=False, message="Enter valid hexadecimal bytes.")

    @staticmethod
    def _sanitize_hex_text(text: str) -> str:
        return "".join(char for char in text.lower() if char in "0123456789abcdef")

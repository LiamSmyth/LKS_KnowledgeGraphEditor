"""Boolean-backed field widget."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QWidget

from lks_utils.gui_qt.components.fields.field_commit_reason import FieldCommitReason
from lks_utils.gui_qt.components.fields.q_field_base import QFieldBase


class QBoolField(QFieldBase):
    """Field widget for single boolean values."""

    def _create_editor(self) -> QWidget:
        checkbox = QCheckBox(self)
        checkbox.setText("")
        return checkbox

    def _connect_editor_signals(self) -> None:
        editor = self._editor
        assert isinstance(editor, QCheckBox)
        editor.checkStateChanged.connect(self._on_check_state_changed)

    def _on_check_state_changed(self, state: int) -> None:
        value = state == Qt.CheckState.Checked
        self._on_editor_value_changed(value)
        self.request_commit(FieldCommitReason.CONFIRM)

    def _read_editor_value(self) -> Any:
        editor = self._editor
        assert isinstance(editor, QCheckBox)
        return editor.isChecked()

    def _write_editor_value(self, value: Any) -> None:
        editor = self._editor
        assert isinstance(editor, QCheckBox)
        editor.setChecked(bool(value))

    def _set_editor_editable(self, editable: bool) -> None:
        editor = self._editor
        assert isinstance(editor, QCheckBox)
        editor.setEnabled(editable)

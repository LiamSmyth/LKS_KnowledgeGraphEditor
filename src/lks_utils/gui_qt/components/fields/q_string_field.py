"""String-backed field widget."""

from __future__ import annotations

from math import ceil
from typing import Any

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFontMetricsF, QTextOption
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QSizePolicy, QWidget

from lks_utils.gui_qt.components.fields.q_field_base import QFieldBase

_DEFAULT_MAX_VISIBLE_LINES = 3


def _estimate_wrapped_line_count(text: str, width: int, metrics: QFontMetricsF) -> int:
    """Estimate wrapped line count for the current widget width."""
    if width <= 1:
        return 1
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return 1

    available_width = max(1, width)
    line_height = max(1.0, metrics.lineSpacing())
    total_lines = 0
    for paragraph in normalized.split("\n"):
        if not paragraph:
            total_lines += 1
            continue
        wrap_rect = metrics.boundingRect(
            QRectF(0.0, 0.0, float(available_width), 100000.0),
            int(Qt.TextFlag.TextWordWrap),
            paragraph,
        )
        total_lines += max(1, ceil(wrap_rect.height() / line_height))
    return max(1, total_lines)


class _OverflowPlainTextEdit(QPlainTextEdit):
    """Single-value text editor that grows to a capped number of wrapped lines."""

    confirm_requested = Signal()

    def __init__(self, *, max_visible_lines: int = _DEFAULT_MAX_VISIBLE_LINES, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._max_visible_lines = max(1, max_visible_lines)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        self.document().setDocumentMargin(2.0)
        self.textChanged.connect(self._refresh_height)
        self._refresh_height()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
            if modifiers == Qt.KeyboardModifier.NoModifier:
                self.confirm_requested.emit()
                event.accept()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_height()

    def _refresh_height(self) -> None:
        metrics = QFontMetricsF(self.font())
        line_height = max(1, ceil(metrics.lineSpacing()))
        frame = self.frameWidth() * 2
        margin = ceil(self.document().documentMargin() * 2)
        line_count = _estimate_wrapped_line_count(
            self.toPlainText(),
            self.viewport().width(),
            metrics,
        )
        visible_lines = min(line_count, self._max_visible_lines)
        target_height = frame + margin + (visible_lines * line_height)
        self.setFixedHeight(target_height)
        scrollbar_policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if line_count > self._max_visible_lines
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(scrollbar_policy)


class QStringField(QFieldBase):
    """Field widget for string values with optional capped multiline overflow."""

    def __init__(
        self,
        default_value: Any,
        *,
        auto_multiline_overflow: bool = False,
        max_visible_lines: int = _DEFAULT_MAX_VISIBLE_LINES,
        commit_policy=None,
        parent: QWidget | None = None,
    ) -> None:
        self._auto_multiline_overflow = auto_multiline_overflow
        self._max_visible_lines = max(1, max_visible_lines)
        super().__init__(
            default_value,
            commit_policy=commit_policy,
            parent=parent,
        )

    def auto_multiline_overflow_enabled(self) -> bool:
        """Return whether overflow text can expand into a capped multiline editor."""
        return self._auto_multiline_overflow

    def _create_editor(self) -> QWidget:
        if self._auto_multiline_overflow:
            return _OverflowPlainTextEdit(
                max_visible_lines=self._max_visible_lines,
                parent=self,
            )
        editor = QLineEdit(self)
        # Use project-owned clear/revert controls to avoid native clear-glyph flicker.
        editor.setClearButtonEnabled(False)
        return editor

    def _connect_editor_signals(self) -> None:
        editor = self._editor
        if isinstance(editor, _OverflowPlainTextEdit):
            editor.textChanged.connect(
                lambda: self._on_editor_value_changed(
                    self._read_editor_value())
            )
            editor.confirm_requested.connect(self._on_confirm_action)
            return
        assert isinstance(editor, QLineEdit)
        editor.textChanged.connect(self._on_editor_value_changed)
        editor.returnPressed.connect(self._on_confirm_action)

    def _read_editor_value(self) -> Any:
        editor = self._editor
        if isinstance(editor, _OverflowPlainTextEdit):
            return editor.toPlainText()
        assert isinstance(editor, QLineEdit)
        return editor.text()

    def _write_editor_value(self, value: Any) -> None:
        editor = self._editor
        if isinstance(editor, _OverflowPlainTextEdit):
            editor.setPlainText(str(value))
            return
        assert isinstance(editor, QLineEdit)
        editor.setText(str(value))

    def _set_editor_editable(self, editable: bool) -> None:
        editor = self._editor
        if isinstance(editor, _OverflowPlainTextEdit):
            editor.setEnabled(editable)
            editor.setReadOnly(not editable)
            return
        assert isinstance(editor, QLineEdit)
        editor.setEnabled(editable)
        editor.setReadOnly(not editable)
        editor.setClearButtonEnabled(editable)

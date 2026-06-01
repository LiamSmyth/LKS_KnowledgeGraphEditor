"""Base classes and formatting helpers for presentation-only value displays."""

from __future__ import annotations

from math import ceil
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFontMetricsF, QTextOption
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget

from lks_utils.theme.color import Color

_DEFAULT_MAX_VISIBLE_LINES = 3


def format_display_value(value: Any) -> str:
    """Convert a Python value into compact display text."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, Color):
        return f"rgba({value.r}, {value.g}, {value.b}, {value.a})"
    if isinstance(value, (tuple, list)):
        return "[" + ", ".join(format_display_value(item) for item in value) + "]"
    return str(value)


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


class _OverflowTextDisplay(QPlainTextEdit):
    """Read-only text display that grows to a capped number of wrapped lines."""

    def __init__(self, *, max_visible_lines: int = _DEFAULT_MAX_VISIBLE_LINES, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._max_visible_lines = max(1, max_visible_lines)
        self.setReadOnly(True)
        self.setFrameStyle(0)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        self.document().setDocumentMargin(0.0)
        self.setStyleSheet(
            "QPlainTextEdit { background: transparent; border: 0; padding: 0; margin: 0; }"
        )
        self.textChanged.connect(self._refresh_height)
        self._refresh_height()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_height()

    def _refresh_height(self) -> None:
        metrics = QFontMetricsF(self.font())
        line_height = max(1, ceil(metrics.lineSpacing()))
        line_count = _estimate_wrapped_line_count(
            self.toPlainText(),
            self.viewport().width(),
            metrics,
        )
        visible_lines = min(line_count, self._max_visible_lines)
        target_height = visible_lines * line_height
        self.setFixedHeight(target_height)
        scrollbar_policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if line_count > self._max_visible_lines
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(scrollbar_policy)


class QValueDisplayBase(QWidget):
    """Read-only value display with no input field chrome."""

    def __init__(
        self,
        value: Any = None,
        *,
        parent: QWidget | None = None,
        auto_multiline_overflow: bool = False,
        max_visible_lines: int = _DEFAULT_MAX_VISIBLE_LINES,
    ) -> None:
        super().__init__(parent)
        self._value: Any = None
        self._auto_multiline_overflow = auto_multiline_overflow

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._label: QLabel | None = None
        if auto_multiline_overflow:
            self._display_widget: QWidget = _OverflowTextDisplay(
                max_visible_lines=max_visible_lines,
                parent=self,
            )
        else:
            self._label = QLabel(self)
            self._label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            self._label.setWordWrap(True)
            self._label.setObjectName("valueDisplayLabel")
            self._display_widget = self._label
        layout.addWidget(self._display_widget)

        self.set_value(value)

    def auto_multiline_overflow_enabled(self) -> bool:
        """Return whether overflow text can expand into a capped multiline display."""
        return self._auto_multiline_overflow

    def value(self) -> Any:
        """Return the raw value represented by this display."""
        return self._value

    def set_value(self, value: Any) -> None:
        """Set the raw value and refresh display text."""
        self._value = value
        text = self.format_value(value)
        if self._label is not None:
            self._label.setText(text)
            return
        display = self._display_widget
        assert isinstance(display, _OverflowTextDisplay)
        display.setPlainText(text)

    def format_value(self, value: Any) -> str:
        """Format raw value for display text."""
        return format_display_value(value)


__all__ = ["QValueDisplayBase", "format_display_value"]

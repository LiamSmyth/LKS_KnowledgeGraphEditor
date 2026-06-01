"""Generic three-column read-only property list display widget."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.theme.palette import PALETTE


class QPropertyListDisplayWidget(QFrame):
    """Three-column read-only property list with row and value overflow policies."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        object_name: str = "property_list_display",
        label_width_px: int = 84,
        type_width_px: int = 72,
        max_text_lines: int = 3,
        long_text_wrap_trigger_chars: int = 72,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)

        self._label_width_px = max(1, int(label_width_px))
        self._type_width_px = max(1, int(type_width_px))
        self._max_text_lines = max(1, int(max_text_lines))
        self._long_text_wrap_trigger_chars = max(
            1, int(long_text_wrap_trigger_chars))

        self._row_widgets: list[QWidget] = []
        self._style_bg = PALETTE["canvas_bg"]
        self._style_border = PALETTE["minimap_painted_outline"]
        self._style_row_sep = PALETTE["dot_grid_strong"]
        self._style_name_text = PALETTE["selection_marquee_alt"]
        self._style_type_text = PALETTE["layer_row_bg"]
        self._style_value_text = PALETTE["selection_marquee"]
        self._style_ref_text = self._style_value_text
        self._style_literal_text = self._style_value_text

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._rows_host = QWidget(self._scroll)
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(6, 4, 6, 4)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch(1)
        self._scroll.setWidget(self._rows_host)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._scroll)

        self._apply_style()

    def set_style_colors(
        self,
        *,
        background: str,
        border: str,
        row_separator: str,
        name_text: str,
        type_text: str,
        value_text: str,
        reference_text: str | None = None,
        literal_text: str | None = None,
    ) -> None:
        self._style_bg = background
        self._style_border = border
        self._style_row_sep = row_separator
        self._style_name_text = name_text
        self._style_type_text = type_text
        self._style_value_text = value_text
        self._style_ref_text = reference_text if reference_text is not None else value_text
        self._style_literal_text = literal_text if literal_text is not None else value_text
        self._apply_style()

    def sync_from_model(
        self,
        *,
        rows: Sequence[Any],
        scroll_offset_rows: int,
        max_visible_rows: int,
    ) -> None:
        _ = max(1, int(max_visible_rows))
        self._row_widgets = []
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Remove stale row widgets from the paint tree immediately so
                # incremental snapshots never capture old+new rows together.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        if not rows:
            self._scroll.verticalScrollBar().setValue(0)
            return

        for row in rows:
            row_widget = self._build_row_widget(row)
            self._row_widgets.append(row_widget)
            self._rows_layout.insertWidget(
                self._rows_layout.count() - 1, row_widget)

        self._apply_scroll_offset(scroll_offset_rows)

    def _build_row_widget(self, row: Any) -> QFrame:
        row_frame = QFrame(self)
        row_frame.setObjectName("property_row")

        layout = QHBoxLayout(row_frame)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        label_text = str(getattr(row, "label", ""))
        value_type = str(getattr(row, "value_type", ""))
        has_type = bool(value_type.strip())
        value_kind = self._resolve_value_kind(row)
        value_text = self._resolve_value_text(row)

        name_label = QLabel(label_text, row_frame)
        name_label.setObjectName("prop_name")
        name_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        name_label.setFixedWidth(self._label_width_px)

        type_label = QLabel(f"({value_type})" if has_type else "", row_frame)
        type_label.setObjectName("prop_type")
        type_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        type_label.setFixedWidth(self._type_width_px if has_type else 0)
        type_label.setVisible(has_type)

        value_widget = self._build_value_widget(
            value_text=value_text,
            value_kind=value_kind,
            parent=row_frame,
        )

        layout.addWidget(name_label, stretch=0)
        if has_type:
            layout.addWidget(type_label, stretch=0)
        layout.addWidget(value_widget, stretch=1)

        return row_frame

    def _resolve_value_text(self, row: Any) -> str:
        return str(getattr(row, "value", ""))

    def _resolve_value_kind(self, row: Any) -> str:
        return str(getattr(row, "value_kind", "plain")).lower()

    def _build_value_widget(
        self,
        *,
        value_text: str,
        value_kind: str,
        parent: QWidget,
    ) -> QWidget:
        if self._should_use_multiline_editor(value_text):
            editor = QPlainTextEdit(parent)
            editor.setObjectName("prop_value_multiline")
            editor.setReadOnly(True)
            editor.setPlainText(value_text)
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            editor.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            editor.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            editor.setFrameShape(QFrame.Shape.NoFrame)
            editor.setProperty("valueKind", value_kind)
            line_height = QFontMetrics(editor.font()).lineSpacing()
            target_height = (line_height * self._max_text_lines) + 6
            editor.setFixedHeight(target_height)
            return editor

        label = QLabel(value_text, parent)
        label.setObjectName("prop_value")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft |
                           Qt.AlignmentFlag.AlignTop)
        label.setProperty("valueKind", value_kind)
        return label

    def _should_use_multiline_editor(self, text: str) -> bool:
        return "\n" in text or len(text) > self._long_text_wrap_trigger_chars

    def _apply_scroll_offset(self, row_offset: int) -> None:
        if not self._row_widgets:
            self._scroll.verticalScrollBar().setValue(0)
            return
        index = max(0, min(int(row_offset), len(self._row_widgets) - 1))
        self._scroll.ensureWidgetVisible(self._row_widgets[index], 0, 0)

    def _apply_style(self) -> None:
        object_name = self.objectName()
        self.setStyleSheet(
            f"QFrame#{object_name} {{"
            f"background: {self._style_bg};"
            f"border: 1px solid {self._style_border};"
            "border-radius: 3px;"
            "}"
            f"QFrame#{object_name} QFrame#property_row {{"
            f"border-bottom: 1px solid {self._style_row_sep};"
            "}"
            f"QFrame#{object_name} QFrame#property_row:last-child {{"
            "border-bottom: none;"
            "}"
            f"QFrame#{object_name} QLabel#prop_name {{"
            f"color: {self._style_name_text};"
            "font-size: 11px;"
            "}"
            f"QFrame#{object_name} QLabel#prop_type {{"
            f"color: {self._style_type_text};"
            "font-size: 11px;"
            "}"
            f"QFrame#{object_name} QLabel#prop_value {{"
            f"color: {self._style_value_text};"
            "font-size: 11px;"
            "}"
            f"QFrame#{object_name} QPlainTextEdit#prop_value_multiline {{"
            f"color: {self._style_value_text};"
            "font-size: 11px;"
            "padding: 0;"
            "margin: 0;"
            "border: none;"
            "background: transparent;"
            "}"
            f"QFrame#{object_name} QLabel#prop_value[valueKind=\"reference\"] {{"
            f"color: {self._style_ref_text};"
            "}"
            f"QFrame#{object_name} QLabel#prop_value[valueKind=\"literal\"] {{"
            f"color: {self._style_literal_text};"
            "}"
            f"QFrame#{object_name} QPlainTextEdit#prop_value_multiline[valueKind=\"reference\"] {{"
            f"color: {self._style_ref_text};"
            "}"
            f"QFrame#{object_name} QPlainTextEdit#prop_value_multiline[valueKind=\"literal\"] {{"
            f"color: {self._style_literal_text};"
            "}"
        )


__all__ = ["QPropertyListDisplayWidget"]

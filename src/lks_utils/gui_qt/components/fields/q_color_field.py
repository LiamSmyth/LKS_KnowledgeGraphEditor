"""Color-backed field widget with a compact swatch picker."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from lks_utils.gui_qt.components.fields.field_validation_result import FieldValidationResult
from lks_utils.gui_qt.components.fields.q_field_base import QFieldBase
from lks_utils.gui_qt.widgets.compact_color_editor_widget import QCompactColorEditorWidget
from lks_utils.gui_qt.theme.color_adapter import from_qcolor, to_qcolor
from lks_utils.theme.color import Color


class _ColorSwatchEditor(QWidget):
    """Clickable swatch that previews RGB plus alpha."""

    clicked = Signal()

    def __init__(self, *, show_alpha: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = Color(255, 255, 255, 255)
        self._show_alpha = show_alpha
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(24)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_color(self, color: Color) -> None:
        self._color = color
        self.update()

    def set_show_alpha(self, show_alpha: bool) -> None:
        self._show_alpha = show_alpha
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        rect = self.rect().adjusted(0, 0, -1, -1)
        rgb_width = max(1, int(rect.width() * 0.75))
        rgb_rect = rect.adjusted(0, 0, -(rect.width() - rgb_width), 0)
        alpha_rect = rect.adjusted(rgb_width, 0, 0, 0)

        fill_opacity = 0.4 if not self.isEnabled() else 1.0
        painter.setOpacity(fill_opacity)
        painter.fillRect(rgb_rect, to_qcolor(self._color.with_alpha(255)))
        if self._show_alpha:
            alpha = self._color.a
            gray = QColor(alpha, alpha, alpha)
            painter.fillRect(alpha_rect, gray)
        else:
            painter.fillRect(alpha_rect, to_qcolor(
                self._color.with_alpha(255)))

        painter.setOpacity(1.0)
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.drawRect(rect)
        if self._show_alpha and alpha_rect.width() > 0:
            painter.drawLine(
                alpha_rect.left(), alpha_rect.top(), alpha_rect.left(), alpha_rect.bottom()
            )
        painter.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _CompactColorPickerDialog(QDialog):
    """Modal compact color picker with explicit OK/Cancel semantics."""

    def __init__(
        self,
        *,
        initial_color: Color,
        show_alpha: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose Color")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._picker = QCompactColorEditorWidget(self)
        self._picker.set_color(to_qcolor(initial_color))
        layout.addWidget(self._picker)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._show_alpha = show_alpha
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def selected_color(self) -> Color:
        qcolor = self._picker.color()
        color = from_qcolor(qcolor)
        if not self._show_alpha:
            return color.with_alpha(255)
        return color


class QColorField(QFieldBase):
    """Field widget for RGBA colors shown as a compact swatch."""

    def __init__(
        self,
        default_value: Color,
        *,
        show_alpha: bool = True,
        use_compact_picker_dialog: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        self._show_alpha = show_alpha
        self._use_compact_picker_dialog = use_compact_picker_dialog
        self._popup_menu: QMenu | None = None
        self._picker_dialog: _CompactColorPickerDialog | None = None
        super().__init__(default_value, parent=parent)

    def _create_editor(self) -> QWidget:
        return _ColorSwatchEditor(show_alpha=self._show_alpha, parent=self)

    def _connect_editor_signals(self) -> None:
        editor = self._editor
        assert isinstance(editor, _ColorSwatchEditor)
        editor.clicked.connect(self._open_color_picker)

    def _open_color_picker(self) -> None:
        if self._use_compact_picker_dialog:
            self._open_compact_picker_dialog()
            return

        menu = QMenu(self)
        menu.setObjectName("color_field_picker_menu")
        menu.setWindowTitle("Choose Color")

        dialog = QColorDialog(to_qcolor(self.value()), menu)
        dialog.setOption(
            QColorDialog.ColorDialogOption.ShowAlphaChannel, self._show_alpha)
        dialog.setOption(
            QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setOption(QColorDialog.ColorDialogOption.NoButtons, True)
        dialog.setWindowTitle("Choose Color")
        dialog.setMinimumWidth(320)
        dialog.setMinimumHeight(280)

        action = QWidgetAction(menu)
        action.setDefaultWidget(dialog)
        menu.addAction(action)

        dialog.currentColorChanged.connect(self._on_dialog_color_changed)
        dialog.colorSelected.connect(self._on_dialog_color_selected)
        menu.aboutToHide.connect(dialog.deleteLater)
        menu.aboutToHide.connect(menu.deleteLater)
        self._popup_menu = menu

        anchor = self.mapToGlobal(self._editor.rect().bottomLeft())
        menu.popup(QPoint(anchor.x(), anchor.y()))

    def _open_compact_picker_dialog(self) -> None:
        dialog = _CompactColorPickerDialog(
            initial_color=self.value(),
            show_alpha=self._show_alpha,
            parent=self.window(),
        )
        self._picker_dialog = dialog

        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            color = dialog.selected_color()
            self._set_editor_value(color)
            self._on_editor_value_changed(color)
            self._on_confirm_action()

        self._picker_dialog = None
        dialog.deleteLater()

    def _on_dialog_color_changed(self, qcolor: QColor) -> None:
        color = from_qcolor(qcolor)
        self._set_editor_value(color)
        self._on_editor_value_changed(color)

    def _on_dialog_color_selected(self, qcolor: QColor) -> None:
        color = from_qcolor(qcolor)
        self._set_editor_value(color)
        self._on_editor_value_changed(color)
        self._on_confirm_action()
        if self._popup_menu is not None:
            self._popup_menu.close()

    def _read_editor_value(self) -> Any:
        editor = self._editor
        assert isinstance(editor, _ColorSwatchEditor)
        return editor._color

    def _write_editor_value(self, value: Any) -> None:
        editor = self._editor
        assert isinstance(editor, _ColorSwatchEditor)
        color = self._coerce_color(value)
        if color is None:
            color = self._default_value
        editor.set_color(color)

    def _set_editor_editable(self, editable: bool) -> None:
        self._editor.setEnabled(editable)

    def validate_value(self, value: Any) -> FieldValidationResult:
        color = self._coerce_color(value)
        if color is None:
            return FieldValidationResult(is_valid=False, message="Enter a valid color.")
        return FieldValidationResult(is_valid=True, normalized_value=color)

    def _coerce_color(self, value: Any) -> Color | None:
        if isinstance(value, Color):
            return value
        if isinstance(value, QColor):
            if not value.isValid():
                return None
            return from_qcolor(value)
        if isinstance(value, str):
            color = QColor(value)
            if color.isValid():
                return from_qcolor(color)
        return None


__all__ = ["QColorField"]

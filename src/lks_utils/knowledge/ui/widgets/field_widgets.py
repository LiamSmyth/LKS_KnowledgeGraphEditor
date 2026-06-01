"""Reusable square field widgets for the Knowledge UI."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from lks_utils.gui_qt.components.fields import (
    FieldCommitPolicy,
    QBoolField,
    QColorField,
    QFieldBase,
    QFloatField,
    QIntField,
    QStringField,
)
from lks_utils.gui_qt.widgets.square_icon_button import QSquareIconButton
from lks_utils.knowledge.models.node_slot import type_default_value
from lks_utils.knowledge.default_theme import (
    FIELD_BUTTON_BG,
    FIELD_BUTTON_BORDER,
    FIELD_BUTTON_DISABLED_BORDER,
    FIELD_BUTTON_DISABLED_TEXT,
    FIELD_BUTTON_HOVER_BORDER,
    FIELD_BUTTON_PRESSED_BG,
    FIELD_BUTTON_PRESSED_BORDER,
    FIELD_BUTTON_TEXT,
    FIELD_INPUT_BG,
    FIELD_INPUT_BORDER,
    FIELD_INPUT_FOCUS_BORDER,
    FIELD_INPUT_TEXT,
    FIELD_LABEL_COLOR,
    FIELD_MONO_FONT_FAMILY,
    FIELD_ROW_BG,
)
from lks_utils.gui_qt.theme.icon_recolor import recolor_svg
from lks_utils.theme.color import Color

_KNOWLEDGE_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "icons"
_SVG_ICON_CACHE: dict[tuple[str, str], QIcon] = {}
FIELD_ROW_HEIGHT: int = 27

SIMPLE_FIELD_STYLE: str = (
    f"QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {FIELD_INPUT_BG};"
    f" color: {FIELD_INPUT_TEXT}; border: 1px solid {FIELD_INPUT_BORDER};"
    f" border-radius: 0; font-size: 11px; padding: 1px 3px; min-height: {FIELD_ROW_HEIGHT}px; max-height: {FIELD_ROW_HEIGHT}px; }}"
    f"QPlainTextEdit {{ background: {FIELD_INPUT_BG}; color: {FIELD_INPUT_TEXT};"
    f" border: 1px solid {FIELD_INPUT_BORDER}; border-radius: 0; font-size: 11px; padding: 1px 3px; }}"
    f"QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border: 1px solid {FIELD_INPUT_FOCUS_BORDER}; }}"
    f"QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QPlainTextEdit:disabled {{"
    f" background: {FIELD_ROW_BG}; color: {FIELD_BUTTON_DISABLED_TEXT}; border: 1px solid {FIELD_BUTTON_DISABLED_BORDER}; }}"
)
SIMPLE_BUTTON_STYLE: str = (
    f"QPushButton {{ background: {FIELD_BUTTON_BG}; color: {FIELD_BUTTON_TEXT};"
    f" border: 1px solid {FIELD_BUTTON_BORDER}; border-radius: 0; padding: 0; }}"
    f"QPushButton:hover {{ border: 1px solid {FIELD_BUTTON_HOVER_BORDER}; }}"
    f"QPushButton:pressed {{ background: {FIELD_BUTTON_PRESSED_BG}; border: 1px solid {FIELD_BUTTON_PRESSED_BORDER}; }}"
    f"QPushButton:disabled {{ color: {FIELD_BUTTON_DISABLED_TEXT}; border: 1px solid {FIELD_BUTTON_DISABLED_BORDER}; }}"
)


def _square_button_style(size: int) -> str:
    """Return button style with explicit square size constraints."""
    return (
        SIMPLE_BUTTON_STYLE
        + f"QPushButton {{ min-width: {size}px; max-width: {size}px; min-height: {size}px; max-height: {size}px; }}"
    )


BASE_VALUE_TYPES: tuple[str, ...] = (
    "any",
    "object",
    "string",
    "str",
    "int",
    "integer",
    "float",
    "number",
    "complex",
    "bool",
    "boolean",
    "NoneType",
    "bytes",
    "list",
    "tuple",
    "dict",
    "set",
    "color",
    "vector2",
    "vector3",
    "vector4",
    "json",
)


def simple_mono_font() -> QFont:
    """Return the monotype font used by Knowledge field controls."""
    font = QFont(FIELD_MONO_FONT_FAMILY)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(10)
    return font


def style_simple_field(widget: QWidget) -> None:
    """Apply the Knowledge square-field visual style."""
    widget.setStyleSheet(SIMPLE_FIELD_STYLE)
    widget.setFont(simple_mono_font())
    # Allow field columns to collapse before trailing action buttons do.
    widget.setMinimumWidth(0)


def _icon_from_svg(svg_name: str, *, color: str = FIELD_BUTTON_TEXT) -> QIcon:
    """Load and recolor a Knowledge SVG icon; cache by name + color."""
    cache_key = (svg_name, color)
    cached = _SVG_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    svg_path = _KNOWLEDGE_DATA_DIR / svg_name
    svg_text = svg_path.read_text(encoding="utf-8")
    recolored = recolor_svg(svg_text, fill=color, stroke=color)
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(recolored.encode("utf-8")), "SVG")
    icon = QIcon(pixmap)
    _SVG_ICON_CACHE[cache_key] = icon
    return icon


def make_square_svg_icon(svg_name: str, *, color: str = FIELD_BUTTON_TEXT) -> QIcon:
    """Return a themed recolored icon from a Knowledge SVG asset."""
    return _icon_from_svg(svg_name, color=color)


def make_field_label(text: str, parent: QWidget | None = None, *, width: int = 78) -> QLabel:
    """Create a fixed-width right-aligned Knowledge field label."""
    label = QLabel(text + ":", parent)
    label.setFixedWidth(width)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft |
                       Qt.AlignmentFlag.AlignVCenter)
    label.setStyleSheet(
        f"QLabel {{ color: {FIELD_LABEL_COLOR}; font-size: 10px; }}"
        f"QLabel:disabled {{ color: {FIELD_BUTTON_DISABLED_TEXT}; }}"
    )
    label.setFont(simple_mono_font())
    return label


class ClearFieldButton(QSquareIconButton):
    """Constant-size square button used to clear a field value."""

    def __init__(self, tooltip: str = "Clear value", parent: QWidget | None = None) -> None:
        super().__init__(FIELD_ROW_HEIGHT, tooltip=tooltip, parent=parent)
        self.setObjectName("clear_field_button")
        self.setFont(simple_mono_font())
        self.set_square_icon(_icon_from_svg("kwb_btn_clear.svg"))

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(FIELD_ROW_HEIGHT, FIELD_ROW_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(FIELD_ROW_HEIGHT, FIELD_ROW_HEIGHT)


class RevertFieldButton(QSquareIconButton):
    """Constant-size square button used to revert a field value to default."""

    def __init__(self, tooltip: str = "Revert to default", parent: QWidget | None = None) -> None:
        super().__init__(FIELD_ROW_HEIGHT, tooltip=tooltip, parent=parent)
        self.setObjectName("revert_field_button")
        self.setFont(simple_mono_font())
        self.set_square_icon(_icon_from_svg("kwb_btn_revert.svg"))

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(FIELD_ROW_HEIGHT, FIELD_ROW_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(FIELD_ROW_HEIGHT, FIELD_ROW_HEIGHT)


def make_simple_button(label: str, tooltip: str = "", parent: QWidget | None = None) -> QPushButton:
    """Create a square-styled Knowledge button."""
    button = QPushButton(label, parent)
    button.setFixedHeight(FIELD_ROW_HEIGHT)
    button.setMinimumWidth(24)
    button.setMaximumWidth(80)
    button.setFont(simple_mono_font())
    button.setStyleSheet(SIMPLE_BUTTON_STYLE)
    button.setToolTip(tooltip or label)
    return button


def make_square_svg_button(
    svg_name: str,
    *,
    tooltip: str,
    parent: QWidget | None = None,
    size: int = FIELD_ROW_HEIGHT,
) -> QPushButton:
    """Create a square icon button from a Knowledge SVG with themed coloring."""
    button = QSquareIconButton(size, tooltip=tooltip, parent=parent)
    button.set_square_icon(make_square_svg_icon(svg_name))
    return button


def make_add_action_button(
    *,
    tooltip: str = "Add",
    parent: QWidget | None = None,
    size: int = FIELD_ROW_HEIGHT,
) -> QPushButton:
    """Create a standard Knowledge add icon button."""
    return make_square_svg_button(
        "kwb_btn_add.svg",
        tooltip=tooltip,
        parent=parent,
        size=size,
    )


def make_delete_action_button(
    *,
    tooltip: str = "Delete",
    parent: QWidget | None = None,
    size: int = FIELD_ROW_HEIGHT,
) -> QPushButton:
    """Create a standard Knowledge delete icon button."""
    return make_square_svg_button(
        "kwb_btn_delete.svg",
        tooltip=tooltip,
        parent=parent,
        size=size,
    )


def make_pick_action_button(
    *,
    tooltip: str = "Pick",
    parent: QWidget | None = None,
    size: int = FIELD_ROW_HEIGHT,
) -> QPushButton:
    """Create a standard Knowledge pick-reference icon button."""
    return make_square_svg_button(
        "kwb_btn_pick_ref.svg",
        tooltip=tooltip,
        parent=parent,
        size=size,
    )


class TypeComboBox(QComboBox):
    """Dropdown-backed selector for primitive types and repository Type categories."""

    def __init__(
        self,
        type_names: list[str],
        current: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setEditable(False)
        style_simple_field(self)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        values = list(BASE_VALUE_TYPES)
        for name in sorted({item for item in type_names if item}):
            if name not in values:
                values.append(name)
        for value in values:
            self.addItem(value, value)
        if current:
            index = self.findData(current)
            if index < 0:
                self.addItem(current, current)
                index = self.findData(current)
            self.setCurrentIndex(index)

    def value(self) -> str:
        """Return the selected type token."""
        data = self.currentData()
        if isinstance(data, str):
            return data
        return self.currentText().strip()


PrimitiveFieldFactory = Callable[[object, QWidget | None], QWidget]


_SHARED_COMMIT_POLICY = FieldCommitPolicy(commit_on_focus_out=True)


def _to_text(value: object) -> str:
    return "" if value is None else str(value)


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def _to_float(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _to_color(value: object) -> Color:
    if isinstance(value, Color):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("#"):
            if len(text) == 7:
                try:
                    return Color.from_hex(text)
                except ValueError:
                    return Color(255, 255, 255, 255)
            if len(text) == 9:
                try:
                    return Color.from_hex(text)
                except ValueError:
                    return Color(255, 255, 255, 255)
    return Color(255, 255, 255, 255)


def _make_string_field(
    value: object,
    parent: QWidget | None,
    *,
    auto_multiline_overflow: bool = False,
) -> QWidget:
    return QStringField(
        default_value=_to_text(value),
        commit_policy=_SHARED_COMMIT_POLICY,
        parent=parent,
        auto_multiline_overflow=auto_multiline_overflow,
    )


def _make_int_field(value: object, parent: QWidget | None) -> QWidget:
    return QIntField(default_value=_to_int(value), commit_policy=_SHARED_COMMIT_POLICY, parent=parent)


def _make_float_field(value: object, parent: QWidget | None) -> QWidget:
    return QFloatField(default_value=_to_float(value), commit_policy=_SHARED_COMMIT_POLICY, parent=parent)


def _make_bool_field(value: object, parent: QWidget | None) -> QWidget:
    return QBoolField(default_value=_to_bool(value), commit_policy=_SHARED_COMMIT_POLICY, parent=parent)


def _make_color_field(value: object, parent: QWidget | None) -> QWidget:
    return QColorField(default_value=_to_color(value), commit_policy=_SHARED_COMMIT_POLICY, parent=parent)


PRIMITIVE_FIELD_FACTORIES: dict[str, PrimitiveFieldFactory] = {
    "any": _make_string_field,
    "object": _make_string_field,
    "string": _make_string_field,
    "str": _make_string_field,
    "json": _make_string_field,
    "int": _make_int_field,
    "integer": _make_int_field,
    "float": _make_float_field,
    "number": _make_float_field,
    "complex": _make_string_field,
    "bool": _make_bool_field,
    "boolean": _make_bool_field,
    "nonetype": _make_string_field,
    "bytes": _make_string_field,
    "list": _make_string_field,
    "tuple": _make_string_field,
    "dict": _make_string_field,
    "set": _make_string_field,
    "color": _make_color_field,
    "vector2": _make_string_field,
    "vector3": _make_string_field,
    "vector4": _make_string_field,
}


def make_primitive_field(
    value_type: str | None,
    value: object,
    parent: QWidget | None = None,
    *,
    auto_multiline_overflow: bool = False,
) -> QWidget:
    """Build the field widget mapped from a primitive type token."""
    key = (value_type or "string").strip().lower()
    factory = PRIMITIVE_FIELD_FACTORIES.get(key, _make_string_field)
    if factory is _make_string_field:
        widget = factory(
            value,
            parent,
            auto_multiline_overflow=auto_multiline_overflow,
        )
    else:
        widget = factory(value, parent)
    vertical_policy = QSizePolicy.Policy.Fixed
    if isinstance(widget, QStringField) and widget.auto_multiline_overflow_enabled():
        vertical_policy = QSizePolicy.Policy.Preferred
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, vertical_policy)
    return widget


def field_value(widget: QWidget) -> object:
    """Return a value from one of the reusable Knowledge field widgets."""
    if isinstance(widget, QFieldBase):
        value = widget.value()
        if isinstance(value, Color):
            return f"#{value.r:02x}{value.g:02x}{value.b:02x}"
        return value
    value_method = getattr(widget, "value", None)
    if callable(value_method):
        return value_method()
    return None


class SwappableDefaultField(QWidget):
    """Default-value editor whose inner widget swaps when the property type changes.

    The inner widget is built from :func:`make_primitive_field` and is replaced
    whenever :meth:`set_type` is called.  :meth:`value` delegates to
    :func:`field_value` on the current inner widget.
    """

    value_changed = Signal(object)
    committed = Signal(object)

    def __init__(
        self,
        value_type: str,
        value: object = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._inner_layout = QHBoxLayout(self)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(0)
        self._current: QWidget | None = None
        self._set_inner(value_type, value)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_type(self, value_type: str) -> None:
        """Replace the inner widget for *value_type*, pre-filling with its default."""
        self._set_inner(value_type, type_default_value(value_type))

    def value(self) -> object:
        """Return the current value from the inner widget."""
        if self._current is None:
            return None
        return field_value(self._current)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_inner(self, value_type: str, value: object) -> None:
        if self._current is not None:
            self._inner_layout.removeWidget(self._current)
            self._current.hide()
            self._current.deleteLater()
        self._current = make_primitive_field(value_type, value, self)
        style_simple_field(self._current)
        self._current.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        key = (value_type or "string").strip().lower()
        if key in {"any", "object", "string", "str", "json", "complex", "bytes", "list", "tuple", "dict", "set", "vector2", "vector3", "vector4"}:
            line_edit = self._current.findChild(QLineEdit)
            if line_edit is not None and not line_edit.placeholderText():
                line_edit.setPlaceholderText("default")
        self._inner_layout.addWidget(self._current)
        # Forward value_changed from the inner widget if it exposes one.
        inner_signal = getattr(self._current, "value_changed", None)
        if inner_signal is not None:
            inner_signal.connect(
                lambda _: self.value_changed.emit(self.value()))
        committed_signal = getattr(self._current, "committed", None)
        if committed_signal is not None:
            committed_signal.connect(
                lambda value, *_args: self.committed.emit(value))


__all__ = [
    "BASE_VALUE_TYPES",
    "ClearFieldButton",
    "TypeComboBox",
    "make_add_action_button",
    "make_delete_action_button",
    "make_field_label",
    "make_pick_action_button",
    "make_primitive_field",
    "make_square_svg_button",
    "make_simple_button",
    "field_value",
    "simple_mono_font",
    "style_simple_field",
]
__all__ += ["SwappableDefaultField", "type_default_value"]

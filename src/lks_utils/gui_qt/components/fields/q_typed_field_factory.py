"""Helpers to build primitive field widgets from type names."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from lks_utils.gui_qt.components.fields.q_bool_field import QBoolField
from lks_utils.gui_qt.components.fields.q_bytes_field import QBytesField
from lks_utils.gui_qt.components.fields.q_color_field import QColorField
from lks_utils.gui_qt.components.fields.q_float_field import QFloatField
from lks_utils.gui_qt.components.fields.q_int_field import QIntField
from lks_utils.gui_qt.components.fields.q_string_field import QStringField
from lks_utils.gui_qt.components.fields.q_vector2_field import QVector2Field
from lks_utils.gui_qt.components.fields.q_vector3_field import QVector3Field
from lks_utils.gui_qt.components.fields.q_vector4_field import QVector4Field
from lks_utils.theme.color import Color

SUPPORTED_VALUE_TYPES: tuple[str, ...] = (
    "string",
    "int",
    "float",
    "bool",
    "bytes",
    "color",
    "vector2",
    "vector3",
    "vector4",
)


def default_for_type(type_name: str) -> Any:
    key = type_name.strip().lower()
    if key == "string":
        return ""
    if key == "int":
        return 0
    if key == "float":
        return 0.0
    if key == "bool":
        return False
    if key == "bytes":
        return b""
    if key == "color":
        return Color(255, 255, 255, 255)
    if key == "vector2":
        return (0.0, 0.0)
    if key == "vector3":
        return (0.0, 0.0, 0.0)
    if key == "vector4":
        return (0.0, 0.0, 0.0, 0.0)
    return ""


def make_field_for_type(type_name: str, *, default_value: Any | None = None, parent: QWidget | None = None) -> QWidget:
    key = type_name.strip().lower()
    value = default_for_type(key) if default_value is None else default_value

    if key == "int":
        return QIntField(default_value=value, parent=parent)
    if key == "float":
        return QFloatField(default_value=value, parent=parent)
    if key == "bool":
        return QBoolField(default_value=value, parent=parent)
    if key == "bytes":
        return QBytesField(default_value=value, parent=parent)
    if key == "color":
        return QColorField(default_value=value, parent=parent)
    if key == "vector2":
        return QVector2Field(default_value=value, parent=parent)
    if key == "vector3":
        return QVector3Field(default_value=value, parent=parent)
    if key == "vector4":
        return QVector4Field(default_value=value, parent=parent)
    return QStringField(default_value=str(value), parent=parent)


__all__ = ["SUPPORTED_VALUE_TYPES", "default_for_type", "make_field_for_type"]

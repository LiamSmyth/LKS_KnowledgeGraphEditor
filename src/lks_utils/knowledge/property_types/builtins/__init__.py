"""Built-in PropertyType implementations for the six core value types.

Importing this module triggers self-registration of all six builtin PropertyTypes
into the PROPERTY_TYPE_REGISTRY.
"""
from __future__ import annotations

from .bool_property_type import BoolPropertyType
from .float_property_type import FloatPropertyType
from .int_property_type import IntPropertyType
from .ref_list_property_type import RefListPropertyType
from .ref_property_type import RefPropertyType
from ..registry import PROPERTY_TYPE_REGISTRY
from .string_property_type import StringPropertyType

# Self-register all builtin PropertyTypes when this module is imported
_BUILTINS = [
    StringPropertyType(),
    IntPropertyType(),
    FloatPropertyType(),
    BoolPropertyType(),
    RefPropertyType(),
    RefListPropertyType(),
]

for _pt in _BUILTINS:
    PROPERTY_TYPE_REGISTRY.register(_pt)

__all__ = [
    "StringPropertyType",
    "IntPropertyType",
    "FloatPropertyType",
    "BoolPropertyType",
    "RefPropertyType",
    "RefListPropertyType",
]

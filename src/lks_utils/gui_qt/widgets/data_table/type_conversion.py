"""Type conversion logic for QDataTableWidget column type changes.

Provides three conversion modes:
- Clear: Remove all data
- Preserve: Keep literal values (11 → 11.0, "11" → 11)
- Unit Conversion: Smart conversion (cents → dollars, etc.)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from lks_utils.gui_qt.widgets.data_table.column_types import ColumnType


class ConversionMode(str, Enum):
    """Type conversion strategies."""
    CLEAR = "clear"
    PRESERVE = "preserve"
    UNIT_CONVERT = "unit_convert"


class ConversionResult:
    """Result of a type conversion attempt."""

    def __init__(self, value: Any, success: bool, error: Optional[str] = None):
        self.value = value
        self.success = success
        self.error = error


def convert_value(
    value: Any,
    from_type: ColumnType,
    to_type: ColumnType,
    mode: ConversionMode
) -> ConversionResult:
    """Convert a value from one column type to another.

    Args:
        value: The value to convert
        from_type: Source column type
        to_type: Target column type
        mode: Conversion strategy

    Returns:
        ConversionResult with converted value and success status
    """
    if value is None:
        return ConversionResult(None, True)

    if mode == ConversionMode.CLEAR:
        return ConversionResult(None, True)

    # Same type = no conversion needed
    if from_type == to_type:
        return ConversionResult(value, True)

    try:
        if mode == ConversionMode.PRESERVE:
            return _preserve_value(value, from_type, to_type)
        elif mode == ConversionMode.UNIT_CONVERT:
            return _unit_convert(value, from_type, to_type)
        else:
            return ConversionResult(None, False, f"Unknown conversion mode: {mode}")

    except Exception as e:
        return ConversionResult(None, False, str(e))


def _preserve_value(value: Any, from_type: ColumnType, to_type: ColumnType) -> ConversionResult:
    """Preserve literal value during type change.

    Args:
        value: Source value
        from_type: Source type
        to_type: Target type

    Returns:
        ConversionResult
    """
    # STRING to anything
    if from_type == ColumnType.STRING:
        if to_type == ColumnType.INT:
            try:
                return ConversionResult(int(value), True)
            except (ValueError, TypeError):
                return ConversionResult(None, False, f"Cannot convert '{value}' to int")

        elif to_type == ColumnType.FLOAT:
            try:
                return ConversionResult(float(value), True)
            except (ValueError, TypeError):
                return ConversionResult(None, False, f"Cannot convert '{value}' to float")

        elif to_type == ColumnType.CURRENCY:
            try:
                # Remove $ if present
                clean = str(value).replace("$", "").replace(",", "").strip()
                return ConversionResult(float(clean), True)
            except (ValueError, TypeError):
                return ConversionResult(None, False, f"Cannot convert '{value}' to currency")

        elif to_type == ColumnType.BOOL:
            lower = str(value).lower()
            if lower in ("true", "yes", "1", "✓", "☑", "checked"):
                return ConversionResult(True, True)
            elif lower in ("false", "no", "0", "✗", "☐", "unchecked", ""):
                return ConversionResult(False, True)
            else:
                return ConversionResult(None, False, f"Cannot convert '{value}' to bool")

    # INT to anything
    elif from_type == ColumnType.INT:
        if to_type == ColumnType.STRING:
            return ConversionResult(str(value), True)
        elif to_type in (ColumnType.FLOAT, ColumnType.CURRENCY):
            return ConversionResult(float(value), True)
        elif to_type == ColumnType.BOOL:
            return ConversionResult(bool(value), True)

    # FLOAT to anything
    elif from_type == ColumnType.FLOAT:
        if to_type == ColumnType.STRING:
            return ConversionResult(str(value), True)
        elif to_type == ColumnType.INT:
            return ConversionResult(int(value), True)
        elif to_type == ColumnType.CURRENCY:
            return ConversionResult(float(value), True)
        elif to_type == ColumnType.BOOL:
            return ConversionResult(bool(value), True)

    # CURRENCY to anything
    elif from_type == ColumnType.CURRENCY:
        if to_type == ColumnType.STRING:
            return ConversionResult(f"${value:.2f}", True)
        elif to_type == ColumnType.INT:
            return ConversionResult(int(value), True)
        elif to_type == ColumnType.FLOAT:
            return ConversionResult(float(value), True)
        elif to_type == ColumnType.BOOL:
            return ConversionResult(bool(value), True)

    # BOOL to anything
    elif from_type == ColumnType.BOOL:
        if to_type == ColumnType.STRING:
            return ConversionResult("true" if value else "false", True)
        elif to_type in (ColumnType.INT, ColumnType.FLOAT, ColumnType.CURRENCY):
            return ConversionResult(1 if value else 0, True)

    return ConversionResult(None, False, f"No preserve conversion from {from_type} to {to_type}")


def _unit_convert(value: Any, from_type: ColumnType, to_type: ColumnType) -> ConversionResult:
    """Smart unit conversion (e.g., cents to dollars).

    Args:
        value: Source value
        from_type: Source type
        to_type: Target type

    Returns:
        ConversionResult
    """
    # INT cents to CURRENCY dollars
    if from_type == ColumnType.INT and to_type == ColumnType.CURRENCY:
        # Assume int value is cents
        return ConversionResult(float(value) / 100.0, True)

    # CURRENCY dollars to INT cents
    if from_type == ColumnType.CURRENCY and to_type == ColumnType.INT:
        # Convert to cents
        return ConversionResult(int(float(value) * 100), True)

    # For other conversions, fall back to preserve
    return _preserve_value(value, from_type, to_type)


def can_convert(from_type: ColumnType, to_type: ColumnType, mode: ConversionMode) -> tuple[bool, str]:
    """Check if conversion is possible and return warnings.

    Args:
        from_type: Source type
        to_type: Target type
        mode: Conversion mode

    Returns:
        Tuple of (possible, warning_message)
    """
    if mode == ConversionMode.CLEAR:
        return True, "All values will be cleared."

    if from_type == to_type:
        return True, ""

    # Check for potentially lossy conversions
    warnings = []

    if from_type == ColumnType.STRING:
        if to_type in (ColumnType.INT, ColumnType.FLOAT, ColumnType.CURRENCY):
            warnings.append("Non-numeric strings will be cleared.")
        elif to_type == ColumnType.BOOL:
            warnings.append(
                "Only 'true'/'false' strings will convert; others will be cleared.")

    elif from_type == ColumnType.FLOAT and to_type == ColumnType.INT:
        warnings.append("Decimal values will be truncated.")

    elif from_type == ColumnType.CURRENCY and to_type == ColumnType.INT:
        if mode == ConversionMode.UNIT_CONVERT:
            warnings.append(
                "Values will be converted to cents (multiplied by 100).")
        else:
            warnings.append("Decimal values will be truncated.")

    elif from_type == ColumnType.INT and to_type == ColumnType.CURRENCY:
        if mode == ConversionMode.UNIT_CONVERT:
            warnings.append(
                "Values will be treated as cents and converted to dollars (divided by 100).")

    elif from_type == ColumnType.BOOL:
        if to_type == ColumnType.STRING:
            warnings.append("Values will become 'true'/'false' strings.")
        elif to_type in (ColumnType.INT, ColumnType.FLOAT, ColumnType.CURRENCY):
            warnings.append("True→1, False→0")

    if warnings:
        return True, " ".join(warnings)

    return True, ""

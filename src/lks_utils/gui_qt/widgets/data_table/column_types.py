"""Column type definitions for QDataTableWidget.

Provides typed column support with automatic formatting and validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ColumnType(str, Enum):
    """Supported column data types."""
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CURRENCY = "currency"  # Float with $ prefix


@dataclass
class ColumnDefinition:
    """Column definition with type and formatting options.

    Attributes:
        name: Display name for the column
        type: Data type for values in this column
        editable: Whether cells in this column are editable
        decimals: Number of decimal places for float/currency (default 2)
        thousands_separator: Whether to use comma separators for large numbers
        currency_symbol: Symbol for currency columns (default "$")
    """
    name: str
    type: ColumnType = ColumnType.STRING
    editable: bool = True
    decimals: int = 2
    thousands_separator: bool = True
    currency_symbol: str = "$"

    def format_value(self, value: Any) -> str:
        """Format value for display based on column type.

        Args:
            value: Raw value to format

        Returns:
            Formatted string for display
        """
        if value is None:
            return ""

        try:
            if self.type == ColumnType.STRING:
                return str(value)

            elif self.type == ColumnType.INT:
                num = int(value) if not isinstance(value, int) else value
                if self.thousands_separator:
                    return f"{num:,}"
                return str(num)

            elif self.type == ColumnType.FLOAT:
                num = float(value) if not isinstance(value, float) else value
                formatted = f"{num:.{self.decimals}f}"
                if self.thousands_separator:
                    # Add commas to integer part
                    parts = formatted.split(".")
                    parts[0] = f"{int(parts[0]):,}"
                    return ".".join(parts)
                return formatted

            elif self.type == ColumnType.CURRENCY:
                num = float(value) if not isinstance(
                    value, (float, int)) else float(value)
                formatted = f"{num:.{self.decimals}f}"
                if self.thousands_separator:
                    parts = formatted.split(".")
                    parts[0] = f"{int(parts[0]):,}"
                    formatted = ".".join(parts)
                return f"{self.currency_symbol}{formatted}"

            elif self.type == ColumnType.BOOL:
                # Return checkbox symbols
                if isinstance(value, str):
                    value = value.lower() in ("true", "yes", "1", "✓", "☑")
                return "✓" if value else "✗"

            return str(value)

        except (ValueError, TypeError):
            return str(value)

    def parse_value(self, text: str) -> tuple[bool, Any, str]:
        """Parse text input and validate against column type.

        Args:
            text: User input text

        Returns:
            Tuple of (valid, parsed_value, error_message)
        """
        text = text.strip()

        if not text:
            return True, None, ""

        try:
            if self.type == ColumnType.STRING:
                return True, text, ""

            elif self.type == ColumnType.INT:
                # Remove commas if present
                clean = text.replace(",", "")
                value = int(clean)
                return True, value, ""

            elif self.type == ColumnType.FLOAT:
                # Remove commas if present
                clean = text.replace(",", "")
                value = float(clean)
                return True, value, ""

            elif self.type == ColumnType.CURRENCY:
                # Remove currency symbol and commas
                clean = text.replace(self.currency_symbol,
                                     "").replace(",", "").strip()
                value = float(clean)
                return True, value, ""

            elif self.type == ColumnType.BOOL:
                # Accept various boolean representations
                lower = text.lower()
                if lower in ("true", "yes", "1", "✓", "☑", "checked"):
                    return True, True, ""
                elif lower in ("false", "no", "0", "✗", "☐", "unchecked", ""):
                    return True, False, ""
                else:
                    return False, None, f"Invalid boolean value: '{text}'"

            return True, text, ""

        except ValueError as e:
            return False, None, f"Invalid {self.type.value}: {e}"

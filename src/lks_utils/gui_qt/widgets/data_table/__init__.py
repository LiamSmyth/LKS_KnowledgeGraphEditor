"""Data table support modules for QDataTableWidget.

Contains:
- column_types: Type definitions and formatters
- type_conversion: Type conversion logic
- type_conversion_dialog: UI for type conversion
- cell_override_mixin: Composable per-cell override layer
- overridable_table_widget: QTableWidget + override mixin convenience class
"""

from __future__ import annotations
from lks_utils.gui_qt.widgets.data_table.cell_override_mixin import QCellOverrideMixin
from lks_utils.gui_qt.widgets.data_table.column_types import ColumnDefinition, ColumnType
from lks_utils.gui_qt.widgets.data_table.overridable_table_widget import QOverridableTableWidget
from lks_utils.gui_qt.widgets.data_table.type_conversion import ConversionMode, ConversionResult, convert_value, can_convert
from lks_utils.gui_qt.widgets.data_table.type_conversion_dialog import QTypeConversionDialog

__all__ = [
    "QCellOverrideMixin",
    "ColumnDefinition",
    "ColumnType",
    "QOverridableTableWidget",
    "ConversionMode",
    "ConversionResult",
    "convert_value",
    "can_convert",
    "QTypeConversionDialog",
]

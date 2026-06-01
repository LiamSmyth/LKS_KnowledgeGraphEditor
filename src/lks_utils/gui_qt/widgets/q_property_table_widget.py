"""QPropertyTableWidget — generic read-only 2-column (Property | Value) table.

Displays a flat or grouped dict of properties as a compact, read-only table.
Suitable for inspection panels, analysis results, and metadata viewers.

Usage::

    table = QPropertyTableWidget()
    table.set_properties({"Width": "1024", "Height": "512", "Format": "EXR"})

    # Grouped with section headers:
    table.set_properties({
        "## Raw": None,          # section header — value None
        "Width": "1024",
        "Height": "512",
        "## Processed": None,
        "Mean": "0.4981",
    })

    # Export:
    json_str = table.to_json()
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class QPropertyTableWidget(QTableWidget):
    """Read-only 2-column (Property | Value) table widget.

    Section headers can be inserted by passing a key that starts with ``##``
    and a ``None`` value.  Section header rows span both columns, use a bold
    italic label, and are visually distinguished with a subtle background.

    The underlying dict is preserved by :meth:`get_properties` (without the
    ``##`` sentinel prefix so callers get clean data back).

    Args:
        parent: Parent widget (optional).
    """

    # Colour used for section-header rows
    _HEADER_BG = QColor("#2a2d34")
    _HEADER_FG = QColor("#9ab8d8")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 2, parent)

        # Column headers
        self.setHorizontalHeaderLabels(["Property", "Value"])
        self.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)

        # Read-only, no selection highlight on individual cells
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)

        # Compact row height
        self.verticalHeader().setDefaultSectionSize(22)

        self._data: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_properties(self, props: dict[str, str | None]) -> None:
        """Populate the table from *props*.

        Keys starting with ``##`` are treated as section headers (their value
        is ignored).  All other entries are ``(property, value)`` rows.

        Args:
            props: Ordered dict mapping property names to string values (or
                   ``None`` to mark a section header).
        """
        self._data = {k: v for k, v in props.items()
                      if not k.startswith("##") and v is not None}

        self.setRowCount(0)
        self.setRowCount(len(props))

        bold_italic = QFont()
        bold_italic.setBold(True)
        bold_italic.setItalic(True)

        for row, (key, value) in enumerate(props.items()):
            if key.startswith("##"):
                # Section header spanning both columns
                label = key.lstrip("# ").strip()
                item = QTableWidgetItem(label)
                item.setFont(bold_italic)
                item.setForeground(self._HEADER_FG)
                item.setBackground(self._HEADER_BG)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.setItem(row, 0, item)
                # Spanning cell for the value column
                span_item = QTableWidgetItem("")
                span_item.setBackground(self._HEADER_BG)
                span_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.setItem(row, 1, span_item)
                self.setSpan(row, 0, 1, 2)
            else:
                # Normal property row
                key_item = QTableWidgetItem(str(key))
                key_item.setFlags(Qt.ItemFlag.ItemIsEnabled |
                                  Qt.ItemFlag.ItemIsSelectable)
                val_item = QTableWidgetItem(
                    str(value) if value is not None else "")
                val_item.setFlags(Qt.ItemFlag.ItemIsEnabled |
                                  Qt.ItemFlag.ItemIsSelectable)
                self.setItem(row, 0, key_item)
                self.setItem(row, 1, val_item)

    def get_properties(self) -> dict[str, str]:
        """Return the currently displayed property dict (no section headers).

        Returns:
            Mapping of property name → value string.
        """
        return dict(self._data)

    def clear_properties(self) -> None:
        """Remove all rows and clear internal data."""
        self._data = {}
        self.setRowCount(0)

    def to_json(self) -> str:
        """Serialise the current properties to a JSON string.

        Returns:
            JSON string of ``{property: value, ...}``.
        """
        return json.dumps(self._data, indent=2, ensure_ascii=False)


__all__ = ["QPropertyTableWidget"]

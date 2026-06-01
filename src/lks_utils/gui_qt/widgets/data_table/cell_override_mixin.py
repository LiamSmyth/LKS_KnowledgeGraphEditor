"""Cell Override Mixin — non-destructive overlay for QTableWidget.

Provides a composable override layer that sits *on top of* a
QTableWidget without mutating its item data.  Overrides are stored
in a separate ``{(row, col): str}`` dictionary and rendered by a
custom ``QStyledItemDelegate``.  The base table always holds the
computed / pipeline values; overrides are purely additive.

Architecture
~~~~~~~~~~~~

::

    ┌──────────────────────────────┐
    │   _OverrideDelegate (paint)  │  ← draws override text + blue bg
    ├──────────────────────────────┤
    │   _overrides dict            │  ← {(row, col): str}
    ├──────────────────────────────┤
    │   QTableWidget items         │  ← always hold base/computed values
    └──────────────────────────────┘

*   ``set_override()`` adds to the dict and repaints the cell.
*   ``clear_override()`` removes from the dict and repaints — the
    base item text is revealed automatically because it was never
    modified.
*   ``get_cell_value()`` returns the override if present, else the
    item text.
*   ``populating()`` suppresses user-edit detection during
    programmatic updates.

Usage::

    class MyTable(QTableWidget, QCellOverrideMixin):
        override_changed = Signal(int, int, object)

        def __init__(self):
            super().__init__()
            self._init_overrides()

    # Or use the pre-composed QOverridableTableWidget.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from PySide6.QtCore import QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


# ------------------------------------------------------------------ #
# Styling constants
# ------------------------------------------------------------------ #

_OVERRIDE_BG = QColor(60, 100, 180, 160)
_OVERRIDE_FG = QColor(255, 255, 255)


# ------------------------------------------------------------------ #
# Delegate — renders override values without touching item data
# ------------------------------------------------------------------ #


class _OverrideDelegate(QStyledItemDelegate):
    """Delegate that paints override values from an external dict.

    Intercepts **paint**, **setEditorData**, and **setModelData** so
    that override values are shown and accepted without modifying the
    underlying ``QTableWidgetItem`` text.
    """

    def __init__(
        self,
        table: QCellOverrideMixin,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._table: QCellOverrideMixin = table

    # -- paint --------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Paint the cell, using override text + blue bg if applicable."""
        row: int = index.row()
        col: int = index.column()
        override: str | None = self._table._overrides.get((row, col))

        if override is None:
            super().paint(painter, option, index)
            return

        painter.save()

        bg_rect: QRect = option.rect
        painter.fillRect(bg_rect, QBrush(_OVERRIDE_BG))

        if option.state & QStyle.State_Selected:
            painter.fillRect(bg_rect, QBrush(QColor(255, 255, 255, 50)))

        painter.setPen(QPen(_OVERRIDE_FG))
        text_rect: QRect = bg_rect.adjusted(4, 0, -4, 0)
        painter.drawText(
            text_rect,
            int(Qt.AlignVCenter | Qt.AlignLeft),
            override,
        )

        painter.restore()

    # -- editing ------------------------------------------------------

    def setEditorData(
        self,
        editor: QWidget,
        index: QModelIndex,
    ) -> None:
        """Pre-fill editor with override value if one exists."""
        row: int = index.row()
        col: int = index.column()
        override: str | None = self._table._overrides.get((row, col))

        if override is not None and hasattr(editor, "setText"):
            editor.setText(override)
            return

        super().setEditorData(editor, index)

    def setModelData(
        self,
        editor: QWidget,
        model: Any,
        index: QModelIndex,
    ) -> None:
        """Intercept commit: store as override, don't touch model data."""
        if self._table._populating:
            super().setModelData(editor, model, index)
            return

        row: int = index.row()
        col: int = index.column()
        new_text: str = ""
        if hasattr(editor, "text"):
            new_text = editor.text()

        # Get the base value from the item (never modified)
        base_value: str = ""
        table_widget: QTableWidget = self._table  # type: ignore[assignment]
        item: QTableWidgetItem | None = table_widget.item(row, col)
        if item:
            base_value = item.text()

        if new_text == base_value:
            # User typed back the original — clear any existing override
            if (row, col) in self._table._overrides:
                self._table.clear_override(row, col)
            return

        self._table._overrides[(row, col)] = new_text
        self._table._repaint_cell(row, col)

        if hasattr(self._table, "override_changed"):
            self._table.override_changed.emit(
                row, col, new_text)  # type: ignore[attr-defined]


# ------------------------------------------------------------------ #
# Mixin
# ------------------------------------------------------------------ #


class QCellOverrideMixin:
    """Non-destructive per-cell override layer for QTableWidget.

    Overrides are stored in ``_overrides`` — a dict mapping
    ``(row, col)`` to the override string.  A custom delegate handles
    painting and editing so that **item data is never modified**.

    Features:
        - Double-click a cell, edit, press Enter → override stored
        - Overridden cells rendered with blue background + white text
        - Right-click → "Clear Override" / "Clear All Overrides"
        - Delete key clears override on selected cells
        - ``populating()`` suppresses override detection
        - ``get_cell_value()`` returns override if present, else base
        - Full override dict serialization for state persistence

    Signals (declare on the concrete class):
        ``override_changed(int, int, object)`` — emitted when a cell
        override is set (value=str) or cleared (value=None).

    Requirements:
        - ``self`` must be a QTableWidget (or subclass)
        - Call ``_init_overrides()`` after ``super().__init__()``
    """

    override_changed: Signal

    def _init_overrides(self) -> None:
        """Initialize the override layer.  Call after ``super().__init__()``."""
        self._overrides: dict[tuple[int, int], str] = {}
        self._populating: bool = False

        table: QTableWidget = self  # type: ignore[assignment]

        # Install the non-destructive delegate
        self._override_delegate = _OverrideDelegate(self, parent=table)
        table.setItemDelegate(self._override_delegate)

        # Context menu
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            self._on_override_context_menu,
        )

    # ------------------------------------------------------------------
    # Populating guard
    # ------------------------------------------------------------------

    @contextmanager
    def populating(self) -> Iterator[None]:
        """Suppress override detection during programmatic updates.

        While active, delegate ``setModelData`` writes directly to the
        model (normal QTableWidget behaviour).

        Example::

            with table.populating():
                table.setItem(0, 0, QTableWidgetItem("computed"))
        """
        self._populating = True
        try:
            yield
        finally:
            self._populating = False

    # ------------------------------------------------------------------
    # Override queries
    # ------------------------------------------------------------------

    def has_override(self, row: int, col: int) -> bool:
        """Check whether a cell has an override value."""
        return (row, col) in self._overrides

    def get_override(self, row: int, col: int) -> str | None:
        """Return the override value for a cell, or ``None``."""
        return self._overrides.get((row, col))

    def get_cell_value(self, row: int, col: int) -> str:
        """Return the effective value (override if present, else base).

        Args:
            row: Row index.
            col: Column index.

        Returns:
            Override string if set, otherwise item text.
        """
        override: str | None = self._overrides.get((row, col))
        if override is not None:
            return override

        table: QTableWidget = self  # type: ignore[assignment]
        item: QTableWidgetItem | None = table.item(row, col)
        return item.text() if item else ""

    def get_overrides_for_row(self, row: int) -> dict[int, str]:
        """Return all overrides for *row* as ``{col: value}``.

        Args:
            row: Row index.

        Returns:
            Dict mapping column index to override value.
        """
        return {
            col: val for (r, col), val in self._overrides.items() if r == row
        }

    # ------------------------------------------------------------------
    # Repaint helpers
    # ------------------------------------------------------------------

    def _repaint_cell(self, row: int, col: int) -> None:
        """Force the delegate to repaint a single cell."""
        table: QTableWidget = self  # type: ignore[assignment]
        model = table.model()
        if model is not None:
            idx: QModelIndex = model.index(row, col)
            model.dataChanged.emit(idx, idx)

    def _repaint_all(self) -> None:
        """Force the delegate to repaint every cell."""
        table: QTableWidget = self  # type: ignore[assignment]
        model = table.model()
        if model is not None and table.rowCount() > 0 and table.columnCount() > 0:
            top_left: QModelIndex = model.index(0, 0)
            bottom_right: QModelIndex = model.index(
                table.rowCount() - 1, table.columnCount() - 1,
            )
            model.dataChanged.emit(top_left, bottom_right)

    # ------------------------------------------------------------------
    # Override mutations
    # ------------------------------------------------------------------

    def set_override(self, row: int, col: int, value: str) -> None:
        """Programmatically set an override on a cell.

        The item text is **not** modified — the delegate paints the
        override value instead.

        Args:
            row: Row index.
            col: Column index.
            value: The override value string.
        """
        self._overrides[(row, col)] = value
        self._repaint_cell(row, col)

        if hasattr(self, "override_changed"):
            # type: ignore[attr-defined]
            self.override_changed.emit(row, col, value)

    def clear_override(self, row: int, col: int) -> None:
        """Clear an override, revealing the base item value.

        Args:
            row: Row index.
            col: Column index.
        """
        if (row, col) not in self._overrides:
            return

        del self._overrides[(row, col)]
        self._repaint_cell(row, col)

        if hasattr(self, "override_changed"):
            # type: ignore[attr-defined]
            self.override_changed.emit(row, col, None)

    def clear_all_overrides(self) -> None:
        """Clear every override, revealing all base values."""
        if not self._overrides:
            return

        self._overrides.clear()
        self._repaint_all()

        if hasattr(self, "override_changed"):
            # type: ignore[attr-defined]
            self.override_changed.emit(-1, -1, None)

    def clear_row_overrides(self, row: int) -> None:
        """Clear all overrides for a specific row.

        Args:
            row: Row index.
        """
        keys: list[tuple[int, int]] = [
            (r, c) for r, c in self._overrides if r == row
        ]
        for r, c in keys:
            self.clear_override(r, c)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def get_overrides_dict(self) -> dict[str, Any]:
        """Serialize all overrides for state persistence.

        Returns:
            Dict with ``"row,col"`` string keys → override value strings.
        """
        return {
            f"{row},{col}": value
            for (row, col), value in self._overrides.items()
        }

    def set_overrides_dict(self, data: dict[str, Any]) -> None:
        """Restore overrides from persisted state.

        Args:
            data: Dict with ``"row,col"`` keys → override value strings.
        """
        self._overrides.clear()
        for key, value in data.items():
            parts = key.split(",", 1)
            if len(parts) == 2:
                try:
                    row, col = int(parts[0]), int(parts[1])
                    self._overrides[(row, col)] = str(value)
                except ValueError:
                    continue

        self._repaint_all()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _on_override_context_menu(self, position: Any) -> None:
        """Show context menu with override actions.

        Args:
            position: Click position (QPoint).
        """
        table: QTableWidget = self  # type: ignore[assignment]
        item: QTableWidgetItem | None = table.itemAt(position)
        if not item:
            return

        row: int = item.row()
        col: int = item.column()

        menu = QMenu(table)

        if self.has_override(row, col):
            clear_action = menu.addAction("Clear Override")
            clear_action.triggered.connect(
                lambda _=False, r=row, c=col: self.clear_override(r, c),
            )

        if self._overrides:
            clear_all = menu.addAction("Clear All Overrides")
            clear_all.triggered.connect(self.clear_all_overrides)

        if menu.actions():
            menu.exec(table.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

    def override_key_press_event(self, event: QKeyEvent) -> bool:
        """Handle Delete key to clear overrides on selected cells.

        Call from ``keyPressEvent``.  Returns ``True`` if consumed.

        Args:
            event: The key event.

        Returns:
            ``True`` if the event was handled.
        """
        if event.key() == Qt.Key_Delete:
            table: QTableWidget = self  # type: ignore[assignment]
            selected = table.selectedItems()
            handled: bool = False
            for sel_item in selected:
                r, c = sel_item.row(), sel_item.column()
                if self.has_override(r, c):
                    self.clear_override(r, c)
                    handled = True
            return handled
        return False

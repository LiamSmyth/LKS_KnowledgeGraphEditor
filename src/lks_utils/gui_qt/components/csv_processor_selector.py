"""CSV processor selector component.

Reusable panel for selecting and ordering :class:`CSVProcessor` instances.
Used for both the preprocessor and postprocessor steps in the CSV mapper
pipeline.

Each line item is a dropdown (``(None)`` by default, skipped during
execution) with a ✕ remove button.  Items can be drag-reordered via
the grip handle (⋮⋮) provided by :class:`QGripBoxContainer`.
"""
from __future__ import annotations

import itertools
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lks_utils.csv.csv_processor import CSVProcessor
from lks_utils.csv.csv_processors import get_all_processors, get_processor_by_id
from lks_utils.gui_qt.theme import COLORS
from lks_utils.gui_qt.widgets import QGripBoxContainer, add_tooltip

# Monotonically increasing counter for unique item IDs
_ITEM_COUNTER: itertools.count = itertools.count()

_NONE_LABEL: str = "(None)"


class _ProcessorLineItem(QWidget):
    """Single line item: processor dropdown + remove button."""

    changed = Signal()   # processor selection changed
    removed = Signal(str)  # item_id of this line item

    def __init__(
        self,
        item_id: str,
        processors: list[CSVProcessor],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.item_id: str = item_id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        # Processor dropdown
        self._combo = QComboBox()
        self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._combo.addItem(_NONE_LABEL, userData="")
        for proc in processors:
            self._combo.addItem(proc.name, userData=proc.id)
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._combo, stretch=1)

        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet(
            f"QPushButton {{ color: {COLORS['danger']}; border: none; "
            f"font-weight: bold; font-size: 14px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['danger']}; "
            f"color: white; border-radius: 3px; }}"
        )
        add_tooltip(remove_btn, "Remove this processor")
        remove_btn.clicked.connect(lambda: self.removed.emit(self.item_id))
        layout.addWidget(remove_btn)

    def _on_combo_changed(self, _index: int) -> None:
        """Update tooltip and emit change."""
        proc_id = self.get_processor_id()
        if proc_id:
            proc = get_processor_by_id(proc_id)
            if proc:
                add_tooltip(self._combo, proc.description)
            else:
                add_tooltip(self._combo, "")
        else:
            add_tooltip(
                self._combo, "No processor selected — this slot will be skipped.")
        self.changed.emit()

    def get_processor_id(self) -> str:
        """Return selected processor ID, or empty string for (None)."""
        return self._combo.currentData() or ""

    def set_processor_id(self, proc_id: str) -> None:
        """Set the dropdown to match the given processor ID."""
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == proc_id:
                self._combo.setCurrentIndex(i)
                return
        # ID not found — reset to (None)
        self._combo.setCurrentIndex(0)


class QCSVProcessorSelector(QWidget):
    """Panel for selecting and ordering CSV processors.

    Provides an Add button to append empty line items.  Each line item
    has a dropdown to choose a processor and a remove button.  Line items
    are drag-reorderable via grip handles.

    Signals:
        selection_changed: Emitted with the ordered list of selected
            processor IDs (empty-string entries for ``(None)`` slots are
            excluded).
    """

    selection_changed = Signal(list)  # list[str] of processor IDs

    def __init__(
        self,
        label: str = "Processors",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._all_processors: list[CSVProcessor] = get_all_processors()
        self._line_items: dict[str, _ProcessorLineItem] = {}

        self._build_ui(label)

    def _build_ui(self, label: str) -> None:
        """Build the selector UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Info
        info = QLabel(
            "Add processors, select from the dropdown, "
            "and drag the grip handle (⋮⋮) to reorder."
        )
        info.setStyleSheet(f"color: {COLORS['light']}; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Dimmer background container for items + add button
        self._container_frame = QFrame()
        self._container_frame.setStyleSheet(
            f"QFrame#processorContainer {{"
            f"  background-color: {COLORS['bg']};"
            f"  border: 1px solid {COLORS['border']};"
            f"  border-radius: 4px;"
            f"}}"
        )
        self._container_frame.setObjectName("processorContainer")
        self._container_frame.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding,
        )

        container_layout = QVBoxLayout(self._container_frame)
        container_layout.setContentsMargins(6, 6, 6, 6)
        container_layout.setSpacing(2)

        # Grip container (reorderable list)
        self._grip_container = QGripBoxContainer()
        self._grip_container.order_changed.connect(self._on_order_changed)
        container_layout.addWidget(self._grip_container)

        # Stretch pushes the add button to the bottom
        container_layout.addStretch()

        # Add button at the bottom of the container
        self._add_btn = QPushButton("+ Add Processor")
        self._add_btn.setStyleSheet("QPushButton { padding: 4px 12px; }")
        self._add_btn.clicked.connect(self._add_empty_item)
        container_layout.addWidget(self._add_btn)

        layout.addWidget(self._container_frame, stretch=1)

        # Status
        self._status_label = QLabel("0 processors")
        self._status_label.setStyleSheet(
            f"color: {COLORS['light']}; font-size: 11px;"
        )
        layout.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _add_empty_item(self) -> None:
        """Add a new empty (None) line item."""
        item_id = f"proc_{next(_ITEM_COUNTER)}"
        self._create_line_item(item_id, proc_id="")

    def _create_line_item(self, item_id: str, proc_id: str) -> None:
        """Create and insert a line item into the grip container.

        Args:
            item_id: Unique ID for the grip item.
            proc_id: Processor ID to pre-select, or ``""`` for (None).
        """
        line = _ProcessorLineItem(
            item_id=item_id,
            processors=self._all_processors,
            parent=self,
        )
        if proc_id:
            line.set_processor_id(proc_id)
        line.changed.connect(self._emit_change)
        line.removed.connect(self._remove_item)
        self._line_items[item_id] = line
        self._grip_container.add_widget(line, item_id=item_id)
        self._emit_change()

    def _remove_item(self, item_id: str) -> None:
        """Remove a line item by its unique ID."""
        line = self._line_items.pop(item_id, None)
        if line:
            self._grip_container.remove_widget(line)
            self._emit_change()

    def _on_order_changed(self, _new_order: list[str]) -> None:
        """Handle drag-drop reorder in grip container."""
        self._emit_change()

    def _emit_change(self) -> None:
        """Emit selection_changed with current active processor IDs."""
        ids = self.get_selected_ids()
        count = len(ids)
        total = self._grip_container.count()
        skipped = total - count
        parts: list[str] = [f"{total} slot{'s' if total != 1 else ''}"]
        if skipped:
            parts.append(f"{skipped} set to (None)")
        self._status_label.setText(" · ".join(parts))
        self.selection_changed.emit(ids)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_selected_ids(self) -> list[str]:
        """Return ordered list of active processor IDs.

        Slots set to ``(None)`` are excluded.

        Returns:
            List of processor ``id`` strings in the user-chosen order.
        """
        result: list[str] = []
        for grip_id in self._grip_container.get_order():
            line = self._line_items.get(grip_id)
            if line:
                pid = line.get_processor_id()
                if pid:
                    result.append(pid)
        return result

    def get_selected_processors(self) -> list[CSVProcessor]:
        """Return ordered list of selected processor instances.

        Returns:
            List of :class:`CSVProcessor` instances in order.
        """
        processors: list[CSVProcessor] = []
        for pid in self.get_selected_ids():
            proc = get_processor_by_id(pid)
            if proc:
                processors.append(proc)
        return processors

    def set_selected_ids(self, processor_ids: list[str]) -> None:
        """Restore selection and order from a list of IDs.

        Clears existing items and creates one line item per ID.

        Args:
            processor_ids: Ordered list of processor ``id`` strings.
        """
        # Clear all
        self._grip_container.clear()
        self._line_items.clear()

        # Rebuild
        for pid in processor_ids:
            item_id = f"proc_{next(_ITEM_COUNTER)}"
            self._create_line_item(item_id, proc_id=pid)

    def to_dict(self) -> dict[str, Any]:
        """Serialize current state for persistence.

        Returns:
            Dict with ``selected_ids`` key.
        """
        return {"selected_ids": self.get_selected_ids()}

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore state from serialized dict.

        Args:
            data: Dict previously returned by :meth:`to_dict`.
        """
        self.set_selected_ids(data.get("selected_ids", []))

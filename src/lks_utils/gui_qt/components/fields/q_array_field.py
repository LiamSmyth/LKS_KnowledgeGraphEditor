"""Array cardinality wrapper widget for typed field items."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.fields.field_icons import (
    get_field_add_icon,
    get_field_delete_icon,
    get_field_grip_icon,
    get_field_revert_icon,
)
from lks_utils.gui_qt.components.fields.q_typed_field_factory import (
    SUPPORTED_VALUE_TYPES,
    default_for_type,
    make_field_for_type,
)
from lks_utils.gui_qt.widgets.collapsible_section import QCollapsibleSection
from lks_utils.gui_qt.widgets.square_icon_button import QSquareIconButton


class _ArrayItemRow(QWidget):
    """Single array item row with field editor and row controls."""

    def __init__(self, field_widget: QWidget, *, removable: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row_index: int = 0
        self.field_widget = field_widget
        self._configure_field_widget()
        self.delete_button = QSquareIconButton(
            14,
            icon=get_field_delete_icon(),
            tooltip="Remove item",
            parent=self,
        )
        self.grip_button = QSquareIconButton(
            14,
            icon=get_field_grip_icon(),
            tooltip="Drag to reorder",
            parent=self,
        )
        self.grip_button.setCursor(Qt.CursorShape.OpenHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.grip_button, 0)
        layout.addWidget(self.field_widget, 1)
        layout.addWidget(self.delete_button, 0)

        self.setFixedHeight(22)

        self.set_removable(removable)

    def set_removable(self, removable: bool) -> None:
        self.delete_button.setVisible(removable)

    def _configure_field_widget(self) -> None:
        # Cardinality rows should avoid extra line-edit clear glyph chrome.
        if hasattr(self.field_widget, "_editor"):
            editor = getattr(self.field_widget, "_editor")
            if isinstance(editor, QLineEdit):
                editor.setClearButtonEnabled(False)

    def apply_row_visual(self, *, row_index: int, bg_color: str, divider_color: str) -> None:
        self._row_index = row_index
        self.setStyleSheet(
            "QWidget {"
            f"background-color: {bg_color};"
            f"border-bottom: 1px solid {divider_color};"
            "}"
            "QLineEdit, QAbstractSpinBox {"
            f"background-color: {bg_color};"
            "}"
        )


class QArrayField(QWidget):
    """Collapsible typed array editor with optional type and size controls."""

    def __init__(
        self,
        *,
        title: str = "Array",
        item_type: str = "string",
        allow_type_selection: bool = False,
        fixed_size: int | None = None,
        allow_size_selection: bool = False,
        initial_size: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._allow_type_selection = allow_type_selection
        self._allow_size_selection = allow_size_selection
        self._fixed_size = fixed_size
        self._is_editable = True
        self._disabled_opacity_effect: QGraphicsOpacityEffect | None = None
        self._item_type = item_type if item_type in SUPPORTED_VALUE_TYPES else "string"
        self._default_item_type = self._item_type

        if self._fixed_size is not None and self._fixed_size < 0:
            raise ValueError("fixed_size must be >= 0")

        self._is_user_dynamic = self._fixed_size is None and not self._allow_size_selection
        default_size = self._fixed_size
        if default_size is None:
            default_size = 1 if initial_size is None else max(0, initial_size)
        self._default_size = default_size

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.section = QCollapsibleSection(
            title=title, initially_expanded=True)
        root.addWidget(self.section)

        self._header_controls = self._build_header_controls()
        self.section.set_header_trailing_widget(self._header_controls)

        self._list = QListWidget(self)
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setSpacing(0)
        self._list.setDragEnabled(True)
        self._list.setAcceptDrops(True)
        self._list.setDropIndicatorShown(True)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        self._empty_label = QLabel("Empty array - no items yet", self)

        self._add_button = QSquareIconButton(
            18,
            icon=get_field_add_icon(),
            tooltip="Add new item",
            parent=self,
        )
        self._add_button.clicked.connect(self.add_item)

        add_row = QWidget(self)
        add_row_layout = QHBoxLayout(add_row)
        add_row_layout.setContentsMargins(0, 0, 0, 0)
        add_row_layout.setSpacing(4)
        add_row_layout.addStretch(1)
        add_row_layout.addWidget(self._add_button)

        body = self.section.content_layout
        body.setSpacing(6)
        body.addWidget(self._empty_label)
        body.addWidget(self._list)
        body.addWidget(add_row)

        target = self._fixed_size
        if target is None and self._allow_size_selection:
            target = int(self._size_spin.value())
        if target is None:
            target = 1 if initial_size is None else max(0, initial_size)
        self._enforce_size(target)
        self._sync_mutation_control_visibility()
        self._refresh_row_visuals()

    def _build_header_controls(self) -> QWidget:
        controls = QWidget(self)
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel("type"))
        if self._allow_type_selection:
            self._type_combo = QComboBox(controls)
            self._type_combo.addItems(list(SUPPORTED_VALUE_TYPES))
            self._type_combo.setCurrentText(self._item_type)
            self._type_combo.currentTextChanged.connect(self._on_type_changed)
            layout.addWidget(self._type_combo)
        else:
            self._type_combo = None
            layout.addWidget(QLabel(self._item_type))

        if self._fixed_size is not None:
            layout.addWidget(QLabel(f"n={self._fixed_size}"))
            self._size_spin = None
        elif self._allow_size_selection:
            layout.addWidget(QLabel("size"))
            self._size_spin = QSpinBox(controls)
            self._size_spin.setRange(0, 999)
            self._size_spin.setValue(self._default_size)
            self._size_spin.valueChanged.connect(self._on_size_changed)
            layout.addWidget(self._size_spin)
        else:
            self._size_spin = None

        self._revert_button = QSquareIconButton(
            18,
            icon=get_field_revert_icon(),
            tooltip="Revert array to default",
            parent=controls,
        )
        self._revert_button.clicked.connect(self.revert_to_default)
        layout.addWidget(self._revert_button)

        return controls

    def _on_type_changed(self, text: str) -> None:
        self._item_type = text if text in SUPPORTED_VALUE_TYPES else "string"
        count = self._list.count()
        self._list.clear()
        for _ in range(count):
            self.add_item()

    def _on_size_changed(self, value: int) -> None:
        self._enforce_size(value)

    def _enforce_size(self, target: int) -> None:
        target = max(0, target)
        while self._list.count() < target:
            self.add_item()
        while self._list.count() > target:
            self._list.takeItem(self._list.count() - 1)
        self._sync_empty_state()

    def _sync_empty_state(self) -> None:
        self._empty_label.setVisible(self._list.count() == 0)
        self._update_list_height()

    def _update_list_height(self) -> None:
        row_height = self._list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 22
        rows = max(1, min(self._list.count(), 6))
        height = rows * row_height + (2 * self._list.frameWidth()) + 4
        self._list.setMinimumHeight(height)
        self._list.setMaximumHeight(height)

    def _sync_mutation_control_visibility(self) -> None:
        show_mutation = self._is_user_dynamic and self._is_editable
        self._add_button.setVisible(show_mutation)
        for index in range(self._list.count()):
            item = self._list.item(index)
            row = self._list.itemWidget(item)
            if isinstance(row, _ArrayItemRow):
                row.set_removable(show_mutation)
                row.grip_button.setVisible(self._is_editable)
                row.delete_button.setEnabled(self._is_editable)
                row.grip_button.setEnabled(self._is_editable)
                row.grip_button.setCursor(
                    Qt.CursorShape.OpenHandCursor if self._is_editable else Qt.CursorShape.ArrowCursor
                )
                if hasattr(row.field_widget, "set_editable"):
                    row.field_widget.set_editable(self._is_editable)

        drag_enabled = self._is_editable
        self._list.setDragEnabled(drag_enabled)
        self._list.setAcceptDrops(drag_enabled)
        self._list.setDropIndicatorShown(drag_enabled)
        self._list.setDragDropMode(
            QListWidget.DragDropMode.InternalMove
            if drag_enabled
            else QListWidget.DragDropMode.NoDragDrop
        )

        if self._type_combo is not None:
            self._type_combo.setEnabled(self._is_editable)
        if self._size_spin is not None:
            self._size_spin.setEnabled(self._is_editable)
        self._revert_button.setVisible(self._is_editable)
        self._revert_button.setEnabled(self._is_editable)
        self._refresh_row_visuals()

    def add_item(self) -> None:
        if self._fixed_size is not None and self._list.count() >= self._fixed_size:
            return
        field = make_field_for_type(
            self._item_type, default_value=default_for_type(self._item_type), parent=self)
        row = _ArrayItemRow(
            field, removable=self._is_user_dynamic, parent=self)
        row.delete_button.clicked.connect(lambda: self._remove_row(row))
        if hasattr(row.field_widget, "set_editable"):
            row.field_widget.set_editable(self._is_editable)

        item = QListWidgetItem(self._list)
        item.setSizeHint(row.sizeHint())
        size = item.sizeHint()
        size.setHeight(22)
        item.setSizeHint(size)
        self._list.addItem(item)
        self._list.setItemWidget(item, row)
        self._sync_empty_state()
        self._sync_mutation_control_visibility()
        self._refresh_row_visuals()

    def _remove_row(self, row: _ArrayItemRow) -> None:
        if not self._is_user_dynamic or not self._is_editable:
            return
        for index in range(self._list.count()):
            item = self._list.item(index)
            if self._list.itemWidget(item) is row:
                self._list.takeItem(index)
                break
        self._sync_empty_state()
        self._refresh_row_visuals()

    def revert_to_default(self) -> None:
        if not self._is_editable:
            return
        if self._type_combo is not None:
            self._type_combo.setCurrentText(self._default_item_type)
        else:
            self._item_type = self._default_item_type

        if self._size_spin is not None:
            self._size_spin.setValue(self._default_size)
        self._enforce_size(self._default_size)

        default_value = default_for_type(self._item_type)
        for row in self.row_widgets():
            if hasattr(row.field_widget, "set_value"):
                row.field_widget.set_value(default_value)

        self._sync_empty_state()
        self._sync_mutation_control_visibility()
        self._refresh_row_visuals()

    def _refresh_row_visuals(self) -> None:
        colors = self._row_colors()
        divider = self.palette().color(QPalette.ColorRole.Dark).name()
        for index, row in enumerate(self.row_widgets()):
            bg = colors[index % 2]
            row.apply_row_visual(
                row_index=index, bg_color=bg, divider_color=divider)

    def _row_colors(self) -> tuple[str, str]:
        base = self.palette().color(QPalette.ColorRole.Base)
        alt = self.palette().color(QPalette.ColorRole.AlternateBase)
        if alt == base:
            if base.lightness() >= 128:
                c0 = base.darker(103)
                c1 = base.darker(108)
            else:
                c0 = base.lighter(106)
                c1 = base.lighter(112)
        else:
            c0 = QColor(base)
            c1 = QColor(alt)
        return (c0.name(), c1.name())

    def row_widgets(self) -> list[_ArrayItemRow]:
        rows: list[_ArrayItemRow] = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            row = self._list.itemWidget(item)
            if isinstance(row, _ArrayItemRow):
                rows.append(row)
        return rows

    def is_editable(self) -> bool:
        """Return whether array-level editing is enabled."""
        return self._is_editable

    def set_editable(self, editable: bool) -> None:
        """Enable or disable edits for header controls and all row editors."""
        if self._is_editable == editable:
            return
        self._is_editable = editable
        self.section.setEnabled(editable)
        self._apply_section_editable_visual(editable)
        self._sync_mutation_control_visibility()

    def _apply_section_editable_visual(self, editable: bool) -> None:
        if editable:
            self.section.setGraphicsEffect(None)
            self._disabled_opacity_effect = None
            return
        effect = QGraphicsOpacityEffect(self.section)
        effect.setOpacity(0.62)
        self.section.setGraphicsEffect(effect)
        self._disabled_opacity_effect = effect


__all__ = ["QArrayField"]

"""Dictionary cardinality wrapper widget for typed key/value entries."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.fields.field_icons import (
    get_field_add_icon,
    get_field_delete_icon,
    get_field_grip_icon,
)
from lks_utils.gui_qt.components.fields.q_typed_field_factory import (
    SUPPORTED_VALUE_TYPES,
    default_for_type,
    make_field_for_type,
)
from lks_utils.gui_qt.widgets.collapsible_section import QCollapsibleSection
from lks_utils.gui_qt.widgets.square_icon_button import QSquareIconButton


class _DictItemRow(QWidget):
    """Single dictionary entry row with key/value editors and controls."""

    def __init__(
        self,
        *,
        key_widget: QWidget,
        value_widget: QWidget,
        removable: bool,
        per_row_type_combo: QComboBox | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._row_index: int = 0
        self.key_widget = key_widget
        self.value_widget = value_widget
        self.value_type_combo = per_row_type_combo

        self._configure_key_widget()

        self.delete_button = QSquareIconButton(
            14,
            icon=get_field_delete_icon(),
            tooltip="Remove entry",
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
        layout.addWidget(self.key_widget, 1)
        if self.value_type_combo is not None:
            layout.addWidget(self.value_type_combo, 0)
        layout.addWidget(self.value_widget, 1)
        layout.addWidget(self.delete_button, 0)

        self.setFixedHeight(22)

        self.set_removable(removable)

    def set_removable(self, removable: bool) -> None:
        self.delete_button.setVisible(removable)

    def _configure_key_widget(self) -> None:
        # Dict rows should expose one revert affordance per row (value field);
        # suppress key-field auxiliary controls to avoid duplicate revert/x icons.
        if hasattr(self.key_widget, "_editor"):
            editor = getattr(self.key_widget, "_editor")
            if isinstance(editor, QLineEdit):
                editor.setClearButtonEnabled(False)
        if hasattr(self.key_widget, "_revert_stack_host"):
            host = getattr(self.key_widget, "_revert_stack_host")
            if isinstance(host, QWidget):
                host.setVisible(False)

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


class QDictField(QWidget):
    """Collapsible typed dictionary editor with optional value type selection."""

    def __init__(
        self,
        *,
        title: str = "Dict",
        key_type: str = "string",
        value_type: str = "string",
        allow_value_type_selection: bool = False,
        per_value_type_selection: bool = False,
        fixed_size: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._key_type = key_type if key_type in SUPPORTED_VALUE_TYPES else "string"
        self._value_type = value_type if value_type in SUPPORTED_VALUE_TYPES else "string"
        self._allow_value_type_selection = allow_value_type_selection
        self._per_value_type_selection = per_value_type_selection
        self._fixed_size = fixed_size
        self._is_user_dynamic = fixed_size is None
        self._is_editable = True

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

        self._empty_label = QLabel("Empty dictionary - no entries yet", self)

        self._add_button = QSquareIconButton(
            18,
            icon=get_field_add_icon(),
            tooltip="Add new entry",
            parent=self,
        )
        self._add_button.clicked.connect(self.add_entry)

        add_row = QWidget(self)
        add_layout = QHBoxLayout(add_row)
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.addStretch(1)
        add_layout.addWidget(self._add_button)

        body = self.section.content_layout
        body.setSpacing(6)
        body.addWidget(self._empty_label)
        body.addWidget(self._list)
        body.addWidget(add_row)

        if self._fixed_size is not None:
            for _ in range(max(0, self._fixed_size)):
                self.add_entry()
        else:
            self.add_entry()
        self._sync_controls()
        self._refresh_row_visuals()

    def _build_header_controls(self) -> QWidget:
        controls = QWidget(self)
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel(f"{self._key_type} ->"))

        if self._allow_value_type_selection and not self._per_value_type_selection:
            self._value_type_combo = QComboBox(controls)
            self._value_type_combo.addItems(list(SUPPORTED_VALUE_TYPES))
            self._value_type_combo.setCurrentText(self._value_type)
            self._value_type_combo.currentTextChanged.connect(
                self._on_header_value_type_changed)
            layout.addWidget(self._value_type_combo)
        else:
            self._value_type_combo = None
            if self._per_value_type_selection:
                layout.addWidget(QLabel("per-entry type"))
            else:
                layout.addWidget(QLabel(self._value_type))

        if self._fixed_size is not None:
            layout.addWidget(QLabel(f"n={self._fixed_size}"))

        return controls

    def _on_header_value_type_changed(self, text: str) -> None:
        self._value_type = text if text in SUPPORTED_VALUE_TYPES else "string"
        self._rebuild_value_widgets()

    def _rebuild_value_widgets(self) -> None:
        for index in range(self._list.count()):
            item = self._list.item(index)
            row = self._list.itemWidget(item)
            if not isinstance(row, _DictItemRow):
                continue
            key_field = row.key_widget
            type_name = self._value_type
            if row.value_type_combo is not None:
                type_name = row.value_type_combo.currentText()
            new_value = make_field_for_type(
                type_name, default_value=default_for_type(type_name), parent=self)
            row.layout().replaceWidget(row.value_widget, new_value)
            row.value_widget.setParent(None)
            row.value_widget = new_value
            if hasattr(row.value_widget, "set_editable"):
                row.value_widget.set_editable(self._is_editable)
            row.value_widget.setEnabled(self._is_editable)

    def _make_per_row_type_combo(self) -> QComboBox | None:
        if not self._per_value_type_selection:
            return None
        combo = QComboBox(self)
        combo.addItems(list(SUPPORTED_VALUE_TYPES))
        combo.setCurrentText(self._value_type)
        combo.currentTextChanged.connect(self._rebuild_value_widgets)
        return combo

    def add_entry(self) -> None:
        if self._fixed_size is not None and self._list.count() >= self._fixed_size:
            return
        key_field = make_field_for_type(
            self._key_type, default_value=default_for_type(self._key_type), parent=self)
        combo = self._make_per_row_type_combo()
        value_type = combo.currentText() if combo is not None else self._value_type
        value_field = make_field_for_type(
            value_type, default_value=default_for_type(value_type), parent=self)

        row = _DictItemRow(
            key_widget=key_field,
            value_widget=value_field,
            removable=self._is_user_dynamic,
            per_row_type_combo=combo,
            parent=self,
        )
        row.delete_button.clicked.connect(lambda: self._remove_row(row))
        if hasattr(row.key_widget, "set_editable"):
            row.key_widget.set_editable(self._is_editable)
        row.key_widget.setEnabled(self._is_editable)
        if hasattr(row.value_widget, "set_editable"):
            row.value_widget.set_editable(self._is_editable)
        row.value_widget.setEnabled(self._is_editable)
        if row.value_type_combo is not None:
            row.value_type_combo.setEnabled(self._is_editable)

        item = QListWidgetItem(self._list)
        item.setSizeHint(row.sizeHint())
        size = item.sizeHint()
        size.setHeight(22)
        item.setSizeHint(size)
        self._list.addItem(item)
        self._list.setItemWidget(item, row)
        self._sync_controls()
        self._refresh_row_visuals()

    def _remove_row(self, row: _DictItemRow) -> None:
        if not self._is_user_dynamic or not self._is_editable:
            return
        for index in range(self._list.count()):
            item = self._list.item(index)
            if self._list.itemWidget(item) is row:
                self._list.takeItem(index)
                break
        self._sync_controls()
        self._refresh_row_visuals()

    def _sync_controls(self) -> None:
        self._empty_label.setVisible(self._list.count() == 0)
        self._update_list_height()
        self._add_button.setVisible(
            self._is_user_dynamic and self._is_editable)
        self._add_button.setEnabled(self._is_editable)
        if self._value_type_combo is not None:
            self._value_type_combo.setEnabled(self._is_editable)
        for index in range(self._list.count()):
            item = self._list.item(index)
            row = self._list.itemWidget(item)
            if isinstance(row, _DictItemRow):
                row.set_removable(self._is_user_dynamic and self._is_editable)
                row.grip_button.setVisible(self._is_editable)
                row.delete_button.setEnabled(self._is_editable)
                row.grip_button.setEnabled(self._is_editable)
                row.grip_button.setCursor(
                    Qt.CursorShape.OpenHandCursor if self._is_editable else Qt.CursorShape.ArrowCursor
                )
                if hasattr(row.key_widget, "set_editable"):
                    row.key_widget.set_editable(self._is_editable)
                row.key_widget.setEnabled(self._is_editable)
                if hasattr(row.value_widget, "set_editable"):
                    row.value_widget.set_editable(self._is_editable)
                row.value_widget.setEnabled(self._is_editable)
                if row.value_type_combo is not None:
                    row.value_type_combo.setEnabled(self._is_editable)

        drag_enabled = self._is_editable
        self._list.setDragEnabled(drag_enabled)
        self._list.setAcceptDrops(drag_enabled)
        self._list.setDropIndicatorShown(drag_enabled)
        self._list.setDragDropMode(
            QListWidget.DragDropMode.InternalMove
            if drag_enabled
            else QListWidget.DragDropMode.NoDragDrop
        )
        self._refresh_row_visuals()

    def _update_list_height(self) -> None:
        row_height = self._list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 22
        rows = max(1, min(self._list.count(), 6))
        height = rows * row_height + (2 * self._list.frameWidth()) + 4
        self._list.setMinimumHeight(height)
        self._list.setMaximumHeight(height)

    def row_widgets(self) -> list[_DictItemRow]:
        rows: list[_DictItemRow] = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            row = self._list.itemWidget(item)
            if isinstance(row, _DictItemRow):
                rows.append(row)
        return rows

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

    def is_editable(self) -> bool:
        """Return whether dictionary-level editing is enabled."""
        return self._is_editable

    def set_editable(self, editable: bool) -> None:
        """Enable or disable edits for header controls and all row editors."""
        if self._is_editable == editable:
            return
        self._is_editable = editable
        self._sync_controls()


__all__ = ["QDictField"]

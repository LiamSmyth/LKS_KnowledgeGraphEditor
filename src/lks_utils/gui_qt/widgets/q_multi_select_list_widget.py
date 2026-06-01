"""Multi-select list widget with explicit anchor-based range semantics."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QKeySequence, QPainter
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QListView, QStyle, QStyleOptionViewItem, QStyledItemDelegate

from lks_utils.input import GestureKind, get_default_bindings
from lks_utils.input.qt_adapter import mouse_event_triple
from lks_utils.gui_qt.widgets.q_multi_select_list_widget_actions import (
    MULTI_SELECT_ADD_RANGE,
    MULTI_SELECT_RANGE,
    MULTI_SELECT_SELECT_ALL,
    MULTI_SELECT_SINGLE,
    MULTI_SELECT_TOGGLE,
)


@dataclass(frozen=True)
class _BadgeItem:
    text: str
    color: str | None = None


@dataclass(frozen=True)
class _ListItem:
    text: str
    badges: tuple[_BadgeItem, ...] = ()


class _RightAlignedMetaDelegate(QStyledItemDelegate):
    """Draw main text left and optional metadata text right in one row."""

    _ROW_PADDING_PX = 8
    _TEXT_STATUS_GAP_PX = 12
    _BADGE_HORIZONTAL_PADDING_PX = 6
    _BADGE_GAP_PX = 6

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: D401
        size = super().sizeHint(option, index)
        view = self.parent()
        if not isinstance(view, QMultiSelectListWidget):
            return size
        left_text = str(index.data(int(Qt.ItemDataRole.DisplayRole)) or "")
        right_width = view.cached_right_column_width()
        text_width = option.fontMetrics.horizontalAdvance(left_text)
        total_width = (
            text_width
            + (self._ROW_PADDING_PX * 2)
            + right_width
            + (self._TEXT_STATUS_GAP_PX if right_width else 0)
        )
        return QSize(max(size.width(), total_width), size.height())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # noqa: D401
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        left_text = styled.text
        badge_data = index.data(int(Qt.ItemDataRole.UserRole) + 2)
        badges: tuple[tuple[str, str | None], ...] = tuple(badge_data or ())
        view = styled.widget if isinstance(
            styled.widget, QMultiSelectListWidget) else None

        styled.text = ""
        style = styled.widget.style() if styled.widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem,
                              styled, painter, styled.widget)
        else:
            super().paint(painter, styled, index)

        painter.save()
        if view is not None and view.active_row() == index.row():
            active_color = QColor(option.palette.color(
                option.palette.ColorRole.Highlight))
            active_color.setAlpha(95 if option.state &
                                  QStyle.StateFlag.State_Selected else 42)
            painter.fillRect(option.rect.adjusted(1, 1, -1, -1), active_color)

        viewport_rect = view.viewport().rect() if view is not None else option.rect
        right_width = view.cached_right_column_width() if view is not None else 0
        right_gap = self._TEXT_STATUS_GAP_PX if right_width else 0
        text_left = option.rect.left() + self._ROW_PADDING_PX
        text_right = viewport_rect.right() - self._ROW_PADDING_PX - \
            right_width - right_gap
        text_rect = QRect(
            text_left,
            option.rect.top(),
            max(0, text_right - text_left),
            option.rect.height(),
        )

        left_pen = (
            option.palette.color(option.palette.ColorRole.HighlightedText)
            if option.state & QStyle.StateFlag.State_Selected
            else option.palette.color(option.palette.ColorRole.Text)
        )
        painter.setPen(left_pen)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            left_text,
        )

        if badges:
            self._paint_badges(painter, option, viewport_rect, badges)
        painter.restore()

    def _paint_badges(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        viewport_rect: QRect,
        badges: tuple[tuple[str, str | None], ...],
    ) -> None:
        font_metrics = option.fontMetrics
        right_edge = viewport_rect.right() - self._ROW_PADDING_PX
        y = option.rect.top() + max(0, (option.rect.height() - font_metrics.height() - 4) // 2)
        x = right_edge
        for text, color_text in reversed(badges):
            text_width = font_metrics.horizontalAdvance(text)
            badge_width = text_width + (self._BADGE_HORIZONTAL_PADDING_PX * 2)
            badge_rect = QRect(
                x - badge_width,
                y,
                badge_width,
                font_metrics.height() + 4,
            )
            badge_color = QColor(str(color_text)) if color_text else option.palette.color(
                option.palette.ColorRole.Text)
            fill_color = QColor(badge_color)
            fill_color.setAlpha(36)
            painter.setBrush(fill_color)
            painter.setPen(badge_color)
            painter.drawRect(badge_rect)
            painter.drawText(
                badge_rect.adjusted(
                    self._BADGE_HORIZONTAL_PADDING_PX, 0, -self._BADGE_HORIZONTAL_PADDING_PX, 0),
                int(Qt.AlignmentFlag.AlignVCenter |
                    Qt.AlignmentFlag.AlignCenter),
                text,
            )
            x = badge_rect.left() - self._BADGE_GAP_PX


class _MultiSelectListModel(QAbstractListModel):
    def __init__(self, parent: QMultiSelectListWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[_ListItem] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        _ = parent
        return 1

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:  # noqa: N802
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        if role == int(Qt.ItemDataRole.DisplayRole):
            return self._items[index.row()].text
        if role == int(Qt.ItemDataRole.UserRole):
            return self._items[index.row()].badges[0].text if self._items[index.row()].badges else ""
        if role == int(Qt.ItemDataRole.UserRole) + 1:
            return self._items[index.row()].badges[0].color if self._items[index.row()].badges else None
        if role == int(Qt.ItemDataRole.UserRole) + 2:
            return tuple((badge.text, badge.color) for badge in self._items[index.row()].badges)
        return None

    def set_items(
        self,
        values: list[str],
        *,
        right_text_by_value: dict[str, str] | None = None,
        right_color_by_value: dict[str, str] | None = None,
        badges_by_value: dict[str, tuple[_BadgeItem, ...]] | None = None,
    ) -> None:
        self.beginResetModel()
        text_map = right_text_by_value or {}
        color_map = right_color_by_value or {}
        badge_map = badges_by_value or {}
        self._items = [
            _ListItem(
                text=value,
                badges=badge_map.get(
                    value,
                    ((_BadgeItem(text=text_map.get(value, ""), color=color_map.get(
                        value)),) if text_map.get(value, "") else ()),
                ),
            )
            for value in values
        ]
        self.endResetModel()

    def item_text(self, row: int) -> str:
        return self._items[row].text


class QMultiSelectListWidget(QListView):
    """QListView with deterministic multi-select semantics and anchor tracking."""

    selection_changed = Signal(list)
    active_row_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._model = _MultiSelectListModel(self)
        self.setModel(self._model)
        self.setItemDelegate(_RightAlignedMetaDelegate(self))
        self.setSelectionMode(QListView.SelectionMode.MultiSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.anchor_index: int | None = None
        self._active_row: int | None = None
        self._selected_rows: set[int] = set()
        self._cached_right_column_width: int = 0
        self.clicked.connect(self._on_clicked)

    def set_items(self, values: list[str]) -> None:
        self._model.set_items(values)
        self.clearSelection()
        self.anchor_index = None
        self._set_active_row(None)
        self._selected_rows = set()
        self._invalidate_width_cache()

    def set_items_with_right_text(
        self,
        values: list[str],
        *,
        right_text_by_value: dict[str, str],
        right_color_by_value: dict[str, str] | None = None,
    ) -> None:
        """Set list items plus optional right-aligned metadata text and color."""
        self._model.set_items(
            values,
            right_text_by_value=right_text_by_value,
            right_color_by_value=right_color_by_value,
        )
        self.clearSelection()
        self.anchor_index = None
        self._set_active_row(None)
        self._selected_rows = set()
        self._invalidate_width_cache()

    def set_items_with_right_badges(
        self,
        values: list[str],
        *,
        badges_by_value: dict[str, tuple[tuple[str, str | None], ...]],
    ) -> None:
        """Set list items with one or more right-aligned colored badges."""
        normalized = {
            value: tuple(_BadgeItem(text=text, color=color)
                         for text, color in badges)
            for value, badges in badges_by_value.items()
        }
        self._model.set_items(values, badges_by_value=normalized)
        self.clearSelection()
        self.anchor_index = None
        self._set_active_row(None)
        self._selected_rows = set()
        self._invalidate_width_cache()

    def active_row(self) -> int | None:
        return self._active_row

    def cached_right_column_width(self) -> int:
        """Return cached right column width (recalculated on set_items)."""
        return self._cached_right_column_width

    def right_column_width(self, font_metrics) -> int:
        widest = 0
        for row in range(self.model().rowCount()):
            badges = self.model().data(self.model().index(row, 0),
                                       int(Qt.ItemDataRole.UserRole) + 2) or ()
            badge_width = 0
            for idx, badge in enumerate(badges):
                text = str(badge[0])
                if not text:
                    continue
                badge_width += font_metrics.horizontalAdvance(text) + (
                    _RightAlignedMetaDelegate._BADGE_HORIZONTAL_PADDING_PX * 2)
                if idx > 0:
                    badge_width += _RightAlignedMetaDelegate._BADGE_GAP_PX
            widest = max(widest, badge_width)
        return widest

    def _invalidate_width_cache(self) -> None:
        """Recalculate and cache the right column width after data changes."""
        font_metrics = self.fontMetrics()
        self._cached_right_column_width = self.right_column_width(font_metrics)

    def selected_rows(self) -> list[int]:
        return sorted(self._selected_rows)

    def selected_values(self) -> list[str]:
        return [self._model.item_text(row) for row in self.selected_rows()]

    def select_values(self, values: list[str]) -> None:
        """Programmatically select items by their text values, preserving order."""
        target = set(values)
        rows_to_select = [
            row for row in range(self._model.rowCount())
            if self._model.item_text(row) in target
        ]
        self.selectionModel().clearSelection()
        self._selected_rows = set()
        self.anchor_index = None
        for row in rows_to_select:
            self._selected_rows.add(row)
            self.selectionModel().select(
                self.model().index(row, 0),
                QItemSelectionModel.SelectionFlag.Select,
            )
        if rows_to_select:
            last_row = rows_to_select[-1]
            self.anchor_index = last_row
            self.setCurrentIndex(self.model().index(last_row, 0))
            self._set_active_row(last_row)
        self.selection_changed.emit(self.selected_values())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        button, modifiers, _ = mouse_event_triple(event, GestureKind.PRESS)
        if button is None:
            return super().mousePressEvent(event)

        bindings = get_default_bindings()
        viewport_point = self.viewport().mapFrom(self, event.position().toPoint())
        index = self.indexAt(viewport_point)
        if not index.isValid():
            # Only clear selection if the click is within the viewport bounds
            if self.viewport().rect().contains(viewport_point):
                if bindings.matches_mouse(MULTI_SELECT_SINGLE.id, button, modifiers, GestureKind.PRESS):
                    self.clearSelection()
                    self.anchor_index = None
                    self._selected_rows = set()
                    self._set_active_row(None)
                    self.selection_changed.emit(self.selected_values())
                    event.accept()
                    return
            return super().mousePressEvent(event)

        row = index.row()
        if bindings.matches_mouse(MULTI_SELECT_ADD_RANGE.id, button, modifiers, GestureKind.PRESS):
            self._apply_range(row, additive=True)
            event.accept()
            return
        if bindings.matches_mouse(MULTI_SELECT_RANGE.id, button, modifiers, GestureKind.PRESS):
            self._apply_range(row, additive=False)
            event.accept()
            return
        if bindings.matches_mouse(MULTI_SELECT_TOGGLE.id, button, modifiers, GestureKind.PRESS):
            self._toggle_row(row)
            self.anchor_index = row
            self.selection_changed.emit(self.selected_values())
            event.accept()
            return
        if bindings.matches_mouse(MULTI_SELECT_SINGLE.id, button, modifiers, GestureKind.PRESS):
            self._select_single(row)
            self.anchor_index = row
            self.selection_changed.emit(self.selected_values())
            event.accept()
            return

        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        bindings = get_default_bindings()
        seq = QKeySequence(int(event.modifiers().value)
                           | int(event.key())).toString()
        if bindings.matches_key(MULTI_SELECT_SELECT_ALL.id, seq):
            self._select_all()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_clicked(self, index: QModelIndex) -> None:
        _ = index
        self.selection_changed.emit(self.selected_values())

    def _set_active_row(self, row: int | None) -> None:
        if row == self._active_row:
            return
        old_row = self._active_row
        self._active_row = row
        if old_row is not None:
            self.viewport().update(self.visualRect(self.model().index(old_row, 0)))
        if row is not None:
            self.viewport().update(self.visualRect(self.model().index(row, 0)))
        self.active_row_changed.emit(row)

    def _select_single(self, row: int) -> None:
        model_index = self.model().index(row, 0)
        self._selected_rows = {row}
        self.selectionModel().setCurrentIndex(
            model_index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )
        self.setCurrentIndex(model_index)
        self._set_active_row(row)

    def _toggle_row(self, row: int) -> None:
        model_index = self.model().index(row, 0)
        if row in self._selected_rows:
            self._selected_rows.remove(row)
        else:
            self._selected_rows.add(row)
        is_selected = self.selectionModel().isSelected(model_index)
        flag = (
            QItemSelectionModel.SelectionFlag.Toggle
            if is_selected
            else QItemSelectionModel.SelectionFlag.Toggle
        )
        self.selectionModel().select(
            model_index,
            flag,
        )
        self.setCurrentIndex(model_index)
        self._set_active_row(row)

    def _apply_range(self, target_row: int, *, additive: bool) -> None:
        if self.anchor_index is None:
            self.anchor_index = target_row
        start = min(self.anchor_index, target_row)
        end = max(self.anchor_index, target_row)
        if not additive:
            self._selected_rows = set()
            self.selectionModel().clearSelection()
        for row in range(start, end + 1):
            self._selected_rows.add(row)
            model_index = self.model().index(row, 0)
            self.selectionModel().select(
                model_index,
                QItemSelectionModel.SelectionFlag.Select,
            )
        self.setCurrentIndex(self.model().index(target_row, 0))
        self.anchor_index = target_row
        self._set_active_row(target_row)
        self.selection_changed.emit(self.selected_values())

    def _select_all(self) -> None:
        self.selectionModel().clearSelection()
        row_count = self.model().rowCount()
        self._selected_rows = set(range(row_count))
        for row in range(row_count):
            model_index = self.model().index(row, 0)
            self.selectionModel().select(
                model_index,
                QItemSelectionModel.SelectionFlag.Select,
            )
        if row_count > 0:
            self.anchor_index = row_count - 1
            self.setCurrentIndex(self.model().index(row_count - 1, 0))
            self._set_active_row(row_count - 1)
        self.selection_changed.emit(self.selected_values())


__all__ = ["QMultiSelectListWidget"]

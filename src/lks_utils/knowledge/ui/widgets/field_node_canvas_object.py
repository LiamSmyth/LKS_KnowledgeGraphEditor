"""Canvas2D item that renders display-only field rows for one knowledge node."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRectF, Signal, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen

from lks_utils.gui_qt.canvas2d.interaction.actions import CANVAS_PRIMARY
from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_widget_adapter_pixmap import CanvasPixmapWidgetObject
from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.input import GestureKind, Modifier, MouseBinding, get_default_bindings
from lks_utils.knowledge.actions import FIELD_COLLAPSE_RECURSIVE
from lks_utils.knowledge.default_theme import (
    COLLAPSE_ARROW_COLOR,
    FIELD_ROW_BG,
    FIELD_ROW_BORDER,
    IMMUTABLE_FIELD_TEXT,
    NODE_FILL_COLOR,
    NODE_SELECTED_STROKE_COLOR,
    NODE_STROKE_COLOR,
    NODE_TEXT_COLOR,
    REF_PILL_BG,
    REF_PILL_TEXT,
    ROOT_HEADER_BG,
    ROOT_HEADER_STROKE,
    ROOT_LABEL_COLOR,
)
from lks_utils.knowledge.models.node_slot import NodeSlot
from lks_utils.knowledge.ui.components.field_row_factory import (
    FieldRow,
    FieldRowFactory,
)
from lks_utils.knowledge.ui.widgets.field_node_widget import QKnowledgeFieldNodeWidget
from lks_utils.spatial.aabb import AABB


def knowledge_field_node_height_for_rows(rows: list[FieldRow]) -> float:
    """Return the card height needed to show *rows*, capped at the scroll threshold.

    Cards taller than ``_MAX_CARD_HEIGHT_WORLD`` overflow their viewable area
    and become scrollable via the mouse wheel.
    """
    visible_count = _count_expanded_rows(rows)
    content_height = (
        QKnowledgeFieldNodeCanvasObject._PADDING_WORLD * 2.0
        + QKnowledgeFieldNodeCanvasObject._HEADER_HEIGHT_WORLD
        + 4.0
        + visible_count * QKnowledgeFieldNodeCanvasObject._ROW_HEIGHT_WORLD
    )
    return min(
        QKnowledgeFieldNodeCanvasObject._MAX_CARD_HEIGHT_WORLD,
        max(72.0, content_height),
    )


def _count_expanded_rows(rows: list[FieldRow]) -> int:
    count = 0
    for row in rows:
        count += 1
        if row.nested_rows:
            count += _count_expanded_rows(row.nested_rows)
    return count


def _control_tooltip_label(action_id: str) -> str:
    if action_id == "field.edit":
        return "Edit"
    if action_id == "knowledge.field.pick_ref":
        return "Pick reference"
    if action_id == "knowledge.field.clear_ref":
        return "Clear reference"
    return action_id


@dataclass(frozen=True, slots=True)
class _ControlRect:
    action_id: str
    rect: QRectF


@dataclass(frozen=True, slots=True)
class _VisibleRow:
    key: str
    row: FieldRow
    depth: int
    top_y: float
    bottom_y: float
    collapse_rect: QRectF | None
    controls: tuple[_ControlRect, ...]


class _KnowledgeFieldNodeCanvasObjectSignals(QObject):
    """Signal bridge for non-QObject canvas objects."""

    edit = Signal(str, object)
    pick_ref = Signal(str, object)
    clear_ref = Signal(str, object)
    row_selected = Signal(str, object)


class QKnowledgeFieldNodeCanvasObject(CanvasPixmapWidgetObject):
    """Render and interact with display-only knowledge field rows in Canvas2D world-space."""

    manages_own_selection_highlight: bool = True

    _PADDING_WORLD: float = 8.0
    _HEADER_HEIGHT_WORLD: float = 20.0
    _ROW_HEIGHT_WORLD: float = 20.0
    _ROW_INDENT_WORLD: float = 14.0
    _COLLAPSE_SIZE_WORLD: float = 10.0
    _CONTROL_WIDTH_WORLD: float = 26.0
    _CONTROL_GAP_WORLD: float = 4.0
    # Cards taller than this get capped and become vertically scrollable.
    _MAX_CARD_HEIGHT_WORLD: float = 280.0
    _SCROLLBAR_WIDTH_WORLD: float = 4.0

    def __init__(
        self,
        *,
        node_id: str,
        node_name: str,
        x: float,
        y: float,
        width: float,
        height: float,
        is_root: bool = False,
        rows: list[FieldRow] | None = None,
        slots: list[NodeSlot] | None = None,
        values: dict[str, object] | None = None,
        row_factory: FieldRowFactory | None = None,
        invalid_slot_names: set[str] | None = None,
        on_edit: Callable[[str, FieldRow], None] | None = None,
        on_pick_ref: Callable[[str, FieldRow], None] | None = None,
        on_clear_ref: Callable[[str, FieldRow], None] | None = None,
        on_row_selected: Callable[[
            str, FieldRow], None] | None = None,
        on_select: Callable[[
            "QKnowledgeFieldNodeCanvasObject"], None] | None = None,
        selection_slot_name: str | None = None,
        header_bg_color: str | None = None,
        header_subtitle: str | None = None,
    ) -> None:
        self._field_widget = QKnowledgeFieldNodeWidget()
        super().__init__(self._field_widget, QRectF(x, y, width, height))
        self.node_id = node_id
        self.node_name = node_name
        self._x = x
        self._y = y
        self._width = width
        self._height = height
        self._is_root = is_root
        self._row_factory = row_factory or FieldRowFactory()
        self._rows: list[FieldRow] = []
        self._collapsed_by_key: dict[str, bool] = {}
        self._invalid_slot_names: set[str] = set(invalid_slot_names or set())
        self._validation_errors: dict[str, str] = {}
        self._validation_error_icon_rect: QRectF | None = None
        self._validation_error_tooltip: str = ""
        self._on_edit = on_edit
        self._on_pick_ref = on_pick_ref
        self._on_clear_ref = on_clear_ref
        self._on_row_selected = on_row_selected
        self._on_select = on_select
        self._selection_slot_name = selection_slot_name
        self._header_bg_color = header_bg_color
        self._header_subtitle = header_subtitle
        self._selected = False
        self._active_selected = False
        self._scroll_offset_world: float = 0.0
        self.signals = _KnowledgeFieldNodeCanvasObjectSignals()

        if rows is not None:
            self.set_rows(rows)
        else:
            self.set_slot_values(slots or [], values or {})
        self._sync_widget()

    def bounds(self) -> AABB:
        return AABB(self._x, self._y, self._x + self._width, self._y + self._height)

    @property
    def selected(self) -> bool:
        """Return current selected state."""
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        if self._selected == value:
            return
        self._selected = value
        self.invalidate()

    @property
    def active_selected(self) -> bool:
        """Return whether this item is the active selection."""
        return self._active_selected

    @active_selected.setter
    def active_selected(self, value: bool) -> None:
        if self._active_selected == value:
            return
        self._active_selected = value
        self.invalidate()

    def set_rows(self, rows: list[FieldRow]) -> None:
        self._rows = list(rows)
        self._prime_collapse_state(self._rows)
        self._scroll_offset_world = 0.0  # reset view to top on content change
        self._sync_widget()
        self.invalidate()

    def set_slot_values(self, slots: list[NodeSlot], values: dict[str, object]) -> None:
        self.set_rows(self._row_factory.build_rows(slots, values))

    def set_invalid_slot_names(self, invalid_slot_names: set[str]) -> None:
        self._invalid_slot_names = set(invalid_slot_names)
        self._sync_widget()
        self.invalidate()

    def set_validation_errors(self, validation_errors: dict[str, str]) -> None:
        """Set the validation error dict and recompute tooltip."""
        self._validation_errors = dict(validation_errors)
        if self._validation_errors:
            lines = [f"⚠ {slot}: {msg}" for slot,
                     msg in sorted(self._validation_errors.items())]
            self._validation_error_tooltip = "\n".join(lines)
        else:
            self._validation_error_tooltip = ""
        self._sync_widget()
        self.invalidate()

    def collapse_state(self) -> dict[str, bool]:
        """Return the current nested-row collapse map for persistence."""
        return dict(self._collapsed_by_key)

    def apply_collapse_state(self, state: dict[str, bool]) -> None:
        """Restore persisted nested-row collapse state after row rebuild."""
        for key in list(self._collapsed_by_key.keys()):
            if key in state:
                self._collapsed_by_key[key] = bool(state[key])
        self._sync_widget()
        self.invalidate()

    def paint(self, ctx: CanvasPaintContext) -> None:
        super().paint(ctx)
        if not (self._selected or self._active_selected):
            return
        rect = self.bounds()
        painter = ctx.painter
        stroke_width = 2.8 if self._active_selected else 2.0
        pen = QPen(QColor(NODE_SELECTED_STROKE_COLOR), stroke_width)
        pen.setCosmetic(True)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect.x0, rect.y0, rect.width, rect.height, 4.0, 4.0)
        painter.restore()

    def handle_input(self, event: CanvasInputEvent) -> bool:
        # Delegate wheel events to handle_wheel.
        if event.phase == "wheel" and event.delta is not None:
            delta_y = event.delta[1] / 120.0
            return self.handle_wheel(event.world_pos, delta_y)
        if event.action.id != CANVAS_PRIMARY.id or event.phase != "press":
            return False
        if not self.hit_test(event.world_pos):
            return False

        visible = self._find_visible_row(event.world_pos)
        if visible is None:
            # Card headers and text regions can sit outside row hit-bands.
            # When this card represents a specific slot, treat any in-card press
            # as selecting that slot so inspector sync is consistent.
            fallback_row = self._selection_fallback_row()
            if fallback_row is not None:
                self._emit_row_selected(fallback_row)
            if self._on_select is not None:
                self._on_select(self)
            return True

        self._emit_row_selected(visible.row)

        # Rects (collapse_rect, control rects) are stored in nominal
        # (unscrolled) content coordinates.  Translate the cursor position
        # to match before doing containment tests.
        content_pos = (
            event.world_pos[0],
            event.world_pos[1] - self._scroll_offset_world,
        )

        if visible.collapse_rect is not None and self._contains_world(visible.collapse_rect, content_pos):
            recursive = self._is_recursive_collapse_event(event)
            self._toggle_collapsed(visible.key, recursive=recursive)
            self._clamp_scroll()  # collapsing may reduce total height
            self.invalidate()
            return True

        for control in visible.controls:
            if self._contains_world(control.rect, content_pos):
                self._invoke_control(control.action_id, visible.row)
                return True
        if self._on_select is not None:
            self._on_select(self)
        return True

    def handle_wheel(self, world_pos: tuple[float, float], delta_y: float) -> bool:
        """Scroll the card vertically when there are more rows than fit.

        *delta_y* > 0 = wheel up (scroll toward the top of the list).
        *delta_y* < 0 = wheel down (scroll toward the bottom).
        Returns ``True`` to consume the event and prevent canvas zoom.
        """
        if not self.hit_test(world_pos) or not self._is_scrollable():
            return False
        # Two-row step per notch feels comfortable at typical zoom levels.
        self._scroll_offset_world -= delta_y * self._ROW_HEIGHT_WORLD * 2.0
        self._clamp_scroll()
        self.invalidate()
        return True

    def _selection_fallback_row(self) -> FieldRow | None:
        """Resolve a stable row for in-card clicks that miss explicit row bands."""
        if not self._rows:
            return None
        if self._selection_slot_name:
            for visible in self._visible_rows():
                if visible.row.slot_name == self._selection_slot_name:
                    return visible.row
        return self._rows[0]

    def tooltip_at(self, world_pt: tuple[float, float]) -> str | None:
        if not self.hit_test(world_pt):
            return None

        title = f"ROOT: {self.node_name}" if self._is_root else self.node_name

        # Check if hovering over validation error icon
        if self._validation_error_icon_rect is not None and self._contains_world(self._validation_error_icon_rect, world_pt):
            if self._validation_error_tooltip:
                return f"{title}\nValidation Issues:\n{self._validation_error_tooltip}"
            return None

        visible = self._find_visible_row(world_pt)
        if visible is None:
            return title

        # Rects are in nominal (unscrolled) coordinates; adjust the query point.
        content_pt = (world_pt[0], world_pt[1] - self._scroll_offset_world)

        if visible.collapse_rect is not None and self._contains_world(visible.collapse_rect, content_pt):
            is_collapsed = self._collapsed_by_key.get(visible.key, False)
            action = "Expand" if is_collapsed else "Collapse"
            return f"{title}\n{action} {visible.row.label}"

        for control in visible.controls:
            if self._contains_world(control.rect, content_pt):
                return (
                    f"{title}\n"
                    f"{visible.row.label}: {_control_tooltip_label(control.action_id)}"
                )

        return f"{title}\n{self._format_row_text(visible.row)}"

    def _visible_rows(self) -> list[_VisibleRow]:
        rows: list[_VisibleRow] = []
        top_cursor = self._y + self._height - \
            self._PADDING_WORLD - self._HEADER_HEIGHT_WORLD - 4.0
        self._append_visible_rows(
            out=rows,
            parent_key="",
            rows=self._rows,
            depth=0,
            top_cursor_ref=[top_cursor],
        )
        return rows

    def _append_visible_rows(
        self,
        *,
        out: list[_VisibleRow],
        parent_key: str,
        rows: list[FieldRow],
        depth: int,
        top_cursor_ref: list[float],
    ) -> None:
        for index, row in enumerate(rows):
            key = f"{parent_key}/{index}" if parent_key else str(index)
            top_y = top_cursor_ref[0]
            bottom_y = top_y - self._ROW_HEIGHT_WORLD
            top_cursor_ref[0] = bottom_y

            collapse_rect = self._collapse_rect(
                key, depth, top_y, bottom_y, row)
            controls = self._control_rects(top_y, bottom_y, row)
            out.append(
                _VisibleRow(
                    key=key,
                    row=row,
                    depth=depth,
                    top_y=top_y,
                    bottom_y=bottom_y,
                    collapse_rect=collapse_rect,
                    controls=controls,
                )
            )
            if row.nested_rows and not self._collapsed_by_key.get(key, False):
                self._append_visible_rows(
                    out=out,
                    parent_key=key,
                    rows=row.nested_rows,
                    depth=depth + 1,
                    top_cursor_ref=top_cursor_ref,
                )

    def _collapse_rect(
        self,
        key: str,
        depth: int,
        top_y: float,
        bottom_y: float,
        row: FieldRow,
    ) -> QRectF | None:
        if not row.nested_rows:
            return None
        if key not in self._collapsed_by_key:
            self._collapsed_by_key[key] = False
        x = self._x + self._PADDING_WORLD + \
            4.0 + (depth * self._ROW_INDENT_WORLD)
        return QRectF(x, bottom_y + 3.0, self._COLLAPSE_SIZE_WORLD, (top_y - bottom_y) - 6.0)

    def _control_rects(self, top_y: float, bottom_y: float, row: FieldRow) -> tuple[_ControlRect, ...]:
        # Field cards are display-only on canvas; action pills are intentionally hidden.
        _ = top_y, bottom_y, row
        return ()

    def _find_visible_row(self, world_pos: tuple[float, float]) -> _VisibleRow | None:
        x, y = world_pos
        if x < self._x + self._PADDING_WORLD or x > (self._x + self._width - self._PADDING_WORLD):
            return None
        # Row positions are in nominal (unscrolled) content coordinates.
        # Subtract the scroll offset to map from world Y to content Y.
        effective_y = y - self._scroll_offset_world
        for visible in self._visible_rows():
            if visible.bottom_y <= effective_y <= visible.top_y:
                return visible
        return None

    # ------------------------------------------------------------------ #
    # Scroll helpers                                                        #
    # ------------------------------------------------------------------ #

    def _content_area_height(self) -> float:
        """Viewable row height (below the header band)."""
        return (
            self._height
            - self._PADDING_WORLD * 2.0
            - self._HEADER_HEIGHT_WORLD
            - 4.0
        )

    def _total_rows_height(self) -> float:
        """Unclipped height of all expanded rows combined."""
        return _count_expanded_rows(self._rows) * self._ROW_HEIGHT_WORLD

    def _is_scrollable(self) -> bool:
        """True when the expanded row content exceeds the viewable area."""
        return self._total_rows_height() > self._content_area_height()

    def _clamp_scroll(self) -> None:
        """Keep *_scroll_offset_world* within ``[0, max_scroll]``."""
        max_scroll = max(
            0.0, self._total_rows_height() - self._content_area_height()
        )
        self._scroll_offset_world = max(
            0.0, min(max_scroll, self._scroll_offset_world)
        )

    def _toggle_collapsed(self, key: str, *, recursive: bool) -> None:
        next_state = not self._collapsed_by_key.get(key, False)
        if not recursive:
            self._collapsed_by_key[key] = next_state
            return
        prefix = f"{key}/"
        for known_key in list(self._collapsed_by_key.keys()):
            if known_key == key or known_key.startswith(prefix):
                self._collapsed_by_key[known_key] = next_state

    def _emit_row_selected(self, row: FieldRow) -> None:
        slot_name = self._selection_slot_name or row.slot_name
        self.signals.row_selected.emit(slot_name, row)
        if self._on_row_selected is not None:
            self._on_row_selected(slot_name, row)

    def _invoke_control(self, action_id: str, row: FieldRow) -> None:
        if action_id == "field.edit":
            slot_name = self._selection_slot_name or row.slot_name
            self.signals.edit.emit(slot_name, row)
            if self._on_edit is not None:
                self._on_edit(slot_name, row)
            return
        if action_id == "knowledge.field.pick_ref":
            self.signals.pick_ref.emit(row.slot_name, row)
            if self._on_pick_ref is not None:
                self._on_pick_ref(row.slot_name, row)
            return
        if action_id == "knowledge.field.clear_ref":
            self.signals.clear_ref.emit(row.slot_name, row)
            if self._on_clear_ref is not None:
                self._on_clear_ref(row.slot_name, row)

    def _control_label(self, row: FieldRow, action_id: str) -> str:
        for control in row.controls:
            if control.action_id == action_id:
                return control.label
        return "?"

    def _format_value(self, row: FieldRow) -> str:
        value = row.value
        if row.kind == "ref_set" and isinstance(value, str):
            return value
        if row.kind == "ref_set" and isinstance(value, list):
            refs: list[str] = []
            for item in value:
                if isinstance(item, str):
                    refs.append(item)
            if refs:
                return ", ".join(refs)
        if row.kind == "ref_empty":
            return "(empty)"
        if value is None:
            return "None"
        text = str(value)
        if text.startswith("ref:") and len(text) > 14:
            return "ref:" + text[-8:]
        if len(text) > 42:
            return text[:39] + "..."
        return text

    def _format_row_text(self, row: FieldRow) -> str:
        value = self._format_value(row)
        if value in ("", "None"):
            return row.label
        if row.label == value:
            return row.label
        if row.slot_name == value:
            return row.label
        return f"{row.label}: {value}"

    def _contains_world(self, rect: QRectF, world_pos: tuple[float, float]) -> bool:
        return rect.contains(world_pos[0], world_pos[1])

    def _prime_collapse_state(self, rows: list[FieldRow]) -> None:
        known = self._collapsed_by_key
        self._collapsed_by_key = {}

        def walk(parent_key: str, nested_rows: list[FieldRow]) -> None:
            for index, row in enumerate(nested_rows):
                key = f"{parent_key}/{index}" if parent_key else str(index)
                if row.nested_rows:
                    self._collapsed_by_key[key] = known.get(key, True)
                    walk(key, row.nested_rows)

        walk("", rows)

    def _is_recursive_collapse_event(self, event: CanvasInputEvent) -> bool:
        try:
            bindings = get_default_bindings().get_bindings(FIELD_COLLAPSE_RECURSIVE.id)
        except KeyError:
            return Modifier.ALT in event.modifiers
        for binding in bindings:
            if isinstance(binding, MouseBinding) and binding.gesture == GestureKind.PRESS:
                if binding.modifiers == event.modifiers:
                    return True
        return False

    def _sync_widget(self) -> None:
        visible_rows_data: list[tuple[str, str, str, str]] = []
        scroll_offset_rows = int(
            self._scroll_offset_world / self._ROW_HEIGHT_WORLD)
        for visible in self._visible_rows():
            if visible.row.kind == "group_header":
                continue
            label = f"{'  ' * max(0, visible.depth)}{visible.row.label}"
            value = self._format_value(visible.row)
            if visible.row.kind.startswith("ref"):
                value_kind = "reference"
                value_type = "ref"
            elif visible.row.kind in {"nested", "literal", "property_contract"}:
                value_kind = "literal"
                value_type = ""
            else:
                value_kind = "literal"
                value_type = visible.row.kind
            visible_rows_data.append(
                (label, value_type, value, value_kind))

        title = f"ROOT {self.node_name}" if self._is_root else self.node_name
        subtitle = self._header_subtitle
        header_bg = self._header_bg_color or ROOT_HEADER_BG
        self._field_widget.sync_from_model(
            title=title,
            subtitle=subtitle,
            is_root=self._is_root,
            selected=self._selected,
            header_bg_color=header_bg,
            has_validation_errors=bool(self._validation_errors),
            visible_rows=visible_rows_data,
            scroll_offset_rows=scroll_offset_rows,
            max_visible_rows=max(1, len(visible_rows_data)),
        )


__all__ = ["QKnowledgeFieldNodeCanvasObject",
           "knowledge_field_node_height_for_rows"]

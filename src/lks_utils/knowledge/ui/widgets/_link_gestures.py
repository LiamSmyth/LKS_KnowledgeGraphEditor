"""Link-creation gesture handlers for the knowledge graph canvas (private)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QKeyEvent, QMouseEvent

from lks_utils.input import GestureKind, get_default_bindings
from lks_utils.input.qt_adapter import qt_button_to_logical, qt_modifiers_to_logical
from lks_utils.knowledge.ui.actions import (
    GRAPH_LINK_CREATE_CANCEL,
    GRAPH_LINK_CREATE_TARGET_COMMIT,
)
from lks_utils.knowledge.ui.widgets.graph_link_canvas_object import (
    QKnowledgeGraphLinkCanvasObject,
)
from lks_utils.knowledge.ui.widgets.graph_node_canvas_object import (
    QKnowledgeGraphNodeCanvasObject,
)

if TYPE_CHECKING:
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QWidget

LINK_TYPE_MIME = "application/x-knowledge-link-type-id"


class GraphLinkGestureHost(Protocol):
    """Surface required from ``QKnowledgeGraphCanvasWidget`` for link gestures."""

    _local_node_objects: dict[str, QKnowledgeGraphNodeCanvasObject]
    _preview_link_item: QKnowledgeGraphLinkCanvasObject | None
    _link_creation_modal_active: bool
    _link_creation_target_mode: bool

    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]: ...
    def add_object(self, item, *, z_order: int = 0) -> None: ...
    def remove_object(self, item) -> None: ...
    def link_source_drag_started(self): ...
    def link_source_drag_hovered(self): ...
    def link_source_drop_finished(self): ...
    def link_target_hovered(self): ...
    def link_target_clicked(self): ...
    def link_creation_cancel_requested(self): ...


def link_type_id_from_event(
    event: QDragEnterEvent | QDragMoveEvent | QDropEvent,
    *,
    mime: str = LINK_TYPE_MIME,
) -> str | None:
    raw = event.mimeData().data(mime)
    if raw:
        try:
            return bytes(raw).decode("utf-8")
        except Exception:
            return None
    return None


class GraphLinkGestures:
    """Encapsulates link-type drag and link-creation modal input routing."""

    def __init__(self, canvas: GraphLinkGestureHost) -> None:
        self._canvas = canvas

    def candidate_source_node_id_from_screen(self, sx: float, sy: float) -> str | None:
        wx, wy = self._canvas._screen_to_world(sx, sy)
        for item in reversed(list(self._canvas._local_node_objects.values())):
            if not item.hit_test((wx, wy)):
                continue
            return item.node_id
        return None

    def set_link_creation_modal_active(self, active: bool) -> None:
        self._canvas._link_creation_modal_active = bool(active)
        if not self._canvas._link_creation_modal_active:
            self._canvas._link_creation_target_mode = False
            self.clear_link_preview()

    def set_link_creation_target_mode(self, active: bool) -> None:
        self._canvas._link_creation_target_mode = bool(active)
        if not self._canvas._link_creation_target_mode:
            self.clear_link_preview()

    def set_link_preview(
        self,
        *,
        source_node_id: str | None,
        target_node_id: str | None,
        cursor_world: tuple[float, float] | None = None,
        color: str | None = None,
    ) -> None:
        self.clear_link_preview()
        if source_node_id is None:
            return
        source_item = next(
            (
                item
                for item in reversed(list(self._canvas._local_node_objects.values()))
                if item.node_id == source_node_id
            ),
            None,
        )
        if source_item is None:
            return
        source_bounds = source_item.bounds()
        source_center = (source_bounds.cx, source_bounds.cy)
        target_center: tuple[float, float] | None = None
        if target_node_id is not None:
            target_item = next(
                (
                    item
                    for item in reversed(list(self._canvas._local_node_objects.values()))
                    if item.node_id == target_node_id
                ),
                None,
            )
            if target_item is not None:
                target_bounds = target_item.bounds()
                target_center = (target_bounds.cx, target_bounds.cy)
        if target_center is None:
            target_center = cursor_world
        if target_center is None:
            return
        source_anchor = source_item.link_anchor_toward(target_center)
        target_anchor = target_center
        if target_node_id is not None:
            target_item = next(
                (
                    item
                    for item in reversed(list(self._canvas._local_node_objects.values()))
                    if item.node_id == target_node_id
                ),
                None,
            )
            if target_item is not None:
                target_anchor = target_item.link_anchor_toward(source_center)
        preview_item = QKnowledgeGraphLinkCanvasObject(
            link_id="__preview_link__",
            source_anchor=source_anchor,
            target_anchor=target_anchor,
            color=color,
            outgoing_label=None,
            incoming_label=None,
            preview=True,
            on_select=None,
        )
        self._canvas.add_object(preview_item)
        self._canvas._preview_link_item = preview_item

    def clear_link_preview(self) -> None:
        if self._canvas._preview_link_item is None:
            return
        self._canvas.remove_object(self._canvas._preview_link_item)
        self._canvas._preview_link_item = None

    def handle_drag_enter(self, event: QDragEnterEvent) -> bool:
        link_type_id = link_type_id_from_event(event)
        if not link_type_id:
            return False
        self._canvas.link_source_drag_started.emit(link_type_id)
        event.acceptProposedAction()
        return True

    def handle_drag_move(self, event: QDragMoveEvent) -> bool:
        link_type_id = link_type_id_from_event(event)
        if not link_type_id:
            return False
        candidate = self.candidate_source_node_id_from_screen(
            float(event.position().x()),
            float(event.position().y()),
        )
        self._canvas.link_source_drag_hovered.emit(link_type_id, candidate)
        event.acceptProposedAction()
        return True

    def handle_drag_leave(self, event: QDragLeaveEvent) -> None:
        self._canvas.link_source_drag_hovered.emit("", None)

    def handle_drop(self, event: QDropEvent) -> bool:
        link_type_id = link_type_id_from_event(event)
        if not link_type_id:
            return False
        candidate = self.candidate_source_node_id_from_screen(
            float(event.position().x()),
            float(event.position().y()),
        )
        self._canvas.link_source_drop_finished.emit(link_type_id, candidate)
        event.acceptProposedAction()
        return True

    def handle_key_press(self, event: QKeyEvent) -> bool:
        if not self._canvas._link_creation_modal_active:
            return False
        from PySide6.QtGui import QKeySequence

        seq = QKeySequence(event.keyCombination()).toString()
        if get_default_bindings().matches_key(GRAPH_LINK_CREATE_CANCEL.id, seq):
            self._canvas.link_creation_cancel_requested.emit()
            event.accept()
            return True
        return False

    def handle_mouse_press(self, event: QMouseEvent) -> bool:
        if self._canvas._link_creation_modal_active and self._canvas._link_creation_target_mode:
            button = qt_button_to_logical(event.button())
            if button is not None:
                mods = qt_modifiers_to_logical(event.modifiers())
                if get_default_bindings().matches_mouse(
                    GRAPH_LINK_CREATE_TARGET_COMMIT.id,
                    button,
                    mods,
                    GestureKind.PRESS,
                ):
                    candidate = self.candidate_source_node_id_from_screen(
                        float(event.position().x()),
                        float(event.position().y()),
                    )
                    wx, wy = self._canvas._screen_to_world(
                        float(event.position().x()),
                        float(event.position().y()),
                    )
                    self._canvas.link_target_clicked.emit(candidate, wx, wy)
                    event.accept()
                    return True
        if self._canvas._link_creation_modal_active:
            button = qt_button_to_logical(event.button())
            if button is not None:
                mods = qt_modifiers_to_logical(event.modifiers())
                if get_default_bindings().matches_mouse(
                    GRAPH_LINK_CREATE_CANCEL.id,
                    button,
                    mods,
                    GestureKind.PRESS,
                ):
                    self._canvas.link_creation_cancel_requested.emit()
                    event.accept()
                    return True
        return False

    def handle_mouse_move(self, event: QMouseEvent) -> bool:
        if not (
            self._canvas._link_creation_modal_active
            and self._canvas._link_creation_target_mode
        ):
            return False
        candidate = self.candidate_source_node_id_from_screen(
            float(event.position().x()),
            float(event.position().y()),
        )
        wx, wy = self._canvas._screen_to_world(
            float(event.position().x()),
            float(event.position().y()),
        )
        self._canvas.link_target_hovered.emit(candidate, wx, wy)
        return False


__all__ = [
    "GraphLinkGestures",
    "LINK_TYPE_MIME",
    "link_type_id_from_event",
]

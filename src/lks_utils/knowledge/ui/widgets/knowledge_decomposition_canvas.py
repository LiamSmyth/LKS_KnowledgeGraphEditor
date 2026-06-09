"""Canvas2D wrapper used by knowledge decomposition for drop + delete behavior."""
from __future__ import annotations

from typing import Protocol

from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QKeyEvent, QKeySequence

from lks_utils.gui_qt.canvas2d import CANVAS_DELETE_SELECTED
from lks_utils.gui_qt.canvas2d.widgets.canvas_widget_policies import CanvasWidgetPolicies
from lks_utils.input import get_default_bindings
from lks_utils.knowledge.ui.components.library_panel import MIME_KNOWLEDGE_NODE_ID
from lks_utils.knowledge.ui.widgets.knowledge_edit_canvas import QKnowledgeEditCanvasWidget


class _DecompositionCanvasOwner(Protocol):
    def delete_selected_components(self) -> bool: ...
    def can_accept_drop(self, node_id: str, position: object) -> bool: ...
    def can_accept_palette_drop(self, palette_id: str) -> bool: ...
    def apply_drop(self, node_id: str, position: object) -> bool: ...
    def apply_palette_drop(self, palette_id: str) -> bool: ...


class _KnowledgeDecompositionCanvas(QKnowledgeEditCanvasWidget):
    """Canvas with drop support for both node-id and palette-component MIME."""

    def __init__(
        self,
        owner: _DecompositionCanvasOwner,
        palette_component_mime: str,
        parent=None,
    ) -> None:
        super().__init__(
            parent,
            capabilities=CanvasWidgetPolicies(
                allow_selection=True,
                bring_selected_to_front=False,
                allow_multi_select=False,
                allow_range_select=False,
                allow_drag=True,
                allow_add_remove=True,
                allow_undo_redo=True,
                allow_clipboard=True,
            ),
        )
        self._owner = owner
        self._palette_component_mime = palette_component_mime

    def keyPressEvent(self, event: QKeyEvent) -> None:
        seq = QKeySequence(event.keyCombination()).toString()
        bindings = get_default_bindings()
        if bindings.matches_key(CANVAS_DELETE_SELECTED.id, seq):
            if self._owner.delete_selected_components():
                event.accept()
                return
        super().keyPressEvent(event)

    def _node_id_from_event(self, event: QDragEnterEvent | QDragMoveEvent | QDropEvent) -> str | None:
        raw = event.mimeData().data(MIME_KNOWLEDGE_NODE_ID)
        if raw:
            try:
                return bytes(raw).decode("utf-8")
            except Exception:
                return None
        return None

    def _palette_id_from_event(self, event: QDragEnterEvent | QDragMoveEvent | QDropEvent) -> str | None:
        raw = event.mimeData().data(self._palette_component_mime)
        if raw:
            try:
                return bytes(raw).decode("utf-8")
            except Exception:
                return None
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        node_id = self._node_id_from_event(event)
        if node_id and self._owner.can_accept_drop(node_id, event.position()):
            event.acceptProposedAction()
            return
        palette_id = self._palette_id_from_event(event)
        if palette_id and self._owner.can_accept_palette_drop(palette_id):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        node_id = self._node_id_from_event(event)
        if node_id and self._owner.can_accept_drop(node_id, event.position()):
            event.acceptProposedAction()
            return
        palette_id = self._palette_id_from_event(event)
        if palette_id and self._owner.can_accept_palette_drop(palette_id):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        node_id = self._node_id_from_event(event)
        if node_id and self._owner.apply_drop(node_id, event.position()):
            event.acceptProposedAction()
            return
        palette_id = self._palette_id_from_event(event)
        if palette_id and self._owner.apply_palette_drop(palette_id):
            event.acceptProposedAction()
            return
        super().dropEvent(event)


__all__ = ["_KnowledgeDecompositionCanvas"]

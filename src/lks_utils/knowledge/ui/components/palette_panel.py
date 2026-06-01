"""Palette panel showing valid graph-item components for the current edit context."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QWidget,
)
from PySide6.QtCore import QMimeData

from lks_utils.gui_qt.components.q_palette_panel_base import QPalettePanelBase
from lks_utils.knowledge.default_theme import EDGE_COLOR, NODE_TEXT_COLOR, SCENE_BACKGROUND_COLOR
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.models.node import Node

# Palette component identifiers
PALETTE_PROPERTY = "property"
# Backward-compatible component IDs accepted by older tests/drag payloads.
PALETTE_SLOT_LITERAL = "slot:literal"
PALETTE_SLOT_REF = "slot:ref"

# MIME type used when dragging a palette item to the canvas
MIME_KNOWLEDGE_PALETTE_COMPONENT = "application/x-lks-knowledge-palette-component"


class _PaletteListWidget(QListWidget):
    """QListWidget that starts a drag carrying the palette component MIME type."""

    # type: ignore[override]
    def startDrag(self, supported_actions: Qt.DropActions) -> None:
        item = self.currentItem()
        if item is None:
            return
        component_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(component_id, str):
            return
        mime = QMimeData()
        mime.setData(MIME_KNOWLEDGE_PALETTE_COMPONENT,
                     component_id.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)


def _type_palette_items() -> list[tuple[str, str]]:
    """Return ``(display_label, component_id)`` pairs for the TYPE context."""
    return [
        ("Property", PALETTE_PROPERTY),
    ]


class QKnowledgePalettePanel(QPalettePanelBase):
    """Palette listing valid components for the type editor.

    Visible only in the type editing context. Shows **Property** to add a new
    slot. Double-clicking emits :attr:`component_activated` with the
    component's identifier string.
    """

    component_activated = Signal(str)  # component_id str

    def __init__(
        self,
        session: EditorSession,
        parent: QWidget | None = None,
    ) -> None:
        self._session = session
        self._list = _PaletteListWidget(None)
        self._list.setDragEnabled(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        super().__init__("Palette", content=self._list, parent=parent)
        self._wire_signals()
        self._apply_styles()
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the palette item list."""
        self._list.clear()
        for label, component_id in _type_palette_items():
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, component_id)
            self._list.addItem(item)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QListWidget {{ background: {SCENE_BACKGROUND_COLOR}; border: 1px solid {EDGE_COLOR}; }}"
        )

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        component_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(component_id, str):
            self.component_activated.emit(component_id)


__all__ = [
    "QKnowledgePalettePanel",
    "PALETTE_PROPERTY",
    "PALETTE_SLOT_LITERAL",
    "PALETTE_SLOT_REF",
    "MIME_KNOWLEDGE_PALETTE_COMPONENT",
]

"""Canvas widget for editing a single link type."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.knowledge.display_color import effective_link_type_display_color
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.ui.components.field_row_factory import FieldRow
from lks_utils.knowledge.ui.widgets.knowledge_edit_canvas import QKnowledgeEditCanvasWidget
from lks_utils.knowledge.ui.widgets.field_node_canvas_item import (
    QKnowledgeFieldNodeCanvasItem,
    knowledge_field_node_height_for_rows,
)

_ROOT_X0 = 80.0
_ROOT_Y0 = 220.0
_ROOT_W = 520.0


class QKnowledgeLinkTypeCanvasWidget(QWidget):
    """Canvas showing a single link type using the standard knowledge card style."""

    selection_changed = Signal(bool)  # True if selected, False if cleared

    def __init__(
        self,
        session: EditorSession,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._link_type: LinkType | None = None
        self._canvas_items: list[CanvasItem] = []

        self._canvas = QKnowledgeEditCanvasWidget(self)
        self._canvas.setMinimumSize(720, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._canvas)

    def open_link_type(self, link_type: LinkType | None) -> None:
        """Load a link type into the canvas."""
        self._link_type = link_type
        self._clear_canvas()
        if link_type is None:
            self.selection_changed.emit(False)
            return

        rows = self._rows_for_link_type(link_type)
        root_h = knowledge_field_node_height_for_rows(rows)
        root = QKnowledgeFieldNodeCanvasItem(
            node_id=str(link_type.id),
            node_name=link_type.name,
            x=_ROOT_X0,
            y=_ROOT_Y0,
            width=_ROOT_W,
            height=root_h,
            rows=rows,
            is_root=True,
            header_bg_color=effective_link_type_display_color(link_type),
            header_subtitle="link_type",
        )
        self._add_item(root)
        self._canvas.fit_to_content(buffer_world_px=40.0)
        self._canvas.camera.set_zoom(
            min(self._canvas.camera.view().zoom, 1.35))
        self.selection_changed.emit(True)

    def clear(self) -> None:
        """Clear the canvas."""
        self._link_type = None
        self._clear_canvas()
        self.selection_changed.emit(False)

    def get_selected_link_type(self) -> LinkType | None:
        """Return the currently loaded link type."""
        return self._link_type

    def _add_item(self, item: CanvasItem) -> None:
        self._canvas.add_item(item)
        self._canvas_items.append(item)

    def _clear_canvas(self) -> None:
        for item in self._canvas_items:
            self._canvas.remove_item(item)
        self._canvas_items = []

    def _rows_for_link_type(self, link_type: LinkType) -> list[FieldRow]:
        cardinality = (
            link_type.cardinality.value
            if hasattr(link_type.cardinality, "value")
            else str(link_type.cardinality)
        )
        return [
            FieldRow("nested", "inverse_name", "inverse_name",
                     link_type.inverse_name, []),
            FieldRow("nested", "source_constraint", "source_constraint",
                     link_type.source_type_constraint or "(none)", []),
            FieldRow("nested", "target_constraint", "target_constraint",
                     link_type.target_type_constraint or "(none)", []),
            FieldRow("nested", "cardinality", "cardinality", cardinality, []),
            FieldRow("nested", "description", "description",
                     link_type.description or "(none)", []),
        ]


__all__ = ["QKnowledgeLinkTypeCanvasWidget"]

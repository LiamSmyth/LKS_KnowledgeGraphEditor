"""SelectableCapability — selection chrome driven by scene SelectionModel."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen

from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability import CanvasObjectCapability
from lks_utils.gui_qt.theme.palette import PALETTE

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
    from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext


class SelectableCapability(CanvasObjectCapability):
    """Integrates host selection with the scene :class:`SelectionModel`."""

    capability_id = "selectable"
    schema_version = 1

    _SELECTED_LINE_WIDTH_PX: float = 2.0
    _ACTIVE_LINE_WIDTH_PX: float = 3.2

    def handle_input(self, event: CanvasInputEvent) -> bool:
        host = self._host
        if host is None or event.phase != "press":
            return False
        selection = host.selection_model()
        if selection is None:
            return False
        from lks_utils.input import Modifier

        additive = Modifier.SHIFT in event.modifiers
        toggle = Modifier.CTRL in event.modifiers
        if toggle:
            selection.toggle(host)
        elif additive:
            selection.select(host, additive=True)
        else:
            selection.select(host, additive=False)
        host.request_repaint()
        return False

    def paint_chrome(self, ctx: CanvasPaintContext) -> None:
        host = self._host
        if host is None:
            return
        selection = host.selection_model()
        if selection is None or not selection.is_selected(host):
            return
        bounds = host.bounds()
        accent = QColor(PALETTE["selection_marquee"])
        is_active = selection.active_object() is host
        painter = ctx.painter
        painter.save()
        pen = QPen(accent, self._SELECTED_LINE_WIDTH_PX)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(
            bounds.x0,
            bounds.y0,
            bounds.width,
            bounds.height,
        )
        if is_active:
            active_pen = QPen(accent, self._ACTIVE_LINE_WIDTH_PX)
            active_pen.setCosmetic(True)
            painter.setPen(active_pen)
            painter.drawRect(
                bounds.x0,
                bounds.y0,
                bounds.width,
                bounds.height,
            )
        painter.restore()


__all__ = ["SelectableCapability"]

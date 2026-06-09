"""`SelectionOverlay`: accent-coloured borders around selected canvas items."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.core.selection_model import SelectionModel


class SelectionOverlay(ViewportOverlay):
    """World-space overlay that draws selection borders around every selected object.

    Instantiate once per :class:`Canvas2DWidget` and register it via
    :meth:`Canvas2DWidget.add_overlay`.  Connect the scene's
    ``selection_changed`` signal to :meth:`_on_selection_changed` so the
    overlay refreshes whenever the selection mutates.

    Args:
        selection: The :class:`~lks_utils.gui_qt.canvas2d.core.selection_model.SelectionModel`
                   to mirror.
        line_width_px: Width of the selection-border stroke in logical pixels.
    """

    screen_space = False
    accepts_input = False
    supports_gpu_rendering = False
    z_order = -1

    _DEFAULT_LINE_WIDTH: float = 4.0

    def __init__(
        self,
        selection: SelectionModel,
        *,
        line_width_px: float = _DEFAULT_LINE_WIDTH,
    ) -> None:
        super().__init__()
        self._selection = selection

        accent = QColor(PALETTE["selection_marquee"])
        self._pen_border = QPen(accent, line_width_px)
        # width stays constant regardless of zoom
        self._pen_border.setCosmetic(True)

        # Re-render whenever the selection changes.
        self._selection.selection_changed.connect(self._on_selection_changed)

    # ------------------------------------------------------------------ #
    # Slot                                                                 #
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self) -> None:
        self.request_repaint()

    # ------------------------------------------------------------------ #
    # Overlay API                                                          #
    # ------------------------------------------------------------------ #

    def paint(self, ctx: CanvasPaintContext) -> None:
        """Draw selection borders in world space."""
        objects = self._selection.selected_objects()
        if not objects:
            return

        p = ctx.painter
        p.save()

        for obj in objects:
            # Skip objects that paint their own selection indicator.
            if getattr(obj, "manages_own_selection_highlight", False):
                continue

            bounds = obj.bounds()
            if bounds is None:
                continue

            # Dashed border around the object's world-space AABB.
            p.setPen(self._pen_border)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(bounds.x0, bounds.y0, bounds.width, bounds.height)

        p.restore()

    def to_dict(self) -> dict | None:  # type: ignore[override]
        """Transient overlay — not persisted."""
        return None

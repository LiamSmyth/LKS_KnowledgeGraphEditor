"""`ImageCanvasObject`: a canvas object that renders a file-backed raster image."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPen, QPixmap

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.canvas_object_registry import register_canvas_object_type
from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.spatial.aabb import AABB

#: File extensions accepted as image drops.
IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif",
})


@register_canvas_object_type("canvas2d.image_object")
class ImageCanvasObject(CanvasObject):
    """A raster image rendered at a given world-space rectangle.

    The image file is loaded lazily on first paint and cached as a
    ``QPixmap``.  Only the file path and world rect are persisted —
    no pixel data is embedded in the serialised form.

    Args:
        image_path: Absolute or relative path to the image file.
        world_rect: Position and size in world coordinates.  The natural
            size (1 pixel = 1 world unit) is used when constructing the
            rect from a drop position.
    """

    #: Registry key used in :meth:`to_dict` and by
    #: :func:`~lks_utils.gui_qt.canvas2d.canvas_object_registry.register_canvas_object_type`.
    OBJECT_TYPE: str = "canvas2d.image_object"

    def __init__(self, image_path: Path | str, world_rect: QRectF) -> None:
        super().__init__()
        self._image_path: Path = Path(image_path)
        self._world_rect: QRectF = QRectF(world_rect)
        self._pixmap: QPixmap | None = None
        self._load_failed: bool = False

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def image_path(self) -> Path:
        """Absolute (or as-stored relative) path to the image file."""
        return self._image_path

    @property
    def world_rect(self) -> QRectF:
        """World-space rectangle (copy) that the image occupies."""
        return QRectF(self._world_rect)

    # ------------------------------------------------------------------ #
    # CanvasObject interface                                                 #
    # ------------------------------------------------------------------ #

    def bounds(self) -> AABB:
        r = self._world_rect
        return AABB(r.left(), r.top(), r.right(), r.bottom())  # x0, y0, x1, y1

    def paint(self, ctx: CanvasPaintContext) -> None:
        """Draw the image inside *world_rect*.

        The painter's transform is already set to world-space by the
        renderer, so we can draw directly in world coordinates.  On load
        failure a red cross placeholder is shown instead.
        """
        self._ensure_pixmap()
        p = ctx.painter

        if self._load_failed or self._pixmap is None or self._pixmap.isNull():
            # Placeholder: red bounding rect with an X through it.
            p.save()
            pen = QPen(QColor(220, 60, 60))
            pen.setCosmetic(True)
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.setBrush(QColor(220, 60, 60, 30))
            p.drawRect(self._world_rect)
            p.drawLine(self._world_rect.topLeft(), self._world_rect.bottomRight())
            p.drawLine(self._world_rect.topRight(), self._world_rect.bottomLeft())
            p.restore()
            return

        # Draw the full pixmap scaled into world_rect.
        # The world-to-screen QPainter transform has Y flipped (world Y-up →
        # screen Y-down), which would render the image upside-down.  Counter-
        # rotate by flipping Y around the rect's vertical centre.
        cx = self._world_rect.center().x()
        cy = self._world_rect.center().y()
        p.save()
        p.translate(cx, cy)
        p.scale(1.0, -1.0)
        p.translate(-cx, -cy)
        p.drawPixmap(self._world_rect, self._pixmap, QRectF(self._pixmap.rect()))
        p.restore()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        r = self._world_rect
        return {
            "type": self.OBJECT_TYPE,
            "image_path": str(self._image_path),
            "world_rect": {
                "x": r.x(),
                "y": r.y(),
                "w": r.width(),
                "h": r.height(),
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> ImageCanvasObject:
        r = d["world_rect"]
        world_rect = QRectF(r["x"], r["y"], r["w"], r["h"])
        return cls(image_path=d["image_path"], world_rect=world_rect)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _ensure_pixmap(self) -> None:
        """Load the image lazily; mark *_load_failed* on error."""
        if self._pixmap is not None or self._load_failed:
            return
        pixmap = QPixmap(str(self._image_path))
        if pixmap.isNull():
            self._load_failed = True
        else:
            self._pixmap = pixmap


__all__ = ["ImageCanvasObject", "IMAGE_EXTENSIONS"]

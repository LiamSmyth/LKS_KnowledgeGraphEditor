"""QImageViewer — generic 2D image viewer with zoom and pan.

Reusable PySide6 widget that displays a NumPy array (float32 or uint8)
as a 2D image.  Supports:
- Zoom via scroll wheel (centered on cursor).
- Pan via middle-mouse-button drag or Shift+left-drag.
- Fit-to-view on double-click.
- Pixel value readout on hover (emitted via signal).
- Grayscale and RGB/multi-channel arrays.
- Optional colormap for single-channel float data.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap, QTransform, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

_MIN_ZOOM: float = 0.01
_MAX_ZOOM: float = 100.0
_ZOOM_FACTOR: float = 1.15


def _numpy_to_qimage(data: np.ndarray) -> QImage:
    """Convert a NumPy array to ``QImage``.

    Accepts:
    - 2-D float32 → grayscale (scaled 0–1 → 0–255)
    - 2-D uint8 → grayscale
    - 3-D float32 with 1, 3, or 4 channels → converted to uint8
    - 3-D uint8 with 1, 3, or 4 channels → direct

    Returns:
        QImage in Format_Grayscale8, Format_RGB888, or Format_RGBA8888.
    """
    if data.ndim == 2:
        if data.dtype == np.float32 or data.dtype == np.float64:
            arr = np.clip(data * 255.0, 0, 255).astype(np.uint8)
        else:
            arr = data.astype(np.uint8)
        h, w = arr.shape
        return QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8).copy()

    if data.ndim == 3:
        h, w, c = data.shape
        if data.dtype == np.float32 or data.dtype == np.float64:
            arr = np.clip(data * 255.0, 0, 255).astype(np.uint8)
        else:
            arr = data.astype(np.uint8)

        if c == 1:
            arr = arr[:, :, 0]
            return QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        if c == 3:
            return QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        if c == 4:
            return QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()

    msg = f"Unsupported array shape {data.shape} / dtype {data.dtype}"
    raise ValueError(msg)


class QImageViewer(QWidget):
    """Zoomable, pannable 2D image viewer.

    Signals:
        pixel_hovered(int, int, str):
            Emitted on mouse move with (x, y, value_text) of the pixel under cursor.
        zoom_changed(float):
            Emitted when zoom level changes.
    """

    pixel_hovered: Signal = Signal(int, int, str)
    zoom_changed: Signal = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._source_data: np.ndarray | None = None
        self._zoom: float = 1.0
        self._pan: QPointF = QPointF(0.0, 0.0)
        self._drag_start: QPointF | None = None
        self._pan_start: QPointF = QPointF(0.0, 0.0)
        self._image_w: int = 0
        self._image_h: int = 0
        # Tile padding: number of extra tile copies in each direction.
        # 0 = no tiling; 1 = one copy on each side (3×3 total); 2 = 5×5; …
        self._tile_padding: int = 0
        # When True, draw a subtle yellow outline around the central tile.
        self._tile_border: bool = False

        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_image(self, data: np.ndarray) -> None:
        """Display *data* as a 2D image and fit to view.

        Args:
            data: 2-D (H\u00d7W) or 3-D (H\u00d7W\u00d7C) NumPy array, float32 or uint8.
        """
        self._source_data = data
        qimg = _numpy_to_qimage(data)
        self._pixmap = QPixmap.fromImage(qimg)
        self._image_w = qimg.width()
        self._image_h = qimg.height()
        self.fit_to_view()

    def update_image(self, data: np.ndarray) -> None:
        """Update the displayed image without resetting zoom or pan.

        Useful for refreshing the same image data (e.g. toggle between raw and
        processed) while preserving the user's current zoom/pan state.

        Args:
            data: 2-D (H\u00d7W) or 3-D (H\u00d7W\u00d7C) NumPy array, float32 or uint8.
        """
        self._source_data = data
        qimg = _numpy_to_qimage(data)
        self._pixmap = QPixmap.fromImage(qimg)
        new_w = qimg.width()
        new_h = qimg.height()
        if new_w != self._image_w or new_h != self._image_h:
            # Image dimensions changed — fit to view to avoid incorrect pan offsets
            self._image_w = new_w
            self._image_h = new_h
            self.fit_to_view()
        else:
            self.update()

    def clear_image(self) -> None:
        """Remove the displayed image."""
        self._pixmap = None
        self._source_data = None
        self._image_w = 0
        self._image_h = 0
        self.update()

    def get_zoom(self) -> float:
        """Return current zoom level."""
        return self._zoom

    def set_zoom(self, zoom: float) -> None:
        """Set zoom level (clamped)."""
        self._zoom = max(_MIN_ZOOM, min(zoom, _MAX_ZOOM))
        self.zoom_changed.emit(self._zoom)
        self.update()

    def fit_to_view(self) -> None:
        """Reset zoom and pan so the image fills the widget."""
        if self._image_w == 0 or self._image_h == 0:
            return
        scale_x = self.width() / self._image_w
        scale_y = self.height() / self._image_h
        self._zoom = min(scale_x, scale_y) * 0.95
        self._zoom = max(_MIN_ZOOM, min(self._zoom, _MAX_ZOOM))
        # Center the image
        self._pan = QPointF(
            (self.width() - self._image_w * self._zoom) / 2.0,
            (self.height() - self._image_h * self._zoom) / 2.0,
        )
        self.zoom_changed.emit(self._zoom)
        self.update()

    def set_tile_border(self, enabled: bool) -> None:
        """Show or hide a subtle yellow outline around the central tile.

        The border is drawn in image coordinates and scales with zoom, so it
        is always one tile-edge wide regardless of the tile padding value.

        Args:
            enabled: True to show the border, False to hide it.
        """
        self._tile_border = bool(enabled)
        self.update()

    def set_tiling(self, padding: int) -> None:
        """Set the number of extra tile copies drawn in each direction.

        The central tile (at image origin) is always drawn; *padding* controls
        how many additional copies appear on each side:

        - ``0`` — no tiling (default)
        - ``1`` — one copy on every side: 3×3 total
        - ``2`` — 5×5 total, …

        Zoom and pan are not changed; the central tile stays at the same
        position and the surrounding copies extend outward.

        Args:
            padding: Non-negative integer tile count per side.
        """
        self._tile_padding = max(0, int(padding))
        self.update()

    def has_image(self) -> bool:
        """Return True if an image is currently loaded."""
        return self._pixmap is not None

    # ------------------------------------------------------------------
    # Coordinate mapping
    # ------------------------------------------------------------------

    def _widget_to_image(self, pos: QPointF) -> tuple[int, int]:
        """Convert widget pixel coordinates to image pixel coordinates."""
        ix = int((pos.x() - self._pan.x()) / self._zoom)
        iy = int((pos.y() - self._pan.y()) / self._zoom)
        return ix, iy

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        """Render the image with current zoom and pan."""
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform, self._zoom < 1.0)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        if self._pixmap is None:
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No image")
            painter.end()
            return

        transform = QTransform()
        transform.translate(self._pan.x(), self._pan.y())
        transform.scale(self._zoom, self._zoom)
        painter.setTransform(transform)

        w = self._image_w
        h = self._image_h
        n = self._tile_padding
        if n > 0:
            # Draw surrounding tile copies first so the central tile renders on top.
            for row in range(-n, n + 1):
                for col in range(-n, n + 1):
                    if row != 0 or col != 0:
                        painter.drawPixmap(col * w, row * h, self._pixmap)
        painter.drawPixmap(0, 0, self._pixmap)

        if self._tile_border:
            pen = QPen(QColor(255, 210, 0, 140))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(0, 0, w - 1, h - 1))

        painter.end()

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Zoom centered on cursor position."""
        if self._pixmap is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return

        factor = _ZOOM_FACTOR if delta > 0 else 1.0 / _ZOOM_FACTOR
        new_zoom = max(_MIN_ZOOM, min(self._zoom * factor, _MAX_ZOOM))

        # Zoom centered on cursor
        cursor_pos = event.position()
        old_img_x = (cursor_pos.x() - self._pan.x()) / self._zoom
        old_img_y = (cursor_pos.y() - self._pan.y()) / self._zoom

        self._zoom = new_zoom
        self._pan = QPointF(
            cursor_pos.x() - old_img_x * self._zoom,
            cursor_pos.y() - old_img_y * self._zoom,
        )
        self.zoom_changed.emit(self._zoom)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Start panning on middle button or Shift+left."""
        if (event.button() == Qt.MouseButton.MiddleButton
                or (event.button() == Qt.MouseButton.LeftButton
                    and event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self._drag_start = event.position()
            self._pan_start = QPointF(self._pan)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handle pan dragging and pixel hover readout."""
        if self._drag_start is not None:
            delta = event.position() - self._drag_start
            self._pan = self._pan_start + delta
            self.update()
            return

        # Pixel hover readout
        if self._source_data is not None:
            ix, iy = self._widget_to_image(event.position())
            if 0 <= ix < self._image_w and 0 <= iy < self._image_h:
                val = self._source_data[iy,
                                        ix] if self._source_data.ndim == 2 else self._source_data[iy, ix]
                if isinstance(val, np.ndarray):
                    val_str = ", ".join(f"{v:.4g}" for v in val)
                else:
                    val_str = f"{val:.6g}"
                self.pixel_hovered.emit(ix, iy, val_str)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Stop panning."""
        if self._drag_start is not None:
            self._drag_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Fit to view on double-click."""
        self.fit_to_view()

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        """Re-fit if no explicit zoom was set."""
        super().resizeEvent(event)


__all__ = ["QImageViewer"]

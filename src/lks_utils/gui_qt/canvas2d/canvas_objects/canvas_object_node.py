"""Generic card/node canvas object geometry and header metadata.

Visible node chrome is rendered only through :class:`CanvasNodeObjectPixmap`
(Qt widget → cached pixmap blit). This base class owns host geometry,
header spec, and capability-host hooks — not vector GL/header painting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
    CapabilityHostObject,
)
from lks_utils.gui_qt.theme.palette import PALETTE

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext


DEFAULT_HEADER_HEIGHT_WORLD: float = 21.0
DEFAULT_CONTENT_PADDING_WORLD: float = 8.0
DEFAULT_CARD_CORNER_RADIUS: float = 4.0


class CanvasNodeSizeMode(str, Enum):
    """How ``host_rect`` is determined."""

    AUTO = "auto"
    USER_OVERRIDE = "user_override"


@dataclass(frozen=True, slots=True)
class CanvasNodeHeaderActionSlot:
    """Reserved header action slot (WO3 may wire icon buttons here)."""

    width_world: float = 11.0
    height_world: float = 11.0
    tooltip: str = ""


@dataclass(slots=True)
class CanvasNodeHeaderSpec:
    """Header ribbon metadata for canvas node objects."""

    title: str
    subtitle: str | None = None
    background_color: QColor = field(
        default_factory=lambda: QColor(PALETTE["canvas2d_node_header_bg"])
    )
    title_color: QColor = field(
        default_factory=lambda: QColor(PALETTE["canvas2d_node_header_title"])
    )
    subtitle_color: QColor | None = None
    separator_color: QColor | None = None
    stroke_color: QColor = field(
        default_factory=lambda: QColor(PALETTE["canvas2d_node_stroke"])
    )
    fill_color: QColor = field(
        default_factory=lambda: QColor(PALETTE["canvas2d_node_fill"])
    )
    action_slots: tuple[CanvasNodeHeaderActionSlot, ...] = ()
    title_font_px: int = 12
    subtitle_font_px: int = 10


class CanvasNodeObject(CapabilityHostObject):
    """Card-shaped canvas node host with header metadata and derived layout rects.

  Subclass :class:`~lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_node_pixmap.CanvasNodeObjectPixmap`
    (or a domain pixmap subclass) for any visible node — pixmap compositing is
    the only supported paint path for node chrome.
    """

    def __init__(
        self,
        *,
        host_rect: QRectF,
        header: CanvasNodeHeaderSpec,
        size_mode: CanvasNodeSizeMode = CanvasNodeSizeMode.USER_OVERRIDE,
        header_height_world: float = DEFAULT_HEADER_HEIGHT_WORLD,
        content_padding_world: float = DEFAULT_CONTENT_PADDING_WORLD,
    ) -> None:
        super().__init__(host_rect=host_rect)
        self._header = header
        self._size_mode = size_mode
        self._header_height_world = float(header_height_world)
        self._content_padding_world = float(content_padding_world)

    @property
    def header(self) -> CanvasNodeHeaderSpec:
        return self._header

    @property
    def size_mode(self) -> CanvasNodeSizeMode:
        return self._size_mode

    @size_mode.setter
    def size_mode(self, value: CanvasNodeSizeMode) -> None:
        self._size_mode = value

    @property
    def content_rect(self) -> QRectF:
        """Body region below the header band, inset by content padding."""
        host = self._host_rect
        inner_left = host.left() + self._content_padding_world
        inner_right = host.right() - self._content_padding_world
        inner_bottom = host.top() + self._content_padding_world
        inner_top = host.bottom() - self._header_height_world - 3.5
        width = max(0.0, inner_right - inner_left)
        height = max(0.0, inner_top - inner_bottom)
        return QRectF(inner_left, inner_bottom, width, height)

    @property
    def header_rect(self) -> QRectF:
        host = self._host_rect
        return QRectF(
            host.left() + 1.0,
            host.bottom() - self._header_height_world - 1.0,
            max(0.0, host.width() - 2.0),
            self._header_height_world,
        )

    def set_header(self, header: CanvasNodeHeaderSpec) -> None:
        self._header = header
        self.request_repaint(self.bounds())

    def apply_auto_host_rect(
        self,
        *,
        content_width: float,
        content_height: float,
    ) -> None:
        """Derive ``host_rect`` from intrinsic content size plus header chrome."""
        pad = self._content_padding_world
        width = max(1.0, float(content_width) + (pad * 2.0))
        height = max(
            1.0,
            float(content_height)
            + self._header_height_world
            + 3.5
            + (pad * 2.0),
        )
        host = self._host_rect
        self._host_rect = QRectF(host.left(), host.bottom(), width, height)
        self._on_host_rect_changed()
        self.request_repaint(self.bounds())

    def _on_host_rect_changed(self) -> None:
        """Hook for subclasses to cascade rect changes into content providers."""

    def paint_host_content(self, ctx: CanvasPaintContext) -> None:
        """No-op on the base class; pixmap subclasses paint Qt widget content."""
        return None


__all__ = [
    "CanvasNodeHeaderActionSlot",
    "CanvasNodeHeaderSpec",
    "CanvasNodeObject",
    "CanvasNodeSizeMode",
    "DEFAULT_CARD_CORNER_RADIUS",
    "DEFAULT_CONTENT_PADDING_WORLD",
    "DEFAULT_HEADER_HEIGHT_WORLD",
]

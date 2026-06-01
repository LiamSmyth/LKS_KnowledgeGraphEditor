"""Canvas2D foundation: a reusable Qt widget for unbounded 2-D viewports.

`Canvas2D` provides pan / zoom / rotation, item placement, dirty
tracking, and overlays. It knows nothing about tiles, brushes, or
pixels — those concerns live in consumer-side `CanvasItem` subclasses.

See ``docs/features/2026-04-29_canvas2d_foundation_feature_spec.md``.
"""
from __future__ import annotations

from lks_utils.gui_qt.canvas2d.actions import (
    CANVAS_COPY,
    CANVAS_CUT,
    CANVAS_DELETE_SELECTED,
    CANVAS_DESELECT_ALL,
    CANVAS_FIT_CONTENT,
    CANVAS_ITEM_DRAG,
    CANVAS_PAN,
    CANVAS_PASTE,
    CANVAS_PRIMARY,
    CANVAS_REDO,
    CANVAS_RESET_VIEW,
    CANVAS_RESET_ZOOM,
    CANVAS_ROTATE,
    CANVAS_SELECT_ALL,
    CANVAS_SECONDARY,
    CANVAS_UNDO,
    CANVAS_ZOOM_IN,
    CANVAS_ZOOM_OUT,
    register_canvas2d_defaults,
)
from lks_utils.gui_qt.canvas2d.canvas2d_capabilities import Canvas2DCapabilities
from lks_utils.gui_qt.canvas2d.command_history import CanvasCommand, CommandHistory
from lks_utils.gui_qt.canvas2d.commands import (
    AddItemCommand,
    CompositeCommand,
    MoveItemsCommand,
    RemoveItemCommand,
)
from lks_utils.gui_qt.canvas2d.canvas_document import CanvasDocument
from lks_utils.gui_qt.canvas2d.canvas_input_event import CanvasInputEvent
from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.gui_qt.canvas2d.canvas_anchored_widget_item import CanvasAnchoredWidgetItem
from lks_utils.gui_qt.canvas2d.canvas_pixmap_widget_item import CanvasPixmapWidgetItem
from lks_utils.gui_qt.canvas2d.canvas_widget_adapter_base import CanvasWidgetAdapterBase
from lks_utils.gui_qt.canvas2d.canvas_item_registry import (
    canvas_item_type_name,
    get_canvas_item_type,
    register_canvas_item_type,
)
from lks_utils.gui_qt.paint.node_header_band_painter import CanvasNodeHeaderPainter
from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.dirty_tracker import DirtyTracker
from lks_utils.gui_qt.canvas2d.image_canvas_item import IMAGE_EXTENSIONS, ImageCanvasItem
from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform
from lks_utils.gui_qt.canvas2d.viewport_overlay import ViewportOverlay
from lks_utils.gui_qt.widgets.canvas_table_rows_painter import (
    CanvasTableColumn,
    CanvasTableRowsPainter,
)

# Widget import is optional (depends on PySide6 + moderngl). Don't fail
# the package import if those are missing.
try:
    from lks_utils.gui_qt.canvas2d.camera2d import Camera2D
    from lks_utils.gui_qt.canvas2d.canvas2d_renderer import FrameTimings, OverlayTiming
    from lks_utils.gui_qt.canvas2d.canvas2d_gl_widget import (
        Canvas2DGLWidget,
        HAS_CANVAS2D_GL,
    )
    from lks_utils.gui_qt.canvas2d.canvas2d_gl_window_widget import (
        Canvas2DGLWindowWidget,
        HAS_CANVAS2D_GL_WINDOW,
    )
    from lks_utils.gui_qt.canvas2d.canvas2d_renderer import Canvas2DRenderer
    from lks_utils.gui_qt.canvas2d.canvas2d_widget import Canvas2D, Canvas2DWidget
    from lks_utils.gui_qt.canvas2d.minimap_widget import MinimapWidget
    from lks_utils.gui_qt.canvas2d.overlays.color_backdrop import ColorBackdrop
    from lks_utils.gui_qt.canvas2d.overlays.selection_overlay import SelectionOverlay
    from lks_utils.gui_qt.canvas2d.scene2d import Scene2D
    from lks_utils.gui_qt.canvas2d.selection_model import SelectionModel
    HAS_CANVAS2D: bool = True
except ImportError:
    Camera2D = None  # type: ignore[assignment,misc]
    Canvas2D = None  # type: ignore[assignment,misc]
    Canvas2DGLWidget = None  # type: ignore[assignment,misc]
    Canvas2DGLWindowWidget = None  # type: ignore[assignment,misc]
    Canvas2DRenderer = None  # type: ignore[assignment,misc]
    Canvas2DWidget = None  # type: ignore[assignment,misc]
    ColorBackdrop = None  # type: ignore[assignment,misc]
    SelectionOverlay = None  # type: ignore[assignment,misc]
    FrameTimings = None  # type: ignore[assignment,misc]
    MinimapWidget = None  # type: ignore[assignment,misc]
    OverlayTiming = None  # type: ignore[assignment,misc]
    Scene2D = None  # type: ignore[assignment,misc]
    SelectionModel = None  # type: ignore[assignment,misc]
    HAS_CANVAS2D_GL = False
    HAS_CANVAS2D_GL_WINDOW = False
    HAS_CANVAS2D = False


__all__ = [
    "ViewTransform",
    "CanvasInputEvent",
    "CanvasItem",
    "CanvasAnchoredWidgetItem",
    "CanvasPixmapWidgetItem",
    "CanvasWidgetAdapterBase",
    "CanvasNodeHeaderPainter",
    "CanvasTableColumn",
    "CanvasTableRowsPainter",
    "CanvasPaintContext",
    "Canvas2DCapabilities",
    "CanvasCommand",
    "CanvasDocument",
    "CommandHistory",
    "CompositeCommand",
    "DirtyTracker",
    "ViewportOverlay",
    "Camera2D",
    "Canvas2D",
    "Canvas2DGLWidget",
    "Canvas2DGLWindowWidget",
    "Canvas2DRenderer",
    "Canvas2DWidget",
    "ColorBackdrop",
    "SelectionOverlay",
    "FrameTimings",
    "OverlayTiming",
    "MinimapWidget",
    "Scene2D",
    "SelectionModel",
    "HAS_CANVAS2D",
    "HAS_CANVAS2D_GL",
    "HAS_CANVAS2D_GL_WINDOW",
    "CANVAS_PAN",
    "CANVAS_ZOOM_IN",
    "CANVAS_ZOOM_OUT",
    "CANVAS_ITEM_DRAG",
    "CANVAS_ROTATE",
    "CANVAS_RESET_VIEW",
    "CANVAS_FIT_CONTENT",
    "CANVAS_RESET_ZOOM",
    "CANVAS_PRIMARY",
    "CANVAS_SECONDARY",
    "CANVAS_DESELECT_ALL",
    "CANVAS_SELECT_ALL",
    "CANVAS_DELETE_SELECTED",
    "CANVAS_COPY",
    "CANVAS_CUT",
    "CANVAS_PASTE",
    "CANVAS_UNDO",
    "CANVAS_REDO",
    "register_canvas2d_defaults",
    "register_canvas_item_type",
    "get_canvas_item_type",
    "canvas_item_type_name",
    "ImageCanvasItem",
    "IMAGE_EXTENSIONS",
    "AddItemCommand",
    "RemoveItemCommand",
    "MoveItemsCommand",
]

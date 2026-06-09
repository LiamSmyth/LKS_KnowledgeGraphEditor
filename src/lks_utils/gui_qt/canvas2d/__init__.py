"""Canvas2D foundation: a reusable Qt widget for unbounded 2-D viewports.

`Canvas2D` provides pan / zoom / rotation, object placement, dirty
tracking, and overlays. It knows nothing about tiles, brushes, or
pixels — those concerns live in consumer-side `CanvasObject` subclasses.

See ``docs/features/2026-04-29_canvas2d_foundation_feature_spec.md``.
"""
from __future__ import annotations

from lks_utils.gui_qt.canvas2d.interaction.actions import (
    CANVAS_COPY,
    CANVAS_CUT,
    CANVAS_DELETE_SELECTED,
    CANVAS_DESELECT_ALL,
    CANVAS_FIT_CONTENT,
    CANVAS_OBJECT_DRAG,
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
from lks_utils.gui_qt.canvas2d.widgets.canvas_widget_policies import CanvasWidgetPolicies
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability import CanvasObjectCapability
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capabilities import (
    DragCapability,
    ResizeRectCapability,
    SelectableCapability,
)
from lks_utils.gui_qt.canvas2d.interaction.command_history import CommandHistory
from lks_utils.gui_qt.canvas2d.interaction.canvas_command import CanvasCommand
from lks_utils.gui_qt.canvas2d.interaction.canvas_commands import (
    AddObjectCommand,
    CompositeCommand,
    MoveObjectsCommand,
    RemoveObjectCommand,
    ResizeObjectCommand,
)
from lks_utils.gui_qt.canvas2d.core.canvas_document import CanvasDocument
from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_widget_adapter_anchored import CanvasAnchoredWidgetObject
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_widget_adapter_pixmap import CanvasPixmapWidgetObject
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_widget_adapter import CanvasObjectWidgetAdapter
from lks_utils.gui_qt.canvas2d.canvas_object_registry import (
    canvas_object_type_name,
    get_canvas_object_type,
    register_canvas_object_type,
)
from lks_utils.gui_qt.canvas2d.canvas_objects import (
    CanvasNodeHeaderSpec,
    CanvasNodeObject,
    CanvasNodeObjectPixmap,
)
from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.core.dirty_tracker import DirtyTracker
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_image import IMAGE_EXTENSIONS, ImageCanvasObject
from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.widgets.canvas_table_rows_painter import (
    CanvasTableColumn,
    CanvasTableRowsPainter,
)

# Widget import is optional (depends on PySide6 + moderngl). Don't fail
# the package import if those are missing.
try:
    from lks_utils.gui_qt.canvas2d.core.camera2d import Camera2D
    from lks_utils.gui_qt.canvas2d.render.canvas_renderer import FrameTimings, OverlayTiming
    from lks_utils.gui_qt.canvas2d.widgets.canvas_widget_gl import (
        Canvas2DGLWidget,
        HAS_CANVAS2D_GL,
    )
    from lks_utils.gui_qt.canvas2d.widgets.canvas_widgets.canvas_widget_gl_window import (
        Canvas2DGLWindowWidget,
        HAS_CANVAS2D_GL_WINDOW,
    )
    from lks_utils.gui_qt.canvas2d.render.canvas_renderer import Canvas2DRenderer
    from lks_utils.gui_qt.canvas2d.widgets.canvas_widget import Canvas2D, Canvas2DWidget
    from lks_utils.gui_qt.canvas2d.widgets.canvas_widgets.widget_minimap import MinimapWidget
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_color_backdrop import ColorBackdrop
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_selection import SelectionOverlay
    from lks_utils.gui_qt.canvas2d.core.scene2d import Scene2D
    from lks_utils.gui_qt.canvas2d.core.selection_model import SelectionModel
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
    "CanvasObject",
    "CanvasAnchoredWidgetObject",
    "CanvasPixmapWidgetObject",
    "CanvasObjectWidgetAdapter",
    "CanvasNodeHeaderSpec",
    "CanvasNodeObject",
    "CanvasNodeObjectPixmap",
    "CanvasTableColumn",
    "CanvasTableRowsPainter",
    "CanvasPaintContext",
    "CanvasWidgetPolicies",
    "CanvasObjectCapability",
    "CanvasCommand",
    "CanvasDocument",
    "CommandHistory",
    "CompositeCommand",
    "DragCapability",
    "ResizeRectCapability",
    "SelectableCapability",
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
    "CANVAS_OBJECT_DRAG",
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
    "register_canvas_object_type",
    "get_canvas_object_type",
    "canvas_object_type_name",
    "ImageCanvasObject",
    "IMAGE_EXTENSIONS",
    "AddObjectCommand",
    "RemoveObjectCommand",
    "MoveObjectsCommand",
    "ResizeObjectCommand",
]

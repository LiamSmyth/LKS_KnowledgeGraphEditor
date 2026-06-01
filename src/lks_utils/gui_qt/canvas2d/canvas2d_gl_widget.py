"""Compatibility alias for the window-backed Canvas2D OpenGL surface.

`Canvas2DGLWidget` is retained for existing canvas2d call sites, but the
implementation now comes from the QOpenGLWindow-based backend.
"""
from __future__ import annotations

from lks_utils.gui_qt.canvas2d.canvas2d_gl_window_widget import (
    Canvas2DGLWindowWidget,
    HAS_CANVAS2D_GL_WINDOW,
)

Canvas2DGLWidget = Canvas2DGLWindowWidget
HAS_CANVAS2D_GL = HAS_CANVAS2D_GL_WINDOW

__all__ = ["Canvas2DGLWidget", "HAS_CANVAS2D_GL"]

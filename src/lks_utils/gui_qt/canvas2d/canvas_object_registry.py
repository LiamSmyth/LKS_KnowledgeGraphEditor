"""`CanvasObjectRegistry`: type → class mapping for canvas object persistence.

Provides a module-level registry used by `Canvas2DWidget.load_document`
to reconstruct `CanvasObject` and `ViewportOverlay` instances from their
serialised dicts.

Usage::

    from lks_utils.gui_qt.canvas2d.canvas_object_registry import (
        register_canvas_object_type,
        get_canvas_object_type,
        canvas_object_type_name,
    )

    # Registering a custom type:
    @register_canvas_object_type("my_app.note_object")
    class NoteObject(CanvasObject):
        ...

    # Or manual registration:
    register_canvas_object_type("my_app.note_object", NoteObject)

    # Looking up and instantiating:
    cls = get_canvas_object_type("my_app.note_object")
    obj = cls.from_dict(data)

The built-in overlays are registered on import of this module so that
:func:`get_canvas_object_type` works for them without any extra setup.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject

_REGISTRY: dict[str, type[Any]] = {}

_LEGACY_TYPE_ALIASES: dict[str, str] = {
    "canvas2d.image_item": "canvas2d.image_object",
    "canvas2d.anchored_widget_item": "canvas2d.anchored_widget_object",
    "canvas2d.pixmap_widget_item": "canvas2d.pixmap_widget_object",
}


def register_canvas_object_type(
    name: str,
    cls: type | None = None,
) -> Any:
    """Register a ``CanvasObject`` subclass under *name*.

    Can be used as a class decorator (when *cls* is ``None``) or
    called directly with both arguments.

    Raises:
        ValueError: If *name* is already registered with a different class.
    """
    if cls is None:
        # Decorator usage: @register_canvas_object_type("foo")
        def _decorator(klass: type) -> type:
            register_canvas_object_type(name, klass)
            return klass
        return _decorator

    existing = _REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"Canvas object type '{name}' is already registered as "
            f"{existing!r}; cannot re-register with {cls!r}."
        )
    _REGISTRY[name] = cls
    return cls


def get_canvas_object_type(name: str) -> type | None:
    """Return the class registered under *name*, or ``None``."""
    cls = _REGISTRY.get(name)
    if cls is not None:
        return cls
    canonical = _LEGACY_TYPE_ALIASES.get(name)
    if canonical is None:
        return None
    return _REGISTRY.get(canonical)


def canvas_object_type_name(cls: type) -> str | None:
    """Return the registry name for *cls*, or ``None`` if not registered."""
    for k, v in _REGISTRY.items():
        if v is cls:
            return k
    return None


# ------------------------------------------------------------------ #
# Bootstrap: register built-ins                                       #
# ------------------------------------------------------------------ #

def _register_builtins() -> None:
    # Lazy local imports so importing the registry does not unconditionally
    # pull in PySide6.
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_canvas_border import (
        CanvasBorderOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_axes_lines import (
        AxesLinesOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_coord_hud import (
        CoordHudOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_checkerboard import (
        CheckerboardOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_dot_grid import (
        DotGridOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_home_grid import (
        HomeGridOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_texture_canvas import (
        TextureCanvasOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_world_grid import (
        WorldGridOverlay,
    )
    register_canvas_object_type("canvas2d.overlays.dot_grid", DotGridOverlay)
    register_canvas_object_type("canvas2d.overlays.world_grid", WorldGridOverlay)
    register_canvas_object_type("canvas2d.overlays.axes_lines", AxesLinesOverlay)
    register_canvas_object_type("canvas2d.overlays.home_grid", HomeGridOverlay)
    register_canvas_object_type(
        "canvas2d.overlays.canvas_border", CanvasBorderOverlay
    )
    register_canvas_object_type("canvas2d.overlays.coord_hud", CoordHudOverlay)
    register_canvas_object_type("canvas2d.overlays.checkerboard", CheckerboardOverlay)
    register_canvas_object_type("canvas2d.overlays.texture_canvas", TextureCanvasOverlay)


_register_builtins()

__all__ = [
    "register_canvas_object_type",
    "get_canvas_object_type",
    "canvas_object_type_name",
]

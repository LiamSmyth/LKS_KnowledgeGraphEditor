"""`CanvasItemRegistry`: type → class mapping for canvas item persistence.

Provides a module-level registry used by `Canvas2DWidget.load_document`
to reconstruct `CanvasItem` and `ViewportOverlay` instances from their
serialised dicts.

Usage::

    from lks_utils.gui_qt.canvas2d.canvas_item_registry import (
        register_canvas_item_type,
        get_canvas_item_type,
        canvas_item_type_name,
    )

    # Registering a custom type:
    @register_canvas_item_type("my_app.note_item")
    class NoteItem(CanvasItem):
        ...

    # Or manual registration:
    register_canvas_item_type("my_app.note_item", NoteItem)

    # Looking up and instantiating:
    cls = get_canvas_item_type("my_app.note_item")
    item = cls.from_dict(data)

The built-in overlays are registered on import of this module so that
:func:`get_canvas_item_type` works for them without any extra setup.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem

_REGISTRY: dict[str, type[Any]] = {}


def register_canvas_item_type(
    name: str,
    cls: type | None = None,
) -> Any:
    """Register a ``CanvasItem`` subclass under *name*.

    Can be used as a class decorator (when *cls* is ``None``) or
    called directly with both arguments.

    Raises:
        ValueError: If *name* is already registered with a different class.
    """
    if cls is None:
        # Decorator usage: @register_canvas_item_type("foo")
        def _decorator(klass: type) -> type:
            register_canvas_item_type(name, klass)
            return klass
        return _decorator

    existing = _REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"Canvas item type '{name}' is already registered as "
            f"{existing!r}; cannot re-register with {cls!r}."
        )
    _REGISTRY[name] = cls
    return cls


def get_canvas_item_type(name: str) -> type | None:
    """Return the class registered under *name*, or ``None``."""
    return _REGISTRY.get(name)


def canvas_item_type_name(cls: type) -> str | None:
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
    from lks_utils.gui_qt.canvas2d.overlays.canvas_border_overlay import (
        CanvasBorderOverlay,
    )
    from lks_utils.gui_qt.canvas2d.overlays.axes_lines_overlay import (
        AxesLinesOverlay,
    )
    from lks_utils.gui_qt.canvas2d.overlays.coord_hud_overlay import (
        CoordHudOverlay,
    )
    from lks_utils.gui_qt.canvas2d.overlays.checkerboard_overlay import (
        CheckerboardOverlay,
    )
    from lks_utils.gui_qt.canvas2d.overlays.dot_grid_overlay import (
        DotGridOverlay,
    )
    from lks_utils.gui_qt.canvas2d.overlays.home_grid_overlay import (
        HomeGridOverlay,
    )
    from lks_utils.gui_qt.canvas2d.overlays.texture_canvas_overlay import (
        TextureCanvasOverlay,
    )
    from lks_utils.gui_qt.canvas2d.overlays.world_grid_overlay import (
        WorldGridOverlay,
    )
    register_canvas_item_type("canvas2d.overlays.dot_grid", DotGridOverlay)
    register_canvas_item_type("canvas2d.overlays.world_grid", WorldGridOverlay)
    register_canvas_item_type("canvas2d.overlays.axes_lines", AxesLinesOverlay)
    register_canvas_item_type("canvas2d.overlays.home_grid", HomeGridOverlay)
    register_canvas_item_type(
        "canvas2d.overlays.canvas_border", CanvasBorderOverlay
    )
    register_canvas_item_type("canvas2d.overlays.coord_hud", CoordHudOverlay)
    register_canvas_item_type("canvas2d.overlays.checkerboard", CheckerboardOverlay)
    register_canvas_item_type("canvas2d.overlays.texture_canvas", TextureCanvasOverlay)


_register_builtins()

__all__ = [
    "register_canvas_item_type",
    "get_canvas_item_type",
    "canvas_item_type_name",
]

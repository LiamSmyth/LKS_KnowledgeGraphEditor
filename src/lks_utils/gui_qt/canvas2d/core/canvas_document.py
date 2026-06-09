"""`CanvasDocument`: frozen snapshot of a `Canvas2D` state for persistence.

A ``CanvasDocument`` is a plain-Python frozen dataclass capturing
the essential state of a canvas — view, objects, overlays, bookmarks,
and optional metadata — for save/load round-trips via JSON.

Production usage::

    doc = canvas.to_document()
    canvas.save_json(path)
    canvas.load_json(path)

Only objects/overlays that implement :meth:`~CanvasObject.to_dict` with a
non-``None`` return are included in the snapshot; everything else is
skipped silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CanvasDocument:
    """Frozen snapshot of a `Canvas2D` state.

    Attributes:
        version:   Schema version (always ``1`` for now).
        view:      The :class:`~lks_utils.gui_qt.canvas2d.core.view_transform.ViewTransform`
                   at the time of saving, serialised as a plain dict with
                   keys ``center_x``, ``center_y``, ``zoom``, ``rotation_radians``.
        objects:   Serialised regular canvas objects (non-overlay).
        overlays:  Serialised overlay objects.
        bookmarks: Dict mapping bookmark name → view dict (same schema as
                   ``view``).
        metadata:  Arbitrary caller-supplied key-value data.
    """

    version: int = 1
    view: dict[str, Any] = field(default_factory=dict)
    objects: list[dict[str, Any]] = field(default_factory=list)
    overlays: list[dict[str, Any]] = field(default_factory=list)
    bookmarks: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Serialisation helpers                                                #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serialisable dict."""
        return {
            "version": self.version,
            "view": dict(self.view),
            "objects": list(self.objects),
            "overlays": list(self.overlays),
            "bookmarks": {k: dict(v) for k, v in self.bookmarks.items()},
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CanvasDocument:
        """Construct a ``CanvasDocument`` from a plain dict."""
        return CanvasDocument(
            version=int(data.get("version", 1)),
            view=dict(data.get("view", {})),
            objects=list(data.get("objects", data.get("items", []))),
            overlays=list(data.get("overlays", [])),
            bookmarks={
                k: dict(v)
                for k, v in data.get("bookmarks", {}).items()
            },
            metadata=dict(data.get("metadata", {})),
        )


def _view_to_dict(view) -> dict[str, Any]:  # noqa: ANN001
    """Serialise a :class:`~ViewTransform` to a plain dict."""
    return {
        "center_x": view.center_world[0],
        "center_y": view.center_world[1],
        "zoom": view.zoom,
        "rotation_radians": view.rotation_radians,
    }


def _view_from_dict(data: dict[str, Any]):  # noqa: ANN202
    """Reconstruct a :class:`~ViewTransform` from a plain dict."""
    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform

    return ViewTransform(
        center_world=(
            float(data.get("center_x", 0.0)),
            float(data.get("center_y", 0.0)),
        ),
        zoom=float(data.get("zoom", 1.0)),
        rotation_radians=float(data.get("rotation_radians", 0.0)),
    )


__all__ = ["CanvasDocument", "_view_to_dict", "_view_from_dict"]

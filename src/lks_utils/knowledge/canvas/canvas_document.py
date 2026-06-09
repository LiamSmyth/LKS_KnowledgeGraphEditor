"""Knowledge canvas document schema helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lks_utils.gui_qt.canvas2d.canvas_object_registry import get_canvas_object_type


@dataclass(frozen=True)
class CanvasDocument:
    """Serializable knowledge-canvas document payload."""

    version: int = 1
    objects: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    overlays: list[dict[str, Any]] = field(default_factory=list)
    bookmarks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping for this document."""
        return {
            "version": self.version,
            "objects": [dict(obj) for obj in self.objects],
            "metadata": dict(self.metadata),
            "overlays": [dict(overlay) for overlay in self.overlays],
            "bookmarks": [dict(bookmark) for bookmark in self.bookmarks],
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> CanvasDocument:
        """Build a document from a mapping with graceful defaults."""
        return CanvasDocument(
            version=int(payload.get("version", 1)),
            objects=[
                dict(obj)
                for obj in payload.get("objects", payload.get("items", []))
            ],
            metadata=dict(payload.get("metadata", {})),
            overlays=[dict(overlay)
                      for overlay in payload.get("overlays", [])],
            bookmarks=[dict(bookmark)
                       for bookmark in payload.get("bookmarks", [])],
        )


def load_canvas_document(payload: dict[str, Any] | str | Path) -> CanvasDocument:
    """Load a ``CanvasDocument`` from a mapping or ``.kbview.json`` path."""
    if isinstance(payload, dict):
        return _from_payload(payload)

    path = Path(payload)
    if not path.exists():
        return CanvasDocument()

    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        return CanvasDocument()
    return _from_payload(raw_payload)


def save_canvas_document(document: CanvasDocument, path: str | Path) -> None:
    """Atomically save a ``CanvasDocument`` to ``path`` via temp-file swap."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = output_path.with_name(f"{output_path.name}.tmp")
    temp_path.write_text(
        json.dumps(document.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(output_path)


def _from_payload(payload: dict[str, Any]) -> CanvasDocument:
    document = CanvasDocument.from_dict(payload)
    normalized_objects: list[dict[str, Any]] = []
    for object_payload in document.objects:
        if not isinstance(object_payload, dict):
            continue

        object_type = object_payload.get("type")
        if not isinstance(object_type, str):
            normalized_objects.append(dict(object_payload))
            continue

        object_cls = get_canvas_object_type(object_type)
        if object_cls is None or not hasattr(object_cls, "from_dict"):
            normalized_objects.append(dict(object_payload))
            continue

        object_obj = object_cls.from_dict(object_payload)
        object_dict = object_obj.to_dict() if hasattr(object_obj, "to_dict") else None
        if isinstance(object_dict, dict):
            normalized_objects.append(object_dict)
        else:
            normalized_objects.append(dict(object_payload))

    return CanvasDocument(
        version=document.version,
        objects=normalized_objects,
        metadata=dict(document.metadata),
        overlays=list(document.overlays),
        bookmarks=list(document.bookmarks),
    )


__all__ = ["CanvasDocument", "load_canvas_document", "save_canvas_document"]

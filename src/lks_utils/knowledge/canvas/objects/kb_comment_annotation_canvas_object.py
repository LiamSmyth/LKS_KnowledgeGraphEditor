"""Canvas-only comment annotation item."""
from __future__ import annotations

from typing import Any

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.canvas_object_registry import register_canvas_object_type
from lks_utils.spatial.aabb import AABB


@register_canvas_object_type("knowledge.annotation_comment")
class KBCommentAnnotationCanvasObject(CanvasObject):
    """Persisted text comment annotation for knowledge canvases."""

    ITEM_TYPE: str = "knowledge.annotation_comment"

    def __init__(
        self,
        *,
        annotation_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        text: str,
    ) -> None:
        super().__init__()
        self.annotation_id: str = annotation_id
        self.x: float = float(x)
        self.y: float = float(y)
        self.width: float = float(width)
        self.height: float = float(height)
        self.text: str = text

    def bounds(self) -> AABB:
        """Return world-space annotation bounds."""
        return AABB(self.x, self.y, self.x + self.width, self.y + self.height)

    def paint(self, ctx) -> None:  # noqa: ANN001
        """No-op paint; UI layer decides annotation rendering."""
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize annotation comment to mapping data."""
        return {
            "type": self.ITEM_TYPE,
            "annotation_id": self.annotation_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> KBCommentAnnotationCanvasObject:
        """Deserialize annotation comment from mapping data."""
        width_value = payload.get("width", payload.get("w", 0.0))
        height_value = payload.get("height", payload.get("h", 0.0))
        return cls(
            annotation_id=str(payload["annotation_id"]),
            x=float(payload.get("x", 0.0)),
            y=float(payload.get("y", 0.0)),
            width=float(width_value),
            height=float(height_value),
            text=str(payload.get("text", "")),
        )


__all__ = ["KBCommentAnnotationCanvasObject"]

"""Canvas-only rectangular annotation item."""
from __future__ import annotations

from typing import Any

from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.gui_qt.canvas2d.canvas_item_registry import register_canvas_item_type
from lks_utils.spatial.aabb import AABB


@register_canvas_item_type("knowledge.annotation_rect")
class KBRectAnnotationCanvasItem(CanvasItem):
    """Persisted rectangular annotation region for knowledge canvases."""

    ITEM_TYPE: str = "knowledge.annotation_rect"

    def __init__(
        self,
        *,
        annotation_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        label: str | None = None,
        style: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.annotation_id: str = annotation_id
        self.x: float = float(x)
        self.y: float = float(y)
        self.width: float = float(width)
        self.height: float = float(height)
        self.label: str | None = label
        self.style: dict[str, Any] = dict(style or {})

    def bounds(self) -> AABB:
        """Return world-space annotation rectangle bounds."""
        return AABB(self.x, self.y, self.x + self.width, self.y + self.height)

    def paint(self, ctx) -> None:  # noqa: ANN001
        """No-op paint; UI layer decides annotation rendering."""
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize annotation rectangle to mapping data."""
        payload: dict[str, Any] = {
            "type": self.ITEM_TYPE,
            "annotation_id": self.annotation_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }
        if self.label is not None:
            payload["label"] = self.label
        if self.style:
            payload["style"] = dict(self.style)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> KBRectAnnotationCanvasItem:
        """Deserialize annotation rectangle from mapping data."""
        width_value = payload.get("width", payload.get("w", 0.0))
        height_value = payload.get("height", payload.get("h", 0.0))
        return cls(
            annotation_id=str(payload["annotation_id"]),
            x=float(payload.get("x", 0.0)),
            y=float(payload.get("y", 0.0)),
            width=float(width_value),
            height=float(height_value),
            label=payload.get("label"),
            style=dict(payload.get("style", {})),
        )


__all__ = ["KBRectAnnotationCanvasItem"]

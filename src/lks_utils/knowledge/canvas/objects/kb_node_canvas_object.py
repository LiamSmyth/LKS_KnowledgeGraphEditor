"""Canvas object representing a positioned knowledge-base node reference."""
from __future__ import annotations

from typing import Any

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.canvas_object_registry import register_canvas_object_type
from lks_utils.spatial.aabb import AABB


@register_canvas_object_type("knowledge.kb_node")
class KBNodeCanvasObject(CanvasObject):
    """Persisted visual placement for a KB node reference on a canvas."""

    ITEM_TYPE: str = "knowledge.kb_node"

    def __init__(
        self,
        *,
        node_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        style: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.node_id: str = node_id
        self.x: float = float(x)
        self.y: float = float(y)
        self.width: float = float(width)
        self.height: float = float(height)
        self.style: dict[str, Any] = dict(style or {})

    def bounds(self) -> AABB:
        """Return the world-space rectangular bounds for this node placement."""
        return AABB(self.x, self.y, self.x + self.width, self.y + self.height)

    def paint(self, ctx) -> None:  # noqa: ANN001
        """No-op paint; concrete visual rendering is provided by UI-specific layers."""
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this node object to the canvas objects-list shape."""
        payload: dict[str, Any] = {
            "type": self.ITEM_TYPE,
            "node_id": self.node_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }
        if self.style:
            payload["style"] = dict(self.style)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> KBNodeCanvasObject:
        """Deserialize a ``KBNodeCanvasObject`` from a plain mapping."""
        width_value = payload.get("width", payload.get("w", 240.0))
        height_value = payload.get("height", payload.get("h", 80.0))
        return cls(
            node_id=str(payload["node_id"]),
            x=float(payload.get("x", 0.0)),
            y=float(payload.get("y", 0.0)),
            width=float(width_value),
            height=float(height_value),
            style=dict(payload.get("style", {})),
        )


__all__ = ["KBNodeCanvasObject"]

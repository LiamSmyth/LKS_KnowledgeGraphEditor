"""Canvas object representing a link between two KB nodes."""
from __future__ import annotations

from typing import Any

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.canvas_object_registry import register_canvas_object_type


@register_canvas_object_type("knowledge.kb_edge")
class KBEdgeCanvasObject(CanvasObject):
    """Persisted visual edge metadata for a KB link reference."""

    ITEM_TYPE: str = "knowledge.kb_edge"

    def __init__(
        self,
        *,
        link_id: str,
        from_node_id: str,
        to_node_id: str,
        style: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.link_id: str = link_id
        self.from_node_id: str = from_node_id
        self.to_node_id: str = to_node_id
        self.style: dict[str, Any] = dict(style or {})

    def paint(self, ctx) -> None:  # noqa: ANN001
        """No-op paint; rendering is provided by UI-specific canvas layers."""
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this edge object for canvas persistence."""
        payload: dict[str, Any] = {
            "type": self.ITEM_TYPE,
            "link_id": self.link_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
        }
        if self.style:
            payload["style"] = dict(self.style)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> KBEdgeCanvasObject:
        """Deserialize a ``KBEdgeCanvasObject`` from mapping data."""
        return cls(
            link_id=str(payload["link_id"]),
            from_node_id=str(payload["from_node_id"]),
            to_node_id=str(payload["to_node_id"]),
            style=dict(payload.get("style", {})),
        )


__all__ = ["KBEdgeCanvasObject"]

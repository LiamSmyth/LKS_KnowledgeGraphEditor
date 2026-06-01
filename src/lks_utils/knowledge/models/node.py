"""Primary knowledge node model — EAV/ULID-based identity primitive."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from lks_utils.knowledge.models.node_id import NodeId


class Node(BaseModel):
    """The single identity primitive for the knowledge kernel.

    Every persisted concept — both instances and types — is a Node.
    Type nodes use ``category == "_type"`` and store slot definitions in
    ``props["slots"]``. Instance nodes reference a type via ``type_id``.
    """

    id: NodeId = Field(default_factory=NodeId.new)
    category: str = ""
    type_id: NodeId | None = None
    name: str = Field(min_length=1)
    description: str = ""
    props: dict[str, object] = Field(default_factory=dict)
    display_color: str | None = None
    rev: int = 0
    source_repo_id: str = ""

    model_config = {
        "extra": "forbid",
        "arbitrary_types_allowed": True,
    }

    @field_validator("display_color")
    @classmethod
    def _validate_display_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if len(text) != 7 or not text.startswith("#"):
            raise ValueError("Node.display_color must be #RRGGBB")
        int(text[1:], 16)
        return text.lower()

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    # type: ignore[override]
    def model_dump(self, **kwargs: object) -> dict[str, object]:
        """Return a JSON-serialisable dict with NodeId as strings."""
        data = super().model_dump(**kwargs)
        data["id"] = str(self.id)
        data["type_id"] = str(
            self.type_id) if self.type_id is not None else None
        return data

    @classmethod
    def model_validate(cls, obj: object, **kwargs: object) -> Node:
        """Accept raw dicts with string 'id'/'type_id' fields.

        Also accepts legacy ``'kind'`` key in place of ``'category'`` to support
        loading JSON files written before the rename.
        """
        if isinstance(obj, dict):
            obj = dict(obj)
            if "id" in obj and isinstance(obj["id"], str):
                obj["id"] = NodeId.from_str(obj["id"])
            if "type_id" in obj and isinstance(obj["type_id"], str) and obj["type_id"]:
                obj["type_id"] = NodeId.from_str(obj["type_id"])
            # Backward-compat: old JSON files used 'kind'; remap to 'category'
            if "kind" in obj and "category" not in obj:
                obj["category"] = obj.pop("kind")
        return super().model_validate(obj, **kwargs)

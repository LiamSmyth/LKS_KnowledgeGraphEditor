"""Pydantic model for atomic semantic link edge records."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator
from ulid import ULID

from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID


class LinkInstance(BaseModel):
    """One directed semantic edge between two knowledge nodes."""

    id: str = Field(default_factory=lambda: str(ULID()))
    link_type_id: str
    source_node_id: str
    target_node_id: str
    metadata: dict[str, object] = Field(default_factory=dict)
    display_color: str | None = None
    source_slot_name: str | None = None

    @field_validator("display_color")
    @classmethod
    def _validate_display_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if len(text) != 7 or not text.startswith("#"):
            raise ValueError("LinkInstance.display_color must be #RRGGBB")
        int(text[1:], 16)
        return text.lower()

    @field_validator("source_slot_name")
    @classmethod
    def _validate_source_slot_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("LinkInstance.source_slot_name must be non-empty when set")
        return stripped

    model_config = {
        "extra": "forbid",
    }

    @field_validator("id", "source_node_id", "target_node_id")
    @classmethod
    def _validate_ulid(cls, value: str) -> str:
        if len(value) != 26:
            raise ValueError("LinkInstance ids must be 26-char ULID strings")
        ULID.from_str(value)
        return value

    @field_validator("link_type_id")
    @classmethod
    def _validate_link_type_id(cls, value: str) -> str:
        if value == SLOT_REF_LINK_TYPE_ID:
            return value
        if len(value) != 26:
            raise ValueError(
                "LinkInstance link_type_id must be ULID or 'slot_ref'")
        ULID.from_str(value)
        return value

    @model_validator(mode="after")
    def _validate_slot_name_symmetry(self) -> LinkInstance:
        is_slot_ref = self.link_type_id == SLOT_REF_LINK_TYPE_ID
        has_slot_name = self.source_slot_name is not None
        if is_slot_ref and not has_slot_name:
            raise ValueError(
                "slot_ref LinkInstance must have source_slot_name set")
        if not is_slot_ref and has_slot_name:
            raise ValueError(
                "Only slot_ref LinkInstances may carry source_slot_name")
        return self


__all__ = ["LinkInstance"]

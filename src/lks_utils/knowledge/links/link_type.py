"""Pydantic model for semantic link-type vocabulary entries."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from ulid import ULID

SLOT_REF_LINK_TYPE_ID = "slot_ref"


class LinkType(BaseModel):
    """Predicate vocabulary row used by link instances."""

    id: str = Field(default_factory=lambda: str(ULID()))
    name: str = Field(min_length=1)
    inverse_name: str = ""
    description: str = ""
    source_type_constraint: str | None = None
    target_type_constraint: str | None = None
    cardinality: Literal["one", "many"] = "many"
    is_system: bool = False
    display_color: str | None = None

    model_config = {
        "extra": "forbid",
    }

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if value == SLOT_REF_LINK_TYPE_ID:
            return value
        if len(value) != 26:
            raise ValueError("LinkType.id must be a 26-char ULID string")
        ULID.from_str(value)
        return value

    @field_validator("display_color")
    @classmethod
    def _validate_display_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if len(text) != 7 or not text.startswith("#"):
            raise ValueError("LinkType.display_color must be #RRGGBB")
        int(text[1:], 16)
        return text.lower()


__all__ = ["LinkType", "SLOT_REF_LINK_TYPE_ID"]

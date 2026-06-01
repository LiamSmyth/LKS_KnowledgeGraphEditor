"""Typed issue model for knowledge graph integrity diagnostics."""
from __future__ import annotations

from pydantic import BaseModel, Field


class IntegrityIssue(BaseModel):
    """One deterministic integrity violation record."""

    code: str = Field(min_length=1)
    link_id: str | None = None
    link_type_id: str | None = None
    source_node_id: str | None = None
    target_node_id: str | None = None
    detail: str = ""

    model_config = {
        "extra": "forbid",
    }


__all__ = ["IntegrityIssue"]

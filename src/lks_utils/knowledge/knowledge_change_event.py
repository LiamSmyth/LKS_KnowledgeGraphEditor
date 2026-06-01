"""Typed change-event model for KnowledgeIO mutation notifications."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


KnowledgeChangeEventType = Literal[
    "node_upserted",
    "node_deleted",
    "link_upserted",
    "link_deleted",
    "link_type_upserted",
]


@dataclass(frozen=True)
class KnowledgeChangeEvent:
    """Event payload emitted after a successful knowledge mutation."""

    event_type: KnowledgeChangeEventType
    entity_id: str
    entity_type: str
    bundle_id: str | None
    timestamp: float
    violations: list[object] = field(default_factory=list)

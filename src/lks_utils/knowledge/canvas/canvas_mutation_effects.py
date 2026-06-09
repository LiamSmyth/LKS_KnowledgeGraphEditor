"""Canvas mutation effects returned by CanvasIO view mutates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CanvasMutationEffects:
    """Rich return payload describing one successful canvas/view mutation."""

    persisted: bool
    event_type: str
    entity_id: str
    touched_object_ids: frozenset[str]
    journal_record: dict[str, Any] | None = None


__all__ = ["CanvasMutationEffects"]

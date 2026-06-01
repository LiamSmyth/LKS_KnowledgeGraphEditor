"""One blast-radius impact entry for confirmation dialogs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImpactEntry:
    """Describes one affected object in a blast-radius preview."""

    object_id: str
    object_kind: str
    reason: str


__all__ = ["ImpactEntry"]

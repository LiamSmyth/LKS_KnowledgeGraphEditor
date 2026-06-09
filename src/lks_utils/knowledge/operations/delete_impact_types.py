"""Shared delete-impact data types."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IncomingRef:
    """One inbound reference from a source node to a delete target."""

    source_node_id: str
    source_slot_path: tuple[str, ...]
    target_node_id: str
    is_resolved: bool


@dataclass(frozen=True, slots=True)
class DeleteImpact:
    """Delete-target set plus inbound refs from outside that set."""

    targets: tuple[str, ...]
    incoming_refs: tuple[IncomingRef, ...]

    @property
    def is_safe(self) -> bool:
        """Return whether deleting the targets would strand no external refs."""
        return not self.incoming_refs


__all__ = ["DeleteImpact", "IncomingRef"]

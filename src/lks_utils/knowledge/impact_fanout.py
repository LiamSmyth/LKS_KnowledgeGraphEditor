"""Ephemeral delete-impact fanout structs (never persisted)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lks_utils.knowledge.operations.delete_impact_types import IncomingRef

UxTier = Literal["silent", "dialog", "blocked"]


@dataclass(frozen=True, slots=True)
class ImpactFanout:
    """Read-only blast radius for one delete gesture."""

    targets: tuple[str, ...]
    incoming_system_refs: tuple[IncomingRef, ...]
    cascade_link_ids: tuple[str, ...]
    cascade_instance_ids: tuple[str, ...]
    validation_fanout_ids: frozenset[str]
    validation_mode: str
    integrity_link_delta: tuple[str, ...]
    affected_view_paths: tuple[str, ...]
    ux_tier: UxTier

    @property
    def is_silent(self) -> bool:
        return self.ux_tier == "silent"


__all__ = ["ImpactFanout", "UxTier"]

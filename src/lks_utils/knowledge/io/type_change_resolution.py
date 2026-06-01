"""Resolution dataclasses for type-slot mutation operations.

These are pure-Python data types used by ``KnowledgeIO.preview_change_type_slots``
and ``KnowledgeIO.change_slot_value_type``.  No Qt imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class TypeSlotChange:
    """One proposed slot mutation on a type node."""

    slot_name: str
    change_kind: Literal["add", "remove", "change_value_type"]
    # populated when change_kind == "change_value_type"
    new_value_type: str | None = None


@dataclass(frozen=True, slots=True)
class TypeSlotChanges:
    """Collection of proposed slot changes for a single type node."""

    type_id: str
    changes: tuple[TypeSlotChange, ...]


@dataclass(frozen=True, slots=True)
class AffectedInstanceInfo:
    """One instance that would be affected by a type-slot change."""

    instance_id: str
    instance_name: str
    slot_name: str
    current_value_summary: str


@dataclass(frozen=True, slots=True)
class TypeSlotChangeImpact:
    """Read-only impact summary for a proposed type-slot change.

    Returned by ``KnowledgeIO.preview_change_type_slots``.
    Pass back to ``KnowledgeIO.change_slot_value_type`` as *resolution*
    to confirm the caller has reviewed the impact.
    """

    type_id: str
    affected_instances: tuple[AffectedInstanceInfo, ...]

    @property
    def is_safe(self) -> bool:
        """Return True when no instances would lose valid data."""
        return not self.affected_instances


SlotResolutionMode = Literal["coerce", "clear", "leave"]


@dataclass(frozen=True, slots=True)
class TypeChangeResolutionEntry:
    """One resolution choice for one affected instance."""

    instance_id: str
    slot_name: str
    mode: SlotResolutionMode


@dataclass(frozen=True, slots=True)
class TypeChangeResolution:
    """Structured resolution covering all affected instances for a type-slot change.

    Passed to ``KnowledgeIO.change_slot_value_type``.
    When *entries* is empty the change is assumed safe (no instances affected).
    """

    entries: tuple[TypeChangeResolutionEntry, ...] = field(
        default_factory=tuple)

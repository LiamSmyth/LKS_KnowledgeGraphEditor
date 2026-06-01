"""Resolution dataclasses for destructive knowledge operations.

These are pure-Python data types shared between the KnowledgeIO layer,
MCP tools, and the UI dialog layer.  No Qt imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lks_utils.knowledge.operations.delete_safety_analyzer import IncomingRef


DeleteResolutionMode = Literal["leave_dangling", "remove_ref", "replace"]


@dataclass(frozen=True, slots=True)
class DeleteResolutionEntry:
    """One resolution choice for one inbound reference row."""

    incoming_ref: IncomingRef
    mode: DeleteResolutionMode
    replacement_id: str | None = None


@dataclass(frozen=True, slots=True)
class DeleteResolution:
    """Structured resolution covering all incoming references for a delete op.

    Passed to :meth:`KnowledgeIO.delete_nodes` (and ``delete_node``).
    When *entries* is empty the deletion is assumed to be safe (no refs).
    """

    entries: tuple[DeleteResolutionEntry, ...]

    @property
    def can_delete_safely(self) -> bool:
        """Return True when no entry leaves a dangling reference."""
        return all(entry.mode != "leave_dangling" for entry in self.entries)

"""Result types for KnowledgeIO operations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValidationMode(str, Enum):
    """Controls how far post-mutation validation recompute spreads."""

    TOUCHED = "touched_only"
    EXPANDED = "expanded"


@dataclass(frozen=True)
class ValidationIssue:
    """One validation problem attached to a specific knowledge object."""

    object_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OperationResult:
    """Unified result from one KnowledgeIO operation.

    *status* is one of ``"ok"``, ``"blocked"`` (destructive op has incoming
    refs that require resolution), or ``"error"`` (unexpected failure).

    *touched_ids* covers every object whose on-disk file was written plus every
    object whose validation status changed during the recompute.

    *validated_ids* is the subset of *touched_ids* that was included in the
    post-mutation validation pass.

    *issues* holds any validation problems discovered for *validated_ids*.
    Empty when *validation_index* was not injected.

    *blocking_impact* is set when *status == "blocked"*; callers may inspect it
    to show a preview or build a two-phase resolution flow.
    """

    status: str
    touched_ids: frozenset[str]
    validated_ids: frozenset[str]
    issues: tuple[ValidationIssue, ...]
    blocking_impact: Any = None
    save_error: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        """Return True when the operation succeeded without blocking."""
        return self.status == "ok"


__all__ = ["OperationResult", "ValidationIssue", "ValidationMode"]

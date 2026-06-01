"""Revert impact summary for knowledge version-control operations."""
from __future__ import annotations

from dataclasses import dataclass, field

from lks_utils.knowledge.impact_entry import ImpactEntry


@dataclass(frozen=True)
class RevertImpactReport:
    """Describe direct and related repository objects affected by a revert."""

    entries: list[ImpactEntry] = field(default_factory=list)
    related_files: set[str] = field(default_factory=set)
    include_related: bool = False

    def is_empty(self) -> bool:
        """Return True when no impacts or related files are present."""
        return not self.entries and not self.related_files


__all__ = ["RevertImpactReport"]

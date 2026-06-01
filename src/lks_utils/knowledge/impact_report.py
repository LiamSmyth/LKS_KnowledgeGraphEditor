"""Impact report payload for side-effect-free blast-radius previews."""
from __future__ import annotations

from dataclasses import dataclass, field

from lks_utils.knowledge.impact_entry import ImpactEntry


@dataclass(frozen=True, slots=True)
class ImpactReport:
    """Collection of impacted objects for one potential operation."""

    entries: list[ImpactEntry] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Return True when there are no impacts to display."""
        return len(self.entries) == 0


__all__ = ["ImpactReport"]

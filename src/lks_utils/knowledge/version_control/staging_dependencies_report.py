"""Dependencies staging preview result for knowledge version-control operations."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StagingDependenciesReport:
    """Describe dependencies to stage for knowledge version-control operations.

    When staging items, this report identifies related changed files that are
    dependencies (forward-link references) of the staged items, so the user can
    optionally stage them together to avoid broken references.
    """

    # Map from changed dependency path -> (object_id, reason)
    # The dependency path may already be staged, changed+unstaged, or untracked
    candidates: dict[str, tuple[str, str]] = field(default_factory=dict)
    # Subset of candidates that are NOT already staged
    unstaged_candidates: dict[str, tuple[str, str]
                              ] = field(default_factory=dict)

    def is_empty(self) -> bool:
        """Return True when no unstaged candidates are present."""
        return not self.unstaged_candidates


__all__ = ["StagingDependenciesReport"]

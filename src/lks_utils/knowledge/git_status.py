"""Structured git status payload for knowledge repositories."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class GitStatus:
    """Normalized git working tree status grouped by category."""

    modified_paths: set[str]
    staged_paths: set[str]
    unstaged_paths: set[str]
    untracked_paths: set[str]
    deleted_paths: set[str]
    # Raw pygit2 flag map keyed by repo-relative path (forward slashes).
    # Populated by status() and the background refresh; used by change_code()
    # to avoid per-file calls to repo.status().
    status_flags: dict[str, int] = dataclasses.field(default_factory=dict)

    @property
    def all_modified_paths(self) -> set[str]:
        """Return union of all path groups representing non-clean state."""
        return (
            set(self.modified_paths)
            | set(self.staged_paths)
            | set(self.unstaged_paths)
            | set(self.untracked_paths)
            | set(self.deleted_paths)
        )


__all__ = ["GitStatus"]

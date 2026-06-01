"""Structured commit metadata for git history display."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommitInfo:
    """Compact commit record used by knowledge git UI surfaces."""

    sha: str
    message: str
    author_name: str
    author_email: str
    commit_time: int


__all__ = ["CommitInfo"]

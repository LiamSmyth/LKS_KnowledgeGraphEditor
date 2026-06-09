"""Projection-layer validation issues for canvas placements."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectionIssue:
    """One orphan or stale graph projection finding."""

    object_id: str
    code: str
    detail: str


__all__ = ["ProjectionIssue"]

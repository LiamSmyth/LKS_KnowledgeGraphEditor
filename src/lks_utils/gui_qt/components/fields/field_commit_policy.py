"""Configurable commit policy for field widgets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldCommitPolicy:
    """Defines optional auto-commit triggers for a field."""

    commit_on_changed: bool = False
    commit_on_focus_out: bool = False

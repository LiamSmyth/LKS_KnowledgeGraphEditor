"""Commit reason identifiers for field widgets."""

from __future__ import annotations

from enum import Enum


class FieldCommitReason(str, Enum):
    """Reason describing why a field commit was requested."""

    CONFIRM = "confirm"
    REVERT = "revert"
    CHANGED = "changed"
    FOCUS_OUT = "focus_out"

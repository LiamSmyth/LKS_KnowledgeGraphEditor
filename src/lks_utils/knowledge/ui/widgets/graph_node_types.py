"""Shared graph node model types."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphNodeFieldRow:
    """Display row for the node body primitive."""

    label: str
    value_type: str
    value: str
    value_kind: str = "plain"


@dataclass(frozen=True, slots=True)
class GraphNodeValidationSummary:
    """Compiled validation summary for a graph node badge and tooltip."""

    warning_count: int = 0
    error_count: int = 0
    tooltip_text: str = ""


__all__ = ["GraphNodeFieldRow", "GraphNodeValidationSummary"]

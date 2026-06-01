"""Helper functions for decomposition canvas card sizing."""
from __future__ import annotations

from lks_utils.knowledge.ui.components.field_row_factory import FieldRow


def visible_collapsed_row_count(rows: list[FieldRow]) -> int:
    return len(rows)


def card_height(rows: list[FieldRow], row_height: float = 22.0) -> float:
    """Return a compact card height tuned for pixmap-backed QWidget cards."""
    # Reconstructed QWidget cards need extra base space for:
    # - header ribbon
    # - frame border/padding
    # - property panel chrome
    return max(96.0, 64.0 + visible_collapsed_row_count(rows) * row_height)


__all__ = ["visible_collapsed_row_count", "card_height"]

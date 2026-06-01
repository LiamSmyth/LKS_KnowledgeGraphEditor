"""Knowledge mutation operations."""
from __future__ import annotations

from lks_utils.knowledge.operations.delete_safety_analyzer import (
    DeleteImpact,
    IncomingRef,
    analyze_delete_impact,
)
from lks_utils.knowledge.operations.promote_inline_literal import promote_inline_literal

__all__ = [
    "DeleteImpact",
    "IncomingRef",
    "analyze_delete_impact",
    "promote_inline_literal",
]
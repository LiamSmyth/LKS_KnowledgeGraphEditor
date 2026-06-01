"""Knowledge IO facade - pure-Python write path for knowledge repositories."""
from __future__ import annotations

from lks_utils.knowledge.io.delete_resolution import (
    DeleteResolution,
    DeleteResolutionEntry,
    DeleteResolutionMode,
)
from lks_utils.knowledge.io.knowledge_io import KnowledgeIO
from lks_utils.knowledge.knowledge_change_listener import KnowledgeChangeListener
from lks_utils.knowledge.io.link_impact import LinkDeleteImpact, LinkTypeDeleteImpact
from lks_utils.knowledge.io.operation_result import (
    OperationResult,
    ValidationIssue,
    ValidationMode,
)
from lks_utils.knowledge.io.type_change_resolution import (
    TypeChangeResolution,
    TypeChangeResolutionEntry,
    TypeSlotChange,
    TypeSlotChangeImpact,
    TypeSlotChanges,
)

__all__ = [
    "KnowledgeIO",
    "KnowledgeChangeListener",
    "OperationResult",
    "ValidationIssue",
    "ValidationMode",
    "DeleteResolution",
    "DeleteResolutionEntry",
    "DeleteResolutionMode",
    "LinkDeleteImpact",
    "LinkTypeDeleteImpact",
    "TypeChangeResolution",
    "TypeChangeResolutionEntry",
    "TypeSlotChange",
    "TypeSlotChangeImpact",
    "TypeSlotChanges",
]

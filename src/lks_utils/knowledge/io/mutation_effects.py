"""Mutation effects and kind hints for KnowledgeIO write operations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from lks_utils.knowledge.knowledge_change_event import KnowledgeChangeEvent


class MutationKind(str, Enum):
    """Drives blast-radius policy for KB mutations."""

    INSTANCE_PROPERTY = "instance_property"
    INSTANCE_PROPERTY_REF = "instance_property_ref"
    NODE_UPSERT = "node_upsert"
    NODE_DELETE = "node_delete"
    LINK_STRUCTURE = "link_structure"
    TYPE_SCHEMA = "type_schema"
    GRAPH_VIEW = "graph_view"


@dataclass(frozen=True)
class JournalContext:
    """Metadata for the single journal record appended per successful mutate."""

    event_type: str
    entity_id: str
    entity_type: str
    bundle_id: str | None = None


@dataclass(frozen=True)
class MutationEffects:
    """Rich return payload describing one successful KB mutation."""

    directly_changed: frozenset[str]
    persisted: bool
    validated_ids: frozenset[str]
    structural_change: bool
    mutation_kind: MutationKind
    journal_record: KnowledgeChangeEvent | None

    @property
    def touched(self) -> frozenset[str]:
        """Union of directly changed and validation-expanded IDs."""
        return self.directly_changed | self.validated_ids


__all__ = ["JournalContext", "MutationEffects", "MutationKind"]

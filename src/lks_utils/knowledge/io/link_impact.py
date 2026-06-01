"""Impact summary types for link and link-type delete operations.

These are pure-Python data types returned by ``KnowledgeIO.preview_delete_*``
methods.  No Qt imports.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LinkDeleteImpact:
    """Impact summary for deleting one or more link instances.

    Returned by ``KnowledgeIO.preview_delete_links``.
    This operation is always structurally safe (links are leaf objects),
    but callers may use the endpoint lists to confirm user intent.
    """

    link_ids: tuple[str, ...]
    affected_node_ids: tuple[str, ...]  # unique source/target node ids

    @property
    def is_safe(self) -> bool:
        """Return True — link deletion is always structurally safe."""
        return True


@dataclass(frozen=True, slots=True)
class LinkTypeDeleteImpact:
    """Impact summary for deleting a link-type definition.

    Returned by ``KnowledgeIO.preview_delete_link_type``.
    Deletion is blocked when there are live link instances of this type.
    """

    link_type_id: str
    link_type_name: str
    dependent_link_ids: tuple[str, ...]
    # unique source/target node ids across all deps
    affected_node_ids: tuple[str, ...]

    @property
    def is_safe(self) -> bool:
        """Return True only when no link instances reference this type."""
        return not self.dependent_link_ids

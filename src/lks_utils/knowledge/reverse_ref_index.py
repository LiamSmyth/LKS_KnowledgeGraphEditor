"""Reverse reference index for efficient impact expansion during validation."""
from __future__ import annotations

from collections import defaultdict

from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.repository import Repository


class ReverseRefIndex:
    """Tracks which objects (nodes/links) reference which other objects.

    Used to efficiently expand impacted ids during validation recompute:
    when object X changes, `referencers_of(X)` returns all ids that might be
    affected by the change, enabling O(refs) impact expansion instead of O(graph).

    Stores bidirectional references:
    - Node refs: type_id → set of node_ids whose type_id points to type_id
    - Link refs: link_type_id → set of link_ids that use that link_type_id
    - Link node refs: node_id → set of link_ids that source/target that node_id
    """

    def __init__(self) -> None:
        # Maps target object_id → set of referrers (node_ids or link_ids)
        self._referencers: dict[str, set[str]] = defaultdict(set)

    def referencers_of(self, object_id: str) -> set[str]:
        """Return all object_ids (nodes or links) that reference the given object_id.

        Empty set if the object is not referenced.
        """
        return set(self._referencers.get(object_id, set()))

    def rebuild_from(self, repository: Repository) -> None:
        """Rebuild the entire index from scratch by scanning all nodes and links."""
        self._referencers.clear()

        # Index node type references.
        for node in repository.list_nodes():
            node_id_str = str(node.id)
            if node.type_id is not None:
                type_id_str = str(node.type_id)
                self._referencers[type_id_str].add(node_id_str)

        # Index all link-to-node and link-to-linktype refs
        for link in repository.list_links():
            link_id_str = str(link.id)

            # Link type reference
            link_type_id_str = str(link.link_type_id)
            self._referencers[link_type_id_str].add(link_id_str)

            # Link node references
            source_node_id_str = str(link.source_node_id)
            self._referencers[source_node_id_str].add(link_id_str)

            target_node_id_str = str(link.target_node_id)
            self._referencers[target_node_id_str].add(link_id_str)

    def on_node_added(self, node: Node) -> None:
        """Update index when a node is added to the repository."""
        node_id_str = str(node.id)

        # Register type reference
        if node.type_id is not None:
            type_id_str = str(node.type_id)
            self._referencers[type_id_str].add(node_id_str)

    def on_node_removed(self, node_id: str) -> None:
        """Update index when a node is removed from the repository."""
        # Remove all entries for this node as a referrer
        for ref_set in self._referencers.values():
            ref_set.discard(node_id)

    def on_node_mutated(self, old_node: Node, new_node: Node) -> None:
        """Update index when a node is mutated (its refs may have changed)."""
        node_id_str = str(new_node.id)

        # Update type reference if it changed
        old_type_id = str(
            old_node.type_id) if old_node.type_id is not None else None
        new_type_id = str(
            new_node.type_id) if new_node.type_id is not None else None

        if old_type_id != new_type_id:
            if old_type_id:
                self._referencers[old_type_id].discard(node_id_str)
            if new_type_id:
                self._referencers[new_type_id].add(node_id_str)

    def on_link_added(self, link: LinkInstance) -> None:
        """Update index when a link is added to the repository."""
        link_id_str = str(link.id)

        # Register link type reference
        link_type_id_str = str(link.link_type_id)
        self._referencers[link_type_id_str].add(link_id_str)

        # Register node references
        source_node_id_str = str(link.source_node_id)
        self._referencers[source_node_id_str].add(link_id_str)

        target_node_id_str = str(link.target_node_id)
        self._referencers[target_node_id_str].add(link_id_str)

    def on_link_removed(self, link_id: str) -> None:
        """Update index when a link is removed from the repository."""
        # Remove all entries for this link as a referrer
        for ref_set in self._referencers.values():
            ref_set.discard(link_id)

"""Index-backed adjacency lookups for O(incident) delete impact queries."""
from __future__ import annotations

from collections import defaultdict

from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.reverse_ref_index import ReverseRefIndex

_SYSTEM_INCOMING_TYPES = frozenset(
    {
        SLOT_REF_LINK_TYPE_ID,
        INSTANCE_OF_LINK_TYPE_ID,
        EXTENDS_LINK_TYPE_ID,
    }
)


class RepositoryIndexes(ReverseRefIndex):
    """Extended reverse-ref index for delete-plan queries.

    API surface (all O(incident) after ``rebuild_from``):

    * ``incoming_system_refs(target_id)`` — one-hop system referencers.
    * ``incident_link_ids(node_id)`` — links touching a node.
    * ``instances_by_type(type_id)`` — instance nodes via ``instance_of`` links.
    * ``types_extending(type_id)`` — child types via ``extends`` links.
    * ``links_of_type(link_type_id)`` — link ids using a link type.
    """

    def __init__(self) -> None:
        super().__init__()
        self._incoming_system: dict[str, list[LinkInstance]] = defaultdict(list)
        self._incident_links: dict[str, set[str]] = defaultdict(set)
        self._instances_by_type: dict[str, set[str]] = defaultdict(set)
        self._types_extending: dict[str, set[str]] = defaultdict(set)
        self._links_by_type: dict[str, set[str]] = defaultdict(set)
        self._link_by_id: dict[str, LinkInstance] = {}

    def incoming_system_refs(self, target_id: str) -> list[LinkInstance]:
        """Return system links whose target is *target_id*."""
        return list(self._incoming_system.get(target_id, ()))

    def incident_link_ids(self, node_id: str) -> set[str]:
        """Return link ids where *node_id* is source or target."""
        return set(self._incident_links.get(node_id, set()))

    def instances_by_type(self, type_id: str) -> set[str]:
        """Return instance node ids typed by *type_id* via ``instance_of`` links."""
        return set(self._instances_by_type.get(type_id, set()))

    def types_extending(self, type_id: str) -> set[str]:
        """Return child type node ids that extend *type_id* via ``extends`` links."""
        return set(self._types_extending.get(type_id, set()))

    def links_of_type(self, link_type_id: str) -> set[str]:
        """Return link ids using *link_type_id*."""
        return set(self._links_by_type.get(link_type_id, set()))

    def link_by_id(self, link_id: str) -> LinkInstance | None:
        return self._link_by_id.get(link_id)

    def rebuild_from(self, repository: Repository) -> None:
        super().rebuild_from(repository)
        self._incoming_system.clear()
        self._incident_links.clear()
        self._instances_by_type.clear()
        self._types_extending.clear()
        self._links_by_type.clear()
        self._link_by_id.clear()

        for link in repository.list_links():
            link_id = str(link.id)
            self._link_by_id[link_id] = link
            link_type_id = str(link.link_type_id)
            self._links_by_type[link_type_id].add(link_id)

            source_id = str(link.source_node_id)
            target_id = str(link.target_node_id)
            self._incident_links[source_id].add(link_id)
            self._incident_links[target_id].add(link_id)

            if link_type_id in _SYSTEM_INCOMING_TYPES:
                self._incoming_system[target_id].append(link)
            if link_type_id == INSTANCE_OF_LINK_TYPE_ID:
                self._instances_by_type[target_id].add(source_id)
            if link_type_id == EXTENDS_LINK_TYPE_ID:
                self._types_extending[target_id].add(source_id)

    def on_link_added(self, link: LinkInstance) -> None:
        super().on_link_added(link)
        link_id = str(link.id)
        self._link_by_id[link_id] = link
        link_type_id = str(link.link_type_id)
        self._links_by_type[link_type_id].add(link_id)
        source_id = str(link.source_node_id)
        target_id = str(link.target_node_id)
        self._incident_links[source_id].add(link_id)
        self._incident_links[target_id].add(link_id)
        if link_type_id in _SYSTEM_INCOMING_TYPES:
            self._incoming_system[target_id].append(link)
        if link_type_id == INSTANCE_OF_LINK_TYPE_ID:
            self._instances_by_type[target_id].add(source_id)
        if link_type_id == EXTENDS_LINK_TYPE_ID:
            self._types_extending[target_id].add(source_id)

    def on_link_removed(self, link_id: str) -> None:
        link = self._link_by_id.pop(link_id, None)
        super().on_link_removed(link_id)
        if link is None:
            return
        link_type_id = str(link.link_type_id)
        self._links_by_type[link_type_id].discard(link_id)
        source_id = str(link.source_node_id)
        target_id = str(link.target_node_id)
        self._incident_links[source_id].discard(link_id)
        self._incident_links[target_id].discard(link_id)
        if link_type_id in _SYSTEM_INCOMING_TYPES:
            bucket = self._incoming_system.get(target_id)
            if bucket is not None:
                self._incoming_system[target_id] = [
                    item for item in bucket if str(item.id) != link_id
                ]
        if link_type_id == INSTANCE_OF_LINK_TYPE_ID:
            self._instances_by_type[target_id].discard(source_id)
        if link_type_id == EXTENDS_LINK_TYPE_ID:
            self._types_extending[target_id].discard(source_id)

    def on_node_removed(self, node_id: str) -> None:
        super().on_node_removed(node_id)
        self._incident_links.pop(node_id, None)
        self._incoming_system.pop(node_id, None)
        for type_id in list(self._instances_by_type):
            self._instances_by_type[type_id].discard(node_id)
        for parent_id in list(self._types_extending):
            self._types_extending[parent_id].discard(node_id)


__all__ = ["RepositoryIndexes"]

"""Type-node and instance introspection helpers for the knowledge system layer."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.system.system_reserved import TYPE_NODE_CATEGORY


class _InstanceListingRepository(Protocol):
    """Protocol for repositories that can list instance nodes."""

    def list_instances(self) -> list[Node]:
        ...


def is_type_node(node: Node) -> bool:
    """Return True when *node* is a type node."""
    return node.category.strip().casefold() == TYPE_NODE_CATEGORY.casefold()


def categorize_node(node: Node) -> str:
    """Return a stable semantic bucket for a node."""
    return "type" if is_type_node(node) else "instance"


def iter_instances_of(repo: _InstanceListingRepository, type_id: str | NodeId) -> Iterator[Node]:
    """Yield instance nodes assigned to *type_id* in deterministic order."""
    target = str(type_id)
    for node in repo.list_instances():
        if node.type_id is not None and str(node.type_id) == target:
            yield node


__all__ = [
    "categorize_node",
    "is_type_node",
    "iter_instances_of",
]

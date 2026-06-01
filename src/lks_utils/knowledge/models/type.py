"""Helper functions for type-nodes (category == "_type")."""
from __future__ import annotations

from dataclasses import dataclass, field

from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_slot import NodeSlot

_TYPE_KIND = "_type"


@dataclass(frozen=True)
class TypeView:
    """A read-only view of a type-node's slot list."""

    node_id: NodeId
    name: str
    description: str
    category: str = ""
    slots: list[NodeSlot] = field(default_factory=list)

    @property
    def type_kind(self) -> str:
        """Backward-compatible alias for callers still expecting type_kind."""
        return self.category


def make_type(
    category: str | None = None,
    name: str = "",
    description: str = "",
    *,
    slots: list[NodeSlot] | None = None,
    source_repo_id: str = "",
    type_kind: str | None = None,
) -> Node:
    """Mint a new type-node.

    Args:
        category: Default instance category for nodes of this type (e.g. ``"term"``).
        name: Human-readable display label for this type (e.g. ``"Term"``).
        description: Non-empty description of what instances of this type represent.
        slots: Optional list of :class:`NodeSlot` definitions.
        source_repo_id: Optional repository identifier for multi-repo scenarios.

    Returns:
        A freshly minted :class:`Node` with ``kind == "_type"``.
    """
    if category is not None:
        resolved_category = str(category).strip()
    elif type_kind is not None:
        resolved_category = str(type_kind).strip()
    else:
        resolved_category = ""
    slots_payload = [s.model_dump() for s in (slots or [])]
    return Node(
        category=_TYPE_KIND,
        name=name,
        description=description,
        props={
            "instance_category": resolved_category,
            "type_kind": resolved_category,
            "slots": slots_payload,
        },
        source_repo_id=source_repo_id,
    )


def is_type(node: Node) -> bool:
    """Return True when *node* is a type-node (``category == "_type"``)."""
    return node.category == _TYPE_KIND


def as_type(node: Node) -> TypeView:
    """Return a typed read-only view of a type-node's slot list.

    Raises:
        ValueError: If *node* is not a type-node.
    """
    if not is_type(node):
        raise ValueError(
            f"Node {node.id} has category {node.category!r}, not '_type'")
    raw_slots = node.props.get("slots", [])
    if not isinstance(raw_slots, list):
        raise ValueError(f"Type-node {node.id} has malformed 'slots' in props")
    slots = [NodeSlot.model_validate(s) for s in raw_slots]
    if "instance_category" in node.props:
        instance_category = str(node.props.get(
            "instance_category") or "").strip()
    else:
        instance_category = str(node.props.get("type_kind") or "").strip()
    return TypeView(
        node_id=node.id,
        name=node.name,
        description=node.description,
        category=instance_category,
        slots=slots,
    )

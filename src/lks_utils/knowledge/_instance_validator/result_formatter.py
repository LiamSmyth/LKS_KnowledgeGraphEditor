"""Error message helpers for InstanceValidator."""
from __future__ import annotations


def format_not_type_node_error(node_id: object, category: object) -> str:
    """Build consistent error text for non-type node lookups."""
    return f"Node {node_id} is not a type-node (category={category!r})"


def format_node_validation_error(
    *,
    node_id: str,
    type_name: str,
    error: Exception,
) -> str:
    """Build consistent validation failure text for one node."""
    return f"Node {node_id} fails validation against type {type_name!r}: {error}"

"""System-level knowledge helpers and reserved behaviors."""
from __future__ import annotations

from lks_utils.knowledge.system.system_reserved import (
    CategoryTransitionValidationResult,
    RESERVED_NODE_CATEGORIES,
    TYPE_NODE_CATEGORY,
    can_write_meta_field,
    is_reserved_node_category,
    validate_instance_category_value,
    validate_node_category_transition,
)
from lks_utils.knowledge.system.type_introspection import (
    categorize_node,
    is_type_node,
    iter_instances_of,
)

__all__ = [
    "CategoryTransitionValidationResult",
    "RESERVED_NODE_CATEGORIES",
    "TYPE_NODE_CATEGORY",
    "can_write_meta_field",
    "categorize_node",
    "is_reserved_node_category",
    "is_type_node",
    "iter_instances_of",
    "validate_instance_category_value",
    "validate_node_category_transition",
]

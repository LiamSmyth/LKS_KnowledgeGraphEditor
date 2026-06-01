"""System-reserved identifiers and structural guardrails for knowledge nodes."""
from __future__ import annotations

from dataclasses import dataclass


TYPE_NODE_CATEGORY = "_type"
RESERVED_NODE_CATEGORIES: frozenset[str] = frozenset({TYPE_NODE_CATEGORY})
_RESERVED_NODE_CATEGORIES_NORMALIZED: frozenset[str] = frozenset(
    value.casefold() for value in RESERVED_NODE_CATEGORIES
)


@dataclass(frozen=True)
class CategoryTransitionValidationResult:
    """Validation result for node-category transition checks."""

    allowed: bool
    message: str = ""


def is_reserved_node_category(category: str) -> bool:
    """Return True when *category* is a reserved system category token."""
    return category.strip().casefold() in _RESERVED_NODE_CATEGORIES_NORMALIZED


def can_write_meta_field(*, field: str, node_category: str) -> bool:
    """Return whether a node meta field should be writable in the UI."""
    if field == "category" and node_category == TYPE_NODE_CATEGORY:
        return False
    return True


def validate_node_category_transition(
    *,
    current_category: str,
    proposed_category: str,
) -> CategoryTransitionValidationResult:
    """Validate a category edit against system-reserved structural invariants."""
    current_normalized = current_category.strip().casefold()
    proposed_normalized = proposed_category.strip().casefold()
    reserved_normalized = TYPE_NODE_CATEGORY.casefold()

    if current_normalized == reserved_normalized and proposed_normalized != reserved_normalized:
        return CategoryTransitionValidationResult(
            allowed=False,
            message=(
                "Type-nodes must keep category '_type'. "
                "Edit 'instance_category' to control categories assigned to instances."
            ),
        )

    if current_normalized != reserved_normalized and proposed_normalized == reserved_normalized:
        return CategoryTransitionValidationResult(
            allowed=False,
            message=(
                "'_type' is a reserved system category and cannot be assigned to instance nodes."
            ),
        )

    return CategoryTransitionValidationResult(allowed=True)


def validate_instance_category_value(value: str) -> CategoryTransitionValidationResult:
    """Validate a type's instance_category value against reserved categories."""
    normalized = value.strip().casefold()
    if normalized == TYPE_NODE_CATEGORY.casefold():
        return CategoryTransitionValidationResult(
            allowed=False,
            message=(
                "'_type' is a reserved internal marker and cannot be used as an instance category."
            ),
        )
    return CategoryTransitionValidationResult(allowed=True)


__all__ = [
    "CategoryTransitionValidationResult",
    "RESERVED_NODE_CATEGORIES",
    "TYPE_NODE_CATEGORY",
    "can_write_meta_field",
    "is_reserved_node_category",
    "validate_instance_category_value",
    "validate_node_category_transition",
]

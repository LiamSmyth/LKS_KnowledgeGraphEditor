"""Legacy knowledge data migrator.

Converts old schema-based JSON node records (using ``node_id``, ``schema_id``,
``fields``) to the new ULID/EAV format (using ``id``, ``props``).

Slot compatibility path
-----------------------
``NodeSlot`` (alias ``PropertyDefinition``) stores type-node property
definitions in ``props["slots"]``.  The model has been extended over time::

    Phase 1 (original fields):
        name, source, required, ref_type, default, entry_mode, description,
        value_type, target_type

    Phase 2 additions (all have defaults - old repos load cleanly):
        value_mode, cardinality, min_count, max_count, version, constraints,
        editor_hint

Because every Phase-2 field carries a default, a type-node saved with only
Phase-1 slot fields loads via ``NodeSlot.model_validate`` without any
manual migration. ``NodeSlot.effective_value_mode()`` derives the correct
``PropertyValueMode`` from the legacy ``source`` field automatically.

For slot dicts that contain *unknown* keys (written by future tooling or
external systems), use :func:`migrate_slot_dict` to strip unrecognised keys
before validation. :func:`migrate_type_node_slots` applies this to a full
type-node dict.
"""
from __future__ import annotations

from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node import Node

__all__ = [
    "migrate_node_dict",
    "migrate_node_dicts",
    "migrate_slot_dict",
    "migrate_type_node_slots",
]

# ---------------------------------------------------------------------------
# Slot-level migration
# ---------------------------------------------------------------------------

_KNOWN_SLOT_FIELDS: frozenset[str] = frozenset({
    "name", "source", "required", "ref_type", "default", "entry_mode",
    "description", "value_type", "value_mode", "target_type", "cardinality",
    "min_count", "max_count", "version", "constraints", "editor_hint",
})


def migrate_slot_dict(raw: dict[str, object]) -> dict[str, object]:
    """Normalise an old-style slot dict to match the current ``NodeSlot`` schema.

    Removes any keys that are not part of the current ``NodeSlot`` model so
    that ``NodeSlot.model_validate`` (which uses ``extra="forbid"``) accepts
    the result.  All recognised fields are passed through as-is; the Phase-2
    fields that are absent will be populated from their model defaults on
    validation.

    Args:
        raw: A raw slot dict loaded from disk (any format version).

    Returns:
        A normalised dict safe to pass to ``NodeSlot.model_validate``.
    """
    return {k: v for k, v in raw.items() if k in _KNOWN_SLOT_FIELDS}


def migrate_type_node_slots(node_dict: dict[str, object]) -> dict[str, object]:
    """Return a copy of *node_dict* with its ``props["slots"]`` list migrated.

    Applies :func:`migrate_slot_dict` to every element in the slot list so the
    resulting dict can be passed to ``Node.model_validate`` and then
    ``as_type()`` without slot-level validation errors.

    Args:
        node_dict: A raw node dict (already decoded from JSON) representing a
            type-node (``category == "_type"``).

    Returns:
        A shallow copy of *node_dict* where ``props["slots"]`` has been
        normalised.  If the node has no ``props`` or no ``slots`` list, the
        original data is returned unchanged.
    """
    raw_props = node_dict.get("props")
    if not isinstance(raw_props, dict):
        return node_dict
    raw_slots = raw_props.get("slots")
    if not isinstance(raw_slots, list):
        return node_dict
    migrated_slots = [
        migrate_slot_dict(s) if isinstance(s, dict) else s
        for s in raw_slots
    ]
    new_props = {**raw_props, "slots": migrated_slots}
    return {**node_dict, "props": new_props}


# ---------------------------------------------------------------------------
# Node-level migration (original)
# ---------------------------------------------------------------------------


def migrate_node_dict(old_dict: dict[str, object]) -> Node:
    """Convert an old-format node record to a :class:`Node`.

    Old format::

        {
            "node_id": "some-old-string-id",
            "schema_id": "term",
            "name": "Velocity",
            "description": "Rate of change.",
            "fields": {"label": "Velocity", "unit": "m/s"}
        }

    New format: a :class:`Node` with ULID ``id``, ``kind`` from
    ``schema_id`` (or ``"generic"`` when absent), and all old ``fields`` values
    promoted into ``props``.

    Args:
        old_dict: A ``dict`` loaded from an old-format JSON node file.

    Returns:
        A fresh :class:`Node` with an auto-generated ULID identity.
    """
    name = str(old_dict.get("name") or "")
    description = str(old_dict.get("description") or "")
    kind = str(old_dict.get("schema_id") or old_dict.get("kind") or "generic")

    # Merge old "fields" dict into props; fall back to existing "props" dict
    raw_fields = old_dict.get("fields")
    raw_props = old_dict.get("props")
    if isinstance(raw_fields, dict):
        props: dict[str, object] = dict(raw_fields)
    elif isinstance(raw_props, dict):
        props = dict(raw_props)
    else:
        props = {}

    return Node(
        id=NodeId.new(),
        category=kind,
        name=name,
        description=description,
        props=props,
    )


def migrate_node_dicts(old_records: list[dict[str, object]]) -> list[Node]:
    """Convert a list of old-format node records to :class:`Node` objects.

    Args:
        old_records: List of old-format node dicts.

    Returns:
        List of migrated :class:`Node` objects with new ULID identities.
    """
    return [migrate_node_dict(record) for record in old_records]

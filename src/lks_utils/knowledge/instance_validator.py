"""Validation of node instances against type-node slot definitions."""
from __future__ import annotations

from pydantic import BaseModel, create_model

from lks_utils.knowledge._editor_session.selection import resolve_ref_type_to_type_ids
from lks_utils.knowledge._instance_validator.result_formatter import (
    format_node_validation_error,
    format_not_type_node_error,
)
from lks_utils.knowledge._instance_validator.rule_registry import (
    PROPERTY_VERSIONS_PROP,
    PROTOTYPE_ID_PROP,
    RESERVED_VALIDATION_PROP_NAMES,
    TYPE_VERSION_PROP,
    VALIDATION_ERRORS_PROP,
    VALIDATION_STATUS_CANNOT_COMPILE,
    VALIDATION_STATUS_PROP,
)
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_slot import NodeSlot, PropertyValueMode
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.resolver import Resolver


class InstanceValidator:
    """Validates nodes against their type-node's slot definitions.

    The validator is bound to a ``Repository``-like object that
    provides ``get(type_id) -> Node``. Pydantic dynamic models are
    cached by ``(type_id_str, type_rev)`` so validation is fast on repeat
    calls and the cache automatically invalidates when the type changes.
    """

    def __init__(self, repository: object) -> None:
        # repository must expose .get(node_id: str | NodeId) -> Node
        self._repository = repository
        self._model_cache: dict[tuple[str, int], type[BaseModel]] = {}

    def validate_node(self, node: Node) -> None:
        """Raise ``ValueError`` when *node* does not conform to its type's slots.

        Nodes without a ``type_id`` pass validation unconditionally.
        """
        if node.type_id is None:
            return

        type_node = self._repository.get(node.type_id)
        if not is_type(type_node):
            raise ValueError(format_not_type_node_error(
                node.type_id, type_node.category))

        merged_slots = self._merged_type_slots(type_node)
        self._validate_props(
            node_id=str(node.id),
            category=node.category,
            props=node.props,
            type_node=type_node,
            slots=merged_slots,
        )

    def version_issues(self, node: Node) -> dict[str, str]:
        """Return schema drift issues for *node* relative to its current type."""
        if node.type_id is None:
            return {}

        type_node = self._repository.get(node.type_id)
        if not is_type(type_node):
            return {"type": f"Node {node.type_id} is not a type-node"}

        issues: dict[str, str] = {}
        stored_type_version = node.props.get(TYPE_VERSION_PROP)
        if isinstance(stored_type_version, int) and stored_type_version != type_node.rev:
            issues["type"] = (
                f"Type version drift: instance snapshot {stored_type_version} != current {type_node.rev}"
            )

        raw_property_versions = node.props.get(PROPERTY_VERSIONS_PROP)
        property_versions = raw_property_versions if isinstance(
            raw_property_versions, dict) else {}
        for slot in self._merged_type_slots(type_node):
            stored_slot_version = property_versions.get(slot.name)
            if isinstance(stored_slot_version, int) and stored_slot_version != slot.version:
                issues[slot.name] = (
                    f"Property version drift: instance snapshot {stored_slot_version} != current {slot.version}"
                )
        return issues

    def repair_node(self, node: Node) -> Node | None:
        """Return a repaired copy of *node* if schema drift is detected, else ``None``.

        Repair strategy:
        - Add missing slots with their type-default values (new slots added to type).
        - Update version stamps (``__type_version__`` and ``__property_versions__``).
        - Existing slot values are always preserved, even for drifted slots.
        - Props for slots removed from the type are left as-is (orphaned) to avoid
          data loss; they will simply not be shown in the inspector.

        Returns ``None`` when the node has no type, the type is unresolvable, or
        no drift is detected (caller can skip the upsert).
        """
        if node.type_id is None:
            return None
        try:
            type_node = self._repository.get(node.type_id)
        except (KeyError, Exception):  # noqa: BLE001
            return None
        if not is_type(type_node):
            return None

        # Check for any drift before doing work.
        if not self.version_issues(node):
            return None

        merged_slots = self._merged_type_slots(type_node)
        repaired_props: dict[str, object] = dict(node.props)

        # Add defaults for slots that don't have a value yet.
        for slot in merged_slots:
            if slot.name not in repaired_props:
                repaired_props[slot.name] = slot.default_value()

        # Refresh version stamps to current type state.
        repaired_props[TYPE_VERSION_PROP] = type_node.rev
        repaired_props[PROPERTY_VERSIONS_PROP] = {
            slot.name: slot.version for slot in merged_slots
        }

        return node.model_copy(update={"props": repaired_props, "rev": node.rev + 1})

    def _merged_type_slots(self, type_node: Node) -> list[NodeSlot]:
        """Return slots merged across the full type ancestry chain."""
        resolver = Resolver(self._repository)
        chain = resolver.fetch_parent_chain(type_node) + [type_node]
        merged: dict[str, NodeSlot] = {}
        for candidate in chain:
            if not is_type(candidate):
                continue
            for slot in as_type(candidate).slots:
                merged[slot.name] = slot
        return list(merged.values())

    def _validate_props(
        self,
        *,
        node_id: str,
        category: str,
        props: dict[str, object],
        type_node: Node,
        slots: list[NodeSlot],
    ) -> None:
        props = {
            key: value
            for key, value in props.items()
            if key not in RESERVED_VALIDATION_PROP_NAMES
        }
        pydantic_model = self._get_or_build_model(
            str(type_node.id), type_node.rev, slots)
        try:
            pydantic_model.model_validate(props)
        except Exception as exc:
            raise ValueError(
                format_node_validation_error(
                    node_id=node_id,
                    type_name=type_node.name,
                    error=exc,
                )
            ) from exc
        self._validate_slot_values(node_id=node_id, props=props, slots=slots)

    def _validate_slot_values(
        self,
        *,
        node_id: str,
        props: dict[str, object],
        slots: list[NodeSlot],
    ) -> None:
        # Import here to avoid circular dependencies and trigger auto-registration
        from lks_utils.knowledge.property_types import (
            PROPERTY_TYPE_REGISTRY,
            SlotContext,
        )
        from lks_utils.knowledge.property_types import builtins as _  # noqa: F401

        for slot in slots:
            value = props.get(slot.name)
            value_mode = slot.effective_value_mode()
            if value_mode.allows_reference:
                target_ids = self._slot_ref_targets(
                    node_id=node_id, slot_name=slot.name)
                if not target_ids:
                    if value is not None:
                        raise ValueError(
                            f"Property {slot.name!r} stores reference data in props; "
                            "references must be represented as slot_ref links."
                        )
                    if slot.required:
                        raise ValueError(
                            f"Required property {slot.name!r} is empty")
                    continue

                if value_mode != PropertyValueMode.REF_LIST:
                    self._validate_reference_target(
                        slot, target_ids[0], field=slot.name)
                else:
                    for index, target_id in enumerate(target_ids):
                        self._validate_reference_target(
                            slot,
                            target_id,
                            field=f"{slot.name}[{index}]",
                        )
                continue

            if value is None:
                default_value = slot.default_value()
                if default_value is not None:
                    continue
                if slot.required:
                    raise ValueError(
                        f"Required property {slot.name!r} is empty")
                continue

            # Try PropertyTypeRegistry dispatch first (core types)
            value_type = (slot.value_type or "any").strip().lower()
            if PROPERTY_TYPE_REGISTRY.has(value_type):
                pt = PROPERTY_TYPE_REGISTRY.get(value_type)

                # Create minimal SlotContext for property type validation
                class _NoOpRepo:
                    def get_node(self, node_id: str):  # type: ignore
                        return None

                    def get_link(self, link_id: str):  # type: ignore
                        return None

                    def list_nodes_of_type(self, type_id: str):  # type: ignore
                        return []

                ctx = SlotContext(
                    slot_name=slot.name,
                    owner_type_id=None,
                    sibling_slot=lambda _: None,
                    repo_read=_NoOpRepo(),  # type: ignore
                )

                # Run PropertyType validation
                issues = pt.validate(value, ctx)
                if issues:
                    raise ValueError(
                        f"Property {slot.name!r} fails PropertyType "
                        f"validation: {'; '.join(str(i) for i in issues)}"
                    )
                continue

    def _slot_ref_targets(self, *, node_id: str, slot_name: str) -> list[str]:
        if not hasattr(self._repository, "list_links"):
            return []
        targets: list[str] = []
        for link in self._repository.list_links():
            if (
                link.link_type_id == SLOT_REF_LINK_TYPE_ID
                and str(link.source_node_id) == node_id
                and link.source_slot_name == slot_name
            ):
                targets.append(str(link.target_node_id))
        return targets

    def _validate_reference_target(self, slot: NodeSlot, target_id: str, *, field: str) -> None:
        try:
            target = self._repository.get(target_id)
        except KeyError as exc:
            raise ValueError(
                f"Property {field!r} references missing node {target_id!r}") from exc

        expected_type_token = str(
            slot.target_type or slot.ref_type or slot.value_type or ""
        ).strip()
        if expected_type_token == "" or expected_type_token.casefold() in {"any", "ref", "ref_list"}:
            return

        allowed_type_ids = resolve_ref_type_to_type_ids(
            iter_types=self._repository.list_types(),
            token=expected_type_token.casefold(),
            iter_links=self._repository.list_links(),
            iter_link_types=self._repository.list_link_types(),
        )

        target_type_id: str | None = None
        if target.type_id is not None:
            target_type_id = str(target.type_id)
        elif is_type(target):
            target_type_id = str(target.id)

        if target_type_id is None:
            raise ValueError(
                f"Property {field!r} expects a typed reference to {expected_type_token!r}, "
                f"but target node {target_id!r} has no type assigned."
            )

        if target_type_id not in allowed_type_ids:
            raise ValueError(
                f"Property {field!r} expects reference to {expected_type_token!r}, got {target.category!r}"
            )

    def _get_or_build_model(
        self,
        type_id_str: str,
        type_rev: int,
        slots: list[NodeSlot],
    ) -> type[BaseModel]:
        cache_key = (type_id_str, type_rev)
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]
        model = _build_pydantic_model(type_id_str, slots)
        self._model_cache[cache_key] = model
        return model


def _build_pydantic_model(type_id_str: str, slots: list[NodeSlot]) -> type[BaseModel]:
    """Build a Pydantic model class from a list of slots."""
    from typing import Any, Optional  # noqa: PLC0415

    field_definitions: dict[str, tuple[type, object]] = {}
    for slot in slots:
        field_definitions[slot.name] = (
            Optional[Any], None)  # type: ignore[assignment]

    safe_name = f"TypeModel_{type_id_str.replace('-', '_')}"
    # type: ignore[call-overload]
    return create_model(safe_name, **field_definitions)

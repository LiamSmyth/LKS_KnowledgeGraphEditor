"""Mutator for promote/inline operations on knowledge nodes."""
from __future__ import annotations

import copy

from lks_utils.knowledge.instance_validator import (
    RESERVED_VALIDATION_PROP_NAMES,
    VALIDATION_ERRORS_PROP,
    VALIDATION_STATUS_CANNOT_COMPILE,
    VALIDATION_STATUS_PROP,
    InstanceValidator,
)
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_slot import NodeSlot, PropertyValueMode, SlotSource
from lks_utils.knowledge.models.type import as_type
from lks_utils.knowledge.instance_validator import PROTOTYPE_ID_PROP
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.resolver import Resolver


class Mutator:
    """Provides promote-to-node and inline-reference operations.

    Both operations work atomically at the repository level: promote writes
    a new node *and* updates the parent in a single transaction (both
    ``repository.upsert`` calls happen before any persistence). Inline
    deletes the target *and* updates the parent inline in the same
    transaction.
    """

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    # ------------------------------------------------------------------
    # Promote
    # ------------------------------------------------------------------

    def promote(
        self,
        parent_id: str | NodeId,
        prop_path: str,
        new_name: str,
        description: str,
    ) -> NodeId:
        """Promote an inline composite at *prop_path* to a standalone node.

        The inline dict at ``parent.props[prop_path]`` is extracted,
        assigned a fresh ULID, saved as a new ``Node``, and the
        parent's slot is replaced with a slot_ref link when the slot
        is reference-capable.

        Args:
            parent_id: ULID of the node that owns the inline composite.
            prop_path: Top-level key in ``parent.props`` to promote.
            new_name: Name for the new standalone node.
            description: Description for the new standalone node.

        Returns:
            The ``NodeId`` of the newly created node.

        Raises:
            KeyError: If *parent_id* is unknown.
            ValueError: If the value at *prop_path* is not a dict
                (inline composite).
        """
        parent = self._repository.get(parent_id)
        value = parent.props.get(prop_path)

        if not isinstance(value, dict):
            raise ValueError(
                f"prop {prop_path!r} in node {parent_id} is not an inline composite "
                f"(got {type(value).__name__!r})"
            )

        new_id = NodeId.new()
        new_node = Node(
            id=new_id,
            category=parent.category,
            name=new_name,
            description=description,
            props=copy.deepcopy(value),
            source_repo_id=parent.source_repo_id,
        )

        self._repository.upsert(new_node)
        self.set_slot_value(parent.id, prop_path, str(new_id))
        return new_id

    # ------------------------------------------------------------------
    # Inline
    # ------------------------------------------------------------------

    def inline(
        self,
        parent_id: str | NodeId,
        prop_path: str,
    ) -> None:
        """Inline a reference target back into the parent, deleting the target node.

        Only works when the target node's ref-count within the repository
        is exactly 1 (i.e., only the parent references it via a slot_ref link).

        Args:
            parent_id: ULID of the node containing the reference slot.
            prop_path: Top-level key for the reference slot.

        Raises:
            KeyError: If *parent_id* or the referenced node is unknown.
            ValueError: If *prop_path* is not a reference slot, or the ref-count
                is not exactly 1.
        """
        parent = self._repository.get(parent_id)
        target_id_str: str | None = None
        for link in self._repository.list_links():
            if (
                link.link_type_id == SLOT_REF_LINK_TYPE_ID
                and str(link.source_node_id) == str(parent.id)
                and link.source_slot_name == prop_path
            ):
                target_id_str = str(link.target_node_id)
                break
        if target_id_str is None:
            raise ValueError(
                f"prop {prop_path!r} in node {parent_id} is not a reference"
            )

        target = self._repository.get(target_id_str)

        # Count references to target across the whole repository
        resolver = Resolver(self._repository)
        dependents = resolver.get_dependents(target_id_str)
        if len(dependents) != 1 or dependents[0] != str(parent.id):
            raise ValueError(
                f"Cannot inline {target_id_str!r}: ref-count is {len(dependents)} "
                f"(dependents: {dependents!r}). Inline only works when ref-count == 1."
            )

        if slot_name := prop_path:
            self._clear_slot_ref_links(str(parent.id), slot_name)
            new_props = dict(parent.props)
            new_props.pop(slot_name, None)
            updated_parent = parent.model_copy(
                update={"props": new_props, "rev": parent.rev + 1}
            )
            self._repository.upsert(updated_parent)
        self._repository.delete(target_id_str)

    # ------------------------------------------------------------------
    # Slot operations on type-nodes
    # ------------------------------------------------------------------

    def add_slot(
        self,
        type_id: str | NodeId,
        slot: NodeSlot | dict[str, object],
    ) -> None:
        """Append one validated slot to a type-node's ``props['slots']`` list."""
        type_node = self._repository.get(type_id)
        type_view = as_type(type_node)
        normalized_slot = self._normalize_slot(slot)
        if any(existing.name == normalized_slot.name for existing in type_view.slots):
            raise ValueError(
                f"Type {type_node.name!r} already has a slot named {normalized_slot.name!r}."
            )
        inherited_slot = self._find_inherited_type_slot(
            type_node, normalized_slot.name)
        if inherited_slot is not None:
            raise ValueError(
                f"Type {type_node.name!r} inherits a slot named {normalized_slot.name!r}; "
                "child types may extend schema but cannot redeclare inherited slots."
            )
        new_slots = [s.model_dump() for s in type_view.slots]
        new_slots.append(normalized_slot.model_dump())
        updated_type = type_node.model_copy(
            update={"props": {**type_node.props, "slots": new_slots},
                    "rev": type_node.rev + 1}
        )
        self._repository.upsert(updated_type)

    def remove_slot(
        self,
        type_id: str | NodeId,
        slot_name: str,
    ) -> None:
        """Remove one slot by name from a type-node."""
        type_node = self._repository.get(type_id)
        type_view = as_type(type_node)
        remaining_slots = [s for s in type_view.slots if s.name != slot_name]
        if len(remaining_slots) == len(type_view.slots):
            raise KeyError(
                f"Slot {slot_name!r} does not exist in type {type_node.id}")
        updated_type = type_node.model_copy(
            update={
                "props": {**type_node.props, "slots": [s.model_dump() for s in remaining_slots]},
                "rev": type_node.rev + 1,
            }
        )
        self._repository.upsert(updated_type)

    def update_slot(
        self,
        type_id: str | NodeId,
        slot_name: str,
        slot: NodeSlot | dict[str, object],
    ) -> None:
        """Replace one slot on a type-node by slot name."""
        type_node = self._repository.get(type_id)
        type_view = as_type(type_node)
        normalized_slot = self._normalize_slot(slot)
        if normalized_slot.name != slot_name:
            inherited_slot = self._find_inherited_type_slot(
                type_node, normalized_slot.name)
            if inherited_slot is not None:
                raise ValueError(
                    f"Type {type_node.name!r} inherits a slot named {normalized_slot.name!r}; "
                    "child types may extend schema but cannot redeclare inherited slots."
                )
        updated_slots: list[NodeSlot] = []
        found = False
        for existing in type_view.slots:
            if existing.name == slot_name:
                found = True
                updated_slots.append(
                    normalized_slot.model_copy(
                        update={"version": existing.version + 1})
                )
                continue
            if existing.name == normalized_slot.name:
                raise ValueError(
                    f"Type {type_node.id} already contains a slot named {normalized_slot.name!r}"
                )
            updated_slots.append(existing)
        if not found:
            raise KeyError(
                f"Slot {slot_name!r} does not exist in type {type_node.id}")
        updated_type = type_node.model_copy(
            update={
                "props": {**type_node.props, "slots": [s.model_dump() for s in updated_slots]},
                "rev": type_node.rev + 1,
            }
        )
        self._repository.upsert(updated_type)

    def set_type_inherited_default_override(
        self,
        type_id: str | NodeId,
        slot_name: str,
        value: object,
    ) -> None:
        """Reject type-level inherited slot overrides.

        Child types may extend schema with new slots, but inherited parent slot
        contracts are immutable in the child schema.
        """
        type_node = self._repository.get(type_id)
        inherited_slot = self._find_inherited_type_slot(type_node, slot_name)
        if inherited_slot is not None:
            raise ValueError(
                f"Type {type_node.name!r} inherits slot {slot_name!r}; child types cannot override inherited slot defaults."
            )

        current_slot = next(
            (slot for slot in as_type(type_node).slots if slot.name == slot_name),
            None,
        )
        if current_slot is None:
            raise KeyError(
                f"Slot {slot_name!r} does not exist in type {type_node.id}."
            )
        updated_slot = current_slot.model_copy(
            update={"default": value, "version": current_slot.version + 1}
        )
        self.update_slot(type_id, slot_name, updated_slot)

    def clear_type_inherited_default_override(
        self,
        type_id: str | NodeId,
        slot_name: str,
    ) -> None:
        """Reject clearing non-existent type-level inherited slot overrides."""
        type_node = self._repository.get(type_id)
        inherited_slot = self._find_inherited_type_slot(type_node, slot_name)
        if inherited_slot is None:
            raise KeyError(
                f"Slot {slot_name!r} is not inherited for type {type_node.id}; nothing to clear."
            )
        raise ValueError(
            f"Type {type_node.name!r} inherits slot {slot_name!r}; child types cannot override inherited slot defaults."
        )

    def set_instance_chain_default_override(
        self,
        node_id: str | NodeId,
        slot_name: str,
        value: object,
    ) -> None:
        """Set prototype/instance-chain default override for derived instances.

        This writes to the selected prototype instance's ``node.props`` delta
        after validating the slot exists in the backing type chain.
        """
        node = self._repository.get(node_id)
        self._require_instance_schema_slot(node, slot_name)
        self.set_slot_value(node_id, slot_name, value)

    def clear_instance_chain_default_override(
        self,
        node_id: str | NodeId,
        slot_name: str,
    ) -> None:
        """Clear a prototype/instance-chain override and restore upstream fallback."""
        node = self._repository.get(node_id)
        self._require_instance_schema_slot(node, slot_name)
        self.discard_slot_value(node_id, slot_name)

    def set_local_instance_override(
        self,
        node_id: str | NodeId,
        slot_name: str,
        value: object,
    ) -> None:
        """Set an explicit per-instance local override in ``node.props``."""
        node = self._repository.get(node_id)
        self._require_instance_schema_slot(node, slot_name)
        self.set_slot_value(node_id, slot_name, value)

    def clear_local_instance_override(
        self,
        node_id: str | NodeId,
        slot_name: str,
    ) -> None:
        """Clear explicit per-instance override so inherited resolution applies."""
        node = self._repository.get(node_id)
        self._require_instance_schema_slot(node, slot_name)
        self.discard_slot_value(node_id, slot_name)

    def set_slot_value(
        self,
        node_id: str | NodeId,
        slot_name: str,
        value: object,
    ) -> None:
        """Set one slot value on an instance.

        REF and REF_LIST slots are stored as slot_ref link instances in the
        repository; the slot_name is NOT written to props.  LITERAL slots
        (and untyped nodes) write the value to props as before.

        Typed instances preserve invalid values and attach validation metadata so
        the editor can keep malformed data visible instead of dropping the write.
        """
        node = self._repository.get(node_id)
        if node.type_id is not None or PROTOTYPE_ID_PROP in node.props:
            self._require_instance_schema_slot(node, slot_name)
        slot_contract = self._get_slot_contract(node, slot_name)
        if (
            slot_contract is not None
            and slot_contract.effective_value_mode() == PropertyValueMode.REF_OR_INLINE
        ):
            if self._is_reference_payload(value):
                target_ids = self._extract_ref_targets(value)
                if len(target_ids) > 1:
                    raise ValueError(
                        f"Property {slot_name!r} expects a single reference target"
                    )
                self._replace_slot_ref_links(
                    str(node_id), slot_name, target_ids)
                if slot_name in node.props:
                    cleaned = dict(node.props)
                    cleaned.pop(slot_name)
                    self._repository.upsert(
                        node.model_copy(
                            update={"props": cleaned, "rev": node.rev + 1})
                    )
                return

            # Inline branch for REF_OR_INLINE: clear stale slot_ref links and
            # persist the inline value in props.
            self._clear_slot_ref_links(str(node_id), slot_name)
            self._set_literal_slot_value(node, slot_name, value)
            return

        slot_source = self._get_slot_source(node, slot_name)

        if slot_source in (SlotSource.REF, SlotSource.REF_LIST):
            target_ids = self._extract_ref_targets(value)
            if slot_source == SlotSource.REF and len(target_ids) > 1:
                raise ValueError(
                    f"Property {slot_name!r} expects a single reference target"
                )
            self._replace_slot_ref_links(str(node_id), slot_name, target_ids)
            # Remove stale inline values from historical payloads now that
            # references are represented exclusively as slot_ref links.
            if slot_name in node.props:
                cleaned = dict(node.props)
                cleaned.pop(slot_name)
                self._repository.upsert(
                    node.model_copy(
                        update={"props": cleaned, "rev": node.rev + 1})
                )
            return

        self._set_literal_slot_value(node, slot_name, value)

    def discard_slot_value(self, node_id: str | NodeId, slot_name: str) -> None:
        """Drop one slot value and clear stale validation metadata for that slot.

        For REF / REF_LIST slots this clears the corresponding slot_ref links.
        """
        node = self._repository.get(node_id)
        slot_source = self._get_slot_source(node, slot_name)

        if slot_source in (SlotSource.REF, SlotSource.REF_LIST):
            self._clear_slot_ref_links(str(node_id), slot_name)
            if slot_name in node.props:
                cleaned = dict(node.props)
                cleaned.pop(slot_name)
                self._repository.upsert(
                    node.model_copy(
                        update={"props": cleaned, "rev": node.rev + 1})
                )
            return

        updated_props = dict(node.props)
        updated_props.pop(slot_name, None)
        validation_errors = self._validation_errors(updated_props)
        validation_errors.pop(slot_name, None)

        if validation_errors:
            updated_props[VALIDATION_STATUS_PROP] = VALIDATION_STATUS_CANNOT_COMPILE
            updated_props[VALIDATION_ERRORS_PROP] = validation_errors
        else:
            for key in RESERVED_VALIDATION_PROP_NAMES:
                updated_props.pop(key, None)

        updated_node = node.model_copy(
            update={"props": updated_props, "rev": node.rev + 1})
        self._repository.upsert(updated_node)

    # ------------------------------------------------------------------ helpers

    def _get_slot_source(self, node: Node, slot_name: str) -> SlotSource | None:
        """Return the SlotSource for *slot_name* from the node's type, or None."""
        if node.type_id is None:
            return None
        try:
            type_node = self._repository.get(node.type_id)
        except KeyError:
            return None
        resolver = Resolver(self._repository)
        chain = resolver.fetch_parent_chain(type_node) + [type_node]
        for candidate in reversed(chain):
            for slot in as_type(candidate).slots:
                if slot.name == slot_name:
                    value_mode = slot.effective_value_mode()
                    if value_mode.allows_reference:
                        return SlotSource.REF_LIST if value_mode.allows_list else SlotSource.REF
                    return slot.source
        return None

    def _get_slot_contract(self, node: Node, slot_name: str) -> NodeSlot | None:
        """Return the merged slot contract for *slot_name* from the node's type."""
        if node.type_id is None:
            return None
        try:
            type_node = self._repository.get(node.type_id)
        except KeyError:
            return None
        resolver = Resolver(self._repository)
        chain = resolver.fetch_parent_chain(type_node) + [type_node]
        for candidate in reversed(chain):
            for slot in as_type(candidate).slots:
                if slot.name == slot_name:
                    return slot
        return None

    def _is_reference_payload(self, value: object) -> bool:
        """Return True when *value* encodes a reference payload shape."""
        if value is None:
            return True
        try:
            self._extract_ref_targets(value)
            return True
        except ValueError:
            return False

    def _set_literal_slot_value(self, node: Node, slot_name: str, value: object) -> None:
        """Persist a literal/inline slot value with validation metadata updates."""
        updated_props = dict(node.props)
        updated_props[slot_name] = value
        validation_errors = self._validation_errors(updated_props)
        validation_errors.pop(slot_name, None)

        if node.type_id is not None:
            validator = InstanceValidator(self._repository)
            updated_node = node.model_copy(
                update={"props": updated_props, "rev": node.rev + 1})
            try:
                validator.validate_node(updated_node)
            except ValueError as exc:
                raise ValueError(
                    f"Cannot set slot {slot_name!r}: {exc}"
                ) from exc

        if validation_errors:
            updated_props[VALIDATION_STATUS_PROP] = VALIDATION_STATUS_CANNOT_COMPILE
            updated_props[VALIDATION_ERRORS_PROP] = validation_errors
        else:
            for key in RESERVED_VALIDATION_PROP_NAMES:
                updated_props.pop(key, None)

        updated_node = node.model_copy(
            update={"props": updated_props, "rev": node.rev + 1})
        self._repository.upsert(updated_node)

    def _find_inherited_type_slot(self, type_node: Node, slot_name: str) -> NodeSlot | None:
        """Return inherited parent slot contract for *slot_name*, if present."""
        resolver = Resolver(self._repository)
        for ancestor in reversed(resolver.fetch_parent_chain(type_node)):
            for slot in as_type(ancestor).slots:
                if slot.name == slot_name:
                    return slot
        return None

    def _require_instance_schema_slot(self, node: Node, slot_name: str) -> None:
        """Enforce schema-locked instance inheritance for value-only overrides."""
        type_node: Node | None = None
        if node.type_id is not None:
            try:
                type_node = self._repository.get(node.type_id)
            except KeyError:
                type_node = None
        if type_node is None:
            resolver = Resolver(self._repository)
            type_node = resolver.fetch_type_for_instance(node)
        if type_node is None:
            raise ValueError(
                f"Node {node.id} has no resolvable type; instance inheritance path is schema-locked."
            )
        resolver = Resolver(self._repository)
        type_slots = resolver.available_slot_names(node)
        if slot_name not in type_slots:
            raise ValueError(
                f"Slot {slot_name!r} is not defined in type schema {type_node.id}; "
                "instance inheritance cannot extend schema."
            )
        prototype_id = node.props.get(PROTOTYPE_ID_PROP)
        if prototype_id is not None and not isinstance(prototype_id, str):
            raise ValueError(
                f"Prototype marker for node {node.id} is malformed: expected string ID."
            )

    def _extract_ref_targets(self, value: object) -> list[str]:
        """Normalize REF/REF_LIST value to canonical node-id strings."""
        if value is None:
            return []
        if isinstance(value, dict):
            # MCP/UI wrappers: {"target_node_id": "..."} or {"$ref": "..."}
            for key in ("target_node_id", "$ref"):
                raw = value.get(key)
                if isinstance(raw, str):
                    stripped = raw.strip()
                    return [stripped] if stripped else []
            raise ValueError(
                "Reference dict payload must include string 'target_node_id' or '$ref'"
            )
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, (list, tuple)):
            result: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    nested = self._extract_ref_targets(item)
                    result.extend(nested)
                    continue
                if not isinstance(item, str):
                    raise ValueError(
                        "Reference list values must contain node-id strings only"
                    )
                stripped = item.strip()
                if stripped:
                    result.append(stripped)
            return list(dict.fromkeys(result))
        raise ValueError(
            f"Reference slot values must be node-id strings, got {type(value).__name__}"
        )

    def _replace_slot_ref_links(
        self,
        source_node_id: str,
        slot_name: str,
        target_node_ids: list[str],
    ) -> None:
        """Replace all slot_ref links for (source_node_id, slot_name) atomically."""
        self._clear_slot_ref_links(source_node_id, slot_name)
        for target_id in dict.fromkeys(target_node_ids):
            self._repository.upsert_link(
                LinkInstance(
                    link_type_id=SLOT_REF_LINK_TYPE_ID,
                    source_node_id=source_node_id,
                    target_node_id=target_id,
                    source_slot_name=slot_name,
                )
            )

    def _clear_slot_ref_links(self, source_node_id: str, slot_name: str) -> None:
        """Remove all slot_ref links for (source_node_id, slot_name)."""
        to_delete = [
            link.id
            for link in self._repository.list_links()
            if (
                link.link_type_id == SLOT_REF_LINK_TYPE_ID
                and link.source_node_id == source_node_id
                and link.source_slot_name == slot_name
            )
        ]
        for link_id in to_delete:
            self._repository.delete_link(link_id)

    def _validation_errors(self, props: dict[str, object]) -> dict[str, str]:
        raw_errors = props.get(VALIDATION_ERRORS_PROP)
        if not isinstance(raw_errors, dict):
            return {}
        errors: dict[str, str] = {}
        for key, value in raw_errors.items():
            if isinstance(key, str) and isinstance(value, str):
                errors[key] = value
        return errors

    def _normalize_slot(self, slot: NodeSlot | dict[str, object]) -> NodeSlot:
        normalized = slot if isinstance(
            slot, NodeSlot) else NodeSlot.model_validate(slot)
        return normalized if normalized.version >= 1 else normalized.model_copy(update={"version": 1})

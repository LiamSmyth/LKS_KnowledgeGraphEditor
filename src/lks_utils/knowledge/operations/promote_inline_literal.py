"""Promote inline literal values to stand-alone typed instances."""
from __future__ import annotations

from copy import deepcopy

from lks_utils.knowledge.mutator import Mutator
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node_slot import NodeSlot, SlotSource
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.resolver import Resolver


def promote_inline_literal(
    repo: Repository,
    owner_node_id: str,
    slot_path: tuple[str, ...],
) -> str:
    """Promote one inline literal slot to a stand-alone instance node.

    Currently supports promotion of top-level slot values only.
    """
    if len(slot_path) != 1:
        raise ValueError(
            "promote_inline_literal currently supports top-level slot paths only")

    slot_name = slot_path[0]
    owner_node = repo.get(owner_node_id)
    if slot_name not in owner_node.props:
        raise KeyError(
            f"Slot {slot_name!r} is not present on owner node {owner_node_id!r}")

    inline_value = owner_node.props[slot_name]
    if not isinstance(inline_value, dict):
        raise ValueError("Only dict-backed inline literals can be promoted")

    slot = _resolve_slot(repo, owner_node, slot_name)
    if slot is None:
        raise ValueError(
            f"Slot {slot_name!r} is not defined in the owner type schema")

    target_type_node = _resolve_target_type_node(repo, slot)
    if target_type_node is None:
        raise ValueError(
            f"Slot {slot_name!r} does not resolve to a promotable target type"
        )

    target_type_view = as_type(target_type_node)
    new_node = Node(
        id=NodeId.new(),
        category=target_type_view.category or owner_node.category,
        type_id=target_type_node.id,
        name=f"New {target_type_node.name}",
        props=deepcopy(inline_value),
        source_repo_id=owner_node.source_repo_id,
    )

    repo.upsert(new_node)
    if slot.source in (SlotSource.REF, SlotSource.REF_LIST):
        Mutator(repo).set_slot_value(
            str(owner_node.id),
            slot_name,
            str(new_node.id),
        )
    else:
        updated_owner_props = dict(owner_node.props)
        updated_owner_props[slot_name] = str(new_node.id)
        updated_owner = owner_node.model_copy(
            update={"props": updated_owner_props, "rev": owner_node.rev + 1}
        )
        repo.upsert(updated_owner)
    return str(new_node.id)


def _resolve_slot(repo: Repository, owner_node: Node, slot_name: str) -> NodeSlot | None:
    resolver = Resolver(repo)
    type_node = resolver.resolve_type_node_for_instance(owner_node)
    if type_node is None or not is_type(type_node):
        return None
    resolved_slot: NodeSlot | None = None
    for candidate_type in [*resolver.fetch_parent_chain(type_node), type_node]:
        for slot in as_type(candidate_type).slots:
            if slot.name == slot_name:
                resolved_slot = slot
    return resolved_slot


def _resolve_target_type_node(repo: Repository, slot: NodeSlot) -> Node | None:
    slot_type = str(slot.value_type or "").strip()
    if not slot_type or slot_type.lower() in {
        "any",
        "object",
        "string",
        "str",
        "int",
        "integer",
        "float",
        "number",
        "bool",
        "boolean",
        "list",
        "tuple",
        "dict",
        "set",
        "json",
        "bytes",
        "none",
        "nonetype",
    }:
        return None
    direct = repo.find_node(slot_type)
    if direct is not None and is_type(direct):
        return direct
    for type_node in repo.list_types():
        if type_node.name == slot_type:
            return type_node
    return None


__all__ = ["promote_inline_literal"]

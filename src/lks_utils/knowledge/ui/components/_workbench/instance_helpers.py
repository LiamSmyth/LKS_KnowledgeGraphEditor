"""Private instance and ref helpers for QKnowledgeWorkbenchWidget."""
from __future__ import annotations

import re

from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.instance_validator import PROTOTYPE_ID_PROP
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.type import as_type
from lks_utils.knowledge.repository import Repository


def has_valid_ref_targets(value: object, ulid_pattern: re.Pattern[str]) -> bool:
    """Return True when value contains one or more valid ULID ref targets."""
    if value is None:
        return False
    targets: list[str] = []
    if isinstance(value, str):
        targets = [value]
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                targets.append(item)
    elif isinstance(value, str):
        targets = [value]
    return bool(targets) and all(ulid_pattern.match(target) for target in targets)


def slot_ref_link_ids_for_node(repo: Repository, node_id: str) -> set[str]:
    """Return slot_ref link ids sourced from node_id in repo."""
    return {
        str(link.id)
        for link in repo.list_links()
        if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
    }


def resolve_instance_defaults(
    *,
    session: EditorSession,
    source_instance: Node,
    type_node: Node,
) -> dict[str, object]:
    """Return effective defaults for a new instance sourced from another instance."""
    type_view = as_type(type_node)
    slot_names = {slot.name for slot in type_view.slots}
    resolved: dict[str, object] = {
        slot.name: slot.default_value() for slot in type_view.slots
    }

    chain: list[Node] = []
    current: Node | None = source_instance
    visited: set[str] = set()
    while current is not None:
        current_id = str(current.id)
        if current_id in visited:
            break
        visited.add(current_id)
        chain.append(current)
        prototype_id = current.props.get(PROTOTYPE_ID_PROP)
        if not isinstance(prototype_id, str) or not prototype_id:
            break
        try:
            next_node = session.get_node(prototype_id)
        except KeyError:
            break
        if next_node.type_id != type_node.id:
            break
        current = next_node

    for instance_node in reversed(chain):
        for key, value in instance_node.props.items():
            if key in slot_names:
                resolved[key] = value
    return resolved

"""Selection and ref-target resolution helpers for EditorSession."""
from __future__ import annotations

from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID


def resolve_ref_type_to_type_ids(
    *,
    iter_types: list,
    token: str,
    iter_links: list | None = None,
    iter_link_types: list | None = None,
) -> set[str]:
    """Resolve one normalized ref token to matching type ids + descendants.

    Types are matched by id or name only.  ``instance_category`` and
    ``type_kind`` props are organizational hints for instances and are NOT
    used as type-query tokens.
    """
    id_matches: set[str] = set()
    name_matches: set[str] = set()

    for type_node in iter_types:
        type_id = str(type_node.id)
        if type_id.casefold() == token:
            id_matches.add(type_id)

        type_name = type_node.name.strip().casefold()
        if type_name and type_name == token:
            name_matches.add(type_id)

    base_type_ids = id_matches or name_matches

    if not base_type_ids:
        return set()

    all_type_ids = {str(type_node.id) for type_node in iter_types}
    children_of: dict[str, set[str]] = {}

    extends_type_ids: set[str] = {EXTENDS_LINK_TYPE_ID}
    if iter_link_types is not None:
        for link_type in iter_link_types:
            if str(getattr(link_type, "name", "")).strip().casefold() == "extends":
                extends_type_ids.add(str(getattr(link_type, "id", "")))

    if iter_links is not None:
        for link in iter_links:
            if str(getattr(link, "link_type_id", "")) not in extends_type_ids:
                continue
            child_id = str(getattr(link, "source_node_id", ""))
            parent_id = str(getattr(link, "target_node_id", ""))
            if child_id in all_type_ids and parent_id in all_type_ids and child_id != parent_id:
                children_of.setdefault(parent_id, set()).add(child_id)

    # Legacy compatibility: some repositories encoded type inheritance via
    # type-node ``type_id`` instead of explicit extends edges.
    for type_node in iter_types:
        child_id = str(type_node.id)
        parent_node_id = getattr(type_node, "type_id", None)
        if parent_node_id is None:
            continue
        parent_id = str(parent_node_id)
        if parent_id in all_type_ids and parent_id != child_id:
            children_of.setdefault(parent_id, set()).add(child_id)

    resolved: set[str] = set(base_type_ids)
    frontier = list(base_type_ids)
    while frontier:
        parent_id = frontier.pop()
        for child_id in children_of.get(parent_id, set()):
            if child_id in resolved:
                continue
            resolved.add(child_id)
            frontier.append(child_id)
    return resolved

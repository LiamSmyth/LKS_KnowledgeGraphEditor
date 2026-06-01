"""Hierarchy-aware storage path computation for the knowledge repository."""
from __future__ import annotations

from pathlib import Path

from lks_utils.core.file_io import safe_filename
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.type import as_type, is_type

_MAX_DEPTH = 32  # guard against cycles


def compute_type_ancestry(
    node_id: str,
    links: list[LinkInstance],
    nodes: dict[str, Node],
) -> list[str]:
    """Traverse *extends* edges upward and return ancestor names, outermost first.

    Example: Cat -extends-> Mammalia -extends-> Animal
    Returns: ["animal", "mammalia"]   (Cat itself is not included)
    """
    chain: list[str] = []
    current_id = node_id
    for _ in range(_MAX_DEPTH):
        parent_id = _find_extends_target(current_id, links)
        if parent_id is None:
            break
        parent_node = nodes.get(parent_id)
        if parent_node is None:
            break
        chain.append(parent_node.name)
        current_id = parent_id
    chain.reverse()
    return chain


def compute_instance_ancestry(
    node_id: str,
    links: list[LinkInstance],
    nodes: dict[str, Node],
) -> list[str]:
    """Resolve full instance lineage: type-chain then parent-instance chain.

    Returns names ordered outermost-first and excludes *node_id* itself.
    """
    parent_instance_names: list[str] = []
    current_id = node_id

    for _ in range(_MAX_DEPTH):
        parent_id = _find_instance_parent_target(
            current_id, links=links, nodes=nodes)
        if parent_id is None:
            break
        parent_node = nodes.get(parent_id)
        if parent_node is None:
            break
        if is_type(parent_node):
            return (
                compute_type_ancestry(parent_id, links=links, nodes=nodes)
                + [parent_node.name]
                + list(reversed(parent_instance_names))
            )
        parent_instance_names.append(parent_node.name)
        current_id = parent_id

    return list(reversed(parent_instance_names))


def compute_type_lineage(
    node_id: str,
    links: list[LinkInstance],
    nodes: dict[str, Node],
) -> list[str]:
    """Return full type lineage from root ancestor to the node itself."""
    node = nodes.get(node_id)
    if node is None:
        return []
    return compute_type_ancestry(node_id, links=links, nodes=nodes) + [node.name]


def storage_folder_for_node(
    node: Node,
    links: list[LinkInstance],
    nodes: dict[str, Node],
) -> Path:
    """Return the folder path (relative to repo root) where *node* should be saved.

    Types:     nodes/types/<type_ancestry>/
    Instances: nodes/instances/<type+instance_lineage>/<category>/
    """
    if is_type(node):
        lineage = compute_type_ancestry(str(node.id), links=links, nodes=nodes)
        folder = Path("nodes") / "types"
        if lineage:
            folder = folder / Path(*[safe_filename(n) for n in lineage])
        return folder

    ancestry = compute_instance_ancestry(
        str(node.id), links=links, nodes=nodes)
    folder = Path("nodes") / "instances"
    if ancestry:
        folder = folder / Path(*[safe_filename(n) for n in ancestry])
    if node.category.strip():
        folder = folder / safe_filename(node.category)
    return folder


def storage_folder_for_link_type(link_type: LinkType) -> Path:
    """Return the folder path for one link-type record.

    Link types are flat by capability class: system vs user.
    """
    if link_type.is_system:
        return Path("link_types") / "system"
    return Path("link_types") / "user"


def unique_link_type_relpath(
    link_type: LinkType,
    used_relative_paths: set[str],
) -> Path:
    """Return a unique, deterministic relative path for one link type."""
    folder = storage_folder_for_link_type(link_type)
    base_name = safe_filename(link_type.name)
    candidate = folder / f"{base_name}.json"
    suffix = 2
    while candidate.as_posix() in used_relative_paths:
        candidate = folder / f"{base_name}_{suffix}.json"
        suffix += 1
    used_relative_paths.add(candidate.as_posix())
    return candidate


def link_instance_relpath(
    link: LinkInstance,
    *,
    source_node: Node | None,
    target_node: Node | None,
    link_type: LinkType | None,
) -> Path:
    """Return deterministic relative path for one link instance."""
    folder = storage_folder_for_link_instance(
        source_node=source_node,
        link_type=link_type,
    )
    filename = link_instance_filename(
        link=link,
        source_node=source_node,
        target_node=target_node,
        link_type=link_type,
    )
    return folder / filename


def storage_folder_for_link_instance(
    *,
    source_node: Node | None,
    link_type: LinkType | None,
) -> Path:
    """Return link-instance folder `<system_type>/<link_type>/<category>`."""
    system_type = "types" if source_node is not None and source_node.category == "_type" else "instances"
    link_type_name = safe_filename(
        link_type.name if link_type is not None else "unknown_link_type")
    category = safe_filename(_link_source_category(source_node))
    return Path("links") / system_type / link_type_name / category


def link_instance_filename(
    *,
    link: LinkInstance,
    source_node: Node | None,
    target_node: Node | None,
    link_type: LinkType | None,
) -> str:
    """Return deterministic link filename with readable names plus link ID."""
    link_type_name = safe_filename(
        link_type.name if link_type is not None else "unknown_link_type")
    source_name = safe_filename(
        source_node.name if source_node is not None else link.source_node_id)
    target_name = safe_filename(
        target_node.name if target_node is not None else link.target_node_id)
    return f"{link_type_name}_{source_name}_to_{target_name}_{link.id}.json"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _find_extends_target(source_id: str, links: list[LinkInstance]) -> str | None:
    for link in links:
        if link.link_type_id == EXTENDS_LINK_TYPE_ID and link.source_node_id == source_id:
            return link.target_node_id
    return None


def _find_instance_of_target(source_id: str, links: list[LinkInstance]) -> str | None:
    for link in links:
        if link.link_type_id == INSTANCE_OF_LINK_TYPE_ID and link.source_node_id == source_id:
            return link.target_node_id
    return None


def _find_instance_parent_target(
    source_id: str,
    *,
    links: list[LinkInstance],
    nodes: dict[str, Node],
) -> str | None:
    parent_id = _find_instance_of_target(source_id, links)
    if parent_id is not None:
        return parent_id
    source_node = nodes.get(source_id)
    if source_node is None or source_node.type_id is None:
        return None
    return str(source_node.type_id)


def _normalize_constraint_scope(constraint: str | None) -> str:
    if constraint is None or not constraint.strip():
        return "user"
    normalized = constraint.strip().casefold()
    if normalized in {"any", "instance"}:
        return "user"
    if normalized == "type":
        return "types"
    return safe_filename(constraint.strip())


def _link_source_category(source_node: Node | None) -> str:
    if source_node is None:
        return "unknown"
    if source_node.category == "_type":
        type_view = as_type(source_node)
        if type_view.category.strip():
            return type_view.category.strip()
        return "type"
    return source_node.category or "unknown"


__all__ = [
    "compute_type_ancestry",
    "compute_type_lineage",
    "compute_instance_ancestry",
    "link_instance_filename",
    "link_instance_relpath",
    "storage_folder_for_node",
    "storage_folder_for_link_instance",
    "storage_folder_for_link_type",
    "unique_link_type_relpath",
]

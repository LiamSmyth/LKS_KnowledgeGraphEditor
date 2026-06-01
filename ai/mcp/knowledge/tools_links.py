"""Link and link-type tools for knowledge MCP."""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import (
    _build_io,
    resolve_existing_repo,
    result_envelope,
)
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
from lks_utils.knowledge.repository import Repository


def _resolve_type_node(
    io: Any,
    *,
    node_id: str | None = None,
    node_name: str | None = None,
) -> Any:
    node = io.resolve_node_identity(node_id=node_id, node_name=node_name)
    if node.category != "_type":
        raise ValueError(f"Node {node.name!r} is not a type node.")
    return node


def list_links_compact_impl(
    path: str,
    *,
    link_type_id: str | None = None,
    source_node_id: str | None = None,
    target_node_id: str | None = None,
    include_names: bool = True,
) -> list[dict[str, Any]]:
    io = _build_io(path)
    links = io.list_links()
    if link_type_id is not None:
        links = [link for link in links if link.link_type_id == link_type_id]
    if source_node_id is not None:
        links = [link for link in links if link.source_node_id == source_node_id]
    if target_node_id is not None:
        links = [link for link in links if link.target_node_id == target_node_id]

    if not include_names:
        return [
            {
                "id": link.id,
                "link_type_id": link.link_type_id,
                "source_node_id": link.source_node_id,
                "target_node_id": link.target_node_id,
            }
            for link in links
        ]

    nodes = {str(node.id): node for node in io.list_nodes()}
    link_types = {
        link_type.id: link_type for link_type in io.list_link_types()}
    results: list[dict[str, Any]] = []
    for link in links:
        source_node = nodes.get(link.source_node_id)
        target_node = nodes.get(link.target_node_id)
        link_type = link_types.get(link.link_type_id)
        results.append(
            {
                "id": link.id,
                "source": source_node.name if source_node else link.source_node_id,
                "predicate": link_type.name if link_type else link.link_type_id,
                "target": target_node.name if target_node else link.target_node_id,
            }
        )
    return results


def delete_link_impl(path: str, link_id: str) -> dict[str, Any]:
    """Delete one link by id via KnowledgeIO, preserving slot_ref cleanup semantics."""
    io = _build_io(path)
    link = io.find_link(link_id)
    if link is None:
        return {
            "status": "ok",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": None,
            "save_error": None,
            "deleted": False,
        }

    result = io.delete_link(link)
    out = result_envelope(result)
    out["deleted"] = result.status == "ok"
    return out


def delete_link_type_impl(path: str, link_type_id: str) -> dict[str, Any]:
    """Delete one link type and cascade-delete its instances via KnowledgeIO."""
    io = _build_io(path)
    if io.find_link_type(link_type_id) is None:
        return {
            "status": "ok",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": None,
            "save_error": None,
            "deleted": False,
            "deleted_link_ids": [],
        }

    deleted_link_ids = [
        link.id
        for link in io.list_links()
        if str(link.link_type_id) == link_type_id
    ]
    result = io.delete_link_type_cascade(link_type_id)
    return {
        **result_envelope(result),
        "deleted": result.status == "ok",
        "deleted_link_ids": deleted_link_ids,
    }


def set_extends_parent_impl(
    path: str,
    *,
    child_node_id: str | None = None,
    child_node_name: str | None = None,
    parent_node_id: str | None = None,
    parent_node_name: str | None = None,
) -> dict[str, Any]:
    """Set or replace the single system `extends` parent for one type node."""
    io = _build_io(path)
    child_node = _resolve_type_node(
        io, node_id=child_node_id, node_name=child_node_name)
    parent_node = _resolve_type_node(
        io, node_id=parent_node_id, node_name=parent_node_name)

    existing_links = [
        link
        for link in io.list_links()
        if link.link_type_id == EXTENDS_LINK_TYPE_ID
        and link.source_node_id == str(child_node.id)
    ]
    matching_link = next(
        (
            link
            for link in existing_links
            if link.target_node_id == str(parent_node.id)
        ),
        None,
    )
    if len(existing_links) == 1 and matching_link is not None:
        return {
            "status": "ok",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": None,
            "save_error": None,
            "created": False,
            "deleted_link_ids": [],
            "link": matching_link.model_dump(),
        }

    created_link = LinkInstance(
        link_type_id=EXTENDS_LINK_TYPE_ID,
        source_node_id=str(child_node.id),
        target_node_id=str(parent_node.id),
    )
    deleted_link_ids = [link.id for link in existing_links]

    def mutator(repo: Any) -> set[str]:
        touched: set[str] = {str(child_node.id), str(parent_node.id)}
        for link in list(repo.list_links()):
            if (
                link.link_type_id == EXTENDS_LINK_TYPE_ID
                and link.source_node_id == str(child_node.id)
            ):
                repo.delete_link(link.id)
                touched.add(link.id)
                touched.add(link.target_node_id)
        repo.upsert_link(created_link)
        touched.add(created_link.id)
        return touched

    result = io.apply_op(mutator)
    persisted = io.find_link(created_link.id)
    return {
        **result_envelope(result),
        "created": result.status == "ok",
        "deleted_link_ids": deleted_link_ids,
        "link": persisted.model_dump() if persisted is not None else None,
    }


def clear_extends_parent_impl(
    path: str,
    *,
    child_node_id: str | None = None,
    child_node_name: str | None = None,
) -> dict[str, Any]:
    """Remove all system `extends` parent links for one type node."""
    io = _build_io(path)
    child_node = _resolve_type_node(
        io, node_id=child_node_id, node_name=child_node_name)

    existing_links = [
        link
        for link in io.list_links()
        if link.link_type_id == EXTENDS_LINK_TYPE_ID
        and link.source_node_id == str(child_node.id)
    ]
    if not existing_links:
        return {
            "status": "ok",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": None,
            "save_error": None,
            "deleted": False,
            "deleted_link_ids": [],
        }

    deleted_link_ids = [link.id for link in existing_links]

    def mutator(repo: Any) -> set[str]:
        touched: set[str] = {str(child_node.id)}
        for link in list(repo.list_links()):
            if (
                link.link_type_id == EXTENDS_LINK_TYPE_ID
                and link.source_node_id == str(child_node.id)
            ):
                repo.delete_link(link.id)
                touched.add(link.id)
                touched.add(link.target_node_id)
        return touched

    result = io.apply_op(mutator)
    return {
        **result_envelope(result),
        "deleted": result.status == "ok",
        "deleted_link_ids": deleted_link_ids,
    }


def set_instance_of_type_impl(
    path: str,
    *,
    instance_node_id: str | None = None,
    instance_node_name: str | None = None,
    type_node_id: str | None = None,
    type_node_name: str | None = None,
) -> dict[str, Any]:
    """Set or replace the system ``instance_of`` type for one instance node.

    Also sets ``node.type_id`` on the instance so the resolver's fast-path
    (``type_id`` field) stays consistent with the explicit link.
    """
    io = _build_io(path)
    instance_node = io.resolve_node_identity(
        node_id=instance_node_id, node_name=instance_node_name)
    type_node = _resolve_type_node(
        io, node_id=type_node_id, node_name=type_node_name)

    existing_links = [
        link
        for link in io.list_links()
        if link.link_type_id == INSTANCE_OF_LINK_TYPE_ID
        and link.source_node_id == str(instance_node.id)
    ]
    matching_link = next(
        (
            link
            for link in existing_links
            if link.target_node_id == str(type_node.id)
        ),
        None,
    )
    # Already wired and type_id in sync — nothing to do.
    if len(existing_links) == 1 and matching_link is not None:
        if str(instance_node.type_id) == str(type_node.id):
            return {
                "status": "ok",
                "touched_ids": [],
                "validated_ids": [],
                "issues": [],
                "error_message": None,
                "save_error": None,
                "created": False,
                "deleted_link_ids": [],
                "link": matching_link.model_dump(),
            }

    created_link = LinkInstance(
        link_type_id=INSTANCE_OF_LINK_TYPE_ID,
        source_node_id=str(instance_node.id),
        target_node_id=str(type_node.id),
    )
    deleted_link_ids = [link.id for link in existing_links]

    def mutator(repo: Any) -> set[str]:
        touched: set[str] = {str(instance_node.id), str(type_node.id)}
        # Remove any existing instance_of links from this instance.
        for link in list(repo.list_links()):
            if (
                link.link_type_id == INSTANCE_OF_LINK_TYPE_ID
                and link.source_node_id == str(instance_node.id)
            ):
                repo.delete_link(link.id)
                touched.add(link.id)
                touched.add(link.target_node_id)
        repo.upsert_link(created_link)
        touched.add(created_link.id)
        # Sync node.type_id to keep resolver fast-path consistent.
        node = repo.get(str(instance_node.id))
        repo.upsert(node.model_copy(
            update={"type_id": NodeId.from_str(
                str(type_node.id)), "rev": node.rev + 1}
        ))
        return touched

    result = io.apply_op(mutator)
    persisted = io.find_link(created_link.id)
    return {
        **result_envelope(result),
        "created": result.status == "ok",
        "deleted_link_ids": deleted_link_ids,
        "link": persisted.model_dump() if persisted is not None else None,
    }


def clear_instance_of_type_impl(
    path: str,
    *,
    instance_node_id: str | None = None,
    instance_node_name: str | None = None,
) -> dict[str, Any]:
    """Remove all system ``instance_of`` links from one instance node.

    Also clears ``node.type_id`` so the resolver fast-path stays consistent.
    """
    io = _build_io(path)
    instance_node = io.resolve_node_identity(
        node_id=instance_node_id, node_name=instance_node_name)

    existing_links = [
        link
        for link in io.list_links()
        if link.link_type_id == INSTANCE_OF_LINK_TYPE_ID
        and link.source_node_id == str(instance_node.id)
    ]
    if not existing_links and instance_node.type_id is None:
        return {
            "status": "ok",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": None,
            "save_error": None,
            "deleted": False,
            "deleted_link_ids": [],
        }

    deleted_link_ids = [link.id for link in existing_links]

    def mutator(repo: Any) -> set[str]:
        touched: set[str] = {str(instance_node.id)}
        for link in list(repo.list_links()):
            if (
                link.link_type_id == INSTANCE_OF_LINK_TYPE_ID
                and link.source_node_id == str(instance_node.id)
            ):
                repo.delete_link(link.id)
                touched.add(link.id)
                touched.add(link.target_node_id)
        # Clear node.type_id so the resolver fast-path stays consistent.
        node = repo.get(str(instance_node.id))
        if node.type_id is not None:
            repo.upsert(node.model_copy(
                update={"type_id": None, "rev": node.rev + 1}
            ))
        return touched

    result = io.apply_op(mutator)
    return {
        **result_envelope(result),
        "deleted": result.status == "ok",
        "deleted_link_ids": deleted_link_ids,
    }


def upsert_link_impl(path: str, link: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace one link from a typed object with pre-write guard."""
    validated = LinkInstance.model_validate(link)

    # Fast-fail structural guard before constructing KnowledgeIO. This keeps
    # rejected writes from touching apply_op during IO bootstrap.
    repo = Repository.load(resolve_existing_repo(path))
    preflight_violations: list[dict[str, str]] = []
    if repo.find_link_type(str(validated.link_type_id)) is None:
        preflight_violations.append(
            {
                "code": "link_type_not_found",
                "message": f"Link type not found: {validated.link_type_id}",
            }
        )
    if repo.find_node(str(validated.source_node_id)) is None:
        preflight_violations.append(
            {
                "code": "source_node_not_found",
                "message": f"Source node not found: {validated.source_node_id}",
            }
        )
    if repo.find_node(str(validated.target_node_id)) is None:
        preflight_violations.append(
            {
                "code": "target_node_not_found",
                "message": f"Target node not found: {validated.target_node_id}",
            }
        )
    if preflight_violations:
        return {
            "status": "rejected",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": None,
            "save_error": None,
            "violations": preflight_violations,
            "link": None,
        }

    io = _build_io(path)
    violations = io.validate_upsert_link(validated)
    if violations:
        return {
            "status": "rejected",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": None,
            "save_error": None,
            "violations": [issue.model_dump() for issue in violations],
            "link": None,
        }

    result = io.upsert_link(validated)
    persisted = io.find_link(validated.id)
    return {
        **result_envelope(result),
        "link": persisted.model_dump() if persisted is not None else None,
    }


def upsert_link_type_impl(path: str, link_type: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace one link type from a typed object."""
    validated = LinkType.model_validate(link_type)
    io = _build_io(path)
    violations = io.validate_upsert_link_type(validated)
    if violations:
        return {
            "status": "rejected",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": None,
            "save_error": None,
            "violations": [issue.model_dump() for issue in violations],
            "link_type": None,
        }
    result = io.upsert_link_type(validated)
    persisted = io.find_link_type(validated.id)
    return {
        **result_envelope(result),
        "link_type": persisted.model_dump() if persisted is not None else None,
    }


def register_link_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_link_types(path: str, include_system: bool = True) -> list[dict[str, Any]]:
        """[READ-ONLY] List link-type summaries."""
        io = _build_io(path)
        link_types = io.list_link_types()
        if not include_system:
            link_types = [
                link_type for link_type in link_types if not link_type.is_system]
        return [
            {
                "id": link_type.id,
                "name": link_type.name,
                "inverse_name": link_type.inverse_name,
                "cardinality": link_type.cardinality,
                "is_system": link_type.is_system,
            }
            for link_type in link_types
        ]

    @mcp.tool()
    def get_link_type(path: str, link_type_id: str) -> dict[str, Any]:
        """[READ-ONLY] Return a single link type as a JSON-ready dict."""
        io = _build_io(path)
        return io.get_link_type(link_type_id).model_dump()

    @mcp.tool()
    def upsert_link_type(path: str, link_type: dict[str, Any]) -> dict[str, Any]:
        """[MUTATES] Insert or replace one link type from a typed object."""
        return upsert_link_type_impl(path, link_type)

    @mcp.tool()
    def ensure_link_type(
        path: str,
        name: str,
        inverse_name: str = "",
        description: str = "",
        source_type_constraint: str | None = None,
        target_type_constraint: str | None = None,
        cardinality: Literal["one", "many"] = "many",
        is_system: bool = False,
    ) -> dict[str, Any]:
        """[MUTATES] Ensure a link type exists by name and upsert it."""
        io = _build_io(path)
        matches = [link_type for link_type in io.list_link_types()
                   if link_type.name == name]
        if len(matches) > 1:
            ids = ", ".join(link_type.id for link_type in matches)
            raise ValueError(
                f"Ambiguous link type name {name!r}; matches multiple IDs: {ids}.")
        existing = matches[0] if matches else None

        payload: dict[str, Any] = {
            "name": name,
            "inverse_name": inverse_name,
            "description": description,
            "source_type_constraint": source_type_constraint,
            "target_type_constraint": target_type_constraint,
            "cardinality": cardinality,
            "is_system": is_system,
        }
        created = existing is None
        if existing is not None:
            payload["id"] = existing.id
        validated = LinkType.model_validate(payload)
        result = io.upsert_link_type(validated)
        persisted = io.find_link_type(validated.id)
        return {
            **result_envelope(result),
            "created": created,
            "link_type": persisted.model_dump() if persisted is not None else None,
        }

    @mcp.tool()
    def list_links(
        path: str,
        link_type_id: str | None = None,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] List link summaries with optional filters."""
        return list_links_compact_impl(
            path,
            link_type_id=link_type_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            include_names=False,
        )

    @mcp.tool()
    def list_links_compact(
        path: str,
        link_type_id: str | None = None,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
        include_names: bool = True,
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] List links with optional human-friendly names and compact fields."""
        return list_links_compact_impl(
            path,
            link_type_id=link_type_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            include_names=include_names,
        )

    @mcp.tool()
    def get_link(path: str, link_id: str) -> dict[str, Any]:
        """[READ-ONLY] Return a single link as a JSON-ready dict."""
        io = _build_io(path)
        link = io.find_link(link_id)
        if link is None:
            raise KeyError(f"Link not found: {link_id}")
        return link.model_dump()

    @mcp.tool()
    def upsert_link(path: str, link: dict[str, Any]) -> dict[str, Any]:
        """[MUTATES] Insert or replace one link from a typed object."""
        return upsert_link_impl(path, link)

    @mcp.tool()
    def ensure_link(
        path: str,
        source_node_id: str | None = None,
        source_node_name: str | None = None,
        target_node_id: str | None = None,
        target_node_name: str | None = None,
        link_type_id: str | None = None,
        link_type_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Ensure a link exists by semantic tuple, resolving names to IDs."""
        io = _build_io(path)
        source_node = io.resolve_node_identity(
            node_id=source_node_id, node_name=source_node_name)
        target_node = io.resolve_node_identity(
            node_id=target_node_id, node_name=target_node_name)
        link_type = io.resolve_link_type_identity(
            link_type_id=link_type_id,
            link_type_name=link_type_name,
        )
        desired_metadata = metadata or {}

        for existing in io.list_links():
            if (
                existing.link_type_id == link_type.id
                and existing.source_node_id == str(source_node.id)
                and existing.target_node_id == str(target_node.id)
                and existing.metadata == desired_metadata
            ):
                return {
                    "status": "ok",
                    "touched_ids": [],
                    "validated_ids": [],
                    "issues": [],
                    "error_message": None,
                    "save_error": None,
                    "created": False,
                    "link": existing.model_dump(),
                }

        payload = {
            "link_type_id": link_type.id,
            "source_node_id": str(source_node.id),
            "target_node_id": str(target_node.id),
            "metadata": desired_metadata,
        }
        validated = LinkInstance.model_validate(payload)
        result = io.upsert_link(validated)
        persisted = io.find_link(validated.id)
        return {
            **result_envelope(result),
            "created": True,
            "link": persisted.model_dump() if persisted is not None else None,
        }

    @mcp.tool()
    def delete_link(path: str, link_id: str) -> dict[str, Any]:
        """[MUTATES] Delete one link by id.

        Uses KnowledgeIO.delete_link so slot_ref deletion cascades remain consistent.
        """
        return delete_link_impl(path, link_id)

    @mcp.tool()
    def set_extends_parent(
        path: str,
        child_node_id: str | None = None,
        child_node_name: str | None = None,
        parent_node_id: str | None = None,
        parent_node_name: str | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Set or replace the system `extends` parent for one type node."""
        return set_extends_parent_impl(
            path,
            child_node_id=child_node_id,
            child_node_name=child_node_name,
            parent_node_id=parent_node_id,
            parent_node_name=parent_node_name,
        )

    @mcp.tool()
    def clear_extends_parent(
        path: str,
        child_node_id: str | None = None,
        child_node_name: str | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Remove all system `extends` parents from one type node."""
        return clear_extends_parent_impl(
            path,
            child_node_id=child_node_id,
            child_node_name=child_node_name,
        )

    @mcp.tool()
    def set_instance_of_type(
        path: str,
        instance_node_id: str | None = None,
        instance_node_name: str | None = None,
        type_node_id: str | None = None,
        type_node_name: str | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Set or replace the system `instance_of` type for one instance node.

        Also syncs ``node.type_id`` for resolver fast-path consistency.
        This is the only correct way to wire an instance to a type via an explicit link.
        """
        return set_instance_of_type_impl(
            path,
            instance_node_id=instance_node_id,
            instance_node_name=instance_node_name,
            type_node_id=type_node_id,
            type_node_name=type_node_name,
        )

    @mcp.tool()
    def clear_instance_of_type(
        path: str,
        instance_node_id: str | None = None,
        instance_node_name: str | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Remove all system `instance_of` links from one instance node.

        Also clears ``node.type_id`` for resolver fast-path consistency.
        """
        return clear_instance_of_type_impl(
            path,
            instance_node_id=instance_node_id,
            instance_node_name=instance_node_name,
        )

    @mcp.tool()
    def delete_link_type(path: str, link_type_id: str) -> dict[str, Any]:
        """[MUTATES] Delete one link type and cascade-delete its instances."""
        return delete_link_type_impl(path, link_type_id)

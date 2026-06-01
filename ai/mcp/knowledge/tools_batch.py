"""Semantic batch planning and apply tools for knowledge MCP."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import _build_io, result_envelope
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.models.node import Node


def _find_node_by_name(io: Any, name: str, category: str | None = None) -> Node | None:
    matches = [
        node
        for node in io.list_nodes()
        if node.name == name and (category is None or node.category == category)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous node name {name!r}; multiple nodes found.")
    return matches[0]


def _find_link_type_by_name(io: Any, name: str) -> LinkType | None:
    matches = [link_type for link_type in io.list_link_types()
               if link_type.name == name]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous link type name {name!r}; multiple link types found.")
    return matches[0]


def apply_batch_mutation_impl(
    path: str,
    node_ensures: list[dict[str, Any]] | None = None,
    link_type_ensures: list[dict[str, Any]] | None = None,
    link_ensures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply semantic ensure operations in dependency-safe order."""
    node_ensures = node_ensures or []
    link_type_ensures = link_type_ensures or []
    link_ensures = link_ensures or []
    io = _build_io(path)

    results: dict[str, list[dict[str, Any]]] = {
        "nodes": [],
        "link_types": [],
        "links": [],
    }
    touched_ids: set[str] = set()
    statuses: list[str] = []

    for spec in node_ensures:
        name = str(spec.get("name", "")).strip()
        category = str(spec.get("category", "")).strip()
        if not name or not category:
            results["nodes"].append(
                {"name": name, "category": category,
                    "status": "skip_missing_required"}
            )
            continue
        existing = _find_node_by_name(io, name=name, category=category)
        payload = {
            "category": category,
            "name": name,
            "description": str(spec.get("description", "")),
            "props": spec.get("props") or {},
            "source_repo_id": io.source_repo_id,
        }
        type_id = spec.get("type_id")
        type_name = spec.get("type_name")
        if type_name:
            type_node = _find_node_by_name(
                io, name=str(type_name), category="_type")
            if type_node is None:
                raise KeyError(f"Type not found by name: {type_name}")
            payload["type_id"] = str(type_node.id)
        elif type_id:
            payload["type_id"] = str(type_id)
        if existing is not None:
            payload["id"] = str(existing.id)
            if "type_id" not in payload and existing.type_id is not None:
                payload["type_id"] = str(existing.type_id)

        validated = Node.model_validate(payload)
        op = io.upsert_node(validated)
        touched_ids.update(op.touched_ids)
        statuses.append(op.status)
        results["nodes"].append(
            {
                "name": name,
                "category": category,
                "status": "created" if existing is None else "updated",
                "id": str(validated.id),
            }
        )

    for spec in link_type_ensures:
        name = str(spec.get("name", "")).strip()
        if not name:
            results["link_types"].append(
                {"name": name, "status": "skip_missing_required"})
            continue
        existing = _find_link_type_by_name(io, name=name)
        payload = {
            "name": name,
            "inverse_name": str(spec.get("inverse_name", "")),
            "description": str(spec.get("description", "")),
            "source_type_constraint": spec.get("source_type_constraint"),
            "target_type_constraint": spec.get("target_type_constraint"),
            "cardinality": spec.get("cardinality", "many"),
            "is_system": bool(spec.get("is_system", False)),
        }
        if existing is not None:
            payload["id"] = existing.id
        validated = LinkType.model_validate(payload)
        op = io.upsert_link_type(validated)
        touched_ids.update(op.touched_ids)
        statuses.append(op.status)
        results["link_types"].append(
            {
                "name": name,
                "status": "created" if existing is None else "updated",
                "id": validated.id,
            }
        )

    for spec in link_ensures:
        source_node = _find_node_by_name(
            io, name=str(spec.get("source_node_name", "")))
        target_node = _find_node_by_name(
            io, name=str(spec.get("target_node_name", "")))
        link_type = _find_link_type_by_name(
            io, name=str(spec.get("link_type_name", "")))
        if source_node is None or target_node is None or link_type is None:
            results["links"].append(
                {"status": "blocked_missing_dependency", "spec": spec})
            continue
        metadata = spec.get("metadata") or {}
        existing_match = next(
            (
                link
                for link in io.list_links()
                if link.link_type_id == link_type.id
                and link.source_node_id == str(source_node.id)
                and link.target_node_id == str(target_node.id)
                and link.metadata == metadata
            ),
            None,
        )
        if existing_match is not None:
            results["links"].append(
                {"status": "noop", "id": existing_match.id})
            continue

        validated = LinkInstance.model_validate(
            {
                "link_type_id": link_type.id,
                "source_node_id": str(source_node.id),
                "target_node_id": str(target_node.id),
                "metadata": metadata,
            }
        )
        op = io.upsert_link(validated)
        touched_ids.update(op.touched_ids)
        statuses.append(op.status)
        results["links"].append({"status": "created", "id": validated.id})

    status = "ok" if all(item == "ok" for item in statuses) else "error"
    return {
        "status": status,
        "touched_ids": sorted(touched_ids),
        "validated_ids": [],
        "issues": [],
        "error_message": None if status == "ok" else "One or more operations failed.",
        "save_error": None,
        **results,
    }


def register_batch_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def batch_upsert_nodes(path: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        """[MUTATES] Insert or replace multiple nodes from typed objects."""
        io = _build_io(path)
        validated = [Node.model_validate(item) for item in nodes]
        result = io.upsert_nodes(validated)
        return {
            **result_envelope(result),
            "count": len(validated),
            "node_ids": [str(node.id) for node in validated],
        }

    @mcp.tool()
    def batch_upsert_links(path: str, links: list[dict[str, Any]]) -> dict[str, Any]:
        """[MUTATES] Insert or replace multiple links from typed objects."""
        io = _build_io(path)
        validated = [LinkInstance.model_validate(item) for item in links]
        result = io.upsert_links(validated)
        return {
            **result_envelope(result),
            "count": len(validated),
            "link_ids": [link.id for link in validated],
        }

    @mcp.tool()
    def plan_batch_mutation(
        path: str,
        node_ensures: list[dict[str, Any]] | None = None,
        link_type_ensures: list[dict[str, Any]] | None = None,
        link_ensures: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """[READ-ONLY] Plan semantic ensure operations and report dry-run actions."""
        io = _build_io(path)
        node_ensures = node_ensures or []
        link_type_ensures = link_type_ensures or []
        link_ensures = link_ensures or []

        plan: dict[str, Any] = {
            "nodes": [],
            "link_types": [],
            "links": [],
            "would_mutate": False,
        }

        for spec in node_ensures:
            name = str(spec.get("name", "")).strip()
            category = str(spec.get("category", "")).strip()
            if not name or not category:
                plan["nodes"].append(
                    {"name": name, "category": category,
                        "action": "skip_missing_required"}
                )
                continue
            existing = _find_node_by_name(io, name=name, category=category)
            action = "noop" if existing else "create"
            plan["nodes"].append(
                {
                    "name": name,
                    "category": category,
                    "action": action,
                    "existing_id": str(existing.id) if existing else None,
                }
            )
            plan["would_mutate"] = plan["would_mutate"] or (action != "noop")

        for spec in link_type_ensures:
            name = str(spec.get("name", "")).strip()
            if not name:
                plan["link_types"].append(
                    {"name": name, "action": "skip_missing_required"})
                continue
            existing = _find_link_type_by_name(io, name=name)
            action = "noop" if existing else "create"
            plan["link_types"].append(
                {
                    "name": name,
                    "action": action,
                    "existing_id": existing.id if existing else None,
                }
            )
            plan["would_mutate"] = plan["would_mutate"] or (action != "noop")

        for spec in link_ensures:
            source_name = str(spec.get("source_node_name", "")).strip()
            target_name = str(spec.get("target_node_name", "")).strip()
            link_type_name = str(spec.get("link_type_name", "")).strip()
            if not source_name or not target_name or not link_type_name:
                plan["links"].append(
                    {
                        "source_node_name": source_name,
                        "target_node_name": target_name,
                        "link_type_name": link_type_name,
                        "action": "skip_missing_required",
                    }
                )
                continue
            source = _find_node_by_name(io, name=source_name)
            target = _find_node_by_name(io, name=target_name)
            link_type = _find_link_type_by_name(io, name=link_type_name)
            if source is None or target is None or link_type is None:
                plan["links"].append(
                    {
                        "source_node_name": source_name,
                        "target_node_name": target_name,
                        "link_type_name": link_type_name,
                        "action": "blocked_missing_dependency",
                    }
                )
                continue
            metadata = spec.get("metadata") or {}
            match = any(
                existing.link_type_id == link_type.id
                and existing.source_node_id == str(source.id)
                and existing.target_node_id == str(target.id)
                and existing.metadata == metadata
                for existing in io.list_links()
            )
            action = "noop" if match else "create"
            plan["links"].append(
                {
                    "source_node_name": source_name,
                    "target_node_name": target_name,
                    "link_type_name": link_type_name,
                    "action": action,
                }
            )
            plan["would_mutate"] = plan["would_mutate"] or (action != "noop")

        return plan

    @mcp.tool()
    def apply_batch_mutation(
        path: str,
        node_ensures: list[dict[str, Any]] | None = None,
        link_type_ensures: list[dict[str, Any]] | None = None,
        link_ensures: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Apply semantic ensure operations in dependency-safe order."""
        return apply_batch_mutation_impl(
            path=path,
            node_ensures=node_ensures,
            link_type_ensures=link_type_ensures,
            link_ensures=link_ensures,
        )

    # ------------------------------------------------------------------
    # WO2: Bulk property mutation
    # ------------------------------------------------------------------

    @mcp.tool()
    def bulk_set_prop(
        path: str,
        node_ids: list[str],
        prop_key: str,
        value: Any,
    ) -> dict[str, Any]:
        """[MUTATES] Apply one prop key/value to multiple nodes.

        Failed nodes do **not** abort the batch — each node is handled
        independently.

        Returns a dict with keys:
        - ``ok_count``: number of nodes updated successfully.
        - ``error_count``: number of nodes that failed.
        - ``results``: per-node list of ``{node_id, status, error}``.
        """
        io = _build_io(path)
        bulk_result = io.bulk_set_prop(node_ids, prop_key, value)
        return bulk_result.to_dict()

"""Node-focused tools for knowledge MCP."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import (
    _build_io,
    node_compact,
    node_summary,
    result_envelope,
)
from lks_utils.knowledge.models.node import Node


def register_node_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_nodes(path: str, category: str | None = None) -> list[dict[str, Any]]:
        """[READ-ONLY] List node summaries."""
        io = _build_io(path)
        nodes = io.list_nodes()
        if category is not None:
            nodes = [node for node in nodes if node.category == category]
        return [node_summary(node) for node in nodes]

    @mcp.tool()
    def list_nodes_compact(path: str, category: str | None = None) -> list[dict[str, Any]]:
        """[READ-ONLY] List nodes with minimal fields for concise authoring loops."""
        io = _build_io(path)
        nodes = io.list_nodes()
        if category is not None:
            nodes = [node for node in nodes if node.category == category]
        return [node_compact(node) for node in nodes]

    @mcp.tool()
    def get_node(path: str, node_id: str) -> dict[str, Any]:
        """[READ-ONLY] Return a single node as a JSON-ready dict."""
        io = _build_io(path)
        return io.get_node(node_id).model_dump()

    @mcp.tool()
    def upsert_node(path: str, node: dict[str, Any]) -> dict[str, Any]:
        """[MUTATES] Insert or replace one node from a typed object."""
        validated = Node.model_validate(node)
        io = _build_io(path)
        violations = io.validate_upsert_node(validated)
        if violations:
            return {
                "status": "rejected",
                "touched_ids": [],
                "validated_ids": [],
                "issues": [],
                "error_message": None,
                "save_error": None,
                "violations": [issue.model_dump() for issue in violations],
                "node": None,
            }
        result = io.upsert_node(validated)
        persisted = io.find_node(str(validated.id))
        return {
            **result_envelope(result),
            "node": persisted.model_dump() if persisted is not None else None,
        }

    @mcp.tool()
    def ensure_type(
        path: str,
        name: str,
        instance_category: str,
        description: str = "",
        slots: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Ensure a type node exists by name and upsert its payload."""
        io = _build_io(path)
        type_matches = [
            node for node in io.list_nodes() if node.name == name and node.category == "_type"
        ]
        if len(type_matches) > 1:
            raise ValueError(
                f"Ambiguous type node name {name!r}; multiple matches found.")
        existing = type_matches[0] if type_matches else None

        payload: dict[str, Any] = {
            "category": "_type",
            "name": name,
            "description": description,
            "props": {
                "instance_category": instance_category,
                "type_kind": instance_category,
                "slots": slots or [],
            },
            "source_repo_id": io.source_repo_id,
        }
        created = existing is None
        if existing is not None:
            payload["id"] = str(existing.id)
        validated = Node.model_validate(payload)
        result = io.upsert_node(validated)
        persisted = io.find_node(str(validated.id))
        return {
            **result_envelope(result),
            "created": created,
            "node": persisted.model_dump() if persisted is not None else None,
        }

    @mcp.tool()
    def ensure_instance(
        path: str,
        name: str,
        category: str,
        description: str = "",
        props: dict[str, Any] | None = None,
        type_id: str | None = None,
        type_name: str | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Ensure an instance node exists by (name, category) and upsert it."""
        io = _build_io(path)
        matches = [
            node for node in io.list_nodes() if node.name == name and node.category == category
        ]
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous instance identity (name={name!r}, category={category!r}); multiple matches found."
            )
        existing = matches[0] if matches else None

        resolved_type_id = type_id
        if type_name is not None:
            type_matches = [
                node for node in io.list_nodes() if node.name == type_name and node.category == "_type"
            ]
            if len(type_matches) > 1:
                raise ValueError(
                    f"Ambiguous type node name {type_name!r}; multiple matches found.")
            type_node = type_matches[0] if type_matches else None
            if type_node is None:
                raise KeyError(f"Type not found by name: {type_name}")
            resolved_type_id = str(type_node.id)

        payload: dict[str, Any] = {
            "category": category,
            "name": name,
            "description": description,
            "props": props or {},
            "source_repo_id": io.source_repo_id,
        }
        if resolved_type_id is not None:
            payload["type_id"] = resolved_type_id
        created = existing is None
        if existing is not None:
            payload["id"] = str(existing.id)
            if "type_id" not in payload and existing.type_id is not None:
                payload["type_id"] = str(existing.type_id)
        validated = Node.model_validate(payload)
        result = io.upsert_node(validated)
        persisted = io.find_node(str(validated.id))
        return {
            **result_envelope(result),
            "created": created,
            "node": persisted.model_dump() if persisted is not None else None,
        }

    # ------------------------------------------------------------------
    # WO2: Property mutation tools
    # ------------------------------------------------------------------

    @mcp.tool()
    def patch_node_props(
        path: str,
        node_id: str,
        props: dict[str, Any],
        expected_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Merge *props* into a node's existing properties (partial update).

        Only the keys present in *props* are written; all other props are
        unchanged.  Supports optimistic locking via *expected_revision_id*.

        Returns a dict with keys:
        - ``status``: ``"ok"``, ``"conflict"``, or ``"error"``.
        - ``touched_ids``: list of changed node IDs on success.
        - ``error_message``: explanation when status is not ``"ok"``.
        """
        from lks_utils.knowledge.io.conflict_error import ConflictError

        io = _build_io(path)
        try:
            result = io.patch_node_props(
                node_id, props, expected_revision_id=expected_revision_id
            )
        except ConflictError as exc:
            return {
                "status": "conflict",
                "touched_ids": [],
                "validated_ids": [],
                "issues": [],
                "error_message": str(exc),
                "save_error": None,
            }
        return result_envelope(result)

    @mcp.tool()
    def get_node_category(path: str, node_id: str) -> dict[str, Any]:
        """[READ-ONLY] Return one node's category."""
        io = _build_io(path)
        return {
            "node_id": node_id,
            "category": io.get_node_category(node_id),
        }

    @mcp.tool()
    def set_node_category(
        path: str,
        node_id: str,
        category: str,
        expected_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Set one node's category with optional optimistic locking."""
        from lks_utils.knowledge.io.conflict_error import ConflictError

        io = _build_io(path)
        try:
            result = io.set_node_category(
                node_id,
                category,
                expected_revision_id=expected_revision_id,
            )
        except ConflictError as exc:
            return {
                "status": "conflict",
                "touched_ids": [],
                "validated_ids": [],
                "issues": [],
                "error_message": str(exc),
                "save_error": None,
            }
        return result_envelope(result)

    @mcp.tool()
    def list_nodes_by_category(path: str, category: str) -> list[dict[str, Any]]:
        """[READ-ONLY] Return nodes whose category equals *category* exactly."""
        io = _build_io(path)
        return [node.model_dump() for node in io.find_nodes_by_category(category)]

    @mcp.tool()
    def find_nodes_multi_prop(
        path: str,
        filters: list[dict[str, Any]],
        match: str = "all",
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] Return nodes matching all (or any) of the given prop filters.

        Each filter dict must have keys:
        - ``prop_key``: the property key to inspect.
        - ``op``: one of ``"eq"``, ``"neq"``, ``"contains"``, ``"starts_with"``.
        - ``value``: the value to compare against.

        *match* must be ``"all"`` (AND) or ``"any"`` (OR).
        """
        from lks_utils.knowledge.io.prop_filter import PropFilter

        parsed = [
            PropFilter(
                prop_key=f["prop_key"],
                op=f["op"],  # type: ignore[arg-type]
                value=f["value"],
            )
            for f in filters
        ]
        io = _build_io(path)
        nodes = io.find_nodes_multi_prop(
            parsed, match=match)  # type: ignore[arg-type]
        return [node.model_dump() for node in nodes]

    @mcp.tool()
    def delete_node(path: str, node_id: str) -> dict[str, Any]:
        """[MUTATES] Delete one node; returns ``blocked`` if incident links exist.

        No cascade — links must be removed first (or use ``delete_node_cascade``).

        Returns a dict with keys:
        - ``status``: ``"ok"`` or ``"blocked"``.
        - ``blocking_impact``: link impact summary when ``status=="blocked"``.
        - ``error_message``: explanation when blocked.
        """
        io = _build_io(path)
        result = io.delete_node_safe(node_id)
        out: dict[str, Any] = result_envelope(result)
        if result.blocking_impact is not None:
            out["blocking_impact"] = result.blocking_impact
        return out

    @mcp.tool()
    def delete_node_cascade(path: str, node_id: str) -> dict[str, Any]:
        """[MUTATES] Delete one node and all its incident links atomically.

        Use when you want a force-delete regardless of existing link connections.
        """
        io = _build_io(path)
        result = io.delete_node_cascade(node_id)
        return result_envelope(result)

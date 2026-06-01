"""Schema and resolver view tools for knowledge MCP."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import _build_io, node_summary
from lks_utils.knowledge.io.prop_filter import PropFilter


def get_node_slot_names_impl(
    path: str,
    node_id: str,
    effective: bool = True,
) -> list[str]:
    """Return slot/property names for one node."""
    io = _build_io(path)
    return io.get_node_slot_names(node_id=node_id, effective=effective)


def get_node_slot_value_impl(
    path: str,
    node_id: str,
    slot_name: str,
    effective: bool = True,
) -> dict[str, Any]:
    """Return one slot/property value for one node as a SlotValueEnvelope dict."""
    io = _build_io(path)
    return io.get_node_slot_value(node_id=node_id, slot_name=slot_name, effective=effective)


def get_node_slot_values_impl(
    path: str,
    node_id: str,
    slot_names: list[str] | None = None,
    effective: bool = True,
) -> dict[str, Any]:
    """Return batch slot/property values for one node."""
    io = _build_io(path)
    return io.get_node_slot_values(node_id=node_id, slot_names=slot_names, effective=effective)


def get_repo_schema_summary_impl(path: str) -> dict[str, Any]:
    io = _build_io(path)
    return io.get_repo_schema_summary()


def list_instances_of_type_query_impl(
    path: str,
    type_query: str,
    include_descendants: bool = True,
) -> list[dict[str, Any]]:
    """Return instances for a case-insensitive type query with suggestions."""
    io = _build_io(path)
    return [
        node_summary(node)
        for node in io.list_instances_of_type_query(
            type_query,
            include_descendants=include_descendants,
        )
    ]


def list_descendant_types_query_impl(
    path: str,
    type_query: str,
    include_self: bool = False,
) -> list[dict[str, Any]]:
    """Return descendant types for a case-insensitive type query."""
    io = _build_io(path)
    return [
        node_summary(node)
        for node in io.list_descendant_types_query(
            type_query,
            include_self=include_self,
        )
    ]


def query_nodes_impl(
    path: str,
    *,
    node_ids: list[str] | None = None,
    node_type_query: str | None = None,
    include_descendant_types: bool = True,
    node_category: str | None = None,
    name_substring: str | None = None,
    prop_filters: list[dict[str, Any]] | None = None,
    prop_match: str = "all",
    return_mode: str = "summary",
) -> dict[str, Any]:
    """Return repository nodes that match caller-supplied filters."""
    io = _build_io(path)
    if prop_match not in {"all", "any"}:
        raise ValueError("prop_match must be one of: all, any")
    if return_mode not in {"compact", "summary", "hydrated"}:
        raise ValueError(
            "return_mode must be one of: compact, summary, hydrated")

    allowed_ids = set(node_ids or [])
    allowed_type_ids: set[str] | None = None
    if node_type_query is not None:
        if include_descendant_types:
            allowed_type_ids = {
                str(node.id)
                for node in io.list_descendant_types_query(node_type_query, include_self=True)
            }
        else:
            allowed_type_ids = {str(io.resolve_type_query(node_type_query).id)}

    parsed_prop_filters: list[PropFilter] = []
    for row in prop_filters or []:
        parsed_prop_filters.append(
            PropFilter(
                prop_key=str(row["prop_key"]),
                op=str(row["op"]),
                value=row["value"],
            )
        )

    name_token = name_substring.casefold() if isinstance(
        name_substring, str) and name_substring else None
    combiner = all if prop_match == "all" else any

    filtered_ids: list[str] = []
    all_nodes = io.list_nodes()
    for node in all_nodes:
        node_id = str(node.id)
        if allowed_ids and node_id not in allowed_ids:
            continue
        if node_category is not None and node.category != node_category:
            continue
        if allowed_type_ids is not None and str(node.type_id) not in allowed_type_ids:
            continue
        if name_token is not None and name_token not in node.name.casefold():
            continue
        if parsed_prop_filters and not combiner(
            flt.matches(node.props or {}) for flt in parsed_prop_filters
        ):
            continue
        filtered_ids.append(node_id)

    filtered_id_set = set(filtered_ids)
    if return_mode == "compact":
        rows = [
            {
                "id": str(node.id),
                "name": node.name,
                "category": node.category,
                "type_id": str(node.type_id) if node.type_id else None,
            }
            for node in all_nodes
            if str(node.id) in filtered_id_set
        ]
    elif return_mode == "summary":
        rows = [
            node_summary(node)
            for node in all_nodes
            if str(node.id) in filtered_id_set
        ]
    else:
        rows = [io.get_node_hydrated(node_id) for node_id in filtered_ids]

    return {
        "count": len(rows),
        "node_ids": filtered_ids,
        "nodes": rows,
    }


def register_schema_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_repo_schema_summary(path: str) -> dict[str, Any]:
        """[READ-ONLY] Return all type slots and link types in one call."""
        return get_repo_schema_summary_impl(path)

    @mcp.tool()
    def get_node_hydrated(path: str, node_id: str) -> dict[str, Any]:
        """[READ-ONLY] Return a node with refs resolved and inheritance merged."""
        io = _build_io(path)
        return io.get_node_hydrated(node_id)

    @mcp.tool()
    def get_type_slots(path: str, type_id: str) -> list[dict[str, Any]]:
        """[READ-ONLY] Return merged slots for a type."""
        io = _build_io(path)
        return [slot.model_dump() for slot in io.get_type_slots(type_id)]

    @mcp.tool()
    def get_node_slot_names(
        path: str,
        node_id: str,
        effective: bool = True,
    ) -> list[str]:
        """[READ-ONLY] Return slot/property names for a node.

        For type nodes, returns type slot names.
        For instances, ``effective=True`` returns resolved slot names from inheritance,
        otherwise returns direct ``node.props`` keys.
        """
        return get_node_slot_names_impl(path, node_id, effective)

    @mcp.tool()
    def get_node_slot_value(
        path: str,
        node_id: str,
        slot_name: str,
        effective: bool = True,
    ) -> dict[str, Any]:
        """[READ-ONLY] Return one slot/property value for a node."""
        return get_node_slot_value_impl(path, node_id, slot_name, effective)

    @mcp.tool()
    def get_node_slot_values(
        path: str,
        node_id: str,
        slot_names: list[str] | None = None,
        effective: bool = True,
    ) -> dict[str, Any]:
        """[READ-ONLY] Return slot/property values for one node in batch."""
        return get_node_slot_values_impl(path, node_id, slot_names, effective)

    @mcp.tool()
    def get_effective_props(path: str, instance_id: str) -> dict[str, Any]:
        """[READ-ONLY] Return effective props with inheritance scope metadata."""
        io = _build_io(path)
        return io.get_effective_props(instance_id)

    @mcp.tool()
    def get_parent_chain(path: str, type_id: str) -> list[dict[str, Any]]:
        """[READ-ONLY] Return ordered ancestor types for a type."""
        io = _build_io(path)
        return [node_summary(node) for node in io.get_parent_chain(type_id)]

    @mcp.tool()
    def get_parent_chain_query(path: str, type_query: str) -> list[dict[str, Any]]:
        """[READ-ONLY] Return ordered ancestor types for a type query by id/name/category."""
        io = _build_io(path)
        type_node = io.resolve_type_query(type_query)
        return [node_summary(node) for node in io.get_parent_chain(str(type_node.id))]

    @mcp.tool()
    def list_instances_of_type(path: str, type_id: str) -> list[dict[str, Any]]:
        """[READ-ONLY] List all instance nodes that reference a given type_id."""
        io = _build_io(path)
        return [node_summary(node) for node in io.list_instances_of_type(type_id)]

    @mcp.tool()
    def list_instances_of_type_query(
        path: str,
        type_query: str,
        include_descendants: bool = True,
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] List instances for a type query by id, name, or category.

        Matching is case-insensitive. When the query misses, the tool raises with
        a "Did you mean ...?" suggestion when a close type name exists.
        """
        return list_instances_of_type_query_impl(
            path,
            type_query,
            include_descendants=include_descendants,
        )

    @mcp.tool()
    def list_descendant_types(path: str, type_id: str, include_self: bool = False) -> list[dict[str, Any]]:
        """[READ-ONLY] List descendant types for a type id."""
        io = _build_io(path)
        return [
            node_summary(node)
            for node in io.list_descendant_types(type_id, include_self=include_self)
        ]

    @mcp.tool()
    def list_descendant_types_query(
        path: str,
        type_query: str,
        include_self: bool = False,
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] List descendant types for a type query by id/name/category."""
        return list_descendant_types_query_impl(
            path,
            type_query,
            include_self=include_self,
        )

    @mcp.tool()
    def find_nodes_by_name(path: str, name_substring: str) -> list[dict[str, Any]]:
        """[READ-ONLY] Search nodes by case-insensitive name substring."""
        io = _build_io(path)
        return [node_summary(node) for node in io.search_nodes_by_name(name_substring)]

    @mcp.tool()
    def find_nodes_by_prop_value(
        path: str,
        prop_key: str,
        value_substring: str,
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] Search instances by top-level string prop value substring."""
        matches: list[dict[str, Any]] = []
        io = _build_io(path)
        for node, value in io.search_nodes_by_prop_value(prop_key, value_substring):
            summary = node_summary(node)
            summary["matched_value"] = value
            matches.append(summary)
        return matches

    @mcp.tool()
    def query_nodes(
        path: str,
        node_ids: list[str] | None = None,
        node_type_query: str | None = None,
        include_descendant_types: bool = True,
        node_category: str | None = None,
        name_substring: str | None = None,
        prop_filters: list[dict[str, Any]] | None = None,
        prop_match: str = "all",
        return_mode: str = "summary",
    ) -> dict[str, Any]:
        """[READ-ONLY] Return nodes matching configurable id/type/category/name/property filters."""
        return query_nodes_impl(
            path,
            node_ids=node_ids,
            node_type_query=node_type_query,
            include_descendant_types=include_descendant_types,
            node_category=node_category,
            name_substring=name_substring,
            prop_filters=prop_filters,
            prop_match=prop_match,
            return_mode=return_mode,
        )

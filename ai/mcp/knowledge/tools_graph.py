"""Graph traversal tools for knowledge MCP."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import _build_io, node_compact, node_summary, nodes_by_id
from lks_utils.knowledge.graph_service import GraphService
from lks_utils.knowledge.io.prop_filter import PropFilter
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID


def propagate_rule_to_module_children_impl(
    path: str,
    rule_node_id: str,
    root_module_id: str,
    max_depth: int = -1,
    link_type_id: str = "rule_applies_to",
    traversal_link_type_id: str = "parent_module",
) -> list[str]:
    """Link one source node to descendants reachable through a traversal link type."""
    io = _build_io(path)
    io.get(rule_node_id)
    io.get(root_module_id)
    applies_link_type_id = _resolve_link_type_id(io, link_type_id)
    traversal_type_id = _resolve_link_type_id(io, traversal_link_type_id)

    descendants = _descendants_from_root(
        io=io,
        root_module_id=root_module_id,
        traversal_link_type_id=traversal_type_id,
        max_depth=max_depth,
    )
    existing_pairs = {
        (link.source_node_id, link.target_node_id, link.link_type_id)
        for link in io.list_links()
    }

    touched_node_ids: list[str] = []
    for module_id in descendants:
        key = (rule_node_id, module_id, applies_link_type_id)
        if key in existing_pairs:
            continue
        link = LinkInstance(
            link_type_id=applies_link_type_id,
            source_node_id=rule_node_id,
            target_node_id=module_id,
        )
        io.upsert_link(link)
        existing_pairs.add(key)
        touched_node_ids.append(module_id)

    return touched_node_ids


def query_rules_for_node_impl(
    path: str,
    node_id: str,
    rule_type_id: str | None = None,
    traversal_link_type_id: str = "parent_module",
    applies_link_type_id: str = "rule_applies_to",
) -> list[dict[str, Any]]:
    """Collect rule nodes connected to a node and its parent chain."""
    io = _build_io(path)
    io.get(node_id)
    traversal_type_id = _resolve_link_type_id(io, traversal_link_type_id)
    applies_type_id = _resolve_link_type_id(io, applies_link_type_id)

    chain = _parent_chain(io=io, node_id=node_id,
                          traversal_link_type_id=traversal_type_id)
    ordered_node_ids = [node_id] + chain
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for current_id in ordered_node_ids:
        for link in io.list_links():
            if link.link_type_id != applies_type_id:
                continue
            if link.target_node_id != current_id:
                continue
            rule_node = io.find_node(link.source_node_id)
            if rule_node is None:
                continue
            rule_id = str(rule_node.id)
            if rule_id in seen:
                continue
            if rule_type_id is not None and str(rule_node.type_id) != rule_type_id:
                continue
            seen.add(rule_id)
            out.append(node_compact(rule_node))
    return out


def query_modules_for_rule_impl(
    path: str,
    rule_node_id: str,
    applies_link_type_id: str = "rule_applies_to",
) -> list[dict[str, Any]]:
    """Return nodes that receive an applies-link from the given rule node."""
    io = _build_io(path)
    io.get(rule_node_id)
    applies_type_id = _resolve_link_type_id(io, applies_link_type_id)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in io.list_links():
        if link.link_type_id != applies_type_id:
            continue
        if link.source_node_id != rule_node_id:
            continue
        node = io.find_node(link.target_node_id)
        if node is None:
            continue
        node_key = str(node.id)
        if node_key in seen:
            continue
        seen.add(node_key)
        out.append(node_compact(node))
    return out


def ascending_collect_impl(
    path: str,
    origin_node_id: str,
    traversal_link_type_id: str,
    collect_link_type_id: str | None = None,
    max_depth: int = -1,
    collect_direction: str = "incoming",
    collect_node_category: str | None = None,
    collect_type_id: str | None = None,
    include_chain: bool = True,
) -> dict[str, Any]:
    """Collect nodes attached along an ancestor chain with fully caller-supplied config."""
    io = _build_io(path)
    io.get(origin_node_id)
    traversal_type_id = _resolve_link_type_id(io, traversal_link_type_id)
    collect_type_resolved = (
        _resolve_link_type_id(io, collect_link_type_id)
        if collect_link_type_id is not None
        else None
    )
    if collect_direction not in {"incoming", "outgoing", "both"}:
        raise ValueError(
            "collect_direction must be one of: incoming, outgoing, both")

    rungs: list[dict[str, Any]] = []
    chain_node_ids = [origin_node_id] + _parent_chain(
        io=io,
        node_id=origin_node_id,
        traversal_link_type_id=traversal_type_id,
    )
    if max_depth >= 0:
        chain_node_ids = chain_node_ids[: max_depth + 1]

    seen_collected: set[str] = set()
    for depth, rung_node_id in enumerate(chain_node_ids):
        rung_node = io.get(rung_node_id)
        collected: list[dict[str, Any]] = []
        for link in io.list_links():
            if collect_type_resolved is not None and link.link_type_id != collect_type_resolved:
                continue

            neighbor_id: str | None = None
            if collect_direction in {"incoming", "both"} and link.target_node_id == rung_node_id:
                neighbor_id = str(link.source_node_id)
            elif collect_direction in {"outgoing", "both"} and link.source_node_id == rung_node_id:
                neighbor_id = str(link.target_node_id)
            if neighbor_id is None:
                continue

            if neighbor_id in seen_collected:
                continue
            neighbor = io.find_node(neighbor_id)
            if neighbor is None:
                continue
            if collect_node_category is not None and neighbor.category != collect_node_category:
                continue
            if collect_type_id is not None and str(neighbor.type_id) != collect_type_id:
                continue
            seen_collected.add(neighbor_id)
            collected.append(
                {
                    **node_compact(neighbor),
                    "via_link_id": link.id,
                    "via_link_type_id": link.link_type_id,
                    "rung_node_id": rung_node_id,
                    "depth": depth,
                }
            )

        rung_payload: dict[str, Any] = {
            "depth": depth,
            "rung_node": node_compact(rung_node),
            "collected": collected,
        }
        if include_chain:
            rung_payload["chain_node_id"] = rung_node_id
        rungs.append(rung_payload)

    return {
        "origin_node_id": origin_node_id,
        "traversal_link_type_id": traversal_link_type_id,
        "collect_link_type_id": collect_link_type_id,
        "collect_direction": collect_direction,
        "collect_node_category": collect_node_category,
        "collect_type_id": collect_type_id,
        "rungs": rungs,
    }


def query_connected_nodes_impl(
    path: str,
    origin_node_id: str,
    *,
    max_depth: int = 2,
    direction: str = "both",
    link_type_ids: list[str] | None = None,
    link_type_queries: list[str] | None = None,
    node_type_query: str | None = None,
    include_descendant_types: bool = True,
    node_category: str | None = None,
    name_substring: str | None = None,
    prop_filters: list[dict[str, Any]] | None = None,
    prop_match: str = "all",
    return_mode: str = "compact",
    include_origin: bool = False,
) -> dict[str, Any]:
    """Return nodes connected to an origin node, filtered by caller-supplied predicates."""
    io = _build_io(path)
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError("direction must be one of: outgoing, incoming, both")
    if prop_match not in {"all", "any"}:
        raise ValueError("prop_match must be one of: all, any")
    if return_mode not in {"compact", "summary", "hydrated"}:
        raise ValueError(
            "return_mode must be one of: compact, summary, hydrated")

    nodes = io.list_nodes()
    links = io.list_links()
    graph = GraphService().build_graph(nodes, links)
    if origin_node_id not in graph:
        raise KeyError(origin_node_id)

    resolved_link_type_ids: set[str] | None = None
    if link_type_ids or link_type_queries:
        resolved_link_type_ids = set(link_type_ids or [])
        for link_type_query in link_type_queries or []:
            resolved_link_type_ids.add(
                _resolve_link_type_id(io, link_type_query))

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

    visited: set[str] = {origin_node_id}
    queue: list[tuple[str, int]] = [(origin_node_id, 0)]
    traversed_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str | None]] = set()

    while queue:
        current_id, depth = queue.pop(0)
        if depth >= max_depth:
            continue

        neighbors: list[tuple[str, str, dict[str, Any]]] = []
        if direction in {"outgoing", "both"}:
            for neighbor_id in sorted(graph.successors(current_id)):
                edge_data = dict(graph.get_edge_data(
                    current_id, neighbor_id) or {})
                neighbors.append((current_id, neighbor_id, edge_data))
        if direction in {"incoming", "both"}:
            for neighbor_id in sorted(graph.predecessors(current_id)):
                edge_data = dict(graph.get_edge_data(
                    neighbor_id, current_id) or {})
                neighbors.append((neighbor_id, current_id, edge_data))

        for source_id, target_id, edge_data in neighbors:
            edge_link_type_id = edge_data.get("link_type_id")
            if resolved_link_type_ids is not None and edge_link_type_id not in resolved_link_type_ids:
                continue

            edge_key = (source_id, target_id, edge_link_type_id)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                traversed_edges.append(
                    {
                        "source_node_id": source_id,
                        "target_node_id": target_id,
                        "link_type_id": edge_link_type_id,
                    }
                )

            next_id = target_id if source_id == current_id else source_id
            if next_id in visited:
                continue
            visited.add(next_id)
            queue.append((next_id, depth + 1))

    candidate_ids = set(visited)
    if not include_origin:
        candidate_ids.discard(origin_node_id)

    name_token = name_substring.casefold() if isinstance(
        name_substring, str) and name_substring else None
    combiner = all if prop_match == "all" else any

    matched_ids: list[str] = []
    for node in nodes:
        node_id = str(node.id)
        if node_id not in candidate_ids:
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
        matched_ids.append(node_id)

    if return_mode == "compact":
        matched_nodes = [
            node_compact(node)
            for node in nodes
            if str(node.id) in set(matched_ids)
        ]
    elif return_mode == "summary":
        matched_nodes = [
            node_summary(node)
            for node in nodes
            if str(node.id) in set(matched_ids)
        ]
    else:
        matched_nodes = [io.get_node_hydrated(
            node_id) for node_id in matched_ids]

    return {
        "origin_node_id": origin_node_id,
        "max_depth": max_depth,
        "direction": direction,
        "matched_count": len(matched_nodes),
        "matched_node_ids": matched_ids,
        "matched_nodes": matched_nodes,
        "traversed_edge_count": len(traversed_edges),
        "traversed_edges": traversed_edges,
    }


def register_graph_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_neighbors(path: str, node_id: str) -> dict[str, list[dict[str, Any]]]:
        """[READ-ONLY] Return all links where node is source or target."""
        io = _build_io(path)
        node_index = nodes_by_id(io.list_nodes())
        incoming: list[dict[str, Any]] = []
        outgoing: list[dict[str, Any]] = []
        for link in io.list_links():
            if link.source_node_id == node_id:
                target = node_index.get(link.target_node_id)
                outgoing.append(
                    {
                        "link_id": link.id,
                        "link_type_id": link.link_type_id,
                        "source_slot_name": link.source_slot_name,
                        "target_node_id": link.target_node_id,
                        "target_node_name": target.name if target else None,
                        "metadata": link.metadata,
                    }
                )
            if link.target_node_id == node_id:
                source = node_index.get(link.source_node_id)
                incoming.append(
                    {
                        "link_id": link.id,
                        "link_type_id": link.link_type_id,
                        "source_slot_name": link.source_slot_name,
                        "source_node_id": link.source_node_id,
                        "source_node_name": source.name if source else None,
                        "metadata": link.metadata,
                    }
                )
        return {"incoming": incoming, "outgoing": outgoing}

    @mcp.tool()
    def get_slot_refs_for_node(
        path: str,
        node_id: str,
        slot_name: str | None = None,
    ) -> dict[str, Any]:
        """[READ-ONLY] Return all slot_ref links from a node grouped by slot name."""
        io = _build_io(path)
        node_index = nodes_by_id(io.list_nodes())

        grouped: dict[str, list[dict[str, Any]]] = {}
        count = 0
        for link in io.list_links():
            if link.source_node_id != node_id:
                continue
            if link.link_type_id != SLOT_REF_LINK_TYPE_ID:
                continue
            current_slot_name = link.source_slot_name
            if not isinstance(current_slot_name, str) or not current_slot_name:
                continue
            count += 1
            if slot_name is not None and current_slot_name != slot_name:
                continue
            target = node_index.get(link.target_node_id)
            grouped.setdefault(current_slot_name, []).append(
                {
                    "link_id": link.id,
                    "target_node_id": link.target_node_id,
                    "target_node_name": target.name if target else None,
                }
            )

        return {"slots": grouped, "total_slot_ref_count": count}

    @mcp.tool()
    def traverse_graph(
        path: str,
        start_node_id: str,
        max_depth: int = 2,
        link_type_name: str | None = None,
        direction: str = "outgoing",
        include_link_meta: bool = False,
    ) -> dict[str, Any]:
        """[READ-ONLY] Traverse graph from a start node and return visited nodes + edges."""
        io = _build_io(path)
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError(
                "direction must be one of: outgoing, incoming, both")

        nodes = io.list_nodes()
        links = io.list_links()
        graph_service = GraphService()
        graph = graph_service.build_graph(nodes, links)

        if start_node_id not in graph:
            raise KeyError(start_node_id)

        resolved_link_type_id: str | None = None
        if link_type_name:
            resolved_link_type_id = _resolve_link_type_id(io, link_type_name)

        visited: set[str] = {start_node_id}
        queue: list[tuple[str, int]] = [(start_node_id, 0)]
        visited_nodes: list[dict[str, Any]] = []
        traversed_edges: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str | None]] = set()

        while queue:
            current_id, depth = queue.pop(0)
            current_node = io.get(current_id)
            visited_nodes.append({
                **node_summary(current_node),
                "depth": depth,
            })
            if depth >= max_depth:
                continue

            neighbors: list[tuple[str, str, dict[str, Any]]] = []
            if direction in {"outgoing", "both"}:
                for neighbor_id in sorted(graph.successors(current_id)):
                    edge_data = dict(graph.get_edge_data(
                        current_id, neighbor_id) or {})
                    neighbors.append((current_id, neighbor_id, edge_data))
            if direction in {"incoming", "both"}:
                for neighbor_id in sorted(graph.predecessors(current_id)):
                    edge_data = dict(graph.get_edge_data(
                        neighbor_id, current_id) or {})
                    neighbors.append((neighbor_id, current_id, edge_data))

            for source_id, target_id, edge_data in neighbors:
                edge_link_type_id = edge_data.get("link_type_id")
                if resolved_link_type_id is not None and edge_link_type_id != resolved_link_type_id:
                    continue

                edge_key = (source_id, target_id, edge_link_type_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edge_payload: dict[str, Any] = {
                        "source_node_id": source_id,
                        "target_node_id": target_id,
                        "link_type_id": edge_link_type_id,
                    }
                    if include_link_meta:
                        edge_payload["metadata"] = edge_data
                    traversed_edges.append(edge_payload)

                next_id = target_id if source_id == current_id else source_id
                if next_id in visited:
                    continue
                visited.add(next_id)
                queue.append((next_id, depth + 1))

        return {
            "start_node_id": start_node_id,
            "direction": direction,
            "max_depth": max_depth,
            "link_type_name": link_type_name,
            "visited_nodes": visited_nodes,
            "edges": traversed_edges,
        }

    @mcp.tool()
    def propagate_rule_to_module_children(
        path: str,
        rule_node_id: str,
        root_module_id: str,
        max_depth: int = -1,
        link_type_id: str = "rule_applies_to",
        traversal_link_type_id: str = "parent_module",
    ) -> list[str]:
        """[MUTATES] Link one source node to descendants reachable through a traversal link type."""
        return propagate_rule_to_module_children_impl(
            path=path,
            rule_node_id=rule_node_id,
            root_module_id=root_module_id,
            max_depth=max_depth,
            link_type_id=link_type_id,
            traversal_link_type_id=traversal_link_type_id,
        )

    @mcp.tool()
    def query_rules_for_node(
        path: str,
        node_id: str,
        rule_type_id: str | None = None,
        traversal_link_type_id: str = "parent_module",
        applies_link_type_id: str = "rule_applies_to",
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] Collect rule nodes connected to a node and its parent chain."""
        return query_rules_for_node_impl(
            path=path,
            node_id=node_id,
            rule_type_id=rule_type_id,
            traversal_link_type_id=traversal_link_type_id,
            applies_link_type_id=applies_link_type_id,
        )

    @mcp.tool()
    def query_modules_for_rule(
        path: str,
        rule_node_id: str,
        applies_link_type_id: str = "rule_applies_to",
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] Return nodes that receive an applies-link from the given rule node."""
        return query_modules_for_rule_impl(
            path=path,
            rule_node_id=rule_node_id,
            applies_link_type_id=applies_link_type_id,
        )

    @mcp.tool()
    def ascending_collect(
        path: str,
        origin_node_id: str,
        traversal_link_type_id: str,
        collect_link_type_id: str | None = None,
        max_depth: int = -1,
        collect_direction: str = "incoming",
        collect_node_category: str | None = None,
        collect_type_id: str | None = None,
        include_chain: bool = True,
    ) -> dict[str, Any]:
        """[READ-ONLY] Generic ancestor-chain collection with caller-supplied traversal and collect filters."""
        return ascending_collect_impl(
            path=path,
            origin_node_id=origin_node_id,
            traversal_link_type_id=traversal_link_type_id,
            collect_link_type_id=collect_link_type_id,
            max_depth=max_depth,
            collect_direction=collect_direction,
            collect_node_category=collect_node_category,
            collect_type_id=collect_type_id,
            include_chain=include_chain,
        )

    @mcp.tool()
    def query_connected_nodes(
        path: str,
        origin_node_id: str,
        max_depth: int = 2,
        direction: str = "both",
        link_type_ids: list[str] | None = None,
        link_type_queries: list[str] | None = None,
        node_type_query: str | None = None,
        include_descendant_types: bool = True,
        node_category: str | None = None,
        name_substring: str | None = None,
        prop_filters: list[dict[str, Any]] | None = None,
        prop_match: str = "all",
        return_mode: str = "compact",
        include_origin: bool = False,
    ) -> dict[str, Any]:
        """[READ-ONLY] Traverse from origin and return connected nodes filtered by link/node predicates."""
        return query_connected_nodes_impl(
            path,
            origin_node_id,
            max_depth=max_depth,
            direction=direction,
            link_type_ids=link_type_ids,
            link_type_queries=link_type_queries,
            node_type_query=node_type_query,
            include_descendant_types=include_descendant_types,
            node_category=node_category,
            name_substring=name_substring,
            prop_filters=prop_filters,
            prop_match=prop_match,
            return_mode=return_mode,
            include_origin=include_origin,
        )


def _resolve_link_type_id(io: Any, link_type_id_or_name: str) -> str:
    if io.find_link_type(link_type_id_or_name) is not None:
        return link_type_id_or_name

    aliases: dict[str, list[str]] = {
        "rule_applies_to": ["applies_to_type"],
        "parent_module": ["belongs_to_module"],
    }
    for alias_name in aliases.get(link_type_id_or_name, []):
        matches = [
            link_type.id
            for link_type in io.list_link_types()
            if link_type.name == alias_name
        ]
        if len(matches) == 1:
            return matches[0]

    matches = [
        link_type.id
        for link_type in io.list_link_types()
        if link_type.name == link_type_id_or_name
    ]
    if not matches:
        raise KeyError(f"Link type not found: {link_type_id_or_name}")
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous link type name {link_type_id_or_name!r}; matches multiple IDs"
        )
    return matches[0]


def _descendants_from_root(
    *,
    io: Any,
    root_module_id: str,
    traversal_link_type_id: str,
    max_depth: int,
) -> list[str]:
    descendants: list[str] = []
    visited: set[str] = {root_module_id}
    frontier: list[tuple[str, int]] = [(root_module_id, 0)]

    while frontier:
        current_id, depth = frontier.pop(0)
        if max_depth >= 0 and depth >= max_depth:
            continue
        for link in io.list_links():
            if link.link_type_id != traversal_link_type_id:
                continue
            if link.source_node_id != current_id:
                continue
            child_id = link.target_node_id
            if child_id in visited:
                continue
            visited.add(child_id)
            descendants.append(child_id)
            frontier.append((child_id, depth + 1))
    return descendants


def _parent_chain(*, io: Any, node_id: str, traversal_link_type_id: str) -> list[str]:
    chain: list[str] = []
    visited: set[str] = {node_id}
    current_id = node_id
    while True:
        parent_id: str | None = None
        for link in io.list_links():
            if link.link_type_id != traversal_link_type_id:
                continue
            if link.target_node_id != current_id:
                continue
            candidate_parent = link.source_node_id
            if candidate_parent in visited:
                continue
            parent_id = candidate_parent
            break
        if parent_id is None:
            break
        visited.add(parent_id)
        chain.append(parent_id)
        current_id = parent_id
    return chain

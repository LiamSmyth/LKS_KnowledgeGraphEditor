"""Graph-service utilities for knowledge nodes."""
from __future__ import annotations

from collections import deque

import networkx as nx

from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.models.node import Node


class GraphService:
    """Builds directed graph views from ULID-referenced nodes."""

    def build_graph(
        self,
        nodes: list[Node],
        links: list[LinkInstance] | None = None,
    ) -> nx.DiGraph:
        """Return a directed graph with ULID-keyed nodes and edges.

        Edges are derived from explicit *links* only.
        Link-instance edges carry a ``link_type_id`` edge attribute.
        """
        graph = nx.DiGraph()
        for node in nodes:
            node_id = str(node.id)
            graph.add_node(node_id, kind=node.category, name=node.name)
        if links:
            for link in links:
                graph.add_edge(
                    link.source_node_id,
                    link.target_node_id,
                    link_type_id=link.link_type_id,
                )
        return graph

    def traverse_from(
        self,
        start_node_id: str,
        nodes: list[Node],
        links: list[LinkInstance] | None = None,
        *,
        max_depth: int | None = None,
    ) -> list[str]:
        """Breadth-first traversal with deterministic ordering and cycle safety."""
        if max_depth is not None and max_depth < 0:
            raise ValueError("max_depth must be non-negative when provided")

        graph = self.build_graph(nodes, links)
        if start_node_id not in graph:
            raise KeyError(start_node_id)

        visited: set[str] = {start_node_id}
        ordered: list[str] = []
        queue: deque[tuple[str, int]] = deque([(start_node_id, 0)])

        while queue:
            node_id, depth = queue.popleft()
            ordered.append(node_id)
            if max_depth is not None and depth >= max_depth:
                continue

            for neighbor_id in sorted(graph.successors(node_id)):
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                queue.append((neighbor_id, depth + 1))

        return ordered

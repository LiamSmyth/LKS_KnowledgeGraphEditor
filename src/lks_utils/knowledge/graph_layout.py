"""Deterministic layout helpers for knowledge graph rendering."""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from lks_utils.knowledge.graph_service import GraphService
from lks_utils.knowledge.models.node import Node


@dataclass(frozen=True, slots=True)
class GraphRenderNode:
    """Precomputed graph node positioned in scene space."""

    node_id: str
    label: str
    category: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class GraphRenderEdge:
    """Precomputed graph edge in scene space."""

    source_node_id: str
    target_node_id: str


def build_graph_layout(nodes: list[Node]) -> tuple[list[GraphRenderNode], list[GraphRenderEdge]]:
    """Return deterministic render nodes and edges for a knowledge graph."""
    graph_service = GraphService()
    graph = graph_service.build_graph(nodes)
    if not graph.nodes:
        return [], []

    positions = nx.spring_layout(graph, seed=42, scale=1.0)
    render_nodes: list[GraphRenderNode] = []
    for node in sorted(nodes, key=lambda item: str(item.id)):
        node_id = str(node.id)
        x, y = positions.get(node_id, (0.0, 0.0))
        render_nodes.append(
            GraphRenderNode(
                node_id=node_id,
                label=f"{node.name}\n[{node.category}]",
                category=node.category,
                x=float(x),
                y=float(y),
            )
        )

    render_edges = [
        GraphRenderEdge(
            source_node_id=source_id, target_node_id=target_id)
        for source_id, target_id in sorted(graph.edges())
    ]
    return render_nodes, render_edges



__all__ = [
    "GraphRenderEdge",
    "GraphRenderNode",
    "build_graph_layout",
]

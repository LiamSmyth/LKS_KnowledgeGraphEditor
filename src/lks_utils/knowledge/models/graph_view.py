"""Graph-view aggregate model."""
from __future__ import annotations

from dataclasses import dataclass, field

from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.graph_view_node_proxy import GraphViewNodeProxy


@dataclass(frozen=True)
class GraphView:
    """A persisted visual layout of node and edge proxies."""

    id: str
    name: str
    nodes: dict[str, GraphViewNodeProxy] = field(default_factory=dict)
    edges: dict[str, GraphViewEdgeProxy] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("GraphView.id must be non-empty")
        if not self.name.strip():
            raise ValueError("GraphView.name must be non-empty")

    def to_dict(self) -> dict[str, object]:
        """Return a strict JSON-serializable GraphView payload."""
        return {
            "id": self.id,
            "name": self.name,
            "nodes": {key: value.to_dict() for key, value in self.nodes.items()},
            "edges": {key: value.to_dict() for key, value in self.edges.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GraphView:
        """Create a GraphView from a strict dictionary payload."""
        expected = {"id", "name", "nodes", "edges"}
        actual = set(data.keys())
        unknown = sorted(actual - expected)
        if unknown:
            raise ValueError(
                f"GraphView.from_dict received unknown keys: {unknown}")
        missing = sorted(expected - actual)
        if missing:
            raise ValueError(f"GraphView.from_dict missing keys: {missing}")

        raw_nodes = data["nodes"]
        raw_edges = data["edges"]
        if not isinstance(raw_nodes, dict):
            raise ValueError(
                "GraphView.from_dict expects 'nodes' to be a dict")
        if not isinstance(raw_edges, dict):
            raise ValueError(
                "GraphView.from_dict expects 'edges' to be a dict")

        node_map: dict[str, GraphViewNodeProxy] = {}
        for local_id, payload in raw_nodes.items():
            if not isinstance(payload, dict):
                raise ValueError(
                    "GraphView.from_dict expects node payloads to be dict values"
                )
            node_map[str(local_id)] = GraphViewNodeProxy.from_dict(payload)

        edge_map: dict[str, GraphViewEdgeProxy] = {}
        for local_id, payload in raw_edges.items():
            if not isinstance(payload, dict):
                raise ValueError(
                    "GraphView.from_dict expects edge payloads to be dict values"
                )
            edge_map[str(local_id)] = GraphViewEdgeProxy.from_dict(payload)

        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            nodes=node_map,
            edges=edge_map,
        )

"""Shared graph helpers used internally by layout algorithms."""
from __future__ import annotations

from lks_utils.graph2d_layout.primitives import LayoutEdge2D

__all__: list[str] = []  # internal module, not exported from package


def build_adjacency(
    node_ids: list[str],
    edges: list[LayoutEdge2D],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return ``(succ, pred)`` adjacency sets for a set of node ids."""
    succ: dict[str, set[str]] = {n: set() for n in node_ids}
    pred: dict[str, set[str]] = {n: set() for n in node_ids}
    node_set = set(node_ids)
    for edge in edges:
        if edge.source_id in node_set and edge.target_id in node_set:
            succ[edge.source_id].add(edge.target_id)
            pred[edge.target_id].add(edge.source_id)
    return succ, pred


def build_components(
    node_ids: list[str],
    edges: list[LayoutEdge2D],
) -> list[list[str]]:
    """Split *node_ids* into undirected connected components.

    Returns a list of components, each a sorted list of node IDs.
    """
    neighbors: dict[str, set[str]] = {n: set() for n in node_ids}
    node_set = set(node_ids)
    for edge in edges:
        if edge.source_id in node_set and edge.target_id in node_set:
            neighbors[edge.source_id].add(edge.target_id)
            neighbors[edge.target_id].add(edge.source_id)

    remaining: set[str] = set(node_ids)
    components: list[list[str]] = []
    while remaining:
        root = min(remaining)
        stack = [root]
        remaining.remove(root)
        component: list[str] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for nxt in neighbors[current]:
                if nxt in remaining:
                    remaining.remove(nxt)
                    stack.append(nxt)
        components.append(sorted(component))
    return components


def topological_order_with_cycle_break(
    node_ids: list[str],
    succ: dict[str, set[str]],
    pred: dict[str, set[str]],
) -> list[str]:
    """Return a stable topological order, breaking cycles by preference.

    Cycles are broken by selecting the node with the highest
    ``out-degree - in-degree`` among remaining nodes (sources first).
    """
    remaining: set[str] = set(node_ids)
    indeg: dict[str, int] = {
        n: len([p for p in pred[n] if p in remaining]) for n in node_ids
    }
    order: list[str] = []

    while remaining:
        zeros = sorted(n for n in remaining if indeg[n] == 0)
        if zeros:
            current = zeros[0]
        else:
            current = max(
                remaining,
                key=lambda n: (
                    len([x for x in succ[n] if x in remaining])
                    - len([x for x in pred[n] if x in remaining]),
                    n,
                ),
            )
        remaining.remove(current)
        order.append(current)
        for nxt in succ[current]:
            if nxt in remaining:
                indeg[nxt] = max(0, indeg[nxt] - 1)

    return order


def segment_intersection(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    """Return ``True`` when segments a1-a2 and b1-b2 strictly cross."""

    def orient(
        p: tuple[float, float],
        q: tuple[float, float],
        r: tuple[float, float],
    ) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_seg(
        p: tuple[float, float],
        q: tuple[float, float],
        r: tuple[float, float],
    ) -> bool:
        return (
            min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
            and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
        )

    o1 = orient(a1, a2, b1)
    o2 = orient(a1, a2, b2)
    o3 = orient(b1, b2, a1)
    o4 = orient(b1, b2, a2)

    if (o1 > 0 > o2 or o1 < 0 < o2) and (o3 > 0 > o4 or o3 < 0 < o4):
        return True

    eps = 1e-9
    if abs(o1) < eps and on_seg(a1, b1, a2):
        return True
    if abs(o2) < eps and on_seg(a1, b2, a2):
        return True
    if abs(o3) < eps and on_seg(b1, a1, b2):
        return True
    if abs(o4) < eps and on_seg(b1, a2, b2):
        return True
    return False

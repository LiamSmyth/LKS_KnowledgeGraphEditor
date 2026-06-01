"""Private helper methods extracted from graph_tab.py."""
from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QMessageBox
from ulid import ULID

from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    NODE_TEXT_COLOR,
    REF_VALID_COLOR,
    SCENE_BACKGROUND_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.link_type_view_state import LinkTypeViewState
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID, LinkType
from lks_utils.knowledge.instance_validator import (
    VALIDATION_ERRORS_PROP,
    VALIDATION_STATUS_CANNOT_COMPILE,
    VALIDATION_STATUS_PROP,
    InstanceValidator,
)
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.graph_view_node_proxy import GraphViewNodeProxy
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.canvas.canvas_io import CanvasIO
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.operations.delete_safety_analyzer import analyze_delete_impact
from lks_utils.knowledge.data_interface.link_mutation_bridge import LinkMutationBridge
from lks_utils.knowledge.ui.graph_link_creation_state_machine import (
    GraphLinkCreationEvent,
    GraphLinkCreationState,
    transition_graph_link_creation_state,
)
from lks_utils.knowledge.ui.components.ref_aware_delete_dialog import QKnowledgeRefAwareDeleteDialog
from lks_utils.knowledge.ui.graph_layout_ops import layout_positions
from lks_utils.graph2d_layout.algorithms.networkx_spread_node_layout_algorithm2d import (
    NetworkXSpreadNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D
from lks_utils.knowledge.ui.widgets.graph_canvas import (
    BatchPlacementPayload,
    estimate_graph_node_size_for_proxy,
)
from lks_utils.knowledge.ui.widgets.graph_node_canvas_item import QKnowledgeGraphNodeCanvasItem
from lks_utils.gui_qt.base.async_task_runner import WorkerThread
from lks_utils.knowledge.ui.components import graph_tab as graph_tab_module


def _on_link_type_view_state_changed(self, view_state: object) -> None:
    if not isinstance(view_state, LinkTypeViewState):
        return
    self._link_type_view_state = view_state
    self._save_link_type_view_state_settings()
    self._canvas.apply_link_type_view_state(view_state)


def _on_set_traversal_direction(
    self,
    direction: Literal["forward", "back", "both"],
) -> None:
    self._traversal_direction = direction


def _on_apply_traversal_selected(self, action_key: str) -> None:
    current = self._current_graph_view
    if current is None:
        return

    current_node_ids = {proxy.global_id for proxy in current.nodes.values()}
    selected_local_ids: set[str] = set()
    if hasattr(self, "_selected_graph_node_local_ids"):
        try:
            selected_local_ids = {
                local_id
                for local_id in self._selected_graph_node_local_ids()
                if local_id in current.nodes
            }
        except Exception:
            selected_local_ids = set()

    if not selected_local_ids:
        active_item = self._canvas.active_selected_item()
        if isinstance(active_item, QKnowledgeGraphNodeCanvasItem):
            for local_id, item in self._canvas._local_node_items.items():  # noqa: SLF001
                if item is active_item and local_id in current.nodes:
                    selected_local_ids = {local_id}
                    break

    if not selected_local_ids:
        selected_global_ids = self._selected_canvas_ids & current_node_ids
        if selected_global_ids:
            for global_id in selected_global_ids:
                matching_locals = sorted(
                    local_id
                    for local_id, proxy in current.nodes.items()
                    if proxy.global_id == global_id
                )
                if not matching_locals:
                    continue
                if len(matching_locals) == 1:
                    selected_local_ids.add(matching_locals[0])
                    continue
                if self._active_canvas_id == global_id:
                    selected_local_ids.add(matching_locals[0])
                    continue
                selected_local_ids.add(matching_locals[0])

    if selected_local_ids:
        selected_ids = {
            current.nodes[local_id].global_id
            for local_id in selected_local_ids
            if local_id in current.nodes
        }
    else:
        selected_ids = set()
    if not selected_ids:
        return

    all_node_ids = {str(node.id) for node in self._session.list_nodes()}
    target_node_ids, force_active_target_ids = CanvasIO.compute_traversal_target_node_ids(
        graph_view=current,
        action_key=action_key,
        current_node_ids=current_node_ids,
        selected_local_ids=selected_local_ids,
        selected_ids=selected_ids,
        all_node_ids=all_node_ids,
        links=self._session.list_links(),
        allowed_link_type_ids=self._allowed_link_type_ids_for_traversal(),
        direction=self._traversal_direction,
    )

    self._apply_graph_node_subset(
        target_node_ids=target_node_ids,
        selected_ids=selected_ids,
        selected_local_ids=selected_local_ids,
        force_active_target_ids=force_active_target_ids,
        preserve_inactive_islands=(
            action_key.startswith("expand")
            or action_key in {"contract", "contract.adjacent", "contract.frontier"}
        ),
    )


def _allowed_link_type_ids_for_traversal(self) -> set[str] | None:
    """Return allowed link-type ids for traversal, or None for filterless mode.

    Filterless mode is active when either no filters are enabled or all
    filters are enabled.
    """
    link_type_ids = [
        str(link_type.id)
        for link_type in self._session.list_link_types()
    ]
    link_type_ids.append(SLOT_REF_LINK_TYPE_ID)
    if not link_type_ids:
        return None
    enabled = {
        link_type_id
        for link_type_id in link_type_ids
        if self._link_type_view_state.get_flags(link_type_id).filtered_out
    }
    if not enabled or len(enabled) == len(link_type_ids):
        return None
    return enabled


def _adjacency_for_traversal(
    self,
    *,
    allowed_link_type_ids: set[str] | None,
    direction: Literal["forward", "back", "both"],
) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {}
    for link in self._session.list_links():
        link_type_id = str(link.link_type_id)
        if allowed_link_type_ids is not None and link_type_id not in allowed_link_type_ids:
            continue
        source_id = str(link.source_node_id)
        target_id = str(link.target_node_id)
        if direction in {"forward", "both"}:
            adjacency.setdefault(source_id, set()).add(target_id)
        if direction in {"back", "both"}:
            adjacency.setdefault(target_id, set()).add(source_id)
    return adjacency


def _expanded_node_set(
    self,
    *,
    seed_ids: set[str],
    base_node_ids: set[str],
    allowed_link_type_ids: set[str] | None,
    max_depth: int | None,
) -> set[str]:
    visited = self._expanded_reachable_node_ids(
        seed_ids=seed_ids,
        allowed_link_type_ids=allowed_link_type_ids,
        max_depth=max_depth,
    )
    return base_node_ids | visited


def _expanded_reachable_node_ids(
    self,
    *,
    seed_ids: set[str],
    allowed_link_type_ids: set[str] | None,
    max_depth: int | None,
) -> set[str]:
    adjacency = self._adjacency_for_traversal(
        allowed_link_type_ids=allowed_link_type_ids,
        direction=self._traversal_direction,
    )
    visited = set(seed_ids)
    frontier = set(seed_ids)
    depth = 0
    while frontier and (max_depth is None or depth < max_depth):
        depth += 1
        next_frontier: set[str] = set()
        for node_id in frontier:
            next_frontier.update(adjacency.get(node_id, set()))
        next_frontier -= visited
        visited.update(next_frontier)
        frontier = next_frontier
    return visited


def _expand_frontier_seed_ids(
    self,
    *,
    seed_ids: set[str],
    base_node_ids: set[str],
    adjacency: dict[str, set[str]],
) -> set[str]:
    """Return the farthest visible frontier from seed_ids inside current view.

    This lets repeated one-step expands progressively advance outward from
    the selected component's edge instead of re-expanding from the literal
    selected nodes each click.
    """
    component = set(seed_ids)
    frontier = set(seed_ids)
    while frontier:
        next_frontier: set[str] = set()
        for node_id in frontier:
            for neighbor_id in adjacency.get(node_id, set()):
                if neighbor_id not in base_node_ids or neighbor_id in component:
                    continue
                component.add(neighbor_id)
                next_frontier.add(neighbor_id)
        frontier = next_frontier

    distances: dict[str, int] = {node_id: 0 for node_id in seed_ids}
    frontier = set(seed_ids)
    while frontier:
        next_frontier: set[str] = set()
        for node_id in frontier:
            node_distance = distances[node_id]
            for neighbor_id in adjacency.get(node_id, set()):
                if neighbor_id not in component or neighbor_id in distances:
                    continue
                distances[neighbor_id] = node_distance + 1
                next_frontier.add(neighbor_id)
        frontier = next_frontier

    if not distances:
        return set(seed_ids)
    max_distance = max(distances.values())
    return {
        node_id
        for node_id, distance in distances.items()
        if distance == max_distance
    }


def _contracted_node_set(
    self,
    *,
    seed_ids: set[str],
    base_node_ids: set[str],
    allowed_link_type_ids: set[str] | None,
    max_depth: int | None,
) -> set[str]:
    adjacency = self._adjacency_for_traversal(
        allowed_link_type_ids=allowed_link_type_ids,
        direction=self._traversal_direction,
    )
    component = set(seed_ids)
    frontier = set(seed_ids)
    while frontier:
        next_frontier: set[str] = set()
        for node_id in frontier:
            for neighbor_id in adjacency.get(node_id, set()):
                if neighbor_id not in base_node_ids or neighbor_id in component:
                    continue
                component.add(neighbor_id)
                next_frontier.add(neighbor_id)
        frontier = next_frontier

    if max_depth is None:
        return (base_node_ids - component) | seed_ids

    distances: dict[str, int] = {node_id: 0 for node_id in seed_ids}
    frontier = set(seed_ids)
    while frontier:
        next_frontier = set()
        for node_id in frontier:
            node_distance = distances[node_id]
            for neighbor_id in adjacency.get(node_id, set()):
                if neighbor_id not in component or neighbor_id in distances:
                    continue
                distances[neighbor_id] = node_distance + 1
                next_frontier.add(neighbor_id)
        frontier = next_frontier

    if not distances:
        return base_node_ids
    max_distance = max(distances.values())
    remove_ids = {
        node_id
        for node_id, distance in distances.items()
        if distance == max_distance and node_id not in seed_ids
    }
    return base_node_ids - remove_ids


def _apply_graph_node_subset(
    self,
    *,
    target_node_ids: set[str],
    selected_ids: set[str],
    selected_local_ids: set[str],
    force_active_target_ids: set[str],
    preserve_inactive_islands: bool,
) -> None:
    current = self._current_graph_view
    if current is None:
        return

    nodes_by_id = {
        str(node.id): node for node in self._session.list_nodes()
    }
    links_by_id = self._collect_links_by_id()
    type_nodes_by_id = {
        node_id: node
        for node_id, node in nodes_by_id.items()
        if node.category == "_type"
    }
    node_sizes = {
        node_id: estimate_graph_node_size_for_proxy(
            node=nodes_by_id.get(node_id),
            proxy_name=nodes_by_id[node_id].name if node_id in nodes_by_id else "",
            nodes_by_id=nodes_by_id,
            links_by_id=links_by_id,
            type_nodes_by_id=type_nodes_by_id,
        )
        for node_id in sorted(target_node_ids)
    }

    new_view = CanvasIO.apply_graph_node_subset_projection(
        graph_view=current,
        target_node_ids=target_node_ids,
        selected_ids=selected_ids,
        selected_local_ids=selected_local_ids,
        force_active_target_ids=force_active_target_ids,
        preserve_inactive_islands=preserve_inactive_islands,
        nodes_by_id=nodes_by_id,
        links=self._session.list_links(),
        node_sizes=node_sizes,
    )
    self._current_graph_view = new_view
    self._current_graph_view_id = str(new_view.id)
    self._persist_graph_view(new_view)
    self._refresh_canvas_nodes_from_repository(preserve_view=True)
    selected_local_ids_in_view = [
        local_id
        for local_id in sorted(selected_local_ids)
        if local_id in new_view.nodes
    ]
    if selected_local_ids_in_view and hasattr(self, "_select_canvas_nodes_by_local_ids"):
        self._select_canvas_nodes_by_local_ids(selected_local_ids_in_view)
        return
    self._select_canvas_nodes_by_global_ids(
        sorted(selected_ids & target_node_ids))


def _layout_incremental_expand_positions(
    self,
    *,
    target_node_ids: list[str],
    new_global_ids: list[str],
    existing_positions: dict[str, tuple[float, float]],
    node_sizes: dict[str, tuple[float, float]],
    edge_pairs: list[tuple[str, str]],
    anchor: tuple[float, float],
) -> dict[str, tuple[float, float]]:
    """Place newly-expanded nodes via a local NetworkX+spread algorithm."""
    if not new_global_ids:
        return {}

    anchor_x, anchor_y = anchor
    layout_nodes: list[LayoutNode2D] = []
    for node_id in target_node_ids:
        width, height = node_sizes.get(node_id, (140.0, 80.0))
        if node_id in existing_positions:
            x, y = existing_positions[node_id]
        else:
            x, y = (anchor_x, anchor_y)
        layout_nodes.append(
            LayoutNode2D(
                node_id=node_id,
                x=x,
                y=y,
                width=width,
                height=height,
            )
        )

    layout_edges = [
        LayoutEdge2D(
            edge_id=f"expand_edge_{index}",
            source_id=source_id,
            target_id=target_id,
        )
        for index, (source_id, target_id) in enumerate(edge_pairs)
    ]
    algorithm = NetworkXSpreadNodeLayoutAlgorithm2D(
        fixed_positions=existing_positions,
        spring_iterations=120,
        spring_k=190.0,
        spread_padding=26.0,
        spread_iterations=56,
        prevent_shape_overlaps=True,
        shape_overlap_padding=18.0,
        shape_overlap_iterations=80,
    )
    all_positions = algorithm.compute(layout_nodes, layout_edges)
    return {
        node_id: all_positions[node_id]
        for node_id in new_global_ids
        if node_id in all_positions
    }


def _reload_canvas_preserving_view(
    self,
    graph_view: GraphView,
    nodes_by_id: Mapping[str, Node],
    links_by_id: Mapping[str, LinkInstance],
    link_types_by_id: Mapping[str, LinkType],
) -> None:
    self._canvas.load_graph_view(
        graph_view,
        nodes_by_id=nodes_by_id,
        links_by_id=links_by_id,
        link_types_by_id=link_types_by_id,
        preserve_view=True,
    )


def _refresh_canvas_title(self, graph_view: GraphView) -> None:
    suffix = "*" if self._has_graph_canvas_dirty() else ""
    self._canvas_title.setText(f"{graph_view.name}{suffix}")


def _graph_canvas_node_ids(self) -> set[str]:
    if self._current_graph_view is None:
        return set()
    return {
        proxy.global_id for proxy in self._current_graph_view.nodes.values()
    }


def _has_graph_canvas_dirty(self) -> bool:
    # Graph edits are persisted immediately; there is no draft-state marker.
    return False


def _on_save(self) -> None:
    self.refresh_palettes()
    return None


def _on_save_all(self) -> None:
    self._on_save()


def load_graph_view_by_id(self, view_id: str) -> None:
    """Load a persisted GraphView by id from the active repository."""
    graph_view = CanvasIO.load_graph_view(self._session._io, view_id)  # noqa: SLF001
    nodes_by_id = {
        str(node.id): node for node in self._session.list_nodes()}
    self.set_graph_view(graph_view, nodes_by_id=nodes_by_id)


def _on_apply_layout_selected(self, algorithm_key: str) -> None:
    if self._current_graph_view is None:
        return
    selected_local_ids = set(self._selected_graph_node_local_ids())
    if not selected_local_ids:
        for global_id in self._selected_canvas_ids:
            matching_locals = sorted(
                local_id
                for local_id, proxy in self._current_graph_view.nodes.items()
                if proxy.global_id == global_id
            )
            if not matching_locals:
                continue
            if len(matching_locals) == 1:
                selected_local_ids.add(matching_locals[0])
                continue
            if self._active_canvas_id == global_id:
                selected_local_ids.add(matching_locals[0])
                continue
            selected_local_ids.add(matching_locals[0])
    selected_nodes = {
        local_id: proxy
        for local_id, proxy in self._current_graph_view.nodes.items()
        if local_id in selected_local_ids
    }
    if len(selected_nodes) < 2:
        return
    # Snapshot local ids before the canvas refresh.
    ids_to_restore_local = sorted(selected_local_ids)
    current_positions = {
        local_id: (proxy.x, proxy.y)
        for local_id, proxy in selected_nodes.items()
    }
    selected_local_ids = set(selected_nodes.keys())
    edge_pairs = [
        (
            edge.source_local_id,
            edge.target_local_id,
        )
        for edge in self._current_graph_view.edges.values()
        if edge.source_local_id in selected_local_ids
        and edge.target_local_id in selected_local_ids
    ]
    canvas_sizes = self._canvas.node_sizes_by_local_id()
    node_sizes = {
        local_id: size
        for local_id, size in canvas_sizes.items()
        if local_id in current_positions
    }
    next_positions = graph_tab_module.layout_positions(
        algorithm_key=algorithm_key,
        current_positions=current_positions,
        node_sizes=node_sizes,
        edge_pairs=edge_pairs,
    )
    local_position_updates = {
        local_id: next_positions.get(local_id, (proxy.x, proxy.y))
        for local_id, proxy in selected_nodes.items()
    }
    new_view = CanvasIO.apply_graph_view_local_position_updates(
        graph_view=self._current_graph_view,
        positions_by_local_id=local_position_updates,
    )

    self._current_graph_view = new_view
    self._current_graph_view_id = str(new_view.id)
    self._persist_graph_view(new_view)
    self._refresh_canvas_nodes_from_repository(preserve_view=True)
    if hasattr(self, "_select_canvas_nodes_by_local_ids"):
        self._select_canvas_nodes_by_local_ids(ids_to_restore_local)
        return
    self._select_canvas_nodes_by_global_ids(
        [
            selected_nodes[local_id].global_id
            for local_id in ids_to_restore_local
            if local_id in selected_nodes
        ]
    )


def _collect_links_by_id(self) -> dict[str, LinkInstance]:
    return {str(link.id): link for link in self._session.list_links()}


def _collect_link_types_by_id(self) -> dict[str, LinkType]:
    result = {
        str(link_type.id): link_type
        for link_type in self._session.list_link_types()
    }
    return result


def install_layout_engine_helpers(cls) -> None:
    cls._on_link_type_view_state_changed = _on_link_type_view_state_changed
    cls._on_set_traversal_direction = _on_set_traversal_direction
    cls._on_apply_traversal_selected = _on_apply_traversal_selected
    cls._allowed_link_type_ids_for_traversal = _allowed_link_type_ids_for_traversal
    cls._adjacency_for_traversal = _adjacency_for_traversal
    cls._expanded_node_set = _expanded_node_set
    cls._expanded_reachable_node_ids = _expanded_reachable_node_ids
    cls._expand_frontier_seed_ids = _expand_frontier_seed_ids
    cls._contracted_node_set = _contracted_node_set
    cls._apply_graph_node_subset = _apply_graph_node_subset
    cls._layout_incremental_expand_positions = _layout_incremental_expand_positions
    cls._reload_canvas_preserving_view = _reload_canvas_preserving_view
    cls._refresh_canvas_title = _refresh_canvas_title
    cls._graph_canvas_node_ids = _graph_canvas_node_ids
    cls._has_graph_canvas_dirty = _has_graph_canvas_dirty
    cls._on_save = _on_save
    cls._on_save_all = _on_save_all
    cls.load_graph_view_by_id = load_graph_view_by_id
    cls._on_apply_layout_selected = _on_apply_layout_selected
    cls._collect_links_by_id = _collect_links_by_id
    cls._collect_link_types_by_id = _collect_link_types_by_id


__all__ = ["install_layout_engine_helpers"]

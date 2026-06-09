"""Private helper methods extracted from graph_tab.py."""
from __future__ import annotations

import dataclasses
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QMessageBox
from ulid import ULID

from lks_utils.knowledge.default_theme import (
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
from lks_utils.knowledge.ui.widgets.graph_node_canvas_object import QKnowledgeGraphNodeCanvasObject
from lks_utils.gui_qt.base.async_task_runner import WorkerThread
from lks_utils.profiling import profile_action
from lks_utils.knowledge.ui.components import graph_tab as graph_tab_module


def _next_graph_instance_name(*, base_name: str, existing_names: set[str]) -> str:
    stripped = base_name.strip() or "Instance"
    existing_folded = {name.casefold()
                       for name in existing_names if name.strip()}
    if stripped.casefold() not in existing_folded:
        return stripped
    counter = 2
    while True:
        candidate = f"{stripped} {counter}"
        if candidate.casefold() not in existing_folded:
            return candidate
        counter += 1


def _on_instance_dropped(
    self,
    global_id: str,
    wx: float,
    wy: float,
    *,
    proxy_name_override: str | None = None,
) -> None:
    """Add a proxy for *global_id* at world position (*wx*, *wy*)."""
    current = self._current_graph_view
    preserved_view = self._canvas.view()
    if current is None:
        current = GraphView(
            id=str(ULID()),
            name="Default View",
            nodes={},
            edges={},
        )
    local_id = str(ULID())
    if proxy_name_override is not None:
        cached_name = proxy_name_override
    else:
        try:
            cached_name = self._session.get_node(global_id).name
        except KeyError:
            cached_name = ""
    proxy = GraphViewNodeProxy(
        global_id=global_id, x=wx, y=wy, cached_name=cached_name)
    new_nodes = {**current.nodes, local_id: proxy}
    new_view = dataclasses.replace(current, nodes=new_nodes)
    nodes_by_id = {
        str(node.id): node for node in self._session.list_nodes()}
    links_by_id = self._collect_links_by_id()
    if self._current_graph_view is None or not self._canvas._local_node_objects:  # noqa: SLF001
        self.set_graph_view(
            new_view,
            nodes_by_id=nodes_by_id,
            preserve_view=True,
        )
        if preserved_view is not None:
            self._canvas.set_view(preserved_view)
            self._canvas.lock_view(preserved_view)
            QTimer.singleShot(
                0, lambda view=preserved_view: self._canvas.lock_view(view))
    else:
        self._current_graph_view = new_view
        self._current_graph_view_id = str(new_view.id)
        self._canvas.add_node_item_fast(
            local_id=local_id,
            proxy=proxy,
            node=nodes_by_id.get(global_id),
            nodes_by_id=nodes_by_id,
            links_by_id=links_by_id,
        )
        if preserved_view is not None:
            self._canvas.lock_view(preserved_view)

    # Persist only the changed graph-view JSON. Using apply_mutation here
    # causes a full repository deepcopy + validation/index work that can
    # stall the UI when dropping nodes into large repositories.
    self._current_graph_view = new_view
    self._current_graph_view_id = str(new_view.id)
    self._persist_graph_view(new_view)
    self._select_canvas_nodes_by_global_ids([global_id])


def _on_instances_dropped(self, payload: object) -> None:
    if not isinstance(payload, BatchPlacementPayload):
        return
    current = self._current_graph_view
    preserved_view = self._canvas.view()
    if current is None:
        current = GraphView(
            id=str(ULID()),
            name="Default View",
            nodes={},
            edges={},
        )
    dropped_instance_ids = list(payload.instance_ids)
    if not dropped_instance_ids:
        return

    drop_x = payload.drop_anchor.x()
    drop_y = payload.drop_anchor.y()
    nodes_by_id = {
        str(node.id): node for node in self._session.list_nodes()}
    links_by_id = self._collect_links_by_id()
    type_nodes_by_id = {
        node_id: node
        for node_id, node in nodes_by_id.items()
        if node.category == "_type"
    }
    dropped_node_sizes = {
        instance_id: estimate_graph_node_size_for_proxy(
            node=nodes_by_id.get(instance_id),
            proxy_name=nodes_by_id.get(
                instance_id).name if instance_id in nodes_by_id else "",
            nodes_by_id=nodes_by_id,
            links_by_id=links_by_id,
            type_nodes_by_id=type_nodes_by_id,
        )
        for instance_id in dropped_instance_ids
    }
    dummy_positions = {iid: (drop_x, drop_y)
                       for iid in dropped_instance_ids}
    grid_map = graph_tab_module.layout_positions(
        algorithm_key="grid",
        current_positions=dummy_positions,
        node_sizes=dropped_node_sizes,
    )
    planned_positions = [grid_map.get(
        iid, (drop_x, drop_y)) for iid in dropped_instance_ids]

    updated_nodes = dict(current.nodes)
    dropped_ids: list[str] = []
    proxies_to_add: list[tuple[str, GraphViewNodeProxy]] = []
    for instance_id, (x, y) in zip(dropped_instance_ids, planned_positions, strict=False):
        dropped_ids.append(instance_id)
        try:
            cached_name = self._session.get_node(instance_id).name
        except KeyError:
            cached_name = ""
        local_id = str(ULID())
        proxy = GraphViewNodeProxy(
            global_id=instance_id,
            x=x,
            y=y,
            cached_name=cached_name,
        )
        updated_nodes[local_id] = proxy
        proxies_to_add.append((local_id, proxy))

    new_view = dataclasses.replace(current, nodes=updated_nodes)
    self._current_graph_view = new_view
    self._current_graph_view_id = str(new_view.id)
    self._persist_graph_view(new_view)
    if current.nodes and self._canvas._local_node_objects:  # noqa: SLF001
        for local_id, proxy in proxies_to_add:
            self._canvas.add_node_item_fast(
                local_id=local_id,
                proxy=proxy,
                node=nodes_by_id.get(proxy.global_id),
                nodes_by_id=nodes_by_id,
                links_by_id=links_by_id,
            )
        if preserved_view is not None:
            self._canvas.lock_view(preserved_view)
    else:
        self._refresh_canvas_nodes_from_repository(preserve_view=True)
    self._select_canvas_nodes_by_global_ids(dropped_ids)


def _select_canvas_nodes_by_global_ids(self, node_ids: list[str]) -> None:
    if not node_ids:
        return
    with profile_action(
        "knowledge.graph_tab.selection",
        phase="restore_multi_select",
        metadata={"requested_ids": len(node_ids)},
    ) as action_scope:
        requested_ids = {str(node_id) for node_id in node_ids}
        items_to_select = [
            item
            for item in self._canvas._local_node_objects.values()  # noqa: SLF001
            if item.node_id in requested_ids
        ]
        if not items_to_select:
            action_scope.add_metadata("resolved_ids", 0)
            return
        # Use the last placed item as the preferred active selection so the
        # inspector update fires exactly once for the whole batch, not once
        # per item.
        self._canvas.scene.select_objects(
            items_to_select,
            additive=False,
            preferred_active=items_to_select[-1],
        )
        action_scope.add_metadata("resolved_ids", len(items_to_select))


def _select_canvas_nodes_by_local_ids(self, local_ids: list[str]) -> None:
    if not local_ids:
        return
    with profile_action(
        "knowledge.graph_tab.selection",
        phase="restore_multi_select_local",
        metadata={"requested_local_ids": len(local_ids)},
    ) as action_scope:
        items_to_select = [
            self._canvas._local_node_objects.get(local_id)  # noqa: SLF001
            for local_id in local_ids
        ]
        items_to_select = [
            item for item in items_to_select if item is not None]
        if not items_to_select:
            action_scope.add_metadata("resolved_local_ids", 0)
            return
        self._canvas.scene.select_objects(
            items_to_select,
            additive=False,
            preferred_active=items_to_select[-1],
        )
        action_scope.add_metadata("resolved_local_ids", len(items_to_select))


def _on_type_dropped(self, type_id: str, wx: float, wy: float) -> None:
    """Mint a new instance of *type_id* and add its proxy at (*wx*, *wy*)."""
    existing_instance_names = {
        instance.name.strip()
        for instance in self._session.iter_instances()
        if instance.name.strip()
    }
    try:
        type_node = self._session.get_node(type_id)
        category = str(type_node.props.get("instance_category", ""))
        instance_name = _next_graph_instance_name(
            base_name=type_node.name,
            existing_names=existing_instance_names,
        )
    except KeyError:
        category = ""
        instance_name = _next_graph_instance_name(
            base_name="Instance",
            existing_names=existing_instance_names,
        )

    new_instance = Node(
        category=category,
        type_id=NodeId.from_str(type_id),
        name=instance_name,
    )
    with self._own_repo_write_scope():
        self._session.upsert_node(new_instance)
    self._on_instance_dropped(str(new_instance.id), wx, wy)


def _on_canvas_objects_moved(self, items: list) -> None:
    """Persist updated proxy positions for moved graph node canvas objects."""
    if getattr(self._canvas, "_is_loading_graph_view", False):  # noqa: SLF001
        return
    if self._current_graph_view is None:
        return
    item_to_local: dict[int, str] = {
        id(it): local_id
        for local_id, it in self._canvas._local_node_objects.items()  # noqa: SLF001
    }
    updated_nodes = dict(self._current_graph_view.nodes)
    moved_positions: dict[str, tuple[float, float]] = {}
    changed = False
    for item in items:
        local_id = item_to_local.get(id(item))
        if local_id is None or not isinstance(item, QKnowledgeGraphNodeCanvasObject):
            continue
        b = item.bounds()
        moved_positions[local_id] = (b.x0, b.y0)
        cap_payload = item.serialize_capabilities()
        updated_nodes[local_id] = GraphViewNodeProxy(
            global_id=updated_nodes[local_id].global_id,
            x=b.x0,
            y=b.y0,
            cached_name=updated_nodes[local_id].cached_name,
            capabilities=cap_payload or None,
        )
        changed = True
    if not changed:
        return
    new_view = dataclasses.replace(
        self._current_graph_view, nodes=updated_nodes)
    persisted_view = self._persist_graph_view_node_positions(
        graph_view_id=str(new_view.id),
        positions_by_local_id=moved_positions,
        fallback_view=new_view,
    )
    self._current_graph_view = persisted_view
    self._current_graph_view_id = str(persisted_view.id)


def _persist_graph_view(self, view: GraphView) -> None:
    """Save graph view to repository; silently skips read-only repositories."""
    if self._session._repository_root is None:  # noqa: SLF001
        return
    try:
        with self._own_repo_write_scope():
            self._session.save_graph_view(view)
    except (PermissionError, OSError) as exc:
        logging.getLogger(__name__).warning(
            "Could not persist graph view %r to %s: %s",
            view.id,
            self._session._repository_root,  # noqa: SLF001
            exc,
        )


def _persist_graph_view_node_positions(
    self,
    *,
    graph_view_id: str,
    positions_by_local_id: dict[str, tuple[float, float]],
    fallback_view: GraphView,
) -> GraphView:
    """Persist only moved proxy positions for one graph view via CanvasIO."""
    if not positions_by_local_id:
        return fallback_view
    view_path = self._session.graph_view_relpath(graph_view_id)
    if view_path is None:
        self._persist_graph_view(fallback_view)
        return fallback_view

    try:
        with self._own_repo_write_scope():
            canvas_io = self._session.canvas_io_for(view_path)
            updated_view, _effects = canvas_io.patch_graph_view_node_positions(
                graph_view_id,
                positions_by_local_id,
            )
            return updated_view
    except KeyError as exc:
        logging.getLogger(__name__).warning(
            "Could not patch graph view %r positions via CanvasIO: %s",
            graph_view_id,
            exc,
        )
        self._persist_graph_view(fallback_view)
        return fallback_view
    except (PermissionError, OSError) as exc:
        logging.getLogger(__name__).warning(
            "Could not patch graph view %r positions via CanvasIO (read-only or locked): %s",
            graph_view_id,
            exc,
        )
        return fallback_view


def _on_remove_selected_proxies(self) -> None:
    """Remove selected graph-node proxies from the current GraphView."""
    if self._current_graph_view is None:
        return
    selected_node_items = [
        item
        for item in self._canvas.selected_objects()
        if isinstance(item, QKnowledgeGraphNodeCanvasObject)
    ]
    selected_node_item_set = set(selected_node_items)
    selected_local_ids: list[str] = [
        local_id
        for local_id, item in self._canvas._local_node_objects.items()  # noqa: SLF001
        if item in selected_node_item_set
    ]
    if not selected_local_ids:
        return
    for local_id in selected_local_ids:
        item = self._canvas._local_node_objects.pop(local_id)  # noqa: SLF001
        self._canvas.remove_object(item)
    updated_nodes = {
        k: v for k, v in self._current_graph_view.nodes.items()
        if k not in selected_local_ids
    }
    new_view = dataclasses.replace(
        self._current_graph_view, nodes=updated_nodes)
    self._current_graph_view = new_view
    self._current_graph_view_id = str(new_view.id)
    self._properties.clear()
    self._connections_panel.set_node(None)
    # Use the fast path that only writes this view's JSON file, avoiding the
    # full apply_mutation cost (deepcopy + reverse-ref rebuild + full repo
    # save + library/palette refresh cascade).  Identical strategy to
    # _on_canvas_objects_moved.
    self._persist_graph_view(new_view)


def install_canvas_object_factory_helpers(cls) -> None:
    cls._on_instance_dropped = _on_instance_dropped
    cls._on_instances_dropped = _on_instances_dropped
    cls._select_canvas_nodes_by_global_ids = _select_canvas_nodes_by_global_ids
    cls._select_canvas_nodes_by_local_ids = _select_canvas_nodes_by_local_ids
    cls._on_type_dropped = _on_type_dropped
    cls._on_canvas_objects_moved = _on_canvas_objects_moved
    cls._persist_graph_view = _persist_graph_view
    cls._persist_graph_view_node_positions = _persist_graph_view_node_positions
    cls._on_remove_selected_proxies = _on_remove_selected_proxies


__all__ = ["install_canvas_object_factory_helpers"]

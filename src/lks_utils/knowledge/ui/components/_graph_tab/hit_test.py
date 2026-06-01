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
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QMessageBox, QSplitter
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
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
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
from lks_utils.knowledge.ui.widgets.graph_link_canvas_item import QKnowledgeGraphLinkCanvasItem
from lks_utils.knowledge.ui.widgets.graph_node_canvas_item import QKnowledgeGraphNodeCanvasItem
from lks_utils.gui_qt.base.async_task_runner import WorkerThread
from lks_utils.profiling import profile_action


def _restore_splitter_sizes(splitter: QSplitter | None, sizes: list[int]) -> None:
    if splitter is None or not sizes:
        return
    try:
        if splitter.count() != len(sizes):
            return
        splitter.setSizes(sizes)
    except RuntimeError:
        return


def _restore_panel_min_width(panel: object, min_width: int) -> None:
    try:
        panel.setMinimumWidth(min_width)
    except RuntimeError:
        return


def _schedule_splitter_restore(
    splitter: QSplitter | None,
    sizes: list[int],
    *,
    delays_ms: tuple[int, ...] = (0, 25, 75),
) -> None:
    if splitter is None or not sizes:
        return
    for delay in delays_ms:
        QTimer.singleShot(
            delay,
            lambda splitter=splitter, sizes=list(sizes): _restore_splitter_sizes(
                splitter,
                sizes,
            ),
        )


def _schedule_panel_min_width_restore(
    panel: object,
    min_width: int | None,
    *,
    delays_ms: tuple[int, ...] = (0, 25, 75),
) -> None:
    if panel is None or min_width is None:
        return
    for delay in delays_ms:
        QTimer.singleShot(
            delay,
            lambda panel=panel, min_width=min_width: _restore_panel_min_width(
                panel,
                min_width,
            ),
        )


@contextmanager
def _preserve_selection_layout(self):
    outer_splitter = getattr(self, "_splitter", None)
    if not isinstance(outer_splitter, QSplitter):
        outer_splitter = None
    right_splitter = getattr(self, "_right_splitter", None)
    if not isinstance(right_splitter, QSplitter):
        right_splitter = None

    outer_sizes = outer_splitter.sizes() if outer_splitter is not None else []
    right_sizes = right_splitter.sizes() if right_splitter is not None else []
    properties_panel = getattr(self, "_properties", None)
    connections_panel = getattr(self, "_connections_panel", None)
    properties_min_width = (
        int(properties_panel.minimumWidth())
        if properties_panel is not None
        else None
    )
    connections_min_width = (
        int(connections_panel.minimumWidth())
        if connections_panel is not None
        else None
    )
    try:
        yield
    finally:
        _schedule_panel_min_width_restore(
            properties_panel,
            properties_min_width,
        )
        _schedule_panel_min_width_restore(
            connections_panel,
            connections_min_width,
        )
        _restore_splitter_sizes(outer_splitter, outer_sizes)
        _restore_splitter_sizes(right_splitter, right_sizes)
        _schedule_splitter_restore(outer_splitter, outer_sizes)
        _schedule_splitter_restore(right_splitter, right_sizes)


def _on_canvas_node_selected(self, node_id: str) -> None:
    with profile_action(
        "knowledge.graph_tab.selection",
        phase="node_selected",
        metadata={"node_id": node_id},
    ):
        with _preserve_selection_layout(self):
            try:
                node = self._session.get_node(node_id)
                node = self._properties.prepare_node_for_display(node)
            except KeyError:
                self._properties.clear()
                self._connections_panel.set_node(None)
                return
            self._properties.set_node(node)
            self._connections_panel.set_node(node)


def _on_canvas_link_selected(self, _link_id: str) -> None:
    """Keep inspector state coherent until link-inspector integration lands."""
    with profile_action(
        "knowledge.graph_tab.selection",
        phase="link_selected",
    ):
        with _preserve_selection_layout(self):
            self._properties.clear()
            self._connections_panel.set_node(None)


def _on_canvas_selection_changed(self) -> None:
    """Keep inspector in sync when active selection is cleared."""
    if self._canvas.active_selected_item() is not None:
        return
    with profile_action(
        "knowledge.graph_tab.selection",
        phase="selection_cleared",
    ):
        with _preserve_selection_layout(self):
            self._properties.clear()
            self._connections_panel.set_node(None)


def _on_canvas_selection_model_changed(
    self,
    selected_ids: object,
    active_id: object,
) -> None:
    selected: set[str] = set(selected_ids) if isinstance(
        selected_ids, set) else set()
    self._selected_canvas_ids = selected
    self._active_canvas_id = active_id if isinstance(
        active_id, str) else None
    self._layout_ribbon.set_selection_count(len(self._selected_canvas_ids))
    self._instance_palette.set_active_selection(self._active_canvas_id)
    self._queue_canvas_viewport_sidecar_write()


def _wire_node_card_actions(self) -> None:
    for item in self._canvas._local_node_items.values():  # noqa: SLF001
        item.configure_actions(
            on_save=None,
            on_revert=None,
            on_remove=self._on_node_card_remove,
            on_delete=self._on_node_card_delete,
            is_save_dirty=None,
        )


def _refresh_graph_validation_badges(self, changed_ids: set[str] | None = None) -> None:
    current = self._current_graph_view
    if current is None:
        return
    changed_filter = {str(node_id)
                      for node_id in changed_ids} if changed_ids else None
    nodes_by_id = {
        str(node.id): node for node in self._session.list_nodes()}
    validator = InstanceValidator(self._session._repository)  # noqa: SLF001
    for item in self._canvas._local_node_items.values():  # noqa: SLF001
        if changed_filter is not None and item.node_id not in changed_filter:
            continue
        node = nodes_by_id.get(item.node_id)
        warning_count, error_count, tooltip_text = self._validation_summary_for_node(
            node=node,
            validator=validator,
        )
        item.set_validation_issues(
            warning_count=warning_count,
            error_count=error_count,
            tooltip_text=tooltip_text,
        )


def _on_validation_changed(self, changed_ids: object) -> None:
    if not isinstance(changed_ids, (set, frozenset, list, tuple)):
        return
    normalized_ids = {str(node_id) for node_id in changed_ids}
    if not normalized_ids:
        return
    self._refresh_graph_validation_badges(changed_ids=normalized_ids)


def _validation_summary_for_node(
    self,
    *,
    node: Node | None,
    validator: InstanceValidator,
) -> tuple[int, int, str]:
    if node is None:
        return (0, 1, "Error:\n- Node not found in repository.")

    warning_lines: list[str] = []
    error_lines: list[str] = []

    version_issues = validator.version_issues(node)
    for key, message in sorted(version_issues.items()):
        warning_lines.append(f"- {key}: {message}")

    live_status = self._session.validation_index.status_for(str(node.id))
    if not live_status.is_valid:
        for reason in live_status.reasons:
            if isinstance(reason, str) and reason.strip():
                error_lines.append(f"- {reason}")

    tooltip_lines: list[str] = []
    if warning_lines:
        tooltip_lines.append("Warnings:")
        tooltip_lines.extend(warning_lines)
    if error_lines:
        if tooltip_lines:
            tooltip_lines.append("")
        tooltip_lines.append("Errors:")
        tooltip_lines.extend(error_lines)

    return (len(warning_lines), len(error_lines), "\n".join(tooltip_lines))


def _on_node_card_remove(self, node_id: str) -> None:
    self._select_canvas_node(node_id)
    self._on_clear_selected_proxies()


def _on_node_card_delete(self, node_id: str) -> None:
    self._select_canvas_node(node_id)
    self._on_delete_selected_nodes()


def _selected_graph_node_local_ids(self) -> list[str]:
    if self._current_graph_view is None:
        return []
    selected_node_items = [
        item
        for item in self._canvas.selected_items()
        if isinstance(item, QKnowledgeGraphNodeCanvasItem)
    ]
    selected_node_item_set = set(selected_node_items)
    return [
        local_id
        for local_id, item in self._canvas._local_node_items.items()  # noqa: SLF001
        if item in selected_node_item_set
    ]


def _graph_view_without_local_ids(
    self,
    local_ids_to_remove: set[str],
) -> GraphView | None:
    if self._current_graph_view is None:
        return None
    updated_nodes = {
        local_id: proxy
        for local_id, proxy in self._current_graph_view.nodes.items()
        if local_id not in local_ids_to_remove
    }
    updated_edges = {
        edge_local_id: edge
        for edge_local_id, edge in self._current_graph_view.edges.items()
        if edge.source_local_id not in local_ids_to_remove
        and edge.target_local_id not in local_ids_to_remove
    }
    return dataclasses.replace(
        self._current_graph_view,
        nodes=updated_nodes,
        edges=updated_edges,
    )


def _selected_graph_edge_local_ids(self) -> list[str]:
    if self._current_graph_view is None:
        return []
    selected_edge_items = [
        item
        for item in self._canvas.selected_items()
        if isinstance(item, QKnowledgeGraphLinkCanvasItem)
    ]
    selected_edge_item_set = set(selected_edge_items)
    return [
        local_id
        for local_id, item in self._canvas._edge_items.items()  # noqa: SLF001
        if item in selected_edge_item_set
    ]


def _graph_view_without_edge_local_ids(
    self,
    edge_local_ids_to_remove: set[str],
) -> GraphView | None:
    if self._current_graph_view is None:
        return None
    updated_edges = {
        edge_local_id: edge
        for edge_local_id, edge in self._current_graph_view.edges.items()
        if edge_local_id not in edge_local_ids_to_remove
    }
    return dataclasses.replace(self._current_graph_view, edges=updated_edges)


def _is_system_link_type_id(link_type_id: str) -> bool:
    return link_type_id in {
        SLOT_REF_LINK_TYPE_ID,
        EXTENDS_LINK_TYPE_ID,
        INSTANCE_OF_LINK_TYPE_ID,
    }


def _apply_pruned_graph_view(self, new_view: GraphView) -> None:
    self._current_graph_view = new_view
    self._current_graph_view_id = str(new_view.id)
    self._properties.clear()
    self._connections_panel.set_node(None)
    self._persist_graph_view(new_view)
    self._refresh_canvas_nodes_from_repository(preserve_view=True)


def _on_clear_selected_proxies(self) -> None:
    """Remove selected graph-node proxies from the current GraphView."""
    selected_local_ids = self._selected_graph_node_local_ids()
    if not selected_local_ids:
        return
    new_view = self._graph_view_without_local_ids(set(selected_local_ids))
    if new_view is None:
        return

    self._apply_pruned_graph_view(new_view)


def _on_delete_selected_nodes(self, delete_knowledge_objects: bool = False) -> None:
    if self._current_graph_view is None:
        return
    selected_edge_local_ids = self._selected_graph_edge_local_ids()
    if selected_edge_local_ids:
        selected_link_ids = {
            self._current_graph_view.edges[local_id].global_link_id
            for local_id in selected_edge_local_ids
            if local_id in self._current_graph_view.edges
        }
        if selected_link_ids:
            new_view = self._graph_view_without_edge_local_ids(
                set(selected_edge_local_ids))
            if new_view is not None:
                # Delete is always graph-view-local for links; Shift+Delete may
                # also delete backing link instances for non-system link types.
                deletable_link_ids = set(selected_link_ids)
                if delete_knowledge_objects:
                    links_by_id = self._collect_links_by_id()
                    deletable_link_ids = {
                        link_id
                        for link_id in selected_link_ids
                        if (
                            (link := links_by_id.get(link_id)) is not None
                            and not _is_system_link_type_id(str(link.link_type_id))
                        )
                    }

                with self._own_repo_write_scope():
                    if delete_knowledge_objects and deletable_link_ids:
                        def _mutate(repository) -> set[str]:
                            touched: set[str] = set()
                            for link_id in deletable_link_ids:
                                repository.delete_link(link_id)
                                touched.add(link_id)
                            return touched

                        self._apply_graph_repo_mutation(
                            "graph_tab_delete_selected_links", _mutate)
                    CanvasIO.save_graph_view(self._session._io, new_view)  # noqa: SLF001

                self._current_graph_view = new_view
                self._current_graph_view_id = str(new_view.id)
                if delete_knowledge_objects and deletable_link_ids:
                    self._session.notify_repository_mutated("graph_view")
                self._refresh_canvas_nodes_from_repository(preserve_view=True)
                self._properties.clear()
                self._connections_panel.set_node(None)
                return

    selected_local_ids = self._selected_graph_node_local_ids()
    if not selected_local_ids:
        return
    selected_node_ids = [
        self._current_graph_view.nodes[local_id].global_id
        for local_id in selected_local_ids
        if local_id in self._current_graph_view.nodes
    ]
    if not selected_node_ids:
        return

    impact = self._session._io.preview_delete_nodes(selected_node_ids)  # noqa: SLF001
    new_view = self._graph_view_without_local_ids(set(selected_local_ids))
    if new_view is None:
        return

    if impact.is_safe:
        node_id_set = set(selected_node_ids)

        def _mutate(repository) -> set[str]:
            touched: set[str] = set(node_id_set)
            for link in list(repository.list_links()):
                if (
                    str(link.source_node_id) in node_id_set
                    or str(link.target_node_id) in node_id_set
                ):
                    repository.delete_link(link.id)
                    touched.add(str(link.id))
            for node_id in node_id_set:
                repository.delete(node_id)
            return touched

        with self._own_repo_write_scope():
            self._apply_graph_repo_mutation(
                "graph_tab_delete_selection", _mutate)
            CanvasIO.save_graph_view(self._session._io, new_view)  # noqa: SLF001
        self._session.notify_repository_mutated("graph_view")
        self._current_graph_view = new_view
        self._current_graph_view_id = str(new_view.id)
        self._refresh_canvas_nodes_from_repository(preserve_view=True)
        self._properties.clear()
        self._connections_panel.set_node(None)
        return

    dialog = QKnowledgeRefAwareDeleteDialog(
        impact, self._session, parent=self)
    if dialog.exec() != dialog.DialogCode.Accepted:
        return
    self._apply_pruned_graph_view(new_view)


def _select_canvas_node(self, node_id: str) -> None:
    for item in reversed(list(self._canvas._local_node_items.values())):  # noqa: SLF001
        if item.node_id == node_id:
            self._canvas.select_item(item, additive=False)
            return


def _on_inspector_node_selection_requested(self, node_id: str) -> None:
    if self._current_graph_view is None:
        return
    if node_id not in {
        proxy.global_id for proxy in self._current_graph_view.nodes.values()
    }:
        active_item = self._canvas.active_selected_item()
        if isinstance(active_item, QKnowledgeGraphNodeCanvasItem):
            bounds = active_item.bounds()
            self._on_instance_dropped(
                node_id, bounds.x0 + 40.0, bounds.y0 + 40.0)
        else:
            self._on_instance_dropped(node_id, 120.0, 120.0)
    self._select_canvas_node(node_id)


def _select_canvas_link(self, link_id: str) -> None:
    for item in self._canvas._edge_items.values():  # noqa: SLF001
        if item.link_id == link_id:
            self._canvas.select_item(item, additive=False)
            return


def _refresh_canvas_nodes_from_repository(self, *, preserve_view: bool) -> None:
    current = self._current_graph_view
    if current is None:
        return
    nodes_by_id = {
        str(node.id): node for node in self._session.list_nodes()}
    self.set_graph_view(current, nodes_by_id=nodes_by_id,
                        preserve_view=preserve_view)


def _on_validation_focus_requested(self, node_id: str) -> None:
    self._canvas.flash_node_by_global_id(node_id)


def install_hit_test_helpers(cls) -> None:
    cls._on_canvas_node_selected = _on_canvas_node_selected
    cls._on_canvas_link_selected = _on_canvas_link_selected
    cls._on_canvas_selection_changed = _on_canvas_selection_changed
    cls._on_canvas_selection_model_changed = _on_canvas_selection_model_changed
    cls._wire_node_card_actions = _wire_node_card_actions
    cls._refresh_graph_validation_badges = _refresh_graph_validation_badges
    cls._on_validation_changed = _on_validation_changed
    cls._validation_summary_for_node = _validation_summary_for_node
    cls._on_node_card_remove = _on_node_card_remove
    cls._on_node_card_delete = _on_node_card_delete
    cls._selected_graph_node_local_ids = _selected_graph_node_local_ids
    cls._selected_graph_edge_local_ids = _selected_graph_edge_local_ids
    cls._graph_view_without_local_ids = _graph_view_without_local_ids
    cls._graph_view_without_edge_local_ids = _graph_view_without_edge_local_ids
    cls._apply_pruned_graph_view = _apply_pruned_graph_view
    cls._on_clear_selected_proxies = _on_clear_selected_proxies
    cls._on_delete_selected_nodes = _on_delete_selected_nodes
    cls._select_canvas_node = _select_canvas_node
    cls._on_inspector_node_selection_requested = _on_inspector_node_selection_requested
    cls._select_canvas_link = _select_canvas_link
    cls._refresh_canvas_nodes_from_repository = _refresh_canvas_nodes_from_repository
    cls._on_validation_focus_requested = _on_validation_focus_requested


__all__ = ["install_hit_test_helpers"]

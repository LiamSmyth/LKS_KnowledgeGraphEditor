"""Private helper methods extracted from graph_tab.py."""
from __future__ import annotations

import dataclasses
import time
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


def _node_category_for_link_validation(self, node_id: str) -> str | None:
    try:
        node = self._session.get_node(node_id)
    except KeyError:
        return None
    return node.category


def _on_link_source_drag_started(self, link_type_id: str) -> None:
    result = transition_graph_link_creation_state(
        self._link_creation_state,
        GraphLinkCreationEvent.BEGIN,
    )
    self._link_creation_state = result.next_state
    self._link_creation_link_type_id = link_type_id
    self._link_creation_source_node_id = None
    self._link_creation_hover_node_id = None
    self._link_creation_hover_world = None
    self._canvas.set_link_creation_modal_active(
        self._link_creation_state != GraphLinkCreationState.IDLE
    )
    self._canvas.set_link_creation_target_mode(False)
    self._apply_link_source_candidate_modulation()


def _on_link_source_drag_hovered(
    self,
    link_type_id: str,
    candidate_source_node_id: object,
) -> None:
    if self._link_creation_state != GraphLinkCreationState.SOURCE_SELECT:
        return
    if self._link_creation_link_type_id is None:
        return
    if link_type_id and link_type_id != self._link_creation_link_type_id:
        return
    self._link_creation_hover_node_id = (
        candidate_source_node_id if isinstance(
            candidate_source_node_id, str) else None
    )
    self._apply_link_source_candidate_modulation()


def _on_link_source_drop_finished(
    self,
    link_type_id: str,
    source_node_id: object,
) -> None:
    if self._link_creation_state != GraphLinkCreationState.SOURCE_SELECT:
        return
    if self._link_creation_link_type_id is None:
        return
    if link_type_id != self._link_creation_link_type_id:
        return
    source_id = source_node_id if isinstance(source_node_id, str) else None
    valid_source = (
        source_id is not None and self._is_valid_source_candidate(
            self._link_creation_link_type_id,
            source_id,
        )
    )
    result = transition_graph_link_creation_state(
        self._link_creation_state,
        GraphLinkCreationEvent.SOURCE_CONFIRM,
        valid_hit=valid_source,
    )
    self._link_creation_state = result.next_state
    self._link_creation_source_node_id = source_id if valid_source else None
    self._link_creation_hover_node_id = None
    self._link_creation_hover_world = None
    self._canvas.set_link_creation_modal_active(
        self._link_creation_state != GraphLinkCreationState.IDLE
    )
    self._canvas.set_link_creation_target_mode(
        self._link_creation_state == GraphLinkCreationState.TARGET_SELECT
    )
    if self._link_creation_state == GraphLinkCreationState.TARGET_SELECT:
        self._apply_link_target_candidate_modulation()
        return
    if self._link_creation_state != GraphLinkCreationState.SOURCE_SELECT:
        self._clear_link_source_candidate_modulation()


def _on_link_target_hovered(
    self,
    candidate_target_node_id: object,
    world_x: float,
    world_y: float,
) -> None:
    if self._link_creation_state != GraphLinkCreationState.TARGET_SELECT:
        return
    self._link_creation_hover_node_id = (
        candidate_target_node_id
        if isinstance(candidate_target_node_id, str)
        else None
    )
    self._link_creation_hover_world = (float(world_x), float(world_y))
    self._apply_link_target_candidate_modulation()


def _on_link_target_clicked(
    self,
    candidate_target_node_id: object,
    world_x: float,
    world_y: float,
) -> None:
    if self._link_creation_state != GraphLinkCreationState.TARGET_SELECT:
        return
    self._link_creation_hover_world = (float(world_x), float(world_y))
    target_node_id = (
        candidate_target_node_id
        if isinstance(candidate_target_node_id, str)
        else None
    )
    link_type_id = self._link_creation_link_type_id
    valid_target = (
        target_node_id is not None
        and link_type_id is not None
        and self._is_valid_target_candidate(link_type_id, target_node_id)
    )
    result = transition_graph_link_creation_state(
        self._link_creation_state,
        GraphLinkCreationEvent.TARGET_COMMIT,
        valid_hit=valid_target,
    )
    self._link_creation_state = result.next_state
    if valid_target and target_node_id is not None and link_type_id is not None:
        self._commit_link_creation(link_type_id, target_node_id)
    self._finalize_link_creation_modal_state()


def _on_link_creation_cancel_requested(self) -> None:
    if self._link_creation_state == GraphLinkCreationState.IDLE:
        return
    result = transition_graph_link_creation_state(
        self._link_creation_state,
        GraphLinkCreationEvent.CANCEL,
    )
    self._link_creation_state = result.next_state
    self._finalize_link_creation_modal_state()


def _finalize_link_creation_modal_state(self) -> None:
    self._link_creation_link_type_id = None
    self._link_creation_source_node_id = None
    self._link_creation_hover_node_id = None
    self._link_creation_hover_world = None
    self._canvas.set_link_creation_modal_active(False)
    self._canvas.set_link_creation_target_mode(False)
    self._canvas.clear_link_preview()
    self._clear_link_source_candidate_modulation()


def _commit_link_creation(self, link_type_id: str, target_node_id: str) -> None:
    source_node_id = self._link_creation_source_node_id
    current = self._current_graph_view
    if source_node_id is None or current is None:
        return
    source_local_id = self._local_id_for_global_node(
        current,
        source_node_id,
    )
    target_local_id = self._local_id_for_global_node(
        current,
        target_node_id,
    )
    if source_local_id is None or target_local_id is None:
        return
    link = None
    link_created = False
    link_type = self._link_type_for_id(link_type_id)
    link_bridge = LinkMutationBridge(self._session._io)  # noqa: SLF001
    try:
        link = link_bridge.create_ad_hoc_link(
            link_type_id=link_type_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
        )
        link_created = True
    except ValueError as exc:
        if "Duplicate link triple" in str(exc):
            link = self._find_existing_link(
                link_type_id, source_node_id, target_node_id
            )
        if link is None:
            return
    link_id = str(link.id)
    if link_type is None:
        link_type = self._link_type_for_id(link_type_id)
    new_edges = dict(current.edges)
    edge_local_id = str(ULID())
    new_edges[edge_local_id] = GraphViewEdgeProxy(
        global_link_id=link_id,
        source_local_id=source_local_id,
        target_local_id=target_local_id,
    )
    new_view = dataclasses.replace(current, edges=new_edges)
    self._current_graph_view = new_view
    self._current_graph_view_id = str(new_view.id)
    self._persist_graph_view(new_view)
    if link_created:
        self._session.notify_io_mutation("link")

    # Fast path: add the single edge to canvas without full rebuild.
    # This avoids clearing all graph items and rebuilding everything.
    self._canvas.add_edge_item_fast(
        edge_local_id=edge_local_id,
        source_local_id=source_local_id,
        target_local_id=target_local_id,
        link_id=link_id,
        link=link,
        link_type=link_type,
    )
    self._select_canvas_link(link_id)


def _find_existing_link(
    self,
    link_type_id: str,
    source_node_id: str,
    target_node_id: str,
) -> LinkInstance | None:
    """Find existing link matching the triple for duplicate detection."""
    for link in self._session.list_links():
        if (
            str(link.link_type_id) == link_type_id
            and str(link.source_node_id) == source_node_id
            and str(link.target_node_id) == target_node_id
        ):
            return link
    return None


def _local_id_for_global_node(graph_view: GraphView, node_id: str) -> str | None:
    for local_id, proxy in graph_view.nodes.items():
        if proxy.global_id == node_id:
            return local_id
    return None


def _link_type_for_id(self, link_type_id: str) -> LinkType | None:
    for link_type in self._session.list_link_types():
        if str(link_type.id) == link_type_id:
            return link_type
    return None


def _link_triple_exists(
    self, link_type_id: str, source_node_id: str, target_node_id: str
) -> bool:
    """Check if a directional link already exists (O(n) over existing links)."""
    for link in self._session.list_links():
        if (
            str(link.link_type_id) == link_type_id
            and str(link.source_node_id) == source_node_id
            and str(link.target_node_id) == target_node_id
        ):
            return True
    return False


def _is_link_allowed(
    self,
    link_type_id: str,
    source_node_id: str,
    target_node_id: str,
) -> bool:
    """Central validation: check if a directional link is allowed.

    Returns True if:
    - Link type exists
    - Source node exists and passes source category constraint
    - Target node exists and passes target category constraint
    - Target != source (no self-loops)
    - No existing link with same type in same direction (duplicate prevention)
    """
    # No self-loops
    if source_node_id == target_node_id:
        return False

    link_type = self._link_type_for_id(link_type_id)
    if link_type is None:
        return False

    source_category = self._node_category_for_link_validation(source_node_id)
    if source_category is None:
        return False
    if not self._matches_category_constraint(
        source_category,
        link_type.source_type_constraint,
    ):
        return False

    target_category = self._node_category_for_link_validation(target_node_id)
    if target_category is None:
        return False
    if not self._matches_category_constraint(
        target_category,
        link_type.target_type_constraint,
    ):
        return False

    # Prevent duplicate directional links (same type, same direction)
    if self._link_triple_exists(link_type_id, source_node_id, target_node_id):
        return False

    return True


def _is_valid_source_candidate(self, link_type_id: str, node_id: str) -> bool:
    link_type = self._link_type_for_id(link_type_id)
    if link_type is None:
        return False
    node_category = self._node_category_for_link_validation(node_id)
    if node_category is None:
        return False
    return self._matches_category_constraint(
        node_category,
        link_type.source_type_constraint,
    )


def _is_valid_target_candidate(self, link_type_id: str, node_id: str) -> bool:
    source_id = self._link_creation_source_node_id
    if source_id is None:
        return False
    return self._is_link_allowed(link_type_id, source_id, node_id)


def _matches_category_constraint(category: str, constraint: str | None) -> bool:
    if constraint is None or not constraint.strip():
        return True
    normalized = constraint.strip().casefold()
    if normalized == "any":
        return True
    if normalized == "type":
        return category == "_type"
    if normalized == "instance":
        return category != "_type"
    return category.casefold() == normalized


def _clear_link_source_candidate_modulation(self) -> None:
    for item in self._canvas._local_node_items.values():  # noqa: SLF001
        item.clear_visual_modulation()
    self._canvas.update()


def _apply_link_source_candidate_modulation(self) -> None:
    link_type_id = self._link_creation_link_type_id
    if self._link_creation_state != GraphLinkCreationState.SOURCE_SELECT or link_type_id is None:
        self._clear_link_source_candidate_modulation()
        return
    hover_node_id = self._link_creation_hover_node_id
    for item in self._canvas._local_node_items.values():  # noqa: SLF001
        valid = self._is_valid_source_candidate(link_type_id, item.node_id)
        if not valid:
            item.set_visual_modulation(opacity=0.42)
            continue
        if hover_node_id is not None and item.node_id != hover_node_id:
            item.set_visual_modulation(opacity=0.86)
            continue
        item.clear_visual_modulation()
    self._canvas.update()


def _apply_link_target_candidate_modulation(self) -> None:
    link_type_id = self._link_creation_link_type_id
    source_id = self._link_creation_source_node_id
    if (
        self._link_creation_state != GraphLinkCreationState.TARGET_SELECT
        or link_type_id is None
        or source_id is None
    ):
        self._canvas.clear_link_preview()
        self._clear_link_source_candidate_modulation()
        return
    hover_node_id = self._link_creation_hover_node_id
    for item in self._canvas._local_node_items.values():  # noqa: SLF001
        if item.node_id == source_id:
            item.clear_visual_modulation()
            continue
        valid = self._is_valid_target_candidate(link_type_id, item.node_id)
        if not valid:
            item.set_visual_modulation(opacity=0.42)
            continue
        if hover_node_id is not None and item.node_id != hover_node_id:
            item.set_visual_modulation(opacity=0.86)
            continue
        item.clear_visual_modulation()
    preview_target = (
        hover_node_id
        if hover_node_id is not None
        and self._is_valid_target_candidate(link_type_id, hover_node_id)
        else None
    )
    self._canvas.set_link_preview(
        source_node_id=source_id,
        target_node_id=preview_target,
        cursor_world=self._link_creation_hover_world,
        color=VALIDATION_ERROR_TEXT if preview_target is None else REF_VALID_COLOR,
    )
    self._canvas.update()


def install_link_router_helpers(cls) -> None:
    cls._on_link_source_drag_started = _on_link_source_drag_started
    cls._on_link_source_drag_hovered = _on_link_source_drag_hovered
    cls._on_link_source_drop_finished = _on_link_source_drop_finished
    cls._on_link_target_hovered = _on_link_target_hovered
    cls._on_link_target_clicked = _on_link_target_clicked
    cls._on_link_creation_cancel_requested = _on_link_creation_cancel_requested
    cls._finalize_link_creation_modal_state = _finalize_link_creation_modal_state
    cls._commit_link_creation = _commit_link_creation
    cls._find_existing_link = _find_existing_link
    cls._local_id_for_global_node = staticmethod(_local_id_for_global_node)
    cls._link_type_for_id = _link_type_for_id
    cls._link_triple_exists = _link_triple_exists
    cls._is_link_allowed = _is_link_allowed
    cls._is_valid_source_candidate = _is_valid_source_candidate
    cls._is_valid_target_candidate = _is_valid_target_candidate
    cls._node_category_for_link_validation = _node_category_for_link_validation
    cls._matches_category_constraint = staticmethod(
        _matches_category_constraint)
    cls._clear_link_source_candidate_modulation = _clear_link_source_candidate_modulation
    cls._apply_link_source_candidate_modulation = _apply_link_source_candidate_modulation
    cls._apply_link_target_candidate_modulation = _apply_link_target_candidate_modulation


__all__ = ["install_link_router_helpers"]

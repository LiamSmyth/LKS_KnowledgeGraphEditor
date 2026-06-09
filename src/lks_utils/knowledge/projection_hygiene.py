"""Projection hygiene — keep placed canvas rows consistent with KB truth."""
from __future__ import annotations

from typing import Any

from lks_utils.knowledge.canvas.canvas_document import CanvasDocument
from lks_utils.knowledge.io.mutation_policy import CanvasHygieneHint
from lks_utils.knowledge.knowledge_change_event import KnowledgeChangeEvent
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.graph_view_node_proxy import GraphViewNodeProxy


class ProjectionHygiene:
    """Controller-side hygiene driven by KB effects — never auto-expands canvas."""

    def apply_to_canvas_document(
        self,
        document: CanvasDocument,
        *,
        hint: CanvasHygieneHint,
        event: KnowledgeChangeEvent | None = None,
        knowledge_io: Any | None = None,
    ) -> CanvasDocument | None:
        """Return an updated canvas document or None when unchanged."""
        if hint == CanvasHygieneHint.NONE or event is None:
            return None

        entity_id = event.entity_id
        if hint is CanvasHygieneHint.REMOVE_PLACEMENTS:
            return self._remove_node_placements(document, entity_id)
        if hint is CanvasHygieneHint.REMOVE_KB_EDGE:
            return self._remove_link_edge(document, entity_id)
        if hint is CanvasHygieneHint.SYNC_KB_EDGE:
            if knowledge_io is None:
                return None
            return self._sync_link_endpoints(document, entity_id, knowledge_io)
        if hint is CanvasHygieneHint.CACHED_NAME_REFRESH:
            if knowledge_io is None:
                return None
            return self._refresh_cached_names(document, entity_id, knowledge_io)
        return None

    def apply_to_graph_view(
        self,
        graph_view: GraphView,
        *,
        hint: CanvasHygieneHint,
        event: KnowledgeChangeEvent | None = None,
        knowledge_io: Any | None = None,
    ) -> GraphView | None:
        """Return an updated graph view or None when unchanged."""
        if hint == CanvasHygieneHint.NONE or event is None:
            return None

        entity_id = event.entity_id
        if hint is CanvasHygieneHint.REMOVE_PLACEMENTS:
            return self._remove_graph_node_placements(graph_view, entity_id)
        if hint is CanvasHygieneHint.REMOVE_KB_EDGE:
            return self._remove_graph_link_edges(graph_view, entity_id)
        if hint is CanvasHygieneHint.SYNC_KB_EDGE:
            if knowledge_io is None:
                return None
            return self._sync_graph_link_endpoints(graph_view, entity_id, knowledge_io)
        if hint is CanvasHygieneHint.CACHED_NAME_REFRESH:
            if knowledge_io is None:
                return None
            return self._refresh_graph_cached_names(graph_view, entity_id, knowledge_io)
        return None

    @staticmethod
    def _remove_node_placements(document: CanvasDocument, node_id: str) -> CanvasDocument | None:
        filtered: list[dict[str, Any]] = []
        touched = False
        for obj in document.objects:
            payload = dict(obj)
            item_type = payload.get("type")
            if item_type == "knowledge.kb_node" and payload.get("node_id") == node_id:
                touched = True
                continue
            if item_type == "knowledge.kb_edge":
                if payload.get("from_node_id") == node_id or payload.get("to_node_id") == node_id:
                    touched = True
                    continue
            filtered.append(payload)
        if not touched:
            return None
        return CanvasDocument(
            version=document.version,
            objects=filtered,
            metadata=document.metadata,
            overlays=document.overlays,
            bookmarks=document.bookmarks,
        )

    @staticmethod
    def _remove_link_edge(document: CanvasDocument, link_id: str) -> CanvasDocument | None:
        filtered: list[dict[str, Any]] = []
        touched = False
        for obj in document.objects:
            payload = dict(obj)
            if payload.get("type") == "knowledge.kb_edge" and payload.get("link_id") == link_id:
                touched = True
                continue
            filtered.append(payload)
        if not touched:
            return None
        return CanvasDocument(
            version=document.version,
            objects=filtered,
            metadata=document.metadata,
            overlays=document.overlays,
            bookmarks=document.bookmarks,
        )

    @staticmethod
    def _sync_link_endpoints(
        document: CanvasDocument,
        link_id: str,
        knowledge_io: Any,
    ) -> CanvasDocument | None:
        link = knowledge_io.repository.find_link(link_id)
        if link is None:
            return None
        updated_objects: list[dict[str, Any]] = []
        touched = False
        for obj in document.objects:
            payload = dict(obj)
            if payload.get("type") == "knowledge.kb_edge" and payload.get("link_id") == link_id:
                style = dict(payload.get("style", {}))
                payload = {
                    "type": "knowledge.kb_edge",
                    "link_id": link_id,
                    "from_node_id": str(link.source_node_id),
                    "to_node_id": str(link.target_node_id),
                }
                if style:
                    payload["style"] = style
                touched = True
            updated_objects.append(payload)
        if not touched:
            return None
        return CanvasDocument(
            version=document.version,
            objects=updated_objects,
            metadata=document.metadata,
            overlays=document.overlays,
            bookmarks=document.bookmarks,
        )

    @staticmethod
    def _refresh_cached_names(
        document: CanvasDocument,
        node_id: str,
        knowledge_io: Any,
    ) -> CanvasDocument | None:
        node = knowledge_io.find_node(node_id)
        if node is None:
            return None
        cached_name = str(getattr(node, "name", "") or node_id)
        updated_objects: list[dict[str, Any]] = []
        touched = False
        for obj in document.objects:
            payload = dict(obj)
            if payload.get("type") == "knowledge.kb_node" and payload.get("node_id") == node_id:
                if payload.get("cached_name") != cached_name:
                    payload["cached_name"] = cached_name
                    touched = True
            updated_objects.append(payload)
        if not touched:
            return None
        return CanvasDocument(
            version=document.version,
            objects=updated_objects,
            metadata=document.metadata,
            overlays=document.overlays,
            bookmarks=document.bookmarks,
        )

    @staticmethod
    def _remove_graph_node_placements(graph_view: GraphView, node_id: str) -> GraphView | None:
        local_ids_to_remove = {
            local_id
            for local_id, proxy in graph_view.nodes.items()
            if proxy.global_id == node_id
        }
        if not local_ids_to_remove:
            return None
        updated_nodes = {
            local_id: proxy
            for local_id, proxy in graph_view.nodes.items()
            if local_id not in local_ids_to_remove
        }
        updated_edges = {
            edge_id: edge
            for edge_id, edge in graph_view.edges.items()
            if edge.source_local_id not in local_ids_to_remove
            and edge.target_local_id not in local_ids_to_remove
        }
        return GraphView(
            id=graph_view.id,
            name=graph_view.name,
            nodes=updated_nodes,
            edges=updated_edges,
        )

    @staticmethod
    def _remove_graph_link_edges(graph_view: GraphView, link_id: str) -> GraphView | None:
        updated_edges = {
            edge_id: edge
            for edge_id, edge in graph_view.edges.items()
            if edge.global_link_id != link_id
        }
        if len(updated_edges) == len(graph_view.edges):
            return None
        return GraphView(
            id=graph_view.id,
            name=graph_view.name,
            nodes=dict(graph_view.nodes),
            edges=updated_edges,
        )

    @staticmethod
    def _sync_graph_link_endpoints(
        graph_view: GraphView,
        link_id: str,
        knowledge_io: Any,
    ) -> GraphView | None:
        link = knowledge_io.repository.find_link(link_id)
        if link is None:
            return None
        global_to_local = {
            proxy.global_id: local_id for local_id, proxy in graph_view.nodes.items()
        }
        source_local = global_to_local.get(str(link.source_node_id))
        target_local = global_to_local.get(str(link.target_node_id))
        if source_local is None or target_local is None:
            return None
        updated_edges = dict(graph_view.edges)
        touched = False
        for edge_id, edge in graph_view.edges.items():
            if edge.global_link_id != link_id:
                continue
            if edge.source_local_id == source_local and edge.target_local_id == target_local:
                continue
            updated_edges[edge_id] = type(edge)(
                global_link_id=edge.global_link_id,
                source_local_id=source_local,
                target_local_id=target_local,
            )
            touched = True
        if not touched:
            return None
        return GraphView(
            id=graph_view.id,
            name=graph_view.name,
            nodes=dict(graph_view.nodes),
            edges=updated_edges,
        )

    @staticmethod
    def _refresh_graph_cached_names(
        graph_view: GraphView,
        node_id: str,
        knowledge_io: Any,
    ) -> GraphView | None:
        node = knowledge_io.find_node(node_id)
        if node is None:
            return None
        cached_name = str(getattr(node, "name", "") or node_id)
        updated_nodes = dict(graph_view.nodes)
        touched = False
        for local_id, proxy in graph_view.nodes.items():
            if proxy.global_id != node_id:
                continue
            if proxy.cached_name == cached_name:
                continue
            updated_nodes[local_id] = GraphViewNodeProxy(
                global_id=proxy.global_id,
                x=proxy.x,
                y=proxy.y,
                cached_name=cached_name,
            )
            touched = True
        if not touched:
            return None
        return GraphView(
            id=graph_view.id,
            name=graph_view.name,
            nodes=updated_nodes,
            edges=dict(graph_view.edges),
        )


__all__ = ["ProjectionHygiene"]

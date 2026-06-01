"""CanvasIO projection layer between KnowledgeIO events and canvas documents."""
from __future__ import annotations

import dataclasses
import json
from collections import defaultdict, deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Protocol

from ulid import ULID

from lks_utils.graph2d_layout.algorithms import (
    CircularNodeLayoutAlgorithm2D,
    ConstrainedForceDirectedNodeLayoutAlgorithm2D,
    GridNodeLayoutAlgorithm2D,
    LaneNodeLayoutAlgorithm2D,
    NetworkXSpreadNodeLayoutAlgorithm2D,
    TreeNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.overlap_resolver2d import OverlapResolver2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D
from lks_utils.knowledge.canvas.canvas_document import (
    CanvasDocument,
    load_canvas_document,
    save_canvas_document,
)
from lks_utils.knowledge.knowledge_change_event import KnowledgeChangeEvent
from lks_utils.knowledge.knowledge_change_listener import KnowledgeChangeListener
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.graph_view_node_proxy import GraphViewNodeProxy


class _KnowledgeIOSubscriber(Protocol):
    """Subset of KnowledgeIO required by CanvasIO."""

    @property
    def repository(self) -> Any:
        """Knowledge repository snapshot accessor."""

    def subscribe(self, listener: KnowledgeChangeListener) -> None:
        """Register one listener for knowledge change events."""


class CanvasIO(KnowledgeChangeListener):
    """Canvas projection service bound to one ``.kbview.json`` view file."""

    def __init__(
        self,
        view_path: str | Path,
        knowledge_io: _KnowledgeIOSubscriber,
    ) -> None:
        self._view_path: Path = Path(view_path)
        self._knowledge_io: _KnowledgeIOSubscriber = knowledge_io
        self._knowledge_io.subscribe(self)

    @property
    def view_path(self) -> Path:
        """Absolute or relative path to the bound canvas view file."""
        return self._view_path

    def load_document(self) -> CanvasDocument:
        """Return the current canvas document for this view path."""
        return self._load_document()

    def save_document(self, document: CanvasDocument) -> None:
        """Persist a full canvas document through CanvasIO."""
        self._save_document(document)

    def read_viewport_sidecar(self) -> dict[str, Any] | None:
        """Return parsed viewport sidecar payload when present and valid."""
        sidecar_path = self._sidecar_path()
        if not sidecar_path.exists():
            return None
        try:
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return dict(payload)

    def read_view_fallback(self) -> dict[str, float]:
        """Return center/zoom fallback from canvas view payload when available."""
        view_payload: dict[str, Any] | None = None
        if self._view_path.exists():
            try:
                raw_payload = json.loads(
                    self._view_path.read_text(encoding="utf-8"))
            except Exception:
                raw_payload = None
            if isinstance(raw_payload, dict):
                candidate_view = raw_payload.get("view")
                if isinstance(candidate_view, dict):
                    view_payload = candidate_view
                if view_payload is None:
                    metadata_obj = raw_payload.get("metadata")
                    if isinstance(metadata_obj, dict):
                        nested_view = metadata_obj.get("view")
                        if isinstance(nested_view, dict):
                            view_payload = nested_view

        if view_payload is None:
            document = self._load_document()
            metadata_obj = document.metadata.get("view")
            if isinstance(metadata_obj, dict):
                view_payload = metadata_obj

        if view_payload is None:
            return {"center_x": 0.0, "center_y": 0.0, "zoom": 1.0}

        return {
            "center_x": float(view_payload.get("center_x", view_payload.get("x", 0.0))),
            "center_y": float(view_payload.get("center_y", view_payload.get("y", 0.0))),
            "zoom": float(view_payload.get("zoom", 1.0)),
        }

    def get_canvas_graph_state(self) -> dict[str, Any]:
        """Return normalized canvas graph state (nodes/edges/bounds)."""
        document = self._load_document()
        node_rows: list[dict[str, Any]] = []
        node_id_to_local: dict[str, str] = {}
        for index, item in enumerate(document.items):
            if item.get("type") != "knowledge.kb_node":
                continue
            node_id = str(item.get("node_id", ""))
            if not node_id:
                continue
            node = self._knowledge_io.repository.find_node(node_id)
            node_name = node.name if node is not None else node_id
            local_id = f"kb_node_{index}"
            node_id_to_local[node_id] = local_id
            node_rows.append(
                {
                    "local_id": local_id,
                    "node_id": node_id,
                    "name": node_name,
                    "x": float(item.get("x", 0.0)),
                    "y": float(item.get("y", 0.0)),
                    "w": float(item.get("width", item.get("w", 240.0))),
                    "h": float(item.get("height", item.get("h", 80.0))),
                }
            )

        edge_rows: list[dict[str, Any]] = []
        for index, item in enumerate(document.items):
            if item.get("type") != "knowledge.kb_edge":
                continue
            from_node_id = str(item.get("from_node_id", ""))
            to_node_id = str(item.get("to_node_id", ""))
            if not from_node_id or not to_node_id:
                continue
            edge_rows.append(
                {
                    "local_id": f"kb_edge_{index}",
                    "link_id": str(item.get("link_id", "")) or None,
                    "source_local_id": node_id_to_local.get(from_node_id),
                    "target_local_id": node_id_to_local.get(to_node_id),
                    "source_node_id": from_node_id,
                    "target_node_id": to_node_id,
                }
            )

        bbox = self._compute_bbox(node_rows)
        return {
            "view_format": "kb_canvas",
            "view_path": str(self._view_path),
            "nodes": node_rows,
            "edges": edge_rows,
            "bbox": bbox,
        }

    def export_canvas_png(
        self,
        output_path: str | Path,
        *,
        width: int = 1600,
        height: int = 1000,
        padding: int = 64,
    ) -> dict[str, Any]:
        """Render a full-graph PNG snapshot for this canvas view."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:
            raise ImportError(
                "Pillow is required for export_canvas_png") from exc

        state = self.get_canvas_graph_state()
        nodes = state["nodes"]
        edges = state["edges"]
        bbox = state["bbox"]

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        image = Image.new("RGB", (int(width), int(height)), (16, 18, 24))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        sidecar = self.read_viewport_sidecar() or {}
        node_world_sizes = self._read_node_world_sizes_from_sidecar(sidecar)

        if nodes:
            world_w = max(1.0, bbox["max_x"] - bbox["min_x"])
            world_h = max(1.0, bbox["max_y"] - bbox["min_y"])
            scale_x = (float(width) - 2.0 * float(padding)) / world_w
            scale_y = (float(height) - 2.0 * float(padding)) / world_h
            scale = max(0.05, min(scale_x, scale_y))
        else:
            scale = 1.0

        def _to_px(wx: float, wy: float) -> tuple[float, float]:
            px = float(padding) + (wx - bbox["min_x"]) * scale
            py = float(padding) + (bbox["max_y"] - wy) * scale
            return px, py

        node_centers: dict[str, tuple[float, float]] = {}
        for node in nodes:
            left, top = _to_px(float(node["x"]), float(node["y"]))
            world_w, world_h = self._effective_world_size_for_render(
                node, node_world_sizes)
            node_w = world_w * scale
            node_h = world_h * scale
            local_id = str(node["local_id"])
            node_centers[local_id] = (left + node_w / 2.0, top + node_h / 2.0)

        for edge in edges:
            source_local = edge.get("source_local_id")
            target_local = edge.get("target_local_id")
            if not source_local or not target_local:
                continue
            source = node_centers.get(str(source_local))
            target = node_centers.get(str(target_local))
            if source is None or target is None:
                continue
            draw.line([source, target], fill=(95, 110, 140), width=2)

        for node in nodes:
            left, top = _to_px(float(node["x"]), float(node["y"]))
            world_w, world_h = self._effective_world_size_for_render(
                node, node_world_sizes)
            node_w = world_w * scale
            node_h = world_h * scale
            right = left + node_w
            bottom = top + node_h
            draw.rounded_rectangle(
                [left, top, right, bottom],
                radius=max(4.0, 8.0 * scale),
                fill=(34, 39, 50),
                outline=(130, 147, 180),
                width=2,
            )
            label = str(node.get("name") or node.get("node_id") or "node")
            draw.text((left + 8.0, top + 8.0),
                      label[:48], fill=(225, 228, 236), font=font)

        image.save(output)
        return {
            "output_path": str(output.resolve()),
            "width": int(width),
            "height": int(height),
            "nodes_rendered": len(nodes),
            "edges_rendered": len(edges),
            "view_format": state["view_format"],
        }

    def render_view(
        self,
        output_path: str | Path | None = None,
        *,
        width: int | None = None,
        height: int | None = None,
        padding: int = 0,
    ) -> dict[str, Any]:
        """Render a viewport-anchored PNG for this canvas view."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:
            raise ImportError("Pillow is required for render_view") from exc

        state = self.get_canvas_graph_state()
        nodes = state["nodes"]
        edges = state["edges"]
        bbox = state["bbox"]

        sidecar = self.read_viewport_sidecar() or {}
        viewport_resolution = sidecar.get("viewport_resolution")
        resolved_width = int(width) if width is not None else 0
        resolved_height = int(height) if height is not None else 0
        if isinstance(viewport_resolution, dict):
            if resolved_width <= 0:
                resolved_width = max(
                    1, int(float(viewport_resolution.get("width_px", 0.0))))
            if resolved_height <= 0:
                resolved_height = max(
                    1, int(float(viewport_resolution.get("height_px", 0.0))))
        if resolved_width <= 0:
            resolved_width = 1600
        if resolved_height <= 0:
            resolved_height = 1000

        if output_path is None or not str(output_path).strip():
            output = self._view_path.with_name(
                f"{self._view_path.stem}_render_view.png")
        else:
            output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        world_region_raw = sidecar.get("viewport_world_region")
        if isinstance(world_region_raw, dict):
            region = {
                "min_x": float(world_region_raw.get("min_x", bbox["min_x"])),
                "min_y": float(world_region_raw.get("min_y", bbox["min_y"])),
                "max_x": float(world_region_raw.get("max_x", bbox["max_x"])),
                "max_y": float(world_region_raw.get("max_y", bbox["max_y"])),
            }
        else:
            region = {
                "min_x": float(bbox["min_x"]),
                "min_y": float(bbox["min_y"]),
                "max_x": float(bbox["max_x"]),
                "max_y": float(bbox["max_y"]),
            }
        region_w = max(1e-6, region["max_x"] - region["min_x"])
        region_h = max(1e-6, region["max_y"] - region["min_y"])

        image = Image.new(
            "RGB", (resolved_width, resolved_height), (16, 18, 24))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        node_world_sizes = self._read_node_world_sizes_from_sidecar(sidecar)

        avail_w = max(1.0, float(resolved_width) - 2.0 * float(padding))
        avail_h = max(1.0, float(resolved_height) - 2.0 * float(padding))
        scale_x = avail_w / region_w
        scale_y = avail_h / region_h

        def _to_px(wx: float, wy: float) -> tuple[float, float]:
            px = float(padding) + (wx - region["min_x"]) * scale_x
            py = float(padding) + (region["max_y"] - wy) * scale_y
            return px, py

        node_centers: dict[str, tuple[float, float]] = {}
        for node in nodes:
            left, top = _to_px(float(node["x"]), float(node["y"]))
            world_w, world_h = self._effective_world_size_for_render(
                node, node_world_sizes)
            node_w = world_w * scale_x
            node_h = world_h * scale_y
            local_id = str(node["local_id"])
            node_centers[local_id] = (left + node_w / 2.0, top + node_h / 2.0)

        for edge in edges:
            source_local = edge.get("source_local_id")
            target_local = edge.get("target_local_id")
            if not source_local or not target_local:
                continue
            source = node_centers.get(str(source_local))
            target = node_centers.get(str(target_local))
            if source is None or target is None:
                continue
            draw.line([source, target], fill=(95, 110, 140), width=2)

        for node in nodes:
            left, top = _to_px(float(node["x"]), float(node["y"]))
            world_w, world_h = self._effective_world_size_for_render(
                node, node_world_sizes)
            node_w = world_w * scale_x
            node_h = world_h * scale_y
            right = left + node_w
            bottom = top + node_h
            draw.rounded_rectangle(
                [left, top, right, bottom],
                radius=max(4.0, 8.0 * min(scale_x, scale_y)),
                fill=(34, 39, 50),
                outline=(130, 147, 180),
                width=2,
            )
            label = str(node.get("name") or node.get("node_id") or "node")
            draw.text((left + 8.0, top + 8.0),
                      label[:48], fill=(225, 228, 236), font=font)

        image.save(output)
        return {
            "output_path": str(output.resolve()),
            "width": int(resolved_width),
            "height": int(resolved_height),
            "nodes_rendered": len(nodes),
            "edges_rendered": len(edges),
            "view_format": state["view_format"],
            "render_mode": "viewport_region",
        }

    def on_knowledge_change(self, event: KnowledgeChangeEvent) -> None:
        """Project incoming knowledge mutation events onto the canvas document."""
        if event.event_type == "node_upserted":
            self._handle_node_upserted(event.entity_id)
            return None
        if event.event_type in {"node_deleted", "node_removed"}:
            self._handle_node_removed(event.entity_id)
            return None
        if event.event_type == "link_upserted":
            self._handle_link_upserted(event.entity_id)
            return None
        if event.event_type in {"link_deleted", "link_removed"}:
            self._handle_link_removed(event.entity_id)
            return None
        if event.event_type == "link_type_upserted":
            self._handle_link_type_upserted(event.entity_id)
        return None

    def update_viewport_sidecar(
        self,
        *,
        center_x: float,
        center_y: float,
        zoom: float,
        visible_node_ids: list[str],
        selected_node_ids: list[str],
        gesture_complete: bool,
        rotation_radians: float | None = None,
        viewport_world_region: dict[str, float] | None = None,
        viewport_resolution: dict[str, float] | None = None,
        node_world_sizes: dict[str, dict[str, float]] | None = None,
    ) -> None:
        """Write the sidecar only when gesture completion is explicitly signaled."""
        if not gesture_complete:
            return None
        self.write_viewport_sidecar(
            center_x=center_x,
            center_y=center_y,
            zoom=zoom,
            visible_node_ids=visible_node_ids,
            selected_node_ids=selected_node_ids,
            rotation_radians=rotation_radians,
            viewport_world_region=viewport_world_region,
            viewport_resolution=viewport_resolution,
            node_world_sizes=node_world_sizes,
        )

    def write_viewport_sidecar(
        self,
        *,
        center_x: float,
        center_y: float,
        zoom: float,
        visible_node_ids: list[str],
        selected_node_ids: list[str],
        rotation_radians: float | None = None,
        viewport_world_region: dict[str, float] | None = None,
        viewport_resolution: dict[str, float] | None = None,
        node_world_sizes: dict[str, dict[str, float]] | None = None,
    ) -> None:
        """Persist ephemeral viewport state alongside the main canvas document."""
        payload = {
            "center_x": float(center_x),
            "center_y": float(center_y),
            "zoom": float(zoom),
            "visible_node_ids": list(visible_node_ids),
            "selected_node_ids": list(selected_node_ids),
        }
        if rotation_radians is not None:
            payload["rotation_radians"] = float(rotation_radians)
        if isinstance(viewport_world_region, dict):
            payload["viewport_world_region"] = {
                key: float(value)
                for key, value in viewport_world_region.items()
                if isinstance(key, str)
            }
        if isinstance(viewport_resolution, dict):
            payload["viewport_resolution"] = {
                key: float(value)
                for key, value in viewport_resolution.items()
                if isinstance(key, str)
            }
        if isinstance(node_world_sizes, dict):
            cleaned_sizes: dict[str, dict[str, float]] = {}
            for node_id, size_payload in node_world_sizes.items():
                if not isinstance(node_id, str) or not node_id.strip():
                    continue
                if not isinstance(size_payload, dict):
                    continue
                raw_w = size_payload.get("width")
                raw_h = size_payload.get("height")
                try:
                    width_value = float(raw_w)
                    height_value = float(raw_h)
                except Exception:
                    continue
                if width_value <= 0.0 or height_value <= 0.0:
                    continue
                cleaned_sizes[node_id] = {
                    "width": width_value,
                    "height": height_value,
                }
            if cleaned_sizes:
                payload["node_world_sizes"] = cleaned_sizes
        sidecar_path = self._sidecar_path()
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _read_node_world_sizes_from_sidecar(
        sidecar: dict[str, Any],
    ) -> dict[str, tuple[float, float]]:
        raw_sizes = sidecar.get("node_world_sizes")
        if not isinstance(raw_sizes, dict):
            return {}
        parsed: dict[str, tuple[float, float]] = {}
        for node_id, payload in raw_sizes.items():
            if not isinstance(node_id, str) or not node_id.strip():
                continue
            if not isinstance(payload, dict):
                continue
            raw_w = payload.get("width")
            raw_h = payload.get("height")
            try:
                width_value = float(raw_w)
                height_value = float(raw_h)
            except Exception:
                continue
            if width_value <= 0.0 or height_value <= 0.0:
                continue
            parsed[node_id] = (width_value, height_value)
        return parsed

    @staticmethod
    def _effective_world_size_for_render(
        node_row: dict[str, Any],
        node_world_sizes: dict[str, tuple[float, float]],
    ) -> tuple[float, float]:
        node_id = str(node_row.get("node_id", ""))
        overridden = node_world_sizes.get(node_id)
        if overridden is not None:
            return overridden
        return (float(node_row.get("w", 240.0)), float(node_row.get("h", 80.0)))

    def clear_view(self, *, clear_sidecar: bool = True) -> None:
        """Clear all canvas items for the bound view and optionally remove viewport sidecar."""
        document = self._load_document()
        self._save_document(
            CanvasDocument(
                version=document.version,
                items=[],
                metadata=document.metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )
        if clear_sidecar:
            sidecar_path = self._sidecar_path()
            if sidecar_path.exists():
                sidecar_path.unlink()

    @staticmethod
    def list_graph_views(knowledge_io: _KnowledgeIOSubscriber) -> list[GraphView]:
        """Return all graph views through CanvasIO boundary."""
        return knowledge_io.repository.list_graph_views()

    @staticmethod
    def load_graph_view(knowledge_io: _KnowledgeIOSubscriber, graph_view_id: str) -> GraphView:
        """Load one graph view through CanvasIO boundary."""
        return knowledge_io.repository.load_graph_view(graph_view_id)

    @staticmethod
    def save_graph_view(knowledge_io: _KnowledgeIOSubscriber, graph_view: GraphView) -> None:
        """Persist one graph view through CanvasIO boundary."""
        knowledge_io.repository.save_graph_view(graph_view)

    @staticmethod
    def delete_graph_view(knowledge_io: _KnowledgeIOSubscriber, graph_view_id: str) -> None:
        """Delete one graph view through CanvasIO boundary."""
        knowledge_io.repository.delete_graph_view(graph_view_id)

    @staticmethod
    def ensure_unique_graph_view_name(
        knowledge_io: _KnowledgeIOSubscriber,
        desired: str,
        *,
        exclude_id: str | None = None,
    ) -> str:
        """Return a unique graph-view name through CanvasIO boundary."""
        return knowledge_io.repository.ensure_unique_graph_view_name(
            desired,
            exclude_id=exclude_id,
        )

    @staticmethod
    def graph_view_relpath(
        knowledge_io: _KnowledgeIOSubscriber,
        graph_view_id: str,
    ) -> Path | None:
        """Return absolute graph-view JSON path if available."""
        rel = knowledge_io.repository.graph_view_relpath(graph_view_id)
        if rel is None:
            return None
        root = getattr(knowledge_io, "repository_root", None)
        if root is None:
            root = getattr(knowledge_io.repository, "_repo_root", None)
        if root is None:
            return None
        return (Path(root) / rel).resolve()

    @staticmethod
    def load_graph_view_from_repo_root(repo_root: Path, graph_view_id: str) -> GraphView:
        """Load one graph view from disk via CanvasIO boundary."""
        from lks_utils.knowledge.io.knowledge_io import KnowledgeIO

        io = KnowledgeIO.from_path(repo_root)
        return CanvasIO.load_graph_view(io, graph_view_id)

    @staticmethod
    def resolve_graph_membership_subset(
        *,
        graph_view: GraphView,
        target_node_ids: set[str],
        selected_local_ids: set[str],
        selected_ids: set[str],
        force_active_target_ids: set[str],
    ) -> dict[str, Any]:
        """Resolve active/inactive island membership for expand/contract operations.

        Policy:
        - Nodes can appear in multiple disconnected islands in one graph view.
                - Active island membership is local-id based (graph membership), not global-id based.
                - For selected islands, membership is deduped per global node id.
                - Traversal depth and direction are resolved by the caller; this helper only
                    applies island-aware projection to those targets.
        """
        local_neighbors: dict[str, set[str]] = {
            local_id: set() for local_id in graph_view.nodes.keys()
        }
        for edge in graph_view.edges.values():
            source_local = edge.source_local_id
            target_local = edge.target_local_id
            if source_local not in local_neighbors or target_local not in local_neighbors:
                continue
            local_neighbors[source_local].add(target_local)
            local_neighbors[target_local].add(source_local)

        components: list[set[str]] = []
        unvisited_local_ids = set(local_neighbors.keys())
        while unvisited_local_ids:
            seed_local = unvisited_local_ids.pop()
            component = {seed_local}
            frontier = {seed_local}
            while frontier:
                next_frontier: set[str] = set()
                for local_id in frontier:
                    for neighbor_local in local_neighbors.get(local_id, set()):
                        if neighbor_local in component:
                            continue
                        component.add(neighbor_local)
                        if neighbor_local in unvisited_local_ids:
                            unvisited_local_ids.remove(neighbor_local)
                        next_frontier.add(neighbor_local)
                frontier = next_frontier
            components.append(component)

        active_components: list[set[str]] = []
        inactive_components: list[set[str]] = []
        effective_selected_local_ids = set(selected_local_ids)
        if not effective_selected_local_ids and selected_ids:
            # Fallback: pick one local proxy per selected global id.
            # Avoid broad activation of every disconnected island that happens
            # to contain the same global node id.
            for global_id in sorted(selected_ids):
                candidate_locals = sorted(
                    local_id
                    for local_id, proxy in graph_view.nodes.items()
                    if proxy.global_id == global_id
                )
                if candidate_locals:
                    effective_selected_local_ids.add(candidate_locals[0])

        for component in components:
            if component & effective_selected_local_ids:
                active_components.append(component)
            else:
                inactive_components.append(component)

        inactive_local_ids = {
            local_id
            for component in inactive_components
            for local_id in component
        }
        active_local_ids = {
            local_id
            for component in active_components
            for local_id in component
        }

        active_existing_local_by_global: dict[str, str] = {}
        for component in active_components:
            per_component_first_local: dict[str, str] = {}
            for local_id in sorted(component):
                proxy = graph_view.nodes.get(local_id)
                if proxy is None:
                    continue
                if proxy.global_id in per_component_first_local:
                    continue
                per_component_first_local[proxy.global_id] = local_id
            for global_id, local_id in per_component_first_local.items():
                if global_id in active_existing_local_by_global:
                    continue
                active_existing_local_by_global[global_id] = local_id

        active_seed_global_ids = {
            graph_view.nodes[local_id].global_id
            for local_id in active_local_ids
            if local_id in graph_view.nodes
        }
        current_global_ids = {
            proxy.global_id
            for proxy in graph_view.nodes.values()
        }
        active_target_global_ids = (
            (target_node_ids & active_seed_global_ids)
            | (target_node_ids - current_global_ids)
            | set(force_active_target_ids)
        )

        return {
            "inactive_local_ids": inactive_local_ids,
            "active_local_ids": active_local_ids,
            "active_existing_local_by_global": active_existing_local_by_global,
            "active_target_global_ids": active_target_global_ids,
        }

    @staticmethod
    def adjacency_for_traversal(
        *,
        links: list[Any],
        allowed_link_type_ids: set[str] | None,
        direction: Literal["forward", "back", "both"],
    ) -> dict[str, set[str]]:
        adjacency: dict[str, set[str]] = {}
        for link in links:
            link_type_id = str(getattr(link, "link_type_id", ""))
            if allowed_link_type_ids is not None and link_type_id not in allowed_link_type_ids:
                continue
            source_id = str(getattr(link, "source_node_id", ""))
            target_id = str(getattr(link, "target_node_id", ""))
            if direction in {"forward", "both"}:
                adjacency.setdefault(source_id, set()).add(target_id)
            if direction in {"back", "both"}:
                adjacency.setdefault(target_id, set()).add(source_id)
        return adjacency

    @staticmethod
    def graph_local_island_adjacency(
        *,
        graph_view: GraphView,
        links_by_id: Mapping[str, Any],
        allowed_link_type_ids: set[str] | None,
    ) -> dict[str, set[str]]:
        """Return undirected local adjacency from currently-present graph edges."""
        adjacency: dict[str, set[str]] = {
            local_id: set() for local_id in graph_view.nodes.keys()
        }
        for edge in graph_view.edges.values():
            source_local = edge.source_local_id
            target_local = edge.target_local_id
            if source_local not in adjacency or target_local not in adjacency:
                continue
            if allowed_link_type_ids is not None:
                edge_link = links_by_id.get(str(edge.global_link_id))
                if edge_link is None:
                    continue
                edge_link_type = str(getattr(edge_link, "link_type_id", ""))
                if edge_link_type not in allowed_link_type_ids:
                    continue
            adjacency[source_local].add(target_local)
            adjacency[target_local].add(source_local)
        return adjacency

    @staticmethod
    def expand_frontier_seed_ids(
        *,
        seed_ids: set[str],
        base_node_ids: set[str],
        adjacency: dict[str, set[str]],
    ) -> set[str]:
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

    @staticmethod
    def expanded_reachable_node_ids(
        *,
        seed_ids: set[str],
        adjacency: dict[str, set[str]],
        max_depth: int | None,
    ) -> set[str]:
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

    @staticmethod
    def expanded_node_set(
        *,
        seed_ids: set[str],
        base_node_ids: set[str],
        adjacency: dict[str, set[str]],
        max_depth: int | None,
    ) -> set[str]:
        visited = CanvasIO.expanded_reachable_node_ids(
            seed_ids=seed_ids,
            adjacency=adjacency,
            max_depth=max_depth,
        )
        return base_node_ids | visited

    @staticmethod
    def contracted_node_set(
        *,
        seed_ids: set[str],
        base_node_ids: set[str],
        adjacency: dict[str, set[str]],
        max_depth: int | None,
    ) -> set[str]:
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

    @staticmethod
    def compute_traversal_target_node_ids(
        *,
        graph_view: GraphView,
        action_key: str,
        current_node_ids: set[str],
        selected_local_ids: set[str],
        selected_ids: set[str],
        all_node_ids: set[str],
        links: list[Any],
        allowed_link_type_ids: set[str] | None,
        direction: Literal["forward", "back", "both"],
    ) -> tuple[set[str], set[str]]:
        links_by_id = {str(getattr(link, "id", "")): link for link in links}
        knowledge_adjacency = CanvasIO.adjacency_for_traversal(
            links=links,
            allowed_link_type_ids=allowed_link_type_ids,
            direction=direction,
        )
        island_adjacency = CanvasIO.graph_local_island_adjacency(
            graph_view=graph_view,
            links_by_id=links_by_id,
            allowed_link_type_ids=allowed_link_type_ids,
        )

        island_local_ids = {
            local_id for local_id in selected_local_ids if local_id in graph_view.nodes
        }
        if not island_local_ids and selected_ids:
            for global_id in sorted(selected_ids):
                candidate_locals = sorted(
                    local_id
                    for local_id, proxy in graph_view.nodes.items()
                    if proxy.global_id == global_id
                )
                if candidate_locals:
                    island_local_ids.add(candidate_locals[0])
        if island_local_ids:
            frontier_local_ids = set(island_local_ids)
            while frontier_local_ids:
                next_frontier_local_ids: set[str] = set()
                for local_id in frontier_local_ids:
                    for neighbor_local_id in island_adjacency.get(local_id, set()):
                        if neighbor_local_id in island_local_ids:
                            continue
                        island_local_ids.add(neighbor_local_id)
                        next_frontier_local_ids.add(neighbor_local_id)
                frontier_local_ids = next_frontier_local_ids

        current_seed_ids = set(selected_ids)
        if not current_seed_ids:
            current_seed_ids = {
                graph_view.nodes[local_id].global_id
                for local_id in island_local_ids
                if local_id in graph_view.nodes
            }

        current_node_ids = set(current_node_ids)
        force_active_target_ids: set[str] = set()

        if action_key in {"expand", "expand.adjacent"}:
            frontier_local_ids = CanvasIO.expand_frontier_seed_ids(
                seed_ids=set(island_local_ids),
                base_node_ids=set(graph_view.nodes.keys()),
                adjacency=island_adjacency,
            )
            frontier_seeds = {
                graph_view.nodes[local_id].global_id
                for local_id in frontier_local_ids
                if local_id in graph_view.nodes
            }
            if not frontier_seeds:
                frontier_seeds = set(current_seed_ids)
            target_node_ids = CanvasIO.expanded_node_set(
                seed_ids=frontier_seeds,
                base_node_ids=current_node_ids,
                adjacency=knowledge_adjacency,
                max_depth=1,
            )
            force_active_target_ids = CanvasIO.expanded_reachable_node_ids(
                seed_ids=frontier_seeds,
                adjacency=knowledge_adjacency,
                max_depth=1,
            )
        elif action_key == "expand.frontier":
            frontier_local_ids = CanvasIO.expand_frontier_seed_ids(
                seed_ids=set(island_local_ids),
                base_node_ids=set(graph_view.nodes.keys()),
                adjacency=island_adjacency,
            )
            frontier_seeds = {
                graph_view.nodes[local_id].global_id
                for local_id in frontier_local_ids
                if local_id in graph_view.nodes
            }
            if not frontier_seeds:
                frontier_seeds = set(current_seed_ids)
            target_node_ids = CanvasIO.expanded_node_set(
                seed_ids=frontier_seeds,
                base_node_ids=current_node_ids,
                adjacency=knowledge_adjacency,
                max_depth=1,
            )
            force_active_target_ids = CanvasIO.expanded_reachable_node_ids(
                seed_ids=frontier_seeds,
                adjacency=knowledge_adjacency,
                max_depth=1,
            )
        elif action_key == "expand_all":
            target_node_ids = CanvasIO.expanded_node_set(
                seed_ids=current_seed_ids,
                base_node_ids=current_node_ids,
                adjacency=knowledge_adjacency,
                max_depth=None,
            )
            force_active_target_ids = CanvasIO.expanded_reachable_node_ids(
                seed_ids=current_seed_ids,
                adjacency=knowledge_adjacency,
                max_depth=None,
            )
        elif action_key == "expand.all":
            target_node_ids = set(all_node_ids)
            force_active_target_ids = set(target_node_ids)
        elif action_key == "contract.adjacent":
            direct_neighbors: set[str] = set()
            for node_id in current_seed_ids:
                direct_neighbors.update(
                    knowledge_adjacency.get(node_id, set()))
            target_node_ids = current_node_ids - \
                (direct_neighbors - current_seed_ids)
        elif action_key == "contract":
            target_node_ids = CanvasIO.contracted_node_set(
                seed_ids=current_seed_ids,
                base_node_ids=current_node_ids,
                adjacency=knowledge_adjacency,
                max_depth=1,
            )
        elif action_key == "contract.frontier":
            target_node_ids = CanvasIO.contracted_node_set(
                seed_ids=current_seed_ids,
                base_node_ids=current_node_ids,
                adjacency=knowledge_adjacency,
                max_depth=1,
            )
        elif action_key == "contract_all":
            frontier_local_ids = CanvasIO.expand_frontier_seed_ids(
                seed_ids=set(island_local_ids),
                base_node_ids=set(graph_view.nodes.keys()),
                adjacency=island_adjacency,
            )
            frontier_globals = {
                graph_view.nodes[local_id].global_id
                for local_id in frontier_local_ids
                if local_id in graph_view.nodes
            }
            target_node_ids = current_node_ids - \
                (frontier_globals - current_seed_ids)
        elif action_key == "contract.all":
            target_node_ids = set(current_seed_ids)
        else:
            target_node_ids = set(current_node_ids)

        return target_node_ids, force_active_target_ids

    @staticmethod
    def apply_graph_view_local_position_updates(
        *,
        graph_view: GraphView,
        positions_by_local_id: Mapping[str, tuple[float, float]],
    ) -> GraphView:
        updated_nodes = dict(graph_view.nodes)
        changed = False
        for local_id, coords in positions_by_local_id.items():
            if local_id not in updated_nodes:
                continue
            proxy = updated_nodes[local_id]
            next_x = float(coords[0])
            next_y = float(coords[1])
            if proxy.x == next_x and proxy.y == next_y:
                continue
            updated_nodes[local_id] = GraphViewNodeProxy(
                global_id=proxy.global_id,
                x=next_x,
                y=next_y,
                cached_name=proxy.cached_name,
            )
            changed = True
        if not changed:
            return graph_view
        return dataclasses.replace(graph_view, nodes=updated_nodes)

    @staticmethod
    def _layout_incremental_expand_positions(
        *,
        target_node_ids: list[str],
        new_global_ids: list[str],
        existing_positions: dict[str, tuple[float, float]],
        node_sizes: dict[str, tuple[float, float]],
        edge_pairs: list[tuple[str, str]],
        anchor: tuple[float, float],
    ) -> dict[str, tuple[float, float]]:
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

    @staticmethod
    def apply_graph_node_subset_projection(
        *,
        graph_view: GraphView,
        target_node_ids: set[str],
        selected_ids: set[str],
        selected_local_ids: set[str],
        force_active_target_ids: set[str],
        preserve_inactive_islands: bool,
        nodes_by_id: Mapping[str, Any],
        links: list[Any],
        node_sizes: Mapping[str, tuple[float, float]],
    ) -> GraphView:
        subset_state = CanvasIO.resolve_graph_membership_subset(
            graph_view=graph_view,
            target_node_ids=target_node_ids,
            selected_local_ids=selected_local_ids,
            selected_ids=selected_ids,
            force_active_target_ids=force_active_target_ids,
        )
        inactive_local_ids = set(subset_state["inactive_local_ids"])
        active_local_ids = set(subset_state["active_local_ids"])

        updated_nodes: dict[str, GraphViewNodeProxy] = {}

        active_existing_local_by_global = dict(
            subset_state["active_existing_local_by_global"]
        )
        active_target_global_ids = set(
            subset_state["active_target_global_ids"])

        for local_id in sorted(inactive_local_ids):
            proxy = graph_view.nodes.get(local_id)
            if proxy is None:
                continue
            if not preserve_inactive_islands and proxy.global_id not in active_target_global_ids:
                continue
            node = nodes_by_id.get(proxy.global_id)
            cached_name = getattr(node, "name", proxy.cached_name)
            updated_nodes[local_id] = GraphViewNodeProxy(
                global_id=proxy.global_id,
                x=proxy.x,
                y=proxy.y,
                cached_name=cached_name,
            )

        active_global_to_local: dict[str, str] = {}
        active_projection_local_ids: set[str] = set()
        for local_id in sorted(active_local_ids):
            proxy = graph_view.nodes.get(local_id)
            if proxy is None:
                continue
            if proxy.global_id not in active_target_global_ids:
                continue
            node = nodes_by_id.get(proxy.global_id)
            cached_name = getattr(node, "name", proxy.cached_name)
            updated_nodes[local_id] = GraphViewNodeProxy(
                global_id=proxy.global_id,
                x=proxy.x,
                y=proxy.y,
                cached_name=cached_name,
            )
            active_projection_local_ids.add(local_id)
            active_global_to_local.setdefault(proxy.global_id, local_id)

        new_global_ids = [
            global_id
            for global_id in sorted(active_target_global_ids)
            if global_id not in active_global_to_local
        ]
        if new_global_ids:
            seed_for_centroid = selected_ids & {
                graph_view.nodes[local_id].global_id
                for local_id in active_local_ids
                if local_id in graph_view.nodes
            }
            if not seed_for_centroid:
                seed_for_centroid = {
                    graph_view.nodes[local_id].global_id
                    for local_id in active_local_ids
                    if local_id in graph_view.nodes
                }
            if seed_for_centroid:
                xs = [
                    graph_view.nodes[active_existing_local_by_global[node_id]].x
                    for node_id in seed_for_centroid
                    if node_id in active_existing_local_by_global
                ]
                ys = [
                    graph_view.nodes[active_existing_local_by_global[node_id]].y
                    for node_id in seed_for_centroid
                    if node_id in active_existing_local_by_global
                ]
                if not xs or not ys:
                    xs = [0.0]
                    ys = [0.0]
                centroid_x = sum(xs) / len(xs)
                centroid_y = sum(ys) / len(ys)
            else:
                centroid_x = 0.0
                centroid_y = 0.0

            edge_pairs: list[tuple[str, str]] = []
            target_id_set = set(active_target_global_ids)
            for link in links:
                source_id = str(getattr(link, "source_node_id", ""))
                target_id = str(getattr(link, "target_node_id", ""))
                if source_id in target_id_set and target_id in target_id_set and source_id != target_id:
                    edge_pairs.append((source_id, target_id))

            existing_positions = {
                node_id: (
                    graph_view.nodes[active_existing_local_by_global[node_id]].x,
                    graph_view.nodes[active_existing_local_by_global[node_id]].y,
                )
                for node_id in active_target_global_ids
                if node_id in active_existing_local_by_global
            }
            new_positions = CanvasIO._layout_incremental_expand_positions(
                target_node_ids=sorted(active_target_global_ids),
                new_global_ids=new_global_ids,
                existing_positions=existing_positions,
                node_sizes=dict(node_sizes),
                edge_pairs=edge_pairs,
                anchor=(centroid_x, centroid_y),
            )
            for node_id in new_global_ids:
                x, y = new_positions.get(node_id, (centroid_x, centroid_y))
                local_id = str(ULID())
                node = nodes_by_id.get(node_id)
                cached_name = getattr(node, "name", "")
                updated_nodes[local_id] = GraphViewNodeProxy(
                    global_id=node_id,
                    x=x,
                    y=y,
                    cached_name=cached_name,
                )
                active_global_to_local[node_id] = local_id
                active_projection_local_ids.add(local_id)

        global_to_local: dict[str, str] = dict(active_global_to_local)
        for local_id, proxy in updated_nodes.items():
            if local_id in active_local_ids:
                continue
            global_to_local.setdefault(proxy.global_id, local_id)

        links_by_id = {
            str(getattr(link, "id", "")): link
            for link in links
        }
        updated_edges: dict[str, GraphViewEdgeProxy] = {}

        # Preserve existing eligible local edges verbatim so repeated local
        # proxies/edges with the same global link id are not collapsed.
        for edge_local_id, edge in graph_view.edges.items():
            source_local_id = edge.source_local_id
            target_local_id = edge.target_local_id
            if source_local_id not in updated_nodes or target_local_id not in updated_nodes:
                continue
            source_global_id = updated_nodes[source_local_id].global_id
            target_global_id = updated_nodes[target_local_id].global_id
            if not preserve_inactive_islands:
                if source_global_id not in target_node_ids or target_global_id not in target_node_ids:
                    continue
            else:
                source_is_active = source_local_id in active_projection_local_ids
                target_is_active = target_local_id in active_projection_local_ids
                if source_is_active != target_is_active:
                    continue
            link_id = str(edge.global_link_id)
            link = links_by_id.get(link_id)
            if link is not None:
                link_source = str(getattr(link, "source_node_id", ""))
                link_target = str(getattr(link, "target_node_id", ""))
                if source_global_id != link_source or target_global_id != link_target:
                    continue
            updated_edges[edge_local_id] = GraphViewEdgeProxy(
                global_link_id=link_id,
                source_local_id=source_local_id,
                target_local_id=target_local_id,
            )

        for link in links:
            source_id = str(getattr(link, "source_node_id", ""))
            target_id = str(getattr(link, "target_node_id", ""))
            if source_id not in target_node_ids or target_id not in target_node_ids:
                continue
            source_local_id = global_to_local.get(source_id)
            target_local_id = global_to_local.get(target_id)
            if source_local_id is None or target_local_id is None:
                continue
            if preserve_inactive_islands:
                if (
                    source_local_id not in active_projection_local_ids
                    or target_local_id not in active_projection_local_ids
                ):
                    continue
            link_id = str(getattr(link, "id", ""))
            has_local_edge = any(
                edge.global_link_id == link_id
                and edge.source_local_id == source_local_id
                and edge.target_local_id == target_local_id
                for edge in updated_edges.values()
            )
            if has_local_edge:
                continue
            edge_local_id = str(ULID())
            updated_edges[edge_local_id] = GraphViewEdgeProxy(
                global_link_id=link_id,
                source_local_id=source_local_id,
                target_local_id=target_local_id,
            )

        return dataclasses.replace(
            graph_view,
            nodes=updated_nodes,
            edges=updated_edges,
        )

    def patch_graph_view_node_positions(
        self,
        graph_view_id: str,
        positions_by_local_id: dict[str, tuple[float, float]],
    ) -> GraphView:
        """Patch only node proxy x/y for one graph view and persist it.

        This is a composition-safe write surface for drag-release commits:
        only provided local ids have position updates applied.
        """
        graph_view = self._knowledge_io.repository.load_graph_view(
            graph_view_id)
        if not positions_by_local_id:
            return graph_view

        updated_nodes = dict(graph_view.nodes)
        changed = False
        for local_id, coords in positions_by_local_id.items():
            if local_id not in updated_nodes:
                continue
            proxy = updated_nodes[local_id]
            new_x = float(coords[0])
            new_y = float(coords[1])
            if proxy.x == new_x and proxy.y == new_y:
                continue
            updated_nodes[local_id] = GraphViewNodeProxy(
                global_id=proxy.global_id,
                x=new_x,
                y=new_y,
                cached_name=proxy.cached_name,
            )
            changed = True

        if not changed:
            return graph_view

        updated_view = dataclasses.replace(graph_view, nodes=updated_nodes)
        self._knowledge_io.repository.save_graph_view(updated_view)
        return updated_view

    def layout_canvas_nodes(
        self,
        *,
        algorithm: str = "grid",
        node_ids: list[str] | None = None,
        anchor_x: float | None = None,
        anchor_y: float | None = None,
        gap_x: float = 80.0,
        gap_y: float = 60.0,
        columns: int | None = None,
        layout_mode: str = "rect",
    ) -> dict[str, Any]:
        """Apply deterministic shared graph2d layout to selected (or all) kb_nodes."""
        key = algorithm.strip().lower()
        if key not in {"grid", "line", "radial"}:
            raise ValueError("algorithm must be one of: grid, line, radial")

        document = self._load_document()
        selected_node_ids = {str(node_id) for node_id in node_ids or []}
        indexed_nodes: list[tuple[int, dict[str, Any]]] = []
        for idx, item in enumerate(document.items):
            if item.get("type") != "knowledge.kb_node":
                continue
            node_id = str(item.get("node_id", ""))
            if selected_node_ids and node_id not in selected_node_ids:
                continue
            indexed_nodes.append((idx, dict(item)))
        if not indexed_nodes:
            return {
                "layout_applied": False,
                "reason": "no_matching_nodes",
                "changed_nodes": 0,
                "algorithm": key,
            }

        indexed_nodes.sort(key=lambda row: self._node_sort_key(
            str(row[1].get("node_id", ""))))
        nodes_for_layout: list[LayoutNode2D] = []
        for _, payload in indexed_nodes:
            width = float(payload.get("width", payload.get("w", 240.0)))
            height = float(payload.get("height", payload.get("h", 80.0)))
            if layout_mode.strip().lower() == "point":
                width = 0.0
                height = 0.0
            nodes_for_layout.append(
                LayoutNode2D(
                    node_id=str(payload.get("node_id", "")),
                    x=float(payload.get("x", 0.0)),
                    y=float(payload.get("y", 0.0)),
                    width=width,
                    height=height,
                )
            )

        min_x = min(float(item.get("x", 0.0)) for _, item in indexed_nodes)
        min_y = min(float(item.get("y", 0.0)) for _, item in indexed_nodes)
        max_x = max(float(item.get("x", 0.0)) + float(item.get("width",
                    item.get("w", 240.0))) for _, item in indexed_nodes)
        max_y = max(float(item.get("y", 0.0)) + float(item.get("height",
                    item.get("h", 80.0))) for _, item in indexed_nodes)
        center_x = float(anchor_x) if anchor_x is not None else (
            min_x + (max_x - min_x) * 0.5)
        center_y = float(anchor_y) if anchor_y is not None else (
            min_y + (max_y - min_y) * 0.5)

        sample_width = max(1.0, float(indexed_nodes[0][1].get(
            "width", indexed_nodes[0][1].get("w", 240.0))))
        sample_height = max(1.0, float(indexed_nodes[0][1].get(
            "height", indexed_nodes[0][1].get("h", 80.0))))

        if key == "line":
            total_w = len(nodes_for_layout) * sample_width + \
                max(0, len(nodes_for_layout) - 1) * float(gap_x)
            origin_x = center_x - total_w * 0.5
            origin_y = center_y - sample_height * 0.5
            algorithm_impl = LaneNodeLayoutAlgorithm2D(
                orientation="horizontal",
                lane_value=origin_y,
                start=origin_x,
                gap=float(gap_x),
                mode=layout_mode,
            )
        elif key == "grid":
            cols = max(1, int(columns)) if columns is not None else None
            if cols is None:
                cols = max(1, int(len(nodes_for_layout) ** 0.5 + 0.9999))
            rows = max(1, int((len(nodes_for_layout) + cols - 1) / cols))
            total_w = cols * sample_width + max(0, cols - 1) * float(gap_x)
            total_h = rows * sample_height + max(0, rows - 1) * float(gap_y)
            origin_x = center_x - total_w * 0.5
            origin_y = center_y - total_h * 0.5
            algorithm_impl = GridNodeLayoutAlgorithm2D(
                col_spacing=sample_width + float(gap_x),
                row_spacing=sample_height + float(gap_y),
                origin_x=origin_x,
                origin_y=origin_y,
                cols=cols,
                prevent_shape_overlaps=False,
            )
        else:
            algorithm_impl = CircularNodeLayoutAlgorithm2D(
                center_x=center_x,
                center_y=center_y,
                radius=None,
                prevent_shape_overlaps=(layout_mode.strip().lower() == "rect"),
            )

        positions = algorithm_impl.compute(nodes_for_layout, [])
        updated_items = list(document.items)
        for idx, payload in indexed_nodes:
            node_id = str(payload.get("node_id", ""))
            item = dict(payload)
            x, y = positions.get(
                node_id, (float(item.get("x", 0.0)), float(item.get("y", 0.0))))
            item["x"] = float(x)
            item["y"] = float(y)
            updated_items[idx] = item

        self._save_document(
            CanvasDocument(
                version=document.version,
                items=updated_items,
                metadata=document.metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )
        return {
            "layout_applied": True,
            "algorithm": key,
            "changed_nodes": len(indexed_nodes),
            "view_format": "kb_canvas",
            "layout_mode": layout_mode,
        }

    def place_nodes_in_lane(
        self,
        *,
        node_ids: list[str],
        orientation: str,
        lane_value: float,
        start: float,
        gap: float,
        layout_mode: str = "rect",
    ) -> dict[str, Any]:
        """Place selected kb_node items into a deterministic lane."""
        key = orientation.strip().lower()
        wanted = {str(node_id) for node_id in node_ids}
        if not wanted:
            return {"placed": 0, "orientation": key}

        document = self._load_document()
        indexed: list[tuple[int, dict[str, Any]]] = []
        for idx, item in enumerate(document.items):
            payload = dict(item)
            if payload.get("type") != "knowledge.kb_node":
                continue
            node_id = str(payload.get("node_id", ""))
            if node_id in wanted:
                indexed.append((idx, payload))

        indexed.sort(key=lambda row: self._node_sort_key(
            str(row[1].get("node_id", ""))))
        if not indexed:
            return {"placed": 0, "orientation": key}

        nodes = [
            LayoutNode2D(
                node_id=str(payload.get("node_id", "")),
                x=float(payload.get("x", 0.0)),
                y=float(payload.get("y", 0.0)),
                width=float(payload.get("width", payload.get("w", 240.0))),
                height=float(payload.get("height", payload.get("h", 80.0))),
            )
            for _, payload in indexed
        ]
        if layout_mode.strip().lower() == "point":
            nodes = [
                LayoutNode2D(
                    node_id=node.node_id,
                    x=node.x,
                    y=node.y,
                    width=0.0,
                    height=0.0,
                )
                for node in nodes
            ]

        algorithm = LaneNodeLayoutAlgorithm2D(
            orientation=key,
            lane_value=float(lane_value),
            start=float(start),
            gap=float(gap),
            mode=layout_mode,
        )
        positions = algorithm.compute(nodes, [])

        updated = list(document.items)
        changed = 0
        for idx, payload in indexed:
            item = dict(payload)
            node_id = str(payload.get("node_id", ""))
            x, y = positions.get(
                node_id, (float(item.get("x", 0.0)), float(item.get("y", 0.0))))
            item["x"] = float(x)
            item["y"] = float(y)
            updated[idx] = item
            changed += 1

        self._save_document(
            CanvasDocument(
                version=document.version,
                items=updated,
                metadata=document.metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )
        return {
            "placed": changed,
            "orientation": key,
            "lane_value": float(lane_value),
            "start": float(start),
            "gap": float(gap),
            "layout_mode": layout_mode,
        }

    def layout_tree_from_root(
        self,
        *,
        root_node_id: str,
        traversal_link_type: str,
        orientation: str = "top_down",
        level_gap: float = 240.0,
        sibling_gap: float = 340.0,
        node_ids_scope: list[str] | None = None,
        layout_mode: str = "rect",
    ) -> dict[str, Any]:
        """Lay out a tree from *root_node_id* based on one traversal link type."""
        direction = orientation.strip().lower()
        if direction not in {"top_down", "left_right"}:
            raise ValueError(
                "orientation must be one of: top_down, left_right")

        link_type_id = self._resolve_link_type_id(traversal_link_type)
        allowed_scope = {str(node_id) for node_id in node_ids_scope or []}

        document = self._load_document()
        placed = self._indexed_kb_nodes(document)
        if root_node_id not in placed:
            raise ValueError(
                f"Root node is not placed in this view: {root_node_id}")

        links = [
            link
            for link in self._knowledge_io.repository.list_links()
            if str(link.link_type_id) == link_type_id
        ]
        children: dict[str, list[str]] = defaultdict(list)
        for link in links:
            src = str(link.source_node_id)
            dst = str(link.target_node_id)
            if src not in placed or dst not in placed:
                continue
            if allowed_scope and (src not in allowed_scope or dst not in allowed_scope):
                continue
            children[src].append(dst)

        queue: deque[str] = deque([root_node_id])
        visited: set[str] = set()
        tree_nodes: list[str] = []
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            tree_nodes.append(current)
            for child in sorted(children.get(current, []), key=self._node_sort_key):
                if child not in visited:
                    queue.append(child)

        # Keep only edges where both nodes are in the rooted tree.
        filtered_edges: list[LayoutEdge2D] = []
        edge_counter = 0
        for parent_id in tree_nodes:
            for child_id in sorted(children.get(parent_id, []), key=self._node_sort_key):
                if child_id not in visited:
                    continue
                filtered_edges.append(
                    LayoutEdge2D(
                        edge_id=f"tree_edge_{edge_counter}",
                        source_id=parent_id,
                        target_id=child_id,
                    )
                )
                edge_counter += 1

        layout_nodes: list[LayoutNode2D] = []
        for node_id in tree_nodes:
            _, payload = placed[node_id]
            width = float(payload.get("width", payload.get("w", 240.0)))
            height = float(payload.get("height", payload.get("h", 80.0)))
            if layout_mode.strip().lower() == "point":
                width = 0.0
                height = 0.0
            layout_nodes.append(
                LayoutNode2D(
                    node_id=node_id,
                    x=float(payload.get("x", 0.0)),
                    y=float(payload.get("y", 0.0)),
                    width=width,
                    height=height,
                )
            )

        layout_direction = "top_to_bottom" if direction == "top_down" else "left_to_right"
        algorithm = TreeNodeLayoutAlgorithm2D(
            direction=layout_direction,
            layer_spacing=float(level_gap),
            sibling_spacing=float(sibling_gap),
            component_gap=float(level_gap),
            origin_x=0.0,
            origin_y=0.0,
            prevent_shape_overlaps=False,
        )
        positions = algorithm.compute(layout_nodes, filtered_edges)

        root_pos = positions.get(root_node_id, (0.0, 0.0))
        root_item = placed[root_node_id][1]
        root_w = float(root_item.get("width", root_item.get("w", 240.0)))
        root_h = float(root_item.get("height", root_item.get("h", 80.0)))
        root_left = float(root_item.get("x", 0.0))
        root_top = float(root_item.get("y", 0.0))
        root_center = (root_left + root_w / 2.0, root_top + root_h / 2.0)

        root_layout_w = 0.0
        root_layout_h = 0.0
        for node in layout_nodes:
            if node.node_id == root_node_id:
                root_layout_w = node.width
                root_layout_h = node.height
                break
        root_layout_center = (
            float(root_pos[0]) + root_layout_w / 2.0,
            float(root_pos[1]) + root_layout_h / 2.0,
        )

        updated = list(document.items)
        changed = 0
        for node_id in tree_nodes:
            idx, payload = placed[node_id]
            item = dict(payload)
            layout_x, layout_y = positions.get(
                node_id, (float(item.get("x", 0.0)), float(item.get("y", 0.0))))
            layout_node = next(
                (n for n in layout_nodes if n.node_id == node_id), None)
            width = float(item.get("width", item.get("w", 240.0)))
            height = float(item.get("height", item.get("h", 80.0)))
            layout_width = layout_node.width if layout_node is not None else width
            layout_height = layout_node.height if layout_node is not None else height
            layout_center = (
                float(layout_x) + float(layout_width) / 2.0,
                float(layout_y) + float(layout_height) / 2.0,
            )
            final_cx = root_center[0] + \
                (layout_center[0] - root_layout_center[0])
            final_cy = root_center[1] + \
                (layout_center[1] - root_layout_center[1])
            item["x"] = final_cx - width / 2.0
            item["y"] = final_cy - height / 2.0
            updated[idx] = item
            changed += 1

        self._save_document(
            CanvasDocument(
                version=document.version,
                items=updated,
                metadata=document.metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )
        return {
            "root_node_id": root_node_id,
            "traversal_link_type_id": link_type_id,
            "orientation": direction,
            "changed_nodes": changed,
            "tree_node_count": len(tree_nodes),
            "layout_mode": layout_mode,
        }

    def resolve_overlaps(
        self,
        *,
        node_ids: list[str] | None = None,
        padding: float = 24.0,
        max_iterations: int = 80,
    ) -> dict[str, Any]:
        """Push overlapping kb_node items apart until overlaps settle."""
        document = self._load_document()
        indexed = self._indexed_kb_nodes(document)
        selected = {str(node_id) for node_id in node_ids or []}
        active_ids = [
            node_id
            for node_id in indexed.keys()
            if not selected or node_id in selected
        ]
        if len(active_ids) < 2:
            return {"iterations": 0, "moved_nodes": 0}

        layout_nodes: list[LayoutNode2D] = []
        initial_positions: dict[str, tuple[float, float]] = {}
        for node_id in active_ids:
            payload = indexed[node_id][1]
            x = float(payload.get("x", 0.0))
            y = float(payload.get("y", 0.0))
            width = float(payload.get("width", payload.get("w", 240.0)))
            height = float(payload.get("height", payload.get("h", 80.0)))
            layout_nodes.append(
                LayoutNode2D(
                    node_id=node_id,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                )
            )
            initial_positions[node_id] = (x, y)

        resolver = OverlapResolver2D(
            padding=float(padding),
            max_iterations=max(1, int(max_iterations)),
        )
        resolved_positions = resolver.resolve(layout_nodes, initial_positions)

        moved = {
            node_id
            for node_id in active_ids
            if initial_positions.get(node_id) != resolved_positions.get(node_id)
        }
        iterations = max(1, int(max_iterations)) if moved else 0

        if not moved:
            return {"iterations": iterations, "moved_nodes": 0}

        updated = list(document.items)
        for node_id in moved:
            idx, payload = indexed[node_id]
            item = dict(payload)
            x, y = resolved_positions.get(
                node_id, (float(item.get("x", 0.0)), float(item.get("y", 0.0))))
            item["x"] = float(x)
            item["y"] = float(y)
            updated[idx] = item

        self._save_document(
            CanvasDocument(
                version=document.version,
                items=updated,
                metadata=document.metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )
        return {
            "iterations": iterations,
            "moved_nodes": len(moved),
        }

    def optimize_layout(
        self,
        *,
        fixed_node_ids: list[str] | None = None,
        movable_node_ids: list[str] | None = None,
        link_type_ids: list[str] | None = None,
        iterations: int = 120,
        step_size: float = 0.18,
        min_distance: float = 220.0,
        layout_mode: str = "rect",
    ) -> dict[str, Any]:
        """Run a constrained spring-style optimization over kb_node positions."""
        document = self._load_document()
        indexed = self._indexed_kb_nodes(document)
        if not indexed:
            return {"optimized": False, "reason": "no_nodes"}

        fixed = {str(node_id) for node_id in fixed_node_ids or []}
        movable = {str(node_id) for node_id in movable_node_ids or []}
        if not movable:
            movable = set(indexed.keys()) - fixed
        movable &= set(indexed.keys())
        if not movable:
            return {"optimized": False, "reason": "no_movable_nodes"}
        allowed_link_type_ids = {str(link_type_id)
                                 for link_type_id in link_type_ids or []}

        layout_nodes: list[LayoutNode2D] = []
        for node_id, (_, payload) in indexed.items():
            width = float(payload.get("width", payload.get("w", 240.0)))
            height = float(payload.get("height", payload.get("h", 80.0)))
            if layout_mode.strip().lower() == "point":
                width = 0.0
                height = 0.0
            layout_nodes.append(
                LayoutNode2D(
                    node_id=node_id,
                    x=float(payload.get("x", 0.0)),
                    y=float(payload.get("y", 0.0)),
                    width=width,
                    height=height,
                )
            )

        layout_edges: list[LayoutEdge2D] = []
        edge_count = 0
        for item in document.items:
            if item.get("type") != "knowledge.kb_edge":
                continue
            if allowed_link_type_ids:
                link_id = str(item.get("link_id", ""))
                if not link_id:
                    continue
                link = self._knowledge_io.repository.find_link(link_id)
                if link is None:
                    continue
                if str(link.link_type_id) not in allowed_link_type_ids:
                    continue
            src = str(item.get("from_node_id", ""))
            dst = str(item.get("to_node_id", ""))
            if src not in indexed or dst not in indexed:
                continue
            layout_edges.append(
                LayoutEdge2D(
                    edge_id=f"kb_edge_{edge_count}",
                    source_id=src,
                    target_id=dst,
                )
            )
            edge_count += 1

        algorithm = ConstrainedForceDirectedNodeLayoutAlgorithm2D(
            fixed_node_ids=fixed,
            iterations=max(1, int(iterations)),
            step_size=float(step_size),
            min_distance=float(min_distance),
            mode=layout_mode,
        )
        computed_positions = algorithm.compute(layout_nodes, layout_edges)

        updated = list(document.items)
        for node_id in movable:
            idx, payload = indexed[node_id]
            item = dict(payload)
            x, y = computed_positions.get(
                node_id, (float(item.get("x", 0.0)), float(item.get("y", 0.0))))
            item["x"] = float(x)
            item["y"] = float(y)
            updated[idx] = item

        self._save_document(
            CanvasDocument(
                version=document.version,
                items=updated,
                metadata=document.metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )
        return {
            "optimized": True,
            "moved_nodes": len(movable),
            "fixed_nodes": len(fixed),
            "iterations": int(iterations),
            "layout_mode": layout_mode,
            "link_type_filter_count": len(allowed_link_type_ids),
        }

    def _load_document(self) -> CanvasDocument:
        return load_canvas_document(self._view_path)

    def _save_document(self, document: CanvasDocument) -> None:
        save_canvas_document(document, self._view_path)

    def _handle_node_upserted(self, node_id: str) -> None:
        document = self._load_document()
        updated_items: list[dict[str, Any]] = []
        touched = False
        for item in document.items:
            payload = dict(item)
            if payload.get("type") == "knowledge.kb_node" and payload.get("node_id") == node_id:
                touched = True
            updated_items.append(payload)

        if touched:
            self._save_document(
                CanvasDocument(
                    version=document.version,
                    items=updated_items,
                    metadata=document.metadata,
                    overlays=document.overlays,
                    bookmarks=document.bookmarks,
                )
            )

    def _handle_node_removed(self, node_id: str) -> None:
        document = self._load_document()
        filtered_items: list[dict[str, Any]] = []
        touched = False
        for item in document.items:
            payload = dict(item)
            item_type = payload.get("type")
            if item_type == "knowledge.kb_node" and payload.get("node_id") == node_id:
                touched = True
                continue
            if item_type == "knowledge.kb_edge":
                if payload.get("from_node_id") == node_id or payload.get("to_node_id") == node_id:
                    touched = True
                    continue
            filtered_items.append(payload)

        if touched:
            self._save_document(
                CanvasDocument(
                    version=document.version,
                    items=filtered_items,
                    metadata=document.metadata,
                    overlays=document.overlays,
                    bookmarks=document.bookmarks,
                )
            )

    def _handle_link_upserted(self, link_id: str) -> None:
        link = self._knowledge_io.repository.find_link(link_id)
        if link is None:
            return None

        document = self._load_document()
        updated_items: list[dict[str, Any]] = []
        touched = False
        for item in document.items:
            payload = dict(item)
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
            updated_items.append(payload)

        if not touched:
            updated_items.append(
                {
                    "type": "knowledge.kb_edge",
                    "link_id": link_id,
                    "from_node_id": str(link.source_node_id),
                    "to_node_id": str(link.target_node_id),
                }
            )

        self._save_document(
            CanvasDocument(
                version=document.version,
                items=updated_items,
                metadata=document.metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )

    def _handle_link_removed(self, link_id: str) -> None:
        document = self._load_document()
        filtered_items: list[dict[str, Any]] = []
        touched = False
        for item in document.items:
            payload = dict(item)
            if payload.get("type") == "knowledge.kb_edge" and payload.get("link_id") == link_id:
                touched = True
                continue
            filtered_items.append(payload)

        if touched:
            self._save_document(
                CanvasDocument(
                    version=document.version,
                    items=filtered_items,
                    metadata=document.metadata,
                    overlays=document.overlays,
                    bookmarks=document.bookmarks,
                )
            )

    def _handle_link_type_upserted(self, link_type_id: str) -> None:
        if self._knowledge_io.repository.find_link_type(link_type_id) is None:
            return None

        document = self._load_document()
        metadata = dict(document.metadata)
        visibility = dict(metadata.get("link_type_visibility", {}))
        if link_type_id in visibility:
            return None

        visibility[link_type_id] = {"visible": True}
        metadata["link_type_visibility"] = visibility
        self._save_document(
            CanvasDocument(
                version=document.version,
                items=document.items,
                metadata=metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )

    def _sidecar_path(self) -> Path:
        base = self._view_path.stem
        return self._view_path.with_name(f"{base}_viewport.json")

    @staticmethod
    def _compute_bbox(nodes: list[dict[str, Any]]) -> dict[str, float]:
        if not nodes:
            return {
                "min_x": 0.0,
                "min_y": 0.0,
                "max_x": 0.0,
                "max_y": 0.0,
                "width": 0.0,
                "height": 0.0,
            }
        min_x = min(float(node["x"]) for node in nodes)
        min_y = min(float(node["y"]) for node in nodes)
        max_x = max(float(node["x"]) + float(node["w"]) for node in nodes)
        max_y = max(float(node["y"]) + float(node["h"]) for node in nodes)
        return {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        }

    def _resolve_link_type_id(self, token: str) -> str:
        raw = token.strip()
        if raw == "":
            raise ValueError("traversal_link_type must not be empty")
        for link_type in self._knowledge_io.repository.list_link_types():
            if str(link_type.id) == raw or link_type.name == raw:
                return str(link_type.id)
        raise KeyError(f"Link type not found: {token}")

    def _indexed_kb_nodes(self, document: CanvasDocument) -> dict[str, tuple[int, dict[str, Any]]]:
        out: dict[str, tuple[int, dict[str, Any]]] = {}
        for idx, item in enumerate(document.items):
            payload = dict(item)
            if payload.get("type") != "knowledge.kb_node":
                continue
            node_id = str(payload.get("node_id", ""))
            if node_id:
                out[node_id] = (idx, payload)
        return out

    def _node_sort_key(self, node_id: str) -> tuple[str, str]:
        node = self._knowledge_io.repository.find_node(node_id)
        if node is None:
            return (node_id, node_id)
        return (node.name, node_id)


__all__ = ["CanvasIO"]

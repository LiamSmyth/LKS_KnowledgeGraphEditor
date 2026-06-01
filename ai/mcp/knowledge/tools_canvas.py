"""Canvas projection MCP tools for knowledge repos."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import _build_io, resolve_existing_repo
from lks_utils.knowledge.canvas.canvas_document import CanvasDocument
from lks_utils.knowledge.canvas.canvas_io import CanvasIO


def list_canvases_impl(path: str) -> list[dict[str, Any]]:
    """Return persisted graph-view canvases for a knowledge repository."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    views = CanvasIO.list_graph_views(io)

    rows: list[dict[str, Any]] = []
    for view in sorted(views, key=lambda entry: entry.name.lower()):
        rel_view_path: str | None = None
        abs_view_path = CanvasIO.graph_view_relpath(io, str(view.id))
        if abs_view_path is not None:
            try:
                rel_view_path = abs_view_path.resolve().relative_to(
                    resolved).as_posix()
            except ValueError:
                rel_view_path = abs_view_path.as_posix()
        rows.append(
            {
                "schema_type": "knowledge_graph_view",
                "graph_view_id": str(view.id),
                "graph_view_name": view.name,
                "view_path": rel_view_path,
                "node_count": len(view.nodes),
                "edge_count": len(view.edges),
            }
        )
    return rows


def open_canvas_impl(path: str, view_path: str) -> dict[str, Any]:
    """Load canvas document and return item counts by type."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)

    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    document = canvas_io.load_document()
    counts: dict[str, int] = {}
    for item in document.items:
        item_type = str(item.get("type", "unknown"))
        counts[item_type] = counts.get(item_type, 0) + 1
    return {
        "view_path": str(resolved_view_path),
        "version": document.version,
        "view_format": "kb_canvas",
        "item_counts": counts,
        "item_total": len(document.items),
    }


def place_node_impl(
    path: str,
    view_path: str,
    node_id: str,
    x: float,
    y: float,
    w: float = 240.0,
    h: float = 80.0,
) -> dict[str, Any]:
    """Add a kb_node placement when the node exists in the KB repo."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    io.get_node(node_id)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    document = canvas_io.load_document()

    items = list(document.items)
    items.append(
        {
            "type": "knowledge.kb_node",
            "node_id": node_id,
            "x": float(x),
            "y": float(y),
            "width": float(w),
            "height": float(h),
        }
    )
    canvas_io.save_document(
        CanvasDocument(
            version=document.version,
            items=items,
            metadata=document.metadata,
            overlays=document.overlays,
            bookmarks=document.bookmarks,
        )
    )
    return {"placed": True, "node_id": node_id}


def remove_node_from_canvas_impl(path: str, view_path: str, node_id: str) -> dict[str, Any]:
    """Remove one kb_node placement and conditionally remove incident kb_edge items."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    document = canvas_io.load_document()

    removed_nodes = 0
    removed_edges = 0
    kept: list[dict[str, Any]] = []
    removed_one = False
    for item in document.items:
        item_type = item.get("type")
        if (
            not removed_one
            and item_type == "knowledge.kb_node"
            and item.get("node_id") == node_id
        ):
            removed_one = True
            removed_nodes = 1
            continue
        kept.append(dict(item))

    if removed_one:
        remaining_node_count = sum(
            1
            for item in kept
            if item.get("type") == "knowledge.kb_node"
            and item.get("node_id") == node_id
        )
        if remaining_node_count == 0:
            next_kept: list[dict[str, Any]] = []
            for item in kept:
                if item.get("type") == "knowledge.kb_edge" and (
                    item.get("from_node_id") == node_id
                    or item.get("to_node_id") == node_id
                ):
                    removed_edges += 1
                    continue
                next_kept.append(item)
            kept = next_kept

    if removed_nodes or removed_edges:
        canvas_io.save_document(
            CanvasDocument(
                version=document.version,
                items=kept,
                metadata=document.metadata,
                overlays=document.overlays,
                bookmarks=document.bookmarks,
            )
        )

    return {
        "removed_nodes": removed_nodes,
        "removed_edges": removed_edges,
        "node_id": node_id,
    }


def set_view_impl(
    path: str,
    view_path: str,
    center_x: float,
    center_y: float,
    zoom: float,
) -> dict[str, Any]:
    """Write viewport sidecar state through CanvasIO."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    canvas_io.write_viewport_sidecar(
        center_x=center_x,
        center_y=center_y,
        zoom=zoom,
        visible_node_ids=[],
        selected_node_ids=[],
    )
    return {
        "center_x": float(center_x),
        "center_y": float(center_y),
        "zoom": float(zoom),
        "view_path": str(resolved_view_path),
    }


def get_current_view_impl(path: str, view_path: str) -> dict[str, Any]:
    """Return current viewport state from sidecar or canvas fallback metadata."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    payload = canvas_io.read_viewport_sidecar()
    if payload is not None:
        result = {
            "center_x": float(payload.get("center_x", 0.0)),
            "center_y": float(payload.get("center_y", 0.0)),
            "zoom": float(payload.get("zoom", 1.0)),
            "visible_node_ids": _string_list(payload.get("visible_node_ids")),
            "selected_node_ids": _string_list(payload.get("selected_node_ids")),
        }
        if "rotation_radians" in payload:
            result["rotation_radians"] = float(
                payload.get("rotation_radians", 0.0))
        world_region = payload.get("viewport_world_region")
        if isinstance(world_region, dict):
            result["viewport_world_region"] = {
                key: float(value)
                for key, value in world_region.items()
                if isinstance(key, str)
            }
        resolution = payload.get("viewport_resolution")
        if isinstance(resolution, dict):
            result["viewport_resolution"] = {
                key: float(value)
                for key, value in resolution.items()
                if isinstance(key, str)
            }
        return result

    fallback = canvas_io.read_view_fallback()
    return {
        "center_x": fallback["center_x"],
        "center_y": fallback["center_y"],
        "zoom": fallback["zoom"],
        "visible_node_ids": [],
        "selected_node_ids": [],
    }


def find_nodes_in_rect_impl(
    path: str,
    view_path: str,
    x: float,
    y: float,
    w: float,
    h: float,
) -> list[dict[str, Any]]:
    """Return compact KB node data for kb_node canvas items overlapping a query rect."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    document = canvas_io.load_document()
    query_x = float(x)
    query_y = float(y)
    query_w = float(w)
    query_h = float(h)

    rows: list[dict[str, Any]] = []
    for item in document.items:
        if item.get("type") != "knowledge.kb_node":
            continue

        node_id = str(item.get("node_id", ""))
        if not node_id:
            continue

        item_x = float(item.get("x", 0.0))
        item_y = float(item.get("y", 0.0))
        item_w = float(item.get("width", item.get("w", 240.0)))
        item_h = float(item.get("height", item.get("h", 80.0)))
        if not _rects_overlap(query_x, query_y, query_w, query_h, item_x, item_y, item_w, item_h):
            continue

        try:
            node = io.get_node(node_id)
        except KeyError:
            # Canvas may contain stale placements after KB deletions.
            continue

        rows.append(
            {
                "id": str(node.id),
                "name": node.name,
                "category": node.category,
                "type_id": str(node.type_id) if node.type_id else None,
                "x": item_x,
                "y": item_y,
                "w": item_w,
                "h": item_h,
            }
        )
    return rows


def get_canvas_graph_state_impl(path: str, view_path: str) -> dict[str, Any]:
    """Return canvas nodes/edges with a normalized graph-state payload."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    return canvas_io.get_canvas_graph_state()


def layout_canvas_nodes_impl(
    path: str,
    view_path: str,
    algorithm: str = "grid",
    node_ids: list[str] | None = None,
    anchor_x: float | None = None,
    anchor_y: float | None = None,
    gap_x: float = 80.0,
    gap_y: float = 60.0,
    columns: int | None = None,
    layout_mode: str = "rect",
) -> dict[str, Any]:
    """Thin CanvasIO wrapper for deterministic layout of selected/all canvas nodes."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    return canvas_io.layout_canvas_nodes(
        algorithm=algorithm,
        node_ids=node_ids,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        gap_x=float(gap_x),
        gap_y=float(gap_y),
        columns=columns,
        layout_mode=layout_mode,
    )


def export_canvas_png_impl(
    path: str,
    view_path: str,
    output_path: str,
    width: int = 1600,
    height: int = 1000,
    padding: int = 64,
) -> dict[str, Any]:
    """Thin CanvasIO wrapper for full-graph PNG snapshot export."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    return canvas_io.export_canvas_png(
        output_path=output_path,
        width=int(width),
        height=int(height),
        padding=int(padding),
    )


def place_nodes_in_lane_impl(
    path: str,
    view_path: str,
    node_ids: list[str],
    orientation: str = "vertical",
    lane_value: float = 0.0,
    start: float = 0.0,
    gap: float = 260.0,
    layout_mode: str = "rect",
) -> dict[str, Any]:
    """Thin CanvasIO wrapper to place nodes in a vertical/horizontal lane."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    return canvas_io.place_nodes_in_lane(
        node_ids=node_ids,
        orientation=orientation,
        lane_value=float(lane_value),
        start=float(start),
        gap=float(gap),
        layout_mode=layout_mode,
    )


def layout_tree_from_root_impl(
    path: str,
    view_path: str,
    root_node_id: str,
    traversal_link_type: str,
    orientation: str = "top_down",
    level_gap: float = 240.0,
    sibling_gap: float = 340.0,
    node_ids_scope: list[str] | None = None,
    layout_mode: str = "rect",
) -> dict[str, Any]:
    """Thin CanvasIO wrapper to layout a rooted tree by one link type."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    return canvas_io.layout_tree_from_root(
        root_node_id=root_node_id,
        traversal_link_type=traversal_link_type,
        orientation=orientation,
        level_gap=float(level_gap),
        sibling_gap=float(sibling_gap),
        node_ids_scope=node_ids_scope,
        layout_mode=layout_mode,
    )


def resolve_overlaps_impl(
    path: str,
    view_path: str,
    node_ids: list[str] | None = None,
    padding: float = 24.0,
    max_iterations: int = 80,
) -> dict[str, Any]:
    """Thin CanvasIO wrapper for overlap-resolution pass."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    return canvas_io.resolve_overlaps(
        node_ids=node_ids,
        padding=float(padding),
        max_iterations=int(max_iterations),
    )


def optimize_layout_impl(
    path: str,
    view_path: str,
    fixed_node_ids: list[str] | None = None,
    movable_node_ids: list[str] | None = None,
    link_type_ids: list[str] | None = None,
    iterations: int = 120,
    step_size: float = 0.18,
    min_distance: float = 220.0,
    layout_mode: str = "rect",
) -> dict[str, Any]:
    """Thin CanvasIO wrapper for constrained layout optimization."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    return canvas_io.optimize_layout(
        fixed_node_ids=fixed_node_ids,
        movable_node_ids=movable_node_ids,
        link_type_ids=link_type_ids,
        iterations=int(iterations),
        step_size=float(step_size),
        min_distance=float(min_distance),
        layout_mode=layout_mode,
    )


def render_view_impl(
    path: str,
    view_path: str,
    output_path: str | None = None,
    width: int | None = None,
    height: int | None = None,
    padding: int = 0,
) -> dict[str, Any]:
    """Thin CanvasIO wrapper for viewport-anchored PNG render."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)
    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    return canvas_io.render_view(
        output_path=output_path,
        width=width,
        height=height,
        padding=int(padding),
    )


def set_link_type_visibility_impl(
    path: str,
    view_path: str,
    link_type_id: str,
    visible: bool,
    ghost: bool = False,
) -> dict[str, Any]:
    """Update metadata.link_type_visibility entry in the canvas document."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    resolved_view_path = _resolve_view_path(resolved, view_path)

    canvas_io = CanvasIO(view_path=resolved_view_path, knowledge_io=io)
    document = canvas_io.load_document()
    metadata = dict(document.metadata)
    visibility = dict(metadata.get("link_type_visibility", {}))
    visibility[link_type_id] = {"visible": bool(visible), "ghost": bool(ghost)}
    metadata["link_type_visibility"] = visibility
    canvas_io.save_document(
        CanvasDocument(
            version=document.version,
            items=document.items,
            metadata=metadata,
            overlays=document.overlays,
            bookmarks=document.bookmarks,
        )
    )
    return {
        "link_type_id": link_type_id,
        "visible": bool(visible),
        "ghost": bool(ghost),
    }


def _resolve_view_path(repo_root: Path, view_path: str | Path) -> Path:
    candidate = Path(view_path)
    if candidate.is_absolute():
        return candidate.resolve()

    resolved_root = repo_root.resolve()
    resolved_candidate = (resolved_root / candidate).resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"view_path must resolve under repository root: {view_path}"
        ) from exc
    return resolved_candidate


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _rects_overlap(
    ax: float,
    ay: float,
    aw: float,
    ah: float,
    bx: float,
    by: float,
    bw: float,
    bh: float,
) -> bool:
    ax2 = ax + aw
    ay2 = ay + ah
    bx2 = bx + bw
    by2 = by + bh
    return ax < bx2 and ax2 > bx and ay < by2 and ay2 > by


def register_canvas_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_canvases(path: str) -> list[dict[str, Any]]:
        """[READ-ONLY] Return persisted knowledge graph-view canvases for a repository."""
        return list_canvases_impl(path)

    @mcp.tool()
    def open_canvas(path: str, view_path: str) -> dict[str, Any]:
        """[READ-ONLY] Load a canvas document and return item summary counts."""
        return open_canvas_impl(path, view_path)

    @mcp.tool()
    def place_node(
        path: str,
        view_path: str,
        node_id: str,
        x: float,
        y: float,
        w: float = 240.0,
        h: float = 80.0,
    ) -> dict[str, Any]:
        """[WRITES DISK] Add a kb_node placement in the canvas view."""
        return place_node_impl(path, view_path, node_id, x, y, w, h)

    @mcp.tool()
    def remove_node_from_canvas(path: str, view_path: str, node_id: str) -> dict[str, Any]:
        """[WRITES DISK] Remove kb_node placement and its incident kb_edges."""
        return remove_node_from_canvas_impl(path, view_path, node_id)

    @mcp.tool()
    def set_view(
        path: str,
        view_path: str,
        center_x: float,
        center_y: float,
        zoom: float,
    ) -> dict[str, Any]:
        """[WRITES DISK] Persist viewport sidecar state for the canvas view."""
        return set_view_impl(path, view_path, center_x, center_y, zoom)

    @mcp.tool()
    def get_current_view(path: str, view_path: str) -> dict[str, Any]:
        """[READ-ONLY] Read viewport sidecar state with fallback to canvas view metadata."""
        return get_current_view_impl(path, view_path)

    @mcp.tool()
    def find_nodes_in_rect(
        path: str,
        view_path: str,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> list[dict[str, Any]]:
        """[READ-ONLY] Return kb_node items that overlap the specified canvas rectangle."""
        return find_nodes_in_rect_impl(path, view_path, x, y, w, h)

    @mcp.tool()
    def get_canvas_graph_state(path: str, view_path: str) -> dict[str, Any]:
        """[READ-ONLY] Return normalized nodes/edges/state for graph inspection."""
        return get_canvas_graph_state_impl(path, view_path)

    @mcp.tool()
    def layout_canvas_nodes(
        path: str,
        view_path: str,
        algorithm: str = "grid",
        node_ids: list[str] | None = None,
        anchor_x: float | None = None,
        anchor_y: float | None = None,
        gap_x: float = 80.0,
        gap_y: float = 60.0,
        columns: int | None = None,
        layout_mode: str = "rect",
    ) -> dict[str, Any]:
        """[WRITES DISK] Apply deterministic auto-spacing layout to canvas nodes."""
        return layout_canvas_nodes_impl(
            path=path,
            view_path=view_path,
            algorithm=algorithm,
            node_ids=node_ids,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            gap_x=gap_x,
            gap_y=gap_y,
            columns=columns,
            layout_mode=layout_mode,
        )

    @mcp.tool()
    def place_nodes_in_lane(
        path: str,
        view_path: str,
        node_ids: list[str],
        orientation: str = "vertical",
        lane_value: float = 0.0,
        start: float = 0.0,
        gap: float = 260.0,
        layout_mode: str = "rect",
    ) -> dict[str, Any]:
        """[WRITES DISK] Place selected kb_node items in a deterministic lane."""
        return place_nodes_in_lane_impl(
            path=path,
            view_path=view_path,
            node_ids=node_ids,
            orientation=orientation,
            lane_value=lane_value,
            start=start,
            gap=gap,
            layout_mode=layout_mode,
        )

    @mcp.tool()
    def layout_tree_from_root(
        path: str,
        view_path: str,
        root_node_id: str,
        traversal_link_type: str,
        orientation: str = "top_down",
        level_gap: float = 240.0,
        sibling_gap: float = 340.0,
        node_ids_scope: list[str] | None = None,
        layout_mode: str = "rect",
    ) -> dict[str, Any]:
        """[WRITES DISK] Layout a rooted tree by one traversal link type."""
        return layout_tree_from_root_impl(
            path=path,
            view_path=view_path,
            root_node_id=root_node_id,
            traversal_link_type=traversal_link_type,
            orientation=orientation,
            level_gap=level_gap,
            sibling_gap=sibling_gap,
            node_ids_scope=node_ids_scope,
            layout_mode=layout_mode,
        )

    @mcp.tool()
    def resolve_overlaps(
        path: str,
        view_path: str,
        node_ids: list[str] | None = None,
        padding: float = 24.0,
        max_iterations: int = 80,
    ) -> dict[str, Any]:
        """[WRITES DISK] Push overlapping kb_node items apart."""
        return resolve_overlaps_impl(
            path=path,
            view_path=view_path,
            node_ids=node_ids,
            padding=padding,
            max_iterations=max_iterations,
        )

    @mcp.tool()
    def optimize_layout(
        path: str,
        view_path: str,
        fixed_node_ids: list[str] | None = None,
        movable_node_ids: list[str] | None = None,
        link_type_ids: list[str] | None = None,
        iterations: int = 120,
        step_size: float = 0.18,
        min_distance: float = 220.0,
        layout_mode: str = "rect",
    ) -> dict[str, Any]:
        """[WRITES DISK] Optimize layout while optionally keeping fixed nodes pinned."""
        return optimize_layout_impl(
            path=path,
            view_path=view_path,
            fixed_node_ids=fixed_node_ids,
            movable_node_ids=movable_node_ids,
            link_type_ids=link_type_ids,
            iterations=iterations,
            step_size=step_size,
            min_distance=min_distance,
            layout_mode=layout_mode,
        )

    @mcp.tool()
    def export_canvas_png(
        path: str,
        view_path: str,
        output_path: str,
        width: int = 1600,
        height: int = 1000,
        padding: int = 64,
    ) -> dict[str, Any]:
        """[WRITES DISK] Export a lightweight PNG snapshot of the graph view."""
        return export_canvas_png_impl(
            path=path,
            view_path=view_path,
            output_path=output_path,
            width=width,
            height=height,
            padding=padding,
        )

    @mcp.tool()
    def render_view(
        path: str,
        view_path: str,
        output_path: str | None = None,
        width: int | None = None,
        height: int | None = None,
        padding: int = 0,
    ) -> dict[str, Any]:
        """[WRITES DISK] Render a viewport-anchored PNG for vision review and return its path."""
        return render_view_impl(
            path=path,
            view_path=view_path,
            output_path=output_path,
            width=width,
            height=height,
            padding=padding,
        )

    @mcp.tool()
    def set_link_type_visibility(
        path: str,
        view_path: str,
        link_type_id: str,
        visible: bool,
        ghost: bool = False,
    ) -> dict[str, Any]:
        """[WRITES DISK] Set link-type visibility metadata in the canvas view."""
        return set_link_type_visibility_impl(path, view_path, link_type_id, visible, ghost)

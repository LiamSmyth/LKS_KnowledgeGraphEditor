"""Repository lifecycle tools for knowledge MCP."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import _build_io, repo_status, resolve_existing_repo, result_envelope
from lks_utils.knowledge.canvas.canvas_io import CanvasIO
from lks_utils.knowledge.io.knowledge_io import KnowledgeIO


def _clear_views_via_canvasio(repo_root: Path, io: KnowledgeIO) -> None:
    views_dir = repo_root / "views"
    if not views_dir.exists():
        return
    for view_file in views_dir.glob("*.json"):
        if view_file.name.endswith("_viewport.json"):
            continue
        CanvasIO(view_path=view_file, knowledge_io=io).clear_view(
            clear_sidecar=True)


def clear_repo_contents_impl(
    path: str,
    *,
    delete_graph_views: bool = True,
    keep_system_link_types: bool = True,
) -> dict[str, Any]:
    """Delete repo contents through MCP-side semantics while keeping the repo root."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    result = io.clear_repo_contents()
    if result.ok and delete_graph_views:
        _clear_views_via_canvasio(resolved, io)

    if keep_system_link_types:
        seed_result = io.ensure_system_link_types()
        if not seed_result.ok:
            return {
                **result_envelope(seed_result),
                "path": str(resolved),
                "source_repo_id": io.source_repo_id,
            }

    return repo_status(resolved, io)


def open_repo_impl(path: str) -> dict[str, Any]:
    """Return repository status plus lightweight graph-view summary."""
    resolved = resolve_existing_repo(path)
    io = _build_io(path)
    status = repo_status(resolved, io)
    views = CanvasIO.list_graph_views(io)
    status["graph_view_count"] = len(views)
    status["graph_view_names"] = [view.name for view in sorted(
        views, key=lambda entry: entry.name.casefold())]
    return status


def register_repo_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def open_repo(path: str) -> dict[str, Any]:
        """[READ-ONLY] Load an existing knowledge repo directory and return status."""
        return open_repo_impl(path)

    @mcp.tool()
    def create_repo(path: str, source_repo_id: str = "default") -> dict[str, Any]:
        """[WRITES DISK] Create a new empty knowledge repo directory."""
        resolved = Path(path).resolve()
        io = KnowledgeIO.create_at(resolved, source_repo_id=source_repo_id)
        return repo_status(resolved, io)

    @mcp.tool()
    def save_repo_snapshot(path: str) -> str:
        """[WRITES DISK] Re-save the repository state."""
        resolved = resolve_existing_repo(path)
        io = _build_io(path)
        result = io.save_snapshot()
        if not result.ok:
            raise RuntimeError(
                result.error_message or result.save_error or "Failed to save repo snapshot")
        return str(resolved)

    @mcp.tool()
    def get_repo_projection(
        path: str,
        mode: Literal["compact", "schema", "links_compact"] = "compact",
    ) -> dict[str, Any]:
        """[READ-ONLY] Return concise projected repository views for low-noise clients."""
        from ai.mcp.knowledge.tools_schema import get_repo_schema_summary_impl
        from ai.mcp.knowledge.tools_links import list_links_compact_impl
        from ai.mcp.knowledge.common import node_compact

        if mode == "schema":
            return get_repo_schema_summary_impl(path)
        if mode == "links_compact":
            return {
                "mode": mode,
                "links": list_links_compact_impl(path, include_names=True),
            }
        io = _build_io(path)
        return {
            "mode": mode,
            "nodes": [node_compact(node) for node in io.list_nodes()],
            "link_types": [
                {
                    "id": link_type.id,
                    "name": link_type.name,
                    "cardinality": link_type.cardinality,
                    "is_system": link_type.is_system,
                }
                for link_type in io.list_link_types()
            ],
            "links": list_links_compact_impl(path, include_names=False),
        }

    @mcp.tool()
    def clear_repo_contents(
        path: str,
        delete_graph_views: bool = True,
        keep_system_link_types: bool = True,
    ) -> dict[str, Any]:
        """[WRITES DISK] Clear nodes, links, and link types from a repo root while preserving the repo directory."""
        return clear_repo_contents_impl(
            path,
            delete_graph_views=delete_graph_views,
            keep_system_link_types=keep_system_link_types,
        )

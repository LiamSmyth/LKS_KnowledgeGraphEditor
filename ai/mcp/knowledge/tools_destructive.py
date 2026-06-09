"""Destructive-operation tools for the knowledge MCP server.

These tools implement the two-phase preflight pattern:

1. ``check_delete_impact`` — pure read; returns a summary of incoming refs
   that would be broken by deleting the requested nodes.
2. ``delete_nodes`` — apply the deletion with an optional resolution dict
   that specifies how each broken ref should be handled.  Returns
   ``blocked`` when impact is non-empty and no resolution is supplied.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import _build_io, result_envelope
from lks_utils.knowledge.canvas.canvas_io import CanvasIO
from lks_utils.knowledge.io.delete_resolution import (
    DeleteResolution,
    DeleteResolutionEntry,
)


def _impact_to_dict(impact: Any) -> dict[str, Any]:
    """Serialize a :class:`DeleteImpact` to a JSON-ready dict."""
    return {
        "targets": list(impact.targets),
        "incoming_refs": [
            {
                "source_node_id": ref.source_node_id,
                "source_slot_path": list(ref.source_slot_path),
                "target_node_id": ref.target_node_id,
                "is_resolved": ref.is_resolved,
            }
            for ref in impact.incoming_refs
        ],
        "is_safe": impact.is_safe,
    }


def _resolution_from_dict(data: list[dict[str, Any]]) -> DeleteResolution:
    """Parse a list of resolution-entry dicts into a :class:`DeleteResolution`."""
    from lks_utils.knowledge.operations.delete_safety_analyzer import IncomingRef

    entries: list[DeleteResolutionEntry] = []
    for item in data:
        ref_data = item["incoming_ref"]
        ref = IncomingRef(
            source_node_id=ref_data["source_node_id"],
            source_slot_path=tuple(ref_data["source_slot_path"]),
            target_node_id=ref_data["target_node_id"],
            is_resolved=ref_data.get("is_resolved", False),
        )
        entries.append(
            DeleteResolutionEntry(
                incoming_ref=ref,
                mode=item["mode"],
                replacement_id=item.get("replacement_id"),
            )
        )
    return DeleteResolution(entries=tuple(entries))


def delete_node_and_clean_canvas_impl(
    path: str,
    node_id: str,
    *,
    force_cascade: bool = True,
) -> dict[str, Any]:
    """Delete one KB node and run scoped projection hygiene on affected canvases."""
    io = _build_io(path)
    preview = io.check_delete_impact(node_id)
    if not force_cascade and int(preview.get("blocking_link_count", 0)) > 0:
        return {
            "status": "blocked",
            "touched_ids": [],
            "validated_ids": [],
            "issues": [],
            "error_message": (
                f"Node {node_id!r} has incident links; "
                "set force_cascade=true or use delete_node_cascade."
            ),
            "blocking_impact": preview,
            "affected_view_paths": list(preview.get("affected_view_paths", [])),
            "hygiene_views_updated": [],
        }

    result = io.delete_node_cascade(node_id)
    out: dict[str, Any] = result_envelope(result)
    affected_paths = list(preview.get("affected_view_paths", []))
    out["affected_view_paths"] = affected_paths
    hygiene_views: list[str] = []
    if result.ok and result.effects is not None and affected_paths:
        hygiene_views = CanvasIO.apply_projection_hygiene_for_effects(
            io,
            result.effects,
            affected_view_ids=frozenset(affected_paths),
        )
    out["hygiene_views_updated"] = hygiene_views
    if result.blocking_impact is not None:
        out["blocking_impact"] = _impact_to_dict(result.blocking_impact)
    return out


def register_destructive_tools(mcp: FastMCP) -> None:
    """Register the two-phase delete tools on *mcp*."""

    @mcp.tool()
    def delete_node_and_clean_canvas(
        path: str,
        node_id: str,
        force_cascade: bool = True,
    ) -> dict[str, Any]:
        """[MUTATES] Delete one KB node and remove stale canvas placements in affected views.

        Runs index-backed delete fanout preview, cascade-deletes incident links,
        then applies scoped ``ProjectionHygiene`` on ``affected_view_paths``.
        Prefer this over ``delete_node`` + manual canvas cleanup for MCP agents.
        """
        return delete_node_and_clean_canvas_impl(
            path,
            node_id,
            force_cascade=force_cascade,
        )

    @mcp.tool()
    def check_delete_impact(path: str, node_ids: list[str]) -> dict[str, Any]:
        """[READ-ONLY] Return the delete impact for *node_ids* without mutating anything.

        Callers should inspect the returned ``incoming_refs`` to decide whether
        a resolution dict is needed before calling ``delete_nodes``.

        Returns a dict with keys:
        - ``targets``: list of node IDs that would be deleted.
        - ``incoming_refs``: list of ref descriptors (source, slot_path, target,
          is_resolved) for references that would become dangling.
        - ``is_safe``: ``true`` when ``incoming_refs`` is empty.
        """
        io = _build_io(path)
        impact = io.preview_delete_nodes(node_ids)
        return _impact_to_dict(impact)

    @mcp.tool()
    def delete_nodes(
        path: str,
        node_ids: list[str],
        resolution: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Delete nodes and handle incoming refs per *resolution*.

        *resolution* is a list of resolution-entry dicts, each with:
        - ``incoming_ref``: the ref descriptor from ``check_delete_impact``.
        - ``mode``: one of ``"leave_dangling"``, ``"remove_ref"``, ``"replace"``.
        - ``replacement_id`` (optional): required when mode is ``"replace"``.

        Returns a dict with keys:
        - ``status``: ``"ok"``, ``"blocked"``, or ``"error"``.
        - ``touched_ids``: list of changed node IDs (on success).
        - ``blocking_impact``: serialized impact dict when status is ``"blocked"``.
        - ``error_message``: error string when status is ``"error"``.

        When ``resolution`` is ``None`` and there are incoming refs, the call
        returns ``status="blocked"`` without mutating anything.
        """
        io = _build_io(path)
        parsed_resolution = _resolution_from_dict(
            resolution) if resolution else None
        result = io.delete_nodes(node_ids, resolution=parsed_resolution)
        out: dict[str, Any] = result_envelope(result)
        if result.blocking_impact is not None:
            out["blocking_impact"] = _impact_to_dict(result.blocking_impact)
        return out

    # ------------------------------------------------------------------
    # WO2: Single-node impact check + cascade link-type delete
    # ------------------------------------------------------------------

    @mcp.tool()
    def check_node_delete_impact(path: str, node_id: str) -> dict[str, Any]:
        """[READ-ONLY] Return link incidents for *node_id* (single-node variant).

        Unlike ``check_delete_impact`` (which uses slot-path refs), this tool
        reports raw link instances that reference the node as source or target.

        Returns a dict with keys:
        - ``blocking_link_ids``: list of link IDs incident to this node.
        - ``blocking_link_count``: integer count.
        - ``incident_link_types``: sorted list of link-type IDs involved.
        """
        io = _build_io(path)
        return io.check_delete_impact(node_id)

    @mcp.tool()
    def delete_link_type_cascade(path: str, link_type_id: str) -> dict[str, Any]:
        """[MUTATES] Delete a link type and all its instances atomically.

        All link instances of *link_type_id* are removed before the type record
        is deleted.  Fails if the link type does not exist.

        Returns a standard result envelope (``status``, ``touched_ids``, etc.).
        """
        io = _build_io(path)
        result = io.delete_link_type_cascade(link_type_id)
        return result_envelope(result)


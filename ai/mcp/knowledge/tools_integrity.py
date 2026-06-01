"""Integrity and validation tools for knowledge MCP."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import _build_io, result_envelope
from lks_utils.knowledge.io.knowledge_io import KnowledgeIO


def register_integrity_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def rebuild_index(path: str, validate_mode: str = "report_only") -> dict[str, Any]:
        """[WRITES DISK] Rebuild index.json from the current in-memory repository snapshot, then optionally validate."""
        io = KnowledgeIO.from_disk_scan(path)
        rebuild_result = io.rebuild_index()
        if not rebuild_result.ok:
            return result_envelope(rebuild_result)

        payload: dict[str, Any] = {
            **result_envelope(rebuild_result),
            "mode": validate_mode,
        }
        if validate_mode == "report_only":
            _, report = io.check_integrity(mode=validate_mode)
            payload.update(report)
            return payload

        op_result, report = io.check_integrity(mode=validate_mode)
        if op_result is None:
            payload.update(report)
            return payload
        payload.update(result_envelope(op_result))
        payload.update(report)
        return payload

    @mcp.tool()
    def validate_instance(path: str, instance_id: str) -> list[str]:
        """[READ-ONLY] Validate one instance node against its type slots."""
        io = _build_io(path)
        return io.validate_instance(instance_id)

    @mcp.tool()
    def check_integrity(path: str, mode: str = "report_only") -> dict[str, Any]:
        """[READ-ONLY or MUTATES] Report and optionally repair link integrity issues."""
        io = _build_io(path)
        op_result, payload = io.check_integrity(mode=mode)
        if op_result is None:
            return payload
        return {
            **result_envelope(op_result),
            **payload,
        }

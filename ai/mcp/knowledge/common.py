"""Shared helpers for the knowledge MCP server."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lks_utils.knowledge.io.knowledge_io import KnowledgeIO
from lks_utils.knowledge.io.operation_result import OperationResult
from lks_utils.knowledge.models.node import Node


def resolve_existing_repo(path: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"Knowledge repo not found: {resolved}")
    return resolved


def _build_io(path: str) -> KnowledgeIO:
    """Construct a :class:`KnowledgeIO` from a repository path."""
    resolved = resolve_existing_repo(path)
    return KnowledgeIO.from_path(resolved)


def result_envelope(result: OperationResult) -> dict[str, Any]:
    """Serialize :class:`OperationResult` into JSON-ready primitive fields."""
    return {
        "status": result.status,
        "touched_ids": sorted(result.touched_ids),
        "validated_ids": sorted(result.validated_ids),
        "issues": [
            {
                "object_id": issue.object_id,
                "reasons": list(issue.reasons),
            }
            for issue in result.issues
        ],
        "error_message": result.error_message,
        "save_error": result.save_error,
    }


def repo_status(path: Path, io: KnowledgeIO) -> dict[str, Any]:
    all_nodes = io.list_nodes()
    all_link_types = io.list_link_types()
    all_links = io.list_links()
    type_count = sum(1 for node in all_nodes if node.category == "_type")
    return {
        "path": str(path),
        "source_repo_id": io.source_repo_id,
        "node_count": len(all_nodes),
        "type_count": type_count,
        "instance_count": len(all_nodes) - type_count,
        "link_type_count": len(all_link_types),
        "link_count": len(all_links),
        "path_mode": "explicit-per-call",
        "immediate_atomic_save": True,
    }


def nodes_by_id(nodes: list[Node]) -> dict[str, Node]:
    return {str(node.id): node for node in nodes}


def node_summary(node: Node) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "name": node.name,
        "category": node.category,
        "type_id": str(node.type_id) if node.type_id else None,
        "rev": node.rev,
    }


def node_compact(node: Node) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "name": node.name,
        "category": node.category,
        "type_id": str(node.type_id) if node.type_id else None,
    }

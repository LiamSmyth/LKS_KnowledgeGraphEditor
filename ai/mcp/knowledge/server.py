"""MCP server bootstrap for semantic knowledge repository operations.

This entrypoint keeps the server surface focused on typed and semantic tools:
- Every tool takes an explicit repository path.
- Mutating tools save immediately and atomically.
- Tool registration is split across focused modules for maintainability.

Usage (stdio):
    python ai/mcp/knowledge/server.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Support both `python -m ai.mcp.knowledge.server` and
# `python ai/mcp/knowledge/server.py` launch styles.
if __package__ in (None, ""):
    _repo_root = Path(__file__).resolve().parents[3]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "The 'mcp' package is required to run the knowledge MCP server.\n"
        "Install it with: pip install mcp"
    ) from exc

from ai.mcp.knowledge.tools_batch import register_batch_tools
from ai.mcp.knowledge.tools_canvas import register_canvas_tools
from ai.mcp.knowledge.tools_destructive import register_destructive_tools
from ai.mcp.knowledge.tools_graph import register_graph_tools
from ai.mcp.knowledge.tools_help import register_help_tools
from ai.mcp.knowledge.tools_integrity import register_integrity_tools
from ai.mcp.knowledge.tools_links import register_link_tools
from ai.mcp.knowledge.tools_nodes import register_node_tools
from ai.mcp.knowledge.tools_repo import register_repo_tools
from ai.mcp.knowledge.tools_schema import register_schema_tools
from ai.mcp.knowledge.tools_structural import register_structural_tools


def create_server() -> FastMCP:
    """Create and configure the knowledge MCP server instance."""
    mcp = FastMCP("knowledge-repo")
    register_help_tools(mcp)
    register_repo_tools(mcp)
    register_node_tools(mcp)
    register_link_tools(mcp)
    register_schema_tools(mcp)
    register_graph_tools(mcp)
    register_structural_tools(mcp)
    register_batch_tools(mcp)
    register_canvas_tools(mcp)
    register_integrity_tools(mcp)
    register_destructive_tools(mcp)
    return mcp


mcp = create_server()


if __name__ == "__main__":
    mcp.run()

"""Self-guidance tools for the knowledge MCP server."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP


def get_usage_guide_impl() -> dict[str, Any]:
    """Return server usage guidance for low-ambiguity agent workflows."""
    return {
        "server": "knowledge-repo",
        "principles": {
            "path_required_per_call": True,
            "mcp_is_thin": True,
            "io_ownership": ["KnowledgeIO", "CanvasIO"],
            "mutations_save_atomically": True,
            "avoid_direct_json_edits": True,
        },
        "token_efficient_defaults": {
            "inventory": [
                "get_repo_inventory(mode='compact')",
                "list_instances_grouped_by_type(mode='compact')",
            ],
            "dedupe_preflight": [
                "suggest_existing_nodes(name_query, category?, type_query?)",
                "find_nodes_by_name(name_substring)",
            ],
            "ids_only_mode": "Use only when caller explicitly asks for id-only payloads.",
        },
        "tool_groups": {
            "repo": ["open_repo", "get_repo_projection", "get_repo_inventory", "save_repo_snapshot"],
            "discovery": [
                "list_nodes_compact",
                "list_links_compact",
                "find_nodes_by_name",
                "find_nodes_by_prop_value",
                "find_nodes_multi_prop",
                "query_nodes",
                "query_connected_nodes",
                "suggest_existing_nodes",
                "list_instances_grouped_by_type",
            ],
            "schema": [
                "get_repo_schema_summary",
                "get_parent_chain",
                "list_descendant_types_query",
                "list_instances_of_type_query",
            ],
            "mutation": [
                "ensure_instance",
                "ensure_link",
                "ensure_instance_and_place_node",
                "ensure_link_and_place_edge",
                "patch_node_props",
                "bulk_set_prop",
                "upsert_node",
                "upsert_link",
            ],
            "composite_canvas": [
                "ensure_instance_and_place_node",
                "ensure_link_and_place_edge",
                "delete_node_and_clean_canvas",
                "resolve_canvas_view_path",
                "get_view_context",
            ],
            "safety": [
                "validate_instance",
                "check_integrity",
                "check_node_delete_impact",
                "check_delete_impact",
                "delete_node_and_clean_canvas",
            ],
            "canvas": [
                "list_canvases",
                "resolve_canvas_view_path",
                "open_canvas",
                "get_view_context",
                "get_current_view",
                "get_canvas_graph_state",
                "get_canvas_graph_slice",
                "place_node",
                "layout_canvas_nodes",
                "render_view",
            ],
        },
        "write_guardrails": [
            "Prefer ensure_* for semantic create/update operations.",
            "Prefer patch_node_props for narrow property edits.",
            "Run delete impact checks before destructive operations.",
            "KB link create (ensure_link) does not place kb_edge — use ensure_link_and_place_edge when graph visibility is required.",
            "Prefer delete_node_and_clean_canvas over delete_node for MCP deletes that must clear canvas projections.",
            "Resolve canvas_ref (name/id/path) via resolve_canvas_view_path before canvas mutations.",
            "Render canvas views via render_view for visual verification.",
        ],
        "wo_scale_mutations_2026_06_08": {
            "validation_trust": "ValidationIndex + ProjectionValidator on load; iter_invalid() for issue counts.",
            "delete_fanout": "check_node_delete_impact / check_delete_impact use DeletePlanQuery (O(incident)); preview == commit fanout.",
            "mutation_engine": "In-place apply_op (no deepcopy); integrity delta on delete; fanout-only ValidationIndex.recompute.",
            "spec": "knowledge/ui/design/2026-06-08_kb-scale-mutations/functionality.md",
        },
        "quickstart": [
            "open_repo(path)",
            "get_repo_inventory(path, mode='compact')",
            "list_instances_grouped_by_type(path, mode='compact')",
            "suggest_existing_nodes(path, name_query='...', category?, type_query?)",
        ],
    }


def get_intent_playbook_impl(intent: str = "") -> dict[str, Any]:
    """Return an intent-oriented tool sequence to reduce tool-choice ambiguity."""
    normalized = intent.strip().lower()

    recipes: dict[str, dict[str, Any]] = {
        "explore": {
            "intent": "explore",
            "when": "Understand what already exists with minimal tokens.",
            "steps": [
                "open_repo(path)",
                "get_repo_inventory(path, mode='compact')",
                "list_instances_grouped_by_type(path, mode='compact')",
                "query_nodes(path, return_mode='compact', ...optional filters...)",
            ],
        },
        "dedupe_before_create": {
            "intent": "dedupe_before_create",
            "when": "Check for near-duplicates before creating nodes or links.",
            "steps": [
                "suggest_existing_nodes(path, name_query='...', category?, type_query?)",
                "find_nodes_by_name(path, name_substring='...')",
                "list_instances_of_type_query(path, type_query='...')",
                "ensure_instance(path, ...) only after review",
            ],
        },
        "targeted_edit": {
            "intent": "targeted_edit",
            "when": "Edit one field or one semantic relationship safely.",
            "steps": [
                "open_repo(path)",
                "patch_node_props(path, node_id, props, expected_revision_id?)",
                "ensure_link(path, source_node_name/id, target_node_name/id, link_type_name/id)",
                "validate_instance(path, instance_id) when schema-sensitive",
            ],
        },
        "safe_delete": {
            "intent": "safe_delete",
            "when": "Delete without accidental data-loss.",
            "steps": [
                "check_node_delete_impact(path, node_id) or check_delete_impact(path, node_ids)",
                "delete_node(path, node_id) for safe path",
                "delete_node_cascade(path, node_id) only with explicit force intent",
            ],
        },
        "canvas_review": {
            "intent": "canvas_review",
            "when": "Inspect or update canvas-layer graph placement.",
            "steps": [
                "list_canvases(path) or resolve_canvas_view_path(path, canvas_ref)",
                "get_view_context(path, view_path)",
                "get_canvas_graph_state(path, view_path, mode='compact')",
                "layout_canvas_nodes(path, view_path, ...optional...)",
                "render_view(path, view_path, ...)",
            ],
        },
        "sync_canvas_to_module": {
            "intent": "sync_canvas_to_module",
            "when": "Update a graph canvas so it reflects KB module/content the user is viewing.",
            "steps": [
                "get_usage_guide()",
                "open_repo(path)",
                "resolve_canvas_view_path(path, canvas_ref) -> view_path",
                "get_view_context(path, view_path) for current placements + in-view nodes",
                "get_repo_inventory(path, mode='compact') + list_instances_grouped_by_type(path, mode='compact')",
                "query_nodes / query_connected_nodes to find module instances missing from canvas",
                "ensure_instance_and_place_node(...) for each missing instance (one-shot create+place)",
                "ensure_link_and_place_edge(...) for graph edges that must be visible",
                "layout_canvas_nodes(path, view_path, ...) when density/overlap is high",
                "render_view(path, view_path, ...) for vision verification",
                "check_integrity(path, mode='report_only')",
            ],
        },
    }

    if not normalized:
        return {
            "available_intents": sorted(recipes.keys()),
            "default": recipes["explore"],
            "note": "Pass intent to receive a focused sequence, for example: explore, dedupe_before_create, targeted_edit, safe_delete, canvas_review, sync_canvas_to_module.",
        }

    if normalized in recipes:
        return recipes[normalized]

    return {
        "available_intents": sorted(recipes.keys()),
        "matched": None,
        "note": f"Unknown intent '{intent}'. Use one of the available intents.",
    }


def register_help_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_usage_guide() -> dict[str, Any]:
        """[READ-ONLY] Return server-level usage guidance, guardrails, and token-efficient defaults."""
        return get_usage_guide_impl()

    @mcp.tool()
    def get_intent_playbook(intent: str = "") -> dict[str, Any]:
        """[READ-ONLY] Return intent-specific tool sequence recommendations for KB operations."""
        return get_intent_playbook_impl(intent)

"""Structural mutation tools for knowledge MCP."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.mcp.knowledge.common import _build_io, result_envelope


def set_slot_value_impl(path: str, node_id: str, slot_name: str, value: Any) -> dict[str, Any]:
    """Set one node slot value through Mutator + KnowledgeIO."""
    io = _build_io(path)
    result = io.set_slot_value(
        node_id=node_id, slot_name=slot_name, value=value)
    node = io.get_node(node_id)
    return {
        **result_envelope(result),
        "node": node.model_dump(),
    }


def clear_slot_value_impl(path: str, node_id: str, slot_name: str) -> dict[str, Any]:
    """Clear one node slot value through Mutator + KnowledgeIO."""
    io = _build_io(path)
    result = io.clear_slot_value(node_id=node_id, slot_name=slot_name)
    node = io.get_node(node_id)
    return {
        **result_envelope(result),
        "node": node.model_dump(),
    }


def set_slot_values_impl(path: str, node_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Set multiple node slot values through Mutator + KnowledgeIO."""
    io = _build_io(path)
    result = io.set_slot_values(node_id=node_id, updates=updates)
    node = io.get_node(node_id)
    return {
        **result_envelope(result),
        "node": node.model_dump(),
    }


def clear_slot_values_impl(path: str, node_id: str, slot_names: list[str]) -> dict[str, Any]:
    """Clear multiple node slot values through Mutator + KnowledgeIO."""
    io = _build_io(path)
    result = io.clear_slot_values(node_id=node_id, slot_names=slot_names)
    node = io.get_node(node_id)
    return {
        **result_envelope(result),
        "node": node.model_dump(),
    }


def register_structural_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def promote_inline(
        path: str,
        parent_id: str,
        prop_path: str,
        new_name: str,
        description: str,
    ) -> dict[str, Any]:
        """[MUTATES] Promote an inline composite to a standalone node."""
        io = _build_io(path)
        result, promoted_id = io.promote_inline(
            parent_id=parent_id,
            prop_path=prop_path,
            new_name=new_name,
            description=description,
        )
        payload = io.get_node(promoted_id).model_dump(
        ) if promoted_id is not None else None
        return {
            **result_envelope(result),
            "id": payload.get("id") if payload else None,
            "name": payload.get("name") if payload else None,
            "description": payload.get("description") if payload else None,
        }

    @mcp.tool()
    def inline_ref(path: str, parent_id: str, prop_path: str) -> dict[str, Any]:
        """[MUTATES] Inline a single-ref node back into parent props."""
        io = _build_io(path)
        result = io.inline_ref(parent_id=parent_id, prop_path=prop_path)
        return {
            **result_envelope(result),
            "parent_id": parent_id,
            "prop_path": prop_path,
        }

    @mcp.tool()
    def add_slot_to_type(
        path: str,
        type_id: str,
        slot: dict[str, Any],
    ) -> dict[str, Any]:
        """[MUTATES] Add or replace one slot on a type node."""
        io = _build_io(path)
        result = io.add_slot_to_type(type_id=type_id, slot=slot)
        updated = io.get_node(type_id)
        return {
            **result_envelope(result),
            "node": updated.model_dump(),
        }

    @mcp.tool()
    def remove_slot_from_type(path: str, type_id: str, slot_name: str) -> dict[str, Any]:
        """[MUTATES] Remove a slot by name from a type node."""
        io = _build_io(path)
        result = io.remove_slot_from_type(type_id=type_id, slot_name=slot_name)
        updated = io.get_node(type_id)
        return {
            **result_envelope(result),
            "node": updated.model_dump(),
        }

    @mcp.tool()
    def update_slot_on_type(
        path: str,
        type_id: str,
        original_name: str,
        slot: dict[str, Any],
    ) -> dict[str, Any]:
        """[MUTATES] Update one slot contract on a type node by original slot name."""
        io = _build_io(path)
        result = io.update_slot_on_type(
            type_id=type_id,
            original_name=original_name,
            slot=slot,
        )
        updated = io.get_node(type_id)
        return {
            **result_envelope(result),
            "node": updated.model_dump(),
        }

    @mcp.tool()
    def set_slot_value(path: str, node_id: str, slot_name: str, value: Any) -> dict[str, Any]:
        """[MUTATES] Set one node slot value through Mutator + KnowledgeIO."""
        return set_slot_value_impl(path, node_id, slot_name, value)

    @mcp.tool()
    def clear_slot_value(path: str, node_id: str, slot_name: str) -> dict[str, Any]:
        """[MUTATES] Clear one node slot value through Mutator + KnowledgeIO."""
        return clear_slot_value_impl(path, node_id, slot_name)

    @mcp.tool()
    def set_slot_values(path: str, node_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """[MUTATES] Set multiple node slot values through Mutator + KnowledgeIO."""
        return set_slot_values_impl(path, node_id, updates)

    @mcp.tool()
    def clear_slot_values(path: str, node_id: str, slot_names: list[str]) -> dict[str, Any]:
        """[MUTATES] Clear multiple node slot values through Mutator + KnowledgeIO."""
        return clear_slot_values_impl(path, node_id, slot_names)

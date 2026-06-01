"""Serializer for splitting node payload writes into node + link records."""
from __future__ import annotations

from dataclasses import dataclass

from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.repository import Repository


@dataclass(frozen=True)
class NodeSaveSplit:
    """Split representation used by future edge-aware save flows."""

    node_payload: dict[str, object]
    link_records: list[dict[str, object]]


class LinkSerializer:
    """Split and apply node-save payloads into node data + slot_ref edges."""

    def split_save_payload(self, node_payload: dict[str, object]) -> NodeSaveSplit:
        payload_copy = dict(node_payload)
        raw_props = payload_copy.get("props")
        props = dict(raw_props) if isinstance(raw_props, dict) else {}
        source_node_id = str(payload_copy.get("id", "")).strip()
        if not source_node_id:
            raise ValueError(
                "node_payload must include a non-empty 'id' field")

        cleaned_props: dict[str, object] = {}
        for slot_name, value in props.items():
            if not isinstance(slot_name, str):
                continue
            cleaned_props[slot_name] = value
        payload_copy["props"] = cleaned_props
        return NodeSaveSplit(node_payload=payload_copy, link_records=[])

    def upsert_from_payload(
        self,
        io: object,
        node_payload: dict[str, object],
    ) -> NodeSaveSplit:
        """Write one payload via KnowledgeIO.apply_op and return its split.

        *io* must be a :class:`~lks_utils.knowledge.io.knowledge_io.KnowledgeIO`
        instance.  Writes are routed through ``apply_op`` so they pass the
        integrity gate and persistence path.
        """
        from lks_utils.knowledge.io.knowledge_io import KnowledgeIO

        if not isinstance(io, KnowledgeIO):
            raise TypeError(
                f"upsert_from_payload expects a KnowledgeIO, got {type(io).__name__}"
            )

        split = self.split_save_payload(node_payload)

        def _mutator(repo: Repository) -> set[str]:
            node = Node.model_validate(split.node_payload)
            repo.upsert(node)
            return {str(node.id)}

        io.apply_op(_mutator)
        return split


__all__ = ["LinkSerializer", "NodeSaveSplit"]

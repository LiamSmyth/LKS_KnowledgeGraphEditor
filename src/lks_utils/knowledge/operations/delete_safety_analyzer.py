"""Analyze inbound-reference safety for knowledge deletes."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.repository import Repository


@dataclass(frozen=True, slots=True)
class IncomingRef:
    """One inbound reference from a source node to a delete target."""

    source_node_id: str
    source_slot_path: tuple[str, ...]
    target_node_id: str
    is_resolved: bool


@dataclass(frozen=True, slots=True)
class DeleteImpact:
    """Delete-target set plus inbound refs from outside that set."""

    targets: tuple[str, ...]
    incoming_refs: tuple[IncomingRef, ...]

    @property
    def is_safe(self) -> bool:
        """Return whether deleting the targets would strand no external refs."""
        return not self.incoming_refs


def analyze_delete_impact(
    repo: Repository,
    target_node_ids: Iterable[str],
) -> DeleteImpact:
    """Return inbound refs from outside the delete set.

    Refs between members of the same delete set are ignored because those
    relationships disappear together.
    """
    target_ids = tuple(dict.fromkeys(str(node_id)
                       for node_id in target_node_ids))
    target_id_set = set(target_ids)
    if not target_ids:
        return DeleteImpact(targets=(), incoming_refs=())

    existing_node_ids = {str(node.id) for node in repo.list_nodes()}
    incoming_refs: list[IncomingRef] = []

    for node in repo.list_nodes():
        source_node_id = str(node.id)
        if source_node_id in target_id_set:
            continue

        if node.type_id is not None:
            target_node_id = str(node.type_id)
            if target_node_id in target_id_set:
                incoming_refs.append(
                    IncomingRef(
                        source_node_id=source_node_id,
                        source_slot_path=("type_id",),
                        target_node_id=target_node_id,
                        is_resolved=target_node_id in existing_node_ids,
                    )
                )

    for link in repo.list_links():
        if link.link_type_id != SLOT_REF_LINK_TYPE_ID:
            continue
        source_node_id = str(link.source_node_id)
        if source_node_id in target_id_set:
            continue
        target_node_id = str(link.target_node_id)
        if target_node_id not in target_id_set:
            continue
        source_slot = str(link.source_slot_name or "")
        path = (source_slot,) if source_slot else ("slot_ref",)
        incoming_refs.append(
            IncomingRef(
                source_node_id=source_node_id,
                source_slot_path=path,
                target_node_id=target_node_id,
                is_resolved=target_node_id in existing_node_ids,
            )
        )

    incoming_refs.sort(
        key=lambda incoming_ref: (
            incoming_ref.source_slot_path,
            incoming_ref.source_node_id,
            incoming_ref.target_node_id,
        )
    )
    return DeleteImpact(targets=target_ids, incoming_refs=tuple(incoming_refs))


__all__ = ["DeleteImpact", "IncomingRef", "analyze_delete_impact"]

"""Index-backed read-only delete impact queries."""
from __future__ import annotations

from collections.abc import Iterable

from lks_utils.knowledge.impact_fanout import ImpactFanout, UxTier
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.operations.delete_impact_types import DeleteImpact, IncomingRef
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.repository_indexes import RepositoryIndexes


def _slot_path(link) -> tuple[str, ...]:
    if str(link.link_type_id) == SLOT_REF_LINK_TYPE_ID:
        slot = str(link.source_slot_name or "")
        return (slot,) if slot else ("slot_ref",)
    if str(link.link_type_id) == INSTANCE_OF_LINK_TYPE_ID:
        return ("instance_of",)
    if str(link.link_type_id) == EXTENDS_LINK_TYPE_ID:
        return ("extends",)
    return ("system_ref",)


class DeletePlanQuery:
    """Produce ephemeral :class:`ImpactFanout` without full-repo scans."""

    def __init__(
        self,
        repository: Repository,
        indexes: RepositoryIndexes,
    ) -> None:
        self._repository = repository
        self._indexes = indexes

    def node_delete_fanout(self, target_node_ids: Iterable[str]) -> ImpactFanout:
        target_ids = tuple(dict.fromkeys(str(node_id) for node_id in target_node_ids))
        target_id_set = set(target_ids)
        if not target_ids:
            return ImpactFanout(
                targets=(),
                incoming_system_refs=(),
                cascade_link_ids=(),
                cascade_instance_ids=(),
                validation_fanout_ids=frozenset(),
                validation_mode="touched_only",
                integrity_link_delta=(),
                affected_view_paths=(),
                ux_tier="silent",
            )

        existing_node_ids = {str(node.id) for node in self._repository.list_nodes()}
        incoming_refs: list[IncomingRef] = []
        cascade_link_ids: set[str] = set()
        validation_ids: set[str] = set(target_id_set)

        for target_id in target_ids:
            for link in self._indexes.incoming_system_refs(target_id):
                source_id = str(link.source_node_id)
                if source_id in target_id_set:
                    continue
                incoming_refs.append(
                    IncomingRef(
                        source_node_id=source_id,
                        source_slot_path=_slot_path(link),
                        target_node_id=target_id,
                        is_resolved=target_id in existing_node_ids,
                    )
                )
                validation_ids.add(source_id)

            for link_id in self._indexes.incident_link_ids(target_id):
                link = self._indexes.link_by_id(link_id)
                if link is None:
                    continue
                link_type = self._repository.find_link_type(str(link.link_type_id))
                if link_type is not None and link_type.is_system:
                    if str(link.link_type_id) in {
                        SLOT_REF_LINK_TYPE_ID,
                        INSTANCE_OF_LINK_TYPE_ID,
                        EXTENDS_LINK_TYPE_ID,
                    }:
                        continue
                cascade_link_ids.add(link_id)
                validation_ids.add(str(link.source_node_id))
                validation_ids.add(str(link.target_node_id))

        incoming_refs.sort(
            key=lambda ref: (ref.source_slot_path, ref.source_node_id, ref.target_node_id)
        )
        ux_tier: UxTier = "silent" if not incoming_refs else "dialog"
        affected_views = self._affected_view_paths(target_id_set | validation_ids)

        return ImpactFanout(
            targets=target_ids,
            incoming_system_refs=tuple(incoming_refs),
            cascade_link_ids=tuple(sorted(cascade_link_ids)),
            cascade_instance_ids=(),
            validation_fanout_ids=frozenset(validation_ids),
            validation_mode="expanded",
            integrity_link_delta=tuple(sorted(cascade_link_ids)),
            affected_view_paths=affected_views,
            ux_tier=ux_tier,
        )

    def node_delete_impact(self, target_node_ids: Iterable[str]) -> DeleteImpact:
        fanout = self.node_delete_fanout(target_node_ids)
        return DeleteImpact(
            targets=fanout.targets,
            incoming_refs=fanout.incoming_system_refs,
        )

    def link_type_delete_fanout(self, link_type_id: str) -> ImpactFanout:
        link_ids = sorted(self._indexes.links_of_type(link_type_id))
        affected_nodes: set[str] = set()
        for link_id in link_ids:
            link = self._indexes.link_by_id(link_id)
            if link is None:
                continue
            affected_nodes.add(str(link.source_node_id))
            affected_nodes.add(str(link.target_node_id))
        ux_tier: UxTier = "silent" if not link_ids else "dialog"
        return ImpactFanout(
            targets=(link_type_id,),
            incoming_system_refs=(),
            cascade_link_ids=tuple(link_ids),
            cascade_instance_ids=(),
            validation_fanout_ids=frozenset(affected_nodes),
            validation_mode="expanded",
            integrity_link_delta=tuple(link_ids),
            affected_view_paths=self._affected_view_paths(affected_nodes),
            ux_tier=ux_tier,
        )

    def _affected_view_paths(self, node_ids: set[str]) -> tuple[str, ...]:
        if not node_ids:
            return ()
        paths: list[str] = []
        try:
            views = self._repository.list_graph_views()
        except Exception:
            return ()
        for view in views:
            if self._view_contains_any(view, node_ids):
                paths.append(str(view.id))
        return tuple(sorted(paths))

    @staticmethod
    def _view_contains_any(view: GraphView, node_ids: set[str]) -> bool:
        for proxy in view.nodes.values():
            if proxy.global_id in node_ids:
                return True
        return False


__all__ = ["DeletePlanQuery"]

"""Validate graph-view placements against repository existence."""
from __future__ import annotations

from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.projection_issue import ProjectionIssue


class ProjectionValidator:
    """Detect orphan kb_node placements and stale kb_edge link ids."""

    @staticmethod
    def scan_graph_views(
        graph_views: list[GraphView],
        existing_node_ids: set[str],
        existing_link_ids: set[str] | None = None,
    ) -> list[ProjectionIssue]:
        """Return projection issues for all supplied graph views."""
        link_ids = existing_link_ids if existing_link_ids is not None else set()
        issues: list[ProjectionIssue] = []
        for graph_view in graph_views:
            for proxy in graph_view.nodes.values():
                global_id = str(proxy.global_id)
                if global_id not in existing_node_ids:
                    issues.append(
                        ProjectionIssue(
                            object_id=global_id,
                            code="orphan_kb_node",
                            detail=(
                                f"Graph view '{graph_view.name}' places missing "
                                f"node id {global_id}."
                            ),
                        )
                    )
            if existing_link_ids is None:
                continue
            for edge in graph_view.edges.values():
                global_link_id = str(edge.global_link_id)
                if global_link_id not in link_ids:
                    issues.append(
                        ProjectionIssue(
                            object_id=global_link_id,
                            code="stale_kb_edge",
                            detail=(
                                f"Graph view '{graph_view.name}' references missing "
                                f"link id {global_link_id}."
                            ),
                        )
                    )
        return issues


__all__ = ["ProjectionValidator"]

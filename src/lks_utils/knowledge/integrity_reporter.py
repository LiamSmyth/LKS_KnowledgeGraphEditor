"""Deterministic integrity reporting for knowledge graph links."""
from __future__ import annotations

from collections import defaultdict

from lks_utils.knowledge._editor_session.selection import resolve_ref_type_to_type_ids
from lks_utils.knowledge.integrity_issue import IntegrityIssue
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID, LinkType
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.type import is_type
from lks_utils.knowledge.repository import Repository


class IntegrityReporter:
    """Emit deterministic integrity issues for the current repository state."""

    @staticmethod
    def fatal_only(repository: Repository) -> list[IntegrityIssue]:
        """Return fatal integrity issues that must block persistence.

        Current integrity checks represent invalid-but-allowed authoring states,
        so none are fatal yet.
        """
        _ = repository
        return []

    def report(self, repository: Repository) -> list[IntegrityIssue]:
        """Return all known link-integrity issues in stable order."""
        nodes: dict[str, Node] = {
            str(node.id): node for node in repository.list_nodes()}
        link_types: dict[str, LinkType] = {
            link_type.id: link_type for link_type in repository.list_link_types()
        }
        links = repository.list_links()

        issues: list[IntegrityIssue] = []
        grouped_by_source_and_type: dict[tuple[str,
                                               str], list[str]] = defaultdict(list)

        for link in links:
            grouped_by_source_and_type[(
                link.source_node_id, link.link_type_id)].append(link.id)

            if link.link_type_id not in link_types:
                issues.append(
                    IntegrityIssue(
                        code="dangling_link_type",
                        link_id=link.id,
                        link_type_id=link.link_type_id,
                        source_node_id=link.source_node_id,
                        target_node_id=link.target_node_id,
                        detail="Link points to missing LinkType.",
                    )
                )

            if link.source_node_id not in nodes:
                issues.append(
                    IntegrityIssue(
                        code="dangling_source_node",
                        link_id=link.id,
                        link_type_id=link.link_type_id,
                        source_node_id=link.source_node_id,
                        target_node_id=link.target_node_id,
                        detail="Link source node does not exist.",
                    )
                )

            if link.target_node_id not in nodes:
                issues.append(
                    IntegrityIssue(
                        code="dangling_target_node",
                        link_id=link.id,
                        link_type_id=link.link_type_id,
                        source_node_id=link.source_node_id,
                        target_node_id=link.target_node_id,
                        detail="Link target node does not exist.",
                    )
                )

            if link.link_type_id == SLOT_REF_LINK_TYPE_ID:
                if not (link.source_slot_name or "").strip():
                    issues.append(
                        IntegrityIssue(
                            code="slot_ref_missing_source_slot",
                            link_id=link.id,
                            link_type_id=link.link_type_id,
                            source_node_id=link.source_node_id,
                            target_node_id=link.target_node_id,
                            detail="slot_ref links must have source_slot_name set.",
                        )
                    )
            elif link.source_slot_name is not None:
                issues.append(
                    IntegrityIssue(
                        code="non_slot_ref_carries_source_slot",
                        link_id=link.id,
                        link_type_id=link.link_type_id,
                        source_node_id=link.source_node_id,
                        target_node_id=link.target_node_id,
                        detail="Only slot_ref links may carry source_slot_name.",
                    )
                )

            link_type = link_types.get(link.link_type_id)
            source_node = nodes.get(link.source_node_id)
            target_node = nodes.get(link.target_node_id)

            if link_type is None or source_node is None or target_node is None:
                continue

            if not self._matches_constraint(repository, source_node, link_type.source_type_constraint):
                issues.append(
                    IntegrityIssue(
                        code="source_constraint_violation",
                        link_id=link.id,
                        link_type_id=link.link_type_id,
                        source_node_id=link.source_node_id,
                        target_node_id=link.target_node_id,
                        detail=(
                            "Source node does not satisfy "
                            f"constraint '{link_type.source_type_constraint}'."
                        ),
                    )
                )

            if not self._matches_constraint(repository, target_node, link_type.target_type_constraint):
                issues.append(
                    IntegrityIssue(
                        code="target_constraint_violation",
                        link_id=link.id,
                        link_type_id=link.link_type_id,
                        source_node_id=link.source_node_id,
                        target_node_id=link.target_node_id,
                        detail=(
                            "Target node does not satisfy "
                            f"constraint '{link_type.target_type_constraint}'."
                        ),
                    )
                )

        for (source_node_id, link_type_id), link_ids in grouped_by_source_and_type.items():
            link_type = link_types.get(link_type_id)
            if link_type is None or link_type.cardinality != "one":
                continue
            ordered_link_ids = sorted(link_ids)
            for duplicate_link_id in ordered_link_ids[1:]:
                issues.append(
                    IntegrityIssue(
                        code="cardinality_violation",
                        link_id=duplicate_link_id,
                        link_type_id=link_type_id,
                        source_node_id=source_node_id,
                        detail="More than one outgoing edge for cardinality='one'.",
                    )
                )

        return sorted(
            issues,
            key=lambda issue: (
                issue.code,
                issue.link_id or "",
                issue.source_node_id or "",
                issue.target_node_id or "",
            ),
        )

    def _matches_constraint(self, repository: Repository, node: Node, constraint: str | None) -> bool:
        if constraint is None or not constraint.strip():
            return True
        normalized = constraint.strip().casefold()
        if normalized == "type":
            return node.category == "_type"
        if normalized == "instance":
            return node.category != "_type"

        allowed_type_ids = resolve_ref_type_to_type_ids(
            iter_types=repository.list_types(),
            token=normalized,
            iter_links=repository.list_links(),
            iter_link_types=repository.list_link_types(),
        )
        if allowed_type_ids:
            if node.type_id is not None and str(node.type_id) in allowed_type_ids:
                return True
            if is_type(node) and str(node.id) in allowed_type_ids:
                return True
        return False


__all__ = ["IntegrityReporter"]

"""Analyze inbound-reference safety for knowledge deletes."""
from __future__ import annotations

from collections.abc import Iterable

from lks_utils.knowledge.operations.delete_impact_types import DeleteImpact, IncomingRef
from lks_utils.knowledge.operations.delete_plan_query import DeletePlanQuery
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.repository_indexes import RepositoryIndexes


def analyze_delete_impact(
    repo: Repository,
    target_node_ids: Iterable[str],
    *,
    indexes: RepositoryIndexes | None = None,
) -> DeleteImpact:
    """Return inbound system refs from outside the delete set.

    Uses index-backed :class:`DeletePlanQuery` — no full ``list_nodes`` scan
    for referencer discovery. Refs between members of the same delete set are
    ignored because those relationships disappear together.
    """
    if indexes is None:
        indexes = RepositoryIndexes()
        indexes.rebuild_from(repo)
    return DeletePlanQuery(repo, indexes).node_delete_impact(target_node_ids)


__all__ = ["DeleteImpact", "IncomingRef", "analyze_delete_impact"]

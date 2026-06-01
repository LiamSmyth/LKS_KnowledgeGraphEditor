"""Mutation bookkeeping helpers for EditorSession."""
from __future__ import annotations

from lks_utils.knowledge.repository import Repository


def compute_all_touched_ids(repo: Repository) -> set[str]:
    """Return a full touched-id set when mutation fn does not report ids."""
    all_ids: set[str] = {str(n.id) for n in repo.list_nodes()}
    all_ids.update(lt.id for lt in repo.list_link_types())
    all_ids.update(lk.id for lk in repo.list_links())
    return all_ids

"""Repository snapshot adoption helpers for EditorSession."""
from __future__ import annotations

from lks_utils.knowledge.repository import Repository


def adopt_repository_snapshot(*, target: Repository, source: Repository) -> None:
    """Copy repository internals from *source* into stable-identity *target*."""
    target._nodes = source._nodes  # noqa: SLF001
    target._link_types = source._link_types  # noqa: SLF001
    target._links = source._links  # noqa: SLF001
    target._source_repo_id = source._source_repo_id  # noqa: SLF001
    target._repo_root = source._repo_root  # noqa: SLF001
    target._names = source._names  # noqa: SLF001
    target._link_type_names = source._link_type_names  # noqa: SLF001

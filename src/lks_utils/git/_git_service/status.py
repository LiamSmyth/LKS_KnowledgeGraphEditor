"""Status helpers for KnowledgeGitService."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pygit2

if TYPE_CHECKING:
    from lks_utils.knowledge.git_status import GitStatus


def _git_status_type() -> type[GitStatus]:
    from lks_utils.knowledge.git_status import GitStatus

    return GitStatus


def empty_git_status() -> GitStatus:
    """Return an empty status payload."""
    git_status = _git_status_type()
    return git_status(
        modified_paths=set(),
        staged_paths=set(),
        unstaged_paths=set(),
        untracked_paths=set(),
        deleted_paths=set(),
        status_flags={},
    )


def status_from_map(status_map: dict[str, int]) -> GitStatus:
    """Convert a pygit2 status map into normalized status buckets."""
    modified_paths: set[str] = set()
    staged_paths: set[str] = set()
    unstaged_paths: set[str] = set()
    untracked_paths: set[str] = set()
    deleted_paths: set[str] = set()
    status_flags: dict[str, int] = {}

    for raw_path, flag in status_map.items():
        path = str(raw_path).replace("\\", "/")
        status_flags[path] = flag
        if flag & pygit2.GIT_STATUS_WT_NEW:
            untracked_paths.add(path)
        if flag & pygit2.GIT_STATUS_INDEX_NEW:
            staged_paths.add(path)
        if flag & (
            pygit2.GIT_STATUS_INDEX_MODIFIED
            | pygit2.GIT_STATUS_INDEX_RENAMED
            | pygit2.GIT_STATUS_INDEX_TYPECHANGE
        ):
            staged_paths.add(path)
        if flag & (
            pygit2.GIT_STATUS_WT_MODIFIED
            | pygit2.GIT_STATUS_WT_RENAMED
            | pygit2.GIT_STATUS_WT_TYPECHANGE
        ):
            unstaged_paths.add(path)
        if flag & (
            pygit2.GIT_STATUS_WT_DELETED
            | pygit2.GIT_STATUS_INDEX_DELETED
        ):
            deleted_paths.add(path)

        if flag != pygit2.GIT_STATUS_CURRENT:
            modified_paths.add(path)

    git_status = _git_status_type()
    return git_status(
        modified_paths=modified_paths,
        staged_paths=staged_paths,
        unstaged_paths=unstaged_paths,
        untracked_paths=untracked_paths,
        deleted_paths=deleted_paths,
        status_flags=status_flags,
    )


def read_repo_status(repo: pygit2.Repository) -> GitStatus:
    """Read and normalize status from a repository instance."""
    try:
        return status_from_map(repo.status())
    except Exception:
        return empty_git_status()


def open_repository(path: Path) -> pygit2.Repository | None:
    """Open a repository rooted exactly at path, or None when absent."""
    git_marker = path / ".git"
    if not git_marker.exists():
        return None
    try:
        return pygit2.Repository(str(path))
    except (KeyError, pygit2.GitError):
        return None

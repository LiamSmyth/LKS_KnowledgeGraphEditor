"""Diff and content helpers for KnowledgeGitService."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygit2

if TYPE_CHECKING:
    from lks_utils.knowledge.git_status import GitStatus


def diff_file(repo: pygit2.Repository | None, rel_path: str, *, staged: bool = False) -> str:
    """Return unified diff patch text for one path."""
    if repo is None:
        return ""
    normalized = rel_path.replace("\\", "/")
    try:
        head_tree = (
            repo.head.peel(pygit2.Tree)
            if not repo.head_is_unborn
            else None
        )
    except (KeyError, pygit2.GitError):
        head_tree = None

    try:
        if staged:
            diff = repo.index.diff_to_tree(head_tree)
        else:
            diff = repo.diff(head_tree)
    except Exception:
        return ""

    hunks: list[str] = []
    for patch in diff:
        new_file = patch.delta.new_file.path or ""
        old_file = patch.delta.old_file.path or ""
        if normalized not in {new_file, old_file}:
            continue
        hunks.append(patch.text)
    return "\n".join(hunks)


def change_code(
    repo: pygit2.Repository | None,
    cached_status: GitStatus,
    rel_path: str,
) -> str:
    """Return one-letter change code for rel_path using status flags."""
    if repo is None:
        return ""
    normalized = rel_path.replace("\\", "/")
    flag = cached_status.status_flags.get(
        normalized, pygit2.GIT_STATUS_CURRENT)
    if flag & (
        pygit2.GIT_STATUS_WT_DELETED
        | pygit2.GIT_STATUS_INDEX_DELETED
    ):
        return "D"
    if flag & (
        pygit2.GIT_STATUS_WT_NEW
        | pygit2.GIT_STATUS_INDEX_NEW
    ):
        return "U"
    if flag != pygit2.GIT_STATUS_CURRENT:
        return "M"
    return ""


def read_head_text(repo: pygit2.Repository | None, rel_path: str) -> str | None:
    """Return UTF-8 text for one HEAD-relative path, or None if absent."""
    if repo is None or repo.head_is_unborn:
        return None
    normalized = rel_path.replace("\\", "/")
    try:
        tree = repo.head.peel(pygit2.Tree)
        entry = tree[normalized]
        blob = repo.get(entry.id)
        raw = bytes(blob.data)
        return raw.decode("utf-8")
    except Exception:
        return None

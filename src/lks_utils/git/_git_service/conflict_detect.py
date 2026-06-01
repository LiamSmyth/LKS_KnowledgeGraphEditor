"""History and message helpers for KnowledgeGitService."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygit2

if TYPE_CHECKING:
    from lks_utils.knowledge.commit_info import CommitInfo
    from lks_utils.knowledge.git_status import GitStatus


def _commit_info_type() -> type[CommitInfo]:
    from lks_utils.knowledge.commit_info import CommitInfo

    return CommitInfo


def commit_touches_path(commit: pygit2.Commit, normalized_path: str) -> bool:
    """Return True when commit modifies normalized_path."""
    if len(commit.parents) == 0:
        try:
            _ = commit.tree[normalized_path]
            return True
        except Exception:
            return False

    for parent in commit.parents:
        try:
            diff = parent.tree.diff_to_tree(commit.tree)
        except Exception:
            continue
        for patch in diff:
            new_file = str(patch.delta.new_file.path or "").replace("\\", "/")
            old_file = str(patch.delta.old_file.path or "").replace("\\", "/")
            if normalized_path in {new_file, old_file}:
                return True
    return False


def recent_commits(repo: pygit2.Repository | None, *, limit: int = 20) -> list[CommitInfo]:
    """Return recent commit metadata for current branch."""
    if repo is None or repo.head_is_unborn:
        return []
    commit_info = _commit_info_type()
    commits: list[CommitInfo] = []
    for commit in repo.walk(repo.head.target, pygit2.GIT_SORT_TIME):
        commits.append(
            commit_info(
                sha=str(commit.id),
                message=commit.message.strip(),
                author_name=commit.author.name,
                author_email=commit.author.email,
                commit_time=int(commit.commit_time),
            )
        )
        if len(commits) >= limit:
            break
    return commits


def last_commit_for_path(
    repo: pygit2.Repository | None,
    rel_path: str,
    *,
    limit: int = 400,
) -> CommitInfo | None:
    """Return newest commit that touched rel_path, or None."""
    if repo is None or repo.head_is_unborn:
        return None
    commit_info = _commit_info_type()
    normalized = rel_path.replace("\\", "/")
    scanned = 0
    for commit in repo.walk(repo.head.target, pygit2.GIT_SORT_TIME):
        if commit_touches_path(commit, normalized):
            return commit_info(
                sha=str(commit.id),
                message=commit.message.strip(),
                author_name=commit.author.name,
                author_email=commit.author.email,
                commit_time=int(commit.commit_time),
            )
        scanned += 1
        if scanned >= limit:
            break
    return None


def auto_message(status: GitStatus) -> str:
    """Generate commit message heuristic from status groups."""
    all_paths = status.all_modified_paths
    if not all_paths:
        raise ValueError("auto_message requires at least one changed path")

    only_deletes = bool(
        status.deleted_paths) and all_paths == status.deleted_paths
    action = "Delete" if only_deletes else "Edit"

    category_counts: dict[str, int] = {}
    for path in sorted(all_paths):
        if path.startswith("nodes/"):
            key = "node"
        elif path.startswith("link_types/"):
            key = "link type"
        elif path.startswith("links/"):
            key = "link"
        elif path.startswith("views/"):
            key = "view"
        else:
            continue
        category_counts[key] = category_counts.get(key, 0) + 1

    if not category_counts:
        return f"{action} knowledge repository"

    parts: list[str] = []
    for key in ("node", "link type", "link", "view"):
        count = category_counts.get(key)
        if count is None:
            continue
        suffix = "" if count == 1 else "s"
        parts.append(f"{count} {key}{suffix}")
    return f"{action} " + ", ".join(parts)

"""Autosave helpers for KnowledgeGitService.

Uses lightweight commits on ``refs/lks-autosave/*`` custom refs instead of
``git stash`` so that the working tree and index are never modified by the
autosave cycle.  Each autosave is a single-parent commit whose tree captures
the full working-directory state at that moment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import pygit2

from lks_utils.git._git_service.stage import default_signature

_AUTOSAVE_REF_PREFIX: str = "refs/lks-autosave/"
_AUTOSAVE_REF_RE: re.Pattern[str] = re.compile(
    r"^refs/lks-autosave/(\d+)$"
)

# The ref name for the next autosave index counter.
_COUNTER_REF: str = f"{_AUTOSAVE_REF_PREFIX}counter"


@dataclass(frozen=True)
class StashInfo:
    """Lightweight metadata for one autosave entry."""

    index: int
    """Zero-based index (0 = newest)."""

    commit_id: str
    """Hex SHA of the autosave commit."""

    message: str
    """Autosave message (e.g. 'Autosave 2026-06-01 14:30:00 UTC')."""

    commit_time: int
    """Unix epoch seconds of the autosave commit."""

    @property
    def formatted_time(self) -> str:
        """Return ISO-formatted UTC timestamp string for display."""
        dt = datetime.fromtimestamp(self.commit_time, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ------------------------------------------------------------------
# Core autosave operations
# ------------------------------------------------------------------


def autosave_create(
    repo: pygit2.Repository | None,
    message: str,
    *,
    last_tree_oid: str | None = None,
) -> tuple[str, str] | None:
    """Create one autosave commit on ``refs/lks-autosave/<N>``.

    Stages all working-tree changes into the index, writes a tree, creates
    a commit, then **restores the original index** so the user's staged state
    is preserved.  The working tree is never touched.

    Args:
        repo: The git repository.
        message: Commit message.
        last_tree_oid: Hex tree OID of the most recent autosave.  When
            provided and the new tree is identical, the call is a no-op.

    Returns:
        ``(ref_name, commit_oid_hex)`` on success, or ``None`` if there are
        no changes or the tree matches *last_tree_oid*.
    """
    if repo is None:
        return None

    try:
        # -- 1. Snapshot the original index tree so we can restore it ----
        original_index = repo.index
        original_tree = original_index.write_tree()

        # -- 2. Stage everything and write the autosave tree ------------
        original_index.add_all()
        original_index.write()
        autosave_tree = original_index.write_tree()
        autosave_tree_hex = str(autosave_tree)

        # -- 3. Dedup against last known tree ---------------------------
        if last_tree_oid is not None and last_tree_oid == autosave_tree_hex:
            # Restore original index and bail.
            _restore_index(repo, original_tree)
            return None

        # -- 4. Check there are actual changes vs HEAD ------------------
        if repo.head_is_unborn:
            _restore_index(repo, original_tree)
            return None
        head_tree = repo[repo.head.target].tree.id
        if autosave_tree == head_tree:
            _restore_index(repo, original_tree)
            return None

        # -- 5. Allocate next ref name and create commit ----------------
        sig = default_signature(repo)
        ref_name = _next_ref_name(repo)
        commit_oid = repo.create_commit(
            ref_name,
            sig,
            sig,
            message,
            autosave_tree,
            [repo.head.target],
        )

        # -- 6. Restore original index ----------------------------------
        _restore_index(repo, original_tree)

        return (ref_name, str(commit_oid))

    except (OSError, ValueError, KeyError, pygit2.GitError):
        return None


def autosave_list(
    repo: pygit2.Repository | None,
) -> list[StashInfo]:
    """Return all autosave entries, newest first."""
    if repo is None:
        return []
    result: list[StashInfo] = []
    try:
        for ref_name in sorted(repo.listall_references()):
            m = _AUTOSAVE_REF_RE.match(ref_name)
            if not m:
                continue
            index = int(m.group(1))
            ref = repo.lookup_reference(ref_name)
            commit_oid = str(ref.target)
            try:
                commit = repo[ref.target]
                commit_time = commit.commit_time
                message = commit.message or ""
            except (KeyError, ValueError, OSError, pygit2.GitError):
                commit_time = 0
                message = ""
            # Strip trailing newline from commit message.
            message = message.rstrip("\n")
            result.append(
                StashInfo(
                    index=index,
                    commit_id=commit_oid,
                    message=message,
                    commit_time=commit_time,
                )
            )
    except (OSError, ValueError, KeyError, pygit2.GitError):
        return []
    # Sort newest-first by index descending.
    result.sort(key=lambda s: s.index, reverse=True)
    return result


def autosave_apply(
    repo: pygit2.Repository | None,
    index: int,
) -> bool:
    """Checkout the tree from autosave *index* into the working tree.

    This overwrites tracked files with the autosave snapshot.  Untracked
    files are left alone.
    """
    if repo is None:
        return False
    ref_name = f"{_AUTOSAVE_REF_PREFIX}{index}"
    try:
        ref = repo.lookup_reference(ref_name)
        commit = repo[ref.target]
        repo.checkout_tree(
            commit.tree,
            strategy=pygit2.GIT_CHECKOUT_SAFE,
        )
    except (OSError, ValueError, KeyError, pygit2.GitError):
        return False
    return True


def autosave_drop(
    repo: pygit2.Repository | None,
    index: int,
) -> bool:
    """Delete the autosave ref for *index*."""
    if repo is None:
        return False
    ref_name = f"{_AUTOSAVE_REF_PREFIX}{index}"
    try:
        ref = repo.lookup_reference(ref_name)
        ref.delete()
    except (OSError, ValueError, KeyError, pygit2.GitError):
        return False
    return True


def autosave_prune(
    repo: pygit2.Repository | None,
    max_keep: int,
) -> None:
    """Drop the oldest autosave refs so at most *max_keep* remain."""
    entries = autosave_list(repo)
    if len(entries) <= max_keep:
        return
    # entries are newest-first; drop from the end (oldest, highest index).
    for entry in reversed(entries):
        if len(autosave_list(repo)) <= max_keep:
            break
        autosave_drop(repo, entry.index)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _restore_index(
    repo: pygit2.Repository,
    original_tree: pygit2.Oid,
) -> None:
    """Restore the index to *original_tree* without touching the working tree."""
    try:
        repo.index.read_tree(original_tree)
        repo.index.write()
    except (OSError, ValueError, KeyError, pygit2.GitError):
        pass


def _next_ref_name(repo: pygit2.Repository) -> str:
    """Return the next available ``refs/lks-autosave/<N>`` ref name.

    Reads the counter ref for an atomic increment; falls back to scanning
    existing autosave refs.
    """
    # Try to read and bump the counter ref first (atomic-ish).
    try:
        counter_ref = repo.lookup_reference(_COUNTER_REF)
        current = int(str(counter_ref.target))
    except (KeyError, ValueError):
        # Counter ref doesn't exist — compute from existing autosave refs.
        existing = autosave_list(repo)
        current = max((s.index for s in existing), default=-1)

    next_val = current + 1
    ref_name = f"{_AUTOSAVE_REF_PREFIX}{next_val}"

    # Write the counter ref forward so concurrent calls don't collide.
    try:
        counter_oid = repo.create_blob(str(next_val).encode("utf-8"))
        try:
            counter_ref = repo.lookup_reference(_COUNTER_REF)
            counter_ref.set_target(counter_oid)
        except KeyError:
            repo.create_reference(_COUNTER_REF, counter_oid)
    except (OSError, pygit2.GitError):
        pass

    return ref_name


# ------------------------------------------------------------------
# Public API — kept backward-compatible for existing callers
# ------------------------------------------------------------------


def stash_save(
    repo: pygit2.Repository | None,
    message: str,
    *,
    include_untracked: bool = True,
    last_tree_oid: str | None = None,
) -> str | None:
    """Create one autosave commit (backward-compat wrapper).

    Use ``autosave_create()`` for new code.
    """
    result = autosave_create(repo, message, last_tree_oid=last_tree_oid)
    if result is None:
        return None
    return result[1]


def stash_apply(repo: pygit2.Repository | None, index: int) -> bool:
    """Apply autosave by index (backward-compat wrapper)."""
    return autosave_apply(repo, index)


def stash_pop(repo: pygit2.Repository | None, index: int) -> bool:
    """Apply then drop autosave by index."""
    if not autosave_apply(repo, index):
        return False
    autosave_drop(repo, index)
    return True


def stash_drop(repo: pygit2.Repository | None, index: int) -> bool:
    """Drop autosave by index (backward-compat wrapper)."""
    return autosave_drop(repo, index)


def list_stashes(repo: pygit2.Repository | None) -> list[StashInfo]:
    """Return all autosave entries, newest first (backward-compat wrapper)."""
    return autosave_list(repo)


def autosave_tree_oid_for_index(
    repo: pygit2.Repository | None,
    index: int,
) -> str | None:
    """Return the tree OID hex for autosave *index*, or ``None``."""
    if repo is None:
        return None
    ref_name = f"{_AUTOSAVE_REF_PREFIX}{index}"
    try:
        ref = repo.lookup_reference(ref_name)
        commit = repo[ref.target]
        return str(commit.tree.id)
    except (OSError, ValueError, KeyError, pygit2.GitError):
        return None


__all__ = [
    "StashInfo",
    "autosave_create",
    "autosave_list",
    "autosave_apply",
    "autosave_drop",
    "autosave_prune",
    "stash_save",
    "stash_apply",
    "stash_pop",
    "stash_drop",
    "list_stashes",
]

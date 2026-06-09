"""Git status service for knowledge repositories."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal, Slot

import pygit2

from lks_utils.git._git_service.conflict_detect import (
    auto_message as _auto_message,
    last_commit_for_path as _last_commit_for_path,
    recent_commits as _recent_commits,
)
from lks_utils.git._git_service.diff import (
    change_code as _change_code,
    diff_file as _diff_file,
    read_head_text as _read_head_text,
)
from lks_utils.git._git_service.stage import (
    commit as _commit,
    default_signature as _default_signature,
    ensure_bootstrap_commit as _ensure_bootstrap_commit,
    revert_file as _revert_file,
    stage_all as _stage_all,
    stage_paths as _stage_paths,
    unstage_all as _unstage_all,
    unstage_paths as _unstage_paths,
)
from lks_utils.git._git_service.stash import (
    StashInfo,
    autosave_prune as _autosave_prune,
    autosave_tree_oid_for_index as _autosave_tree_oid_for_index,
    list_stashes as _list_stashes,
    stash_apply as _stash_apply,
    stash_drop as _stash_drop,
    stash_pop as _stash_pop,
    stash_save as _stash_save,
)
from lks_utils.git._git_service.status import (
    empty_git_status,
    open_repository,
    read_repo_status,
)
if TYPE_CHECKING:
    from lks_utils.knowledge.commit_info import CommitInfo
    from lks_utils.knowledge.git_status import GitStatus


class KnowledgeGitService(QObject):
    """Tracks modified paths for one git-backed repository root."""

    git_status_changed = Signal(object)
    commit_completed = Signal()

    # Internal signal used to ferry background-thread git results back to the
    # main thread via a guaranteed QueuedConnection. Never connect to this externally.
    _background_refresh_result: Signal = Signal(object)

    def __init__(self, *, repository_root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._repository_root = Path(repository_root)
        self._repo: pygit2.Repository | None = self._open_repository(
            self._repository_root)
        self._cached_status: GitStatus = empty_git_status()
        self._modified_paths_cache: set[str] = set()

        # Async refresh state (main-thread only except where noted).
        self._refresh_in_progress: bool = False
        self._refresh_pending: bool = False
        # Monotonically-increasing serial used to discard stale async status results.
        self._status_serial: int = 0
        self._background_refresh_result.connect(
            self._apply_background_status,
            Qt.ConnectionType.QueuedConnection,
        )
        # Kick off first status scan in the background — non-blocking.
        self.refresh_status_async()

    @property
    def repository_root(self) -> Path:
        """Return the git repository root path."""
        return self._repository_root

    @property
    def is_repo(self) -> bool:
        """Return whether repository root is a valid git repository."""
        return self._repo is not None

    @property
    def has_head_commit(self) -> bool:
        """Return whether repository has at least one commit on HEAD."""
        return self._repo is not None and not self._repo.head_is_unborn

    def init_repo(self) -> bool:
        """Initialize git repository when missing and refresh cached status."""
        if self._repo is None:
            pygit2.init_repository(str(self._repository_root), False)
            self._repo = self._open_repository(self._repository_root)
        if self._repo is not None:
            self._ensure_bootstrap_commit()
        self.refresh_status_async()
        return self._repo is not None

    def status(self) -> GitStatus:
        """Return normalized status buckets for the current repository."""
        if self._repo is None:
            return empty_git_status()
        return read_repo_status(self._repo)

    def refresh_status(self) -> set[str]:
        """Refresh status cache and emit when modified-path set changes."""
        new_status = self.status()
        current = new_status.all_modified_paths
        self._cached_status = new_status
        if current != self._modified_paths_cache:
            self._modified_paths_cache = set(current)
            self.git_status_changed.emit(set(current))
        self._status_serial += 1
        return current

    def refresh_status_async(self) -> None:
        """Schedule a background git status refresh — returns immediately."""
        if self._refresh_in_progress:
            self._refresh_pending = True
            return
        self._refresh_in_progress = True
        repo_path = str(self._repository_root)
        serial = self._status_serial
        threading.Thread(
            target=self._run_status_in_background,
            args=(repo_path, serial),
            daemon=True,
            name="lks-git-status-refresh",
        ).start()

    @property
    def cached_status(self) -> GitStatus:
        """Return the most recently computed git status (may be slightly stale)."""
        return self._cached_status

    def _run_status_in_background(self, repo_path: str, serial: int) -> None:
        """Open a fresh Repository and compute status in background thread."""
        try:
            repo = self._open_repository(Path(repo_path))
            full_status = empty_git_status() if repo is None else read_repo_status(repo)
        except Exception:
            full_status = empty_git_status()
        self._background_refresh_result.emit((full_status, serial))

    @Slot(object)
    def _apply_background_status(self, result: object) -> None:
        """Receive background result on main thread and update the cache."""
        full_status, serial = result  # type: ignore[misc]
        self._refresh_in_progress = False
        if serial != self._status_serial:
            if self._refresh_pending:
                self._refresh_pending = False
                self.refresh_status_async()
            return
        current = full_status.all_modified_paths
        self._cached_status = full_status
        if current != self._modified_paths_cache:
            self._modified_paths_cache = current
            self.git_status_changed.emit(set(current))
        if self._refresh_pending:
            self._refresh_pending = False
            self.refresh_status_async()

    def is_modified(self, rel_path: str) -> bool:
        """Return whether one repository-relative path is currently modified."""
        normalized = rel_path.replace("\\", "/")
        return normalized in self._modified_paths_cache

    def diff_file(self, rel_path: str, *, staged: bool = False) -> str:
        """Return unified diff patch text for one path."""
        return _diff_file(self._repo, rel_path, staged=staged)

    def change_code(self, rel_path: str) -> str:
        """Return one-letter change code for rel_path using git status flags."""
        return _change_code(self._repo, self._cached_status, rel_path)

    def read_head_text(self, rel_path: str) -> str | None:
        """Return UTF-8 text for one HEAD-relative path, or None if absent."""
        return _read_head_text(self._repo, rel_path)

    def stage(self, rel_paths: list[str]) -> None:
        """Stage selected repository-relative paths."""
        _stage_paths(self._repo, rel_paths)
        self.refresh_status()

    def stage_all(self) -> None:
        """Stage all current repository changes."""
        _stage_all(self._repo)
        self.refresh_status()

    def unstage(self, rel_paths: list[str]) -> None:
        """Unstage selected repository-relative paths."""
        _unstage_paths(self._repo, rel_paths)
        self.refresh_status()

    def unstage_all(self) -> None:
        """Unstage all currently staged paths."""
        staged_paths = self.status().staged_paths
        _unstage_all(self._repo, staged_paths)
        self.refresh_status()

    def commit(self, message: str) -> str | None:
        """Commit currently staged changes and return commit SHA."""
        oid = _commit(self._repo, message)
        if oid is None:
            return None
        self.refresh_status()
        self.commit_completed.emit()
        return oid

    def commit_all(self, message: str) -> str | None:
        """Stage all changes then commit."""
        if self._repo is None:
            return None
        _stage_all(self._repo)
        return self.commit(message)

    def revert_file(self, rel_path: str) -> None:
        """Revert one file to HEAD state in working tree and index."""
        _revert_file(self._repo, self._repository_root, rel_path)
        self.refresh_status()

    def recent_commits(self, *, limit: int = 20) -> list[CommitInfo]:
        """Return recent commit metadata for current branch."""
        return _recent_commits(self._repo, limit=limit)

    def last_commit_for_path(self, rel_path: str, *, limit: int = 400) -> CommitInfo | None:
        """Return newest commit that touched rel_path, or None."""
        return _last_commit_for_path(self._repo, rel_path, limit=limit)

    def auto_message(self, status: GitStatus | None = None) -> str:
        """Generate commit message heuristic from current status groups."""
        current = status if status is not None else self.status()
        return _auto_message(current)

    # ------------------------------------------------------------------
    # Stash (autosave)
    # ------------------------------------------------------------------

    def stash_save(
        self,
        message: str,
        *,
        include_untracked: bool = True,
        last_tree_oid: str | None = None,
    ) -> str | None:
        """Create an autosave commit without touching the working tree.

        Stages all changes, writes a tree, creates a commit on
        ``refs/lks-autosave/<N>``, then restores the original index.
        When *last_tree_oid* is provided and the new tree is identical,
        the call is a no-op.

        Returns:
            Commit OID hex string, or ``None`` if there are no changes.
        """
        return _stash_save(
            self._repo,
            message,
            include_untracked=include_untracked,
            last_tree_oid=last_tree_oid,
        )

    def stash_apply(self, index: int) -> bool:
        """Apply one stash by zero-based index (0 = newest)."""
        return _stash_apply(self._repo, index)

    def stash_pop(self, index: int) -> bool:
        """Apply a stash, then drop it from the reflog."""
        return _stash_pop(self._repo, index)

    def stash_drop(self, index: int) -> bool:
        """Drop one stash by index from the reflog."""
        return _stash_drop(self._repo, index)

    def list_stashes(self) -> list[StashInfo]:
        """Return all autosave entries, newest first."""
        return _list_stashes(self._repo)

    def autosave_prune(self, max_keep: int) -> None:
        """Drop the oldest autosave refs so at most *max_keep* remain."""
        _autosave_prune(self._repo, max_keep)

    def autosave_tree_oid_for_index(self, index: int) -> str | None:
        """Return the tree OID hex for autosave *index*, or ``None``."""
        return _autosave_tree_oid_for_index(self._repo, index)

    def revert_to_commit(self, sha: str) -> None:
        """Revert repository to a previous commit hash."""
        _ = sha
        raise NotImplementedError(
            "TODO: implement safe revert-to-commit workflow")

    def _default_signature(self) -> pygit2.Signature:
        return _default_signature(self._repo)

    def _ensure_bootstrap_commit(self) -> None:
        _ensure_bootstrap_commit(self._repo, self._repository_root)

    @staticmethod
    def _open_repository(path: Path) -> pygit2.Repository | None:
        return open_repository(path)


__all__ = ["KnowledgeGitService"]

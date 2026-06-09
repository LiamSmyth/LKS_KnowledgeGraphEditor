"""Git-backed autosave for knowledge working-tree changes.

Uses lightweight commits on ``refs/lks-autosave/*`` custom refs so that the
working tree is **never** modified by the autosave cycle.  Only the git index
is briefly staged, committed, and immediately restored.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from lks_utils.git._git_service.stash import StashInfo
from lks_utils.knowledge.git_service import KnowledgeGitService


class ShelfService(QObject):
    """Periodically save working-tree changes as autosave commits on a timer.

    Each autosave is a single-parent commit whose tree captures the full
    working-directory state at that moment.  The working tree is never
    touched — the index is staged, committed, and restored in one fast
    pass.  Redundant saves (same tree as the last autosave) are skipped.

    Old autosave refs are pruned to keep at most *max_stashes* entries.
    Autosaves are NOT cleared on commit — they serve as a rolling history
    that the user can recover from at any time via the revert dialog.
    """

    shelves_changed = Signal()
    """Emitted when the autosave list changes (new entry or pruned)."""

    snapshot_created = Signal(object)
    """Emitted with the set of changed paths when a new autosave is saved."""

    def __init__(
        self,
        *,
        repository_root: Path,
        git_service: KnowledgeGitService,
        interval_minutes: float = 5.0,
        max_stashes: int = 10,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository_root = Path(repository_root)
        self._git_service = git_service
        self._interval_minutes = interval_minutes
        self._max_stashes = max(1, max_stashes)
        self._last_autosave_tree_oid: str | None = None
        self._snapshot_in_progress: bool = False
        self._timer = QTimer(self)
        self._timer.setInterval(max(1, int(interval_minutes * 60_000)))
        self._timer.timeout.connect(self.snapshot_now)
        self._timer.start()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def interval_minutes(self) -> float:
        """Return the current autosave interval in minutes."""
        return self._interval_minutes

    @property
    def max_stashes(self) -> int:
        """Return the maximum number of autosave stashes to keep."""
        return self._max_stashes

    def set_interval(self, minutes: float) -> None:
        """Change the autosave interval and restart the timer."""
        self._interval_minutes = max(0.1, minutes)
        self._timer.setInterval(max(1, int(self._interval_minutes * 60_000)))
        self._timer.start()

    def set_max_stashes(self, max_stashes: int) -> None:
        """Change the max stash count and prune immediately."""
        self._max_stashes = max(1, max_stashes)
        self._git_service.autosave_prune(self._max_stashes)
        self.shelves_changed.emit()

    def snapshot_now(self) -> str | None:
        """Create one autosave commit if the working tree differs from the last.

        Skips when no changes exist or the tree is identical to the most
        recent autosave (deduplication).

        Returns the commit OID hex string, or ``None`` when skipped.
        """
        if self._snapshot_in_progress:
            return None
        if not self._git_service.is_repo:
            return None

        changed_paths = sorted(self._git_service.status().all_modified_paths)
        if not changed_paths:
            return None

        message = "Autosave " + datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

        self._snapshot_in_progress = True
        try:
            oid = self._git_service.stash_save(
                message,
                last_tree_oid=self._last_autosave_tree_oid,
            )
        finally:
            self._snapshot_in_progress = False

        if oid is None:
            return None

        # Update dedup state — we need the tree OID from the commit.
        # Read it back from the most recent autosave list entry.
        stashes = self._git_service.list_stashes()
        if stashes:
            self._last_autosave_tree_oid = self._read_tree_oid(stashes[0].commit_id)

        self._git_service.autosave_prune(self._max_stashes)
        self.shelves_changed.emit()
        self.snapshot_created.emit(set(changed_paths))
        return oid

    def list_stashes(self) -> list[StashInfo]:
        """Return all autosave entries, newest first."""
        return self._git_service.list_stashes()

    def stash_count(self) -> int:
        """Return the number of autosave entries currently stored."""
        return len(self._git_service.list_stashes())

    def drop_stash(self, index: int) -> bool:
        """Drop one autosave by index."""
        return self._git_service.stash_drop(index)

    def apply_stash(self, index: int) -> bool:
        """Checkout the tree from one autosave by index."""
        return self._git_service.stash_apply(index)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_tree_oid(self, commit_id: str) -> str | None:
        """Return the tree OID hex for a commit, or None on failure."""
        stashes = self._git_service.list_stashes()
        for s in stashes:
            if s.commit_id == commit_id:
                return self._git_service.autosave_tree_oid_for_index(s.index)
        return None


__all__ = ["ShelfService"]

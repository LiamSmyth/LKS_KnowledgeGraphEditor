"""Periodic file-copy shelves for knowledge git changes."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from shutil import copy2, rmtree

from PySide6.QtCore import QObject, QTimer, Signal

from lks_utils.knowledge.git_service import KnowledgeGitService


class ShelfService(QObject):
    """Copy changed files into timestamped shelf folders and clear on commit."""

    shelves_changed = Signal()
    snapshot_created = Signal(object)

    def __init__(
        self,
        *,
        repository_root: Path,
        git_service: KnowledgeGitService,
        interval_minutes: float = 5.0,
        max_shelves: int = 10,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository_root = Path(repository_root)
        self._git_service = git_service
        self._interval_minutes = interval_minutes
        self._max_shelves = max(1, max_shelves)
        self._timer = QTimer(self)
        self._timer.setInterval(max(1, int(interval_minutes * 60_000)))
        self._timer.timeout.connect(self.snapshot_now)
        self._git_service.commit_completed.connect(self.clear_shelves)
        self._timer.start()

    @property
    def shelves_root(self) -> Path:
        """Return the root directory that stores shelf snapshots."""
        return self._repository_root / ".lks" / "shelves"

    def snapshot_now(self) -> Path | None:
        """Copy currently changed files into a new shelf directory."""
        if not self._git_service.is_repo:
            return None
        changed_paths = sorted(self._git_service.status().all_modified_paths)
        if not changed_paths:
            return None

        shelf_dir = self.shelves_root / datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S_%f"
        )
        shelf_dir.mkdir(parents=True, exist_ok=True)
        for rel_path in changed_paths:
            source_path = self._repository_root / rel_path
            if not source_path.exists():
                continue
            target_path = shelf_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            copy2(source_path, target_path)

        self._prune_old_shelves()
        self.shelves_changed.emit()
        self.snapshot_created.emit(set(changed_paths))
        return shelf_dir

    def clear_shelves(self) -> None:
        """Remove all stored shelf snapshots after a real commit."""
        if self.shelves_root.exists():
            rmtree(self.shelves_root)
        self.shelves_changed.emit()

    def _prune_old_shelves(self) -> None:
        if not self.shelves_root.exists():
            return
        shelves = sorted(
            [path for path in self.shelves_root.iterdir() if path.is_dir()]
        )
        excess = len(shelves) - self._max_shelves
        if excess <= 0:
            return
        for shelf_dir in shelves[:excess]:
            rmtree(shelf_dir, ignore_errors=True)


__all__ = ["ShelfService"]

"""Shared base for knowledge editor tabs with a title + action ribbon.

Provides the canvas-title label and revert button so that editor tabs share
one implementation of that chrome.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from lks_utils.git._git_service.stash import StashInfo
from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.ui.widgets.field_widgets import make_square_svg_button


class QKnowledgeEditorTabBase(QWidget):
    """Base class for knowledge editor tabs with a canvas-title + revert ribbon.

    Attributes provided for subclasses:
        _session: The active editor session.
        _canvas_title: QLabel showing the currently open item name.
        _revert_btn: Revert action button wired to ``_on_revert``.
    """

    # Optional: subclasses may emit this to signal an open event.
    node_opened = Signal(str)

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session

        self._canvas_title = QLabel("No item loaded", self)
        self._canvas_title.setObjectName("canvas_title")

        self._revert_btn = make_square_svg_button(
            "kwb_btn_revert.svg",
            tooltip="Reload the current item and discard unsaved edits",
            parent=self,
        )
        self._revert_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # type: ignore[override]
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Ribbon construction
    # ------------------------------------------------------------------

    def _build_ribbon(self) -> QWidget:
        """Return a horizontal ribbon widget containing title + revert."""
        ribbon = QWidget(self)
        ribbon.setObjectName("canvas_ribbon")
        row = QHBoxLayout(ribbon)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(6)
        row.addWidget(self._canvas_title, stretch=1)
        row.addWidget(self._revert_btn)
        row.setAlignment(self._revert_btn, Qt.AlignmentFlag.AlignRight)
        return ribbon

    def _confirm_and_revert_file_to_last_commit(
        self,
        *,
        core_label: str,
        rel_path: str,
    ) -> bool | None:
        """Revert one repository-relative file to HEAD after user confirmation.

        Returns:
            ``True`` when a git revert was applied.
            ``False`` when user canceled or revert failed.
            ``None`` when git context is unavailable; callers may use fallback.
        """
        git = self._session.git_service
        if git is None or not git.is_repo:
            return None
        if not git.has_head_commit:
            QMessageBox.warning(
                self,
                "Revert Unavailable",
                "No commits exist yet, so this item cannot be reverted to last commit.",
            )
            return False

        commit = git.last_commit_for_path(rel_path)
        if commit is None:
            QMessageBox.warning(
                self,
                "Revert Unavailable",
                f"No commit history was found for {rel_path}.",
            )
            return False

        # If autosave stashes exist, show the full selection dialog.
        stashes = git.list_stashes()
        if stashes:
            return self._show_revert_selection_dialog(
                core_label=core_label,
                rel_path=rel_path,
                last_commit=commit,
                stashes=stashes,
                git=git,
            )

        age_text = self._format_commit_age_text(commit.commit_time)
        answer = QMessageBox.question(
            self,
            "Confirm Revert",
            (
                f"This will revert this {core_label} to last commit, {age_text} ago.\n\n"
                "Are you sure?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False

        try:
            git.revert_file(rel_path)
            return True
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Revert Failed", str(exc))
            return False

    def _show_revert_selection_dialog(
        self,
        *,
        core_label: str,
        rel_path: str,
        last_commit: object,
        stashes: list[StashInfo],
        git: object,
    ) -> bool | None:
        """Show a dialog letting the user pick from last-commit or autosave stashes.

        Returns:
            ``True`` when a revert or stash-apply was applied.
            ``False`` when the user canceled.
        """
        from lks_utils.knowledge.commit_info import CommitInfo

        dialog = _QKnowledgeRevertSelectionDialog(
            core_label=core_label,
            last_commit=last_commit if isinstance(
                last_commit, CommitInfo) else None,
            stashes=stashes,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        choice = dialog.selected_choice()
        if choice is None:
            return False

        try:
            if choice == "last_commit":
                git.revert_file(rel_path)
            elif isinstance(choice, StashInfo):
                git.stash_apply(choice.index)
            else:
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Revert Failed", str(exc))
            return False

    def _format_commit_age_text(self, commit_epoch_seconds: int) -> str:
        """Return compact human-readable age string for a commit timestamp."""
        now = datetime.now(timezone.utc)
        then = datetime.fromtimestamp(commit_epoch_seconds, tz=timezone.utc)
        seconds = max(0, int((now - then).total_seconds()))
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h"
        days = hours // 24
        if days < 30:
            return f"{days}d"
        months = days // 30
        if months < 12:
            return f"{months}mo"
        years = months // 12
        return f"{years}y"

    # ------------------------------------------------------------------
    # Shared stylesheet fragments
    # ------------------------------------------------------------------

    def _base_ribbon_stylesheet(self) -> str:
        """Return the shared stylesheet fragment for ribbon + canvas title."""
        return (
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QWidget#canvas_ribbon {{ background: #1e1e1e; border-bottom: 1px solid {EDGE_COLOR}; }}"
            f"QLabel#canvas_title {{ color: {NODE_TEXT_COLOR}; font-weight: 600; }}"
        )


# ------------------------------------------------------------------
# Revert Selection Dialog
# ------------------------------------------------------------------


class _QKnowledgeRevertSelectionDialog(QDialog):
    """Modal dialog listing last-commit and autosave stashes for revert."""

    _CHOICE_LAST_COMMIT = "last_commit"

    def __init__(
        self,
        *,
        core_label: str,
        last_commit: object | None,
        stashes: list[StashInfo],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Revert — Select Source")
        self.setMinimumSize(500, 320)
        self._core_label = core_label
        self._last_commit = last_commit
        self._stashes = stashes
        self._selected_choice: str | StashInfo | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        label = QLabel(
            f"Choose a restore point for this {core_label}:", self
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        self._list = QListWidget(self)
        self._list.setAlternatingRowColors(True)
        layout.addWidget(self._list, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate_list()

    def _populate_list(self) -> None:
        """Fill list with last-commit entry (first) then stashes (newest first)."""
        # Last commit entry
        if self._last_commit is not None:
            from lks_utils.knowledge.commit_info import CommitInfo

            lc: CommitInfo = self._last_commit  # type: ignore[assignment]
            now = datetime.now(timezone.utc)
            then = datetime.fromtimestamp(lc.commit_time, tz=timezone.utc)
            seconds = max(0, int((now - then).total_seconds()))
            if seconds < 60:
                age = "just now"
            else:
                minutes = seconds // 60
                if minutes < 60:
                    age = f"{minutes}m"
                else:
                    hours = minutes // 60
                    if hours < 24:
                        age = f"{hours}h"
                    else:
                        days = hours // 24
                        if days < 30:
                            age = f"{days}d"
                        else:
                            months = days // 30
                            if months < 12:
                                age = f"{months}mo"
                            else:
                                years = months // 12
                                age = f"{years}y"
            item = QListWidgetItem(
                f"Last commit ({age}) — {lc.message}", self._list
            )
            item.setData(Qt.ItemDataRole.UserRole, self._CHOICE_LAST_COMMIT)
            item.setToolTip(f"SHA: {lc.sha}\n{lc.message}")

        # Stash entries (already newest-first from list_stashes)
        for stash in self._stashes:
            item = QListWidgetItem(
                f"Autosave: {stash.formatted_time} — {stash.message}",
                self._list,
            )
            item.setData(Qt.ItemDataRole.UserRole, stash)
            item.setToolTip(f"SHA: {stash.commit_id}")

        # Select first item by default
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def selected_choice(self) -> str | StashInfo | None:
        """Return the user's selection, or None."""
        return self._selected_choice

    def accept(self) -> None:
        current = self._list.currentItem()
        if current is not None:
            data = current.data(Qt.ItemDataRole.UserRole)
            self._selected_choice = data
        super().accept()


__all__ = ["QKnowledgeEditorTabBase"]

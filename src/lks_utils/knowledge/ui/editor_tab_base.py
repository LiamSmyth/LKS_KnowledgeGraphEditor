"""Shared base for knowledge editor tabs with a title + action ribbon.

Provides the canvas-title label and revert button so that editor tabs share
one implementation of that chrome.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

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


__all__ = ["QKnowledgeEditorTabBase"]

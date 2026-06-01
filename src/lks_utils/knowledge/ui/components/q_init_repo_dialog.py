"""Prompt to initialize git tracking for a knowledge repository."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.q_dialog_scaffold_base import QDialogScaffoldBase

from lks_utils.knowledge.default_theme import NODE_TEXT_COLOR, SCENE_BACKGROUND_COLOR


class QInitRepoDialog(QDialogScaffoldBase):
    """Modal confirmation dialog for initializing git in a repo directory."""

    def __init__(self, *, repository_path: Path, parent: QWidget | None = None) -> None:
        super().__init__("Initialize Git Repository", parent=parent)
        self.setModal(True)

        self._repository_path = repository_path

        status_label = QLabel(
            "Git not initialized for this knowledge repo.", self)
        status_label.setObjectName("initRepoStatusLabel")
        status_label.setWordWrap(True)

        detail_label = QLabel(
            "Git is required for rollback and autosave.",
            self,
        )
        detail_label.setObjectName("initRepoDetailLabel")
        detail_label.setWordWrap(True)

        path_label = QLabel(str(repository_path), self)
        path_label.setObjectName("initRepoPathLabel")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setWordWrap(True)

        question_label = QLabel("Create repo now?", self)
        question_label.setObjectName("initRepoQuestionLabel")
        question_label.setWordWrap(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(status_label)
        content_layout.addWidget(detail_label)
        content_layout.addWidget(path_label)
        content_layout.addWidget(question_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes
            | QDialogButtonBox.StandardButton.No,
            Qt.Orientation.Horizontal,
            self,
        )
        yes_button = button_box.button(QDialogButtonBox.StandardButton.Yes)
        if yes_button is not None:
            yes_button.setText("Yes")
            yes_button.setDefault(True)
            yes_button.setAutoDefault(True)
        no_button = button_box.button(QDialogButtonBox.StandardButton.No)
        if no_button is not None:
            no_button.setText("No")
            no_button.setAutoDefault(True)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        content_layout.addWidget(button_box)
        self.set_content(content)

        self.setStyleSheet(
            (
                f"QDialog {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
                f"QLabel {{ color: {NODE_TEXT_COLOR}; }}"
                "QLabel#initRepoStatusLabel { font-size: 16px; font-weight: 600; }"
                "QLabel#initRepoDetailLabel { color: #c7c7c7; }"
                "QLabel#initRepoPathLabel { font-family: Consolas; }"
                "QLabel#initRepoQuestionLabel { padding-top: 4px; }"
            )
        )


__all__ = ["QInitRepoDialog"]

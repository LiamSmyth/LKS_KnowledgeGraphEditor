"""Repository control strip for the knowledge workbench."""
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import QEvent, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget
from lks_utils.gui_qt.widgets.q_validation_badge import QValidationBadge

from lks_utils.knowledge.actions import REPO_NEW, REPO_OPEN, REPO_SAVE_AS
from lks_utils.knowledge.default_theme import EDGE_COLOR, NODE_TEXT_COLOR, SCENE_BACKGROUND_COLOR
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.validation_statuses.invalid_validation_status import InvalidValidationStatus
from lks_utils.knowledge.ui.widgets.field_widgets import make_square_svg_button


class QKnowledgeRepoControlsWidget(QWidget):
    """Top-strip controls for New/Open/Save/Save As repository operations."""

    repo_new_requested = Signal()
    repo_open_requested = Signal()
    repo_save_as_requested = Signal()
    preferences_requested = Signal()

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._invalid_clipboard_payload: str = ""

        self._repo_id_label = QLabel(self)
        self._root_label = QLabel(self)
        self._invalid_badge = QValidationBadge(self)
        self._invalid_count_label = QLabel(self)
        self._last_save_status_label = QLabel(self)

        self._new_button = self._make_button(
            icon_name="kwb_btn_new.svg",
            action_id=REPO_NEW.id,
            tooltip="Create a new repository",
        )
        self._open_button = self._make_button(
            icon_name="kwb_btn_load.svg",
            action_id=REPO_OPEN.id,
            tooltip="Open an existing repository",
        )
        self._save_as_button = self._make_button(
            icon_name="kwb_btn_save_as.svg",
            action_id=REPO_SAVE_AS.id,
            tooltip="Save the current repository to a new location",
        )
        self._preferences_button = QPushButton("Preferences", self)
        self._preferences_button.setToolTip(
            "Open theme, bindings, and graph live reload preferences")

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self._refresh_labels()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.remove_listener(self._on_session_change)
        super().closeEvent(event)

    def _make_button(self, *, icon_name: str, action_id: str, tooltip: str) -> QPushButton:
        button = make_square_svg_button(
            icon_name, tooltip=tooltip, parent=self)
        button.setProperty("action_id", action_id)
        return button

    def _build_layout(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        root.addWidget(self._new_button)
        root.addWidget(self._open_button)
        root.addWidget(self._save_as_button)
        root.addWidget(self._preferences_button)
        root.addSpacing(18)
        root.addWidget(QLabel("Repo ID:", self))
        root.addWidget(self._repo_id_label)
        root.addSpacing(10)
        root.addWidget(QLabel("Root:", self))
        root.addWidget(self._root_label, stretch=1)
        root.addSpacing(10)
        root.addWidget(self._invalid_badge)
        root.addWidget(self._invalid_count_label)
        root.addSpacing(8)
        root.addWidget(self._last_save_status_label)

    def _wire_signals(self) -> None:
        self._new_button.clicked.connect(self.repo_new_requested.emit)
        self._open_button.clicked.connect(self.repo_open_requested.emit)
        self._save_as_button.clicked.connect(self.repo_save_as_requested.emit)
        self._preferences_button.clicked.connect(
            self.preferences_requested.emit)
        self._invalid_badge.installEventFilter(self)
        self._invalid_count_label.installEventFilter(self)

        self._session.add_listener(self._on_session_change)

    # type: ignore[override]
    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched in {self._invalid_badge, self._invalid_count_label}:
            if event.type() == QEvent.Type.MouseButtonRelease and self._invalid_clipboard_payload:
                QApplication.clipboard().setText(self._invalid_clipboard_payload)
                self._last_save_status_label.setToolTip(
                    "Most recent mutation persisted successfully (invalid assets copied to clipboard)"
                )
                return True
        return super().eventFilter(watched, event)

    def _refresh_labels(self) -> None:
        self._repo_id_label.setText(self._session.source_repo_id)
        root = self._session.repository_root
        self._root_label.setText(
            str(root) if isinstance(root, Path) else "(not set)")

        invalid_count, invalid_tooltip = self._invalid_assets_summary()
        has_invalid = invalid_count > 0
        self._invalid_badge.setVisible(has_invalid)
        self._invalid_count_label.setVisible(has_invalid)
        if has_invalid:
            self._invalid_clipboard_payload = invalid_tooltip
            click_help = "\n\nClick warning badge/count to copy this list."
            tooltip_with_copy = invalid_tooltip + click_help
            self._invalid_badge.set_status(
                InvalidValidationStatus([f"{invalid_count} invalid assets"])
            )
            self._invalid_badge.setToolTip(tooltip_with_copy)
            self._invalid_count_label.setText(str(invalid_count))
            self._invalid_count_label.setToolTip(tooltip_with_copy)
        else:
            self._invalid_clipboard_payload = ""
            self._invalid_badge.clear()
            self._invalid_badge.setToolTip("")
            self._invalid_count_label.setText("")
            self._invalid_count_label.setToolTip("")

        status = self._session.last_save_status.value.upper()
        self._last_save_status_label.setText(f"SAVE {status}")
        self._last_save_status_label.setProperty(
            "save_status", self._session.last_save_status.value
        )
        self._last_save_status_label.setProperty(
            "has_invalid_assets", "true" if has_invalid else "false"
        )
        save_error = self._session.last_save_error
        self._last_save_status_label.setToolTip(
            save_error if save_error else "Most recent mutation persisted successfully"
        )
        self.style().unpolish(self._last_save_status_label)
        self.style().polish(self._last_save_status_label)

    def _invalid_assets_summary(self) -> tuple[int, str]:
        entries: list[str] = []
        node_names_by_id = {
            str(node.id): node.name for node in self._session.list_nodes()
        }
        link_type_names_by_id = {
            str(link_type.id): link_type.name
            for link_type in self._session.list_link_types()
        }

        for node in self._session.list_nodes():
            object_id = str(node.id)
            status = self._session.validation_index.status_for(object_id)
            if status.is_valid:
                continue
            reason = status.reasons[0] if status.reasons else "invalid"
            entries.append(f"Node: {node.name} ({reason})")

        for link_type in self._session.list_link_types():
            object_id = str(link_type.id)
            status = self._session.validation_index.status_for(object_id)
            if status.is_valid:
                continue
            reason = status.reasons[0] if status.reasons else "invalid"
            entries.append(f"Link Type: {link_type.name} ({reason})")

        for link in self._session.list_links():
            object_id = str(link.id)
            status = self._session.validation_index.status_for(object_id)
            if status.is_valid:
                continue
            link_type_name = link_type_names_by_id.get(
                str(link.link_type_id), str(link.link_type_id)
            )
            source_name = node_names_by_id.get(
                str(link.source_node_id), str(link.source_node_id)
            )
            target_name = node_names_by_id.get(
                str(link.target_node_id), str(link.target_node_id)
            )
            reason = status.reasons[0] if status.reasons else "invalid"
            entries.append(
                f"Link: {source_name} -> {target_name} [{link_type_name}] ({reason})"
            )

        if not entries:
            return 0, ""
        preview = entries[:12]
        if len(entries) > len(preview):
            preview.append(f"(+{len(entries) - len(preview)} more)")
        tooltip = "Invalid assets:\n" + \
            "\n".join(f"- {line}" for line in preview)
        return len(entries), tooltip

    def _on_session_change(self, change_type: str) -> None:
        if change_type in {"node", "repo_loaded", "repo_saved", "dirty_changed"}:
            self._refresh_labels()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QPushButton {{ border: 1px solid {EDGE_COLOR}; padding: 4px 8px; }}"
            "QLabel[save_status='ok'] { color: #6fbf73; font-weight: 700; }"
            "QLabel[save_status='ok'][has_invalid_assets='true'] { color: #d4a24a; font-weight: 700; }"
            "QLabel[save_status='failed'] { color: #d96a6a; font-weight: 700; }"
        )


__all__ = ["QKnowledgeRepoControlsWidget"]

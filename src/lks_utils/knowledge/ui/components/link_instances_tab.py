"""Tab for browsing and deleting semantic link instances.

Layout: Library + Validation (left) | Details canvas (center) | Inspector (right)
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    FIELD_MONO_FONT_FAMILY,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.editor_session_types import SessionChangeEvent
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.ui.components.link_instances_library_panel import (
    QKnowledgeLinkInstancesLibraryPanel,
)
from lks_utils.knowledge.ui.components.properties_panel import QKnowledgeInspectorPanel
from lks_utils.knowledge.ui.editor_tab_base import QKnowledgeEditorTabBase
from lks_utils.knowledge.ui.widgets.validation_log import (
    QKnowledgeValidationLogWidget,
    ValidationErrorEntry,
)


class QKnowledgeLinkInstancesTabWidget(QKnowledgeEditorTabBase):
    """Three-panel link instances browser with multi-select delete in library."""

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(session, parent)
        self._current_link_instance_id: str | None = None
        self._refresh_pending: bool = False

        self._library = QKnowledgeLinkInstancesLibraryPanel(session, self)
        self._validation_log = QKnowledgeValidationLogWidget(self)
        self._validation_log.setObjectName("kb_link_instances_validation_log")
        self._details = QPlainTextEdit(self)
        self._details.setObjectName("kb_link_instance_details")
        self._details.setReadOnly(True)
        self._details.setPlaceholderText(
            "Select a link instance to inspect details")
        self._inspector = QKnowledgeInspectorPanel(session, parent=self)
        self._inspector.setObjectName("kb_link_instance_inspector")
        self._inspector.setMinimumWidth(340)

        # Reverting link files is not exposed in this first pass.
        self._revert_btn.setEnabled(False)
        self._revert_btn.setToolTip(
            "Revert is not available in Link Instances tab")

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self._adjust_validation_panel_size()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.remove_change_listener(self._on_session_change)
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # type: ignore[override]
        if self._refresh_pending:
            self._refresh_pending = False
            self._refresh_validation_log()
            if self._current_link_instance_id is not None:
                self.open_link_instance(self._current_link_instance_id)
        super().showEvent(event)

    def current_link_instance_id(self) -> str | None:
        """Return the currently opened link instance id."""
        return self._current_link_instance_id

    def open_link_instance(self, link_instance_id: str) -> None:
        """Open one link instance in the details canvas."""
        self._current_link_instance_id = link_instance_id
        self._library.set_current_open_link_instance(link_instance_id)

        link = self._find_link_instance(link_instance_id)
        if link is None:
            self._canvas_title.setText(f"(missing) {link_instance_id}")
            self._details.clear()
            self._inspector.clear()
            self._refresh_validation_log()
            return

        self._canvas_title.setText(self._link_title(link))
        self._details.setPlainText(self._format_link_details(link))
        self._inspector.set_node(self._inspector_node_for_link(link))
        self._refresh_validation_log()
        self.node_opened.emit(link_instance_id)

    def splitter_state(self) -> dict[str, list[int]]:
        """Return current splitter sizes for UI state persistence."""
        return {"outer": self._splitter.sizes()}

    def restore_splitter_state(self, state: dict[str, list[int]]) -> None:
        """Restore splitter sizes from a previously saved state dict."""
        outer = state.get("outer")
        if outer and len(outer) == 3:
            self._splitter.setSizes(outer)

    def _build_layout(self) -> None:
        self._left_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._left_splitter.setObjectName("kb_link_instances_left_splitter")
        self._left_splitter.addWidget(self._library)
        self._left_splitter.addWidget(self._validation_log)
        self._left_splitter.setHandleWidth(8)
        self._left_splitter.setStretchFactor(0, 3)
        self._left_splitter.setStretchFactor(1, 1)
        self._left_splitter.setSizes([320, 170])
        self._left_splitter.setMinimumWidth(180)

        ribbon = self._build_ribbon()

        center_panel = QWidget(self)
        center_panel.setObjectName("kb_center_panel")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(ribbon)
        center_layout.addWidget(self._details, stretch=1)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setObjectName("kb_link_instances_splitter")
        self._splitter.addWidget(self._left_splitter)
        self._splitter.addWidget(center_panel)
        self._splitter.addWidget(self._inspector)
        self._splitter.setHandleWidth(8)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.setSizes([260, 760, 360])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._splitter, stretch=1)

    def _wire_signals(self) -> None:
        self._library.link_instance_load_requested.connect(
            self.open_link_instance)
        self._library.link_instance_deleted.connect(
            self._on_link_instance_deleted)
        self._validation_log.panel_height_changed.connect(
            self._adjust_validation_panel_size
        )
        self._session.add_change_listener(self._on_session_change)

    def _adjust_validation_panel_size(self, preferred: int | None = None) -> None:
        if preferred is None:
            preferred = self._validation_log.preferred_panel_height()
        sizes = self._left_splitter.sizes()
        if len(sizes) < 2:
            return
        target = max(32, min(preferred, 280))
        total = max(sum(sizes), target + 1)
        top = max(total - target, 120)
        self._left_splitter.setSizes([top, target])

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            self._base_ribbon_stylesheet()
            + f"QSplitter#kb_link_instances_splitter::handle:horizontal {{"
            " background: #2c2c2c;"
            " border-left: 1px solid #5b5b5b;"
            " border-right: 1px solid #171717;"
            "}"
            "QSplitter#kb_link_instances_splitter::handle:horizontal:hover {"
            " background: #3a3a3a;"
            " border-left: 1px solid #7b7b7b;"
            "}"
            "QSplitter#kb_link_instances_left_splitter::handle:vertical {"
            " background: #2c2c2c;"
            " border-top: 1px solid #5b5b5b;"
            " border-bottom: 1px solid #171717;"
            "}"
            "QSplitter#kb_link_instances_left_splitter::handle:vertical:hover {"
            " background: #3a3a3a;"
            " border-top: 1px solid #7b7b7b;"
            "}"
            "QSplitter#kb_link_instances_left_splitter { border: 1px solid #4a4a4a; }"
            "QWidget#kb_center_panel { border: 1px solid #4a4a4a; }"
            "QWidget#kb_link_instance_inspector { border: 1px solid #4a4a4a; }"
            f"QPlainTextEdit#kb_link_instance_details {{"
            f" background: {SCENE_BACKGROUND_COLOR};"
            f" color: {NODE_TEXT_COLOR};"
            f" border: 1px solid {EDGE_COLOR};"
            f" font-family: '{FIELD_MONO_FONT_FAMILY}';"
            " padding: 8px;"
            "}"
        )

    def _on_session_change(self, event: SessionChangeEvent) -> None:
        change_type = event.change_type
        if change_type not in {"link", "node", "link_type", "repo_loaded"}:
            return
        if change_type == "repo_loaded":
            self._current_link_instance_id = None
            self._library.set_current_open_link_instance(None)
            self._canvas_title.setText("No item loaded")
            self._details.clear()
            self._inspector.clear()
        if change_type == "node" and not self._node_change_affects_current_link_instance(event):
            return
        if not self.isVisible():
            self._refresh_pending = True
            return
        self._refresh_validation_log()
        if self._current_link_instance_id is None:
            return
        link = self._find_link_instance(self._current_link_instance_id)
        if link is None:
            self._canvas_title.setText(
                f"(missing) {self._current_link_instance_id}")
            self._details.clear()
            self._inspector.clear()
            return
        self._canvas_title.setText(self._link_title(link))
        self._details.setPlainText(self._format_link_details(link))
        self._inspector.set_node(self._inspector_node_for_link(link))

    def _node_change_affects_current_link_instance(self, event: SessionChangeEvent) -> bool:
        touched_ids = event.touched_ids
        if touched_ids is None:
            return True
        if self._current_link_instance_id is None:
            return False
        link = self._find_link_instance(self._current_link_instance_id)
        if link is None:
            return self._current_link_instance_id in touched_ids
        relevant_ids = {
            str(link.id),
            str(link.source_node_id),
            str(link.target_node_id),
            str(link.link_type_id),
        }
        return bool(relevant_ids.intersection(touched_ids))

    def _on_link_instance_deleted(self, link_instance_id: str) -> None:
        if self._current_link_instance_id != link_instance_id:
            return
        self._current_link_instance_id = None
        self._canvas_title.setText("No item loaded")
        self._details.clear()
        self._inspector.clear()

    def _find_link_instance(self, link_instance_id: str) -> LinkInstance | None:
        for link in self._session.list_links():
            if str(link.id) == link_instance_id:
                return link
        return None

    def _link_title(self, link: LinkInstance) -> str:
        source = self._node_name(str(link.source_node_id))
        target = self._node_name(str(link.target_node_id))
        link_type_name = self._link_type_name(str(link.link_type_id))
        return f"{source} -> {target} [{link_type_name}]"

    def _format_link_details(self, link: LinkInstance) -> str:
        metadata_text = json.dumps(link.metadata, indent=2, sort_keys=True)
        return "\n".join(
            [
                f"id: {link.id}",
                f"link_type: {self._link_type_name(str(link.link_type_id))} ({link.link_type_id})",
                f"source: {self._node_name(str(link.source_node_id))} ({link.source_node_id})",
                f"target: {self._node_name(str(link.target_node_id))} ({link.target_node_id})",
                f"display_color: {link.display_color or '(none)'}",
                "metadata:",
                metadata_text,
            ]
        )

    def _inspector_node_for_link(self, link: LinkInstance):
        """Choose a representative node for shared inspector display."""
        try:
            return self._session.get_node(str(link.source_node_id))
        except KeyError:
            try:
                return self._session.get_node(str(link.target_node_id))
            except KeyError:
                return None

    def _refresh_validation_log(self) -> None:
        entries: list[ValidationErrorEntry] = []

        if self._current_link_instance_id is None:
            self._validation_log.set_validation_errors([])
            return

        link = self._find_link_instance(self._current_link_instance_id)
        if link is None:
            entries.append(
                ValidationErrorEntry(
                    node_id=self._current_link_instance_id,
                    node_name="(missing link)",
                    field_name="id",
                    error_message="Link instance no longer exists.",
                    error_level="error",
                )
            )
            self._validation_log.set_validation_errors(entries)
            return

        try:
            self._session.get_link_type(str(link.link_type_id))
        except KeyError:
            entries.append(
                ValidationErrorEntry(
                    node_id=str(link.id),
                    node_name=self._link_title(link),
                    field_name="link_type_id",
                    error_message="Link type is missing.",
                    error_level="error",
                )
            )
        try:
            self._session.get_node(str(link.source_node_id))
        except KeyError:
            entries.append(
                ValidationErrorEntry(
                    node_id=str(link.id),
                    node_name=self._link_title(link),
                    field_name="source_node_id",
                    error_message="Source node is missing.",
                    error_level="error",
                )
            )
        try:
            self._session.get_node(str(link.target_node_id))
        except KeyError:
            entries.append(
                ValidationErrorEntry(
                    node_id=str(link.id),
                    node_name=self._link_title(link),
                    field_name="target_node_id",
                    error_message="Target node is missing.",
                    error_level="error",
                )
            )

        self._validation_log.set_validation_errors(entries)

    def _node_name(self, node_id: str) -> str:
        try:
            return self._session.get_node(node_id).name
        except KeyError:
            return "(missing node)"

    def _link_type_name(self, link_type_id: str) -> str:
        try:
            return self._session.get_link_type(link_type_id).name
        except KeyError:
            return "(missing link type)"


__all__ = ["QKnowledgeLinkInstancesTabWidget"]

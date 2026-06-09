"""Shell tab for browsing and creating semantic link types.

Layout: Library (left) | Canvas (center) | Inspector (right)
Matches the primitive tab widget structure but without palette or connections pane.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.q_dialog_scaffold_base import QDialogScaffoldBase

from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
    REF_VALID_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.editor_session_types import SessionChangeEvent
from lks_utils.knowledge.display_color import normalize_display_color
from lks_utils.knowledge.links.link_type import LinkType, SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
    validate_extends_link_type,
    validate_instance_of_link_type,
)
from lks_utils.knowledge.ui.components.link_type_editor_panel import QKnowledgeLinkTypeEditorPanel
from lks_utils.knowledge.ui.components.link_types_library_panel import QKnowledgeLinkTypesLibraryPanel
from lks_utils.knowledge.ui.widgets.link_type_canvas import QKnowledgeLinkTypeCanvasWidget
from lks_utils.knowledge.ui.widgets.validation_log import (
    QKnowledgeValidationLogWidget,
    ValidationErrorEntry,
)
from lks_utils.knowledge.ui.editor_tab_base import QKnowledgeEditorTabBase


class _QNewLinkTypeDialog(QDialogScaffoldBase):
    """Collect a new link-type name with live uniqueness validation."""

    def __init__(
        self,
        existing_names: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Create Link Type", parent=parent)
        self._existing_names = {name.strip()
                                for name in existing_names if name.strip()}

        self._name_edit = QLineEdit(self)
        self._name_edit.setToolTip(
            "Name for the new link type. Must be unique among all link types."
        )
        self._name_status = QLabel("", self)
        self._name_status.setObjectName("new_link_type_name_status")
        self._name_status.setWordWrap(True)

        form = QFormLayout()
        name_row = QWidget(self)
        name_layout = QVBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(2)
        name_layout.addWidget(self._name_edit)
        name_layout.addWidget(self._name_status)
        form.addRow("Name", name_row)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addLayout(form)
        self.set_content(content)
        self._ok_button = self.add_footer_button(
            "OK", QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_footer_button(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)

        self._name_edit.textChanged.connect(self._update_status)
        self._update_status()

    def name_value(self) -> str:
        """Return the normalized entered name."""
        return self._name_edit.text().strip()

    def _update_status(self) -> None:
        candidate = self.name_value()
        if not candidate:
            self._name_status.setText("X Name is required.")
            self._name_status.setStyleSheet(
                f"color: {VALIDATION_ERROR_TEXT}; padding: 0 2px;"
            )
            self._ok_button.setEnabled(False)
            return
        if candidate in self._existing_names:
            self._name_status.setText(
                "X Name already exists. Choose a unique name.")
            self._name_status.setStyleSheet(
                f"color: {VALIDATION_ERROR_TEXT}; padding: 0 2px;"
            )
            self._ok_button.setEnabled(False)
            return
        self._name_status.setText("OK Name available")
        self._name_status.setStyleSheet(
            f"color: {REF_VALID_COLOR}; padding: 0 2px;"
        )
        self._ok_button.setEnabled(True)


class QKnowledgeLinkTypesTabWidget(QKnowledgeEditorTabBase):
    """Three-panel link types editor: Library | Canvas | Inspector."""

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(session, parent)
        self._current_link_type_id: str | None = None
        self._editing_link_type: LinkType | None = None
        self._inspector_baseline: tuple[str | None, str, str, str,
                                        str | None, str | None, str, str | None] | None = None
        self._inspector_dirty: bool = False
        self._autosave_in_progress: bool = False
        self._refresh_pending: bool = False

        self._revert_btn.setToolTip(
            "Revert this link-type file to last git commit after confirmation")

        # -- Left: Library ------------------------------------------------
        self._library = QKnowledgeLinkTypesLibraryPanel(session, self)
        self._validation_log = QKnowledgeValidationLogWidget(self)
        self._validation_log.setObjectName("kb_link_types_validation_log")

        # -- Center: Canvas -----------------------------------------------
        self._canvas = QKnowledgeLinkTypeCanvasWidget(session, self)

        # -- Right: Inspector ---------------------------------------------
        self._inspector = QKnowledgeLinkTypeEditorPanel(session, self)
        self._inspector.setObjectName("kb_link_type_inspector")
        self._inspector.setMinimumWidth(340)

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self._adjust_validation_panel_size()
        self._refresh_canvas_title()
        self._refresh_validation_log()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.remove_change_listener(self._on_session_change)
        super().closeEvent(event)  # base stops save hint timer

    def showEvent(self, event) -> None:  # type: ignore[override]
        if self._refresh_pending:
            self._refresh_pending = False
            self._on_session_change("node")
        super().showEvent(event)

    def open_link_type(self, link_type_id: str) -> None:
        """Load a link type into the canvas and inspector."""
        self._current_link_type_id = link_type_id
        self._library.set_current_open_link_type(link_type_id)

        try:
            link_type = self._session.get_link_type(link_type_id)
        except KeyError:
            self._canvas_title.setText(f"(missing) {link_type_id}")
            self._canvas.clear()
            self._inspector.clear()
            self._refresh_validation_log()
            return

        self._editing_link_type = link_type
        self._canvas.open_link_type(link_type)
        self._inspector.load_link_type(link_type)
        self._reset_inspector_baseline_from_editor()
        self._refresh_canvas_title()
        self._refresh_validation_log()

    def create_new_link_type(self) -> None:
        """Prepare to create a new link type."""
        self._current_link_type_id = None
        self._editing_link_type = None
        self._library.set_current_open_link_type("")
        self._canvas.clear()
        self._inspector.edit_new()
        self._reset_inspector_baseline_from_editor()
        self._refresh_canvas_title()
        self._refresh_validation_log()

    def request_new_link_type(self) -> None:
        """Ask for a link-type name, then seed a draft in inspector/canvas."""
        existing_names = [
            link_type.name
            for link_type in self._session.list_link_types()
        ]
        dialog = _QNewLinkTypeDialog(existing_names, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name = dialog.name_value()
        self.create_new_link_type()
        self._inspector._name_edit.setText(name)  # noqa: SLF001
        draft = self._inspector.build_link_type()
        self._editing_link_type = draft
        self._canvas.open_link_type(draft)
        self._update_inspector_dirty_state()
        self._refresh_canvas_title()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self._left_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._left_splitter.setObjectName("kb_link_types_left_splitter")
        self._left_splitter.addWidget(self._library)
        self._left_splitter.addWidget(self._validation_log)
        self._left_splitter.setHandleWidth(8)
        self._left_splitter.setStretchFactor(0, 3)
        self._left_splitter.setStretchFactor(1, 1)
        self._left_splitter.setSizes([320, 170])
        self._left_splitter.setMinimumWidth(180)

        # Center: ribbon + canvas
        ribbon = self._build_ribbon()
        center_panel = QWidget(self)
        center_panel.setObjectName("kb_center_panel")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(ribbon)
        center_layout.addWidget(self._canvas, stretch=1)

        # Outer horizontal splitter: Library | Canvas | Inspector
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setObjectName("kb_link_types_splitter")
        self._splitter.addWidget(self._left_splitter)
        self._splitter.addWidget(center_panel)
        self._splitter.addWidget(self._inspector)
        self._splitter.setHandleWidth(8)
        self._splitter.setStretchFactor(0, 0)  # Library: no stretch
        self._splitter.setStretchFactor(1, 1)  # Canvas: stretch
        self._splitter.setStretchFactor(2, 0)  # Inspector: no stretch
        self._splitter.setSizes([240, 760, 340])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._splitter, stretch=1)

    def _wire_signals(self) -> None:
        self._library.new_item_requested.connect(self.request_new_link_type)
        self._library.link_type_load_requested.connect(self.open_link_type)
        self._library.link_type_deleted.connect(self._on_link_type_deleted)
        self._inspector.save_requested.connect(self._on_inspector_save)
        self._inspector.changed.connect(self._on_inspector_changed)
        self._inspector.committed.connect(self._on_inspector_committed)
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

    def _on_session_change(self, event: SessionChangeEvent | str) -> None:
        event_obj = event if isinstance(
            event, SessionChangeEvent) else SessionChangeEvent(change_type=event)
        change_type = event_obj.change_type
        # EditorSession.apply_mutation emits "node" for generic repository edits,
        # including link-type saves from this tab.
        if change_type not in {"node", "link_type", "repo_loaded"}:
            return
        if change_type == "node" and not self._node_change_affects_tab(event_obj):
            return
        if not self.isVisible():
            self._refresh_pending = True
            return
        self._library.refresh()
        self._inspector.refresh_constraint_options()
        if self._current_link_type_id:
            try:
                self._session.get_link_type(self._current_link_type_id)
            except KeyError:
                self.create_new_link_type()
        self._refresh_validation_log()

    def _node_change_affects_tab(self, event: SessionChangeEvent) -> bool:
        touched_ids = event.touched_ids
        if touched_ids is None:
            return True
        if self._current_link_type_id is not None and self._current_link_type_id in touched_ids:
            return True
        link_type_ids = {str(link_type.id)
                         for link_type in self._session.list_link_types()}
        return bool(link_type_ids.intersection(touched_ids))

    def _on_link_type_deleted(self, _link_type_id: str) -> None:
        self.create_new_link_type()

    def _on_inspector_changed(self) -> None:
        self._update_inspector_dirty_state()
        self._refresh_validation_log()

    def _on_inspector_committed(self) -> None:
        if self._autosave_in_progress:
            return
        self._update_inspector_dirty_state()
        self._refresh_validation_log()
        self._auto_save_if_valid()

    def _on_save(self) -> None:
        """Persist the currently edited link type immediately via apply_mutation."""
        link_type = self._inspector.build_link_type()

        reserved_ids = {
            SLOT_REF_LINK_TYPE_ID,
            EXTENDS_LINK_TYPE_ID,
            INSTANCE_OF_LINK_TYPE_ID,
        }
        if str(link_type.id) in reserved_ids:
            QMessageBox.warning(
                self,
                "Cannot Save",
                "System link types cannot be edited from the link types editor.",
            )
            self.open_link_type(str(link_type.id))
            return

        result = self._session.io_upsert_link_type(link_type)
        if not result.ok:
            QMessageBox.warning(
                self,
                "Save Failed",
                result.error_message or "Unable to save link type.",
            )
            return
        self._current_link_type_id = str(link_type.id)
        self._editing_link_type = link_type
        self.open_link_type(str(link_type.id))
        self._refresh_validation_log()

    def _on_revert(self) -> None:
        """Revert current link-type file to HEAD (with confirmation) then reload."""
        try:
            if self._current_link_type_id:
                root = self._session.repository_root
                if root is not None:
                    lt_paths = self._session.link_type_storage_paths(root)
                    target = lt_paths.get(self._current_link_type_id)
                    if target is not None:
                        rel_path = target.relative_to(root).as_posix()
                        git_result = self._confirm_and_revert_file_to_last_commit(
                            core_label="link type",
                            rel_path=rel_path,
                        )
                        if git_result is False:
                            return
                if self._session.repository_root is not None:
                    self._session.load()
                self.open_link_type(self._current_link_type_id)
            else:
                self.create_new_link_type()
            self._refresh_validation_log()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Revert Failed", str(exc))

    def _on_save_all(self) -> None:
        """Save-all mirrors save in immediate mode."""
        try:
            self._on_save()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Save All Failed", str(exc))

    def _on_inspector_save(self, _link_type: LinkType) -> None:
        """Respond to inspector save signal."""
        self._on_save()

    def _auto_save_if_valid(self) -> None:
        """Persist a committed edit when the current draft is valid."""
        if self._autosave_in_progress:
            return
        if not self._inspector_dirty:
            return

        try:
            candidate = self._inspector.build_link_type()
        except Exception as exc:
            self._inspector.set_status_message(str(exc))
            return

        valid_name, message = self._inspector._validate_name(  # noqa: SLF001
            candidate.name.strip()
        )
        if not valid_name:
            self._inspector.set_status_message(message)
            return

        reserved_ids = {
            SLOT_REF_LINK_TYPE_ID,
            EXTENDS_LINK_TYPE_ID,
            INSTANCE_OF_LINK_TYPE_ID,
        }
        if str(candidate.id) in reserved_ids:
            return

        self._autosave_in_progress = True
        try:
            result = self._session.io_upsert_link_type(candidate)
            if not result.ok:
                self._inspector.set_status_message(
                    result.error_message or "Unable to save link type."
                )
                return

            self._inspector.set_status_message("")
            self._current_link_type_id = str(candidate.id)
            self._editing_link_type = candidate
            self.open_link_type(str(candidate.id))
            self._refresh_validation_log()
        finally:
            self._autosave_in_progress = False

    def _refresh_validation_log(self) -> None:
        entries: list[ValidationErrorEntry] = []

        if self._editing_link_type is None:
            self._validation_log.set_validation_errors([])
            return

        try:
            candidate = self._inspector.build_link_type()
        except Exception as exc:
            entries.append(
                ValidationErrorEntry(
                    node_id=str(self._editing_link_type.id),
                    node_name=self._editing_link_type.name or "(new link type)",
                    field_name="editor",
                    error_message=str(exc),
                    error_level="error",
                )
            )
            self._validation_log.set_validation_errors(entries)
            return

        valid_name, name_msg = self._inspector._validate_name(  # noqa: SLF001
            candidate.name.strip()
        )
        if not valid_name and name_msg:
            entries.append(
                ValidationErrorEntry(
                    node_id=str(candidate.id),
                    node_name=candidate.name or "(new link type)",
                    field_name="name",
                    error_message=name_msg,
                    error_level="error",
                )
            )

        if str(candidate.id) == EXTENDS_LINK_TYPE_ID:
            try:
                validate_extends_link_type(candidate)
            except Exception as exc:
                entries.append(
                    ValidationErrorEntry(
                        node_id=str(candidate.id),
                        node_name=candidate.name,
                        field_name="system_contract",
                        error_message=str(exc),
                        error_level="error",
                    )
                )
        if str(candidate.id) == INSTANCE_OF_LINK_TYPE_ID:
            try:
                validate_instance_of_link_type(candidate)
            except Exception as exc:
                entries.append(
                    ValidationErrorEntry(
                        node_id=str(candidate.id),
                        node_name=candidate.name,
                        field_name="system_contract",
                        error_message=str(exc),
                        error_level="error",
                    )
                )

        self._validation_log.set_validation_errors(entries)

    def _refresh_canvas_title(self) -> None:
        if self._editing_link_type:
            self._canvas_title.setText(
                f"Link Type: {self._editing_link_type.name}")
        else:
            self._canvas_title.setText("New Link Type")

    def _reset_inspector_baseline_from_editor(self) -> None:
        snapshot = self._snapshot_from_editor()
        self._inspector_baseline = snapshot
        self._inspector_dirty = False

    def _update_inspector_dirty_state(self) -> None:
        current = self._snapshot_from_editor()
        if current is None:
            self._inspector_dirty = False
            return
        if self._inspector_baseline is None:
            self._inspector_dirty = True
            return
        self._inspector_dirty = current != self._inspector_baseline

    def _snapshot_from_editor(
        self,
    ) -> tuple[str | None, str, str, str, str | None, str | None, str, str | None] | None:
        try:
            return self._snapshot_link_type(self._inspector.build_link_type())
        except Exception:
            return None

    def _snapshot_link_type(
        self,
        link_type: LinkType,
    ) -> tuple[str | None, str, str, str, str | None, str | None, str, str | None]:
        return (
            str(link_type.id) if link_type.id else None,
            link_type.name.strip(),
            link_type.inverse_name.strip(),
            link_type.description.strip(),
            link_type.source_type_constraint,
            link_type.target_type_constraint,
            link_type.cardinality,
            normalize_display_color(link_type.display_color),
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QWidget#canvas_ribbon {{ background: #1e1e1e; border-bottom: 1px solid {EDGE_COLOR}; }}"
            f"QLabel#canvas_title {{ color: {NODE_TEXT_COLOR}; font-weight: 600; }}"
            "QSplitter#kb_link_types_splitter::handle:horizontal {"
            " background: #2c2c2c;"
            " border-left: 1px solid #5b5b5b;"
            " border-right: 1px solid #171717;"
            "}"
            "QSplitter#kb_link_types_splitter::handle:horizontal:hover {"
            " background: #3a3a3a;"
            " border-left: 1px solid #7b7b7b;"
            "}"
            "QSplitter#kb_link_types_left_splitter::handle:vertical {"
            " background: #2c2c2c;"
            " border-top: 1px solid #5b5b5b;"
            " border-bottom: 1px solid #171717;"
            "}"
            "QSplitter#kb_link_types_left_splitter::handle:vertical:hover {"
            " background: #3a3a3a;"
            " border-top: 1px solid #7b7b7b;"
            "}"
            "QSplitter#kb_link_types_left_splitter { border: 1px solid #4a4a4a; }"
            "QWidget#kb_center_panel { border: 1px solid #4a4a4a; }"
            "QWidget#kb_link_type_inspector { border: 1px solid #4a4a4a; }"
        )


class QKnowledgeLinkTypesTabWidget_Legacy(QWidget):
    """Legacy two-panel link types tab (kept for backward compatibility)."""

    add_requested = Signal()

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        # Delegate to new widget
        self._new_widget = QKnowledgeLinkTypesTabWidget(session, self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._new_widget, stretch=1)

    def refresh(self) -> None:
        """For backward compatibility."""
        self._new_widget._library.refresh()


__all__ = ["QKnowledgeLinkTypesTabWidget",
           "QKnowledgeLinkTypesTabWidget_Legacy",
           "_QNewLinkTypeDialog"]

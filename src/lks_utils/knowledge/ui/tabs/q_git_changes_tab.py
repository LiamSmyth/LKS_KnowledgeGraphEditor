"""Git changes tab UI skeleton for staged/unstaged knowledge repo actions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.widgets import QMultiSelectListWidget
from lks_utils.knowledge.default_theme import (
    FIELD_BUTTON_TEXT,
    GIT_DELETED_COLOR,
    GIT_MODIFIED_COLOR,
    GIT_UNTRACKED_COLOR,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.ui.components.q_impact_confirm_dialog import (
    QImpactConfirmDialog,
)
from lks_utils.knowledge.ui.tabs.q_git_changes_tab_actions import (
    GIT_COMMIT_ALL,
    GIT_COMMIT_STAGED,
    GIT_LOAD_DIFF,
    GIT_REVERT_SELECTED,
    GIT_STAGE_ALL,
    GIT_STAGE_SELECTED,
    GIT_UNSTAGE_ALL,
    GIT_UNSTAGE_SELECTED,
)
from lks_utils.knowledge.shelf_service import ShelfService
from lks_utils.knowledge.version_control import KnowledgeVersionControl

if TYPE_CHECKING:
    from PySide6.QtGui import QShowEvent

    from lks_utils.knowledge.editor_session import EditorSession
    from lks_utils.knowledge.editor_session_types import SessionChangeEvent
    from lks_utils.knowledge.git_service import KnowledgeGitService
    from lks_utils.knowledge.version_control import KnowledgeVersionControl


class QGitChangesTab(QWidget):
    """Two-pane git-change review tab with commit action toolbar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._session: EditorSession | None = None
        self._git_service: KnowledgeGitService | None = None
        self._version_control: KnowledgeVersionControl | None = None
        self._shelf_service: ShelfService | None = None
        self._staged_paths: set[str] = set()
        self._unstaged_paths: set[str] = set()
        self._change_paths: list[str] = []
        self._status_codes_by_path: dict[str, str] = {}
        self._invalid_changed_paths: set[str] = set()
        self._object_id_by_path: dict[str, str] = {}
        self._object_id_cache_valid: bool = False
        self._last_shelf_warning_signature: tuple[str, ...] = ()
        self._refresh_pending: bool = False

        self._empty_label = QLabel("No repository loaded", self)
        self._empty_label.setObjectName("gitChangesEmptyLabel")

        self._status_label = QLabel("", self)
        self._status_label.setObjectName("gitChangesStatusLabel")

        self._shelf_banner = QWidget(self)
        self._shelf_banner.setObjectName("gitChangesShelfBanner")
        banner_layout = QHBoxLayout(self._shelf_banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        banner_layout.setSpacing(6)
        self._shelf_banner_label = QLabel("", self._shelf_banner)
        self._recover_shelf_btn = QPushButton(
            "Recover from shelf", self._shelf_banner)
        self._recover_shelf_btn.clicked.connect(self._open_shelves_folder)
        banner_layout.addWidget(self._shelf_banner_label)
        banner_layout.addStretch(1)
        banner_layout.addWidget(self._recover_shelf_btn)

        self._file_list = QMultiSelectListWidget(self)
        self._file_list.setObjectName("gitChangesFileList")

        self._staged_label = QLabel("Staged files (0)", self)
        self._staged_label.setObjectName("gitChangesStagedLabel")

        self._staged_list = QMultiSelectListWidget(self)
        self._staged_list.setObjectName("gitChangesStagedList")

        self._diff_view = QTextEdit(self)
        self._diff_view.setReadOnly(True)
        self._diff_view.setObjectName("gitChangesDiffView")
        self._diff_view.setPlaceholderText("Diff preview")

        self._load_diff_btn = QPushButton("Load Diff", self)
        self._load_diff_btn.setProperty("action_id", GIT_LOAD_DIFF.id)
        self._load_diff_btn.clicked.connect(self._handle_load_diff)

        self._commit_message = QPlainTextEdit(self)
        self._commit_message.setObjectName("gitChangesCommitMessage")
        self._commit_message.setPlaceholderText("Commit message")
        self._commit_message.setPlainText("")

        self._stage_btn = QPushButton("Stage Selected", self)
        self._stage_all_btn = QPushButton("Stage All", self)
        self._stage_deps_btn = QPushButton("Stage Dependencies", self)
        self._unstage_btn = QPushButton("Unstage Selected", self)
        self._unstage_all_btn = QPushButton("Unstage All", self)
        self._revert_btn = QPushButton("Revert Selected", self)
        self._commit_staged_btn = QPushButton("Commit Staged", self)
        self._commit_all_btn = QPushButton("Commit All", self)

        self._stage_btn.setProperty("action_id", GIT_STAGE_SELECTED.id)
        self._stage_all_btn.setProperty("action_id", GIT_STAGE_ALL.id)
        self._unstage_btn.setProperty("action_id", GIT_UNSTAGE_SELECTED.id)
        self._unstage_all_btn.setProperty("action_id", GIT_UNSTAGE_ALL.id)
        self._revert_btn.setProperty("action_id", GIT_REVERT_SELECTED.id)
        self._commit_staged_btn.setProperty(
            "action_id", GIT_COMMIT_STAGED.id)
        self._commit_all_btn.setProperty("action_id", GIT_COMMIT_ALL.id)

        self._stage_btn.clicked.connect(self._handle_stage_selected)
        self._stage_all_btn.clicked.connect(self._handle_stage_all)
        self._unstage_btn.clicked.connect(self._handle_unstage_selected)
        self._unstage_all_btn.clicked.connect(self._handle_unstage_all)
        self._revert_btn.clicked.connect(self._handle_revert_selected)
        self._commit_staged_btn.clicked.connect(self._handle_commit_staged)
        self._commit_all_btn.clicked.connect(self._handle_commit_all)
        self._stage_deps_btn.clicked.connect(self._handle_stage_dependencies)

        self._build_layout()
        self._apply_styles()
        self._file_list.selection_changed.connect(
            self._on_file_selection_changed)
        self.set_repo_loaded(False)

    def bind_sources(
        self,
        *,
        session: EditorSession | None,
        git_service: KnowledgeGitService | None,
    ) -> None:
        """Attach session and git service to drive event-based status refresh."""
        if self._session is not None:
            self._session.remove_listener(self._on_session_change)
        if self._git_service is not None:
            try:
                self._git_service.git_status_changed.disconnect(
                    self._on_git_status_changed)
            except Exception:
                pass
        if self._shelf_service is not None:
            try:
                self._shelf_service.shelves_changed.disconnect(
                    self._on_shelves_changed)
            except Exception:
                pass
            try:
                self._shelf_service.snapshot_created.disconnect(
                    self._on_snapshot_created)
            except Exception:
                pass

        self._session = session
        self._git_service = git_service
        self._version_control = None
        self._shelf_service = None
        self._object_id_cache_valid = False  # Invalidate cache when repo changes

        if self._session is not None and self._git_service is not None:
            self._version_control = KnowledgeVersionControl(
                repository=self._session._repository,  # noqa: SLF001
                git_service=self._git_service,
            )
            if self._session.repository_root is not None:
                self._shelf_service = ShelfService(
                    repository_root=self._session.repository_root,
                    git_service=self._git_service,
                    parent=self,
                )
                self._shelf_service.shelves_changed.connect(
                    self._on_shelves_changed)
                self._shelf_service.snapshot_created.connect(
                    self._on_snapshot_created)

        if self._session is not None:
            self._session.add_change_listener(self._on_session_change)
        if self._git_service is not None:
            self._git_service.git_status_changed.connect(
                self._on_git_status_changed)

        self.refresh_changes_from_git()

    def set_repo_loaded(self, loaded: bool) -> None:
        """Switch between empty state and active tab content."""
        self._empty_label.setVisible(not loaded)
        self._status_label.setVisible(loaded)
        self._file_list.setEnabled(loaded)
        self._staged_label.setVisible(loaded)
        self._staged_list.setEnabled(loaded)
        self._diff_view.setEnabled(loaded)
        self._commit_message.setEnabled(loaded)
        self._update_toolbar_state()

    def set_changes(self, rel_paths: list[str]) -> None:
        """Replace change-list items shown in left pane."""
        self._change_paths = list(rel_paths)
        self._status_codes_by_path = {}
        self._file_list.set_items(rel_paths)
        if not rel_paths:
            self._diff_view.setPlainText("No changes")
            self._empty_label.setText("No changes")

    def set_changes_with_status(
        self,
        rel_paths: list[str],
        *,
        status_by_path: dict[str, str],
    ) -> None:
        """Replace change-list rows and show right-aligned status badges."""
        self._change_paths = list(rel_paths)
        self._status_codes_by_path = dict(status_by_path)
        color_by_status = {
            "U": GIT_UNTRACKED_COLOR,
            "M": GIT_MODIFIED_COLOR,
            "D": GIT_DELETED_COLOR,
        }
        badges_by_path = {
            path: self._badges_for_path(path, status_by_path.get(
                path, ""), path in self._invalid_changed_paths)
            for path in rel_paths
        }
        _ = color_by_status
        self._file_list.set_items_with_right_badges(
            rel_paths,
            badges_by_value=badges_by_path,
        )
        if not rel_paths:
            self._diff_view.setPlainText("No changes")
            self._empty_label.setText("No changes")

    def set_diff_text(self, text: str) -> None:
        """Set right-pane diff preview text."""
        self._diff_view.setPlainText(text)

    def commit_message(self) -> str:
        """Return current commit message editor text."""
        return self._commit_message.toPlainText()

    def refresh_changes_from_git(self) -> None:
        """Refresh left file-list from current git status snapshot.

        Reads from the cached status snapshot (non-blocking).  When
        ``_refresh_pending`` is set — meaning the tab was hidden during a
        session or filesystem change — performs a synchronous cache refresh
        first so that the UI reflects the current on-disk state immediately.
        """
        if self._git_service is None:
            self._staged_paths = set()
            self._unstaged_paths = set()
            self.set_repo_loaded(False)
            self.set_changes([])
            self._empty_label.setText("No repository loaded")
            self._status_label.setText("")
            self._update_shelf_banner()
            self._update_diff_hint_for_selection()
            return
        # If a deferred refresh was pending (tab was hidden during a session
        # or filesystem change), sync-scan now to avoid showing stale data.
        if self._refresh_pending:
            self._refresh_pending = False
            self._git_service.refresh_status()
        previously_selected = set(self._file_list.selected_values())
        status = self._git_service.cached_status
        self._staged_paths = set(status.staged_paths)
        self._unstaged_paths = set(
            status.unstaged_paths) | set(status.untracked_paths)
        paths = sorted(status.all_modified_paths)
        self.set_repo_loaded(True)
        # Only rebuild object ID mapping when cache is invalid (on node/link/type changes)
        if not self._object_id_cache_valid:
            self._object_id_by_path = self._build_object_id_by_path()
            self._object_id_cache_valid = True
        self._invalid_changed_paths = {
            path for path in paths if self._path_has_validation_failure(path)}
        status_by_path = {
            path: self._git_service.change_code(path)
            for path in paths
        }
        self.set_changes_with_status(paths, status_by_path=status_by_path)
        if previously_selected:
            paths_set = set(paths)
            to_reselect = [
                p for p in paths if p in previously_selected and p in paths_set]
            if to_reselect:
                self._file_list.select_values(to_reselect)
        self._update_staged_items_view()
        self._status_label.setText(
            f"Changed: {len(paths)} | Staged: {len(self._staged_paths)} | Unstaged: {len(self._unstaged_paths)} | Invalid: {len(self._invalid_changed_paths)}"
        )
        self._update_toolbar_state()
        self._update_diff_hint_for_selection()
        self._update_shelf_banner()
        self._update_shelf_banner()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        # Schedule an async scan so the tab shows fresh data when revealed.
        # _request_refresh_from_events reads from cache (may be slightly stale
        # until the background result arrives via _on_git_status_changed).
        if self._git_service is not None:
            self._git_service.refresh_status_async()
        self._request_refresh_from_events(force=True)
        super().showEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._session is not None:
            self._session.remove_change_listener(self._on_session_change)
        if self._git_service is not None:
            try:
                self._git_service.git_status_changed.disconnect(
                    self._on_git_status_changed)
            except Exception:
                pass
        super().closeEvent(event)

    def _request_refresh_from_events(self, *, force: bool = False) -> None:
        """Refresh immediately only when visible; otherwise defer until shown."""
        if force or self.isVisible():
            self._refresh_pending = False
            self.refresh_changes_from_git()
            return
        self._refresh_pending = True

    def _on_session_change(self, event: object) -> None:
        change_type = event if isinstance(event, str) else getattr(
            event, "change_type", "")
        if not isinstance(change_type, str) or not change_type:
            return
        # Invalidate object ID cache when node/link structure changes
        if change_type in {"node", "link", "link_type", "repo_loaded", "repo_saved"}:
            self._object_id_cache_valid = False
        self._request_refresh_from_events()

    def _on_git_status_changed(self, _paths: object) -> None:
        # Background cache is already updated by the emitting call-site
        # (refresh_status / _apply_background_status); refresh UI from it.
        self._request_refresh_from_events()

    def _on_shelves_changed(self) -> None:
        self._update_shelf_banner()

    def _on_snapshot_created(self, changed_paths: object) -> None:
        changed = {
            str(path).replace("\\", "/")
            for path in (changed_paths or set())
            if path
        }
        invalid = tuple(
            sorted(changed.intersection(self._invalid_changed_paths)))
        if not invalid or invalid == self._last_shelf_warning_signature:
            return
        self._last_shelf_warning_signature = invalid
        self._status_label.setText(
            f"Shelved with warnings: {len(invalid)} invalid item(s)"
        )

    def _on_file_selection_changed(self, _selected_values: list[str]) -> None:
        self._update_toolbar_state()
        self._update_diff_hint_for_selection()

    def _update_diff_hint_for_selection(self) -> None:
        if self._git_service is None:
            self.set_diff_text("No repository loaded")
            return
        selected_paths = self._file_list.selected_values()
        if len(selected_paths) != 1:
            self.set_diff_text("Select a single file to view diff")
            return
        rel_path = selected_paths[0]
        status_code = self._status_codes_by_path.get(rel_path, "")
        if status_code in {"U", "D"}:
            self.set_diff_text(f"No diff needed for {status_code} entries")
            return
        self.set_diff_text("Click Load Diff to preview the selected file")

    def _update_toolbar_state(self) -> None:
        has_repo = self._git_service is not None
        has_selection = bool(self._file_list.selected_values())
        self._stage_btn.setEnabled(has_repo and has_selection)
        self._stage_all_btn.setEnabled(has_repo and bool(self._unstaged_paths))
        self._stage_deps_btn.setEnabled(has_repo and bool(self._staged_paths))
        self._unstage_btn.setEnabled(has_repo and has_selection)
        self._unstage_all_btn.setEnabled(has_repo and bool(self._staged_paths))
        self._revert_btn.setEnabled(has_repo and has_selection)
        self._load_diff_btn.setEnabled(has_repo and self._can_load_diff())
        self._commit_staged_btn.setEnabled(
            has_repo and bool(self._staged_paths))
        self._commit_all_btn.setEnabled(has_repo)

    def _can_load_diff(self) -> bool:
        selected_path = self._selected_single_path()
        if selected_path is None:
            return False
        return self._status_codes_by_path.get(selected_path, "") not in {"U", "D"}

    def _selected_paths(self) -> list[str]:
        return self._file_list.selected_values()

    def _selected_single_path(self) -> str | None:
        selected_paths = self._selected_paths()
        if len(selected_paths) != 1:
            return None
        return selected_paths[0]

    def _update_shelf_banner(self) -> None:
        if self._shelf_service is None:
            self._shelf_banner.setVisible(False)
            return
        shelf_root = self._shelf_service.shelves_root
        shelves = [path for path in shelf_root.iterdir(
        ) if path.is_dir()] if shelf_root.exists() else []
        has_shelves = bool(shelves)
        self._shelf_banner.setVisible(has_shelves)
        if has_shelves:
            warning = ""
            if self._invalid_changed_paths:
                warning = f" | Warning: {len(self._invalid_changed_paths)} invalid changed item(s) may be shelved"
            self._shelf_banner_label.setText(
                f"Recoverable shelves: {len(shelves)}{warning}"
            )

    def _update_staged_items_view(self) -> None:
        staged_paths = sorted(self._staged_paths)
        self._staged_label.setText(f"Staged files ({len(staged_paths)})")
        self._staged_list.set_items(staged_paths)

    def _badges_for_path(
        self,
        rel_path: str,
        change_code: str,
        is_invalid: bool,
    ) -> tuple[tuple[str, str | None], ...]:
        color_by_status = {
            "U": GIT_UNTRACKED_COLOR,
            "M": GIT_MODIFIED_COLOR,
            "D": GIT_DELETED_COLOR,
        }
        badges: list[tuple[str, str | None]] = []
        if change_code:
            badges.append((change_code, color_by_status.get(
                change_code, NODE_TEXT_COLOR)))
        if is_invalid:
            badges.append(("!", VALIDATION_ERROR_TEXT))
        return tuple(badges)

    def _path_has_validation_failure(self, rel_path: str) -> bool:
        if self._session is None:
            return False
        object_id = self._object_id_by_path.get(rel_path.replace("\\", "/"))
        if object_id is None:
            return False
        return not self._session.validation_index.status_for(object_id).is_valid

    def _build_object_id_by_path(self) -> dict[str, str]:
        if self._session is None or self._session.repository_root is None:
            return {}
        repository = self._session._repository  # noqa: SLF001
        root = self._session.repository_root
        mapping: dict[str, str] = {}
        for object_id, path in repository._build_storage_paths(root).items():  # noqa: SLF001
            mapping[path.relative_to(root).as_posix()] = object_id
        for object_id, path in repository._build_link_type_storage_paths(root).items():  # noqa: SLF001
            mapping[path.relative_to(root).as_posix()] = object_id
        for object_id, path in repository._build_link_storage_paths(root).items():  # noqa: SLF001
            mapping[path.relative_to(root).as_posix()] = object_id
        return mapping

    def _open_shelves_folder(self) -> None:
        if self._shelf_service is None:
            return
        folder = self._shelf_service.shelves_root
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _maybe_seed_commit_message(self) -> None:
        if self._commit_message.toPlainText().strip():
            return
        if self._git_service is None:
            return
        status = self._git_service.status()
        self._commit_message.setPlainText(
            self._git_service.auto_message(status))

    def _handle_stage_selected(self) -> None:
        if self._git_service is None:
            return
        selected_paths = self._selected_paths()
        if not selected_paths:
            return
        self._git_service.stage(selected_paths)
        self.refresh_changes_from_git()
        self._maybe_seed_commit_message()

    def _handle_stage_all(self) -> None:
        if self._git_service is None or not self._unstaged_paths:
            return
        self._git_service.stage_all()
        self.refresh_changes_from_git()
        self._maybe_seed_commit_message()

    def _handle_unstage_selected(self) -> None:
        if self._git_service is None:
            return
        selected_paths = self._selected_paths()
        if not selected_paths:
            return
        self._git_service.unstage(selected_paths)
        self.refresh_changes_from_git()

    def _handle_unstage_all(self) -> None:
        if self._git_service is None or not self._staged_paths:
            return
        self._git_service.unstage_all()
        self.refresh_changes_from_git()

    def _handle_commit_staged(self) -> None:
        if self._git_service is None or not self._staged_paths:
            return
        message = self.commit_message().strip()
        if not message:
            self._maybe_seed_commit_message()
            message = self.commit_message().strip()
        if not message:
            return
        self._git_service.commit(message)
        self.refresh_changes_from_git()

    def _handle_commit_all(self) -> None:
        if self._git_service is None:
            return
        message = self.commit_message().strip()
        if not message:
            self._maybe_seed_commit_message()
            message = self.commit_message().strip()
        if not message:
            return
        self._git_service.commit_all(message)
        self.refresh_changes_from_git()

    def _handle_load_diff(self) -> None:
        if self._git_service is None:
            return
        rel_path = self._selected_single_path()
        if rel_path is None:
            self.set_diff_text("Select a single file to view diff")
            return
        status_code = self._status_codes_by_path.get(rel_path, "")
        if status_code in {"U", "D"}:
            self.set_diff_text(f"No diff needed for {status_code} entries")
            return
        staged = rel_path in self._staged_paths and rel_path not in self._unstaged_paths
        diff_text = self._git_service.diff_file(rel_path, staged=staged)
        self.set_diff_text(diff_text or "No diff available")

    def _handle_revert_selected(self) -> None:
        if self._version_control is None:
            return
        selected_paths = self._selected_paths()
        if not selected_paths:
            return
        report = self._version_control.preview_revert(selected_paths)
        if report.is_empty() and not report.related_files:
            self._version_control.revert_files(selected_paths)
            if self._session is not None:
                self._session.load()
            self.refresh_changes_from_git()
            return
        include_related = QCheckBox(
            f"Also revert {len(report.related_files)} related file(s)", self)
        include_related.setChecked(bool(report.related_files))
        dialog = QImpactConfirmDialog(
            title="Confirm revert",
            message=(
                "This revert may affect related knowledge objects. "
                "Review the impact list below before proceeding."
            ),
            report=report,
            apply_label="Revert selected",
            extra_widget=include_related,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._version_control.revert_files(
            selected_paths,
            include_related=include_related.isChecked(),
        )
        if self._session is not None:
            self._session.load()
        self.refresh_changes_from_git()

    def _handle_stage_dependencies(self) -> None:
        if self._version_control is None or not self._staged_paths:
            return
        staged_paths = sorted(self._staged_paths)
        report = self._version_control.preview_stage_dependencies(staged_paths)
        if report.is_empty():
            QMessageBox.information(
                self,
                "No dependencies",
                "The staged items have no unstaged changed dependencies.",
            )
            return
        # Show a preview dialog with the unstaged candidates
        from lks_utils.knowledge.impact_entry import ImpactEntry
        entries = [
            ImpactEntry(
                object_id=obj_id,
                object_kind="node",  # simplified for now
                reason=reason,
            )
            for rel_path, (obj_id, reason) in report.unstaged_candidates.items()
        ]
        from lks_utils.knowledge.version_control.revert_impact_report import (
            RevertImpactReport,
        )
        preview_report = RevertImpactReport(
            entries=entries,
            related_files=set(report.unstaged_candidates.keys()),
            include_related=False,
        )
        dialog = QImpactConfirmDialog(
            title="Stage dependencies",
            message=(
                "The following changed items are dependencies of staged items. "
                "Stage them to ensure references are complete?"
            ),
            report=preview_report,
            apply_label="Stage dependencies",
            extra_widget=None,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        paths_to_stage = sorted(report.unstaged_candidates.keys())
        self._git_service.stage(paths_to_stage)
        self.refresh_changes_from_git()
        self._maybe_seed_commit_message()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(self._empty_label)
        root.addWidget(self._status_label)
        root.addWidget(self._shelf_banner)

        splitter = QSplitter(self)
        splitter.addWidget(self._file_list)

        staged_panel = QWidget(splitter)
        staged_layout = QVBoxLayout(staged_panel)
        staged_layout.setContentsMargins(0, 0, 0, 0)
        staged_layout.setSpacing(6)
        staged_layout.addWidget(self._staged_label)
        staged_layout.addWidget(self._staged_list, stretch=1)
        splitter.addWidget(staged_panel)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        diff_actions = QHBoxLayout()
        diff_actions.setContentsMargins(0, 0, 0, 0)
        diff_actions.addStretch(1)
        diff_actions.addWidget(self._load_diff_btn)
        right_layout.addLayout(diff_actions)
        right_layout.addWidget(self._diff_view, stretch=3)
        right_layout.addWidget(self._commit_message, stretch=2)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 3)
        root.addWidget(splitter, stretch=1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(self._stage_btn)
        actions.addWidget(self._stage_all_btn)
        actions.addWidget(self._stage_deps_btn)
        actions.addWidget(self._unstage_btn)
        actions.addWidget(self._unstage_all_btn)
        actions.addWidget(self._revert_btn)
        actions.addStretch(1)
        actions.addWidget(self._commit_staged_btn)
        actions.addWidget(self._commit_all_btn)
        root.addLayout(actions)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            (
                f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
                f"QPushButton {{ color: {FIELD_BUTTON_TEXT}; }}"
            )
        )


__all__ = ["QGitChangesTab"]

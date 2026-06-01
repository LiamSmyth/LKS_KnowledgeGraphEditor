"""Abstract base class for reusable Qt field widgets."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedLayout, QWidget

from lks_utils.gui_qt.components.fields.field_commit_policy import FieldCommitPolicy
from lks_utils.gui_qt.components.fields.field_commit_reason import FieldCommitReason
from lks_utils.gui_qt.components.fields.field_icons import get_field_revert_icon
from lks_utils.gui_qt.components.fields.field_validation_result import FieldValidationResult
from lks_utils.gui_qt.widgets.square_icon_button import QSquareIconButton


class QFieldBase(QWidget):
    """Base class for typed UI fields with consistent commit/revert behavior."""

    value_changed = Signal(object)
    commit_requested = Signal(object, object)
    committed = Signal(object, object)
    commit_rejected = Signal(object, object, str)
    reverted = Signal(object)
    active_changed = Signal(bool)
    editable_changed = Signal(bool)
    dirty_changed = Signal(bool)

    def __init__(
        self,
        default_value: Any,
        *,
        commit_policy: FieldCommitPolicy | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._commit_policy: FieldCommitPolicy = commit_policy or FieldCommitPolicy()
        self._default_value: Any = default_value
        self._current_value: Any = default_value
        self._last_good_value: Any = default_value
        self._is_active: bool = False
        self._is_editable: bool = True
        self._is_dirty: bool = False
        self._suspend_change_notifications: bool = False

        self._editor: QWidget = self._create_editor()
        self._editor.installEventFilter(self)
        self._revert_button: QSquareIconButton = QSquareIconButton(
            18, icon=get_field_revert_icon(), tooltip="Revert to default", parent=self)
        self._revert_button.clicked.connect(self._on_revert_clicked)

        self._revert_placeholder: QWidget = QWidget(self)
        self._revert_placeholder.setFixedSize(self._revert_button.sizeHint())

        self._revert_stack_host: QWidget = QWidget(self)
        self._revert_stack: QStackedLayout = QStackedLayout(
            self._revert_stack_host)
        self._revert_stack.setContentsMargins(0, 0, 0, 0)
        self._revert_stack.addWidget(self._revert_placeholder)
        self._revert_stack.addWidget(self._revert_button)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._editor, 1)
        layout.addWidget(self._revert_stack_host, 0,
                         Qt.AlignmentFlag.AlignVCenter)

        self._connect_editor_signals()
        self._write_editor_value(self._current_value)
        self._refresh_dirty_state(emit_signal=False)

    def default_value(self) -> Any:
        """Return the default value for this field."""
        return self._default_value

    def set_default_value(self, value: Any) -> None:
        """Set the field default value."""
        self._default_value = value
        self._refresh_dirty_state(emit_signal=True)

    def value(self) -> Any:
        """Return the currently displayed value."""
        return self._current_value

    def set_value(self, value: Any) -> None:
        """Set a new value and mark it as last valid state."""
        self._last_good_value = value
        self._set_editor_value(value)
        self._current_value = value
        self._refresh_dirty_state(emit_signal=True)

    def is_active(self) -> bool:
        """Return whether the field currently has focus."""
        return self._is_active

    def is_editable(self) -> bool:
        """Return whether the field can be edited."""
        return self._is_editable

    def set_editable(self, editable: bool) -> None:
        """Enable or disable editing while keeping the value visible."""
        if self._is_editable == editable:
            return
        self._is_editable = editable
        self._set_editor_editable(editable)
        self._refresh_dirty_state(emit_signal=False)
        self.editable_changed.emit(editable)

    def is_dirty(self) -> bool:
        """Return whether the current value differs from the default."""
        return self._is_dirty

    def request_commit(self, reason: FieldCommitReason) -> bool:
        """Validate and commit the current editor value."""
        candidate = self._read_editor_value()
        self.commit_requested.emit(candidate, reason)
        validation = self.validate_value(candidate)
        if not validation.is_valid:
            self._set_editor_value(self._last_good_value)
            self._current_value = self._last_good_value
            self._refresh_dirty_state(emit_signal=True)
            self.commit_rejected.emit(candidate, reason, validation.message)
            return False

        committed_value = validation.normalized_value if validation.normalized_value is not None else candidate
        self._last_good_value = committed_value
        self._set_editor_value(committed_value)
        self._current_value = committed_value
        self._refresh_dirty_state(emit_signal=True)
        self.committed.emit(committed_value, reason)
        return True

    def revert_to_default(self) -> bool:
        """Restore the default value by running it through the commit pipeline."""
        self._set_editor_value(self._default_value)
        committed = self.request_commit(FieldCommitReason.REVERT)
        if committed:
            # Commit handlers may rebuild parent UI and delete this widget.
            try:
                self.reverted.emit(self._default_value)
            except RuntimeError:
                pass
        return committed

    def validate_value(self, value: Any) -> FieldValidationResult:
        """Validate value before commit; subclasses can override."""
        return FieldValidationResult(is_valid=True)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Track focus and optional focus-out commit behavior."""
        if watched is self._editor:
            if event.type() == QEvent.Type.FocusIn:
                self._set_active(True)
            elif event.type() == QEvent.Type.FocusOut:
                self._set_active(False)
                if self._commit_policy.commit_on_focus_out:
                    self.request_commit(FieldCommitReason.FOCUS_OUT)
        return super().eventFilter(watched, event)

    def _on_editor_value_changed(self, value: Any) -> None:
        """Handle raw editor changes and apply optional auto-commit policy."""
        if self._suspend_change_notifications:
            return
        self._current_value = value
        self.value_changed.emit(value)
        self._refresh_dirty_state(emit_signal=True)
        if self._commit_policy.commit_on_changed:
            self.request_commit(FieldCommitReason.CHANGED)

    def _set_editor_value(self, value: Any) -> None:
        """Set editor value while suppressing signal loops."""
        self._suspend_change_notifications = True
        try:
            self._write_editor_value(value)
        finally:
            self._suspend_change_notifications = False

    def _on_confirm_action(self) -> None:
        """Commit current value via explicit user confirmation."""
        self.request_commit(FieldCommitReason.CONFIRM)

    def _on_revert_clicked(self) -> None:
        """Handle revert button click."""
        self.revert_to_default()

    def _set_active(self, active: bool) -> None:
        if self._is_active == active:
            return
        self._is_active = active
        self.active_changed.emit(active)

    def _refresh_dirty_state(self, *, emit_signal: bool) -> None:
        was_dirty = self._is_dirty
        self._is_dirty = self._current_value != self._default_value
        show_revert = self._is_dirty and self._is_editable
        self._revert_stack.setCurrentIndex(1 if show_revert else 0)
        self._revert_stack_host.setVisible(show_revert)
        if emit_signal and was_dirty != self._is_dirty:
            self.dirty_changed.emit(self._is_dirty)

    def _create_editor(self) -> QWidget:
        """Create the editor widget used by this field."""
        raise NotImplementedError

    def _connect_editor_signals(self) -> None:
        """Connect editor signals to base handlers."""
        raise NotImplementedError

    def _read_editor_value(self) -> Any:
        """Read and parse the current editor value."""
        raise NotImplementedError

    def _write_editor_value(self, value: Any) -> None:
        """Write a value to the editor UI."""
        raise NotImplementedError

    def _set_editor_editable(self, editable: bool) -> None:
        """Toggle editor editable state while preserving readability."""
        raise NotImplementedError

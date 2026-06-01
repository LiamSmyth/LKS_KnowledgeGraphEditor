"""SessionStateMixin — dirty-flag and confirm-discard dialog for editor GUIs.

Provides a generic "unsaved changes" guard for any editor that manages a session
(layer stack, document, project). Works as a mixin alongside any QWidget subclass.

Usage::

    class MyEditor(QWidget, SessionStateMixin):
        def __init__(self):
            super().__init__()
            # ... build UI ...

        def _on_stack_mutated(self):
            self.mark_dirty()

        def _do_new_session(self):
            self.new_session(
                clear_callback=self._clear_all_state,
                parent_widget=self,
                title="New Session",
                message="Discard current unsaved changes and start a new session?",
            )
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QMessageBox, QWidget


class SessionStateMixin:
    """Mixin that tracks a dirty flag and guards against accidental data loss.

    Intended to be used alongside ``QWidget`` in a multiple-inheritance chain::

        class MyEditor(QWidget, SessionStateMixin):
            ...

    The mixin does NOT call any methods on ``QWidget`` — it is fully standalone.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._session_dirty: bool = False

    # ------------------------------------------------------------------ #
    # Dirty flag                                                           #
    # ------------------------------------------------------------------ #

    def mark_dirty(self) -> None:
        """Mark the current session as having unsaved changes."""
        self._session_dirty = True

    def mark_clean(self) -> None:
        """Clear the dirty flag (call after save)."""
        self._session_dirty = False

    @property
    def is_dirty(self) -> bool:
        """Return ``True`` if there are unsaved changes."""
        return self._session_dirty

    # ------------------------------------------------------------------ #
    # Confirm-discard dialog                                               #
    # ------------------------------------------------------------------ #

    def confirm_discard(
        self,
        parent_widget: QWidget | None = None,
        title: str = "Unsaved Changes",
        message: str = "You have unsaved changes. Discard them and continue?",
    ) -> bool:
        """Show a confirmation dialog if the session is dirty.

        If the session is clean, returns ``True`` immediately (no dialog shown).

        Args:
            parent_widget: Widget to parent the dialog to (for correct centering).
                           Falls back to ``self`` if it is a ``QWidget``.
            title: Dialog window title.
            message: Message shown to the user.

        Returns:
            ``True`` if the user confirmed (or session was clean).
            ``False`` if the user cancelled.
        """
        if not self._session_dirty:
            return True

        parent = parent_widget
        if parent is None and isinstance(self, QWidget):
            parent = self  # type: ignore[assignment]

        reply = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Discard

    # ------------------------------------------------------------------ #
    # New session                                                          #
    # ------------------------------------------------------------------ #

    def new_session(
        self,
        clear_callback: Callable[[], None],
        parent_widget: QWidget | None = None,
        title: str = "New Session",
        message: str = "Start a new session? Unsaved changes will be lost.",
    ) -> bool:
        """Guard a "new session" action with a confirm-discard dialog.

        If :meth:`confirm_discard` returns ``True`` (user confirmed or session
        was clean), calls *clear_callback* to reset the editor state, then
        marks the session as clean.

        Args:
            clear_callback: Zero-argument callable that resets editor state.
            parent_widget: Widget to parent the dialog to.
            title: Dialog window title.
            message: Message shown to the user.

        Returns:
            ``True`` if the action proceeded (callback was called).
            ``False`` if the user cancelled.
        """
        if not self.confirm_discard(
                parent_widget=parent_widget, title=title, message=message):
            return False
        clear_callback()
        self.mark_clean()
        return True


__all__ = ["SessionStateMixin"]

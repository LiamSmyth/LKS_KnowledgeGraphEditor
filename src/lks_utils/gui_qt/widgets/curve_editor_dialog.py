"""QCurveEditorDialog — modal dialog wrapping :class:`QCurveEditorWidget`.

Usage::

    # Open editing modally and retrieve the result
    edited = QCurveEditorDialog.edit_curve(parent=self, curve=my_curve)
    if edited is not None:
        # User pressed OK — apply the edited curve
        apply(edited)
"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from lks_utils.curve import SplineCurve
from lks_utils.gui_qt.widgets.curve_editor_widget import QCurveEditorWidget


class QCurveEditorDialog(QDialog):
    """Modal dialog for interactive curve editing with OK / Cancel buttons.

    Args:
        parent:     Parent widget.
        curve:      Initial curve to edit (will be deep-copied internally).
        title:      Window / dialog title.
        monotonic:  Whether to restrict the curve to monotonic-only edits.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        curve: SplineCurve | None = None,
        title: str = "Edit Curve",
        monotonic: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(280, 320)

        layout = QVBoxLayout(self)

        # Hint label
        hint = QLabel("LMB add/move · RMB cycle type · Del remove · RMB space = menu")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(hint)

        # Curve editor
        self._editor = QCurveEditorWidget(parent=self, monotonic=monotonic)
        if curve is not None:
            self._editor.set_curve(curve.copy())
        layout.addWidget(self._editor, stretch=1)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._result: SplineCurve | None = None

    def accept(self) -> None:
        self._result = self._editor.get_curve().copy()
        super().accept()

    @property
    def result_curve(self) -> SplineCurve | None:
        """The edited curve after ``exec()`` returned, or None if cancelled."""
        return self._result

    @staticmethod
    def edit_curve(
        parent: QWidget | None = None,
        curve: SplineCurve | None = None,
        title: str = "Edit Curve",
        monotonic: bool = False,
    ) -> SplineCurve | None:
        """Open the dialog and return the edited curve, or None if cancelled.

        This is the preferred way to invoke one-shot curve editing::

            edited = QCurveEditorDialog.edit_curve(parent=self,
                                                   curve=current_curve,
                                                   monotonic=True)

        Args:
            parent:    Parent widget for the dialog.
            curve:     Starting curve (copied; original is not mutated).
            title:     Dialog window title.
            monotonic: Use a monotonic-constrained editor.

        Returns:
            The edited :class:`SplineCurve`, or ``None`` if the user cancelled.
        """
        dialog = QCurveEditorDialog(
            parent=parent, curve=curve, title=title, monotonic=monotonic
        )
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            return dialog.result_curve
        return None


__all__ = ["QCurveEditorDialog"]

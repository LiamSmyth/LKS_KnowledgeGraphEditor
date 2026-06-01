"""Validation status badge widget for list rows."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QStyle, QWidget

if TYPE_CHECKING:
    from lks_utils.knowledge.validation_status import ValidationStatus
    from lks_utils.theme import Theme


class QValidationBadge(QLabel):
    """
    Small widget that displays validation status for a list row.

    States:
    - Valid: Renders nothing (zero pixels) or fixed placeholder
    - Invalid: Renders warning triangle icon (16px) in validation_invalid color

    Hover tooltip shows first N reasons from ValidationStatus.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize validation badge widget."""
        super().__init__(parent)
        self._status: ValidationStatus | None = None
        self.setAlignment(Qt.AlignCenter)
        # Fixed size based on theme metric (16px default)
        self.setFixedSize(16, 16)

    def set_status(self, status: ValidationStatus) -> None:
        """Update the badge display based on validation status.

        Args:
            status: ValidationStatus to display (valid or invalid)
        """
        self._status = status
        self._update_display()

    def clear(self) -> None:
        """Clear the badge (equivalent to setting valid status)."""
        self._status = None
        self._update_display()

    def _update_display(self) -> None:
        """Update the visual display based on current status."""
        if self._status is None or self._status.is_valid:
            # Valid state: hide badge so rows do not reserve empty badge width.
            self.setPixmap(QPixmap())  # Clear pixmap
            self.setToolTip("")
            self.hide()
            return

        # Invalid state: render warning triangle icon
        self.show()
        self._render_warning_icon()
        self._update_tooltip()

    def _render_warning_icon(self) -> None:
        """Render a warning triangle icon."""
        icon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)
        self.setPixmap(icon.pixmap(16, 16))

    def _update_tooltip(self) -> None:
        """Update tooltip with validation reasons."""
        if self._status is None or self._status.is_valid:
            self.setToolTip("")
            return

        # Collect reasons from status
        reasons = self._status.reasons if hasattr(
            self._status, "reasons") else []

        if not reasons:
            self.setToolTip("Invalid (no reasons)")
            return

        # Truncate to 5 reasons and append "(+M more)" if needed
        max_reasons = 5
        displayed_reasons = reasons[:max_reasons]
        tooltip_lines = [f"- {reason}" for reason in displayed_reasons]

        if len(reasons) > max_reasons:
            remaining = len(reasons) - max_reasons
            tooltip_lines.append(f"(+{remaining} more)")

        tooltip = "\n".join(tooltip_lines)
        self.setToolTip(tooltip)

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme colors to the badge.

        Args:
            theme: Theme object with validation_invalid color
        """
        # Store theme reference for use in rendering
        # Update display to apply new colors
        self._update_display()

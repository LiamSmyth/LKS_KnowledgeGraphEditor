"""Generic blast-radius confirmation dialog for impact reports."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.q_dialog_scaffold_base import QDialogScaffoldBase

from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    FIELD_BUTTON_BG,
    FIELD_BUTTON_BORDER,
    FIELD_BUTTON_PRESSED_BG,
    FIELD_BUTTON_TEXT,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.impact_report import ImpactReport


class QImpactConfirmDialog(QDialogScaffoldBase):
    """Show an ImpactReport and ask user to apply or cancel."""

    def __init__(
        self,
        *,
        title: str,
        message: str,
        report: ImpactReport,
        apply_label: str = "Apply anyway",
        extra_widget: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent=parent)
        self._report = report

        header = QLabel(message, self)
        header.setTextFormat(Qt.TextFormat.RichText)

        count_label = QLabel(
            f"Impacted objects: <b>{len(report.entries)}</b>", self
        )
        count_label.setTextFormat(Qt.TextFormat.RichText)

        self._impact_list = QListWidget(self)
        self._impact_list.setMaximumHeight(220)
        self._impact_list.setVisible(not report.is_empty())
        for entry in report.entries:
            text = f"{entry.object_kind}: {entry.object_id}  --  {entry.reason}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry.object_id)
            self._impact_list.addItem(item)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(header)
        content_layout.addWidget(count_label)
        if not report.is_empty():
            content_layout.addWidget(self._impact_list)
        if extra_widget is not None:
            content_layout.addWidget(extra_widget)
        self.set_content(content)

        self._cancel_btn = self.add_footer_button(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self._apply_btn = self.add_footer_button(
            apply_label, QDialogButtonBox.ButtonRole.AcceptRole)

        self.setMinimumWidth(640)
        self._apply_styles()

    def _apply_styles(self) -> None:
        apply_style = (
            f"color: {VALIDATION_ERROR_TEXT};"
            f"border: 1px solid {VALIDATION_ERROR_TEXT};"
            f"background: {FIELD_BUTTON_BG};"
        )
        cancel_style = (
            f"color: {FIELD_BUTTON_TEXT};"
            f"border: 1px solid {FIELD_BUTTON_BORDER};"
            f"background: {FIELD_BUTTON_BG};"
        )
        self._apply_btn.setStyleSheet(apply_style)
        self._cancel_btn.setStyleSheet(cancel_style)
        self.setStyleSheet(
            f"QDialog {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QListWidget {{ background: {SCENE_BACKGROUND_COLOR}; border: 1px solid {EDGE_COLOR}; }}"
            f"QPushButton:hover {{ background: {FIELD_BUTTON_PRESSED_BG}; }}"
        )


__all__ = ["QImpactConfirmDialog"]

"""Private theme/style application helpers for the workbench shell."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    FIELD_BUTTON_BG,
    FIELD_BUTTON_BORDER,
    FIELD_BUTTON_DISABLED_BORDER,
    FIELD_BUTTON_DISABLED_TEXT,
    FIELD_BUTTON_HOVER_BORDER,
    FIELD_BUTTON_PRESSED_BG,
    FIELD_BUTTON_PRESSED_BORDER,
    FIELD_BUTTON_TEXT,
    FIELD_MONO_FONT_FAMILY,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
)

if TYPE_CHECKING:
    from lks_utils.knowledge.ui.components.workbench import QKnowledgeWorkbenchWidget


def apply_styles(workbench: QKnowledgeWorkbenchWidget) -> None:
    workbench.setStyleSheet(
        f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR};"
        f" font-family: '{FIELD_MONO_FONT_FAMILY}'; }}"
        f"QTabWidget::pane {{ border: 1px solid {EDGE_COLOR}; }}"
        f"QTabBar::tab {{ background: #2d2d2d; color: {NODE_TEXT_COLOR};"
        f" border: 1px solid {EDGE_COLOR}; padding: 6px 16px; min-height: 24px; }}"
        f"QTabBar::tab:selected {{ background: #1e1e1e; }}"
        f"QPushButton {{ background: {FIELD_BUTTON_BG}; color: {FIELD_BUTTON_TEXT};"
        f" border: 1px solid {FIELD_BUTTON_BORDER}; border-radius: 0;"
        " padding: 2px 8px; min-height: 22px; }"
        f"QPushButton:hover {{ border: 1px solid {FIELD_BUTTON_HOVER_BORDER}; }}"
        f"QPushButton:pressed {{ background: {FIELD_BUTTON_PRESSED_BG}; border: 1px solid {FIELD_BUTTON_PRESSED_BORDER}; }}"
        f"QPushButton:disabled {{ color: {FIELD_BUTTON_DISABLED_TEXT}; border: 1px solid {FIELD_BUTTON_DISABLED_BORDER}; }}"
        "QLabel#knowledge_status_label { padding: 2px 8px; }"
    )

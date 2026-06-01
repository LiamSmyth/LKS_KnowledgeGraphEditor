"""Sub-header helper - Small section header for subdividing sections.

Provides a convenience function to create small sub-section headers.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


def create_sub_header(text: str) -> QLabel:
    """Create a styled sub-section header label.

    Args:
        text: Header text

    Returns:
        QLabel styled as a sub-header

    Example:
        layout.addWidget(create_sub_header("Section Name"))
    """
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #b0c4de; font-size: 9px; font-weight: bold;"
    )
    return lbl

"""
Dark theme stylesheet for PySide6 GUIs.

Provides a consistent dark theme matching ttkbootstrap "darkly" for
visual parity with existing tkinter GUIs.
"""

from __future__ import annotations
import sys
# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        # Try apartment-threaded mode first for clipboard compatibility
        ctypes.windll.ole32.CoInitializeEx(
            None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass


from PySide6.QtWidgets import QApplication

from lks_utils.gui_qt.theme.colors import COLORS

DARK_QSS = """
QWidget {
    background-color: %(bg)s;
    color: %(fg)s;
    font-family: 'Segoe UI', sans-serif;
    font-size: 10pt;
}

QPushButton {
    background-color: %(primary)s;
    border: 1px solid %(border)s;
    border-radius: 4px;
    padding: 6px 16px;
    min-width: 80px;
}

QPushButton:hover {
    background-color: %(primary_hover)s;
}

QPushButton:pressed {
    background-color: %(primary_pressed)s;
}

QPushButton:disabled {
    background-color: %(secondary)s;
    color: %(disabled_fg)s;
}

QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: %(input_bg)s;
    border: 1px solid %(border)s;
    border-radius: 4px;
    padding: 4px 8px;
    padding-right: 26px;
}

QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid %(primary)s;
}

QLineEdit:disabled, QTextEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background-color: %(secondary)s;
    color: %(disabled_fg)s;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid %(border)s;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
    background-color: %(secondary)s;
}

QComboBox::down-arrow {
    width: 10px;
    height: 10px;
}

QComboBox QAbstractItemView {
    background-color: %(input_bg)s;
    color: %(fg)s;
    selection-background-color: %(primary)s;
    selection-color: %(fg)s;
    border: 1px solid %(border)s;
}

/* Some styles can host combo popups in a top-level view/frame rather than
   a child selector target. Force opaque list/dropdown popups globally. */
QAbstractItemView {
    background-color: %(input_bg)s;
    color: %(fg)s;
    border: 1px solid %(border)s;
    selection-background-color: %(primary)s;
    selection-color: %(fg)s;
}

QListView {
    background-color: %(input_bg)s;
    color: %(fg)s;
    border: 1px solid %(border)s;
}

QSpinBox, QDoubleSpinBox {
    background-color: %(input_bg)s;
    border: 1px solid %(border)s;
    border-radius: 4px;
    padding: 4px 8px;
    color: %(fg)s;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid %(primary)s;
}

QProgressBar {
    background-color: %(secondary)s;
    border: 1px solid %(border)s;
    border-radius: 4px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: %(success)s;
    border-radius: 3px;
}

QGroupBox {
    border: 1px solid %(border)s;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}

QTabWidget::pane {
    border: 1px solid %(border)s;
    border-radius: 4px;
    background-color: %(bg)s;
}

QTabBar::tab {
    background-color: %(secondary)s;
    border: 1px solid %(border)s;
    padding: 8px 16px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: %(primary)s;
}

QTabBar::tab:hover {
    background-color: %(primary_hover)s;
}

QScrollBar:vertical {
    background: %(scrollbar_bg)s;
    width: 12px;
    border: none;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: %(scrollbar_handle)s;
    border-radius: 6px;
    min-height: 20px;
    margin: 0px;
}

QScrollBar::handle:vertical:hover {
    background: %(scrollbar_handle_hover)s;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: %(scrollbar_bg)s;
}

QScrollBar:horizontal {
    background: %(scrollbar_bg)s;
    height: 12px;
    border: none;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: %(scrollbar_handle)s;
    border-radius: 6px;
    min-width: 20px;
    margin: 0px;
}

QScrollBar::handle:horizontal:hover {
    background: %(scrollbar_handle_hover)s;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: none;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: %(scrollbar_bg)s;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid %(border)s;
    border-radius: 3px;
    background-color: %(input_bg)s;
}

QCheckBox::indicator:checked {
    background-color: %(primary)s;
    border-color: %(primary)s;
}

QCheckBox::indicator:hover {
    border-color: %(primary)s;
}

QRadioButton {
    spacing: 8px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid %(border)s;
    border-radius: 8px;
    background-color: %(input_bg)s;
}

QRadioButton::indicator:checked {
    background-color: %(primary)s;
    border-color: %(primary)s;
}

QRadioButton::indicator:hover {
    border-color: %(primary)s;
}

QLabel {
    background-color: transparent;
}

QFrame {
    background-color: transparent;
}

QFrame[frameShape="4"], QFrame[frameShape="5"] {
    background-color: %(border)s;
    max-height: 1px;
}

QTableWidget, QTreeWidget {
    background-color: %(input_bg)s;
    alternate-background-color: %(secondary)s;
    color: %(fg)s;
    border: 1px solid %(border)s;
    gridline-color: %(border)s;
    selection-background-color: %(primary)s;
    selection-color: %(fg)s;
}

QTableWidget::item, QTreeWidget::item {
    color: %(fg)s;
    padding: 6px 4px;  /* Increased vertical padding from 4px to 6px to prevent text clipping */
}

QTableWidget::item:alternate, QTreeWidget::item:alternate {
    background-color: %(secondary)s;
    color: %(fg)s;
}

QTableWidget::item:selected, QTreeWidget::item:selected {
    background-color: %(primary)s;
    color: %(fg)s;
}

QHeaderView::section {
    background-color: %(secondary)s;
    color: %(fg)s;
    border: 1px solid %(border)s;
    padding: 4px 8px;
}

QMenu {
    background-color: %(bg)s;
    border: 1px solid %(border)s;
}

QMenu::item {
    padding: 4px 24px 4px 8px;
}

QMenu::item:selected {
    background-color: %(primary)s;
}

QToolTip {
    background-color: %(dark)s;
    border: 1px solid %(border)s;
    color: %(fg)s;
    padding: 4px;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}
""" % COLORS


_DARK_THEME_SENTINEL = "_lks_dark_theme_applied"


def apply_dark_theme(app: QApplication) -> None:
    """
    Apply dark theme stylesheet to the application.

    Idempotent: subsequent calls on the same QApplication instance are no-ops,
    preventing repeated setStyleSheet() calls that can crash Qt on Windows when
    called many times across a test session.

    Args:
        app: QApplication instance to style

    Example:
        >>> app = QApplication(sys.argv)
        >>> apply_dark_theme(app)
        >>> window = MyMainWindow()
        >>> window.show()
        >>> sys.exit(app.exec())
    """
    if getattr(app, _DARK_THEME_SENTINEL, False):
        return
    setattr(app, _DARK_THEME_SENTINEL, True)
    app.setStyleSheet(DARK_QSS)


__all__ = ["DARK_QSS", "apply_dark_theme"]

"""
PySide6 GUI components for lks_utils.

This module provides Qt-based equivalents of the tkinter components
in lks_utils.gui. Both packages maintain API compatibility.
"""

from __future__ import annotations

import platform
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

from lks_utils.gui_qt.base import QAsyncTaskRunner, QConfigUIBase, QDualModeWidget, QGUIStateMixin, SessionStateMixin, TaskProgress, WorkerThread
from lks_utils.gui_qt.test_runner import run_qt_gui_test, is_interactive_mode, DEFAULT_GUI_TEST_TIMEOUT
from lks_utils.gui_qt.components import (
    ProgressLevel,
    QActivityLogComponent,
    QCompositeRuleBuilder,
    QDualProgressComponent,
    QExecutablePathComponent,
    QFileSourceSelectorComponent,
    QGridPanel,
    QLabeledSpinboxComponent,
    QCompactLibraryComponent,
    QLibraryComponent,
    QMapEditorComponent,
    QMultiLevelProgressComponent,
    QOutputDirComponent,
    QPathSelectorComponent,
    QPatternBuilderComponent,
    QResultsDisplayComponent,
    QRowFilterComponent,
    QScrollableContainer,
    QScrollablePage,
)
from lks_utils.gui_qt.theme import COLORS, apply_dark_theme
from lks_utils.gui_qt.widgets import (
    QCollapsibleBar, QCollapsiblePanel, QCollapsibleSection, QCompactButton,
    QFloatSliderSpinBox,
    QPropertyListDisplayWidget,
    QPropertyTableWidget, QScrollableTab, QColoredLogWidget, add_tooltip,
    QCurveEditorWidget, QCurveEditorDialog, QConfigUIDialog,
    QMarkdownHighlighter, QMarkdownViewerWidget,
)

from lks_utils.gui_qt.qt_paint_profile_mixin import QtPaintProfileMixin

__all__ = [
    # Base classes
    "QGUIStateMixin",
    "SessionStateMixin",
    "WorkerThread",
    "TaskProgress",
    "QAsyncTaskRunner",
    "QConfigUIBase",
    "QDualModeWidget",
    # Profiling mixins
    "QtPaintProfileMixin",
    # Application
    "create_qt_app",
    # Test utilities
    "run_qt_gui_test",
    "is_interactive_mode",
    "DEFAULT_GUI_TEST_TIMEOUT",
    # Theme
    "COLORS",
    "apply_dark_theme",
    # Widgets
    "QCollapsibleBar",
    "QCollapsiblePanel",
    "QCollapsibleSection",
    "QCompactButton",
    "QFloatSliderSpinBox",
    "QPropertyListDisplayWidget",
    "QPropertyTableWidget",
    "QScrollableTab",
    "QColoredLogWidget",
    "add_tooltip",
    "QCurveEditorWidget",
    "QCurveEditorDialog",
    "QConfigUIDialog",
    "QMarkdownHighlighter",
    "QMarkdownViewerWidget",
    # Components
    "ProgressLevel",
    "QActivityLogComponent",
    "QCompositeRuleBuilder",
    "QDualProgressComponent",
    "QExecutablePathComponent",
    "QFileSourceSelectorComponent",
    "QGridPanel",
    "QLabeledSpinboxComponent",
    "QCompactLibraryComponent",
    "QLibraryComponent",
    "QMapEditorComponent",
    "QMultiLevelProgressComponent",
    "QOutputDirComponent",
    "QPathSelectorComponent",
    "QPatternBuilderComponent",
    "QResultsDisplayComponent",
    "QRowFilterComponent",
    "QScrollableContainer",
    "QScrollablePage",
]


def create_qt_app(argv: list[str] | None = None) -> "QApplication":
    """
    Create a QApplication with proper initialization for all platforms.

    Note: On Windows, COM must be initialized BEFORE importing PySide6 for proper
    clipboard support. Add this at the very top of your main script (after docstring
    but before PySide6 imports):

        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
            except Exception:
                pass

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        Initialized QApplication instance.

    Example:
        >>> # At top of file, before PySide6 imports:
        >>> if sys.platform == "win32":
        ...     import ctypes
        ...     ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        >>> 
        >>> from lks_utils.gui_qt import create_qt_app, apply_dark_theme
        >>> def main():
        ...     app = create_qt_app()
        ...     apply_dark_theme(app)
        ...     window = MyWindow()
        ...     window.show()
        ...     sys.exit(app.exec())
    """
    from PySide6 import QtCore, QtWidgets

    # Create application with provided or default arguments
    if argv is None:
        argv = sys.argv

    app = QtWidgets.QApplication(argv)

    # Suppress the Qt 6 "QFont::setPointSize: Point size <= 0 (-1)" warning.
    # Root cause: widgets styled with CSS `font-size: Xpx` store the font with
    # pixelSize only (pointSize == -1).  Qt's internal style machinery then tries
    # to copy that font via setPointSize(-1), which is harmless but noisy.
    # Installing a message handler lets us silently drop just this one warning
    # while leaving all other Qt messages intact.
    _orig_handler: QtCore.QtMessageHandler | None = None

    def _qt_message_filter(
        mode: QtCore.QtMsgType,
        context: QtCore.QMessageLogContext,
        message: str,
    ) -> None:
        if (
            mode == QtCore.QtMsgType.QtWarningMsg
            and "QFont::setPointSize" in message
            and "Point size <= 0" in message
        ):
            return
        if _orig_handler is not None:
            _orig_handler(mode, context, message)

    _orig_handler = QtCore.qInstallMessageHandler(_qt_message_filter)

    return app

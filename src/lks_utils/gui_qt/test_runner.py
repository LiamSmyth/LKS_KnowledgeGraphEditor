"""Qt GUI test runner utilities.

Provides auto-closing test window functionality for PySide6/PyQt6 GUIs,
similar to lks_utils.gui.test_runner for tkinter.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING

try:
    from PySide6.QtCore import QTimer
except Exception:
    QTimer = None

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

DEFAULT_GUI_TEST_TIMEOUT: int = 5  # seconds


def is_interactive_mode() -> bool:
    """Check if GUI tests should run in interactive mode (no auto-close).

    Interactive mode is enabled by:
    - Command line flag: --interactive
    - Environment variable: GUI_TEST_INTERACTIVE=1

    Returns:
        True if interactive mode is enabled.
    """
    # Check command line
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--interactive", action="store_true")
    args, _ = parser.parse_known_args()
    if args.interactive:
        return True

    # Check environment variable
    env_val: str = os.environ.get("GUI_TEST_INTERACTIVE", "").strip().lower()
    return env_val in ("1", "true", "yes")


def run_qt_gui_test(
    app: "QApplication",
    timeout_seconds: int = DEFAULT_GUI_TEST_TIMEOUT,
) -> None:
    """Run a Qt GUI test application with optional auto-close timeout.

    By default, the application will auto-close after `timeout_seconds` to prevent
    hanging during automated testing. Use `--interactive` flag or set
    `GUI_TEST_INTERACTIVE=1` environment variable to disable auto-close.

    Args:
        app: The Qt QApplication instance.
        timeout_seconds: Seconds before auto-close (default: 10). Ignored in interactive mode.

    Example:
        app = QApplication(sys.argv)
        window = MyTestWindow()
        window.show()
        run_qt_gui_test(app)  # Auto-closes after 10s unless --interactive

        # With custom timeout:
        run_qt_gui_test(app, timeout_seconds=30)
    """
    qt_timer = QTimer
    if qt_timer is None:
        from PySide6.QtCore import QTimer as qt_timer

    if is_interactive_mode():
        # Interactive mode: run normally without timeout
        sys.exit(app.exec())
    else:
        # Automated mode: schedule auto-close
        def _auto_close() -> None:
            try:
                app.quit()
            except Exception:
                pass  # App may already be closed

        # Schedule the auto-close
        qt_timer.singleShot(timeout_seconds * 1000, _auto_close)

        # Print message so test output shows what's happening
        print(
            f"[Qt GUI Test] Auto-closing in {timeout_seconds}s (use --interactive to disable)")

        # Run the app
        app.exec()

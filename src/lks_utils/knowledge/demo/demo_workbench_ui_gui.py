"""Standalone demo for the embeddable knowledge workbench widget."""
from __future__ import annotations

import sys

if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except Exception:
        pass

from PySide6.QtWidgets import QMainWindow

from lks_utils.gui_qt import apply_dark_theme, create_qt_app
from lks_utils.knowledge.ui.components.workbench import QKnowledgeWorkbenchWidget


def main() -> None:
    app = create_qt_app()
    apply_dark_theme(app)

    window = QMainWindow()
    window.setWindowTitle("Knowledge Workbench MVP")
    window.resize(1480, 900)
    workbench = QKnowledgeWorkbenchWidget()
    window.setCentralWidget(workbench)
    window.show()
    workbench.restore_ui_state()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

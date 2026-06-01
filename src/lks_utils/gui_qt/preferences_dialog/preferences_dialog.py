"""QPreferencesDialog — tabbed preferences dialog (Theme + Bindings)."""
from __future__ import annotations

from collections.abc import Sequence

from lks_utils.gui_qt.theme_editor.theme_editor_widget import QThemeEditorWidget
from lks_utils.gui_qt.bindings_editor.bindings_editor_widget import QBindingsEditorWidget
from lks_utils.gui_qt.base import QGUIStateMixin

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QPushButton,
    QWidget,
)
from PySide6.QtCore import Qt


class QPreferencesDialog(QDialog, QGUIStateMixin):
    """Modal preferences dialog with Theme and Bindings tabs.

    Both editors apply changes in real-time via their respective
    singletons (``QThemeProvider`` / ``QInputBindingsProvider``).
    """

    def __init__(
        self,
        parent=None,
        *,
        extra_tabs: Sequence[tuple[str, QWidget]] | None = None,
        state_key: str = "preferences_dialog",
        state_org: str = "lks_utils",
        state_settings_path: str | None = None,
        state_format: str = "registry",
    ) -> None:
        super().__init__(parent=parent)
        QGUIStateMixin.__init__(self)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(800, 600)
        self.setModal(False)  # allow interaction with main window

        self._build_ui(extra_tabs=extra_tabs)
        self._tabs.currentChanged.connect(lambda _: self._save_state())
        self._init_state(
            state_key,
            org=state_org,
            settings_path=state_settings_path,
            format=state_format,
        )

    # ------------------------------------------------------------------

    def _build_ui(self, *, extra_tabs: Sequence[tuple[str, QWidget]] | None = None) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._tabs = QTabWidget()

        self._theme_editor = QThemeEditorWidget()
        self._tabs.addTab(self._theme_editor, "Theme")

        self._bindings_editor = QBindingsEditorWidget()
        self._tabs.addTab(self._bindings_editor, "Bindings")

        for label, widget in extra_tabs or ():
            self._tabs.addTab(widget, label)

        root.addWidget(self._tabs, stretch=1)

        # Close button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setDefault(True)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _get_state_fields(self) -> dict:
        return {
            "tab": self._tabs.currentIndex(),
            "width": self.width(),
            "height": self.height(),
        }

    def _set_state_fields(self, state: dict) -> None:
        w = state.get("width")
        h = state.get("height")
        if w and h:
            self.resize(w, h)
        tab = state.get("tab", 0)
        self._tabs.setCurrentIndex(tab)

    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._save_state()

    def theme_editor(self) -> QThemeEditorWidget:
        return self._theme_editor

    def bindings_editor(self) -> QBindingsEditorWidget:
        return self._bindings_editor


__all__ = ["QPreferencesDialog"]

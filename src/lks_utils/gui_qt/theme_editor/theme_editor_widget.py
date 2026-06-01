"""QThemeEditorWidget — tabbed editor for Theme dataclasses."""
from __future__ import annotations

import dataclasses
import json

from pathlib import Path

from lks_utils.theme.theme import Theme
from lks_utils.theme.theme_registry import ThemeRegistry
from lks_utils.theme.theme_io import builtin_themes, load_theme, save_theme
from lks_utils.gui_qt.theme.theme_provider import QThemeProvider
from lks_utils.gui_qt.base import QGUIStateMixin
from lks_utils.gui_qt.theme_editor.palette_section import QPaletteSection
from lks_utils.gui_qt.theme_editor.metrics_section import QMetricsSection
from lks_utils.gui_qt.theme_editor.typography_section import QTypographySection
from lks_utils.gui_qt.theme_editor.extension_section import QExtensionSection
from lks_utils.gui_qt.theme_editor.theme_preview_widget import QThemePreviewWidget

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QComboBox,
    QPushButton,
    QCheckBox,
    QLabel,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QSizePolicy,
    QFrame,
)
from PySide6.QtCore import Signal, Qt


class QThemeEditorWidget(QWidget, QGUIStateMixin):
    """Full reflective editor for a ``Theme``.

    Toolbar: theme selector, New/Duplicate/Delete, Save/Load, Set Active.
    Tabs: Palette | Metrics | Typography.
    Footer: live preview widget.

    Emits ``theme_changed`` when the in-progress theme is modified.
    """

    theme_changed = Signal(object)  # Theme

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        state_key: str = "theme_editor_widget",
        state_org: str = "lks_utils",
        state_settings_path: str | None = None,
        state_format: str = "registry",
    ) -> None:
        QWidget.__init__(self, parent=parent)
        QGUIStateMixin.__init__(self)

        self._provider = QThemeProvider.instance()
        self._registry = self._provider.registry()
        self._current_theme: Theme = self._provider.current()
        self._live_preview = True

        self._build_ui()
        self._populate_theme_selector()
        self._load_theme_into_editor(self._current_theme)
        # Sync selector to current theme name (use userData lookup)
        idx = self._theme_selector.findData(self._current_theme.name)
        if idx < 0:
            idx = self._theme_selector.findText(self._current_theme.name)
        if idx >= 0:
            self._theme_selector.blockSignals(True)
            self._theme_selector.setCurrentIndex(idx)
            self._theme_selector.blockSignals(False)
        self._refresh_delete_button()
        self._tabs.currentChanged.connect(lambda _: self._save_state())
        self._init_state(
            state_key,
            org=state_org,
            settings_path=state_settings_path,
            format=state_format,
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addLayout(self._build_toolbar())
        root.addWidget(self._build_tabs(), stretch=1)
        root.addWidget(self._build_footer())

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(6)

        lbl = QLabel("Theme:")
        self._theme_selector = QComboBox()
        self._theme_selector.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._theme_selector.currentTextChanged.connect(
            self._on_selector_changed)

        btn_new = QPushButton("New")
        btn_new.setFixedWidth(60)
        btn_new.clicked.connect(self._new_theme)

        btn_dup = QPushButton("Dup")
        btn_dup.setFixedWidth(48)
        btn_dup.clicked.connect(self._duplicate_theme)

        btn_del = QPushButton("Delete")
        btn_del.setFixedWidth(60)
        btn_del.clicked.connect(self._delete_theme)
        self._btn_delete = btn_del

        btn_save = QPushButton("Save")
        btn_save.setFixedWidth(60)
        btn_save.clicked.connect(self._save_theme)

        btn_load = QPushButton("Load")
        btn_load.setFixedWidth(60)
        btn_load.clicked.connect(self._load_theme_from_file)

        btn_apply = QPushButton("Set Active")
        btn_apply.clicked.connect(self._set_active)

        self._live_check = QCheckBox("Live preview")
        self._live_check.setChecked(True)
        self._live_check.toggled.connect(self._on_live_toggle)

        for w in (
            lbl,
            self._theme_selector,
            btn_new,
            btn_dup,
            btn_del,
            btn_save,
            btn_load,
            btn_apply,
            self._live_check,
        ):
            bar.addWidget(w)

        return bar

    def _build_tabs(self) -> QTabWidget:
        self._tabs = QTabWidget()

        self._palette_section = QPaletteSection(self._current_theme.palette)
        self._palette_section.palette_changed.connect(
            lambda p: self._on_section_changed(palette=p)
        )

        self._metrics_section = QMetricsSection(self._current_theme.metrics)
        self._metrics_section.metrics_changed.connect(
            lambda m: self._on_section_changed(metrics=m)
        )

        self._typography_section = QTypographySection(
            self._current_theme.typography)
        self._typography_section.typography_changed.connect(
            lambda t: self._on_section_changed(typography=t)
        )

        self._extension_section = QExtensionSection(
            self._current_theme.extensions
        )
        self._extension_section.extensions_changed.connect(
            lambda e: self._on_section_changed(extensions=e)
        )

        self._tabs.addTab(self._palette_section, "Palette")
        self._tabs.addTab(self._metrics_section, "Metrics")
        self._tabs.addTab(self._typography_section, "Typography")
        self._tabs.addTab(self._extension_section, "Extensions")

        return self._tabs

    def _build_footer(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)

        footer = QWidget()
        lay = QVBoxLayout(footer)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(line)

        self._preview = QThemePreviewWidget(self._current_theme)
        lay.addWidget(self._preview)
        return footer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def theme(self) -> Theme:
        return self._current_theme

    def set_theme(self, theme: Theme) -> None:
        self._current_theme = theme
        self._load_theme_into_editor(theme)
        self._refresh_preview()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _populate_theme_selector(self) -> None:
        self._theme_selector.blockSignals(True)
        current = self._theme_selector.currentText()
        self._theme_selector.clear()
        builtin_names = {t.name for t in builtin_themes()}
        for name in sorted(self._registry.names()):
            label = f"{name} 🔒" if name in builtin_names else name
            self._theme_selector.addItem(label, userData=name)
        idx = self._theme_selector.findData(current)
        if idx < 0:
            idx = self._theme_selector.findText(current)
        if idx >= 0:
            self._theme_selector.setCurrentIndex(idx)
        self._theme_selector.blockSignals(False)
        self._refresh_delete_button()

    def _load_theme_into_editor(self, theme: Theme) -> None:
        self._palette_section.set_palette(theme.palette)
        self._metrics_section.set_metrics(theme.metrics)
        self._typography_section.set_typography(theme.typography)
        self._extension_section.set_extensions(theme.extensions)

    def _refresh_preview(self) -> None:
        self._preview.set_theme(self._current_theme)
        if self._live_preview:
            self._provider.set_current(self._current_theme)
        self.theme_changed.emit(self._current_theme)

    def _on_section_changed(
        self,
        *,
        palette=None,
        metrics=None,
        typography=None,
        extensions=None,
    ) -> None:
        kw: dict = {}
        if palette is not None:
            kw["palette"] = palette
        if metrics is not None:
            kw["metrics"] = metrics
        if typography is not None:
            kw["typography"] = typography
        if extensions is not None:
            kw["extensions"] = extensions
        self._current_theme = dataclasses.replace(self._current_theme, **kw)
        self._refresh_preview()

    def _on_selector_changed(self, name: str) -> None:
        # Use userData (actual theme name) rather than display text which may have 🔒
        actual_name = self._theme_selector.currentData() or name
        if not actual_name:
            return
        try:
            theme = self._registry.get(actual_name)
            self._current_theme = theme
            self._load_theme_into_editor(theme)
            self._refresh_preview()
            self._save_state()
        except KeyError:
            pass
        self._refresh_delete_button()

    def _refresh_delete_button(self) -> None:
        name = self._theme_selector.currentData() or self._theme_selector.currentText()
        builtin_names = {t.name for t in builtin_themes()}
        is_builtin = name in builtin_names
        self._btn_delete.setEnabled(not is_builtin)
        self._btn_delete.setToolTip(
            "Built-in themes cannot be deleted. Use 'Dup' to make a copy."
            if is_builtin else "Delete this theme"
        )

    def _on_live_toggle(self, checked: bool) -> None:
        self._live_preview = checked
        self._save_state()

    def _new_theme(self) -> None:
        name, ok = QInputDialog.getText(self, "New Theme", "Theme name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        base = self._current_theme
        new_theme = dataclasses.replace(base, name=name)
        try:
            self._registry.register(new_theme)
        except ValueError:
            QMessageBox.warning(self, "Duplicate",
                                f"Theme '{name}' already exists.")
            return
        self._populate_theme_selector()
        self._theme_selector.setCurrentText(name)

    def _duplicate_theme(self) -> None:
        base_name = self._theme_selector.currentText()
        name, ok = QInputDialog.getText(
            self, "Duplicate Theme", "New name:", text=f"{base_name}_copy"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        dup = dataclasses.replace(self._current_theme, name=name)
        try:
            self._registry.register(dup)
        except ValueError:
            QMessageBox.warning(self, "Duplicate",
                                f"Theme '{name}' already exists.")
            return
        self._populate_theme_selector()
        self._theme_selector.setCurrentText(name)

    def _delete_theme(self) -> None:
        name = self._theme_selector.currentText()
        if not name:
            return
        builtin_names = {t.name for t in builtin_themes()}
        if name in builtin_names:
            QMessageBox.warning(
                self,
                "Cannot Delete Built-in",
                f"'{name}' is a built-in theme and cannot be deleted.\n"
                "Use 'Dup' to create an editable copy.",
            )
            return
        reply = QMessageBox.question(
            self,
            "Delete Theme",
            f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.unregister(name)
        except (KeyError, AttributeError):
            pass
        self._populate_theme_selector()

    def _save_theme(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Theme",
            str(Path.home() / ".lks_utils" / "themes"),
            "Theme JSON (*.json)",
        )
        if path:
            save_theme(self._current_theme, Path(path))

    def _load_theme_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Theme",
            str(Path.home() / ".lks_utils" / "themes"),
            "Theme JSON (*.json)",
        )
        if path:
            theme = load_theme(Path(path))
            try:
                self._registry.register(theme)
            except ValueError:
                pass  # already registered; just switch to it
            self._populate_theme_selector()
            self._theme_selector.setCurrentText(theme.name)

    def _set_active(self) -> None:
        self._provider.set_current(self._current_theme)
        # Persist user preference
        app_dir = Path.home() / ".lks_utils" / "themes"
        app_dir.mkdir(parents=True, exist_ok=True)
        save_theme(self._current_theme, app_dir / "active.json")

    # ------------------------------------------------------------------
    # QGUIStateMixin implementation
    # ------------------------------------------------------------------

    def _get_state_fields(self) -> dict:
        # Use userData (actual theme name) not display text which has 🔒 suffix
        selected = self._theme_selector.currentData() or self._theme_selector.currentText()
        return {
            "selected_theme": selected,
            "active_tab": self._tabs.currentIndex(),
            "live_preview": self._live_preview,
        }

    def _set_state_fields(self, state: dict) -> None:
        if "selected_theme" in state:
            idx = self._theme_selector.findData(state["selected_theme"])
            if idx < 0:
                idx = self._theme_selector.findText(state["selected_theme"])
            if idx >= 0:
                self._theme_selector.setCurrentIndex(idx)
        if "active_tab" in state:
            self._tabs.setCurrentIndex(state["active_tab"])
        if "live_preview" in state:
            val = state["live_preview"]
            if isinstance(val, str):
                val = val.lower() not in ("false", "0", "no", "off")
            self._live_check.setChecked(bool(val))


__all__ = ["QThemeEditorWidget"]

"""Preferences widget for knowledge graph live reload behavior."""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class QKnowledgeLiveReloadPreferencesWidget(QWidget):
    """Editable settings for graph-tab external live reload scheduling."""

    def __init__(
        self,
        *,
        settings_org: str = "lks_utils",
        settings_app: str = "KnowledgeWorkbench",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_org = settings_org
        self._settings_app = settings_app

        self._enabled_checkbox = QCheckBox("Enable external live reload", self)
        self._focus_checkbox = QCheckBox(
            "Reload pending external changes on window focus", self)

        self._debounce_spin = QSpinBox(self)
        self._debounce_spin.setRange(0, 60_000)
        self._debounce_spin.setSuffix(" ms")

        self._poll_spin = QSpinBox(self)
        self._poll_spin.setRange(250, 300_000)
        self._poll_spin.setSuffix(" ms")

        self._min_gap_spin = QSpinBox(self)
        self._min_gap_spin.setRange(0, 60_000)
        self._min_gap_spin.setSuffix(" ms")

        self._build_ui()
        self._wire_signals()
        self.reload_from_settings()

    def reload_from_settings(self) -> None:
        settings = QSettings(self._settings_org, self._settings_app)
        settings.beginGroup("workbench/graph_tab")
        self._enabled_checkbox.setChecked(self._coerce_bool(
            settings.value("live_reload_enabled", True), True))
        self._focus_checkbox.setChecked(self._coerce_bool(
            settings.value("live_reload_on_focus", True), True))
        self._debounce_spin.setValue(self._coerce_int(
            settings.value("live_reload_debounce_ms", 400), 400, minimum=0))
        self._poll_spin.setValue(self._coerce_int(settings.value(
            "live_reload_poll_ms", 2000), 2000, minimum=250))
        self._min_gap_spin.setValue(self._coerce_int(
            settings.value("live_reload_min_gap_ms", 1000), 1000, minimum=0))
        settings.endGroup()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        intro = QLabel(
            "Tune how the Graph View reconciles external repo edits from agents, MCP tools, or manual file changes.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.addRow("Mode", self._enabled_checkbox)
        form.addRow("Focus Flush", self._focus_checkbox)
        form.addRow("Debounce", self._debounce_spin)
        form.addRow("Poll Interval", self._poll_spin)
        form.addRow("Minimum Reload Gap", self._min_gap_spin)
        root.addLayout(form)

        note = QLabel(
            "Watcher events only mark external changes as pending. Debounce and poll settings control when the coalesced reload actually runs.",
            self,
        )
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch(1)

    def _wire_signals(self) -> None:
        self._enabled_checkbox.toggled.connect(self._save_settings)
        self._focus_checkbox.toggled.connect(self._save_settings)
        self._debounce_spin.valueChanged.connect(self._save_settings)
        self._poll_spin.valueChanged.connect(self._save_settings)
        self._min_gap_spin.valueChanged.connect(self._save_settings)

    def _save_settings(self) -> None:
        settings = QSettings(self._settings_org, self._settings_app)
        settings.beginGroup("workbench/graph_tab")
        settings.setValue("live_reload_enabled",
                          self._enabled_checkbox.isChecked())
        settings.setValue("live_reload_on_focus",
                          self._focus_checkbox.isChecked())
        settings.setValue("live_reload_debounce_ms",
                          self._debounce_spin.value())
        settings.setValue("live_reload_poll_ms", self._poll_spin.value())
        settings.setValue("live_reload_min_gap_ms", self._min_gap_spin.value())
        settings.endGroup()

    @staticmethod
    def _coerce_bool(value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().casefold()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _coerce_int(value: object, default: int, *, minimum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, parsed)


__all__ = ["QKnowledgeLiveReloadPreferencesWidget"]

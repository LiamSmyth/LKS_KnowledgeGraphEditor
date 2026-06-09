"""Preferences widget for knowledge autosave (git-stash-based)."""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class QKnowledgeAutosavePreferencesWidget(QWidget):
    """Editable settings for knowledge repository autosave behaviour."""

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

        self._enabled_checkbox = QCheckBox(
            "Enable periodic autosave (git stash)", self
        )

        self._interval_spin = QDoubleSpinBox(self)
        self._interval_spin.setRange(0.5, 1440.0)
        self._interval_spin.setDecimals(1)
        self._interval_spin.setSingleStep(0.5)
        self._interval_spin.setSuffix(" min")

        self._max_stashes_spin = QSpinBox(self)
        self._max_stashes_spin.setRange(1, 100)
        self._max_stashes_spin.setSuffix(" stashes")

        self._build_ui()
        self._wire_signals()
        self.reload_from_settings()

    def reload_from_settings(self) -> None:
        settings = QSettings(self._settings_org, self._settings_app)
        settings.beginGroup("workbench/autosave")
        self._enabled_checkbox.setChecked(
            self._coerce_bool(settings.value("enabled", True), True))
        self._interval_spin.setValue(
            self._coerce_float(settings.value("interval_minutes", 5.0), 5.0,
                               minimum=0.5))
        self._max_stashes_spin.setValue(
            self._coerce_int(settings.value("max_stashes", 10), 10,
                             minimum=1))
        settings.endGroup()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        intro = QLabel(
            "Configure how often working changes are saved as git stashes. "
            "Each autosave creates a stash and immediately restores the "
            "working tree so your workflow is uninterrupted.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.addRow("Autosave", self._enabled_checkbox)
        form.addRow("Interval", self._interval_spin)
        form.addRow("Keep", self._max_stashes_spin)
        root.addLayout(form)

        note = QLabel(
            "Autosave stashes appear in the Revert dialog alongside the "
            "last commit, newest first. They are NOT cleared on commit — "
            "they roll off automatically when the stash limit is exceeded.",
            self,
        )
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch(1)

    def _wire_signals(self) -> None:
        self._enabled_checkbox.toggled.connect(self._save_settings)
        self._interval_spin.valueChanged.connect(self._save_settings)
        self._max_stashes_spin.valueChanged.connect(self._save_settings)

    def _save_settings(self) -> None:
        settings = QSettings(self._settings_org, self._settings_app)
        settings.beginGroup("workbench/autosave")
        settings.setValue("enabled", self._enabled_checkbox.isChecked())
        settings.setValue("interval_minutes", self._interval_spin.value())
        settings.setValue("max_stashes", self._max_stashes_spin.value())
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

    @staticmethod
    def _coerce_float(
        value: object, default: float, *, minimum: float
    ) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, parsed)


__all__ = ["QKnowledgeAutosavePreferencesWidget"]

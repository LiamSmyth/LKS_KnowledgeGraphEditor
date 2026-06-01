"""apply_theme — apply a Theme to a QApplication.

Replaces the legacy ``apply_dark_theme(app)`` function.
"""
from __future__ import annotations

from pathlib import Path

from lks_utils.theme.theme import Theme
from lks_utils.theme.theme_io import load_theme
from lks_utils.gui_qt.theme.theme_provider import QThemeProvider

from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication, theme: Theme | None = None) -> None:
    """Apply *theme* app-wide.

    If *theme* is ``None``, uses the current
    :class:`~lks_utils.gui_qt.theme.QThemeProvider` theme (which defaults to
    the built-in *dark* theme on first call).

    This sets:
    - The application :class:`QPalette`.
    - The global QSS stylesheet.
    - The ``QThemeProvider`` current theme (so all mixin widgets update).
    """
    provider = QThemeProvider.instance()

    # Allow a per-user override if a theme.json exists
    if theme is None:
        override = _find_user_override(app.applicationName())
        if override is not None:
            theme = override

    if theme is not None:
        provider.set_current(theme)

    app.setPalette(provider.qpalette())
    app.setStyleSheet(provider.qss())


def _find_user_override(app_name: str) -> Theme | None:
    """Look for ``~/.lks_utils/<app_name>/theme.json``."""
    if not app_name:
        return None
    candidate = Path.home() / ".lks_utils" / app_name / "theme.json"
    if candidate.exists():
        try:
            return load_theme(candidate)
        except Exception:
            return None
    return None


__all__ = ["apply_theme"]

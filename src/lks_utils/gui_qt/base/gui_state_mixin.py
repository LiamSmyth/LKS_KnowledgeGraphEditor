"""
GUI State Management Mixin for PySide6.

Provides standardized state persistence using QSettings.
Port of lks_utils.gui.GUIStateMixin from tkinter to Qt.
"""

from __future__ import annotations
import sys
# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        # Try apartment-threaded mode first for clipboard compatibility
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass


from typing import Any
from pathlib import Path
import json

from PySide6.QtCore import QSettings


class QGUIStateMixin:
    """
    Mixin providing automatic state persistence via QSettings.

    Replaces JSON file-based persistence from tkinter version with
    QSettings (uses Windows Registry on Windows, .ini files on Linux).

    Usage:
        class MyGUI(QWidget, QGUIStateMixin):
            def __init__(self):
                super().__init__()
                # Build UI first...
                self._init_state("my_gui")  # Call after UI setup

            def _get_state_fields(self) -> dict[str, Any]:
                return {
                    "path": self.path_input.text(),
                    "recursive": self.recursive_check.isChecked(),
                }

            def _set_state_fields(self, state: dict[str, Any]) -> None:
                self.path_input.setText(state.get("path", ""))
                self.recursive_check.setChecked(state.get("recursive", False))

            def _on_some_change(self):
                self._save_state()  # Save when UI changes

    Note:
        - Call _init_state() in __init__ AFTER building UI
        - Implement _get_state_fields() and _set_state_fields()
        - Use _loading flag to prevent saves during initialization
        - Call _save_state() when UI changes to persist state
    """

    _settings: QSettings | None = None
    _state_key: str = ""
    _loading: bool = False
    _backend: str = "registry"  # registry | ini | json
    _json_path: Path | None = None

    def _init_state(
        self,
        state_key: str,
        org: str = "lks_utils",
        settings_path: str | Path | None = None,
        format: str = "registry",
    ) -> None:
        """
        Initialize state persistence. Call in __init__ after UI setup.

        Args:
            state_key: Unique key for this GUI (e.g., "video_compressor")
            org: Organization name for QSettings (default: "lks_utils")
            settings_path: Optional file path for storing state
            format: Backend format: "registry" (default), "ini" (QSettings file), or "json"
        """
        self._state_key = state_key
        self._backend = format

        if format == "json":
            if settings_path is None:
                # Default to local ini behavior if no path provided
                self._json_path = None
            else:
                self._json_path = Path(settings_path)
                # Ensure parent exists
                try:
                    self._json_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
            # No QSettings for JSON backend
            self._settings = None
        elif settings_path is not None and format == "ini":
            # Use QSettings INI file at provided path
            ini_path = Path(settings_path)
            try:
                ini_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            self._settings = QSettings(str(ini_path), QSettings.IniFormat)
        else:
            # Default system-backed settings (Registry on Windows)
            self._settings = QSettings(org, state_key)

        self._load_state()

    def _load_state(self) -> None:
        """Load persisted state. Called automatically by _init_state()."""
        self._loading = True
        try:
            state: dict[str, Any] = {}
            if self._backend == "json" and self._json_path:
                try:
                    if self._json_path.exists():
                        with self._json_path.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                            if isinstance(data, dict):
                                state = data.get("state", data)
                        print(
                            f"[QGUIStateMixin] Loaded state from {self._json_path}")
                    else:
                        print(
                            f"[QGUIStateMixin] State file does not exist: {self._json_path}")
                except Exception as e:
                    # Log malformed JSON or read errors
                    print(
                        f"[QGUIStateMixin] Failed to load state from {self._json_path}: {e}")
                    state = {}
            elif self._settings is not None:
                self._settings.beginGroup("state")
                for key in self._settings.childKeys():
                    state[key] = self._settings.value(key)
                self._settings.endGroup()

            if state:
                self._set_state_fields(state)
                print(f"[QGUIStateMixin] Restored {len(state)} state fields")
            else:
                print(
                    "[QGUIStateMixin] No state to restore (first run or empty state)")
        except Exception as e:
            print(f"[QGUIStateMixin] Failed to restore state: {e}")
        finally:
            self._loading = False

    def _save_state(self) -> None:
        """
        Persist current state. Call when UI changes to save.

        Automatically blocked during initialization (_loading flag).
        """
        if self._loading:
            return
        try:
            state: dict[str, Any] = self._get_state_fields()
            if self._backend == "json" and self._json_path:
                try:
                    payload = {"state": state}
                    with self._json_path.open("w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    # Log save errors for debugging
                    print(
                        f"[QGUIStateMixin] Failed to save state to {self._json_path}: {e}")
            elif self._settings is not None:
                self._settings.beginGroup("state")
                for key, value in state.items():
                    self._settings.setValue(key, value)
                self._settings.endGroup()
                self._settings.sync()
        except Exception as e:
            # Log state collection errors for debugging
            print(f"[QGUIStateMixin] Failed to collect state: {e}")

    def _get_state_fields(self) -> dict[str, Any]:
        """
        Get current state as dictionary for persistence.

        Override in subclass to return all fields that should be persisted.

        Returns:
            Dictionary with field_name -> value pairs
        """
        raise NotImplementedError(
            "Subclass must implement _get_state_fields()")

    def _set_state_fields(self, state: dict[str, Any]) -> None:
        """
        Restore state from dictionary.

        Override in subclass to apply state to UI widgets.
        Should check for key existence before applying each value.

        Args:
            state: Dictionary with field_name -> value pairs
        """
        raise NotImplementedError(
            "Subclass must implement _set_state_fields()")


__all__ = ["QGUIStateMixin"]

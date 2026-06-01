"""Bindings editor widgets for the preferences dialog."""
from __future__ import annotations

from lks_utils.gui_qt.bindings_editor.key_capture_widget import QKeyCaptureWidget
from lks_utils.gui_qt.bindings_editor.mouse_capture_widget import QMouseCaptureWidget
from lks_utils.gui_qt.bindings_editor.wheel_capture_widget import QWheelCaptureWidget
from lks_utils.gui_qt.bindings_editor.action_row_widget import QActionRowWidget
from lks_utils.gui_qt.bindings_editor.bindings_editor_widget import QBindingsEditorWidget

__all__ = [
    "QKeyCaptureWidget",
    "QMouseCaptureWidget",
    "QWheelCaptureWidget",
    "QActionRowWidget",
    "QBindingsEditorWidget",
]

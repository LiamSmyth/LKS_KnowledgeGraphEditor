"""  
Executable Path Component (PySide6)

Reusable component for selecting executable paths (FFmpeg, yt-dlp, etc.)
with test button and auto-detect fallback.
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


import subprocess
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from lks_utils.gui_qt.widgets.tooltip import add_tooltip


class QExecutablePathComponent(QWidget):
    """
    Reusable component for selecting and testing executable paths.

    Provides:
    - Entry field for path
    - Browse button for file dialog
    - Test button to verify executable works
    - Status indicator showing availability
    - Auto-detect from common locations

    Signals:
        path_changed: Emitted when path changes, passes path or None
        test_completed: Emitted after test with (success: bool, message: str)

    Usage:
        exec_path = QExecutablePathComponent(
            parent,
            label="FFmpeg:",
            executable_name="ffmpeg",
            test_args=["--version"],
            fallback_dirs=["dependencies", "bin"],
            tooltip="Path to FFmpeg executable"
        )
        exec_path.path_changed.connect(lambda path: print(f"Path: {path}"))

        # Get current path (or None if empty/invalid)
        path = exec_path.get_path()

        # Check if executable is valid
        if exec_path.is_valid:
            print("Executable available!")

    State persistence:
        state = exec_path.to_dict()  # {"path": "/usr/bin/ffmpeg", "auto_detected": False}
        exec_path.from_dict(state)
    """

    path_changed = Signal(object)  # str | None
    test_completed = Signal(bool, str)  # success, message

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "Executable:",
        executable_name: str = "",
        test_args: list[str] | None = None,
        fallback_dirs: list[str | Path] | None = None,
        on_change: Callable[[str | None], None] | None = None,
        on_test_result: Callable[[bool, str], None] | None = None,
        tooltip: str = "",
        show_status: bool = True,
        file_types: list[tuple[str, str]] | None = None,
    ) -> None:
        """
        Initialize the QExecutablePathComponent.

        Args:
            parent: Parent widget
            label: Label text shown before the entry
            executable_name: Name of executable (e.g., "ffmpeg", "yt-dlp")
            test_args: Arguments to pass when testing (e.g., ["--version"])
            fallback_dirs: Directories to search for auto-detection
            on_change: Callback when path changes, receives path or None
            on_test_result: Callback with (success, message) after test
            tooltip: Tooltip text for the entry field
            show_status: Whether to show status indicator
            file_types: File types for dialog, defaults to executables
        """
        super().__init__(parent)

        self.label_text: str = label
        self.executable_name: str = executable_name
        self.test_args: list[str] = test_args or ["--version"]
        self.fallback_dirs: list[Path] = [
            Path(d) for d in (fallback_dirs or [])]
        self._on_change_callback: Callable[[
            str | None], None] | None = on_change
        self._on_test_result_callback: Callable[[
            bool, str], None] | None = on_test_result
        self.tooltip_text: str = tooltip
        self.show_status: bool = show_status
        self.file_types: list[tuple[str, str]] | None = file_types

        # State
        self._auto_detected: bool = False
        self._is_valid: bool = False
        self._last_test_message: str = ""

        # Connect signal to callback if provided
        if self._on_change_callback:
            self.path_changed.connect(self._on_change_callback)
        if self._on_test_result_callback:
            self.test_completed.connect(self._on_test_result_callback)

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the component UI."""
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.setColumnStretch(1, 1)

        row: int = 0

        # Label
        label = QLabel(self.label_text)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft)

        # Entry
        self._entry = QLineEdit()
        self._entry.textChanged.connect(self._on_path_changed)
        layout.addWidget(self._entry, row, 1)

        if self.tooltip_text:
            add_tooltip(self._entry, self.tooltip_text)

        # Button frame
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(3)

        # Browse button
        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.setFixedWidth(80)
        self._browse_btn.clicked.connect(self._browse)
        btn_layout.addWidget(self._browse_btn)
        add_tooltip(self._browse_btn,
                    f"Browse for {self.executable_name or 'executable'}")

        # Test button
        self._test_btn = QPushButton("Test")
        self._test_btn.setFixedWidth(60)
        self._test_btn.clicked.connect(self._test_executable)
        btn_layout.addWidget(self._test_btn)
        add_tooltip(self._test_btn, "Test if executable works")

        layout.addWidget(btn_frame, row, 2)

        row += 1

        # Status row (optional)
        if self.show_status:
            self._status_label = QLabel("")
            self._status_label.setStyleSheet("color: gray;")
            layout.addWidget(self._status_label, row, 0, 1,
                             3, Qt.AlignmentFlag.AlignLeft)
        else:
            self._status_label = None

    def _browse(self) -> None:
        """Open file dialog to select executable."""
        # Build filter string for Qt
        if self.file_types:
            filter_parts: list[str] = []
            for desc, pattern in self.file_types:
                filter_parts.append(f"{desc} ({pattern})")
            filter_str = ";;".join(filter_parts)
        else:
            filter_str = "Executables (*.exe);;All files (*.*)"

        initial_dir: str | None = None
        current = self._entry.text().strip()
        if current:
            path = Path(current)
            if path.parent.exists():
                initial_dir = str(path.parent)

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {self.executable_name or 'Executable'}",
            initial_dir or "",
            filter_str,
            options=QFileDialog.Option.DontUseNativeDialog,
        )

        if filepath:
            self._auto_detected = False
            self._entry.setText(filepath)

    def _on_path_changed(self, text: str) -> None:
        """Handle path text change."""
        path = text.strip()

        # Reset validity until tested
        self._is_valid = False
        self._update_status("", "gray")

        self.path_changed.emit(path if path else None)

    def _test_executable(self) -> None:
        """Test if the executable works."""
        path = self._entry.text().strip()

        # If empty, try auto-detect first
        if not path:
            detected = self._auto_detect()
            if detected:
                path = detected
                self._entry.setText(path)
                self._auto_detected = True

        if not path:
            self._set_test_result(False, "No path specified")
            return

        # Verify file exists
        if not Path(path).is_file():
            self._set_test_result(False, f"File not found: {path}")
            return

        # Try running with test args
        try:
            result = subprocess.run(
                [path] + self.test_args,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Extract version info if available
                output = result.stdout.strip() or result.stderr.strip()
                version_line = output.split("\n")[0][:60] if output else "OK"
                self._set_test_result(True, f"✓ {version_line}")
            else:
                error = result.stderr.strip(
                )[:60] if result.stderr else "Unknown error"
                self._set_test_result(False, f"✗ {error}")

        except subprocess.TimeoutExpired:
            self._set_test_result(False, "✗ Timeout (10s)")
        except FileNotFoundError:
            self._set_test_result(False, f"✗ Not found: {path}")
        except PermissionError:
            self._set_test_result(False, "✗ Permission denied")
        except Exception as e:
            self._set_test_result(False, f"✗ Error: {str(e)[:40]}")

    def _set_test_result(self, success: bool, message: str) -> None:
        """Set test result and update UI."""
        self._is_valid = success
        self._last_test_message = message

        color = "green" if success else "red"
        self._update_status(message, color)

        self.test_completed.emit(success, message)

    def _update_status(self, message: str, color: str) -> None:
        """Update status label."""
        if self._status_label:
            self._status_label.setText(message)
            self._status_label.setStyleSheet(f"color: {color};")

    def _auto_detect(self) -> str | None:
        """
        Try to auto-detect executable from fallback directories.

        Returns:
            Path to executable if found, None otherwise.
        """
        if not self.executable_name:
            return None

        # Possible executable names
        names: list[str] = [self.executable_name]
        if not self.executable_name.endswith(".exe"):
            names.append(f"{self.executable_name}.exe")

        for fallback_dir in self.fallback_dirs:
            if not fallback_dir.is_absolute():
                # Try relative to various bases
                bases = [Path.cwd(), Path(
                    __file__).parent.parent.parent.parent.parent]
                for base in bases:
                    check_dir = base / fallback_dir
                    for name in names:
                        check_path = check_dir / name
                        if check_path.is_file():
                            return str(check_path)
            else:
                for name in names:
                    check_path = fallback_dir / name
                    if check_path.is_file():
                        return str(check_path)

        return None

    # ---- Public API ----

    def get_path(self) -> str | None:
        """
        Get current path value.

        Returns:
            Path string if set, None if empty.
        """
        path = self._entry.text().strip()
        return path if path else None

    def set_path(self, path: str | None) -> None:
        """
        Set path value programmatically.

        Args:
            path: Path to set, or None to clear.
        """
        self._auto_detected = False
        self._entry.setText(path or "")

    def clear(self) -> None:
        """Clear the path."""
        self._auto_detected = False
        self._is_valid = False
        self._entry.setText("")
        self._update_status("", "gray")

    def auto_detect(self) -> bool:
        """
        Attempt auto-detection of executable.

        Returns:
            True if auto-detection succeeded.
        """
        detected = self._auto_detect()
        if detected:
            self._entry.setText(detected)
            self._auto_detected = True
            self._test_executable()
            return True
        return False

    @property
    def is_valid(self) -> bool:
        """Check if the executable has been tested and is valid."""
        return self._is_valid

    @property
    def is_auto_detected(self) -> bool:
        """Check if current path was auto-detected."""
        return self._auto_detected

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the component.

        Args:
            enabled: Whether component should be enabled.
        """
        self._entry.setEnabled(enabled)
        self._browse_btn.setEnabled(enabled)
        self._test_btn.setEnabled(enabled)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Returns:
            Dict with path and auto_detected flag.
        """
        return {
            "path": self.get_path(),
            "auto_detected": self._auto_detected,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Args:
            data: Dict with path and optional auto_detected flag.
        """
        path = data.get("path")
        self._auto_detected = data.get("auto_detected", False)
        self._entry.setText(path or "")

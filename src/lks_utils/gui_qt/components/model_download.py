"""Model download component for PySide6.

Provides a UI component for downloading models with progress tracking,
status updates, and integration with QModelStatusComponent.

Example:
    def download_ram_model(progress_callback, status_callback):
        from lks_utils.deps import download_file, get_ram_model_url
        
        url = get_ram_model_url("ram_plus")
        dest = Path("/models/ram_plus_swin_large_14m.pth")
        
        result = download_file(url, dest, progress_callback=progress_callback)
        
        if result["success"]:
            status_callback(True, "Download complete")
        else:
            status_callback(False, f"Error: {result['error']}")
    
    component = QModelDownloadComponent(
        parent=parent,
        model_name="RAM Model",
        download_callback=download_ram_model
    )
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


from typing import Callable, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QMessageBox
)
from PySide6.QtCore import Signal, Slot, QThread
from PySide6.QtGui import QFont

from lks_utils.gui_qt.base import WorkerThread


class QModelDownloadComponent(QWidget):
    """Component for downloading models with progress tracking.

    Shows a download button, progress bar, and status messages.
    Uses WorkerThread for background downloads.

    Signals:
        download_started: Emitted when download starts
        download_progress: Emitted during download (int: current, int: total)
        download_complete: Emitted when download finishes (bool: success, str: message)
    """

    download_started = Signal()
    download_progress = Signal(int, int)  # (current, total)
    download_complete = Signal(bool, str)  # (success, message)

    def __init__(
        self,
        parent: QWidget | None = None,
        model_name: str = "Model",
        download_callback: Callable[[Callable, Callable], None] | None = None,
        show_progress: bool = True
    ):
        """Initialize the model download component.

        Args:
            parent: Parent widget
            model_name: Display name of the model (e.g., "RAM Model", "CLIP ViT-B-32")
            download_callback: Function to perform the download.
                Should accept two callbacks: progress_callback(current, total)
                and status_callback(success: bool, message: str).
                Example:
                    def download(progress_cb, status_cb):
                        # Do download
                        progress_cb(50, 100)
                        # On completion
                        status_cb(True, "Success")
            show_progress: Whether to show progress bar
        """
        super().__init__(parent)

        self._model_name = model_name
        self._download_callback = download_callback
        self._show_progress = show_progress
        self._downloading = False
        self._download_result: tuple[bool, str] | None = None
        self._worker_thread: WorkerThread | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Top row: Model name + Download button
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self.model_label = QLabel(self._model_name)
        font = self.model_label.font()
        font.setBold(True)
        self.model_label.setFont(font)
        top_layout.addWidget(self.model_label)

        self.download_btn = QPushButton("Download")
        self.download_btn.clicked.connect(self._on_download_clicked)
        self.download_btn.setMinimumWidth(100)
        top_layout.addWidget(self.download_btn)

        top_layout.addStretch()
        layout.addLayout(top_layout)

        # Progress bar (if enabled)
        if self._show_progress:
            self.progress_bar = QProgressBar()
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            layout.addWidget(self.progress_bar)
        else:
            self.progress_bar = None

        # Status label
        self.status_label = QLabel("")
        status_font = QFont()
        status_font.setPointSize(9)
        self.status_label.setFont(status_font)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def set_model_name(self, model_name: str) -> None:
        """Set the model name display.

        Args:
            model_name: New model name
        """
        self._model_name = model_name
        self.model_label.setText(model_name)

    def get_model_name(self) -> str:
        """Get the current model name.

        Returns:
            Current model name
        """
        return self._model_name

    def set_download_callback(self, callback: Callable[[Callable, Callable], None]) -> None:
        """Set the download callback function.

        Args:
            callback: Function that performs the download
        """
        self._download_callback = callback

    def is_downloading(self) -> bool:
        """Check if download is in progress.

        Returns:
            True if currently downloading
        """
        return self._downloading

    @Slot()
    def _on_download_clicked(self) -> None:
        """Handle download button click."""
        if self._downloading:
            return

        if not self._download_callback:
            self._set_status("✗ No download callback configured", error=True)
            return

        self.start_download()

    def start_download(self) -> None:
        """Start the download process in a background thread."""
        if self._downloading:
            return

        self._downloading = True
        self.download_btn.setEnabled(False)
        if self.progress_bar:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
        self._set_status("Starting download...")
        self.download_started.emit()

        # Create worker thread
        self._worker_thread = WorkerThread(
            work_func=self._download_worker
        )
        self._worker_thread.progress.connect(self._on_worker_progress)
        self._worker_thread.finished.connect(self._on_download_finished)
        self._worker_thread.error.connect(self._on_download_error)
        self._worker_thread.start()

    def _download_worker(
        self,
        progress_callback: Callable[[int, int, str], None],
        should_cancel: Callable[[], bool]
    ) -> Any:
        """Worker function that runs the download.

        Args:
            progress_callback: Callback for progress updates (current, total, message)
            should_cancel: Function to check if cancellation requested

        Returns:
            None (success signals are via status_callback)
        """
        def wrapped_progress(current: int, total: int) -> None:
            """Wrapper for progress callback that emits signal."""
            progress_callback(current, total, "Downloading...")
            self.download_progress.emit(current, total)

        def status_callback(success: bool, message: str) -> None:
            """Callback for final status."""
            # Store result for finished signal
            self._download_result = (success, message)

        # Call the user's download callback
        self._download_callback(wrapped_progress, status_callback)

    @Slot(object)
    def _on_worker_progress(self, progress: Any) -> None:
        """Handle progress updates from worker thread."""
        if hasattr(progress, 'current') and hasattr(progress, 'total'):
            if self.progress_bar and progress.total > 0:
                percentage = int((progress.current / progress.total) * 100)
                self.progress_bar.setValue(percentage)

            if hasattr(progress, 'message') and progress.message:
                self._set_status(progress.message)

    @Slot()
    def _on_download_finished(self) -> None:
        """Handle download completion."""
        self._downloading = False
        self.download_btn.setEnabled(True)
        if self.progress_bar:
            self.progress_bar.setVisible(False)

        # Get result from worker (if set by status_callback)
        result = getattr(self, '_download_result', None)
        if result:
            success, message = result
            self._set_status(message, error=not success)
            self.download_complete.emit(success, message)

            if success:
                self._show_success_dialog(message)
        else:
            self._set_status("✓ Download complete")
            self.download_complete.emit(True, "Download complete")

    @Slot(Exception)
    def _on_download_error(self, error: Exception) -> None:
        """Handle download error."""
        self._downloading = False
        self.download_btn.setEnabled(True)
        if self.progress_bar:
            self.progress_bar.setVisible(False)

        error_msg = str(error)
        self._set_status(f"✗ Error: {error_msg}", error=True)
        self.download_complete.emit(False, error_msg)

        QMessageBox.critical(
            self,
            "Download Error",
            f"Failed to download {self._model_name}:\n\n{error_msg}"
        )

    def _set_status(self, message: str, error: bool = False) -> None:
        """Set the status label text.

        Args:
            message: Status message
            error: Whether this is an error message (changes color)
        """
        self.status_label.setText(message)
        if error:
            self.status_label.setStyleSheet("color: #dc3545;")  # Red
        else:
            self.status_label.setStyleSheet("color: #6c757d;")  # Gray

    def _show_success_dialog(self, message: str) -> None:
        """Show success dialog.

        Args:
            message: Success message
        """
        QMessageBox.information(
            self,
            "Download Complete",
            f"{self._model_name} downloaded successfully.\n\n{message}"
        )

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the component.

        Args:
            enabled: Whether to enable the component
        """
        self.setEnabled(enabled)
        self.download_btn.setEnabled(enabled and not self._downloading)

    # State persistence
    def to_dict(self) -> dict[str, Any]:
        """Serialize component state to dictionary.

        Returns:
            Dictionary with model_name and downloading state
        """
        return {
            "model_name": self._model_name,
            "downloading": self._downloading,
        }

    def from_dict(self, state: dict[str, Any]) -> None:
        """Restore component state from dictionary.

        Note: Does not restore downloading state (downloads should not persist).

        Args:
            state: Dictionary from to_dict()
        """
        if "model_name" in state:
            self.set_model_name(state["model_name"])

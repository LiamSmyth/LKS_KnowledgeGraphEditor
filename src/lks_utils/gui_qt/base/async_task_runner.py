"""
Asynchronous task execution for PySide6 GUIs.

Provides WorkerThread and QAsyncTaskRunner for background work without
blocking the UI thread.
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


from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal


@dataclass
class TaskProgress:
    """Progress update from background task."""
    current: int
    total: int
    message: str = ""


class WorkerThread(QThread):
    """
    Generic worker thread for background tasks.

    Emits progress, finished, and error signals.
    Supports cancellation via cancel() method.
    """

    progress = Signal(TaskProgress)
    finished = Signal(object)  # Result object
    error = Signal(Exception)

    def __init__(
        self,
        work_func: Callable[..., Any],
        args: tuple = (),
        kwargs: dict | None = None,
    ):
        """
        Initialize worker thread.

        Args:
            work_func: Function to execute in background
            args: Positional arguments for work_func
            kwargs: Keyword arguments for work_func
        """
        super().__init__()
        self._work_func = work_func
        self._args = args
        self._kwargs = kwargs or {}
        self._cancelled = False

    def run(self) -> None:
        """Execute work function and emit result or error."""
        try:
            # Inject progress callback if function accepts it
            if "progress_callback" in self._work_func.__code__.co_varnames:
                self._kwargs["progress_callback"] = self._emit_progress

            # Inject cancel callback if function accepts it
            if "cancel_callback" in self._work_func.__code__.co_varnames:
                self._kwargs["cancel_callback"] = self._is_cancelled

            result: Any = self._work_func(*self._args, **self._kwargs)

            if not self._cancelled:
                self.finished.emit(result)

        except Exception as e:
            if not self._cancelled:
                self.error.emit(e)

    def _emit_progress(self, current: int, total: int, message: str = "") -> None:
        """Emit progress update. Called by work function."""
        if not self._cancelled:
            self.progress.emit(TaskProgress(current, total, message))

    def _is_cancelled(self) -> bool:
        """Check if task has been cancelled."""
        return self._cancelled

    def cancel(self) -> None:
        """Cancel the task. Work function should check for cancellation."""
        self._cancelled = True


class QAsyncTaskRunner(QObject):
    """
    Base class/mixin for GUIs that run background tasks.

    Replaces tkinter's threading.Thread + .after() pattern with QThread.

    Usage:
        class MyGUI(QWidget, QAsyncTaskRunner):
            def __init__(self):
                QWidget.__init__(self)
                QAsyncTaskRunner.__init__(self)

            def _on_start_clicked(self):
                self._run_task(
                    work_func=self._do_work,
                    args=(self.get_input(),),
                    on_progress=self._on_progress,
                    on_finished=self._on_finished,
                    on_error=self._on_error,
                )

            def _do_work(self, input_data, progress_callback=None):
                for i in range(100):
                    if progress_callback:
                        progress_callback(i, 100, f"Step {i}")
                    # Do work...
                return result
    """

    task_started = Signal()
    task_finished = Signal(object)
    task_error = Signal(Exception)
    task_progress = Signal(TaskProgress)

    def __init__(self):
        """Initialize async task runner. Must call super().__init__()."""
        super().__init__()
        self._worker: WorkerThread | None = None

    def _run_task(
        self,
        work_func: Callable[..., Any],
        args: tuple = (),
        kwargs: dict | None = None,
        on_progress: Callable[[TaskProgress], None] | None = None,
        on_finished: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """
        Run a task in a background thread with progress updates.

        Args:
            work_func: Function to execute in background
            args: Positional arguments for work_func
            kwargs: Keyword arguments for work_func
            on_progress: Callback for progress updates (optional)
            on_finished: Callback when task completes (optional)
            on_error: Callback when task errors (optional)
        """
        if self._worker and self._worker.isRunning():
            return  # Already running

        self._worker = WorkerThread(work_func, args, kwargs)

        # Connect signals
        if on_progress:
            self._worker.progress.connect(on_progress)
        if on_finished:
            self._worker.finished.connect(on_finished)
        if on_error:
            self._worker.error.connect(on_error)

        # Emit started signal
        self.task_started.emit()
        self._worker.start()

    def _cancel_task(self) -> None:
        """Cancel the running task."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.quit()
            self._worker.wait(1000)  # Wait up to 1 second

    def _is_task_running(self) -> bool:
        """Check if a task is currently running."""
        return self._worker is not None and self._worker.isRunning()


__all__ = ["TaskProgress", "WorkerThread", "QAsyncTaskRunner"]

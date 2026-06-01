"""QFileBrowserPanel — live file-system browser with extension filtering and thumbnails.

Reusable PySide6 component for browsing a directory, filtering by extension,
and displaying files in an icon/list view with thumbnail generation.
Supports:
- Folder selection via ``set_directory(path)`` or built-in Browse button.
- Directory navigation — double-click folders to descend, Back button to ascend.
- Extension filtering (e.g., ``[".png", ".tiff", ".exr"]``).
- Icon-mode with thumbnail generation via a pluggable callback.
- Single-click selection emits ``file_selected(Path)``.
- Multi-select mode for batch operations.
"""
from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDir, QModelIndex, QRect, QSize, Qt, Signal, QTimer, QItemSelectionModel
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWidgets import QFileSystemModel
except ImportError:
    from PySide6.QtCore import QFileSystemModel  # type: ignore[attr-defined]

_ICON_SIZE: int = 64
_DEFAULT_EXTENSIONS: list[str] = [".png", ".tif", ".tiff", ".exr"]
_THUMB_THREAD_BATCH: int = 8  # thumbnails generated per timer tick


class _ThumbnailDelegate(QStyledItemDelegate):
    """Item delegate that renders cached thumbnails for image files."""

    def __init__(
        self,
        fs_model: QFileSystemModel,
        cache: dict[str, QIcon],
        icon_size: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fs_model = fs_model
        self._cache = cache
        self._icon_size = icon_size

    def set_icon_size(self, size: int) -> None:
        self._icon_size = size

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Paint item, replacing system icon with cached thumbnail when available."""
        file_path = self._fs_model.filePath(index)
        cached = self._cache.get(file_path)
        if cached is None:
            # No thumbnail yet — use default delegate (system icon)
            super().paint(painter, option, index)
            return

        # Let the base delegate draw selection highlight, background, label, etc.
        # We temporarily clear the decoration so the base pass draws no icon,
        # then we draw the thumbnail ourselves in the decoration rect.
        super().paint(painter, option, index)

        # Draw thumbnail centred in the decoration area
        deco_size = QSize(self._icon_size, self._icon_size)
        rect = option.rect
        # Icon sits in the top portion; label occupies the bottom ~30px
        icon_rect = QRect(
            rect.x() + (rect.width() - deco_size.width()) // 2,
            rect.y() + 4,
            deco_size.width(),
            deco_size.height(),
        )
        cached.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        """Clear the system decoration icon when we have a cached thumbnail."""
        super().initStyleOption(option, index)
        file_path = self._fs_model.filePath(index)
        if file_path in self._cache:
            # Suppress the system file icon; paint() will draw our thumbnail
            option.icon = QIcon()
            option.decorationSize = QSize(self._icon_size, self._icon_size)


class QFileBrowserPanel(QWidget):
    """Live file-system browser with extension filtering and directory navigation.

    Features:
    - **Directory navigation**: double-click a folder to enter it; Back (``\u2190``)
      button to go up one level.
    - **Thumbnails**: supply a ``thumbnail_callback`` to render file previews.
    - **Extension filtering**: only matching files shown; folders always visible.

    Signals:
        file_selected(Path): Emitted on single-click of a file.
        file_activated(Path): Emitted on double-click of a file.
        selection_changed(list[Path]): Emitted when multi-selection changes.
        directory_changed(Path): Emitted when the browsed directory changes.
    """

    file_selected: Signal = Signal(Path)
    file_activated: Signal = Signal(Path)
    selection_changed: Signal = Signal(list)
    directory_changed: Signal = Signal(Path)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        extensions: list[str] | None = None,
        multi_select: bool = False,
        show_browse_button: bool = True,
        icon_size: int = _ICON_SIZE,
        thumbnail_callback: Callable[[Path], QImage | None] | None = None,
    ) -> None:
        """Initialize the file browser panel.

        Args:
            parent: Parent widget.
            extensions: File extensions to show (e.g., ``[".png", ".exr"]``).
                        If ``None``, uses a default set of displacement map extensions.
            multi_select: Allow multi-file selection.
            show_browse_button: Show a Browse button for directory selection.
            icon_size: Thumbnail icon size in pixels.
            thumbnail_callback: Optional function ``(Path) -> QImage | None`` to
                                generate custom thumbnails.  Called lazily per file.
                                If ``None``, a built-in Pillow thumbnail generator
                                is used (when Pillow is available).
        """
        super().__init__(parent)
        self._extensions: list[str] = extensions or list(_DEFAULT_EXTENSIONS)
        self._multi_select: bool = multi_select
        self._icon_size: int = icon_size
        self._thumbnail_callback: Callable[[
            Path], QImage | None] | None = thumbnail_callback
        self._current_dir: Path | None = None
        self._thumbnail_cache: dict[str, QIcon] = {}
        self._dir_history: list[Path] = []
        self._persistent_selected_paths: list[Path] = []
        self._restoring_selection: bool = False

        # Thumbnail generation queue
        self._thumb_pending: list[str] = []
        self._thumb_timer: QTimer | None = None
        # Results queue: background threads put (path_str, QImage|None) here;
        # main thread drains each tick, converts QImage -> QIcon (must be main
        # thread) and stores in the cache.
        self._thumb_results: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue(
        )
        self._thumb_inflight: int = 0  # threads currently running

        self._build_ui(show_browse_button)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, show_browse: bool) -> None:
        """Build the panel layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Navigation bar: Back + dir label + browse
        nav_bar = QHBoxLayout()
        nav_bar.setSpacing(4)

        self._hist_btn = QPushButton("\u2190")
        self._hist_btn.setToolTip("Go back to previous directory")
        self._hist_btn.setFixedWidth(28)
        self._hist_btn.setEnabled(False)
        self._hist_btn.clicked.connect(self._on_navigate_back)
        nav_bar.addWidget(self._hist_btn)

        self._up_btn = QPushButton("\u2191")
        self._up_btn.setToolTip("Go to parent directory")
        self._up_btn.setFixedWidth(28)
        self._up_btn.setEnabled(False)
        self._up_btn.clicked.connect(self._on_navigate_up)
        nav_bar.addWidget(self._up_btn)

        self._dir_label = QLabel("No folder selected")
        self._dir_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self._dir_label.setWordWrap(True)
        nav_bar.addWidget(self._dir_label, stretch=1)

        if show_browse:
            browse_btn = QPushButton("Browse\u2026")
            browse_btn.setToolTip("Select a folder to browse")
            browse_btn.setFixedWidth(70)
            browse_btn.clicked.connect(self._on_browse)
            nav_bar.addWidget(browse_btn)

        layout.addLayout(nav_bar)

        # File system model — show dirs + filtered files
        self._fs_model = QFileSystemModel()
        self._fs_model.setReadOnly(True)
        self._fs_model.setNameFilterDisables(False)
        # Show both directories and filtered files
        self._fs_model.setFilter(
            QDir.Filter.AllDirs
            | QDir.Filter.Files
            | QDir.Filter.NoDotAndDotDot
        )
        self._update_name_filters()

        # Connect directoryLoaded to deferred thumbnail generation
        self._fs_model.directoryLoaded.connect(self._on_directory_loaded)

        # List view
        self._list_view = QListView()
        self._list_view.setModel(self._fs_model)
        self._list_view.setViewMode(QListView.ViewMode.IconMode)
        self._list_view.setIconSize(QSize(self._icon_size, self._icon_size))
        self._list_view.setGridSize(
            QSize(self._icon_size + 20, self._icon_size + 30))
        self._list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self._list_view.setWrapping(True)
        self._list_view.setUniformItemSizes(True)
        self._list_view.setSpacing(4)

        # Wire up thumbnail delegate — reads from _thumbnail_cache keyed by
        # file path.  initStyleOption injects cached icons before each paint.
        self._delegate = _ThumbnailDelegate(
            self._fs_model, self._thumbnail_cache, self._icon_size, self._list_view
        )
        self._list_view.setItemDelegate(self._delegate)

        if self._multi_select:
            self._list_view.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection)
        else:
            self._list_view.setSelectionMode(
                QAbstractItemView.SelectionMode.SingleSelection)

        self._list_view.clicked.connect(self._on_item_clicked)
        self._list_view.doubleClicked.connect(self._on_item_double_clicked)
        if self._multi_select:
            sel_model = self._list_view.selectionModel()
            if sel_model:
                sel_model.selectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self._list_view, stretch=1)

        # Status bar
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self._status_label)

    def _update_name_filters(self) -> None:
        """Set name filters on the QFileSystemModel."""
        patterns = [f"*{ext}" for ext in self._extensions]
        self._fs_model.setNameFilters(patterns)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_directory(self, path: str | Path) -> None:
        """Set the directory to browse."""
        p = Path(path)
        if not p.is_dir():
            return
        # Track history for back navigation
        if self._current_dir is not None and self._current_dir != p:
            self._dir_history.append(self._current_dir)

        self._current_dir = p
        self._persistent_selected_paths = []
        root = self._fs_model.setRootPath(str(p))
        self._list_view.setRootIndex(root)
        self._dir_label.setText(p.name or str(p))
        self._dir_label.setToolTip(str(p))
        self._dir_label.setStyleSheet("color: #ccc; font-size: 11px;")
        self._up_btn.setEnabled(p.parent != p)
        self._hist_btn.setEnabled(len(self._dir_history) > 0)
        self._thumbnail_cache.clear()
        self.directory_changed.emit(p)

        # Defer status update and thumbnail generation until model has loaded.
        # The directoryLoaded signal triggers _schedule_thumbnails for new dirs;
        # the singleShot here is a fallback for directories already cached by
        # QFileSystemModel (where directoryLoaded may not re-fire).
        QTimer.singleShot(200, self._update_status)
        QTimer.singleShot(300, self._schedule_thumbnails)

    def get_directory(self) -> Path | None:
        """Return the currently browsed directory."""
        return self._current_dir

    def set_extensions(self, extensions: list[str]) -> None:
        """Update the set of visible file extensions."""
        self._extensions = extensions
        self._update_name_filters()

    def get_selected_paths(self) -> list[Path]:
        """Return currently selected file paths."""
        paths: list[Path] = []
        for idx in self._list_view.selectedIndexes():
            file_path = self._fs_model.filePath(idx)
            if file_path:
                paths.append(Path(file_path))
        return paths

    def set_icon_size(self, size: int) -> None:
        """Update icon/thumbnail size."""
        self._icon_size = size
        self._list_view.setIconSize(QSize(size, size))
        self._list_view.setGridSize(QSize(size + 20, size + 30))
        self._delegate.set_icon_size(size)
        # Re-generate thumbnails at new size
        self._thumbnail_cache.clear()
        if self._current_dir:
            self._schedule_thumbnails()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize browser state for persistence."""
        return {
            "directory": str(self._current_dir) if self._current_dir else "",
            "icon_size": self._icon_size,
        }

    def from_dict(self, state: dict[str, Any]) -> None:
        """Restore browser state from dict."""
        directory = state.get("directory", "")
        if directory and Path(directory).is_dir():
            self.set_directory(directory)
        icon_size = state.get("icon_size", _ICON_SIZE)
        self.set_icon_size(int(icon_size))

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        """Open directory selection dialog."""
        start = str(self._current_dir) if self._current_dir else ""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Folder", start,
        )
        if directory:
            self.set_directory(directory)

    def _on_navigate_up(self) -> None:
        """Navigate to parent directory."""
        if self._current_dir is not None:
            parent = self._current_dir.parent
            if parent != self._current_dir:
                self.set_directory(parent)

    def _on_navigate_back(self) -> None:
        """Navigate back to the previously visited directory (browser-style Back)."""
        if not self._dir_history:
            return
        target = self._dir_history.pop()
        # Navigate without pushing target back onto history
        self._navigate_without_history(target)

    def _navigate_without_history(self, p: Path) -> None:
        """Set directory without recording the transition in _dir_history."""
        if not p.is_dir():
            return
        self._current_dir = p
        self._persistent_selected_paths = []
        root = self._fs_model.setRootPath(str(p))
        self._list_view.setRootIndex(root)
        self._dir_label.setText(p.name or str(p))
        self._dir_label.setToolTip(str(p))
        self._dir_label.setStyleSheet("color: #ccc; font-size: 11px;")
        self._up_btn.setEnabled(p.parent != p)
        self._hist_btn.setEnabled(len(self._dir_history) > 0)
        self._thumbnail_cache.clear()
        self.directory_changed.emit(p)
        QTimer.singleShot(200, self._update_status)
        QTimer.singleShot(300, self._schedule_thumbnails)

    def _on_item_clicked(self, index: QModelIndex) -> None:
        """Handle single click on a file."""
        path_str = self._fs_model.filePath(index)
        if path_str:
            p = Path(path_str)
            if p.is_file():
                self.file_selected.emit(p)

    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        """Handle double click on a file or directory."""
        path_str = self._fs_model.filePath(index)
        if path_str:
            p = Path(path_str)
            if p.is_dir():
                self.set_directory(p)
            elif p.is_file():
                self.file_activated.emit(p)

    def _on_selection_changed(self, *_args: Any) -> None:
        """Emit selection_changed with current selected paths."""
        paths = self.get_selected_paths()
        if paths:
            self._persistent_selected_paths = paths
            self.selection_changed.emit(paths)
            self._update_status()
            return

        if self._restoring_selection:
            self._update_status()
            return

        if self._multi_select and self._persistent_selected_paths and not self._list_view.hasFocus():
            QTimer.singleShot(0, self._restore_persistent_selection)
            self._update_status()
            return

        self._persistent_selected_paths = []
        self.selection_changed.emit([])
        self._update_status()

    def _restore_persistent_selection(self) -> None:
        """Restore the last persisted multi-selection after external focus changes."""
        if not self._multi_select or not self._persistent_selected_paths:
            return
        sel_model = self._list_view.selectionModel()
        if sel_model is None:
            return

        root_path = self._current_dir.resolve() if self._current_dir else None
        restored = False
        self._restoring_selection = True
        try:
            sel_model.clearSelection()
            current_index = QModelIndex()
            for path in self._persistent_selected_paths:
                if root_path is not None and path.parent.resolve() != root_path:
                    continue
                index = self._fs_model.index(str(path))
                if not index.isValid():
                    continue
                sel_model.select(
                    index,
                    QItemSelectionModel.SelectionFlag.Select,
                )
                if not restored:
                    current_index = index
                restored = True
            if current_index.isValid():
                sel_model.setCurrentIndex(
                    current_index,
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
        finally:
            self._restoring_selection = False

        if restored:
            self.selection_changed.emit(self.get_selected_paths())
            self._update_status()

    def _on_directory_loaded(self, path: str) -> None:
        """Called when QFileSystemModel finishes loading a directory."""
        if self._current_dir and str(self._current_dir) == path:
            self._update_status()
            self._schedule_thumbnails()

    def _update_status(self) -> None:
        """Update the status label with file count."""
        if self._current_dir is None:
            self._status_label.setText("")
            return
        root_idx = self._list_view.rootIndex()
        count = self._fs_model.rowCount(root_idx)
        # Count only files (not directories) for the status
        file_count = 0
        dir_count = 0
        for i in range(count):
            child = self._fs_model.index(i, 0, root_idx)
            if self._fs_model.isDir(child):
                dir_count += 1
            else:
                file_count += 1
        selected = len(self._list_view.selectedIndexes())
        parts: list[str] = []
        if dir_count > 0:
            parts.append(f"{dir_count} folders")
        parts.append(f"{file_count} files")
        if selected > 0:
            parts.append(f"{selected} selected")
        self._status_label.setText("  |  ".join(parts))

    # ------------------------------------------------------------------
    # Thumbnail generation
    # ------------------------------------------------------------------

    def _schedule_thumbnails(self) -> None:
        """Scan visible files and queue thumbnail generation."""
        if self._current_dir is None:
            return

        root_idx = self._list_view.rootIndex()
        count = self._fs_model.rowCount(root_idx)
        self._thumb_pending.clear()

        for i in range(count):
            child = self._fs_model.index(i, 0, root_idx)
            path_str = self._fs_model.filePath(child)
            if not path_str or path_str in self._thumbnail_cache:
                continue
            p = Path(path_str)
            if p.is_file() and p.suffix.lower() in self._extensions:
                self._thumb_pending.append(path_str)

        if self._thumb_pending or self._thumb_inflight:
            if self._thumb_timer is None:
                self._thumb_timer = QTimer(self)
                self._thumb_timer.timeout.connect(self._process_thumb_batch)
            self._thumb_timer.start(100)

    def _process_thumb_batch(self) -> None:
        """Drain completed results and submit a new batch to background threads."""
        # 1 — Drain completed results (background threads put QImage here;
        #     QPixmap/QIcon MUST be created in the main thread).
        newly_cached: list[str] = []
        while True:
            try:
                path_str, img = self._thumb_results.get_nowait()
                self._thumb_inflight = max(0, self._thumb_inflight - 1)
                if img is not None and path_str not in self._thumbnail_cache:
                    pixmap = QPixmap.fromImage(img).scaled(
                        self._icon_size, self._icon_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._thumbnail_cache[path_str] = QIcon(pixmap)
                    newly_cached.append(path_str)
            except queue.Empty:
                break

        if newly_cached:
            # Repaint only the specific items whose thumbnails just arrived.
            # Calling viewport().update() for every batch triggers Qt's
            # accessibility layer to enumerate ALL children — which races with
            # QFileSystemModel's async row insertions and produces spurious
            # "QAccessibleList::child: Invalid index" warnings.
            root_idx = self._list_view.rootIndex()
            cached_set = set(newly_cached)
            for i in range(self._fs_model.rowCount(root_idx)):
                child = self._fs_model.index(i, 0, root_idx)
                if self._fs_model.filePath(child) in cached_set:
                    self._list_view.update(child)

        # 2 — Submit new batch (up to _THUMB_THREAD_BATCH concurrent threads).
        while self._thumb_pending and self._thumb_inflight < _THUMB_THREAD_BATCH:
            path_str = self._thumb_pending.pop(0)
            if path_str in self._thumbnail_cache:
                continue
            self._thumb_inflight += 1
            p = Path(path_str)
            results_q = self._thumb_results
            icon_size = self._icon_size
            callback = self._thumbnail_callback

            def _worker(
                p: Path = p,
                path_str: str = path_str,
                rq: queue.SimpleQueue[tuple[str, Any]] = results_q,
                cb: Callable[[Path], QImage | None] | None = callback,
                sz: int = icon_size,
            ) -> None:
                try:
                    img = cb(p) if cb is not None else None
                    if img is None:
                        img = _pillow_thumbnail_image(p, sz)
                    rq.put((path_str, img))
                except Exception:
                    rq.put((path_str, None))

            threading.Thread(target=_worker, daemon=True).start()

        # 3 — Stop timer when all work is done.
        if not self._thumb_pending and self._thumb_inflight == 0:
            if self._thumb_timer is not None:
                self._thumb_timer.stop()

    @staticmethod
    def _pillow_thumbnail(path: Path, size: int = 64) -> QIcon | None:
        """Generate a thumbnail QIcon using Pillow (main-thread fallback)."""
        img = _pillow_thumbnail_image(path, size)
        if img is None:
            return None
        return QIcon(QPixmap.fromImage(img))


def _pillow_thumbnail_image(path: Path, size: int = 64) -> QImage | None:
    """Generate a thumbnail QImage via Pillow.  Thread-safe (no Qt painting)."""
    try:
        from PIL import Image as PILImage
    except ImportError:
        return None

    try:
        img = PILImage.open(path)
        # For multi-channel images, take first channel
        if img.mode not in ("L", "F", "I", "I;16", "I;16B", "I;16L"):
            img = img.split()[0]
        # Convert to float32 for universal normalisation (handles 8-bit, 16-bit, float)
        import numpy as np
        arr = np.array(img.convert("F"), dtype=np.float32)
        a_min, a_max = float(arr.min()), float(arr.max())
        if a_max > a_min:
            norm = ((arr - a_min) / (a_max - a_min) * 255).astype(np.uint8)
        else:
            norm = np.zeros_like(arr, dtype=np.uint8)
        pil_gray = PILImage.fromarray(norm, mode="L")
        pil_gray.thumbnail((size, size), PILImage.Resampling.LANCZOS)
        pil_rgb = pil_gray.convert("RGB")
        data = pil_rgb.tobytes()
        qimg = QImage(data, pil_rgb.width, pil_rgb.height,
                      QImage.Format.Format_RGB888)
        return qimg.copy()
    except Exception:
        return None


__all__ = ["QFileBrowserPanel"]

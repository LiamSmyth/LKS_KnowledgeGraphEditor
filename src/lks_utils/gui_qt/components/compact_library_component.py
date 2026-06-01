"""Compact single-row library toolbar for Save/Load/Store/Library file operations (PySide6).

A condensed variant of :class:`QLibraryComponent` using icon-only tool buttons
and a minimal status indicator. Designed for embedding in narrow side panels
where horizontal space is at a premium.

API contract is identical to :class:`QLibraryComponent` — same signals and
public methods — so the two are interchangeable from the caller's perspective.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStyle,
    QToolButton,
    QWidget,
)

from lks_utils.gui_qt.components.library_component import QLibraryComponent


class QCompactLibraryComponent(QLibraryComponent):
    """Compact single-row toolbar for Save/Load/Store/Library file operations.

    Inherits all I/O logic from :class:`QLibraryComponent`.  Only
    :meth:`_build_ui` is overridden to produce a compact, icon-based layout
    that fits inside narrow side-panels without horizontal scrolling.

    Differences from the full variant:

    * ``Save As`` is hidden (available via :meth:`save_as` programmatically).
    * Buttons use icons + short tooltips instead of full text labels.
    * ``setMaximumHeight(28)`` keeps the bar single-row.
    * No ``setMinimumWidth`` constraint.

    Example::

        library = QCompactLibraryComponent(
            parent=self,
            extra_library_dirs=[Path("data/layer_stacks")],
            file_filter="Layer Stacks (*.json)",
            file_extension=".json",
        )
        library.data_requested.connect(self._on_data_requested)
        library.data_loaded.connect(self._on_data_loaded)
    """

    def _build_ui(self) -> None:
        """Build the compact toolbar layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self.setMaximumHeight(28)

        # ── New ───────────────────────────────────────────────────────────
        self._new_btn = QToolButton()
        self._new_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self._new_btn.setToolTip("New — clear to an empty layer stack")
        self._new_btn.setFixedSize(24, 24)
        self._new_btn.clicked.connect(self.new)
        layout.addWidget(self._new_btn)

        # ── Save ──────────────────────────────────────────────────────────
        self._save_btn = QToolButton()
        self._save_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self._save_btn.setToolTip("Save layer stack to current file (Ctrl+S)")
        self._save_btn.setFixedSize(24, 24)
        self._save_btn.clicked.connect(self.save)
        layout.addWidget(self._save_btn)

        # Save As — hidden; fulfils parent attribute contract
        self._save_as_btn = QToolButton()
        self._save_as_btn.setVisible(False)
        self._save_as_btn.clicked.connect(self.save_as)
        layout.addWidget(self._save_as_btn)

        # ── Load ──────────────────────────────────────────────────────────
        self._load_btn = QToolButton()
        self._load_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self._load_btn.setToolTip("Load layer stack from file")
        self._load_btn.setFixedSize(24, 24)
        self._load_btn.clicked.connect(self.load)
        layout.addWidget(self._load_btn)

        # ── Separator ─────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # ── Store ─────────────────────────────────────────────────────────
        self._store_btn = QToolButton()
        self._store_btn.setText("Store")
        self._store_btn.setToolTip("Add current layer stack to library")
        self._store_btn.setFixedHeight(24)
        self._store_btn.clicked.connect(self.store)
        layout.addWidget(self._store_btn)

        # ── Library dropdown ──────────────────────────────────────────────
        self._library_btn = QToolButton()
        self._library_btn.setText("Library ▾")
        self._library_btn.setToolTip("Load a layer stack from the library")
        self._library_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        self._library_menu = QMenu(self)
        self._library_btn.setMenu(self._library_menu)
        self._library_btn.setFixedHeight(24)
        layout.addWidget(self._library_btn)

        layout.addStretch()

        # ── Status label ──────────────────────────────────────────────────
        self._status_label = QLabel("Untitled")
        self._status_label.setStyleSheet(
            "font-style: italic; color: #666; font-size: 10px;")
        self._status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._status_label.setMaximumWidth(140)
        self._status_label.setToolTip("")  # updated by _update_title
        layout.addWidget(self._status_label)

    def _update_title(self) -> None:
        """Update compact status label (filename only, tooltip shows full path)."""
        if self._current_file_path:
            # Compact form: filename only (no parent dir)
            title = self._current_file_path.name
            self._status_label.setToolTip(str(self._current_file_path))
        else:
            title = "Untitled"
            self._status_label.setToolTip("")

        if self._is_dirty:
            title += " *"

        self._status_label.setText(title)
        self.title_changed.emit(title)

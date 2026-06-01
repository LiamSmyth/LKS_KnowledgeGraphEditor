"""
Qt component for editing .gitignore-style exclusion pattern files.

Provides:
- Multi-line text editor with .gitignore-style syntax highlighting
  - ``#`` comments → grey italic
  - ``!`` negation patterns → muted green (re-include a previously excluded path)
  - normal patterns → default text colour
- QLibraryComponent toolbar for save / load / store presets
- ``get_patterns()`` → parsed ``list[str]`` ready for
  ``create_archive(exclude_patterns=...)``
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(
            None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.library_component import QLibraryComponent


def _parse_gitignore_patterns(text: str) -> list[str]:
    """Parse .gitignore-style text into a list of patterns.

    - Blank lines are skipped
    - Lines starting with ``#`` are comments and are skipped
    - Negation patterns (``!``) are preserved with their prefix
    - Leading/trailing whitespace is stripped
    - Trailing ``/`` is stripped (directory marker, unsupported by fnmatch)
    - Leading ``/`` is stripped (root-anchor, unsupported — becomes unanchored)
    """
    patterns: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("!"):
            prefix, pattern = "!", stripped[1:]
        else:
            prefix, pattern = "", stripped
        pattern = pattern.lstrip("/").rstrip("/")
        if pattern:
            patterns.append(prefix + pattern)
    return patterns

_PRESET_DIR = Path(__file__).parent / "data" / "gitignore_presets"


class _GitignoreHighlighter(QSyntaxHighlighter):
    """Minimal syntax highlighter for .gitignore-style text.

    - Lines starting with ``#`` → grey italic (comments)
    - Lines starting with ``!`` → muted green (negation / re-include)
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)

        self._comment_fmt = QTextCharFormat()
        self._comment_fmt.setForeground(QColor("#777777"))
        self._comment_fmt.setFontItalic(True)

        self._negation_fmt = QTextCharFormat()
        self._negation_fmt.setForeground(QColor("#6db365"))

    def highlightBlock(self, text: str) -> None:
        stripped = text.strip()
        if stripped.startswith("#"):
            self.setFormat(0, len(text), self._comment_fmt)
        elif stripped.startswith("!"):
            self.setFormat(0, len(text), self._negation_fmt)


class QGitignoreEditorComponent(QWidget):
    """Text-based editor for .gitignore-style exclusion patterns.

    Features:
    - Free-form multi-line editor with syntax highlighting
    - ``QLibraryComponent`` toolbar for save / load / store presets
    - ``get_patterns()`` returns a parsed ``list[str]`` ready for
      ``create_archive(exclude_patterns=...)``

    Signals:
        patterns_changed: Emitted when the text content changes.
    """

    patterns_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the gitignore editor component.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        _PRESET_DIR.mkdir(parents=True, exist_ok=True)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        """Build the UI widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Library bar -------------------------------------------------------
        lib_row = QHBoxLayout()
        lib_label = QLabel("Preset:")
        lib_label.setFixedWidth(50)
        self._library = QLibraryComponent(
            parent=self,
            library_dir=_PRESET_DIR,
            file_filter="Gitignore Patterns (*.gitignore);;Text Files (*.txt);;All Files (*)",
            file_extension=".gitignore",
            label="",
        )
        self._library.data_requested.connect(self._on_save_requested)
        self._library.data_loaded.connect(self._on_data_loaded)
        lib_row.addWidget(lib_label)
        lib_row.addWidget(self._library, stretch=1)
        layout.addLayout(lib_row)

        # Text editor -------------------------------------------------------
        self._editor = QTextEdit()
        self._editor.setAcceptRichText(False)
        self._editor.setPlaceholderText(
            "# Enter exclusion patterns — one per line\n"
            "# Examples:  *.tmp   .git   __pycache__   !important.log"
        )
        self._editor.setFont(
            QFont("Cascadia Code, Consolas, Courier New", 9)
        )
        self._editor.setMinimumHeight(120)
        self._editor.setMaximumHeight(200)

        self._highlighter = _GitignoreHighlighter(self._editor.document())
        layout.addWidget(self._editor)

        # Hint label --------------------------------------------------------
        hint = QLabel(
            "# = comment    ! = re-include (negate previous exclusion)    * = wildcard"
        )
        hint.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(hint)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self._editor.textChanged.connect(self._on_text_changed)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _on_text_changed(self) -> None:
        self._library.mark_dirty()
        self.patterns_changed.emit()

    def _on_save_requested(self) -> None:
        """Provide raw text content to QLibraryComponent for saving."""
        self._library.set_data(self.get_text())

    def _on_data_loaded(self, content: str) -> None:
        """Load raw text content from QLibraryComponent."""
        self.set_text(content)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_text(self) -> str:
        """Return the raw editor text (including comments and blank lines)."""
        return self._editor.toPlainText()

    def set_text(self, text: str) -> None:
        """Set the editor content.

        Blocks internal signals during update to avoid double emission.

        Args:
            text: Raw .gitignore-style text.
        """
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self.patterns_changed.emit()

    def get_patterns(self) -> list[str]:
        """Return the effective pattern list, stripping comments and blank lines.

        Returns:
            Parsed patterns ready for ``create_archive(exclude_patterns=...)``.
            Negation patterns (``!``) are included with their prefix.
        """
        return _parse_gitignore_patterns(self.get_text())

    def set_patterns(self, patterns: list[str]) -> None:
        """Populate the editor from a plain list of patterns.

        No comment lines are inserted; whitespace is preserved.

        Args:
            patterns: List of pattern strings (may include ``!`` negations).
        """
        self.set_text("\n".join(patterns))

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize editor state for persistence.

        Returns:
            Dict with ``"text"`` key containing the raw editor content.
        """
        return {"text": self.get_text()}

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore editor state from a persisted dict.

        Args:
            data: Dict with optional ``"text"`` key.  Falls back to empty
                  string if key is absent.
        """
        self.set_text(data.get("text", ""))


__all__ = ["QGitignoreEditorComponent"]

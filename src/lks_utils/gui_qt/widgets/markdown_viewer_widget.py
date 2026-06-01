"""QMarkdownViewerWidget — a split-pane markdown editor and preview widget.

Provides an edit-only, preview-only, or side-by-side layout for authoring
and viewing markdown content.  The preview is rendered via the ``markdown``
Python library into styled HTML and displayed in a ``QTextBrowser`` that
works without any extra PySide6 extras.

Modes
-----
``"edit"``
    Plain-text editor only.
``"preview"``
    Read-only rendered preview only.
``"split"``
    Editor on the left, live preview on the right.

Signals
-------
``content_changed(str)``
    Emitted after every keystroke with the current markdown text.

Example
-------
::

    from lks_utils.gui_qt.widgets import QMarkdownViewerWidget

    widget = QMarkdownViewerWidget(mode="split")
    widget.set_markdown("# Hello\\n\\nSome **bold** text.")
    widget.content_changed.connect(lambda md: print("changed"))
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QFont, QTextOption
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.widgets.markdown_highlighter import QMarkdownHighlighter

try:
    import markdown
    from markdown.extensions.codehilite import CodeHiliteExtension
    from markdown.extensions.fenced_code import FencedCodeExtension
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

# ------------------------------------------------------------------ #
# Dark-theme CSS injected into rendered HTML                         #
# ------------------------------------------------------------------ #
_CSS = """
body {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    margin: 12px 16px;
}
h1, h2, h3, h4, h5, h6 {
    color: #eeeeee;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
    font-weight: 600;
}
h1 { font-size: 1.8em; border-bottom: 1px solid #444; padding-bottom: 0.2em; }
h2 { font-size: 1.4em; border-bottom: 1px solid #333; padding-bottom: 0.15em; }
h3 { font-size: 1.15em; }
a { color: #4da6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
code {
    background-color: #2d2d2d;
    border: 1px solid #444;
    border-radius: 3px;
    padding: 2px 4px;
    font-family: "Consolas", "Cascadia Code", monospace;
    font-size: 0.9em;
    color: #e8c07d;
}
pre {
    background-color: #252525;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 10px 14px;
    overflow-x: auto;
    line-height: 1.45;
}
pre code {
    background: none;
    border: none;
    padding: 0;
    color: #ce9178;
    font-size: 0.9em;
}
blockquote {
    border-left: 4px solid #375a7f;
    margin: 0;
    padding: 4px 16px;
    color: #aaa;
    background-color: #252525;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.6em 0;
}
th, td {
    border: 1px solid #444;
    padding: 6px 12px;
    text-align: left;
}
th {
    background-color: #2d2d2d;
    color: #eeeeee;
}
tr:nth-child(even) { background-color: #252525; }
hr {
    border: none;
    border-top: 1px solid #444;
    margin: 1.2em 0;
}
ul, ol {
    padding-left: 1.5em;
}
li { margin-bottom: 0.2em; }
"""

_MARKDOWN_EXTENSIONS = [
    "tables",
    "fenced_code",
    "codehilite",
    "nl2br",
    "sane_lists",
    "toc",
]

_PLACEHOLDER_HTML = "<p style='color:#666;font-style:italic;margin:16px;'>No content.</p>"


def _md_to_html(text: str) -> str:
    """Convert markdown text to a complete dark-themed HTML document."""
    if not text.strip():
        return f"<html><head><style>{_CSS}</style></head><body>{_PLACEHOLDER_HTML}</body></html>"

    if not HAS_MARKDOWN:
        # Minimal fallback: escape HTML and wrap in <pre>
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        body = f"<pre style='white-space:pre-wrap'>{escaped}</pre>"
        return f"<html><head><style>{_CSS}</style></head><body>{body}</body></html>"

    extensions = [e for e in _MARKDOWN_EXTENSIONS if _extension_available(e)]
    body = markdown.markdown(text, extensions=extensions)
    return f"<html><head><style>{_CSS}</style></head><body>{body}</body></html>"


def _extension_available(name: str) -> bool:
    """Return True if the named markdown extension can be imported."""
    try:
        markdown.markdown("", extensions=[name])
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ #
# Editor pane                                                         #
# ------------------------------------------------------------------ #

class _MarkdownEditor(QPlainTextEdit):
    """Plain-text editor styled for dark markdown authoring with live highlighting."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1e1e1e;"
            "  color: #d4d4d4;"
            "  border: 1px solid #444;"
            "  selection-background-color: #264f78;"
            "}"
        )
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        # Attach syntax highlighter — must be after setDocument / after __init__
        self._highlighter = QMarkdownHighlighter(
            self.document(), self, base_font_pt=11.0)


# ------------------------------------------------------------------ #
# Preview pane                                                         #
# ------------------------------------------------------------------ #

class _MarkdownPreview(QTextBrowser):
    """Read-only HTML preview pane."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setStyleSheet(
            "QTextBrowser {"
            "  background-color: #1e1e1e;"
            "  border: 1px solid #444;"
            "}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setHtml(
            f"<html><head><style>{_CSS}</style></head><body>{_PLACEHOLDER_HTML}</body></html>")


# ------------------------------------------------------------------ #
# Public widget                                                        #
# ------------------------------------------------------------------ #

ViewMode = Literal["edit", "preview", "split"]


class QMarkdownViewerWidget(QWidget):
    """A combined markdown editor and preview widget.

    Args:
        parent: Optional parent widget.
        mode: Initial display mode — ``"edit"``, ``"preview"``, or ``"split"``.
        preview_delay_ms: Debounce delay in milliseconds before updating the
            preview after a keystroke.  Defaults to 50 ms (imperceptible but
            still batches rapid paste / IME input).

    Signals:
        content_changed(str): Emitted (debounced) when the editor content
            changes.  The argument is the current markdown text.
    """

    content_changed = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        mode: ViewMode = "split",
        preview_delay_ms: int = 50,
    ) -> None:
        super().__init__(parent)
        self._mode: ViewMode = mode
        self._preview_delay = preview_delay_ms

        self._editor = _MarkdownEditor(self)
        self._preview = _MarkdownPreview(self)

        # Debounce timer — 50 ms default batches rapid keystrokes without perceptible lag
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._flush_preview)

        self._editor.textChanged.connect(self._on_text_changed)

        self._splitter = QSplitter(self)
        self._splitter.addWidget(self._editor)
        self._splitter.addWidget(self._preview)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStyleSheet(
            "QSplitter::handle { background-color: #444; width: 3px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)

        self._apply_mode(mode)

    # ---------------------------------------------------------------- #
    # Public API                                                         #
    # ---------------------------------------------------------------- #

    def get_markdown(self) -> str:
        """Return the current raw markdown text."""
        return self._editor.toPlainText()

    def set_markdown(self, text: str) -> None:
        """Replace the editor content without emitting ``content_changed``."""
        self._editor.blockSignals(True)
        try:
            self._editor.setPlainText(text)
        finally:
            self._editor.blockSignals(False)
        self._refresh_preview(text)

    def set_mode(self, mode: ViewMode) -> None:
        """Switch display mode at runtime."""
        self._mode = mode
        self._apply_mode(mode)

    def get_mode(self) -> ViewMode:
        """Return the current display mode."""
        return self._mode

    def is_modified(self) -> bool:
        """Return True if the editor document has unsaved changes."""
        return self._editor.document().isModified()

    def mark_saved(self) -> None:
        """Clear the modified flag (call after saving to file)."""
        self._editor.document().setModified(False)

    # ---------------------------------------------------------------- #
    # Internal helpers                                                   #
    # ---------------------------------------------------------------- #

    def _apply_mode(self, mode: ViewMode) -> None:
        if mode == "edit":
            self._editor.setVisible(True)
            self._preview.setVisible(False)
        elif mode == "preview":
            self._editor.setVisible(False)
            self._preview.setVisible(True)
            # Force a render in case content was set while in edit mode
            self._refresh_preview(self._editor.toPlainText())
        else:  # split
            self._editor.setVisible(True)
            self._preview.setVisible(True)

    def _on_text_changed(self) -> None:
        self._update_timer.start(self._preview_delay)

    def _flush_preview(self) -> None:
        text = self._editor.toPlainText()
        if self._mode != "edit":
            self._refresh_preview(text)
        self.content_changed.emit(text)

    def _refresh_preview(self, text: str) -> None:
        html = _md_to_html(text)
        # Preserve scroll position
        scrollbar = self._preview.verticalScrollBar()
        pos = scrollbar.value() if scrollbar else 0
        self._preview.setHtml(html)
        if scrollbar:
            scrollbar.setValue(pos)

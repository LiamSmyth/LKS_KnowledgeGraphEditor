"""QMarkdownHighlighter — QSyntaxHighlighter for dark-themed Markdown editing.

Applies live syntax highlighting inside a ``QPlainTextEdit`` to make the raw
Markdown source legible as formatted text without hiding any characters.

Active-line behaviour
---------------------
When the text cursor is on a line, syntax marker characters (``#``, ``**``,
`` ` ``, ``>``, ``~~``, etc.) are shown in a visible muted-blue colour so
you can see and edit them.  On all other lines the markers are dimmed to
near-black so they recede visually and the formatted appearance of the
content dominates.

Supported constructs
--------------------
- ATX headings ``# … ######`` — bold text, scaled font size (h1–h3), dimmed markers
- Fenced code blocks (``` or ~~~) — multi-line state machine, amber content
- Inline code `` `…` `` — amber monospace, dimmed backtick markers
- Bold ``**…**`` / ``__…__``
- Italic ``*…*`` / ``_…_``
- Bold-italic ``***…***``
- Strikethrough ``~~…~~``
- Blockquotes ``> …``
- Unordered/ordered list markers
- Links ``[text](url)`` and images ``![alt](url)``
- Horizontal rules (``---``, ``***``, ``___``)

Usage
-----
::

    editor = QPlainTextEdit()
    highlighter = QMarkdownHighlighter(editor.document(), editor)

The highlighter is re-applied automatically when the cursor moves so that
the active-line marker colour updates instantly.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

# ─────────────────────────────────────────────────────────────────────────────
# Block state constants
# ─────────────────────────────────────────────────────────────────────────────
_STATE_NORMAL: int = 0
_STATE_FENCE: int = 1

# ─────────────────────────────────────────────────────────────────────────────
# Colour tokens
# ─────────────────────────────────────────────────────────────────────────────
_MARKER_DIM = "#3e3e3e"     # non-active: syntax chars nearly invisible
_MARKER_VIS = "#6e8ab0"     # active line: syntax chars visible (muted blue)
_CODE_FG = "#e8c07d"     # inline code / fenced code content
_LANG_FG = "#6a9955"     # language tag on opening fence ``` line
_STRIKE_FG = "#777777"
_QUOTE_FG = "#888888"
_LINK_FG = "#4da6ff"
_URL_FG = "#3a7ab0"
_HR_FG = "#555555"
_H_FG: dict[int, str] = {
    1: "#eeeeee",
    2: "#e8e8df",
    3: "#ddddcc",
    4: "#ccccaa",
    5: "#bbbbaa",
    6: "#aaaaaa",
}

_BASE_PT: float = 11.0
_H_PT: dict[int, float] = {
    1: round(_BASE_PT * 1.55, 1),
    2: round(_BASE_PT * 1.35, 1),
    3: round(_BASE_PT * 1.15, 1),
}

# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns (module-level for performance — compiled once at import)
# ─────────────────────────────────────────────────────────────────────────────
_RE_FENCE = re.compile(r'^(`{3,}|~{3,})(\s*\w*)\s*$')
_RE_HEADING = re.compile(r'^(#{1,6})([ \t]+)(.*?)(\s*(?:#+\s*)?)$')
_RE_HR = re.compile(r'^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$')
_RE_BQ = re.compile(r'^(>+[ \t]?)(.*)')
_RE_LIST = re.compile(r'^([ \t]*)([-*+]|\d+[.\)])(\s+)(.*)')

# Inline — processed in priority order inside _apply_inline
_RE_CODE = re.compile(r'(`+)(.+?)\1', re.DOTALL)
_RE_BI = re.compile(r'(\*{3})(?![ \t])(.+?)(?<![ \t])(\*{3})')
_RE_BOLD_S = re.compile(r'(\*{2})(?![ \t*])(.+?)(?<![ \t*])(\*{2})')
_RE_BOLD_U = re.compile(r'(_{2})(?![ \t_])(.+?)(?<![ \t_])(_{2})')
_RE_LINK = re.compile(r'(!?\[)([^\]]*?)(\]\()([^)]*?)(\))')
_RE_STRIKE = re.compile(r'(~~)(?![ \t])(.+?)(?<![ \t])(~~)')
_RE_ITALIC_S = re.compile(r'(?<!\*)\*(?![ \t*])(.+?)(?<![ \t])\*(?!\*)')
_RE_ITALIC_U = re.compile(r'(?<![\w_])_(?![ \t_])(.+?)(?<![ \t])_(?![\w_])')


# ─────────────────────────────────────────────────────────────────────────────
# QTextCharFormat factory
# ─────────────────────────────────────────────────────────────────────────────
def _fmt(
    *,
    fg: str | None = None,
    bold: bool = False,
    italic: bool = False,
    strike: bool = False,
    pt: float | None = None,
    mono: bool = False,
) -> QTextCharFormat:
    """Build and return a QTextCharFormat from keyword flags."""
    f = QTextCharFormat()
    if fg:
        f.setForeground(QColor(fg))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    if strike:
        f.setFontStrikeOut(True)
    if pt is not None:
        f.setFontPointSize(pt)
    if mono:
        f.setFontFamilies(["Consolas", "Cascadia Code", "Courier New"])
    return f


# ─────────────────────────────────────────────────────────────────────────────
# Highlighter
# ─────────────────────────────────────────────────────────────────────────────
class QMarkdownHighlighter(QSyntaxHighlighter):
    """Markdown syntax highlighter with active-line source visibility.

    Args:
        document: ``QTextDocument`` to highlight (``editor.document()``).
        editor: The owning ``QPlainTextEdit`` — required for cursor tracking.
        base_font_pt: Base font point size; headings h1–h3 are scaled
            relative to this value.  Defaults to 11.0.
    """

    def __init__(
        self,
        document: QTextDocument,
        editor: "QPlainTextEdit",
        base_font_pt: float = _BASE_PT,
    ) -> None:
        super().__init__(document)
        self._editor = editor
        self._base_pt = base_font_pt
        self._active_bn: int = editor.textCursor().blockNumber()
        editor.cursorPositionChanged.connect(self._on_cursor_changed)

    # ─────────────────────────────────────────────────────────────────────────
    # Cursor tracking
    # ─────────────────────────────────────────────────────────────────────────

    def _on_cursor_changed(self) -> None:
        new_bn = self._editor.textCursor().blockNumber()
        if new_bn == self._active_bn:
            return
        old_bn, self._active_bn = self._active_bn, new_bn
        for bn in (old_bn, new_bn):
            blk = self.document().findBlockByNumber(bn)
            if blk.isValid():
                self.rehighlightBlock(blk)

    # ─────────────────────────────────────────────────────────────────────────
    # Per-call format builders
    # ─────────────────────────────────────────────────────────────────────────

    def _dim(self, active: bool) -> QTextCharFormat:
        return _fmt(fg=_MARKER_VIS if active else _MARKER_DIM)

    def _h_fmt(self, level: int, active: bool) -> QTextCharFormat:
        fg = _H_FG.get(level, "#aaaaaa")
        pt = self._base_pt if active else _H_PT.get(level, self._base_pt)
        return _fmt(fg=fg, bold=True, pt=pt)

    # ─────────────────────────────────────────────────────────────────────────
    # Main block highlighter
    # ─────────────────────────────────────────────────────────────────────────

    def highlightBlock(self, text: str) -> None:
        active = self.currentBlock().blockNumber() == self._active_bn
        dim = self._dim(active)

        # ── Fenced code block state machine ──────────────────────────────────
        if self.previousBlockState() == _STATE_FENCE:
            m = _RE_FENCE.match(text)
            if m:
                # Closing fence
                self.setFormat(0, len(text), dim)
                self.setCurrentBlockState(_STATE_NORMAL)
            else:
                # Interior fence content
                self.setFormat(0, len(text), _fmt(fg=_CODE_FG, mono=True))
                self.setCurrentBlockState(_STATE_FENCE)
            return

        fm = _RE_FENCE.match(text)
        if fm:
            # Opening fence
            self.setFormat(0, len(fm.group(1)), dim)
            lang = fm.group(2).strip()
            if lang:
                self.setFormat(fm.start(2), len(
                    fm.group(2)), _fmt(fg=_LANG_FG))
            self.setCurrentBlockState(_STATE_FENCE)
            return

        self.setCurrentBlockState(_STATE_NORMAL)

        # ── Horizontal rule ───────────────────────────────────────────────────
        if _RE_HR.match(text) and len(text.strip()) >= 3:
            self.setFormat(0, len(text), _fmt(fg=_HR_FG))
            return

        # ── ATX Heading ───────────────────────────────────────────────────────
        hm = _RE_HEADING.match(text)
        if hm:
            markers, space, content, trail = (
                hm.group(1), hm.group(2), hm.group(3), hm.group(4)
            )
            level = len(markers)
            p = 0
            self.setFormat(p, len(markers), dim)
            p += len(markers)
            self.setFormat(p, len(space), _fmt())
            p += len(space)
            self.setFormat(p, len(content), self._h_fmt(level, active))
            if trail:
                self.setFormat(p + len(content), len(trail), dim)
            # Apply inline rules to heading content (bold/italic inside headings)
            self._apply_inline(text, p, len(content), active)
            return

        # ── Blockquote ────────────────────────────────────────────────────────
        bm = _RE_BQ.match(text)
        if bm:
            marker_end = len(bm.group(1))
            self.setFormat(0, marker_end, dim)
            self.setFormat(marker_end, len(bm.group(2)),
                           _fmt(fg=_QUOTE_FG, italic=True))
            self._apply_inline(text, marker_end, len(bm.group(2)), active)
            return

        # ── List item ─────────────────────────────────────────────────────────
        lm = _RE_LIST.match(text)
        if lm:
            indent, bullet, sp = lm.group(1), lm.group(2), lm.group(3)
            p = len(indent)
            self.setFormat(p, len(bullet), dim)
            p += len(bullet) + len(sp)
            self._apply_inline(text, p, len(lm.group(4)), active)
            return

        # ── Regular paragraph ─────────────────────────────────────────────────
        self._apply_inline(text, 0, len(text), active)

    # ─────────────────────────────────────────────────────────────────────────
    # Inline rules
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_inline(self, text: str, offset: int, length: int, active: bool) -> None:
        """Apply inline formatting rules to ``text[offset : offset+length]``."""
        segment = text[offset: offset + length]
        dim = self._dim(active)

        # Track claimed character positions to prevent double-processing
        claimed: set[int] = set()

        def try_apply(pattern: re.Pattern, handler: Callable) -> None:
            for m in pattern.finditer(segment):
                span = set(range(m.start(), m.end()))
                if span & claimed:
                    continue
                claimed.update(span)
                handler(m)

        # ── Handler definitions ───────────────────────────────────────────────

        def h_code(m: re.Match) -> None:
            s = offset + m.start()
            tick = len(m.group(1))
            self.setFormat(s, tick, dim)
            self.setFormat(s + tick, len(m.group(2)),
                           _fmt(fg=_CODE_FG, mono=True))
            self.setFormat(s + tick + len(m.group(2)), tick, dim)

        def h_bi(m: re.Match) -> None:
            s = offset + m.start()
            self.setFormat(s, 3, dim)
            self.setFormat(s + 3, len(m.group(2)),
                           _fmt(bold=True, italic=True))
            self.setFormat(s + 3 + len(m.group(2)), 3, dim)

        def h_bold(m: re.Match) -> None:
            s = offset + m.start()
            self.setFormat(s, 2, dim)
            self.setFormat(s + 2, len(m.group(2)), _fmt(bold=True))
            self.setFormat(s + 2 + len(m.group(2)), 2, dim)

        def h_link(m: re.Match) -> None:
            s = offset + m.start()
            p = s
            self.setFormat(p, len(m.group(1)), dim)           # ![ or [
            p += len(m.group(1))
            self.setFormat(p, len(m.group(2)), _fmt(fg=_LINK_FG))  # link text
            p += len(m.group(2))
            self.setFormat(p, len(m.group(3)), dim)           # ](
            p += len(m.group(3))
            self.setFormat(p, len(m.group(4)), _fmt(fg=_URL_FG))   # url
            p += len(m.group(4))
            self.setFormat(p, len(m.group(5)), dim)           # )

        def h_strike(m: re.Match) -> None:
            s = offset + m.start()
            self.setFormat(s, 2, dim)
            self.setFormat(s + 2, len(m.group(2)),
                           _fmt(fg=_STRIKE_FG, strike=True))
            self.setFormat(s + 2 + len(m.group(2)), 2, dim)

        def h_italic_s(m: re.Match) -> None:
            s = offset + m.start()
            content_len = len(m.group(1))
            self.setFormat(s, 1, dim)
            self.setFormat(s + 1, content_len, _fmt(italic=True))
            self.setFormat(s + 1 + content_len, 1, dim)

        def h_italic_u(m: re.Match) -> None:
            s = offset + m.start()
            content_len = len(m.group(1))
            self.setFormat(s, 1, dim)
            self.setFormat(s + 1, content_len, _fmt(italic=True))
            self.setFormat(s + 1 + content_len, 1, dim)

        # ── Apply in priority order ───────────────────────────────────────────
        # Code first — claims its interior so other spans don't consume it.
        # Bold-italic before bold (consumes *** so * isn't re-used by bold/**).
        # Links before italic ([ won't be confused with *).
        # Italic last — lowest priority single-char marker.
        try_apply(_RE_CODE,     h_code)
        try_apply(_RE_BI,       h_bi)
        try_apply(_RE_BOLD_S,   h_bold)
        try_apply(_RE_BOLD_U,   h_bold)
        try_apply(_RE_LINK,     h_link)
        try_apply(_RE_STRIKE,   h_strike)
        try_apply(_RE_ITALIC_S, h_italic_s)
        try_apply(_RE_ITALIC_U, h_italic_u)

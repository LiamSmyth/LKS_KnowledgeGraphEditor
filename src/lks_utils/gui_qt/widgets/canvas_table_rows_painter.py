"""Reusable Canvas2D table-rows painter for node-like card items.

Row text is centred vertically using Qt's ``AlignVCenter`` flag — exactly like
:class:`CanvasNodeHeaderPainter` — so there is no manual baseline arithmetic
and no risk of glyph ascenders escaping their slot.

Layout in a Y-up canvas::

    ┌─────────────────────────────┐  ← row_top   (higher world-Y)
    │  label | type | value ...   │   text centred with AlignVCenter
    ├─────────────────────────────┤  ← row_bottom (lower world-Y)
    │  ...                        │
    └─────────────────────────────┘

The separator line is drawn at ``row_bottom`` (the lower boundary).
A per-cell ``IntersectClip`` rect ensures no glyph can cross the separator
even at fractional zoom levels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen, QTextLayout, QTextOption

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext

# ─────────────────────────────────────────────────────────────────────────────
# Column descriptor
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CanvasTableColumn:
    """Layout + style descriptor for one column in a :class:`CanvasTableRowsPainter`."""

    width: float
    """World-unit width of this column."""

    color: QColor
    """Text colour."""

    x_pad: float = 4.0
    """Horizontal padding applied to both the clip rect and the text origin."""

    vertical_align: str = "center"
    """Vertical alignment for single-line text: ``center`` (default) or ``top``."""


@dataclass(frozen=True, slots=True)
class CanvasTableCellStyle:
    """Optional cell-level paint overrides for :class:`CanvasTableRowsPainter`."""

    multiline: bool = False
    """When True, wrap text within the cell instead of ellipsizing it to one line."""

    max_lines: int | None = None
    """Optional cap on visible wrapped lines; the last visible line is ellipsized."""

    text_color: QColor | None = None
    """Optional text color override for this specific cell."""


# ─────────────────────────────────────────────────────────────────────────────
# Painter
# ─────────────────────────────────────────────────────────────────────────────


class CanvasTableRowsPainter:
    """Paint equal-height rows with inter-row separator lines in a Y-up canvas.

    Usage pattern mirrors :class:`CanvasNodeHeaderPainter`::

        painter = CanvasTableRowsPainter(row_height=20.0, font_px=11)
        painter.paint_rows(ctx, panel_rect=panel, columns=cols, rows=data)

    ``panel_rect`` is a :class:`~PySide6.QtCore.QRectF` in **world coordinates**.
    In a Y-up canvas ``panel_rect.bottom()`` is the *higher* world-Y value
    (visually at the top) and ``panel_rect.top()`` is the *lower* world-Y value
    (visually at the bottom).  This matches how ``_rows_panel_rect()`` is built
    in ``QKnowledgeGraphNodeCanvasItem``.
    """

    def __init__(
        self,
        *,
        row_height: float = 20.0,
        font_px: int = 11,
        separator_color: QColor | None = None,
    ) -> None:
        self._row_height = row_height
        self._font_px = font_px
        self._sep_color = separator_color or QColor("#2c3f5c")

    # ------------------------------------------------------------------
    # public API

    def paint_rows(
        self,
        ctx: "CanvasPaintContext",
        *,
        panel_rect: QRectF,
        columns: list[CanvasTableColumn],
        rows: list[tuple[str, ...]],
        first_row_top: float | None = None,
        scrollbar_right_inset: float = 0.0,
        row_heights: list[float] | None = None,
        cell_styles: dict[tuple[int, int], CanvasTableCellStyle] | None = None,
    ) -> None:
        """Paint *rows* inside *panel_rect*.

        Args:
            ctx: active paint context.
            panel_rect: inner panel rect in world/painter coordinates.
            columns: ordered column descriptors.
            rows: each item is a tuple of strings — one per column.
            first_row_top: world-Y of the first row's upper boundary.
                Defaults to ``panel_rect.bottom() - 2``.
            scrollbar_right_inset: reserve this many world units on the right
                for a scrollbar track (e.g. pass ``6.0`` when overflow is shown).
        """
        if not rows or not columns:
            return

        painter = ctx.painter
        font = QFont()
        font.setPixelSize(self._font_px)
        metrics = QFontMetrics(font)

        row_top_0 = (
            panel_rect.bottom() - 2.0 if first_row_top is None else first_row_top
        )
        panel_left = panel_rect.left()
        panel_right = panel_rect.right() - scrollbar_right_inset

        sep_pen = QPen(self._sep_color, 1.0)
        sep_pen.setCosmetic(True)

        for index, row_values in enumerate(rows):
            h = (
                row_heights[index]
                if row_heights is not None and index < len(row_heights)
                else self._row_height
            )
            row_top = row_top_0
            if row_heights is not None:
                row_top -= sum(row_heights[:index])
            else:
                row_top -= index * h
            row_bottom = row_top - h

            # Skip slots below the visible panel area.
            if row_bottom < panel_rect.top() - 0.5:
                continue
            # Skip slots above the visible panel area (when scrolled).
            if row_top > panel_rect.bottom() + 0.5:
                continue

            # ── separator at the lower boundary (between this row and next) ──
            painter.save()
            painter.setPen(sep_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(
                panel_left + 2.0,
                row_bottom,
                panel_right - 2.0,
                row_bottom,
            )
            painter.restore()

            # ── column text, per-cell clipped ─────────────────────────────────
            col_x = panel_left
            for col_idx, column in enumerate(columns):
                if col_idx >= len(row_values):
                    break
                text = row_values[col_idx]
                col_right = col_x + column.width

                # Hard clip so no glyph can cross the separator.
                # QRectF(x, y, w, h): y is QRectF "top" = lower world-Y.
                cell_clip = QRectF(
                    col_x,
                    row_bottom + 0.5,
                    min(column.width, panel_right - col_x) - column.x_pad,
                    h - 1.0,
                )

                painter.save()
                painter.setClipRect(cell_clip, Qt.ClipOperation.IntersectClip)

                # Translate to visual top of the row slot, flip Y so that
                # y=0 is the slot's visual top and y=h is the slot's visual
                # bottom — the same trick CanvasNodeHeaderPainter uses.
                # Qt's AlignVCenter then handles font-metric centering
                # without any manual baseline arithmetic.
                painter.translate(col_x + column.x_pad, row_top)
                painter.scale(1.0, -1.0)
                painter.setFont(font)

                max_text_w = max(
                    0, int(min(column.width, panel_right - col_x) - column.x_pad * 2.0))
                style = None if cell_styles is None else cell_styles.get(
                    (index, col_idx))
                painter.setPen(
                    column.color
                    if style is None or style.text_color is None
                    else style.text_color
                )
                if style is not None and style.multiline:
                    self._draw_multiline_text(
                        painter,
                        text,
                        font,
                        metrics,
                        max_text_w=max_text_w,
                        max_lines=style.max_lines,
                    )
                else:
                    elided = metrics.elidedText(
                        text,
                        Qt.TextElideMode.ElideRight,
                        max_text_w,
                    )
                    vertical_alignment = (
                        Qt.AlignmentFlag.AlignTop
                        if column.vertical_align == "top"
                        else Qt.AlignmentFlag.AlignVCenter
                    )
                    painter.drawText(
                        QRectF(0.0, 0.0, float(max_text_w), h),
                        Qt.AlignmentFlag.AlignLeft | vertical_alignment,
                        elided,
                    )

                painter.restore()
                col_x = col_right

    def _draw_multiline_text(
        self,
        painter,
        text: str,
        font: QFont,
        metrics: QFontMetrics,
        *,
        max_text_w: int,
        max_lines: int | None,
    ) -> None:
        layout = QTextLayout(text, font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)

        lines: list[tuple[int, int]] = []
        truncated = False
        layout.beginLayout()
        try:
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(float(max_text_w))
                if max_lines is not None and len(lines) >= max_lines:
                    truncated = True
                    break
                lines.append((line.textStart(), line.textLength()))
        finally:
            layout.endLayout()

        line_height = float(metrics.lineSpacing())
        baseline = float(metrics.ascent()) + 2.0
        for index, (text_start, text_length) in enumerate(lines):
            fragment = text[text_start:text_start + text_length]
            if truncated and index == len(lines) - 1:
                fragment = metrics.elidedText(
                    text[text_start:],
                    Qt.TextElideMode.ElideRight,
                    max_text_w,
                )
            painter.drawText(
                QPointF(0.0, baseline + (index * line_height)),
                fragment,
            )


__all__ = [
    "CanvasTableCellStyle",
    "CanvasTableColumn",
    "CanvasTableRowsPainter",
]

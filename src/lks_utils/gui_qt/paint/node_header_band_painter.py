"""Reusable Qt painter for compact node-style header bands."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen

from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext


class CanvasNodeHeaderPainter:
    """Draw a compact top ribbon with bold title and optional italic subtitle."""

    def __init__(
        self,
        *,
        title_font_px: int = 11,
        subtitle_font_px: int = 11,
    ) -> None:
        self._title_font_px = title_font_px
        self._subtitle_font_px = subtitle_font_px

    def paint_band(
        self,
        ctx: CanvasPaintContext,
        *,
        x0: float,
        x1: float,
        top_y: float,
        height: float,
        title: str,
        subtitle: str | None,
        background_color: QColor,
        title_color: QColor,
        subtitle_color: QColor | None = None,
        separator_color: QColor | None = None,
        text_padding_x: float = 6.0,
        text_baseline_offset: float = 6.0,
        subtitle_gap: float = 6.0,
    ) -> None:
        """Paint one ribbon band in world space with an optional subtitle.

        Text is vertically centered using Qt's AlignVCenter so glyph ascent/descent
        asymmetry is handled automatically. The subtitle is right-aligned with
        AlignRight so its right edge sits exactly at the text-area boundary.
        """
        _ = text_baseline_offset  # preserved for API compatibility
        if x1 <= x0 or height <= 0.0:
            return

        painter = ctx.painter
        bottom_y = top_y - height

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background_color)
        painter.drawRect(x0, bottom_y, x1 - x0, height)

        painter.setPen(QPen(separator_color or title_color, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(x0, bottom_y, x1, bottom_y)

        title_font = QFont()
        title_font.setPixelSize(self._title_font_px)
        title_font.setBold(True)

        subtitle_font = QFont()
        subtitle_font.setPixelSize(self._subtitle_font_px)
        subtitle_font.setItalic(True)

        clip_margin_y = 0.5
        painter.save()
        painter.setClipRect(x0, bottom_y + clip_margin_y,
                            x1 - x0, height - (clip_margin_y * 2.0))
        painter.save()

        painter.translate(x0 + text_padding_x, top_y)
        painter.scale(1.0, -1.0)

        title_metrics = QFontMetrics(title_font)
        subtitle_metrics = QFontMetrics(subtitle_font)
        available_px = max(0, int((x1 - x0) - (text_padding_x * 2.0)))

        subtitle_text = ""
        subtitle_width = 0
        if subtitle:
            subtitle_text = subtitle_metrics.elidedText(
                subtitle,
                Qt.TextElideMode.ElideRight,
                available_px,
            )
            subtitle_width = subtitle_metrics.horizontalAdvance(subtitle_text)

        reserved_gap = int(subtitle_gap) if subtitle_text else 0
        title_available = max(0, available_px - subtitle_width - reserved_gap)
        title_text = title_metrics.elidedText(
            title,
            Qt.TextElideMode.ElideRight,
            title_available,
        )

        band_h = float(height)

        painter.setPen(title_color)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(0.0, 0.0, float(title_available), band_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title_text,
        )

        if subtitle_text:
            painter.setPen(subtitle_color or title_color)
            painter.setFont(subtitle_font)
            painter.drawText(
                QRectF(0.0, 0.0, float(available_px), band_h),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                subtitle_text,
            )

        painter.restore()
        painter.restore()


__all__ = ["CanvasNodeHeaderPainter"]

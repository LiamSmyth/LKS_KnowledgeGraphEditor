"""Perceptual heat-ramp color mapper for frame-time budget visualization.

Color scale relative to budget (ratio = total_ms / budget_ms):

  0.0 – 1.0   : blue (comfortable / fast) → green (exactly at target)
  > 1.0        : hard jump to yellow (over-budget alarm)
  1.0 – 1.25  : yellow → red
  1.25 – 2.0  : red → purple
  ≥ 2.0        : purple → white (critically bad, 2× or more over budget)
"""
from __future__ import annotations

from PySide6.QtGui import QColor

# ---------------------------------------------------------------------------
# Color stop constants
# ---------------------------------------------------------------------------
_BLUE = QColor(0x21, 0x96, 0xF3)   # comfortable / fast
_GREEN = QColor(0x66, 0xBB, 0x6A)  # exactly at budget
_YELLOW = QColor(0xFF, 0xC1, 0x07)  # just over budget (hard break)
_RED = QColor(0xEF, 0x53, 0x50)    # +25% over budget
_PURPLE = QColor(0xAB, 0x47, 0xBC)  # +100% over budget
_WHITE = QColor(0xFF, 0xFF, 0xFF)   # ≥ 2× over budget (critically bad)


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


class PerfGradientMapper:
    """Maps a frame-time or percentage value to a perceptual heat-ramp ``QColor``.

    Usage::

        mapper = PerfGradientMapper(budget_ms=16.6)
        color = mapper.map_ms(total_ms)   # by absolute ms value
        color = mapper.map_pct(pct)       # by % of frame (0–100)
    """

    def __init__(self, budget_ms: float = 16.6) -> None:
        self._budget_ms: float = max(float(budget_ms), 1e-6)

    @property
    def budget_ms(self) -> float:
        return self._budget_ms

    def set_budget_ms(self, budget_ms: float) -> None:
        self._budget_ms = max(float(budget_ms), 1e-6)

    def map_ms(self, total_ms: float) -> QColor:
        """Return the heat-ramp color for *total_ms*."""
        ratio = float(total_ms) / self._budget_ms
        return PerfGradientMapper._map_ratio(ratio)

    def map_pct(self, pct: float) -> QColor:
        """Return the heat-ramp color for *pct* (0–100) fraction of frame budget consumed."""
        ratio = float(pct) / 100.0
        return PerfGradientMapper._map_ratio(ratio)

    @staticmethod
    def _map_ratio(ratio: float) -> QColor:
        """Core mapping from ratio (ms / budget_ms) to color."""
        if ratio <= 0.0:
            return QColor(_BLUE)
        if ratio < 1.0:
            # Smooth blue → green as we approach the budget
            return _lerp_color(_BLUE, _GREEN, ratio)
        # Exactly at or over budget: hard cut to yellow, then worsens
        if ratio < 1.25:
            # yellow → red over the first +25% overshoot
            t = (ratio - 1.0) / 0.25
            return _lerp_color(_YELLOW, _RED, t)
        if ratio < 2.0:
            # red → purple over the next overshoot band
            t = (ratio - 1.25) / 0.75
            return _lerp_color(_RED, _PURPLE, t)
        # ≥ 2× budget: purple → white (reaches white at 3×)
        t = min((ratio - 2.0) / 1.0, 1.0)
        return _lerp_color(_PURPLE, _WHITE, t)


__all__ = ["PerfGradientMapper"]

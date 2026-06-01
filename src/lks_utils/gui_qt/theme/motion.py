"""Motion / animation timing constants for PySide6 GUIs.

Centralised time-constants for hover transitions, momentum-scroll
decay, view-transform lerp, etc. Per Phase 17h.

All durations are in **milliseconds** unless suffixed ``_S`` (seconds)
or ``_TC`` (time-constant for an exponential decay).
"""
from __future__ import annotations


# Hover / focus transitions.
HOVER_FADE_MS: int = 120
FOCUS_RING_FADE_MS: int = 80

# Wheel-driven scroll lerp (Phase 16f / 17i).
WHEEL_LERP_MS: int = 120
WHEEL_LERP_DISTANCE_PX: int = 64

# Momentum scroll (Phase 16f / 17i).
MOMENTUM_DECAY_TC: float = 0.18  # exponential time-constant in seconds
MOMENTUM_VELOCITY_WINDOW_MS: int = 100
MOMENTUM_MIN_VELOCITY_PX_S: float = 30.0  # below this, snap to rest

# Carousel-style edge fade in QMomentumScrollArea.
CAROUSEL_FADE_DISTANCE_PX: int = 24

# View-transform lerps (pinned-location fly-to, fit-to-view).
VIEW_LERP_MS: int = 250

# Generic overlay fade-in / fade-out (HUD, minimap show/hide).
OVERLAY_FADE_MS: int = 150


__all__ = [
    "HOVER_FADE_MS", "FOCUS_RING_FADE_MS",
    "WHEEL_LERP_MS", "WHEEL_LERP_DISTANCE_PX",
    "MOMENTUM_DECAY_TC", "MOMENTUM_VELOCITY_WINDOW_MS",
    "MOMENTUM_MIN_VELOCITY_PX_S",
    "CAROUSEL_FADE_DISTANCE_PX",
    "VIEW_LERP_MS",
    "OVERLAY_FADE_MS",
]

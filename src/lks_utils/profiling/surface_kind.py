"""Surface kind classification for performance targets."""
from __future__ import annotations

from enum import Enum


class SurfaceKind(str, Enum):
    """Performance surface category with default budget guidance.

    Attributes:
        INTERACTIVE: Frame-driven surface (painter, canvas, viewport).
            Default budget: 16.6 ms/frame (60 FPS).
        BATCH: Per-object processing (image compression, frame extraction).
            Budget declared per target.
        INIT: Module initialisation / first-paint.
            Default budget: ≤500 ms.
    """

    INTERACTIVE = "interactive"
    BATCH = "batch"
    INIT = "init"


__all__ = ["SurfaceKind"]

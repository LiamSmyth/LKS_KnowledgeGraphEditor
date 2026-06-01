"""`ViewportOverlay`: chrome drawn on top of all `CanvasItem`s.

Overlays inherit from `CanvasItem` so they participate in the same
paint pipeline, but are stored separately by `Canvas2D` and always
render last. They typically opt out of hit-testing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas2d_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform


class ViewportOverlay(CanvasItem):
    """A `CanvasItem` flagged as chrome.

    Attributes:
        screen_space: When True, the overlay's :meth:`paint` is given a
            paint context whose `view` is identity-at-current-viewport-
            size — so painting happens in screen pixels regardless of
            the actual viewport zoom/rotation. When False, the overlay
            paints in world space like any other item.
        accepts_input: When False (default), the overlay never consumes
            input even if its `handle_input` returns True. Set True for
            interactive overlays (e.g. minimap drag).
    """

    screen_space: bool = False
    accepts_input: bool = False
    supports_gpu_rendering: bool = False

    def __init__(self) -> None:
        super().__init__()
        self.gpu_enabled: bool = True

    def set_gpu_enabled(self, enabled: bool) -> None:
        """Enable or disable the overlay's GPU path.

        When disabled, GPU-capable canvases leave this overlay to the CPU
        renderer, which is useful for debugging parity between paths.
        """
        self.gpu_enabled = bool(enabled)
        self.request_repaint()

    def paint_cpu(self, ctx) -> None:  # noqa: ANN001
        """CPU fallback/default paint implementation.

        Existing overlays implement :meth:`paint`; the base class keeps that
        contract intact by delegating the CPU path to it.
        """
        self.paint(ctx)

    def can_render_gpu(self) -> bool:
        """Return whether this overlay should be consumed by the GPU backend."""
        return self.gpu_enabled and self.supports_gpu_rendering

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        """Render through the active GPU overlay backend.

        Subclasses that return ``True`` from :meth:`can_render_gpu` must
        override this method.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.render_gpu must be implemented when can_render_gpu() is True"
        )

    def hit_test(self, world_pt: tuple[float, float]) -> bool:  # noqa: D401
        """Overlays do not participate in hit-testing by default."""
        return self.accepts_input and super().hit_test(world_pt)


__all__ = ["ViewportOverlay"]

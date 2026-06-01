"""GPUContext factory for ModernGL contexts.

Provides a unified entry point for creating GPU contexts for both
interactive (Qt-shared) and headless (batch/CLI) use.

Usage — headless batch processing::

    ctx = GPUContext.create_headless()
    dispatch = ctx.make_dispatch()
    # use dispatch with GPU filters...

Usage — shared with a running QOpenGLWidget::

    ctx = GPUContext.from_widget(gl_viewport)
    dispatch = ctx.make_dispatch()

The raw ModernGL context is accessible via the :attr:`ctx` property for
code that uses ModernGL directly (e.g. ``GLDisplacementViewport``).
"""
from __future__ import annotations

from typing import Any

try:
    import moderngl
    HAS_MODERNGL: bool = True
except ImportError:
    HAS_MODERNGL = False


class GPUContext:
    """Wrapper around a ModernGL context with factory constructors.

    Args:
        ctx: A ``moderngl.Context`` instance (standalone or shared).
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx: Any = ctx

    # ------------------------------------------------------------------ #
    # Factories                                                            #
    # ------------------------------------------------------------------ #

    @classmethod
    def create_headless(cls) -> GPUContext:
        """Create an off-screen (standalone) ModernGL context.

        Does not require a display or Qt application.  Suitable for
        batch processing and CLI pipelines.

        Returns:
            A new :class:`GPUContext` backed by a standalone ModernGL context.

        Raises:
            RuntimeError: If ModernGL is not installed or context creation fails.
        """
        if not HAS_MODERNGL:
            msg = (
                "ModernGL is not installed. "
                "Install with: pip install moderngl"
            )
            raise RuntimeError(msg)
        ctx = moderngl.create_context(standalone=True)
        return cls(ctx)

    @classmethod
    def from_widget(cls, widget: Any) -> GPUContext:
        """Share a context with an existing ``QOpenGLWidget``.

        The widget must have been initialised (``initializeGL`` called) and
        have a ``.ctx`` attribute pointing to a ``moderngl.Context``.

        Args:
            widget: A ``QOpenGLWidget`` with ``ctx`` attribute.

        Returns:
            A :class:`GPUContext` backed by the widget's ModernGL context.

        Raises:
            AttributeError: If the widget does not expose ``.ctx``.
        """
        ctx = getattr(widget, "ctx", None)
        if ctx is None:
            msg = (
                f"{type(widget).__name__} does not have a .ctx attribute. "
                "Ensure the widget has been initialised (initializeGL called)."
            )
            raise AttributeError(msg)
        return cls(ctx)

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def ctx(self) -> Any:
        """The underlying ``moderngl.Context``."""
        return self._ctx

    # ------------------------------------------------------------------ #
    # Convenience                                                          #
    # ------------------------------------------------------------------ #

    def make_dispatch(self) -> Any:
        """Create a :class:`~lks_utils.gpu.compute_dispatch.ComputeDispatch` for this context.

        Returns:
            A ``ComputeDispatch`` instance bound to this context.
        """
        from lks_utils.gpu.compute_dispatch import ComputeDispatch
        return ComputeDispatch(self._ctx)

    def release(self) -> None:
        """Release the underlying ModernGL context (standalone contexts only).

        No-op for shared contexts — the Qt widget owns the lifecycle.
        """
        try:
            self._ctx.release()
        except Exception:
            pass


__all__ = ["GPUContext", "HAS_MODERNGL"]

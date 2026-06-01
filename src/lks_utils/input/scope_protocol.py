"""``HasInputScope`` protocol and scope-dispatch helpers.

Widgets that define an active input scope implement ``HasInputScope`` by
providing an ``input_scope()`` method.  The Qt-level focus-chain helper
lives in ``lks_utils.gui_qt.input_bindings_qt`` because it depends on
``QWidget``; this module is pure-Python and dependency-free.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HasInputScope(Protocol):
    """Widget protocol for declaring an active input scope.

    Implement ``input_scope()`` on any focusable widget that activates a
    scope-specific binding set (e.g. ``"canvas2d"``, ``"painter.canvas"``).
    Returning ``None`` means "no specific scope — fall back to global".
    """

    def input_scope(self) -> str | None:
        """Return the scope string active when this widget has focus, or None."""
        ...


__all__ = ["HasInputScope"]

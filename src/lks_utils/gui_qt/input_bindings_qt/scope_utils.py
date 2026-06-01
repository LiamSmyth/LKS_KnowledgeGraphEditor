"""Utilities for resolving active input scopes from the Qt focus chain.

``active_scopes_from_focus`` walks from the given widget up through its
parent chain and collects scope strings from any widget that implements
:class:`~lks_utils.input.scope_protocol.HasInputScope`.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from lks_utils.input.scope_protocol import HasInputScope


def active_scopes_from_focus(focus_widget: QWidget | None) -> list[str]:
    """Return the ordered list of active input scopes for *focus_widget*.

    Walks from *focus_widget* up through its parent chain.  Any widget
    that satisfies the :class:`HasInputScope` protocol contributes its
    scope string to the result.  Duplicate scopes are preserved in order
    (innermost first) so callers can do priority-aware dispatch.

    Returns an empty list when *focus_widget* is ``None`` or no widget in
    the chain declares a scope.
    """
    scopes: list[str] = []
    widget: QWidget | None = focus_widget
    while widget is not None:
        if isinstance(widget, HasInputScope):
            scope = widget.input_scope()
            if scope is not None:
                scopes.append(scope)
        widget = widget.parentWidget()
    return scopes


__all__ = ["active_scopes_from_focus"]

"""Qt-aware bindings provider and related helpers."""
from __future__ import annotations

from lks_utils.gui_qt.input_bindings_qt.bindings_aware_mixin import BindingsAwareMixin
from lks_utils.gui_qt.input_bindings_qt.input_bindings_provider_qt import QInputBindingsProvider
from lks_utils.gui_qt.input_bindings_qt.scope_utils import active_scopes_from_focus

__all__ = [
    "QInputBindingsProvider",
    "BindingsAwareMixin",
    "active_scopes_from_focus",
]

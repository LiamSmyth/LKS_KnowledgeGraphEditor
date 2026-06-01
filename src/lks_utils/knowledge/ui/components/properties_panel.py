"""Inspector panel: editing and ref navigation for a selected node."""
from __future__ import annotations

from lks_utils.knowledge.ui.components._properties_panel import inspector_layout as _impl

from lks_utils.knowledge.ui.components._properties_panel.inspector_layout import (
    QKnowledgeInspectorPanel as _QKnowledgeInspectorPanel,
)


class QKnowledgeInspectorPanel(_QKnowledgeInspectorPanel):
    """Thin owner shell delegating implementation to private helper modules."""


QKnowledgePropertiesPanel = QKnowledgeInspectorPanel

# Keep legacy test/helper imports stable while implementation lives in _properties_panel.
_EditableRow = _impl._EditableRow
_ReadonlyRow = _impl._ReadonlyRow
_RefListRow = _impl._RefListRow
_is_inline_structured = _impl._is_inline_structured
_flatten_inline_leaf_paths = _impl._flatten_inline_leaf_paths
_collect_inherited_slots = _impl._collect_inherited_slots


__all__ = ["QKnowledgeInspectorPanel", "QKnowledgePropertiesPanel"]

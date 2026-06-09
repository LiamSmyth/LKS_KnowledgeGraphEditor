"""Qt UI helpers for the knowledge module."""
from __future__ import annotations

from lks_utils.knowledge.ui.components.context_library_panel import QKnowledgeContextLibraryPanel
from lks_utils.knowledge.ui.components.decomposition_canvas import QKnowledgeDecompositionCanvasWidget
from lks_utils.knowledge.ui.components.graph_tab import QKnowledgeGraphTabWidget
from lks_utils.knowledge.ui.components.library_panel import QKnowledgeLibraryPanel
from lks_utils.knowledge.ui.components.graph_instance_palette_panel import QGraphInstancePalettePanel
from lks_utils.knowledge.ui.components.graph_link_type_palette_panel import QGraphLinkTypePalettePanel
from lks_utils.knowledge.ui.components.graph_type_palette_panel import QGraphTypePalettePanel
from lks_utils.knowledge.ui.components.palette_panel import QKnowledgePalettePanel
from lks_utils.knowledge.ui.components.primitive_tab import QKnowledgePrimitiveTabWidget
from lks_utils.knowledge.ui.components.q_impact_confirm_dialog import QImpactConfirmDialog
from lks_utils.knowledge.ui.components.properties_panel import (
    QKnowledgeInspectorPanel,
    QKnowledgePropertiesPanel,
)
from lks_utils.knowledge.ui.components.ref_aware_delete_dialog import QKnowledgeRefAwareDeleteDialog
from lks_utils.knowledge.ui.components.ref_picker_dialog import QKnowledgeRefPickerDialog
from lks_utils.knowledge.ui.components.repo_controls_widget import QKnowledgeRepoControlsWidget
from lks_utils.knowledge.ui.widgets.graph_canvas import QKnowledgeGraphCanvasWidget
from lks_utils.knowledge.ui.widgets.field_node_canvas_object import QKnowledgeFieldNodeCanvasObject
from lks_utils.knowledge.ui.components.workbench import QKnowledgeWorkbenchWidget

__all__ = [
    "QKnowledgeContextLibraryPanel",
    "QKnowledgeDecompositionCanvasWidget",
    "QKnowledgeGraphTabWidget",
    "QKnowledgeGraphCanvasWidget",
    "QGraphInstancePalettePanel",
    "QGraphLinkTypePalettePanel",
    "QGraphTypePalettePanel",
    "QKnowledgeLibraryPanel",
    "QKnowledgePalettePanel",
    "QKnowledgePrimitiveTabWidget",
    "QImpactConfirmDialog",
    "QKnowledgeInspectorPanel",
    "QKnowledgePropertiesPanel",
    "QKnowledgeRefAwareDeleteDialog",
    "QKnowledgeRefPickerDialog",
    "QKnowledgeRepoControlsWidget",
    "QKnowledgeFieldNodeCanvasObject",
    "QKnowledgeWorkbenchWidget",
]

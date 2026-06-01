"""Reusable composite UI components for the knowledge module."""
from __future__ import annotations

from lks_utils.knowledge.ui.components.context_library_panel import QKnowledgeContextLibraryPanel
from lks_utils.knowledge.ui.components.field_row_factory import FieldRowFactory
from lks_utils.knowledge.ui.components.graph_instance_palette_panel import QGraphInstancePalettePanel
from lks_utils.knowledge.ui.components.graph_link_type_palette_panel import QGraphLinkTypePalettePanel
from lks_utils.knowledge.ui.components.graph_type_palette_panel import QGraphTypePalettePanel
from lks_utils.knowledge.ui.components.library_panel import QKnowledgeLibraryPanel
from lks_utils.knowledge.ui.components.link_instances_library_panel import QKnowledgeLinkInstancesLibraryPanel
from lks_utils.knowledge.ui.components.link_instances_tab import QKnowledgeLinkInstancesTabWidget
from lks_utils.knowledge.ui.components.palette_panel import QKnowledgePalettePanel
from lks_utils.knowledge.ui.components.q_impact_confirm_dialog import QImpactConfirmDialog
from lks_utils.knowledge.ui.components.q_init_repo_dialog import QInitRepoDialog
from lks_utils.knowledge.ui.components.properties_panel import (
    QKnowledgeInspectorPanel,
    QKnowledgePropertiesPanel,
)
from lks_utils.knowledge.ui.components.ref_aware_delete_dialog import QKnowledgeRefAwareDeleteDialog
from lks_utils.knowledge.ui.components.ref_picker_dialog import QKnowledgeRefPickerDialog
from lks_utils.knowledge.ui.components.type_picker_dialog import QKnowledgeTypePickerDialog
from lks_utils.knowledge.ui.components.repo_controls_widget import QKnowledgeRepoControlsWidget

__all__ = [
    "QKnowledgeContextLibraryPanel",
    "QKnowledgeInspectorPanel",
    "QKnowledgeLibraryPanel",
    "QKnowledgeLinkInstancesLibraryPanel",
    "QKnowledgeLinkInstancesTabWidget",
    "QKnowledgePalettePanel",
    "QKnowledgePropertiesPanel",
    "QImpactConfirmDialog",
    "QKnowledgeRefAwareDeleteDialog",
    "QKnowledgeRefPickerDialog",
    "QKnowledgeTypePickerDialog",
    "QKnowledgeRepoControlsWidget",
    "QInitRepoDialog",
    "FieldRowFactory",
    "QGraphInstancePalettePanel",
    "QGraphLinkTypePalettePanel",
    "QGraphTypePalettePanel",
]

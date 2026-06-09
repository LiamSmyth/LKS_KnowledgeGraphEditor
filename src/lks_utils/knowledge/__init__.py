"""Knowledge-system primitives for EAV/ULID graph authoring."""
from __future__ import annotations

from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.legacy_migrator import (
    migrate_node_dict,
    migrate_node_dicts,
    migrate_slot_dict,
    migrate_type_node_slots,
)
from lks_utils.knowledge.graph_layout import build_graph_layout
from lks_utils.knowledge.graph_service import GraphService
from lks_utils.knowledge.integrity_issue import IntegrityIssue
from lks_utils.knowledge.integrity_repairer import (
    IntegrityRepairResult,
    IntegrityRepairer,
)
from lks_utils.knowledge.integrity_reporter import IntegrityReporter
from lks_utils.knowledge.instance_validator import InstanceValidator
from lks_utils.knowledge.mutator import Mutator
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.resolver import Resolver
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_slot import (
    NodeSlot,
    PropertyCardinality,
    PropertyDefinition,
    PropertyValueMode,
    SlotSource,
)
from lks_utils.knowledge.models.type import TypeView, as_type, is_type, make_type
from lks_utils.knowledge.multi_repo_index import MultiRepoIndex
from lks_utils.knowledge.ui.widgets.field_node_canvas_object import QKnowledgeFieldNodeCanvasObject
from lks_utils.knowledge.ui.components.field_row_factory import FieldRowFactory
from lks_utils.knowledge.ui.components.decomposition_canvas import QKnowledgeDecompositionCanvasWidget
from lks_utils.knowledge.ui.components.library_panel import QKnowledgeLibraryPanel
from lks_utils.knowledge.ui.components.ref_picker_dialog import QKnowledgeRefPickerDialog
from lks_utils.knowledge.ui.components.repo_controls_widget import QKnowledgeRepoControlsWidget
from lks_utils.knowledge.ui.components.workbench import QKnowledgeWorkbenchWidget
from lks_utils.knowledge.version_control import (
    KnowledgeVersionControl,
    RevertImpactReport,
)

__all__ = [
    "EditorSession",
    "GraphService",
    "IntegrityIssue",
    "IntegrityRepairResult",
    "IntegrityRepairer",
    "IntegrityReporter",
    "NodeId",
    "InstanceValidator",
    "Mutator",
    "Node",
    "Repository",
    "Resolver",
    "NodeSlot",
    "PropertyCardinality",
    "PropertyDefinition",
    "PropertyValueMode",
    "SlotSource",
    "TypeView",
    "MultiRepoIndex",
    "as_type",
    "build_graph_layout",
    "is_type",
    "make_type",
    "QKnowledgeFieldNodeCanvasObject",
    "QKnowledgeDecompositionCanvasWidget",
    "QKnowledgeLibraryPanel",
    "QKnowledgeRefPickerDialog",
    "QKnowledgeRepoControlsWidget",
    "QKnowledgeWorkbenchWidget",
    "KnowledgeVersionControl",
    "RevertImpactReport",
    "FieldRowFactory",
    "migrate_node_dict",
    "migrate_node_dicts",
    "migrate_slot_dict",
    "migrate_type_node_slots",
]

"""Knowledge model types."""
from __future__ import annotations

from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.graph_view_node_proxy import GraphViewNodeProxy
from lks_utils.knowledge.models.node_slot import (
    NodeSlot,
    PropertyCardinality,
    PropertyDefinition,
    PropertyValueMode,
    SlotSource,
)
from lks_utils.knowledge.models.type import TypeView, as_type, is_type, make_type

__all__ = [
    "NodeId",
    "Node",
    "GraphView",
    "GraphViewNodeProxy",
    "GraphViewEdgeProxy",
    "NodeSlot",
    "PropertyCardinality",
    "PropertyDefinition",
    "PropertyValueMode",
    "SlotSource",
    "TypeView",
    "as_type",
    "is_type",
    "make_type",
]

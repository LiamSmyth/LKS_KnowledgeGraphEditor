"""Data interface exports for knowledge UI/runtime bridging."""
from __future__ import annotations

from lks_utils.knowledge.data_interface.db_adapter import DBAdapter
from lks_utils.knowledge.data_interface.link_mutation_bridge import LinkMutationBridge
from lks_utils.knowledge.data_interface.link_serializer import (
    LinkSerializer,
    NodeSaveSplit,
)
from lks_utils.knowledge.data_interface.ui_memory_bridge import UIMemoryBridge

__all__ = [
    "DBAdapter",
    "LinkMutationBridge",
    "LinkSerializer",
    "NodeSaveSplit",
    "UIMemoryBridge",
]

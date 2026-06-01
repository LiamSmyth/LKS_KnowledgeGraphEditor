"""PropertyType extension system for the knowledge graph.

This module provides the core abstraction for extensible value types in the knowledge system.
A PropertyType bundles codec + validator + editor/display widget classes, enabling new value
types to be added with ~50 LOC + 1 register() call, with zero edits to kernel code.

Public API:
- PropertyType: ABC for all value type implementations
- PropertyCapabilities: frozen dataclass of capability flags
- SlotContext: frozen context passed to PropertyType methods
- RepositoryReadProtocol: read-only repository access protocol
- PropertyTypeRegistry: singleton registry for value type lookup
"""
from __future__ import annotations

from .property_capabilities import PropertyCapabilities
from .property_type import PropertyType
from .registry import PROPERTY_TYPE_REGISTRY, PropertyTypeRegistry
from .slot_context import RepositoryReadProtocol, SlotContext

__all__ = [
    "PropertyType",
    "PropertyCapabilities",
    "SlotContext",
    "RepositoryReadProtocol",
    "PropertyTypeRegistry",
    "PROPERTY_TYPE_REGISTRY",
]

"""Layout and MIME constants for the knowledge decomposition canvas widget."""
from __future__ import annotations

MIME_KNOWLEDGE_PALETTE_COMPONENT = "application/x-lks-knowledge-palette-component"

# Layout constants (Y-UP world space: y1 > y0, y1 = visual TOP)
ROOT_W = 460.0
INSTANCE_ROOT_W = 400.0
ROOT_X0 = 60.0
ROOT_Y0 = 300.0
ROOT_H_BASE = 80.0
ROW_H = 22.0
VERT_GAP = 60.0
CHILD_W = 300.0
CHILD_H = 90.0
CHILD_GAP = 36.0
TYPE_CARD_W = 260.0
TYPE_CARD_GAP = 30.0
TYPE_PROPERTY_EDGE_LABEL = "owns"


__all__ = [
    "MIME_KNOWLEDGE_PALETTE_COMPONENT",
    "ROOT_W",
    "INSTANCE_ROOT_W",
    "ROOT_X0",
    "ROOT_Y0",
    "ROOT_H_BASE",
    "ROW_H",
    "VERT_GAP",
    "CHILD_W",
    "CHILD_H",
    "CHILD_GAP",
    "TYPE_CARD_W",
    "TYPE_CARD_GAP",
    "TYPE_PROPERTY_EDGE_LABEL",
]

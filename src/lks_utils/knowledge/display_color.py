"""Display color helpers for knowledge objects.

Display color is optional metadata. When absent, a deterministic color is
derived from a stable seed (typically an object's id).
"""
from __future__ import annotations

import colorsys
import hashlib
import random
import re
from typing import Literal

from lks_utils.knowledge.default_theme import (
    LINK_EXTENDS_COLOR,
    LINK_INSTANCE_OF_COLOR,
    LINK_SLOT_REF_COLOR,
)
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
from lks_utils.knowledge.models.node import Node
from lks_utils.theme.color import Color

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
# Keep explicit colors for reserved system link types so seeded assets render
# with stable semantic colors even when no per-repo override is present.
_BUILTIN_LINK_TYPE_COLORS: dict[str, str] = {
    SLOT_REF_LINK_TYPE_ID: LINK_SLOT_REF_COLOR,
    EXTENDS_LINK_TYPE_ID: LINK_EXTENDS_COLOR,
    INSTANCE_OF_LINK_TYPE_ID: LINK_INSTANCE_OF_COLOR,
}


def normalize_display_color(value: object) -> str | None:
    """Normalize a display color to #RRGGBB or return None.

    Accepts:
    - None
    - #RRGGBB strings
    - lks_utils.theme.color.Color
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if _HEX_COLOR_RE.fullmatch(text):
            return text.lower()
        return None
    if isinstance(value, Color):
        return f"#{value.r:02x}{value.g:02x}{value.b:02x}"
    return None


def seeded_display_color(seed: str, *, variant: Literal["bright", "dim"] = "bright") -> str:
    """Return a deterministic seeded color from a seed string.

    Variants:
    - bright: for links rendered directly on dark graph backgrounds
    - dim: for header fills with light text rendered on top
    """
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    hue = rng.random()
    if variant == "bright":
        sat = 0.62 + (0.28 * rng.random())
        lightness = 0.54 + (0.18 * rng.random())
    else:
        sat = 0.52 + (0.28 * rng.random())
        lightness = 0.15 + (0.09 * rng.random())
    r, g, b = colorsys.hls_to_rgb(hue, lightness, sat)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def effective_link_type_display_color(link_type: LinkType) -> str:
    """Resolve link type display color with deterministic fallback."""
    override = normalize_display_color(link_type.display_color)
    if override is not None:
        return override
    builtin = _BUILTIN_LINK_TYPE_COLORS.get(str(link_type.id))
    if builtin is not None:
        return builtin
    return seeded_display_color(str(link_type.id), variant="bright")


def effective_node_display_color(node: Node, type_node: Node | None = None) -> str:
    """Resolve node display color with deterministic fallback.

    Rules:
    - If node has explicit override, use it.
    - For instances, inherit override from type when available.
    - Otherwise, derive by stable seed:
      - type node: node.id
      - instance with type: type id
      - untyped instance: node.id
    """
    override = normalize_display_color(node.display_color)
    if override is not None:
        return override

    if type_node is not None:
        type_override = normalize_display_color(type_node.display_color)
        if type_override is not None:
            return type_override
        return seeded_display_color(str(type_node.id), variant="dim")

    if node.category == "_type":
        return seeded_display_color(str(node.id), variant="dim")

    if node.type_id is not None:
        return seeded_display_color(str(node.type_id), variant="dim")

    return seeded_display_color(str(node.id), variant="dim")


__all__ = [
    "effective_link_type_display_color",
    "effective_node_display_color",
    "normalize_display_color",
    "seeded_display_color",
]

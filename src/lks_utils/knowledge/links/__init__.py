"""Semantic link model exports for the knowledge module."""
from __future__ import annotations

from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType, SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_slot_ref import (
    clear_slot_ref_links,
    create_slot_ref_links,
    make_slot_ref_link_type,
    replace_slot_ref_links,
)
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
    clear_extends_edge,
    clear_instance_of_edge,
    make_extends_link_type,
    make_instance_of_link_type,
    set_extends_edge,
    set_instance_of_edge,
    validate_extends_link_type,
    validate_instance_of_link_type,
)

__all__ = [
    "LinkInstance",
    "LinkType",
    "SLOT_REF_LINK_TYPE_ID",
    "clear_slot_ref_links",
    "create_slot_ref_links",
    "make_slot_ref_link_type",
    "replace_slot_ref_links",
    "EXTENDS_LINK_TYPE_ID",
    "INSTANCE_OF_LINK_TYPE_ID",
    "make_extends_link_type",
    "make_instance_of_link_type",
    "validate_extends_link_type",
    "validate_instance_of_link_type",
    "set_extends_edge",
    "clear_extends_edge",
    "set_instance_of_edge",
    "clear_instance_of_edge",
]

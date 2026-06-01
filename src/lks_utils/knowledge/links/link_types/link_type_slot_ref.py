"""Helpers for the reserved slot_ref link relation."""
from __future__ import annotations

from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType, SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.default_theme import LINK_SLOT_REF_COLOR


def make_slot_ref_link_type() -> LinkType:
    """Return the reserved system LinkType definition for slot references."""
    return LinkType(
        id=SLOT_REF_LINK_TYPE_ID,
        name="slot_ref",
        inverse_name="slot_ref_of",
        description="System relation for slot-backed references.",
        source_type_constraint=None,
        target_type_constraint=None,
        cardinality="many",
        is_system=True,
        display_color=LINK_SLOT_REF_COLOR,
    )



def create_slot_ref_links(
    *,
    source_node_id: str,
    slot_name: str,
    target_node_ids: list[str],
) -> list[LinkInstance]:
    """Create atomic slot_ref edges for a source+slot pair."""
    deduped_target_ids: list[str] = list(dict.fromkeys(target_node_ids))
    return [
        LinkInstance(
            link_type_id=SLOT_REF_LINK_TYPE_ID,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            source_slot_name=slot_name,
        )
        for target_node_id in deduped_target_ids
    ]


def clear_slot_ref_links(
    *,
    links: list[LinkInstance],
    source_node_id: str,
    slot_name: str,
) -> list[LinkInstance]:
    """Drop all slot_ref links for one (source, slot_name) pair."""
    return [
        link
        for link in links
        if not _is_matching_slot_ref(
            link=link,
            source_node_id=source_node_id,
            slot_name=slot_name,
        )
    ]


def replace_slot_ref_links(
    *,
    links: list[LinkInstance],
    source_node_id: str,
    slot_name: str,
    target_node_ids: list[str],
) -> list[LinkInstance]:
    """Replace a source+slot pair with a fresh fan-out set of target edges."""
    cleaned = clear_slot_ref_links(
        links=links,
        source_node_id=source_node_id,
        slot_name=slot_name,
    )
    replacements = create_slot_ref_links(
        source_node_id=source_node_id,
        slot_name=slot_name,
        target_node_ids=target_node_ids,
    )
    return cleaned + replacements


def _is_matching_slot_ref(*, link: LinkInstance, source_node_id: str, slot_name: str) -> bool:
    if link.link_type_id != SLOT_REF_LINK_TYPE_ID:
        return False
    if link.source_node_id != source_node_id:
        return False
    return link.source_slot_name == slot_name


__all__ = [
    "SLOT_REF_LINK_TYPE_ID",
    "clear_slot_ref_links",
    "create_slot_ref_links",
    "make_slot_ref_link_type",
    "replace_slot_ref_links",
]

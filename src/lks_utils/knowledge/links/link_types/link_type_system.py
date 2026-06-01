"""Helpers for reserved system link relations beyond slot_ref."""
from __future__ import annotations

from ulid import ULID

from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType


EXTENDS_LINK_TYPE_ID = "01JTVYQMDM2APAK2EZ4AA8YJ03"
INSTANCE_OF_LINK_TYPE_ID = "01JTVYQMDM2APAK2EZ4AA8YJ04"


def make_extends_link_type() -> LinkType:
    """Return the system LinkType definition for type inheritance edges."""
    return LinkType(
        id=EXTENDS_LINK_TYPE_ID,
        name="extends",
        inverse_name="extended_by",
        description="System relation modeling strict type inheritance.",
        source_type_constraint="Type",
        target_type_constraint="Type",
        cardinality="one",
        is_system=True,
    )


def validate_extends_link_type(link_type: LinkType) -> None:
    """Validate that a LinkType instance matches the reserved extends contract."""
    if link_type.name != "extends":
        raise ValueError("extends LinkType must use name='extends'")
    if link_type.source_type_constraint != "Type":
        raise ValueError(
            "extends LinkType source_type_constraint must be 'Type'")
    if link_type.target_type_constraint != "Type":
        raise ValueError(
            "extends LinkType target_type_constraint must be 'Type'")
    if link_type.cardinality != "one":
        raise ValueError("extends LinkType cardinality must be 'one'")

    # Keep this relation deterministic so repositories can seed it once.
    if str(link_type.id) != EXTENDS_LINK_TYPE_ID:
        raise ValueError("extends LinkType id must match EXTENDS_LINK_TYPE_ID")
    ULID.from_str(str(link_type.id))


def make_instance_of_link_type() -> LinkType:
    """Return the system LinkType definition for instance-to-type edges."""
    return LinkType(
        id=INSTANCE_OF_LINK_TYPE_ID,
        name="instance_of",
        inverse_name="has_instance",
        description="System relation mapping an instance node to its type node.",
        source_type_constraint="Instance",
        target_type_constraint="Type",
        cardinality="one",
        is_system=True,
    )


def validate_instance_of_link_type(link_type: LinkType) -> None:
    """Validate that a LinkType instance matches the reserved instance_of contract."""
    if link_type.name != "instance_of":
        raise ValueError("instance_of LinkType must use name='instance_of'")
    if link_type.source_type_constraint != "Instance":
        raise ValueError(
            "instance_of LinkType source_type_constraint must be 'Instance'")
    if link_type.target_type_constraint != "Type":
        raise ValueError(
            "instance_of LinkType target_type_constraint must be 'Type'")
    if link_type.cardinality != "one":
        raise ValueError("instance_of LinkType cardinality must be 'one'")

    if str(link_type.id) != INSTANCE_OF_LINK_TYPE_ID:
        raise ValueError(
            "instance_of LinkType id must match INSTANCE_OF_LINK_TYPE_ID")
    ULID.from_str(str(link_type.id))


__all__ = [
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


# ---------------------------------------------------------------------------
# Edge helpers — cardinality-one; no orphans, no duplicates
# ---------------------------------------------------------------------------


def set_extends_edge(
    links: list[LinkInstance],
    *,
    source_node_id: str,
    target_type_id: str,
) -> list[LinkInstance]:
    """Replace any existing 'extends' edge from *source* with a new one pointing to *target*.

    Cardinality is enforced: at most one extends edge per source node.
    """
    cleaned = clear_extends_edge(links, source_node_id=source_node_id)
    new_edge = LinkInstance(
        link_type_id=EXTENDS_LINK_TYPE_ID,
        source_node_id=source_node_id,
        target_node_id=target_type_id,
    )
    return cleaned + [new_edge]


def clear_extends_edge(
    links: list[LinkInstance],
    *,
    source_node_id: str,
) -> list[LinkInstance]:
    """Remove the 'extends' edge from *source_node_id*, if any."""
    return [
        link
        for link in links
        if not (
            link.link_type_id == EXTENDS_LINK_TYPE_ID
            and link.source_node_id == source_node_id
        )
    ]


def set_instance_of_edge(
    links: list[LinkInstance],
    *,
    source_node_id: str,
    target_type_id: str,
) -> list[LinkInstance]:
    """Replace any existing 'instance_of' edge from *source* with a new one pointing to *target*.

    Cardinality is enforced: at most one instance_of edge per source node.
    """
    cleaned = clear_instance_of_edge(links, source_node_id=source_node_id)
    new_edge = LinkInstance(
        link_type_id=INSTANCE_OF_LINK_TYPE_ID,
        source_node_id=source_node_id,
        target_node_id=target_type_id,
    )
    return cleaned + [new_edge]


def clear_instance_of_edge(
    links: list[LinkInstance],
    *,
    source_node_id: str,
) -> list[LinkInstance]:
    """Remove the 'instance_of' edge from *source_node_id*, if any."""
    return [
        link
        for link in links
        if not (
            link.link_type_id == INSTANCE_OF_LINK_TYPE_ID
            and link.source_node_id == source_node_id
        )
    ]

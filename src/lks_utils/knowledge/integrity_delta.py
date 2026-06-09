"""Incremental integrity cache updates for structural mutations."""
from __future__ import annotations

from dataclasses import dataclass

from lks_utils.knowledge.repository import Repository

IntegrityFingerprint = tuple[
    frozenset[str],
    frozenset[tuple[str, str, str, str]],
    frozenset[str],
]


def build_integrity_fingerprint(repository: Repository) -> IntegrityFingerprint:
    """Build the structural signature used to invalidate integrity cache."""
    node_ids = frozenset(str(node.id) for node in repository.list_nodes())
    link_tuples = frozenset(
        (
            str(link.id),
            str(link.source_node_id),
            str(link.target_node_id),
            str(link.link_type_id),
        )
        for link in repository.list_links()
    )
    link_type_ids = frozenset(
        str(link_type.id) for link_type in repository.list_link_types()
    )
    return (node_ids, link_tuples, link_type_ids)


@dataclass(frozen=True, slots=True)
class IntegrityDelta:
    """Known structural removals after delete / link-structure mutate."""

    removed_link_ids: frozenset[str] = frozenset()
    removed_node_ids: frozenset[str] = frozenset()

    @classmethod
    def from_link_ids(cls, link_ids: tuple[str, ...] | frozenset[str]) -> IntegrityDelta:
        """Build a delta that drops removed link ids from the integrity cache."""
        if isinstance(link_ids, frozenset):
            removed = link_ids
        else:
            removed = frozenset(link_ids)
        return cls(removed_link_ids=removed)


def apply_integrity_delta_to_fingerprint(
    fingerprint: IntegrityFingerprint,
    delta: IntegrityDelta,
) -> IntegrityFingerprint:
    """Return an updated fingerprint with removed entities excised."""
    node_ids, link_tuples, link_type_ids = fingerprint
    new_nodes = node_ids - delta.removed_node_ids
    new_links = frozenset(
        entry for entry in link_tuples if entry[0] not in delta.removed_link_ids
    )
    return (new_nodes, new_links, link_type_ids)


def scrub_integrity_reasons(
    reasons_by_object: dict[str, list[str]],
    delta: IntegrityDelta,
) -> dict[str, list[str]]:
    """Remove cache entries for deleted links and nodes."""
    if not delta.removed_link_ids and not delta.removed_node_ids:
        return reasons_by_object

    removed = delta.removed_link_ids | delta.removed_node_ids
    scrubbed: dict[str, list[str]] = {}
    for object_id, reasons in reasons_by_object.items():
        if object_id in removed:
            continue
        kept = [
            reason
            for reason in reasons
            if not any(token in reason for token in removed)
        ]
        if kept:
            scrubbed[object_id] = kept
    return scrubbed


def reconcile_integrity_fingerprint(
    repository: Repository,
    cached: IntegrityFingerprint | None,
    delta: IntegrityDelta,
) -> IntegrityFingerprint | None:
    """Apply *delta* to *cached* or rebuild when cache is absent."""
    if cached is None:
        return build_integrity_fingerprint(repository)
    return apply_integrity_delta_to_fingerprint(cached, delta)


__all__ = [
    "IntegrityDelta",
    "IntegrityFingerprint",
    "apply_integrity_delta_to_fingerprint",
    "build_integrity_fingerprint",
    "reconcile_integrity_fingerprint",
    "scrub_integrity_reasons",
]

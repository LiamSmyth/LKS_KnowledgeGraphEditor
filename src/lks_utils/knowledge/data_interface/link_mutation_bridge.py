"""Data-interface bridge for ad-hoc link CRUD from UI widgets."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_utils.knowledge._editor_session.selection import resolve_ref_type_to_type_ids
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.models.type import is_type
from lks_utils.knowledge.repository import Repository

if TYPE_CHECKING:
    from lks_utils.knowledge.io import KnowledgeIO


class LinkMutationBridge:
    """Route ad-hoc link mutations through the data-interface seam."""

    def __init__(self, source: Repository | KnowledgeIO) -> None:
        self._io: KnowledgeIO | None = None
        if isinstance(source, Repository):
            self._repository = source
        else:
            self._io = source
            self._repository = source.repository

    def list_outgoing_ad_hoc_links(self, source_node_id: str) -> list[LinkInstance]:
        """Return non-system outgoing links for one source node."""
        link_type_cache: dict[str, bool] = {}
        result: list[LinkInstance] = []
        for link in self._repository.list_links():
            if str(link.source_node_id) != source_node_id:
                continue
            lt_id = str(link.link_type_id)
            if lt_id not in link_type_cache:
                try:
                    lt = self._repository.get_link_type(lt_id)
                    link_type_cache[lt_id] = lt.is_system
                except KeyError:
                    link_type_cache[lt_id] = False
            if not link_type_cache[lt_id]:
                result.append(link)
        return result

    def list_incoming_ad_hoc_links(self, target_node_id: str) -> list[LinkInstance]:
        """Return non-system incoming links for one target node."""
        link_type_cache: dict[str, bool] = {}
        result: list[LinkInstance] = []
        for link in self._repository.list_links():
            if str(link.target_node_id) != target_node_id:
                continue
            lt_id = str(link.link_type_id)
            if lt_id not in link_type_cache:
                try:
                    lt = self._repository.get_link_type(lt_id)
                    link_type_cache[lt_id] = lt.is_system
                except KeyError:
                    link_type_cache[lt_id] = False
            if not link_type_cache[lt_id]:
                result.append(link)
        return result

    def create_ad_hoc_link(
        self,
        *,
        link_type_id: str,
        source_node_id: str,
        target_node_id: str,
    ) -> tuple[LinkInstance, object | None]:
        """Create and store one ad-hoc link record."""
        try:
            link_type = self._repository.get_link_type(link_type_id)
        except KeyError as exc:
            raise ValueError(f"Unknown link_type_id: {link_type_id}") from exc

        if link_type.is_system:
            raise ValueError(
                f"System link type {link_type_id!r} must be managed by its own write-through path")

        try:
            source_node = self._repository.get(source_node_id)
        except KeyError as exc:
            raise ValueError(
                f"Unknown source node id: {source_node_id}") from exc

        try:
            target_node = self._repository.get(target_node_id)
        except KeyError as exc:
            raise ValueError(
                f"Unknown target node id: {target_node_id}") from exc

        if not self._matches_constraint(source_node, link_type.source_type_constraint):
            raise ValueError(
                f"Source node {source_node.id!s} violates "
                f"constraint {link_type.source_type_constraint!r}."
            )

        if not self._matches_constraint(target_node, link_type.target_type_constraint):
            raise ValueError(
                f"Target node {target_node.id!s} violates "
                f"constraint {link_type.target_type_constraint!r}."
            )

        existing_links = self._repository.list_links()
        duplicate = next(
            (
                existing
                for existing in existing_links
                if existing.link_type_id == link_type_id
                and existing.source_node_id == source_node_id
                and existing.target_node_id == target_node_id
            ),
            None,
        )
        if duplicate is not None:
            raise ValueError("Duplicate link triple is not allowed.")

        if link_type.cardinality == "one":
            conflict = next(
                (
                    existing
                    for existing in existing_links
                    if existing.link_type_id == link_type_id
                    and existing.source_node_id == source_node_id
                ),
                None,
            )
            if conflict is not None:
                raise ValueError(
                    "cardinality='one' permits only one outgoing link for this source/type."
                )

        link = LinkInstance(
            link_type_id=link_type_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
        )
        if self._io is None:
            self._repository.upsert_link(link)
            return link, None
        result = self._io.upsert_link(link)
        if not result.ok:
            raise ValueError(
                result.error_message or "Failed to create link")
        return link, result

    def delete_link(self, link_id: str) -> object | None:
        """Delete one link instance by id."""
        if self._io is None:
            self._repository.delete_link(link_id)
            return None
        result = self._io.remove_link(link_id)
        if not result.ok:
            raise KeyError(link_id)
        return result

    def _matches_constraint(self, node: object, constraint: str | None) -> bool:
        if constraint is None or not constraint.strip():
            return True
        normalized = constraint.strip().casefold()
        if normalized == "any":
            return True
        if normalized == "type":
            return getattr(node, "category", None) == "_type"
        if normalized == "instance":
            return getattr(node, "category", None) != "_type"

        allowed_type_ids = resolve_ref_type_to_type_ids(
            iter_types=self._repository.list_types(),
            token=normalized,
            iter_links=self._repository.list_links(),
            iter_link_types=self._repository.list_link_types(),
        )
        if allowed_type_ids:
            node_type_id = getattr(node, "type_id", None)
            if node_type_id is not None and str(node_type_id) in allowed_type_ids:
                return True
            if is_type(node) and str(getattr(node, "id", "")) in allowed_type_ids:
                return True
        return False


__all__ = ["LinkMutationBridge"]

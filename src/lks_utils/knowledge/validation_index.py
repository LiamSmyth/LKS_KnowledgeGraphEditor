"""Incremental validation index for knowledge repositories."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Literal

from PySide6.QtCore import QObject, Signal

from lks_utils.knowledge.instance_validator import InstanceValidator
from lks_utils.knowledge.integrity_reporter import IntegrityReporter
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.reverse_ref_index import ReverseRefIndex
from lks_utils.knowledge.validation_status import ValidationStatus
from lks_utils.knowledge.validation_statuses.invalid_validation_status import (
    InvalidValidationStatus,
)
from lks_utils.knowledge.validation_statuses.valid_validation_status import (
    ValidValidationStatus,
)


class ValidationIndex(QObject):
    """Tracks validation status by object id and supports incremental recompute."""

    validation_changed = Signal(object)

    def __init__(
        self,
        *,
        repository_getter: Callable[[], Repository],
        reverse_ref_index_getter: Callable[[], ReverseRefIndex] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository_getter = repository_getter
        self._reverse_ref_index_getter = reverse_ref_index_getter
        self._status_by_object_id: dict[str, ValidationStatus] = {}
        self._valid_sentinel = ValidValidationStatus()
        # Integrity cache: recompute only when links or link-types change.
        self._cached_integrity_sig: tuple[frozenset[str],
                                          frozenset[str]] | None = None
        self._cached_integrity_reasons: dict[str, list[str]] = {}

    def status_for(self, object_id: str) -> ValidationStatus:
        """Return validity status for ``object_id`` (valid sentinel by default)."""
        return self._status_by_object_id.get(object_id, self._valid_sentinel)

    def recompute(
        self,
        touched_ids: set[str] | None = None,
        *,
        impact_mode: Literal["expanded", "touched_only"] = "expanded",
    ) -> set[str]:
        """Recompute all or affected object statuses and emit changed ids."""
        repository = self._repository_getter()
        all_node_ids = {str(node.id) for node in repository.list_nodes()}
        all_link_type_ids = {str(link_type.id)
                             for link_type in repository.list_link_types()}
        all_link_ids = {str(link.id) for link in repository.list_links()}
        all_ids = all_node_ids | all_link_type_ids | all_link_ids

        impacted_ids = self._expand_impacted_ids(
            repository,
            touched_ids,
            include_referencers=impact_mode == "expanded",
        )
        if touched_ids is None:
            impacted_ids = set(all_ids)
        elif impacted_ids:
            impacted_ids |= {
                object_id for object_id in touched_ids if object_id in all_ids}

        # Reuse cached integrity results when the link/link-type structure is
        # unchanged.  Integrity issues are purely structural (dangling links /
        # link-types); they cannot change when only node *properties* are edited.
        structural_sig = (frozenset(all_link_ids),
                          frozenset(all_link_type_ids))
        if structural_sig != self._cached_integrity_sig:
            self._cached_integrity_reasons = self._integrity_reasons_by_object(
                repository
            )
            self._cached_integrity_sig = structural_sig
        issue_reasons = self._cached_integrity_reasons

        validator = InstanceValidator(repository)
        new_statuses: dict[str, ValidationStatus] = {}

        for object_id in impacted_ids:
            reasons = list(issue_reasons.get(object_id, ()))
            node = self._safe_get_node(repository, object_id)
            if node is not None:
                try:
                    validator.validate_node(node)
                except Exception as exc:
                    reasons.append(str(exc))

            if reasons:
                new_statuses[object_id] = InvalidValidationStatus(reasons)
            else:
                new_statuses[object_id] = self._valid_sentinel

        changed_ids: set[str] = set()
        for object_id in impacted_ids:
            previous = self._status_by_object_id.get(
                object_id, self._valid_sentinel)
            current = new_statuses[object_id]
            if previous.is_valid != current.is_valid or previous.reasons != current.reasons:
                changed_ids.add(object_id)

        for object_id in impacted_ids:
            current = new_statuses[object_id]
            if current.is_valid:
                self._status_by_object_id.pop(object_id, None)
            else:
                self._status_by_object_id[object_id] = current

        for object_id in impacted_ids:
            if object_id not in all_ids and object_id in self._status_by_object_id:
                self._status_by_object_id.pop(object_id, None)
                changed_ids.add(object_id)

        if changed_ids:
            self.validation_changed.emit(set(changed_ids))
        return changed_ids

    def _expand_impacted_ids(
        self,
        repository: Repository,
        touched_ids: set[str] | None,
        *,
        include_referencers: bool,
    ) -> set[str]:
        if touched_ids is None:
            return set()

        impacted = set(touched_ids)
        if not touched_ids or not include_referencers:
            return impacted

        # Use reverse_ref_index for fast O(referencers) lookup instead of O(graph) scan
        if self._reverse_ref_index_getter is not None:
            reverse_ref_index = self._reverse_ref_index_getter()
            for touched_id in touched_ids:
                referencers = reverse_ref_index.referencers_of(touched_id)
                impacted.update(referencers)
        else:
            # Fallback to O(graph) scan if reverse_ref_index not available
            for node in repository.list_nodes():
                node_id = str(node.id)
                if node.type_id is not None and str(node.type_id) in touched_ids:
                    impacted.add(node_id)

            for link in repository.list_links():
                if (
                    link.source_node_id in touched_ids
                    or link.target_node_id in touched_ids
                    or link.link_type_id in touched_ids
                ):
                    impacted.add(str(link.id))

        return impacted

    def _integrity_reasons_by_object(self, repository: Repository) -> dict[str, list[str]]:
        reasons_by_object: dict[str, list[str]] = defaultdict(list)
        for issue in IntegrityReporter().report(repository):
            targets = [
                issue.link_id,
                issue.link_type_id,
                issue.source_node_id,
                issue.target_node_id,
            ]
            detail = issue.detail or issue.code
            for target in targets:
                if isinstance(target, str) and target:
                    reasons_by_object[target].append(f"{issue.code}: {detail}")
        return reasons_by_object

    def _safe_get_node(self, repository: Repository, object_id: str):
        try:
            return repository.get(object_id)
        except KeyError:
            return None


__all__ = ["ValidationIndex"]

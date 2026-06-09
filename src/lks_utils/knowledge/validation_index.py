"""Incremental validation index for knowledge repositories."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import Literal

from PySide6.QtCore import QObject, Signal

from lks_utils.knowledge.integrity_delta import (
    IntegrityDelta,
    IntegrityFingerprint,
    apply_integrity_delta_to_fingerprint,
    build_integrity_fingerprint,
    scrub_integrity_reasons,
)
from lks_utils.knowledge.instance_validator import InstanceValidator
from lks_utils.knowledge.integrity_reporter import IntegrityReporter
from lks_utils.knowledge.projection_issue import ProjectionIssue
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
        self._cached_integrity_sig: IntegrityFingerprint | None = None
        self._cached_integrity_reasons: dict[str, list[str]] = {}
        self._projection_reasons_by_object_id: dict[str, list[str]] = {}

    def status_for(self, object_id: str) -> ValidationStatus:
        """Return validity status for ``object_id`` (valid sentinel by default)."""
        base = self._status_by_object_id.get(object_id, self._valid_sentinel)
        projection_reasons = self._projection_reasons_by_object_id.get(
            object_id, ()
        )
        if not projection_reasons:
            return base
        merged_reasons = list(base.reasons) + list(projection_reasons)
        if base.is_valid and not merged_reasons:
            return self._valid_sentinel
        if base.is_valid:
            return InvalidValidationStatus(merged_reasons)
        return InvalidValidationStatus(merged_reasons)

    def iter_invalid(self) -> Iterator[str]:
        """Yield object ids with materialized semantic, structural, or projection issues."""
        seen: set[str] = set()
        for object_id in self._status_by_object_id:
            if not self.status_for(object_id).is_valid:
                seen.add(object_id)
                yield object_id
        for object_id in self._projection_reasons_by_object_id:
            if object_id in seen:
                continue
            if not self.status_for(object_id).is_valid:
                yield object_id

    def apply_projection_issues(self, issues: list[ProjectionIssue]) -> set[str]:
        """Replace projection-layer findings and emit ``validation_changed``."""
        new_reasons: dict[str, list[str]] = defaultdict(list)
        for issue in issues:
            new_reasons[issue.object_id].append(f"{issue.code}: {issue.detail}")

        changed_ids: set[str] = set()
        old_ids = set(self._projection_reasons_by_object_id) | set(new_reasons)
        for object_id in old_ids:
            previous = tuple(self._projection_reasons_by_object_id.get(object_id, ()))
            current = tuple(new_reasons.get(object_id, ()))
            if previous != current:
                changed_ids.add(object_id)

        self._projection_reasons_by_object_id = {
            object_id: reasons
            for object_id, reasons in new_reasons.items()
            if reasons
        }

        if changed_ids:
            self.validation_changed.emit(set(changed_ids))
        return changed_ids

    def apply_integrity_delta(self, delta: IntegrityDelta) -> None:
        """Incrementally update the integrity sub-cache after structural delete."""
        if not delta.removed_link_ids and not delta.removed_node_ids:
            return
        self._cached_integrity_reasons = scrub_integrity_reasons(
            self._cached_integrity_reasons,
            delta,
        )
        if self._cached_integrity_sig is not None:
            self._cached_integrity_sig = apply_integrity_delta_to_fingerprint(
                self._cached_integrity_sig,
                delta,
            )

    def refresh_integrity_cache(self, repository: Repository) -> None:
        """Rebuild the integrity sub-cache from a full report (load/repair only)."""
        self._cached_integrity_sig = build_integrity_fingerprint(repository)
        self._cached_integrity_reasons = self._integrity_reasons_by_object(repository)

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

        structural_sig = build_integrity_fingerprint(repository)
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


__all__ = [
    "IntegrityFingerprint",
    "IntegrityDelta",
    "ValidationIndex",
    "build_integrity_fingerprint",
]

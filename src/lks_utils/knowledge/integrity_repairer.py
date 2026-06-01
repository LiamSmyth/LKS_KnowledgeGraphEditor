"""Deterministic repair engine for knowledge graph integrity issues."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from lks_utils.knowledge.integrity_issue import IntegrityIssue
from lks_utils.knowledge.integrity_reporter import IntegrityReporter
from lks_utils.knowledge.repository import Repository

RepairMode = Literal["report_only", "repair_safe", "repair_prune"]

_SAFE_REMOVAL_CODES: set[str] = {
    "dangling_link_type",
    "dangling_source_node",
    "dangling_target_node",
    "cardinality_violation",
}

_PRUNE_ONLY_REMOVAL_CODES: set[str] = {
    "source_constraint_violation",
    "target_constraint_violation",
    "slot_ref_missing_source_slot",
    "non_slot_ref_carries_source_slot",
}


class IntegrityRepairResult(BaseModel):
    """Summary of one integrity-repair execution."""

    mode: RepairMode
    issues_before: list[IntegrityIssue] = Field(default_factory=list)
    issues_after: list[IntegrityIssue] = Field(default_factory=list)
    removed_link_ids: list[str] = Field(default_factory=list)

    model_config = {
        "extra": "forbid",
    }


class IntegrityRepairer:
    """Apply deterministic integrity-repair policies to repository links."""

    def __init__(self, reporter: IntegrityReporter | None = None) -> None:
        self._reporter = reporter or IntegrityReporter()

    def repair(self, repository: Repository, *, mode: RepairMode) -> IntegrityRepairResult:
        """Run one repair pass with the specified policy mode."""
        issues_before = self._reporter.report(repository)
        if mode == "report_only":
            return IntegrityRepairResult(
                mode=mode,
                issues_before=issues_before,
                issues_after=issues_before,
                removed_link_ids=[],
            )

        removed_link_ids = self._select_links_to_remove(
            issues_before, mode=mode)
        for link_id in removed_link_ids:
            repository.delete_link(link_id)

        issues_after = self._reporter.report(repository)
        return IntegrityRepairResult(
            mode=mode,
            issues_before=issues_before,
            issues_after=issues_after,
            removed_link_ids=removed_link_ids,
        )

    def _select_links_to_remove(
        self,
        issues: list[IntegrityIssue],
        *,
        mode: RepairMode,
    ) -> list[str]:
        removable_codes = set(_SAFE_REMOVAL_CODES)
        if mode == "repair_prune":
            removable_codes.update(_PRUNE_ONLY_REMOVAL_CODES)

        link_ids: set[str] = set()
        for issue in issues:
            if issue.code not in removable_codes:
                continue
            if issue.link_id is None:
                continue
            link_ids.add(issue.link_id)
        return sorted(link_ids)


__all__ = ["IntegrityRepairResult", "IntegrityRepairer", "RepairMode"]

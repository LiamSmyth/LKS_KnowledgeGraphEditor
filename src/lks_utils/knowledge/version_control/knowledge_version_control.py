"""Knowledge repository version-control facade built on git service."""
from __future__ import annotations

from pathlib import Path

from lks_utils.knowledge.commit_info import CommitInfo
from lks_utils.knowledge.git_service import KnowledgeGitService
from lks_utils.knowledge.git_status import GitStatus
from lks_utils.knowledge.impact_entry import ImpactEntry
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.version_control.revert_impact_report import RevertImpactReport
from lks_utils.knowledge.version_control.staging_dependencies_report import (
    StagingDependenciesReport,
)


class KnowledgeVersionControl:
    """Coordinate repo-aware revert previews and git operations for knowledge data."""

    def __init__(self, *, repository: Repository, git_service: KnowledgeGitService) -> None:
        self._repository = repository
        self._git_service = git_service

    @property
    def git_service(self) -> KnowledgeGitService:
        """Return underlying git-service dependency."""
        return self._git_service

    def preview_revert(self, rel_paths: list[str]) -> RevertImpactReport:
        """Build a revert impact report from repository-relative paths."""
        normalized = [path.replace("\\", "/") for path in rel_paths if path]
        selected_paths = set(normalized)
        selected_node_ids: set[str] = set()
        selected_link_ids: set[str] = set()
        selected_link_type_ids: set[str] = set()

        for rel_path in normalized:
            # Step (a): inspect HEAD content side-effect free to know whether
            # this path exists in would-be post-revert state.
            _ = self._git_service.read_head_text(rel_path)

            path_obj = Path(rel_path)
            stem = path_obj.stem
            top = path_obj.parts[0] if path_obj.parts else ""
            if top == "nodes":
                selected_node_ids.add(stem)
            elif top == "links":
                selected_link_ids.add(stem)
            elif top == "link_types":
                selected_link_type_ids.add(stem)

        entries: list[ImpactEntry] = []
        related_files: set[str] = set()

        # Step (b/c): find would-dangle references and mark related files.
        for node in self._repository.list_nodes():
            node_id = str(node.id)
            if node_id in selected_node_ids:
                continue
            refs = _collect_slot_ref_target_ids(self._repository, node_id)
            intersects = sorted(refs.intersection(selected_node_ids))
            if intersects:
                target_id = intersects[0]
                entries.append(
                    ImpactEntry(
                        object_id=node_id,
                        object_kind="node",
                        reason=f"references reverted node {target_id}",
                    )
                )
                rel = self._node_relpath(node_id)
                if rel not in selected_paths:
                    related_files.add(rel)
            if str(node.type_id or "") in selected_node_ids:
                entries.append(
                    ImpactEntry(
                        object_id=node_id,
                        object_kind="instance",
                        reason=f"depends on reverted type node {node.type_id}",
                    )
                )
                rel = self._node_relpath(node_id)
                if rel not in selected_paths:
                    related_files.add(rel)

        for link in self._repository.list_links():
            link_id = str(link.id)
            if link_id in selected_link_ids:
                continue
            reason: str | None = None
            if link.source_node_id in selected_node_ids or link.target_node_id in selected_node_ids:
                reason = "touches reverted node"
            elif link.link_type_id in selected_link_type_ids:
                reason = f"uses reverted link type {link.link_type_id}"
            if reason is None:
                continue
            entries.append(
                ImpactEntry(
                    object_id=link_id,
                    object_kind="link",
                    reason=reason,
                )
            )
            rel = self._link_relpath(link_id)
            if rel not in selected_paths:
                related_files.add(rel)

        return RevertImpactReport(
            entries=_dedupe_entries(entries),
            related_files=related_files,
            include_related=False,
        )

    def preview_stage_dependencies(self, rel_paths: list[str]) -> StagingDependenciesReport:
        """Build a staging dependencies report for staged paths.

        This finds all changed objects that reference (via forward links) the staged
        objects, so they can optionally be staged together to avoid broken references.
        """
        normalized = [path.replace("\\", "/") for path in rel_paths if path]

        # Map paths to object IDs
        staged_node_ids: set[str] = set()
        staged_link_ids: set[str] = set()
        staged_link_type_ids: set[str] = set()

        for rel_path in normalized:
            path_obj = Path(rel_path)
            stem = path_obj.stem
            top = path_obj.parts[0] if path_obj.parts else ""
            if top == "nodes":
                staged_node_ids.add(stem)
            elif top == "links":
                staged_link_ids.add(stem)
            elif top == "link_types":
                staged_link_type_ids.add(stem)

        # Get current git status to know what's changed but unstaged
        status = self._git_service.status()
        all_changed_paths = set(status.all_modified_paths)
        staged_paths = set(normalized)
        unstaged_changed_paths = all_changed_paths - staged_paths

        # Candidates: all_candidates that are in unstaged_changed_paths
        # path -> (object_id, reason)
        candidates: dict[str, tuple[str, str]] = {}
        unstaged_candidates: dict[str, tuple[str, str]] = {}

        # Find nodes that reference staged nodes
        for node in self._repository.list_nodes():
            node_id = str(node.id)
            if node_id in staged_node_ids:
                continue  # Don't add staged items themselves
            refs = _collect_slot_ref_target_ids(self._repository, node_id)
            intersects = sorted(refs.intersection(staged_node_ids))
            if intersects:
                target_id = intersects[0]
                rel = self._node_relpath(node_id)
                reason = f"references staged node {target_id}"
                candidates[rel] = (node_id, reason)
                if rel in unstaged_changed_paths:
                    unstaged_candidates[rel] = (node_id, reason)

        # Find nodes that depend on staged type nodes
        for node in self._repository.list_nodes():
            node_id = str(node.id)
            if str(node.type_id or "") in staged_node_ids:
                rel = self._node_relpath(node_id)
                reason = f"depends on staged type node {node.type_id}"
                candidates[rel] = (node_id, reason)
                if rel in unstaged_changed_paths:
                    unstaged_candidates[rel] = (node_id, reason)

        # Find links that reference staged items
        for link in self._repository.list_links():
            link_id = str(link.id)
            if link_id in staged_link_ids:
                continue  # Don't add staged items themselves
            reason: str | None = None
            if link.source_node_id in staged_node_ids:
                reason = f"links from staged node {link.source_node_id}"
            elif link.target_node_id in staged_node_ids:
                reason = f"links to staged node {link.target_node_id}"
            elif link.link_type_id in staged_link_type_ids:
                reason = f"uses staged link type {link.link_type_id}"
            if reason is None:
                continue
            rel = self._link_relpath(link_id)
            candidates[rel] = (link_id, reason)
            if rel in unstaged_changed_paths:
                unstaged_candidates[rel] = (link_id, reason)

        return StagingDependenciesReport(
            candidates=candidates,
            unstaged_candidates=unstaged_candidates,
        )

    def revert_files(self, rel_paths: list[str], *, include_related: bool = False) -> RevertImpactReport:
        """Revert selected files and return report describing impacted records."""
        report = self.preview_revert(rel_paths)
        targets = [path.replace("\\", "/") for path in rel_paths if path]
        if include_related:
            targets.extend(sorted(report.related_files))
        if targets and "index.json" not in targets:
            targets.append("index.json")
        for rel_path in targets:
            self._git_service.revert_file(rel_path)
        return RevertImpactReport(
            entries=list(report.entries),
            related_files=set(report.related_files),
            include_related=include_related,
        )

    def status(self) -> GitStatus:
        """Forward to git service status."""
        return self._git_service.status()

    def diff_file(self, rel_path: str, *, staged: bool = False) -> str:
        """Forward to git service diff_file."""
        return self._git_service.diff_file(rel_path, staged=staged)

    def stage(self, rel_paths: list[str]) -> None:
        """Forward to git service stage."""
        self._git_service.stage(rel_paths)

    def stage_all(self) -> None:
        """Forward to git service stage_all."""
        self._git_service.stage_all()

    def unstage(self, rel_paths: list[str]) -> None:
        """Forward to git service unstage."""
        self._git_service.unstage(rel_paths)

    def unstage_all(self) -> None:
        """Forward to git service unstage_all."""
        self._git_service.unstage_all()

    def commit(self, message: str) -> str | None:
        """Forward to git service commit."""
        return self._git_service.commit(message)

    def commit_all(self, message: str) -> str | None:
        """Forward to git service commit_all."""
        return self._git_service.commit_all(message)

    def recent_commits(self, *, limit: int = 20) -> list[CommitInfo]:
        """Forward to git service recent_commits."""
        return self._git_service.recent_commits(limit=limit)

    def auto_message(self, status: GitStatus | None = None) -> str:
        """Forward to git service auto_message."""
        return self._git_service.auto_message(status)

    def revert_to_commit(self, sha: str) -> None:
        """Forward to git service revert_to_commit."""
        self._git_service.revert_to_commit(sha)

    def _node_relpath(self, node_id: str) -> str:
        return f"nodes/{node_id}.json"

    def _link_relpath(self, link_id: str) -> str:
        return f"links/{link_id}.json"


def _collect_slot_ref_target_ids(repository: Repository, source_node_id: str) -> set[str]:
    return {
        str(link.target_node_id)
        for link in repository.list_links()
        if (
            link.link_type_id == SLOT_REF_LINK_TYPE_ID
            and str(link.source_node_id) == source_node_id
        )
    }


def _dedupe_entries(entries: list[ImpactEntry]) -> list[ImpactEntry]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ImpactEntry] = []
    for entry in entries:
        key = (entry.object_id, entry.object_kind, entry.reason)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


__all__ = ["KnowledgeVersionControl"]

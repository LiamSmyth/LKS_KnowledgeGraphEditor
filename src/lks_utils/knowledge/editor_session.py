"""In-memory editing session for knowledge types and node instances."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Literal

from lks_utils.knowledge._editor_session.clipboard import adopt_repository_snapshot
from lks_utils.knowledge._editor_session.selection import resolve_ref_type_to_type_ids
from lks_utils.knowledge._editor_session.undo_stack import compute_all_touched_ids
from lks_utils.knowledge.editor_session_types import (
    FatalValidationError,
    LastSaveStatus,
    MutationResult,
    SessionChangeEvent,
)
from lks_utils.knowledge.git_service import KnowledgeGitService
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node_slot import NodeSlot
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.mutator import Mutator
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.repository_indexes import RepositoryIndexes
from lks_utils.knowledge.reverse_ref_index import ReverseRefIndex
from lks_utils.knowledge.projection_validator import ProjectionValidator
from lks_utils.knowledge.validation_index import ValidationIndex
from lks_utils.knowledge.canvas.canvas_io import CanvasIO
from lks_utils.knowledge.io import KnowledgeIO, OperationResult, ValidationMode
from lks_utils.knowledge.io.mutation_effects import MutationEffects, MutationKind
from lks_utils.knowledge.io.mutation_policy import CanvasHygieneHint, resolve_policy
from lks_utils.knowledge.projection_hygiene import ProjectionHygiene
from lks_utils.profiling import profile_action

_SESSION_LABEL_TO_KIND: dict[str, MutationKind] = {
    "upsert_node": MutationKind.NODE_UPSERT,
    "delete_node": MutationKind.NODE_DELETE,
    "upsert_link": MutationKind.LINK_STRUCTURE,
    "delete_link": MutationKind.LINK_STRUCTURE,
    "patch_node_props": MutationKind.INSTANCE_PROPERTY,
}


class EditorSession:
    """Maintains an editable repository of types and node instances."""

    def __init__(self, *, source_repo_id: str = "default") -> None:
        self._repository = Repository(source_repo_id=source_repo_id)
        self._listeners: list[Callable[[str], None]] = []
        self._change_listeners: list[Callable[[SessionChangeEvent], None]] = []
        self._repo_loaded_listeners: list[Callable[[Path], None]] = []
        self._repo_saved_listeners: list[Callable[[Path], None]] = []
        self._repository_root: Path | None = None
        self._is_dirty: bool = False
        self._last_save_status: LastSaveStatus = LastSaveStatus.OK
        self._last_save_error: str | None = None
        self._git_service: KnowledgeGitService | None = None
        self._mutation_lock = RLock()
        self._current_change_touched_ids: frozenset[str] | None = None
        self._current_change_event: SessionChangeEvent | None = None
        self._reverse_ref_index: RepositoryIndexes = RepositoryIndexes()
        self._validation_index = ValidationIndex(
            repository_getter=lambda: self._repository,
            reverse_ref_index_getter=lambda: self._reverse_ref_index,
        )
        self._rebuild_io()

    # ------------------------------------------------------------------
    # Listener API
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked on session changes."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str], None]) -> None:
        """Remove a previously registered callback."""
        self._listeners = [cb for cb in self._listeners if cb is not callback]

    def add_change_listener(self, callback: Callable[[SessionChangeEvent], None]) -> None:
        """Register a callback invoked with typed session change events."""
        self._change_listeners.append(callback)

    def remove_change_listener(self, callback: Callable[[SessionChangeEvent], None]) -> None:
        """Remove a previously registered typed session change callback."""
        self._change_listeners = [
            cb for cb in self._change_listeners if cb is not callback
        ]

    def add_repo_loaded_listener(self, callback: Callable[[Path], None]) -> None:
        """Register callback invoked when a repository is loaded/newly created."""
        self._repo_loaded_listeners.append(callback)

    def add_repo_saved_listener(self, callback: Callable[[Path], None]) -> None:
        """Register callback invoked after a repository save operation."""
        self._repo_saved_listeners.append(callback)

    @property
    def is_dirty(self) -> bool:
        """Return whether there are unsaved direct-edit changes."""
        return self._is_dirty

    @property
    def repository_root(self) -> Path | None:
        """Return the active repository root path, if configured."""
        return self._repository_root

    @property
    def source_repo_id(self) -> str:
        """Return the source repository identifier from the active repository."""
        return self._repository.source_repo_id

    @property
    def validation_index(self) -> ValidationIndex:
        """Return the validation index for object-level status lookups."""
        return self._validation_index

    @property
    def reverse_ref_index(self) -> RepositoryIndexes:
        """Return the reverse reference index for efficient impact expansion."""
        return self._reverse_ref_index

    @property
    def repository(self) -> Repository:
        """Return the active in-memory repository snapshot."""
        return self._repository

    @property
    def knowledge_io(self) -> KnowledgeIO:
        """Return the KnowledgeIO facade for read/query and bridge wiring."""
        return self._io

    @property
    def last_save_status(self) -> LastSaveStatus:
        """Return persistence status of the most recent write-bearing operation."""
        return self._last_save_status

    @property
    def last_save_error(self) -> str | None:
        """Return last persistence error message when ``last_save_status`` is failed."""
        return self._last_save_error

    @property
    def git_service(self) -> KnowledgeGitService | None:
        """Return git status service for the configured repository root, if available."""
        return self._git_service

    @property
    def current_change_touched_ids(self) -> frozenset[str] | None:
        """Return touched ids for the in-flight ``node`` change notification.

        This is only populated while listeners are being notified for a mutation.
        """
        return self._current_change_touched_ids

    @property
    def current_change_event(self) -> SessionChangeEvent | None:
        """Return typed metadata for the in-flight change notification."""
        return self._current_change_event

    def node_change_touches(self, object_ids: set[str] | list[str] | tuple[str, ...]) -> bool:
        """Return whether the in-flight ``node`` change touches any ids.

        When touched ids are unavailable (legacy/coarse notifications), this
        returns ``True`` so callers preserve prior refresh behavior.
        """
        touched_ids = self._current_change_touched_ids
        if touched_ids is None:
            return True
        for object_id in object_ids:
            if str(object_id) in touched_ids:
                return True
        return False

    # ------------------------------------------------------------------
    # Node access
    # ------------------------------------------------------------------

    def _rebuild_io(self) -> None:
        """Reconstruct the KnowledgeIO facade after repository or root changes."""
        self._io = KnowledgeIO(
            repository=self._repository,
            reverse_ref_index=self._reverse_ref_index,
            validation_index=self._validation_index,
            repository_root=self._repository_root,
        )
        # Re-point the validation getter at io.repository so that apply_op's
        # internal recompute reads the post-mutation snapshot rather than the
        # pre-mutation editor_session._repository.
        self._validation_index._repository_getter = lambda: self._io.repository  # noqa: SLF001

    def _adopt_io_repository_preserving_identity(self) -> None:
        """Mirror KnowledgeIO's repository snapshot into ``self._repository``.

        KnowledgeIO mutates in place; EditorSession keeps a stable repository object
        so legacy callers that cache ``session._repository`` continue to see updates.
        """
        io_repo = self._io.repository
        if self._repository is io_repo:
            return

        # Keep object identity stable while adopting latest snapshot internals.
        adopt_repository_snapshot(target=self._repository, source=io_repo)
        self._rebuild_io()

    def iter_types(self) -> list[Node]:
        """Return all type-nodes (kind == '_type') in ULID order."""
        return self._repository.list_types()

    def iter_instances(self) -> list[Node]:
        """Return all non-type nodes in ULID order."""
        return self._repository.list_instances()

    def list_nodes(self) -> list[Node]:
        """Return all nodes (types + instances) in ULID order."""
        return self._repository.list_nodes()

    def get_node(self, node_id: str | NodeId) -> Node:
        """Return one node by ULID; raises KeyError if absent."""
        return self._repository.get(node_id)

    def upsert_node(self, node: Node) -> None:
        """Insert or replace one node, then notify listeners."""
        def mutate(repo: Repository) -> set[str]:
            repo.upsert(node)
            return {str(node.id)}
        self.apply_mutation("upsert_node", mutate)
        self._set_dirty(True)

    def delete_node(self, node_id: str | NodeId) -> None:
        """Delete a node by ULID, cascade-delete its links, then notify listeners."""
        key = str(node_id)

        def mutate(repo: Repository) -> set[str]:
            touched: set[str] = {key}
            for link in list(repo.list_links()):
                if link.source_node_id == key or link.target_node_id == key:
                    repo.delete_link(link.id)
                    touched.add(link.id)
            repo.delete(key)
            return touched
        self.apply_mutation("delete_node", mutate)
        self._set_dirty(True)

    def notify_repository_mutated(self, change_type: str = "node") -> None:
        """Mark session dirty after direct repository mutations."""
        self._reverse_ref_index.rebuild_from(self._repository)
        self._validation_index.recompute()
        self._set_dirty(True)
        self._emit_change(change_type, origin="notify_repository_mutated")

    def notify_link_added(self, link: LinkInstance) -> None:
        """Mark session dirty after one newly added link with incremental updates.

        This avoids the full reverse-ref rebuild + full validation recompute path
        used by ``notify_repository_mutated``.
        """
        self._reverse_ref_index.on_link_added(link)
        touched_ids = {
            str(link.id),
            str(link.link_type_id),
            str(link.source_node_id),
            str(link.target_node_id),
        }
        self._validation_index.recompute(touched_ids=touched_ids)
        self._set_dirty(True)
        self._emit_change(
            "link",
            touched_ids=touched_ids,
            origin="notify_link_added",
        )

    # ------------------------------------------------------------------
    # KnowledgeIO read delegates + canvas gateway (UI funnel — R11)
    # ------------------------------------------------------------------

    def ensure_io_synced(self) -> None:
        """Rebuild KnowledgeIO when ``_repository`` drifted from the IO snapshot."""
        if self._io.repository is self._repository:
            return
        self._reverse_ref_index.rebuild_from(self._repository)
        self._rebuild_io()

    def preview_delete_nodes(self, node_ids: list[str]):
        """Delegate to KnowledgeIO delete-impact preview."""
        return self._io.preview_delete_nodes(node_ids)

    def get_type_slots(self, type_id: str) -> list[NodeSlot]:
        """Return merged type slots via KnowledgeIO."""
        return self._io.get_type_slots(type_id)

    def load_graph_view(self, view_id: str) -> GraphView:
        """Load one graph view through the CanvasIO gateway."""
        return CanvasIO.load_graph_view(self._io, view_id)

    def save_graph_view(self, view: GraphView) -> None:
        """Persist one graph view through the CanvasIO gateway."""
        CanvasIO.save_graph_view(self._io, view)

    def list_graph_views(self) -> list[GraphView]:
        """List graph views through the CanvasIO gateway."""
        return CanvasIO.list_graph_views(self._io)

    def delete_graph_view(self, view_id: str) -> None:
        """Delete one graph view through the CanvasIO gateway."""
        CanvasIO.delete_graph_view(self._io, view_id)

    def ensure_unique_graph_view_name(
        self,
        desired: str,
        *,
        exclude_id: str | None = None,
    ) -> str:
        """Return a unique graph-view name through the CanvasIO gateway."""
        return CanvasIO.ensure_unique_graph_view_name(
            self._io,
            desired,
            exclude_id=exclude_id,
        )

    def graph_view_relpath(self, view_id: str) -> Path | None:
        """Return on-disk path for one graph view, if known."""
        return CanvasIO.graph_view_relpath(self._io, view_id)

    def canvas_io_for(self, view_path: str | Path) -> CanvasIO:
        """Return a CanvasIO bound to one view file and this session's IO."""
        return CanvasIO(view_path=view_path, knowledge_io=self._io)

    def absorb_io_operation_result(
        self,
        result: OperationResult,
        *,
        change_type: str = "node",
        origin: str = "absorb_io_operation_result",
    ) -> None:
        """Adopt snapshot and notify after a component wrote via ``self._io`` directly."""
        if not result.ok:
            return
        self._adopt_io_repository_preserving_identity()
        if result.effects is not None:
            self._apply_projection_hygiene(
                result.effects,
                affected_view_ids=self._hygiene_view_ids(result.effects),
            )
        touched_ids = (
            set(result.effects.touched)
            if result.effects is not None
            else set(result.touched_ids)
        )
        io_already_validated = (
            result.effects is not None and bool(result.validated_ids)
        )
        if touched_ids:
            self._reverse_ref_index.rebuild_from(self._repository)
            if not io_already_validated:
                self._validation_index.recompute(touched_ids=touched_ids)
            self._recompute_projection_validation()
        self._set_dirty(True)
        if touched_ids:
            self._current_change_touched_ids = frozenset(touched_ids)
            try:
                self._emit_change(
                    change_type,
                    touched_ids=touched_ids,
                    origin=origin,
                )
            finally:
                self._current_change_touched_ids = None

    def _run_io_write(
        self,
        fn,
        *,
        change_type: str = "node",
        origin: str,
        structural_change: bool = False,
        mutation_kind: MutationKind | None = None,
    ) -> OperationResult:
        """Execute one KnowledgeIO write, adopt snapshot, hygiene, and notify."""
        with self._mutation_lock:
            result = fn(self._io)
            if not result.ok:
                return result
            self._adopt_io_repository_preserving_identity()
            if result.effects is not None:
                self._apply_projection_hygiene(
                    result.effects,
                    affected_view_ids=self._hygiene_view_ids(result.effects),
                )
            touched_ids = (
                set(result.effects.touched)
                if result.effects is not None
                else set(result.touched_ids)
            )
            io_already_validated = (
                result.effects is not None and bool(result.validated_ids)
            )
            if touched_ids and not io_already_validated:
                self._validation_index.recompute(touched_ids=touched_ids)
            if touched_ids:
                self._recompute_projection_validation()
            self._set_dirty(True)
            if touched_ids:
                self._current_change_touched_ids = frozenset(touched_ids)
                try:
                    self._emit_change(
                        change_type,
                        touched_ids=touched_ids,
                        origin=origin,
                    )
                finally:
                    self._current_change_touched_ids = None
            return result

    def _recompute_projection_validation(self) -> None:
        """Refresh orphan kb_node / stale kb_edge projection findings."""
        existing_node_ids = {
            str(node.id) for node in self._repository.list_nodes()
        }
        existing_link_ids = {str(link.id) for link in self._repository.list_links()}
        graph_views: list[GraphView] = []
        if getattr(self._repository, "_repo_root", None) is not None:
            graph_views = list(self._repository.list_graph_views())
        issues = ProjectionValidator.scan_graph_views(
            graph_views,
            existing_node_ids,
            existing_link_ids,
        )
        self._validation_index.apply_projection_issues(issues)

    def _hygiene_view_ids(
        self,
        effects: MutationEffects,
    ) -> frozenset[str] | None:
        from lks_utils.knowledge.io.mutation_effects import MutationKind
        from lks_utils.knowledge.operations.delete_plan_query import DeletePlanQuery

        if effects.mutation_kind is not MutationKind.NODE_DELETE:
            return None
        if not effects.directly_changed:
            return None
        query = DeletePlanQuery(self._repository, self._reverse_ref_index)
        fanout = query.node_delete_fanout(sorted(effects.directly_changed))
        if not fanout.affected_view_paths:
            return None
        return frozenset(fanout.affected_view_paths)

    def _apply_projection_hygiene(
        self,
        effects: MutationEffects,
        *,
        affected_view_ids: frozenset[str] | None = None,
    ) -> None:
        """Run projection hygiene for graph views after a KB mutate."""
        if effects.journal_record is None:
            return
        policy = resolve_policy(effects.mutation_kind, effects.structural_change)
        hint = policy.canvas_hygiene_hint
        if hint is CanvasHygieneHint.NONE:
            return
        if getattr(self._repository, "_repo_root", None) is None:
            return
        hygiene = ProjectionHygiene()
        for graph_view in list(self._repository.list_graph_views()):
            if (
                affected_view_ids is not None
                and str(graph_view.id) not in affected_view_ids
            ):
                continue
            updated = hygiene.apply_to_graph_view(
                graph_view,
                hint=hint,
                event=effects.journal_record,
                knowledge_io=self._io,
            )
            if updated is not None:
                CanvasIO.save_graph_view(self._io, updated)

    def io_upsert_node(self, node: Node) -> OperationResult:
        return self._run_io_write(
            lambda io: io.upsert_node(node),
            origin="io_upsert_node",
            mutation_kind=MutationKind.NODE_UPSERT,
            structural_change=True,
        )

    def io_apply_op(self, mutator_fn, **kwargs) -> OperationResult:
        return self._run_io_write(
            lambda io: io.apply_op(mutator_fn, **kwargs),
            origin="io_apply_op",
        )

    def io_patch_node_props(self, node_id: str, updates: dict[str, object]) -> OperationResult:
        return self._run_io_write(
            lambda io: io.patch_node_props(node_id, updates),
            origin="io_patch_node_props",
            mutation_kind=MutationKind.INSTANCE_PROPERTY,
        )

    def io_delete_node_cascade(self, node_id: str) -> OperationResult:
        return self._run_io_write(
            lambda io: io.delete_node_cascade(node_id),
            change_type="node",
            origin="io_delete_node_cascade",
            mutation_kind=MutationKind.NODE_DELETE,
            structural_change=True,
        )

    def io_delete_nodes(self, node_ids: list[str], **kwargs) -> OperationResult:
        return self._run_io_write(
            lambda io: io.delete_nodes(node_ids, **kwargs),
            change_type="node",
            origin="io_delete_nodes",
            mutation_kind=MutationKind.NODE_DELETE,
            structural_change=True,
        )

    def io_add_slot_to_type(self, type_id: str, slot_payload: dict[str, object]) -> OperationResult:
        return self._run_io_write(
            lambda io: io.add_slot_to_type(type_id, slot_payload),
            origin="io_add_slot_to_type",
            mutation_kind=MutationKind.TYPE_SCHEMA,
            structural_change=True,
        )

    def io_remove_slot_from_type(self, type_id: str, slot_name: str) -> OperationResult:
        return self._run_io_write(
            lambda io: io.remove_slot_from_type(type_id, slot_name),
            origin="io_remove_slot_from_type",
            mutation_kind=MutationKind.TYPE_SCHEMA,
            structural_change=True,
        )

    def io_set_slot_value(self, node_id: str, slot_name: str, value: object) -> OperationResult:
        return self._run_io_write(
            lambda io: io.set_slot_value(node_id, slot_name, value),
            origin="io_set_slot_value",
            mutation_kind=MutationKind.INSTANCE_PROPERTY,
        )

    def io_clear_slot_value(self, node_id: str, slot_name: str) -> OperationResult:
        return self._run_io_write(
            lambda io: io.clear_slot_value(node_id, slot_name),
            origin="io_clear_slot_value",
            mutation_kind=MutationKind.INSTANCE_PROPERTY,
        )

    def io_upsert_link_type(self, link_type: LinkType) -> OperationResult:
        return self._run_io_write(
            lambda io: io.upsert_link_type(link_type),
            change_type="link_type",
            origin="io_upsert_link_type",
            mutation_kind=MutationKind.TYPE_SCHEMA,
            structural_change=True,
        )

    def io_delete_link_type_cascade(self, link_type_id: str) -> OperationResult:
        return self._run_io_write(
            lambda io: io.delete_link_type_cascade(link_type_id),
            change_type="link_type",
            origin="io_delete_link_type_cascade",
            mutation_kind=MutationKind.TYPE_SCHEMA,
            structural_change=True,
        )

    def io_remove_link(self, link_id: str) -> OperationResult:
        return self._run_io_write(
            lambda io: io.remove_link(link_id),
            change_type="link",
            origin="io_remove_link",
            mutation_kind=MutationKind.LINK_STRUCTURE,
            structural_change=True,
        )

    def io_upsert_link(self, link: LinkInstance) -> OperationResult:
        return self._run_io_write(
            lambda io: io.upsert_link(link),
            change_type="link",
            origin="io_upsert_link",
            mutation_kind=MutationKind.LINK_STRUCTURE,
            structural_change=True,
        )

    def commit_view_positions(
        self,
        *,
        view_path: str | Path,
        graph_view_id: str,
        positions_by_local_id: dict[str, tuple[float, float]],
    ):
        """Commit graph-view position changes via CanvasIO.mutate_view gateway."""
        return self.canvas_io_for(view_path).patch_graph_view_node_positions(
            graph_view_id,
            positions_by_local_id,
        )

    def apply_mutation(
        self,
        label: str,
        fn: Callable[[Repository], set[str] | list[str] | tuple[str, ...] | None],
        *,
        validation_mode: Literal["expanded", "touched_only"] = "touched_only",
    ) -> MutationResult:
        """Apply one mutation atomically against a repository snapshot.

        Delegates to :class:`KnowledgeIO` for in-place mutate, fatal integrity gate,
        incremental ref updates, and O(k) ``save_touched``.
        """
        mutation_kind = _SESSION_LABEL_TO_KIND.get(
            label, MutationKind.INSTANCE_PROPERTY)
        vmode = (
            ValidationMode.EXPANDED
            if validation_mode == "expanded"
            else ValidationMode.TOUCHED
        )
        fallback_full_rebuild = False

        def wrapped_fn(repo: Repository) -> set[str]:
            nonlocal fallback_full_rebuild
            raw = fn(repo)
            if raw is None:
                fallback_full_rebuild = True
                return compute_all_touched_ids(repo)
            return {str(tid) for tid in raw}

        with self._mutation_lock:
            with profile_action(
                "knowledge.session.apply_mutation",
                phase="io_apply_op",
                metadata={
                    "validation_mode": validation_mode,
                },
            ):
                if label in _SESSION_LABEL_TO_KIND:
                    result = self._io.apply_op(
                        wrapped_fn,
                        hint=mutation_kind,
                        structural_change=label in {"delete_node", "upsert_link", "delete_link"},
                    )
                else:
                    result = self._io.apply_op(wrapped_fn, validation_mode=vmode)
                if result.ok:
                    self._adopt_io_repository_preserving_identity()
                if fallback_full_rebuild and result.ok:
                    self._reverse_ref_index.rebuild_from(self._repository)

            if (
                result.status == "error"
                and result.error_message is not None
                and "Fatal integrity" in result.error_message
            ):
                raise FatalValidationError([])

            save_status = LastSaveStatus.OK if result.save_error is None else LastSaveStatus.FAILED
            save_error = result.save_error

            self._last_save_status = save_status
            self._last_save_error = save_error

            if save_error is None and self._repository_root is not None:
                with profile_action(
                    "knowledge.session.apply_mutation",
                    phase="emit_repo_saved",
                ):
                    self._emit_change("repo_saved")
                    self._emit_repo_saved(self._repository_root)
                if self._git_service is not None:
                    self._git_service.refresh_status_async()

            if result.effects is not None:
                touched_ids = set(result.effects.touched)
            else:
                touched_ids = set(result.touched_ids)
            if touched_ids:
                with profile_action(
                    "knowledge.session.apply_mutation",
                    phase="emit_node",
                    metadata={"touched_count": len(touched_ids)},
                ):
                    self._current_change_touched_ids = frozenset(touched_ids)
                    try:
                        self._emit_change(
                            "node",
                            touched_ids=touched_ids,
                            origin=label,
                        )
                    finally:
                        self._current_change_touched_ids = None

            return MutationResult(
                ok=result.status == "ok",
                last_save_status=save_status,
                touched_ids=touched_ids,
                save_error=save_error,
            )

    def list_links(self) -> list[LinkInstance]:
        """Return all LinkInstance records in the active repository."""
        return self._repository.list_links()

    def list_link_types(self) -> list[LinkType]:
        """Return all link types in ULID order."""
        return self._repository.list_link_types()

    def node_storage_paths(self, root: Path) -> dict[str, Path]:
        """Return node-id to storage path mapping for diagnostics/UI reveals."""
        return self._repository._build_storage_paths(root)  # noqa: SLF001

    def link_type_storage_paths(self, root: Path) -> dict[str, Path]:
        """Return link-type-id to storage path mapping for diagnostics/UI reveals."""
        return self._repository._build_link_type_storage_paths(root)  # noqa: SLF001

    def get_link_type(self, link_type_id: str) -> LinkType:
        """Return one link type by id."""
        return self._repository.get_link_type(link_type_id)

    def reference_options(self, ref_type: str | None = None) -> list[Node]:
        """Return nodes selectable as ref targets, filtered by slot type token."""
        nodes = self.list_nodes()
        if ref_type is None:
            return nodes
        token = ref_type.strip().casefold()
        if token in {"", "any"}:
            return nodes

        matching_type_ids = self._resolve_ref_type_to_type_ids(token)
        return [
            node
            for node in nodes
            if node.type_id is not None and str(node.type_id) in matching_type_ids
        ]

    def _resolve_ref_type_to_type_ids(self, token: str) -> set[str]:
        """Resolve a normalized ref token to type ids with stable precedence."""
        return resolve_ref_type_to_type_ids(
            iter_types=self.iter_types(),
            token=token,
            iter_links=self.list_links(),
            iter_link_types=self.list_link_types(),
        )

    # ------------------------------------------------------------------
    # Repository root (persistence)
    # ------------------------------------------------------------------

    def set_repository_root(self, root: str | Path, *, source_repo_id: str | None = None) -> None:
        """Configure the disk path used by save/load."""
        self._repository_root = Path(root)
        self._configure_git_service()
        if source_repo_id is not None:
            self._repository = Repository(source_repo_id=source_repo_id)
        self._rebuild_io()

    def new_repo(self, root: str | Path, *, source_repo_id: str = "default") -> None:
        """Create and switch to a new empty in-memory repository bound to root."""
        self._repository_root = Path(root)
        self._repository = Repository(source_repo_id=source_repo_id)
        self._reverse_ref_index.rebuild_from(self._repository)
        self._configure_git_service()
        self._rebuild_io()
        self._validation_index.recompute()
        self._recompute_projection_validation()
        self._last_save_status = LastSaveStatus.OK
        self._last_save_error = None
        self._set_dirty(False)
        self.apply_mutation(
            "seed_system_link_types",
            KnowledgeIO.seed_system_link_types,
            validation_mode="touched_only",
        )
        self._emit_change("node", origin="new_repo")
        self._emit_change("repo_loaded", origin="new_repo")
        self._emit_repo_loaded(self._repository_root)

    def save_as(self, root: str | Path) -> None:
        """Persist to a new root and make it active."""
        self._repository_root = Path(root)
        self._configure_git_service()
        self.save()

    def load_from(self, root: str | Path) -> None:
        """Load repository data from root and make it active."""
        self._repository_root = Path(root)
        self._configure_git_service()
        self.load()

    def save(self) -> None:
        """Persist current nodes to the configured repository root."""
        if self._repository_root is None:
            raise ValueError("Repository root is not configured")
        self._repository.save(self._repository_root)
        self._last_save_status = LastSaveStatus.OK
        self._last_save_error = None
        self._set_dirty(False)
        self._emit_change("repo_saved", origin="save")
        self._emit_repo_saved(self._repository_root)

    def load(self) -> None:
        """Load nodes from the configured repository root."""
        if self._repository_root is None:
            raise ValueError("Repository root is not configured")
        self._repository = Repository.load(self._repository_root)
        self._reverse_ref_index.rebuild_from(self._repository)
        self._rebuild_io()
        self._validation_index.recompute()
        self._recompute_projection_validation()
        self._last_save_status = LastSaveStatus.OK
        self._last_save_error = None
        self._set_dirty(False)
        self._emit_change("node", origin="load")
        self._emit_change("repo_loaded", origin="load")
        self._emit_repo_loaded(self._repository_root)
        self.apply_mutation(
            "seed_system_link_types",
            KnowledgeIO.seed_system_link_types,
            validation_mode="touched_only",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit_change(
        self,
        change_type: str,
        *,
        touched_ids: set[str] | frozenset[str] | None = None,
        origin: str | None = None,
    ) -> None:
        if touched_ids is None:
            event_touched_ids = self._current_change_touched_ids
        else:
            event_touched_ids = frozenset(str(object_id)
                                          for object_id in touched_ids)
        event = SessionChangeEvent(
            change_type=change_type,
            touched_ids=event_touched_ids,
            origin=origin,
        )
        previous_event = self._current_change_event
        self._current_change_event = event
        for listener in list(self._listeners):
            listener(change_type)
        for listener in list(self._change_listeners):
            listener(event)
        self._current_change_event = previous_event

    def _set_dirty(self, is_dirty: bool) -> None:
        if self._is_dirty == is_dirty:
            return
        self._is_dirty = is_dirty
        self._emit_change("dirty_changed", origin="set_dirty")

    def _emit_repo_loaded(self, root: Path) -> None:
        for listener in list(self._repo_loaded_listeners):
            listener(root)

    def _emit_repo_saved(self, root: Path) -> None:
        for listener in list(self._repo_saved_listeners):
            listener(root)

    def _configure_git_service(self) -> None:
        if self._repository_root is None:
            self._git_service = None
            return
        self._git_service = KnowledgeGitService(
            repository_root=self._repository_root)


__all__ = ["EditorSession"]

"""KnowledgeIO — single write-path facade for knowledge repositories.

Pure Python: no Qt imports.  Accepts a ValidationIndex via injection so the
UI layer (EditorSession) can wire Qt signals while MCP/CLI paths can pass None.
"""
from __future__ import annotations

import copy
import time
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Literal

from lks_utils.knowledge.integrity_issue import IntegrityIssue
from lks_utils.knowledge.integrity_repairer import IntegrityRepairer
from lks_utils.knowledge.integrity_reporter import IntegrityReporter
from lks_utils.knowledge.instance_validator import InstanceValidator
from lks_utils.knowledge.knowledge_change_event import KnowledgeChangeEvent
from lks_utils.knowledge.knowledge_change_listener import KnowledgeChangeListener
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType, SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node_slot import NodeSlot, SlotSource
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.resolver import Resolver
from lks_utils.knowledge.reverse_ref_index import ReverseRefIndex
from lks_utils.knowledge.io.operation_result import (
    OperationResult,
    ValidationIssue,
    ValidationMode,
)
from lks_utils.knowledge.io.knowledge_change_journal import append_change_event
from lks_utils.knowledge.io.slot_value_envelope import SlotValueEnvelope
from lks_utils.knowledge.io.delete_resolution import DeleteResolution
from lks_utils.knowledge.io.link_impact import LinkDeleteImpact, LinkTypeDeleteImpact
from lks_utils.knowledge.operations.delete_safety_analyzer import (
    DeleteImpact,
    analyze_delete_impact,
)
from lks_utils.knowledge.links.link_types.link_type_slot_ref import make_slot_ref_link_type
from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
    make_extends_link_type,
    make_instance_of_link_type,
)
from lks_utils.knowledge.mutator import Mutator
from lks_utils.knowledge.repository_hierarchy import (
    compute_instance_ancestry,
    compute_type_ancestry,
)
from lks_utils.knowledge._editor_session.selection import resolve_ref_type_to_type_ids
from lks_utils.profiling import profile_action
from lks_utils.text.search import normalize_search_text, suggest_close_matches

# System link types are backend-managed infrastructure.  They must NEVER be
# created, updated, or deleted through the public IO surface.  Use the
# appropriate node-lifecycle or property-mutation workflows instead.
_SYSTEM_LINK_TYPE_IDS: frozenset[str] = frozenset({
    SLOT_REF_LINK_TYPE_ID,
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
})
_SYSTEM_LINK_MANAGED_MSG = (
    "is backend-managed and cannot be directly created, updated, or deleted. "
    "Use the appropriate node-lifecycle or property-mutation workflow instead "
    "(e.g. set_extends_parent, set_instance_of_type, or patch_node_props for raw node-id reference values)."
)

if TYPE_CHECKING:
    from lks_utils.knowledge.io.bulk_prop_result import BulkPropResult
    from lks_utils.knowledge.io.prop_filter import PropFilter
    from lks_utils.knowledge.io.type_change_resolution import (
        TypeSlotChangeImpact,
        TypeSlotChanges,
    )
    from lks_utils.knowledge.validation_index import ValidationIndex


class KnowledgeIO:
    """Single write-path for all knowledge repository mutations.

    Responsibilities
    ----------------
    1. Accept a mutator function, apply it against a deep-copy snapshot.
    2. Reject mutations that leave fatal integrity violations.
    3. Classify which files are dirty, run ``save_touched`` (O(k) writes).
    4. Optionally recompute validation on the touched set.
    5. Return a typed :class:`OperationResult`.

    Construction
    ------------
    * UI path: ``EditorSession`` builds one instance at session start and injects
      it with the live repository, reverse-ref index, and validation index.
    * MCP/CLI path: use the :meth:`from_path` factory — no Qt required.
    """

    def __init__(
        self,
        repository: Repository,
        reverse_ref_index: ReverseRefIndex,
        *,
        validation_index: ValidationIndex | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self._repository = repository
        self._reverse_ref_index = reverse_ref_index
        self._validation_index = validation_index
        self._repository_root = repository_root
        self._lock = RLock()
        # Event listeners are wired in a follow-up slice; keep the storage ready.
        self._listeners: list[KnowledgeChangeListener] = []
        self._last_violations_by_entity: dict[str, list[IntegrityIssue]] = {}

    @classmethod
    def from_path(cls, path: str | Path) -> KnowledgeIO:
        """Load a repository from *path* and return a ready-to-use instance.

        No Qt or ValidationIndex is created.  Suitable for MCP and CLI callers.
        """
        root = Path(path)
        repo = Repository.load(root)
        rri = ReverseRefIndex()
        rri.rebuild_from(repo)
        io = cls(
            repository=repo,
            reverse_ref_index=rri,
            repository_root=root,
        )
        result = io.apply_op(cls.seed_system_link_types,
                             validation_mode=ValidationMode.TOUCHED)
        if result.status == "error":
            raise RuntimeError(
                f"Failed to seed system link types for repository {root}: {result.error_message}"
            )
        return io

    @classmethod
    def from_disk_scan(cls, path: str | Path) -> KnowledgeIO:
        """Load a repository by scanning disk files directly, ignoring any stale index."""
        root = Path(path)
        repo = Repository.load_from_disk_scan(root)
        rri = ReverseRefIndex()
        rri.rebuild_from(repo)
        io = cls(
            repository=repo,
            reverse_ref_index=rri,
            repository_root=root,
        )
        result = io.apply_op(cls.seed_system_link_types,
                             validation_mode=ValidationMode.TOUCHED)
        if result.status == "error":
            raise RuntimeError(
                f"Failed to seed system link types for repository {root}: {result.error_message}"
            )
        return io

    @staticmethod
    def seed_system_link_types(repo: Repository) -> set[str]:
        """Seed built-in system link types and return touched IDs."""
        existing_ids = {lt.id for lt in repo.list_link_types()}
        touched: set[str] = set()
        if SLOT_REF_LINK_TYPE_ID not in existing_ids:
            repo.upsert_link_type(make_slot_ref_link_type())
            touched.add(SLOT_REF_LINK_TYPE_ID)
        if EXTENDS_LINK_TYPE_ID not in existing_ids:
            repo.upsert_link_type(make_extends_link_type())
            touched.add(EXTENDS_LINK_TYPE_ID)
        if INSTANCE_OF_LINK_TYPE_ID not in existing_ids:
            repo.upsert_link_type(make_instance_of_link_type())
            touched.add(INSTANCE_OF_LINK_TYPE_ID)
        return touched

    # ------------------------------------------------------------------
    # Core primitive
    # ------------------------------------------------------------------

    def apply_op(
        self,
        mutator_fn: Callable[[Repository], set[str]],
        *,
        validation_mode: ValidationMode = ValidationMode.TOUCHED,
    ) -> OperationResult:
        """Apply one mutation atomically and return a typed result.

        *mutator_fn* receives a **deep-copy** snapshot of the repository, may
        mutate it freely, and must return the set of string IDs it touched.
        Unknown IDs in the returned set are silently ignored during
        classification.

        The method:
        1. Deep-copies the repository into a snapshot.
        2. Runs *mutator_fn* against the snapshot.
        3. Rejects the mutation if fatal integrity violations exist.
        4. Classifies touched IDs into nodes / link-types / links.
        5. Updates the reverse-ref index incrementally.
        6. Swaps ``self._repository`` to the new snapshot.
        7. Persists via ``save_touched`` when *repository_root* is set.
        8. Optionally triggers an incremental validation recompute.
        9. Returns :class:`OperationResult`.
        """
        with self._lock:
            old_repo = self._repository
            with profile_action("knowledge.io.apply_op", phase="snapshot_clone"):
                snapshot = copy.deepcopy(self._repository)

            with profile_action("knowledge.io.apply_op", phase="mutator"):
                raw_ids = mutator_fn(snapshot)
                touched_ids: set[str] = {str(tid) for tid in raw_ids}

            # Integrity gate — fatal violations abort the mutation.
            with profile_action("knowledge.io.apply_op", phase="integrity_gate"):
                fatal = IntegrityReporter.fatal_only(snapshot)
            if fatal:
                return OperationResult(
                    status="error",
                    touched_ids=frozenset(),
                    validated_ids=frozenset(),
                    issues=(),
                    error_message=f"Fatal integrity violation: {len(fatal)} issue(s)",
                )

            with profile_action("knowledge.io.apply_op", phase="classify_touched"):
                t_nodes, t_link_types, t_links = _classify_touched_ids(
                    old_repo, snapshot, touched_ids, self._reverse_ref_index
                )

            with profile_action("knowledge.io.apply_op", phase="incremental_ref_update"):
                _apply_incremental_ref_update(
                    old_repo, snapshot, t_nodes, t_links, self._reverse_ref_index
                )
            self._repository = snapshot

            # Persist incrementally.
            save_error: str | None = None
            if self._repository_root is not None:
                try:
                    with profile_action(
                        "knowledge.io.apply_op",
                        phase="save_touched",
                        metadata={
                            "touched_nodes": len(t_nodes),
                            "touched_link_types": len(t_link_types),
                            "touched_links": len(t_links),
                        },
                    ):
                        self._repository.save_touched(
                            self._repository_root,
                            touched_node_ids=t_nodes,
                            touched_link_type_ids=t_link_types,
                            touched_link_ids=t_links,
                            old_repo=old_repo,
                        )
                except Exception as exc:  # pragma: no cover
                    save_error = str(exc)

            # Validation recompute (skipped when no index is injected).
            validated_ids: frozenset[str] = frozenset()
            issues: tuple[ValidationIssue, ...] = ()
            if self._validation_index is not None:
                with profile_action(
                    "knowledge.io.apply_op",
                    phase="validation_recompute",
                    metadata={
                        "touched_ids": len(touched_ids),
                        "impact_mode": validation_mode.value,
                    },
                ):
                    changed = self._validation_index.recompute(
                        touched_ids=touched_ids,
                        impact_mode=validation_mode.value,
                    )
                touched_ids |= changed
                validated_ids = frozenset(touched_ids)
                issues = _collect_issues(self._validation_index, validated_ids)

            return OperationResult(
                status="ok" if save_error is None else "error",
                touched_ids=frozenset(touched_ids),
                validated_ids=validated_ids,
                issues=issues,
                save_error=save_error,
                error_message=save_error,
            )

    # ------------------------------------------------------------------
    # Typed wrappers (Slice 1: no-resolution paths only)
    # ------------------------------------------------------------------

    def upsert_node(self, node: Node, *, bundle_id: str | None = None) -> OperationResult:
        """Insert or replace one node.

        Touched set: ``{node.id} + index.json``
        Validation set: ``{node.id} ∪ referencers_of(node.id)``
        """
        _ = bundle_id
        node_id = str(node.id)

        def mutator(repo: Repository) -> set[str]:
            repo.upsert(node)
            return {node_id}

        result = self.apply_op(mutator)
        if result.ok:
            self._run_post_write_integrity(node_id)
            self._emit(
                KnowledgeChangeEvent(
                    event_type="node_upserted",
                    entity_id=node_id,
                    entity_type="node",
                    bundle_id=bundle_id,
                    timestamp=time.time(),
                    violations=list(
                        self._last_violations_by_entity.get(node_id, [])),
                )
            )
        return result

    def delete_node(self, node_id: str | NodeId) -> OperationResult:
        """Delete one node (no-resolution path — no incoming-ref check).

        Cascade-deletes all links whose source or target is *node_id*.

        Touched set: ``{node_id} + affected_link_ids + index.json``
        """
        key = str(node_id)

        def mutator(repo: Repository) -> set[str]:
            touched: set[str] = {key}
            for link in list(repo.list_links()):
                if link.source_node_id == key or link.target_node_id == key:
                    repo.delete_link(link.id)
                    touched.add(link.id)
            repo.delete(key)
            return touched

        return self.apply_op(mutator)

    def remove_node(
        self,
        node_id: str | NodeId,
        *,
        bundle_id: str | None = None,
    ) -> OperationResult:
        """Compatibility API: delegate node removal through ``delete_node``."""
        _ = bundle_id
        result = self.delete_node(node_id)
        if result.ok:
            self._run_post_write_integrity(str(node_id))
            self._emit(
                KnowledgeChangeEvent(
                    event_type="node_deleted",
                    entity_id=str(node_id),
                    entity_type="node",
                    bundle_id=bundle_id,
                    timestamp=time.time(),
                    violations=list(
                        self._last_violations_by_entity.get(str(node_id), [])),
                )
            )
        return result

    def upsert_link(
        self,
        link: LinkInstance,
        *,
        bundle_id: str | None = None,
    ) -> OperationResult:
        """Insert or replace one link edge.

        Touched set: ``{link.id} + index.json``
        Validation set: ``{link.source_node_id, link.target_node_id}``
        """
        _ = bundle_id
        if str(link.link_type_id) in _SYSTEM_LINK_TYPE_IDS:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message=(
                    f"Link type {link.link_type_id!r} {_SYSTEM_LINK_MANAGED_MSG}"
                ),
            )
        link_id = link.id

        def mutator(repo: Repository) -> set[str]:
            repo.upsert_link(link)
            return {link_id, link.source_node_id, link.target_node_id}

        result = self.apply_op(mutator)
        if result.ok:
            self._run_post_write_integrity(link_id)
            self._emit(
                KnowledgeChangeEvent(
                    event_type="link_upserted",
                    entity_id=link_id,
                    entity_type="link",
                    bundle_id=bundle_id,
                    timestamp=time.time(),
                    violations=list(
                        self._last_violations_by_entity.get(link_id, [])),
                )
            )
        return result

    def delete_link(self, link: LinkInstance) -> OperationResult:
        """Delete one link edge.

        For slot_ref links, also evicts any stale slot payload from the source
        node's ``props[source_slot_name]`` so the in-memory view stays
        consistent with the link store.

        Touched set: ``{link.id} + index.json``
        Validation set: ``{link.source_node_id, link.target_node_id}``
        """
        if str(link.link_type_id) in _SYSTEM_LINK_TYPE_IDS:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message=(
                    f"Link type {link.link_type_id!r} {_SYSTEM_LINK_MANAGED_MSG}"
                ),
            )
        link_id = link.id
        is_slot_ref = str(link.link_type_id) == SLOT_REF_LINK_TYPE_ID
        slot_name = link.source_slot_name if is_slot_ref else None
        source_id = link.source_node_id

        def mutator(repo: Repository) -> set[str]:
            repo.delete_link(link_id)
            touched: set[str] = {link_id, source_id, link.target_node_id}
            # Cascade: evict stale slot payload from props when a slot_ref link is removed.
            if slot_name is not None:
                try:
                    node = repo.get(source_id)
                except KeyError:
                    return touched
                if slot_name in node.props:
                    cleaned = dict(node.props)
                    cleaned.pop(slot_name)
                    repo.upsert(node.model_copy(
                        update={"props": cleaned, "rev": node.rev + 1}
                    ))
                    touched.add(source_id)
            return touched

        return self.apply_op(mutator)

    def remove_link(
        self,
        link_id: str,
        *,
        bundle_id: str | None = None,
    ) -> OperationResult:
        """Remove one link by ID by delegating to ``delete_link``."""
        _ = bundle_id
        link = self._repository.find_link(link_id)
        if link is None:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message=f"Link not found: {link_id}",
            )
        result = self.delete_link(link)
        if result.ok:
            self._run_post_write_integrity(link_id)
            self._emit(
                KnowledgeChangeEvent(
                    event_type="link_deleted",
                    entity_id=link_id,
                    entity_type="link",
                    bundle_id=bundle_id,
                    timestamp=time.time(),
                    violations=list(
                        self._last_violations_by_entity.get(link_id, [])),
                )
            )
        return result

    def upsert_link_type(
        self,
        link_type: LinkType,
        *,
        bundle_id: str | None = None,
    ) -> OperationResult:
        """Insert or replace one link-type definition.

        Touched set: ``{link_type.id} + index.json``
        Validation set: all links of this type + their endpoint nodes
        """
        _ = bundle_id
        if link_type.is_system:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message=(
                    f"Link type {link_type.id!r} {_SYSTEM_LINK_MANAGED_MSG}"
                ),
            )
        lt_id = str(link_type.id)

        def mutator(repo: Repository) -> set[str]:
            repo.upsert_link_type(link_type)
            touched: set[str] = {lt_id}
            for link in repo.list_links():
                if str(link.link_type_id) == lt_id:
                    touched.add(link.id)
                    touched.add(link.source_node_id)
                    touched.add(link.target_node_id)
            return touched

        result = self.apply_op(mutator)
        if result.ok:
            self._run_post_write_integrity(lt_id)
            self._emit(
                KnowledgeChangeEvent(
                    event_type="link_type_upserted",
                    entity_id=lt_id,
                    entity_type="link_type",
                    bundle_id=bundle_id,
                    timestamp=time.time(),
                    violations=list(
                        self._last_violations_by_entity.get(lt_id, [])),
                )
            )
        return result

    # ------------------------------------------------------------------
    # Property mutation helpers (WO2)
    # ------------------------------------------------------------------

    def patch_node_props(
        self,
        node_id: str | NodeId,
        props: dict[str, object],
        *,
        expected_revision_id: str | None = None,
    ) -> OperationResult:
        """Merge *props* into the node's existing properties (partial update).

        Only the keys present in *props* are written; all other keys on the
        node are left unchanged (no replace-all semantics).

        Parameters
        ----------
        node_id:
            Target node identifier.
        props:
            Key/value pairs to merge in.
        expected_revision_id:
            When supplied, the operation fails with :class:`ConflictError`
            if the node's current ``rev`` does not equal this string.
            Pass ``str(node.rev)`` to enable optimistic locking.

        Raises
        ------
        ConflictError
            When *expected_revision_id* is provided and does not match.
        """
        from lks_utils.knowledge.io.conflict_error import ConflictError
        from lks_utils.knowledge.models.type import as_type, is_type

        key = str(node_id)
        # Capture in a one-element list so the mutator can signal early exits
        _early: list[str | None] = [None]  # [0] = error message or None
        _conflict: list[ConflictError | None] = [None]

        def mutator(repo: Repository) -> set[str]:
            node = repo.find_node(key)
            if node is None:
                _early[0] = f"Node not found: {key}"
                return set()

            # Optimistic locking — compare inside snapshot for correctness
            if expected_revision_id is not None and str(node.rev) != expected_revision_id:
                _conflict[0] = ConflictError(
                    node_id=key,
                    current_rev=node.rev,
                    expected_rev=expected_revision_id,
                )
                return set()

            # Unknown-key validation (only for typed nodes)
            if node.type_id is not None:
                type_node = repo.find_node(str(node.type_id))
                if type_node is not None and is_type(type_node):
                    slot_names = {s.name for s in as_type(type_node).slots}
                    unknown = {k for k in props if k not in slot_names}
                    if unknown:
                        _early[0] = f"Unknown slot keys: {sorted(unknown)}"
                        return set()

            merged = {**node.props, **props}
            updated = node.model_copy(
                update={"props": merged, "rev": node.rev + 1})
            repo.upsert(updated)
            return {key}

        result = self.apply_op(mutator)

        if _conflict[0] is not None:
            raise _conflict[0]
        if _early[0] is not None:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message=_early[0],
            )
        return result

    def bulk_set_prop(
        self,
        node_ids: list[str],
        prop_key: str,
        value: object,
    ) -> BulkPropResult:
        """Apply one prop key/value to multiple nodes without aborting on failure.

        Each node is patched atomically.  A failure on one node is recorded in
        the result but does **not** stop processing of subsequent nodes.

        Returns
        -------
        BulkPropResult
            Per-node outcome with ``ok_count`` / ``error_count`` summary.
        """
        from lks_utils.knowledge.io.bulk_prop_result import (
            BulkPropResult,
            NodePropMutationResult,
        )
        from lks_utils.knowledge.io.conflict_error import ConflictError

        results: list[NodePropMutationResult] = []
        for nid in node_ids:
            try:
                op = self.patch_node_props(nid, {prop_key: value})
                if op.ok:
                    results.append(NodePropMutationResult(
                        node_id=nid, status="ok"))
                else:
                    results.append(NodePropMutationResult(
                        node_id=nid, status="error", error=op.error_message,
                    ))
            except ConflictError as exc:
                results.append(NodePropMutationResult(
                    node_id=nid, status="conflict", error=str(exc),
                ))
            except Exception as exc:
                results.append(NodePropMutationResult(
                    node_id=nid, status="error", error=str(exc),
                ))

        return BulkPropResult(results=tuple(results))

    def find_nodes_multi_prop(
        self,
        filters: list[PropFilter],
        match: Literal["all", "any"] = "all",
    ) -> list[Node]:
        """Return nodes whose props satisfy all (or any) of the given filters.

        Parameters
        ----------
        filters:
            List of :class:`PropFilter` predicates to apply.
        match:
            ``"all"`` — every filter must match (AND).
            ``"any"`` — at least one filter must match (OR).

        Returns
        -------
        list[Node]
            Matching nodes in stable iteration order.
        """
        combiner = all if match == "all" else any
        return [
            node
            for node in self._repository.list_nodes()
            if filters and combiner(f.matches(node.props or {}) for f in filters)
        ]

    def get_node_category(self, node_id: str | NodeId) -> str:
        """Return the category for one node."""
        return self.get_node(node_id).category

    def find_nodes_by_category(self, category: str) -> list[Node]:
        """Return all nodes whose category equals *category* exactly."""
        return [node for node in self._repository.list_nodes() if node.category == category]

    def set_node_category(
        self,
        node_id: str | NodeId,
        category: str,
        *,
        expected_revision_id: str | None = None,
    ) -> OperationResult:
        """Set one node's category with optional optimistic locking.

        Returns an ``OperationResult``. When *expected_revision_id* mismatches,
        raises :class:`ConflictError`.
        """
        from lks_utils.knowledge.io.conflict_error import ConflictError

        key = str(node_id)
        next_category = category.strip()
        if not next_category:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message="category must be a non-empty string",
            )

        _conflict: list[ConflictError | None] = [None]
        _early: list[str | None] = [None]

        def mutator(repo: Repository) -> set[str]:
            node = repo.find_node(key)
            if node is None:
                _early[0] = f"Node not found: {key}"
                return set()

            if expected_revision_id is not None and str(node.rev) != expected_revision_id:
                _conflict[0] = ConflictError(
                    node_id=key,
                    current_rev=node.rev,
                    expected_rev=expected_revision_id,
                )
                return set()

            if node.category == next_category:
                return set()

            updated = node.model_copy(
                update={"category": next_category, "rev": node.rev + 1}
            )
            repo.upsert(updated)
            return {key}

        result = self.apply_op(mutator)

        if _conflict[0] is not None:
            raise _conflict[0]
        if _early[0] is not None:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message=_early[0],
            )
        return result

    def subscribe(self, listener: KnowledgeChangeListener) -> None:
        """Register a change listener if not already registered."""
        if not hasattr(listener, "on_knowledge_change"):
            raise TypeError(
                "listener must implement on_knowledge_change(event)"
            )
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: KnowledgeChangeListener) -> None:
        """Unregister a previously registered listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _emit(self, event: KnowledgeChangeEvent) -> None:
        """Emit one change event to all registered listeners."""
        if self._repository_root is not None:
            try:
                append_change_event(self._repository_root, event)
            except Exception:
                # Journal persistence must not break write-path behavior.
                pass
        for listener in list(self._listeners):
            try:
                listener.on_knowledge_change(event)
            except Exception:
                # Listener failures must not break write-path behavior.
                continue

    def _run_post_write_integrity(self, entity_id: str) -> None:
        """Run non-blocking post-write integrity reporting for one mutation."""
        reporter = IntegrityReporter()
        try:
            violations = reporter.report(self._repository)
        except Exception:
            violations = []
        self._last_violations_by_entity[entity_id] = violations
        if self._validation_index is not None:
            try:
                self._validation_index.recompute(
                    touched_ids={entity_id},
                    impact_mode=ValidationMode.TOUCHED.value,
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Cascade-delete suite (WO2)
    # ------------------------------------------------------------------

    def check_delete_impact(self, node_id: str | NodeId) -> dict[str, object]:
        """Return link-instance blocking info for deleting *node_id*.

        **Read-only** — does not mutate the repository.

        Returns
        -------
        dict with keys:

        * ``blocking_link_ids`` — IDs of links where node appears as source or target.
        * ``blocking_link_count`` — Count of those links.
        * ``incident_link_types`` — Sorted unique link-type IDs used by those links.
        """
        key = str(node_id)
        blocking = [
            link
            for link in self._repository.list_links()
            if link.source_node_id == key or link.target_node_id == key
        ]
        incident_types = sorted({str(link.link_type_id) for link in blocking})
        return {
            "blocking_link_ids": [link.id for link in blocking],
            "blocking_link_count": len(blocking),
            "incident_link_types": incident_types,
        }

    def delete_node_safe(self, node_id: str | NodeId) -> OperationResult:
        """Delete one node; fails fast when incident links exist.

        Returns ``OperationResult(status="blocked", ...)`` if any link
        instance references *node_id* as source or target.  No disk write
        occurs in that case.

        When the node has no incident links, delegates to a standard
        ``apply_op`` mutator and returns ``status="ok"``.
        """
        key = str(node_id)
        impact = self.check_delete_impact(key)
        if impact["blocking_link_count"] > 0:
            return OperationResult(
                status="blocked",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                blocking_impact=impact,
                error_message=(
                    f"Node {key!r} has {impact['blocking_link_count']} incident link(s); "
                    "use delete_node_cascade to force-delete."
                ),
            )

        def mutator(repo: Repository) -> set[str]:
            repo.delete(key)
            return {key}

        return self.apply_op(mutator)

    def delete_node_cascade(self, node_id: str | NodeId) -> OperationResult:
        """Atomically delete one node and all incident links.

        This is an explicit alias for the existing cascade semantics already
        in :meth:`delete_node`, provided for a clearer MCP tool surface.
        """
        return self.delete_node(node_id)

    def delete_link_type_cascade(self, link_type_id: str) -> OperationResult:
        """Atomically delete one link type and all link instances of that type.

        All affected source/target nodes are included in the touched set so
        post-mutation validation covers them.
        """
        lt_id = str(link_type_id)
        if lt_id in _SYSTEM_LINK_TYPE_IDS:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message=(
                    f"Link type {lt_id!r} {_SYSTEM_LINK_MANAGED_MSG}"
                ),
            )

        def mutator(repo: Repository) -> set[str]:
            touched: set[str] = {lt_id}
            for link in list(repo.list_links()):
                if str(link.link_type_id) == lt_id:
                    repo.delete_link(link.id)
                    touched.add(link.id)
                    touched.add(link.source_node_id)
                    touched.add(link.target_node_id)
            repo.delete_link_type(lt_id)
            return touched

        return self.apply_op(mutator)

    def clear_repo_contents(self) -> OperationResult:
        """Delete all nodes, links, and link types from the repository.

        This preserves the repository root and source repo id, and routes all
        object deletion through the standard ``apply_op`` save path.
        """
        touched_before: set[str] = {
            *(str(node.id) for node in self._repository.list_nodes()),
            *(str(link_type.id)
              for link_type in self._repository.list_link_types()),
            *(str(link.id) for link in self._repository.list_links()),
        }

        def mutator(repo: Repository) -> set[str]:
            for link in list(repo.list_links()):
                repo.delete_link(link.id)
            for link_type in list(repo.list_link_types()):
                repo.delete_link_type(str(link_type.id))
            for node in list(repo.list_nodes()):
                repo.delete(str(node.id))
            return touched_before

        return self.apply_op(mutator, validation_mode=ValidationMode.TOUCHED)

    def ensure_system_link_types(self) -> OperationResult:
        """Ensure built-in system link types exist via the IO write path."""
        return self.apply_op(self.seed_system_link_types)

    def save_snapshot(self) -> OperationResult:
        """Persist the current snapshot through the IO save pipeline."""
        if self._repository_root is None:
            return OperationResult(
                status="error",
                touched_ids=frozenset(),
                validated_ids=frozenset(),
                issues=(),
                error_message="Repository root is not set",
            )

        self._repository.save(self._repository_root)
        touched_ids = frozenset(str(node.id)
                                for node in self._repository.list_nodes())
        touched_ids |= frozenset(str(link_type.id)
                                 for link_type in self._repository.list_link_types())
        touched_ids |= frozenset(str(link.id)
                                 for link in self._repository.list_links())
        return OperationResult(
            status="ok",
            touched_ids=touched_ids,
            validated_ids=frozenset(),
            issues=(),
        )

    def rebuild_index(self) -> OperationResult:
        """Rebuild index.json from the current in-memory repository snapshot."""
        return self.save_snapshot()

    # ------------------------------------------------------------------
    # MCP-facing convenience methods
    # ------------------------------------------------------------------

    def upsert_nodes(self, nodes: list[Node]) -> OperationResult:
        """Insert or replace multiple nodes in one atomic operation."""

        def mutator(repo: Repository) -> set[str]:
            touched: set[str] = set()
            for node in nodes:
                repo.upsert(node)
                touched.add(str(node.id))
            return touched

        return self.apply_op(mutator)

    def upsert_links(self, links: list[LinkInstance]) -> OperationResult:
        """Insert or replace multiple links in one atomic operation."""
        for link in links:
            if str(link.link_type_id) in _SYSTEM_LINK_TYPE_IDS:
                return OperationResult(
                    status="error",
                    touched_ids=frozenset(),
                    validated_ids=frozenset(),
                    issues=(),
                    error_message=(
                        f"Link type {link.link_type_id!r} {_SYSTEM_LINK_MANAGED_MSG}"
                    ),
                )

        def mutator(repo: Repository) -> set[str]:
            touched: set[str] = set()
            for link in links:
                repo.upsert_link(link)
                touched.add(link.id)
                touched.add(link.source_node_id)
                touched.add(link.target_node_id)
            return touched

        return self.apply_op(mutator)

    def upsert_link_types(self, link_types: list[LinkType]) -> OperationResult:
        """Insert or replace multiple link types in one atomic operation."""
        for link_type in link_types:
            if link_type.is_system:
                return OperationResult(
                    status="error",
                    touched_ids=frozenset(),
                    validated_ids=frozenset(),
                    issues=(),
                    error_message=(
                        f"Link type {link_type.id!r} {_SYSTEM_LINK_MANAGED_MSG}"
                    ),
                )

        def mutator(repo: Repository) -> set[str]:
            touched: set[str] = set()
            for link_type in link_types:
                repo.upsert_link_type(link_type)
                touched.add(str(link_type.id))
            return touched

        return self.apply_op(mutator)

    def list_nodes(self) -> list[Node]:
        """Return all nodes from the live repository snapshot."""
        return self._repository.list_nodes()

    def list_links(self) -> list[LinkInstance]:
        """Return all links from the live repository snapshot."""
        return self._repository.list_links()

    def list_link_types(self) -> list[LinkType]:
        """Return all link types from the live repository snapshot."""
        return self._repository.list_link_types()

    def get_node(self, node_id: str | NodeId) -> Node:
        """Get one node by ID from the live repository snapshot."""
        return self._repository.get(str(node_id))

    def find_node(self, node_id: str | NodeId) -> Node | None:
        """Find one node by ID from the live repository snapshot."""
        return self._repository.find_node(str(node_id))

    def find_link(self, link_id: str) -> LinkInstance | None:
        """Find one link by ID from the live repository snapshot."""
        return self._repository.find_link(link_id)

    def find_link_type(self, link_type_id: str) -> LinkType | None:
        """Find one link type by ID from the live repository snapshot."""
        return self._repository.find_link_type(link_type_id)

    def get_link_type(self, link_type_id: str) -> LinkType:
        """Get one link type by ID from the live repository snapshot."""
        return self._repository.get_link_type(link_type_id)

    def get_link(self, link_id: str) -> LinkInstance:
        """Get one link by ID from the live repository snapshot."""
        link = self._repository.find_link(link_id)
        if link is None:
            raise KeyError(f"Link not found: {link_id}")
        return link

    def get(self, node_id: str | NodeId) -> Node:
        """Compatibility alias for repository.get."""
        return self.get_node(node_id)

    def list_types(self) -> list[Node]:
        """Return all type nodes from the live repository snapshot."""
        return [node for node in self._repository.list_nodes() if node.category == "_type"]

    @property
    def source_repo_id(self) -> str:
        """Return source repository ID from the live snapshot."""
        return self._repository.source_repo_id

    def validate_upsert_node(self, node: Node) -> list[IntegrityIssue]:
        """Return integrity violations for a hypothetical node upsert."""
        snapshot = copy.deepcopy(self._repository)
        snapshot.upsert(node)
        return IntegrityReporter().report(snapshot)

    def validate_upsert_link(self, link: LinkInstance) -> list[IntegrityIssue]:
        """Return integrity violations for a hypothetical link upsert."""
        snapshot = copy.deepcopy(self._repository)
        snapshot.upsert_link(link)
        return IntegrityReporter().report(snapshot)

    def validate_upsert_link_type(self, link_type: LinkType) -> list[IntegrityIssue]:
        """Return integrity violations for a hypothetical link-type upsert."""
        snapshot = copy.deepcopy(self._repository)
        snapshot.upsert_link_type(link_type)
        return IntegrityReporter().report(snapshot)

    def find_node_by_name(self, name: str, category: str | None = None) -> Node | None:
        """Find one node by name, optionally filtered by category."""
        candidates = [node for node in self._repository.list_nodes()
                      if node.name == name]
        if category is not None:
            candidates = [
                node for node in candidates if node.category == category]
        if not candidates:
            return None
        if len(candidates) > 1:
            ids = ", ".join(str(node.id) for node in candidates)
            raise ValueError(
                f"Ambiguous node name {name!r}; matches multiple nodes: {ids}. "
                "Pass node_id to disambiguate."
            )
        return candidates[0]

    def find_link_type_by_name(self, name: str) -> LinkType | None:
        """Find one link type by name."""
        candidates = [link_type for link_type in self._repository.list_link_types(
        ) if link_type.name == name]
        if not candidates:
            return None
        if len(candidates) > 1:
            ids = ", ".join(link_type.id for link_type in candidates)
            raise ValueError(
                f"Ambiguous link type name {name!r}; matches multiple IDs: {ids}. "
                "Pass link_type_id to disambiguate."
            )
        return candidates[0]

    def resolve_node_identity(self, node_id: str | None = None, node_name: str | None = None) -> Node:
        """Resolve a node identity using either node_id or node_name."""
        has_id = bool(node_id)
        has_name = bool(node_name)
        if has_id == has_name:
            raise ValueError("Provide exactly one of node_id or node_name")
        if has_id:
            return self.get_node(str(node_id))
        resolved = self.find_node_by_name(str(node_name))
        if resolved is None:
            raise KeyError(f"Node not found by name: {node_name}")
        return resolved

    def resolve_link_type_identity(self, link_type_id: str | None = None, link_type_name: str | None = None) -> LinkType:
        """Resolve a link-type identity using either id or name."""
        has_id = bool(link_type_id)
        has_name = bool(link_type_name)
        if has_id == has_name:
            raise ValueError(
                "Provide exactly one of link_type_id or link_type_name")
        if has_id:
            return self.get_link_type(str(link_type_id))
        resolved = self.find_link_type_by_name(str(link_type_name))
        if resolved is None:
            raise KeyError(f"Link type not found by name: {link_type_name}")
        return resolved

    def get_repo_schema_summary(self) -> dict[str, object]:
        """Return type-slot and link-type summary from the live snapshot."""
        resolver = Resolver(self._repository)
        types_payload: list[dict[str, object]] = []
        for type_node in self.list_types():
            parent_chain = resolver.fetch_parent_chain(type_node)
            slots = self.get_type_slots(str(type_node.id))
            types_payload.append(
                {
                    "id": str(type_node.id),
                    "name": type_node.name,
                    "parent_chain_ids": [str(parent.id) for parent in parent_chain],
                    "slots": [
                        {
                            "name": slot.name,
                            "field_type": slot.value_type,
                            "required": slot.required,
                            "description": slot.description,
                        }
                        for slot in slots
                    ],
                }
            )

        link_types_payload = [
            {
                "id": link_type.id,
                "name": link_type.name,
                "inverse_name": link_type.inverse_name,
                "cardinality": link_type.cardinality,
                "is_system": link_type.is_system,
            }
            for link_type in self.list_link_types()
        ]
        return {"types": types_payload, "link_types": link_types_payload}

    def get_parent_chain(self, type_id: str) -> list[Node]:
        """Return ordered ancestor types for a type node."""
        resolver = Resolver(self._repository)
        type_node = self.get_node(type_id)
        if not is_type(type_node):
            raise ValueError(f"Node is not a type: {type_id}")
        return resolver.fetch_parent_chain(type_node)

    def get_type_slots(self, type_id: str) -> list[NodeSlot]:
        """Return merged slots for a type with child override precedence."""
        resolver = Resolver(self._repository)
        type_node = self.get_node(type_id)
        if not is_type(type_node):
            raise ValueError(f"Node is not a type: {type_id}")
        chain = resolver.fetch_parent_chain(type_node) + [type_node]
        merged: dict[str, NodeSlot] = {}
        for candidate in chain:
            if not is_type(candidate):
                continue
            for slot in as_type(candidate).slots:
                merged[slot.name] = slot
        return [merged[name] for name in sorted(merged.keys())]

    def get_node_hydrated(self, node_id: str) -> dict[str, object]:
        """Return a node payload plus hydrated inherited properties."""
        resolver = Resolver(self._repository)
        node = self.get_node(node_id)

        def _jsonify(value: object) -> object:
            if isinstance(value, Node):
                return {
                    "id": str(value.id),
                    "name": value.name,
                    "category": value.category,
                    "type_id": str(value.type_id) if value.type_id is not None else None,
                }
            if isinstance(value, dict):
                return {str(key): _jsonify(item) for key, item in value.items()}
            if isinstance(value, list):
                return [_jsonify(item) for item in value]
            return value

        payload = node.model_dump()
        payload["hydrated_props"] = _jsonify(
            resolver.hydrate_node_with_inheritance(node))
        return payload

    def get_node_slot_names(self, node_id: str, effective: bool = True) -> list[str]:
        """Return slot/property names for a type or instance node."""
        node = self.get_node(node_id)
        if is_type(node):
            return [slot.name for slot in as_type(node).slots]
        if not effective:
            return sorted(node.props.keys())
        resolver = Resolver(self._repository)
        inherited = set(resolver.available_slot_names(node))
        local = set(node.props.keys())
        linked = {
            str(link.source_slot_name)
            for link in self.list_links()
            if link.link_type_id == SLOT_REF_LINK_TYPE_ID
            and str(link.source_node_id) == node_id
            and isinstance(link.source_slot_name, str)
            and link.source_slot_name
        }
        return sorted(inherited | local | linked)

    def get_node_slot_value(self, node_id: str, slot_name: str, effective: bool = True) -> dict[str, object]:
        """Return one slot/property value as a SlotValueEnvelope dict."""
        node = self.get_node(node_id)
        if is_type(node):
            for slot in as_type(node).slots:
                if slot.name == slot_name:
                    return SlotValueEnvelope(
                        slot_name=slot_name,
                        field_type_id=slot.value_type,
                        value=slot.model_dump(),
                        exists=True,
                        scope="own",
                    ).to_dict()
            return SlotValueEnvelope(
                slot_name=slot_name,
                field_type_id=None,
                value=None,
                exists=False,
                scope="absent",
            ).to_dict()

        contract = self._resolve_slot_contract(node=node, slot_name=slot_name)
        field_type_id = contract.value_type if contract is not None else None
        if not effective:
            if slot_name not in node.props:
                return SlotValueEnvelope(
                    slot_name=slot_name,
                    field_type_id=field_type_id,
                    value=None,
                    exists=False,
                    scope="absent",
                ).to_dict()
            return SlotValueEnvelope(
                slot_name=slot_name,
                field_type_id=field_type_id,
                value=node.props.get(slot_name),
                exists=True,
                scope="own",
            ).to_dict()

        ref_links = self._slot_ref_links(node_id=node_id, slot_name=slot_name)
        if ref_links:
            is_list = contract is not None and contract.source == SlotSource.REF_LIST
            value: object = ref_links if is_list else ref_links[0]
            return SlotValueEnvelope(
                slot_name=slot_name,
                field_type_id=field_type_id,
                value=value,
                exists=True,
                scope="own",
            ).to_dict()

        resolver = Resolver(self._repository)
        if slot_name in node.props:
            return SlotValueEnvelope(
                slot_name=slot_name,
                field_type_id=field_type_id,
                value=node.props.get(slot_name),
                exists=True,
                scope="own",
            ).to_dict()

        available = resolver.available_slot_names(node)
        if slot_name not in available:
            return SlotValueEnvelope(
                slot_name=slot_name,
                field_type_id=field_type_id,
                value=None,
                exists=False,
                scope="absent",
            ).to_dict()

        scope = resolver.effective_instance_value_scope(node, slot_name)
        return SlotValueEnvelope(
            slot_name=slot_name,
            field_type_id=field_type_id,
            value=None,
            scope="inherited" if scope else "absent",
            exists=scope is not None,
        ).to_dict()

    def get_node_slot_values(
        self,
        node_id: str,
        slot_names: list[str] | None = None,
        effective: bool = True,
    ) -> dict[str, object]:
        """Return slot/property values for one node in batch."""
        node = self.get_node(node_id)
        if is_type(node):
            slots = {slot.name: slot.model_dump()
                     for slot in as_type(node).slots}
            names = slot_names if slot_names is not None else sorted(
                slots.keys())
            return {
                "node_id": node_id,
                "effective": False,
                "values": {name: slots.get(name) for name in names},
            }
        if effective:
            names = slot_names if slot_names is not None else self.get_node_slot_names(
                node_id=node_id, effective=True)
            return {
                "node_id": node_id,
                "effective": True,
                "values": {name: self.get_node_slot_value(node_id=node_id, slot_name=name, effective=True) for name in names},
            }
        names = slot_names if slot_names is not None else sorted(
            node.props.keys())
        return {
            "node_id": node_id,
            "effective": False,
            "values": {name: node.props.get(name) for name in names},
        }

    def get_effective_props(self, instance_id: str) -> dict[str, object]:
        """Return effective slot values with inheritance scope metadata."""
        node = self.get_node(instance_id)
        names = self.get_node_slot_names(node_id=instance_id, effective=True)
        return {
            "node_id": instance_id,
            "category": node.category,
            "effective": {
                name: self.get_node_slot_value(
                    node_id=instance_id, slot_name=name, effective=True)
                for name in names
            },
        }

    def list_instances_of_type(self, type_id: str) -> list[Node]:
        """Return all instance nodes that reference a given type id."""
        return [
            node
            for node in self.list_nodes()
            if node.type_id is not None and str(node.type_id) == type_id
        ]

    def list_instances_of_type_query(
        self,
        type_query: str,
        *,
        include_descendants: bool = True,
    ) -> list[Node]:
        """Return instances for a type resolved from id/name/category query text."""
        type_node = self.resolve_type_query(type_query)
        type_ids = {str(type_node.id)}
        if include_descendants:
            type_ids = resolve_ref_type_to_type_ids(
                iter_types=self.list_types(),
                token=str(type_node.id).casefold(),
                iter_links=self.list_links(),
                iter_link_types=self.list_link_types(),
            )
        return [
            node
            for node in self.list_nodes()
            if node.type_id is not None and str(node.type_id) in type_ids
        ]

    def list_descendant_types(
        self,
        type_id: str,
        *,
        include_self: bool = False,
    ) -> list[Node]:
        """Return descendant types for a type id, optionally including itself."""
        type_node = self.get_node(type_id)
        if not is_type(type_node):
            raise ValueError(f"Node is not a type: {type_id}")
        return self.list_descendant_types_query(
            str(type_node.id),
            include_self=include_self,
        )

    def list_descendant_types_query(
        self,
        type_query: str,
        *,
        include_self: bool = False,
    ) -> list[Node]:
        """Return descendant types for a type query resolved by id/name/category."""
        type_node = self.resolve_type_query(type_query)
        descendant_ids = resolve_ref_type_to_type_ids(
            iter_types=self.list_types(),
            token=str(type_node.id).casefold(),
            iter_links=self.list_links(),
            iter_link_types=self.list_link_types(),
        )
        if not include_self:
            descendant_ids.discard(str(type_node.id))
        descendant_id_set = set(descendant_ids)
        return [
            node
            for node in self.list_types()
            if str(node.id) in descendant_id_set
        ]

    def resolve_type_query(self, type_query: str) -> Node:
        """Resolve one human-facing type query to a unique type node.

        Types are matched by id or name only.  ``instance_category`` and
        ``type_kind`` props are organizational hints for instances and are NOT
        used as type-query tokens.
        """
        token = normalize_search_text(type_query)
        if not token:
            raise ValueError("Type query is required.")

        id_matches: list[Node] = []
        name_matches: list[Node] = []
        type_nodes = self.list_types()
        for type_node in type_nodes:
            type_id = str(type_node.id)
            if type_id.casefold() == token:
                id_matches.append(type_node)

            if type_node.name.strip().casefold() == token:
                name_matches.append(type_node)

        if len(id_matches) == 1:
            return id_matches[0]
        if len(name_matches) == 1:
            return name_matches[0]

        matches = id_matches or name_matches
        if matches:
            labels = ", ".join(sorted(node.name for node in matches))
            raise ValueError(
                f"Type query {type_query!r} is ambiguous. Matches: {labels}."
            )

        suggestions = suggest_close_matches(
            type_query,
            [type_node.name for type_node in type_nodes],
        )
        if suggestions:
            raise ValueError(
                f"Type {type_query!r} does not exist. Did you mean: {', '.join(suggestions)}?"
            )
        raise ValueError(f"Type {type_query!r} does not exist.")

    def search_nodes_by_name(self, name_substring: str) -> list[Node]:
        """Case-insensitive name substring search across all nodes."""
        needle = normalize_search_text(name_substring)
        return [node for node in self.list_nodes() if needle in node.name.casefold()]

    def search_nodes_by_prop_value(self, prop_key: str, value_substring: str) -> list[tuple[Node, str]]:
        """Case-insensitive top-level string prop substring search for instances."""
        needle = value_substring.lower()
        matches: list[tuple[Node, str]] = []
        for node in self.list_nodes():
            if node.category == "_type":
                continue
            value = node.props.get(prop_key)
            if isinstance(value, str) and needle in value.lower():
                matches.append((node, value))
        return matches

    def validate_instance(self, instance_id: str) -> list[str]:
        """Validate one instance node against resolved type slot constraints."""
        validator = InstanceValidator(self._repository)
        node = self.get_node(instance_id)
        try:
            validator.validate_node(node)
        except ValueError as exc:
            return [str(exc)]
        return []

    def _slot_ref_links(self, node_id: str, slot_name: str) -> list[dict[str, str]]:
        return [
            {
                "link_id": str(link.id),
                "link_type_id": str(link.link_type_id),
                "target_node_id": str(link.target_node_id),
                "source_slot_name": slot_name,
            }
            for link in self.list_links()
            if link.link_type_id == SLOT_REF_LINK_TYPE_ID
            and str(link.source_node_id) == node_id
            and link.source_slot_name == slot_name
        ]

    def _resolve_slot_contract(self, node: Node, slot_name: str) -> NodeSlot | None:
        resolver = Resolver(self._repository)
        if is_type(node):
            chain = resolver.fetch_parent_chain(node) + [node]
        else:
            type_node = resolver.resolve_type_node_for_instance(node)
            if type_node is None:
                return None
            chain = resolver.fetch_parent_chain(type_node) + [type_node]
        resolved: NodeSlot | None = None
        for candidate in chain:
            if not is_type(candidate):
                continue
            for slot in as_type(candidate).slots:
                if slot.name == slot_name:
                    resolved = slot
        return resolved

    def set_slot_value(self, node_id: str, slot_name: str, value: object) -> OperationResult:
        """Set one node slot value through the IO write path."""
        def mutator(repo: Repository) -> set[str]:
            before = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
            }
            Mutator(repo).set_slot_value(node_id=node_id,
                                         slot_name=slot_name, value=value)
            after = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
            }
            return {node_id, *before, *after}

        return self.apply_op(mutator)

    def clear_slot_value(self, node_id: str, slot_name: str) -> OperationResult:
        """Clear one node slot value through the IO write path."""

        def mutator(repo: Repository) -> set[str]:
            before = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
            }
            Mutator(repo).discard_slot_value(
                node_id=node_id, slot_name=slot_name)
            after = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
            }
            return {node_id, *before, *after}

        return self.apply_op(mutator)

    def set_slot_values(self, node_id: str, updates: dict[str, object]) -> OperationResult:
        """Set multiple node slot values through the IO write path."""
        def mutator(repo: Repository) -> set[str]:
            before = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
            }
            mut = Mutator(repo)
            for slot_name, value in updates.items():
                mut.set_slot_value(
                    node_id=node_id, slot_name=slot_name, value=value)
            after = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
            }
            return {node_id, *before, *after}

        return self.apply_op(mutator)

    def clear_slot_values(self, node_id: str, slot_names: list[str]) -> OperationResult:
        """Clear multiple node slot values through the IO write path."""

        def mutator(repo: Repository) -> set[str]:
            before = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
            }
            mut = Mutator(repo)
            for slot_name in slot_names:
                mut.discard_slot_value(node_id=node_id, slot_name=slot_name)
            after = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
            }
            return {node_id, *before, *after}

        return self.apply_op(mutator)

    def promote_inline(
        self,
        parent_id: str,
        prop_path: str,
        new_name: str,
        description: str,
    ) -> tuple[OperationResult, str | None]:
        """Promote an inline composite to a standalone node through IO."""
        promoted_id: list[str] = []

        def mutator(repo: Repository) -> set[str]:
            before = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == parent_id
            }
            result_id = Mutator(repo).promote(
                parent_id=parent_id,
                prop_path=prop_path,
                new_name=new_name,
                description=description,
            )
            promoted_id.append(str(result_id))
            after = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == parent_id
            }
            return {str(result_id), parent_id, *before, *after}

        return self.apply_op(mutator), (promoted_id[0] if promoted_id else None)

    def inline_ref(self, parent_id: str, prop_path: str) -> OperationResult:
        """Inline a single-ref node back into parent props through IO."""

        def mutator(repo: Repository) -> set[str]:
            before = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == parent_id
            }
            Mutator(repo).inline(parent_id=parent_id, prop_path=prop_path)
            after = {
                str(link.id)
                for link in repo.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == parent_id
            }
            return {parent_id, *before, *after}

        return self.apply_op(mutator)

    def add_slot_to_type(self, type_id: str, slot: dict[str, object]) -> OperationResult:
        """Add or replace one slot on a type node through IO."""

        def mutator(repo: Repository) -> set[str]:
            Mutator(repo).add_slot(type_id=type_id, slot=slot)
            return {type_id}

        return self.apply_op(mutator)

    def remove_slot_from_type(self, type_id: str, slot_name: str) -> OperationResult:
        """Remove one slot by name from a type node through IO."""

        def mutator(repo: Repository) -> set[str]:
            Mutator(repo).remove_slot(type_id=type_id, slot_name=slot_name)
            return {type_id}

        return self.apply_op(mutator)

    def update_slot_on_type(self, type_id: str, original_name: str, slot: dict[str, object]) -> OperationResult:
        """Update one slot contract on a type node through IO."""

        def mutator(repo: Repository) -> set[str]:
            Mutator(repo).update_slot(type_id=type_id,
                                      slot_name=original_name, slot=slot)
            return {type_id}

        return self.apply_op(mutator)

    def check_integrity(self, mode: str = "report_only") -> tuple[OperationResult | None, dict[str, object]]:
        """Report integrity issues and optionally apply safe/prune repairs through IO."""

        def inspect(repo: Repository) -> tuple[dict[str, object], set[str]]:
            reporter = IntegrityReporter()
            issues = reporter.report(repo)
            report: dict[str, object] = {
                "mode": mode,
                "issue_count": len(issues),
                "issues": [issue.model_dump() for issue in issues],
            }
            touched: set[str] = set()
            if mode in {"repair_safe", "repair_prune"}:
                repairer = IntegrityRepairer(reporter=reporter)
                repair_result = repairer.repair(repo, mode=mode)
                touched = set(repair_result.removed_link_ids)
                report["removed_links"] = list(repair_result.removed_link_ids)
                report["post_issue_count"] = len(repair_result.issues_after)
                report["post_issues"] = [issue.model_dump()
                                         for issue in repair_result.issues_after]
            return report, touched

        if mode == "report_only":
            report, _ = inspect(self._repository)
            return None, report
        if mode not in {"repair_safe", "repair_prune"}:
            raise ValueError(
                "mode must be one of: report_only, repair_safe, repair_prune")

        payload: list[dict[str, object]] = []

        def mutator(repo: Repository) -> set[str]:
            report, touched = inspect(repo)
            payload.append(report)
            return touched

        result = self.apply_op(mutator)
        return result, (payload[0] if payload else {"mode": mode, "issue_count": 0, "issues": []})

    # ------------------------------------------------------------------
    # Repository access (read-only forwarding)
    # ------------------------------------------------------------------

    def preview_delete_nodes(
        self,
        node_ids: list[NodeId] | list[str],
    ) -> DeleteImpact:
        """Return the delete impact for *node_ids* without mutating anything.

        Delegates to :func:`analyze_delete_impact`.  Callers use the result
        to determine whether a :class:`DeleteResolution` is required before
        calling :meth:`delete_nodes`.
        """
        return analyze_delete_impact(self._repository, node_ids)

    def preview_delete_links(
        self,
        link_ids: list[str],
    ) -> LinkDeleteImpact:
        """Return the delete impact for the given link instance IDs.

        Link deletion is always structurally safe; callers use the result
        for confirmation UIs only.
        """
        affected_nodes: set[str] = set()
        valid_ids: list[str] = []
        for link_id in link_ids:
            link = self._repository.find_link(link_id)
            if link is not None:
                valid_ids.append(link_id)
                affected_nodes.add(link.source_node_id)
                affected_nodes.add(link.target_node_id)
        return LinkDeleteImpact(
            link_ids=tuple(valid_ids),
            affected_node_ids=tuple(sorted(affected_nodes)),
        )

    def preview_delete_link_type(
        self,
        link_type_id: str,
    ) -> LinkTypeDeleteImpact:
        """Return the delete impact for a single link-type definition.

        Deletion is blocked if live links reference this type.
        """
        lt = self._repository.find_link_type(link_type_id)
        lt_name = lt.name if lt is not None else link_type_id
        dep_links: list[str] = []
        affected_nodes: set[str] = set()
        for link in self._repository.list_links():
            if str(link.link_type_id) == link_type_id:
                dep_links.append(link.id)
                affected_nodes.add(link.source_node_id)
                affected_nodes.add(link.target_node_id)
        return LinkTypeDeleteImpact(
            link_type_id=link_type_id,
            link_type_name=lt_name,
            dependent_link_ids=tuple(dep_links),
            affected_node_ids=tuple(sorted(affected_nodes)),
        )

    def preview_change_type_slots(
        self,
        type_id: str,
        changes: TypeSlotChanges,
    ) -> TypeSlotChangeImpact:
        """Return the impact of proposed type-slot changes on existing instances.

        Delegates to :mod:`lks_utils.knowledge.io.type_change_resolution`.
        Callers should pass the result to ``change_slot_value_type`` as the
        *resolution* to confirm intent before the mutation is applied.
        """
        from lks_utils.knowledge.io.type_change_resolution import (
            AffectedInstanceInfo,
            TypeSlotChangeImpact,
        )

        affected: list[AffectedInstanceInfo] = []
        for change in changes.changes:
            if change.change_kind in ("remove", "change_value_type"):
                for node in self._repository.list_nodes():
                    if str(node.type_id) != type_id:
                        continue
                    props = node.props or {}
                    if change.slot_name in props:
                        affected.append(
                            AffectedInstanceInfo(
                                instance_id=node.id,
                                instance_name=node.name,
                                slot_name=change.slot_name,
                                current_value_summary=str(
                                    props[change.slot_name])[:80],
                            )
                        )
        return TypeSlotChangeImpact(
            type_id=type_id,
            affected_instances=tuple(affected),
        )

    # ------------------------------------------------------------------
    # Multi-node delete (two-phase: preview → apply with optional resolution)
    # ------------------------------------------------------------------

    def delete_nodes(
        self,
        node_ids: list[NodeId] | list[str],
        *,
        resolution: DeleteResolution | None = None,
    ) -> OperationResult:
        """Delete multiple nodes.

        Two-phase contract
        ------------------
        1. :meth:`preview_delete_nodes` returns a :class:`DeleteImpact`.
        2. If the impact has incoming references, the caller must supply a
           :class:`DeleteResolution`; otherwise the method returns
           ``OperationResult(status="blocked", blocking_impact=impact)``.

        When a resolution is supplied, this method applies it (removes/replaces
        dangling references) before deleting the target nodes.
        """
        impact = self.preview_delete_nodes(node_ids)

        if not impact.is_safe:
            if resolution is None:
                return OperationResult(
                    status="blocked",
                    touched_ids=frozenset(),
                    validated_ids=frozenset(),
                    issues=(),
                    blocking_impact=impact,
                )

        str_ids = [str(nid) for nid in node_ids]

        def mutator(repo: Repository) -> set[str]:
            touched: set[str] = set()

            # 1. Apply resolution entries to remove/replace dangling refs
            if resolution is not None:
                for entry in resolution.entries:
                    ref = entry.incoming_ref
                    src = repo.find_node(ref.source_node_id)
                    if src is None:
                        continue
                    if ref.source_slot_path == ("type_id",):
                        if entry.mode == "remove_ref":
                            repo.upsert(src.model_copy(
                                update={"type_id": None}))
                            touched.add(src.id)
                        elif entry.mode == "replace" and entry.replacement_id is not None:
                            repo.upsert(
                                src.model_copy(
                                    update={"type_id": NodeId.from_str(
                                        entry.replacement_id)}
                                )
                            )
                            touched.add(src.id)
                        continue

                    slot_name: str | None
                    if ref.source_slot_path == ("slot_ref",):
                        slot_name = None
                    else:
                        slot_name = ref.source_slot_path[0] if ref.source_slot_path else None
                    matching_links = [
                        link
                        for link in repo.list_links()
                        if link.link_type_id == SLOT_REF_LINK_TYPE_ID
                        and str(link.source_node_id) == str(src.id)
                        and str(link.target_node_id) == ref.target_node_id
                        and (slot_name is None or str(link.source_slot_name or "") == slot_name)
                    ]

                    if entry.mode == "remove_ref":
                        for link in matching_links:
                            repo.delete_link(link.id)
                            touched.add(link.id)
                    elif entry.mode == "replace" and entry.replacement_id is not None:
                        for link in matching_links:
                            repo.upsert_link(
                                link.model_copy(
                                    update={"target_node_id": entry.replacement_id})
                            )
                            touched.add(link.id)

            # 2. Delete target nodes and their attached links
            for nid in str_ids:
                for link in list(repo.list_links()):
                    if link.source_node_id == nid or link.target_node_id == nid:
                        repo.delete_link(link.id)
                        touched.add(link.id)
                repo.delete(nid)
                touched.add(nid)

            return touched

        return self.apply_op(mutator)

    @property
    def repository(self) -> Repository:
        """Return the current live repository (snapshot after last apply_op)."""
        return self._repository

    @property
    def repository_root(self) -> Path | None:
        """Return the configured repository root path."""
        return self._repository_root

    @repository_root.setter
    def repository_root(self, value: Path | None) -> None:
        """Set the configured repository root path."""
        self._repository_root = value

    @property
    def reverse_ref_index(self) -> ReverseRefIndex:
        """Return the reverse-ref index maintained alongside the repository."""
        return self._reverse_ref_index


# ------------------------------------------------------------------
# Module-level helpers (shared with EditorSession delegation path)
# ------------------------------------------------------------------

def _classify_touched_ids(
    old_repo: Repository,
    snapshot: Repository,
    touched_ids: set[str],
    reverse_ref_index: ReverseRefIndex,
) -> tuple[set[str], set[str], set[str]]:
    """Classify *touched_ids* into nodes, link-types, and links.

    Also expands ``touched_link_ids`` to include any links whose on-disk path
    depends on a renamed node or link-type (source/target/type name is embedded
    in the file path).  Those links' files must be moved even though their IDs
    did not change.

    Unknown IDs (e.g. graph-view IDs) are silently ignored.

    Returns ``(touched_node_ids, touched_link_type_ids, touched_link_ids)``.
    """
    t_nodes: set[str] = set()
    t_link_types: set[str] = set()
    t_links: set[str] = set()
    ancestry_changed_type_ids: set[str] = set()

    for tid in touched_ids:
        old_node = old_repo.find_node(tid)
        new_node = snapshot.find_node(tid)
        if old_node is not None or new_node is not None:
            t_nodes.add(tid)
            if (
                old_node is not None
                and new_node is not None
                and _node_path_affects_descendants(old_repo, snapshot, tid)
            ):
                descendant_ids = resolve_ref_type_to_type_ids(
                    iter_types=snapshot.list_types(),
                    token=tid.casefold(),
                    iter_links=snapshot.list_links(),
                    iter_link_types=snapshot.list_link_types(),
                )
                expanded_type_ids = set(descendant_ids)
                expanded_type_ids.add(tid)
                t_nodes.update(expanded_type_ids)
                ancestry_changed_type_ids.update(expanded_type_ids)
            # Renamed node: links embedding this node's name in their path need
            # their files moved too.
            if (
                old_node is not None
                and new_node is not None
                and old_node.name != new_node.name
            ):
                for ref_id in reverse_ref_index.referencers_of(tid):
                    if (
                        old_repo.find_link(ref_id) is not None
                        or snapshot.find_link(ref_id) is not None
                    ):
                        t_links.add(ref_id)
            continue

        old_lt = old_repo.find_link_type(tid)
        new_lt = snapshot.find_link_type(tid)
        if old_lt is not None or new_lt is not None:
            t_link_types.add(tid)
            # Renamed link-type: links embedding this type's name in their path
            # need their files moved too.
            if (
                old_lt is not None
                and new_lt is not None
                and old_lt.name != new_lt.name
            ):
                for ref_id in reverse_ref_index.referencers_of(tid):
                    if (
                        old_repo.find_link(ref_id) is not None
                        or snapshot.find_link(ref_id) is not None
                    ):
                        t_links.add(ref_id)
            continue

        if (
            old_repo.find_link(tid) is not None
            or snapshot.find_link(tid) is not None
        ):
            t_links.add(tid)
        # else: unknown id (graph-view, etc.) — silently ignored

    if ancestry_changed_type_ids:
        t_nodes.update(
            _instances_with_changed_type_ancestry(
                old_repo=old_repo,
                snapshot=snapshot,
            )
        )

    return t_nodes, t_link_types, t_links


def _node_path_affects_descendants(
    old_repo: Repository,
    snapshot: Repository,
    node_id: str,
) -> bool:
    old_node = old_repo.find_node(node_id)
    new_node = snapshot.find_node(node_id)
    if old_node is None or new_node is None:
        return False
    if old_node.name != new_node.name:
        return True
    if old_node.category == "_type" and new_node.category == "_type":
        return _type_ancestry_names(old_repo, node_id) != _type_ancestry_names(snapshot, node_id)
    if old_node.category != new_node.category:
        return True
    return False


def _type_ancestry_names(repository: Repository, node_id: str) -> tuple[str, ...]:
    node = repository.find_node(node_id)
    if node is None:
        return ()
    nodes = {str(candidate.id): candidate for candidate in repository.list_nodes()}
    return tuple(compute_type_ancestry(node_id, repository.list_links(), nodes))


def _instance_ancestry_names(repository: Repository, node_id: str) -> tuple[str, ...]:
    node = repository.find_node(node_id)
    if node is None or node.category == "_type":
        return ()
    nodes = {str(candidate.id)             : candidate for candidate in repository.list_nodes()}
    return tuple(compute_instance_ancestry(node_id, links=repository.list_links(), nodes=nodes))


def _instances_with_changed_type_ancestry(
    old_repo: Repository,
    snapshot: Repository,
) -> set[str]:
    instance_ids = {
        str(node.id) for node in old_repo.list_instances()
    } | {
        str(node.id) for node in snapshot.list_instances()
    }
    changed: set[str] = set()
    for instance_id in instance_ids:
        old_node = old_repo.find_node(instance_id)
        new_node = snapshot.find_node(instance_id)
        if old_node is None or new_node is None:
            continue
        if old_node.category == "_type" or new_node.category == "_type":
            continue
        if _instance_ancestry_names(old_repo, instance_id) != _instance_ancestry_names(snapshot, instance_id):
            changed.add(instance_id)
    return changed


def _apply_incremental_ref_update(
    old_repo: Repository,
    snapshot: Repository,
    t_nodes: set[str],
    t_links: set[str],
    reverse_ref_index: ReverseRefIndex,
) -> None:
    """Update the reverse-ref index for only the changed nodes and links.

    Skips link-type IDs: link types are only *targets* in the index, never
    referrers, so no index update is needed when a link type changes.
    """
    for node_id in t_nodes:
        old_node = old_repo.find_node(node_id)
        new_node = snapshot.find_node(node_id)
        if old_node is None and new_node is not None:
            reverse_ref_index.on_node_added(new_node)
        elif old_node is not None and new_node is None:
            reverse_ref_index.on_node_removed(node_id)
        elif old_node is not None and new_node is not None:
            reverse_ref_index.on_node_mutated(old_node, new_node)

    for link_id in t_links:
        old_lk = old_repo.find_link(link_id)
        new_lk = snapshot.find_link(link_id)
        if old_lk is None and new_lk is not None:
            reverse_ref_index.on_link_added(new_lk)
        elif old_lk is not None and new_lk is None:
            reverse_ref_index.on_link_removed(link_id)
        elif old_lk is not None and new_lk is not None:
            if (
                old_lk.source_node_id != new_lk.source_node_id
                or old_lk.target_node_id != new_lk.target_node_id
                or old_lk.link_type_id != new_lk.link_type_id
            ):
                reverse_ref_index.on_link_removed(link_id)
                reverse_ref_index.on_link_added(new_lk)


def _collect_issues(
    validation_index: ValidationIndex,
    validated_ids: frozenset[str],
) -> tuple[ValidationIssue, ...]:
    """Gather validation issues for all *validated_ids* from the index."""
    result: list[ValidationIssue] = []
    for oid in validated_ids:
        status = validation_index.status_for(oid)
        if not status.is_valid:
            result.append(ValidationIssue(
                object_id=oid, reasons=status.reasons))
    return tuple(result)


__all__ = [
    "KnowledgeIO",
    "_classify_touched_ids",
    "_apply_incremental_ref_update",
    "_collect_issues",
]

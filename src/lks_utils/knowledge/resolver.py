"""Reference resolver for hydrated node views and inheritance traversal."""
from __future__ import annotations

from lks_utils.knowledge.links.link_types.link_type_system import (
    EXTENDS_LINK_TYPE_ID,
    INSTANCE_OF_LINK_TYPE_ID,
)
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.instance_validator import PROTOTYPE_ID_PROP
from lks_utils.knowledge.repository import Repository


class Resolver:
    """Resolves structure-backed dependencies and edge-based inheritance paths."""

    def __init__(self, repository: Repository) -> None:
        self._repository = repository
        self._reverse_index: dict[str, set[str]] = {}
        self.refresh_reverse_index()

    def refresh_reverse_index(self) -> None:
        """Rebuild reverse dependencies from current repository state."""
        reverse_index: dict[str, set[str]] = {}

        # Node type references.
        for node in self._repository.list_nodes():
            node_id_str = str(node.id)
            if node.type_id is not None:
                reverse_index.setdefault(
                    str(node.type_id), set()).add(node_id_str)

        # Slot-ref references.
        for link in self._repository.list_links():
            if str(link.link_type_id) != SLOT_REF_LINK_TYPE_ID:
                continue
            reverse_index.setdefault(str(link.target_node_id), set()).add(
                str(link.source_node_id)
            )

        self._reverse_index = reverse_index

    def get_dependents(self, node_id: str | NodeId) -> list[str]:
        """Return ULID strings of nodes that directly reference *node_id*."""
        return sorted(self._reverse_index.get(str(node_id), set()))

    def ref_count(self, node_id: str | NodeId) -> int:
        """Return how many nodes reference *node_id*."""
        return len(self._reverse_index.get(str(node_id), set()))

    def hydrate_node(self, node: Node) -> dict[str, object]:
        """Return a recursively hydrated props dict for *node*."""
        hydrated: dict[str, object] = {}
        for key, value in node.props.items():
            hydrated[key] = self._hydrate_value(value)
        return hydrated

    # ------------------------------------------------------------------ inheritance

    _MAX_DEPTH = 32  # guard against cycles in extends chain

    def fetch_parent_chain(self, type_node: Node) -> list[Node]:
        """Return ordered ancestor type-nodes for *type_node*, outermost first.

        Traverses ``extends`` edges upward. Stops at the root or after
        ``_MAX_DEPTH`` hops to guard against cycles.

        Example: Cat -extends-> Mammalia -extends-> Animal
        Returns: [Animal, Mammalia]
        """
        links = self._repository.list_links()
        chain: list[Node] = []
        current_id = str(type_node.id)
        for _ in range(self._MAX_DEPTH):
            parent_id = self._find_link_target(
                current_id, EXTENDS_LINK_TYPE_ID, links)
            if parent_id is None:
                break
            try:
                parent_node = self._repository.get(parent_id)
            except KeyError:
                break
            chain.append(parent_node)
            current_id = parent_id
        chain.reverse()
        return chain

    def fetch_type_for_instance(self, instance_node: Node) -> Node | None:
        """Return the type Node for *instance_node* via an ``instance_of`` edge, or None."""
        links = self._repository.list_links()
        type_id = self._find_link_target(
            str(instance_node.id), INSTANCE_OF_LINK_TYPE_ID, links)
        if type_id is None:
            return None
        try:
            return self._repository.get(type_id)
        except KeyError:
            return None

    def resolve_type_node_for_instance(self, instance_node: Node) -> Node | None:
        """Resolve type node for an instance via ``node.type_id`` first, then link fallback."""
        if instance_node.type_id is not None:
            try:
                candidate = self._repository.get(instance_node.type_id)
                if is_type(candidate):
                    return candidate
            except KeyError:
                pass
        return self.fetch_type_for_instance(instance_node)

    def is_slot_overridden_locally(self, node: Node, slot_name: str) -> bool:
        """Return ``True`` when *node* carries an explicit local value for *slot_name*."""
        return slot_name in node.props

    def slot_is_inherited_for_node(self, node: Node, slot_name: str) -> bool:
        """Return ``True`` when *slot_name* comes from ancestry and has no local value."""
        if slot_name in node.props:
            return False
        available = self.available_slot_names(node)
        return slot_name in available

    def available_slot_names(self, node: Node) -> set[str]:
        """Return merged slot names available to *node* through inheritance."""
        if is_type(node):
            chain = self.fetch_parent_chain(node) + [node]
            return self._slot_names_from_type_chain(chain)

        type_node = self.resolve_type_node_for_instance(node)
        if type_node is None:
            return set()
        chain = self.fetch_parent_chain(type_node) + [type_node]
        return self._slot_names_from_type_chain(chain)

    def effective_instance_value_scope(self, instance_node: Node, slot_name: str) -> str:
        """Return value scope for an instance slot.

        Returns one of: ``local_instance``, ``instance_chain_default``,
        ``type_default``, ``unknown``.
        """
        if is_type(instance_node):
            return "unknown"

        slot_names = self.available_slot_names(instance_node)
        if slot_name not in slot_names:
            return "unknown"
        if slot_name in instance_node.props:
            return "local_instance"

        type_node = self.resolve_type_node_for_instance(instance_node)
        if type_node is None:
            return "unknown"

        prototype_chain = self._fetch_prototype_chain(
            instance_node, str(type_node.id))
        for prototype in reversed(prototype_chain):
            if slot_name in prototype.props:
                return "instance_chain_default"
        return "type_default"

    def hydrate_node_with_inheritance(self, node: Node) -> dict[str, object]:
        """Return a props dict with slots merged from the full inheritance chain.

        For type nodes: merges slots from all ancestor types (outermost first),
        then overlays the node's own slots (child overrides parent).

        For instance nodes: resolves the type chain via ``instance_of`` + ``extends``,
        then merges inherited slots.
        """
        if is_type(node):
            # Ancestors are everything *above* node (not including node itself)
            inherited_nodes = self.fetch_parent_chain(node)
        else:
            type_node = self.resolve_type_node_for_instance(node)
            if type_node is None:
                return self.hydrate_node(node)
            # For instances: ancestors of the type, plus the direct type
            inherited_nodes = self.fetch_parent_chain(type_node) + [type_node]

        # Build inherited slot baseline (ancestors outermost-first)
        inherited_slots = self._merge_slots(inherited_nodes)

        # Overlay node's own slots on top of inherited baseline
        base_props = dict(node.props)
        own_slots: list[dict[str, object]] = [
            s if isinstance(s, dict) else s.model_dump()
            for s in (node.props.get("slots") or [])
        ]
        final_slots = _merge_slot_lists(inherited_slots, own_slots)
        if final_slots:
            base_props["slots"] = final_slots

        hydrated: dict[str, object] = {}
        for key, value in base_props.items():
            hydrated[key] = self._hydrate_value(value)
        return hydrated

    def _merge_slots(self, nodes_outermost_first: list[Node]) -> list[dict[str, object]]:
        """Merge slot lists from *nodes_outermost_first*, child overrides parent."""
        merged: list[dict[str, object]] = []
        for ancestor in nodes_outermost_first:
            raw = ancestor.props.get("slots") or []
            ancestor_slots: list[dict[str, object]] = [
                s if isinstance(s, dict) else s.model_dump()
                for s in raw
            ]
            merged = _merge_slot_lists(merged, ancestor_slots)
        return merged

    def _slot_names_from_type_chain(self, chain: list[Node]) -> set[str]:
        names: set[str] = set()
        for candidate in chain:
            if not is_type(candidate):
                continue
            for slot in as_type(candidate).slots:
                names.add(slot.name)
        return names

    def _fetch_prototype_chain(self, instance_node: Node, type_id: str) -> list[Node]:
        """Return prototype chain from nearest parent upward for same-typed instances."""
        chain: list[Node] = []
        current: Node | None = instance_node
        visited: set[str] = set()
        while current is not None:
            prototype_id = current.props.get(PROTOTYPE_ID_PROP)
            if not isinstance(prototype_id, str) or not prototype_id:
                break
            if prototype_id in visited:
                break
            visited.add(prototype_id)
            try:
                prototype_node = self._repository.get(prototype_id)
            except KeyError:
                break
            if str(prototype_node.type_id) != type_id:
                break
            chain.append(prototype_node)
            current = prototype_node
        return chain

    @staticmethod
    def _find_link_target(
        source_id: str,
        link_type_id: str,
        links: list[object],
    ) -> str | None:
        for link in links:
            # type: ignore[union-attr]
            if str(link.link_type_id) == link_type_id and str(link.source_node_id) == source_id:
                return str(link.target_node_id)  # type: ignore[union-attr]
        return None

    def _hydrate_value(self, value: object) -> object:
        if isinstance(value, dict):
            return {key: self._hydrate_value(v) for key, v in value.items()}
        if isinstance(value, list):
            return [self._hydrate_value(item) for item in value]
        return value


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _merge_slot_lists(
    base: list[dict[str, object]],
    override: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Merge two slot lists — *override* entries replace *base* entries with the same name.

    Slots are keyed by their ``name`` field. Order: base slots first (preserving order),
    then any override slots not present in base appended at the end.
    """
    result: dict[str, dict[str, object]] = {
        s["name"]: s for s in base if "name" in s  # type: ignore[index]
    }
    for slot in override:
        name = slot.get("name")
        if name is not None:
            result[name] = slot  # type: ignore[index]
    return list(result.values())

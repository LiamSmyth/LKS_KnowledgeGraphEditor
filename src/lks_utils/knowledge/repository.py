"""Repository abstraction for ULID-keyed knowledge nodes, link types, and link instances."""
from __future__ import annotations

import json
from pathlib import Path

from lks_utils.core.file_io import atomic_write, safe_filename
from lks_utils.knowledge._repository.cache_invalidation import (
    require_repo_root,
    sync_index,
)
from lks_utils.knowledge._repository.disk_io import (
    load_index_data,
    load_repository,
    pretty_json,
    save_new_links,
    save_new_link_types,
    save_repository,
    save_touched,
)
from lks_utils.knowledge._repository.graph_views import (
    build_views_index,
    delete_graph_view,
    ensure_unique_graph_view_name,
    graph_view_relpath,
    list_graph_views,
    load_graph_view,
    save_graph_view,
)
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.repository_hierarchy import (
    link_instance_relpath,
    storage_folder_for_node,
    unique_link_type_relpath,
)


class Repository:
    """In-memory CRUD repository with stable IDs and human-readable storage paths.

    Storage layout::

        <root>/
            index.json
            nodes/
                instances/
                    <kind>/
                        <safe-name>.json
                types/
                    <type-kind>/
                        <safe-name>.json

    ULIDs remain the runtime identity and the only durable reference target.
    Disk layout is derived from the node's kind/type and user-facing name so
    filenames stay readable. Renames and filename collisions may change the
    on-disk slug (`_2`, `_3`, ...) but never the node ID or reference
    relationships that point at it.
    """

    def __init__(self, *, source_repo_id: str = "default") -> None:
        self._nodes: dict[str, Node] = {}
        self._link_types: dict[str, LinkType] = {}
        self._links: dict[str, LinkInstance] = {}
        self._source_repo_id: str = source_repo_id
        self._repo_root: Path | None = None
        self._names: dict[str, str] = {}
        self._link_type_names: dict[str, str] = {}

    @property
    def source_repo_id(self) -> str:
        """Return the identifier for this repository's provenance."""
        return self._source_repo_id

    def upsert(self, node: Node) -> None:
        """Insert or replace a node by its ULID identity.

        Name uniqueness is enforced within the repository. If a different node
        already owns the requested name, a numeric suffix is applied.
        """
        node_id = str(node.id)
        existing = self._nodes.get(node_id)
        if existing is not None and existing.name != node.name:
            self._names.pop(existing.name, None)

        final_name = self._resolve_unique_name(node.name, exclude_id=node_id)
        if final_name != node.name:
            node = node.model_copy(update={"name": final_name})
        self._nodes[node_id] = node
        self._names[final_name] = node_id

    def get(self, node_id: str | NodeId) -> Node:
        """Return one node by ULID string or ``NodeId``; raises KeyError."""
        return self._nodes[str(node_id)]

    def find_node(self, node_id: str) -> Node | None:
        """Return one node by ULID string, or None if absent."""
        return self._nodes.get(node_id)

    def delete(self, node_id: str | NodeId) -> None:
        """Remove a node by ULID; raises KeyError if absent."""
        key = str(node_id)
        node = self._nodes.pop(key)
        self._names.pop(node.name, None)

    def list_nodes(self) -> list[Node]:
        """Return all nodes in insertion/time-sorted ULID order."""
        return sorted(self._nodes.values(), key=lambda n: str(n.id))

    def list_types(self) -> list[Node]:
        """Return only type-nodes (category == '_type')."""
        return [n for n in self.list_nodes() if n.category == "_type"]

    def list_instances(self) -> list[Node]:
        """Return only non-type nodes."""
        return [n for n in self.list_nodes() if n.category != "_type"]

    # ------------------------------------------------------------------ links

    def upsert_link_type(self, link_type: LinkType) -> None:
        """Insert or replace a link-type vocabulary entry."""
        link_type_id = str(link_type.id)
        existing = self._link_types.get(link_type_id)
        if existing is not None and existing.name != link_type.name:
            self._link_type_names.pop(existing.name, None)

        final_name = self._resolve_unique_link_type_name(
            link_type.name,
            exclude_id=link_type_id,
        )
        if final_name != link_type.name:
            link_type = link_type.model_copy(update={"name": final_name})

        self._link_types[link_type_id] = link_type
        self._link_type_names[final_name] = link_type_id

    def get_link_type(self, link_type_id: str) -> LinkType:
        """Return one link type by id; raises KeyError if absent."""
        return self._link_types[link_type_id]

    def find_link_type(self, link_type_id: str) -> LinkType | None:
        """Return one link type by id, or None if absent."""
        return self._link_types.get(link_type_id)

    def list_link_types(self) -> list[LinkType]:
        """Return all link types in stable id order."""
        return sorted(self._link_types.values(), key=lambda lt: lt.id)

    def delete_link_type(self, link_type_id: str) -> None:
        """Remove a link type and cascade-delete all its instances."""
        removed = self._link_types.pop(link_type_id, None)
        if removed is not None:
            self._link_type_names.pop(removed.name, None)
        for link_id in [k for k, v in self._links.items()
                        if v.link_type_id == link_type_id]:
            self._links.pop(link_id, None)

    def upsert_link(self, link: LinkInstance) -> None:
        """Insert or replace a link instance."""
        self._links[link.id] = link

    def list_links(self) -> list[LinkInstance]:
        """Return all link instances in stable id order."""
        return sorted(self._links.values(), key=lambda lk: lk.id)

    def find_link(self, link_id: str) -> LinkInstance | None:
        """Return one link instance by id, or None if absent."""
        return self._links.get(link_id)

    def delete_link(self, link_id: str) -> None:
        """Remove a link instance by id; no-op if absent."""
        self._links.pop(link_id, None)

    # --------------------------------------------------------------- graph views

    def save_graph_view(self, view: GraphView) -> None:
        """Persist one graph-view JSON under ``<repo_root>/views/<safe_name>.json``."""
        save_graph_view(repository=self, view=view)

    def load_graph_view(self, view_id: str) -> GraphView:
        """Load one graph-view by id from ``<repo_root>/views``."""
        return load_graph_view(repository=self, view_id=view_id)

    def list_graph_views(self) -> list[GraphView]:
        """Return all graph views found under ``<repo_root>/views``."""
        return list_graph_views(repository=self)

    def delete_graph_view(self, view_id: str) -> None:
        """Delete one graph-view file by id; no-op when absent."""
        delete_graph_view(repository=self, view_id=view_id)

    def graph_view_relpath(self, view_id: str) -> str | None:
        """Return stored relative path for a graph view id, when known."""
        return graph_view_relpath(repository=self, view_id=view_id)

    def ensure_unique_graph_view_name(
        self,
        desired: str,
        *,
        exclude_id: str | None = None,
    ) -> str:
        """Return a graph-view name that is unique in the repository."""
        return ensure_unique_graph_view_name(
            repository=self,
            desired=desired,
            exclude_id=exclude_id,
        )

    def _resolve_unique_name(
        self,
        desired: str,
        *,
        exclude_id: str | None = None,
    ) -> str:
        """Return *desired* if unique, else append ``_2``, ``_3``, ..."""
        owner = self._names.get(desired)
        if owner is None or owner == exclude_id:
            return desired
        suffix = 2
        while True:
            candidate = f"{desired}_{suffix}"
            owner = self._names.get(candidate)
            if owner is None or owner == exclude_id:
                return candidate
            suffix += 1

    def _resolve_unique_link_type_name(
        self,
        desired: str,
        *,
        exclude_id: str | None = None,
    ) -> str:
        """Return link-type name with deterministic numeric suffix on collision."""
        owner = self._link_type_names.get(desired)
        if owner is None or owner == exclude_id:
            return desired
        suffix = 2
        while True:
            candidate = f"{desired}_{suffix}"
            owner = self._link_type_names.get(candidate)
            if owner is None or owner == exclude_id:
                return candidate
            suffix += 1

    def save(self, directory: str | Path) -> None:
        """Persist all nodes, link types, link instances, and the sidecar index to *directory*."""
        save_repository(repository=self, directory=directory)

    def save_new_links(
        self,
        directory: str | Path,
        *,
        new_link_ids: set[str],
    ) -> None:
        """Persist only newly created links (no old_repo needed for diff).

        O(k) file I/O where k = number of new links.  Fast path for link creation
        workflows that have no renames/deletions — only new link writes.

        Use this instead of save_touched() when you know:
        - These links did not exist before (no old_path to delete)
        - No rename-detection needed (just write + index update)
        - old_repo deep copy would be wasteful

        Ideal for: interactive link creation in UI with sub-100ms response target.
        """
        save_new_links(
            repository=self,
            directory=directory,
            new_link_ids=new_link_ids,
        )

    def save_new_link_types(
        self,
        directory: str | Path,
        *,
        new_link_type_ids: set[str],
    ) -> None:
        """Persist only newly created link types (no old_repo needed for diff).

        O(k) file I/O where k = number of new link types.  Fast path for link type
        creation workflows that have no renames/deletions — only new writes.

        Use this instead of save_touched() when you know:
        - These link types did not exist before (no old_path to delete)
        - No rename-detection needed (just write + index update)
        - old_repo deep copy would be wasteful

        Ideal for: interactive link type creation in UI with sub-100ms response target.
        """
        save_new_link_types(
            repository=self,
            directory=directory,
            new_link_type_ids=new_link_type_ids,
        )

    def save_touched(
        self,
        directory: str | Path,
        *,
        touched_node_ids: set[str],
        touched_link_type_ids: set[str],
        touched_link_ids: set[str],
        old_repo: Repository,
    ) -> None:
        """Persist only the touched objects; always rewrites index.json.

        O(k) file I/O where k = number of changed objects.  Use when
        ``apply_mutation`` knows exactly what changed.  Falls back gracefully
        when called with empty sets (writes only the index).

        ``old_repo`` is the repository state *before* this mutation; it is used
        to locate and delete stale files when objects are renamed or removed.
        """
        save_touched(
            repository=self,
            directory=directory,
            touched_node_ids=touched_node_ids,
            touched_link_type_ids=touched_link_type_ids,
            touched_link_ids=touched_link_ids,
            old_repo=old_repo,
        )

    def save_node_type(self, directory: str | Path, type_id: str) -> Path:
        """Persist one type-node by id and return its written path."""
        node = self.get(type_id)
        if node.category != "_type":
            raise ValueError(f"Node {type_id} is not a type node")
        root = Path(directory)
        self.save(root)
        return self._build_storage_paths(root)[str(node.id)]

    def save_instance(self, directory: str | Path, instance_id: str) -> Path:
        """Persist one instance-node by id and return its written path."""
        node = self.get(instance_id)
        if node.category == "_type":
            raise ValueError(f"Node {instance_id} is not an instance node")
        root = Path(directory)
        self.save(root)
        return self._build_storage_paths(root)[str(node.id)]

    def save_link_type(self, directory: str | Path, link_type_id: str) -> Path:
        """Persist one link type by id and return its written path."""
        if link_type_id not in self._link_types:
            raise KeyError(link_type_id)
        root = Path(directory)
        self.save(root)
        return self._build_link_type_storage_paths(root)[link_type_id]

    def save_link(self, directory: str | Path, link_id: str) -> Path:
        """Persist one link instance by id and return its written path."""
        if link_id not in self._links:
            raise KeyError(link_id)
        root = Path(directory)
        self.save(root)
        return self._build_link_storage_paths(root)[link_id]

    def delete_node_type_file(self, directory: str | Path, type_id: str) -> None:
        """Delete one type node from repository and persist resulting disk state."""
        node = self.get(type_id)
        if node.category != "_type":
            raise ValueError(f"Node {type_id} is not a type node")
        self.delete(type_id)
        self.save(directory)

    def delete_instance_file(self, directory: str | Path, instance_id: str) -> None:
        """Delete one instance node from repository and persist resulting disk state."""
        node = self.get(instance_id)
        if node.category == "_type":
            raise ValueError(f"Node {instance_id} is not an instance node")
        self.delete(instance_id)
        self.save(directory)

    def delete_link_type_file(self, directory: str | Path, link_type_id: str) -> None:
        """Delete one link-type entry from repository and persist resulting disk state."""
        self.delete_link_type(link_type_id)
        self.save(directory)

    def delete_link_file(self, directory: str | Path, link_id: str) -> None:
        """Delete one link entry from repository and persist resulting disk state."""
        self.delete_link(link_id)
        self.save(directory)

    def _build_storage_paths(self, root: Path) -> dict[str, Path]:
        used_relative_paths: set[str] = set()
        paths: dict[str, Path] = {}
        for node in self.list_nodes():
            relpath = self._unique_storage_relpath(node, used_relative_paths)
            paths[str(node.id)] = root / relpath
        return paths

    def _build_link_type_storage_paths(self, root: Path) -> dict[str, Path]:
        used_relative_paths: set[str] = set()
        paths: dict[str, Path] = {}
        for link_type in self.list_link_types():
            relpath = unique_link_type_relpath(link_type, used_relative_paths)
            paths[link_type.id] = root / relpath
        return paths

    def _build_link_storage_paths(self, root: Path) -> dict[str, Path]:
        nodes_by_id = self._nodes
        link_types_by_id = self._link_types
        paths: dict[str, Path] = {}
        for link in self.list_links():
            source_node = nodes_by_id.get(link.source_node_id)
            target_node = nodes_by_id.get(link.target_node_id)
            link_type = link_types_by_id.get(link.link_type_id)
            relpath = link_instance_relpath(
                link,
                source_node=source_node,
                target_node=target_node,
                link_type=link_type,
            )
            paths[link.id] = root / relpath
        return paths

    def _compute_link_path(self, link_id: str, root: Path) -> Path | None:
        """Compute storage path for one link without iterating all links.

        O(1) fast path for single-link writes. Returns None if link not found.
        """
        link = self._links.get(link_id)
        if link is None:
            return None
        source_node = self._nodes.get(link.source_node_id)
        target_node = self._nodes.get(link.target_node_id)
        link_type = self._link_types.get(link.link_type_id)
        relpath = link_instance_relpath(
            link,
            source_node=source_node,
            target_node=target_node,
            link_type=link_type,
        )
        return root / relpath

    def _unique_storage_relpath(self, node: Node, used_relative_paths: set[str]) -> Path:
        folder = self._storage_folder(node)
        base_name = safe_filename(node.name)
        candidate = folder / f"{base_name}.json"
        suffix = 2
        while candidate.as_posix() in used_relative_paths:
            candidate = folder / f"{base_name}_{suffix}.json"
            suffix += 1
        used_relative_paths.add(candidate.as_posix())
        return candidate

    def _storage_folder(self, node: Node) -> Path:
        links = list(self._links.values())
        nodes = self._nodes
        return storage_folder_for_node(node, links=links, nodes=nodes)

    def _build_index(self, *, root: Path, desired_paths: dict[str, Path]) -> dict[str, object]:
        nodes_index: dict[str, dict[str, str]] = {}
        for node in self.list_nodes():
            nodes_index[str(node.id)] = {
                "category": node.category,
                "name": node.name,
                "path": desired_paths[str(node.id)].relative_to(root).as_posix(),
            }
        return {
            "format_version": 2,
            "source_repo_id": self._source_repo_id,
            "nodes": nodes_index,
            "link_types": {lt.id: lt.name for lt in self.list_link_types()},
            "links": {lk.id: {"source": lk.source_node_id, "target": lk.target_node_id}
                      for lk in self.list_links()},
            "views": build_views_index(root=root),
        }

    @classmethod
    def load(
        cls,
        directory: str | Path,
        *,
        source_repo_id: str | None = None,
    ) -> Repository:
        """Load a repository from *directory*."""
        return load_repository(
            repository_cls=cls,
            directory=directory,
            source_repo_id=source_repo_id,
        )

    @classmethod
    def load_from_disk_scan(
        cls,
        directory: str | Path,
        *,
        source_repo_id: str | None = None,
    ) -> Repository:
        """Load a repository by scanning disk files directly, ignoring any index.json hints."""
        return load_repository(
            repository_cls=cls,
            directory=directory,
            source_repo_id=source_repo_id,
            use_index=False,
        )

    def _require_repo_root(self) -> Path:
        """Return the repository root configured via ``save`` or ``load``."""
        return require_repo_root(repository=self)

    def _sync_index(self) -> None:
        """Rebuild ``index.json`` from current repository and view state."""
        sync_index(repository=self)

    def _pretty_json(self, value: object) -> str:
        """Render deterministic pretty JSON for repository files."""
        return pretty_json(value)

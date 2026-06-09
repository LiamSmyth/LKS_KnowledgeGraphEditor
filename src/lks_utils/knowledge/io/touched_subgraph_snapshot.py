"""In-memory undo snapshot for structural blast-radius mutations."""
from __future__ import annotations

from dataclasses import dataclass, field

from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.repository import Repository


@dataclass
class TouchedSubgraphSnapshot:
    """Shallow copies of entities in a rollback scope before in-place mutate."""

    nodes: dict[str, Node] = field(default_factory=dict)
    links: dict[str, LinkInstance] = field(default_factory=dict)
    link_types: dict[str, LinkType] = field(default_factory=dict)

    @classmethod
    def capture(cls, repository: Repository, scope_ids: frozenset[str]) -> TouchedSubgraphSnapshot:
        """Capture pre-mutation state for ids in *scope_ids* and incident links."""
        if not scope_ids:
            return cls()

        nodes: dict[str, Node] = {}
        links: dict[str, LinkInstance] = {}
        link_types: dict[str, LinkType] = {}

        for entity_id in scope_ids:
            node = repository.find_node(entity_id)
            if node is not None:
                nodes[entity_id] = node.model_copy(deep=True)
            link = repository.find_link(entity_id)
            if link is not None:
                links[entity_id] = link.model_copy(deep=True)
            link_type = repository.find_link_type(entity_id)
            if link_type is not None:
                link_types[entity_id] = link_type.model_copy(deep=True)

        for entity_id in scope_ids:
            if repository.find_node(entity_id) is None:
                continue
            for link in repository.list_links():
                link_id = str(link.id)
                if link_id in links:
                    continue
                if link.source_node_id == entity_id or link.target_node_id == entity_id:
                    links[link_id] = link.model_copy(deep=True)

        return cls(nodes=nodes, links=links, link_types=link_types)

    def restore(self, repository: Repository) -> None:
        """Restore *repository* to the captured pre-mutation subgraph state."""
        scope_nodes = set(self.nodes)
        scope_links = set(self.links)

        for link_id in list(repository._links):  # noqa: SLF001
            link = repository._links[link_id]  # noqa: SLF001
            if link_id in scope_links:
                continue
            if (
                link.source_node_id in scope_nodes
                or link.target_node_id in scope_nodes
            ):
                repository.delete_link(link_id)

        for node_id in list(repository._nodes):  # noqa: SLF001
            if node_id in scope_nodes and node_id not in self.nodes:
                repository.delete(node_id)

        for link_type_id, link_type in self.link_types.items():
            repository.upsert_link_type(link_type)

        for node_id, node in self.nodes.items():
            repository.upsert(node)

        for link_id, link in self.links.items():
            repository.upsert_link(link)


class PreMutateRepositoryView:
    """Read-only repository view for pre-mutation state after in-place mutate."""

    def __init__(
        self,
        live: Repository,
        snapshot: TouchedSubgraphSnapshot,
        *,
        rollback_scope: frozenset[str] = frozenset(),
    ) -> None:
        self._live = live
        self._snapshot = snapshot
        self._rollback_scope = rollback_scope

    def to_repository(self) -> Repository:
        """Materialize a :class:`Repository` for disk path comparisons."""
        repo = Repository(source_repo_id=self._live.source_repo_id)
        repo._repo_root = self._live._repo_root  # noqa: SLF001
        repo._nodes = dict(self._live._nodes)  # noqa: SLF001
        repo._links = dict(self._live._links)  # noqa: SLF001
        repo._link_types = dict(self._live._link_types)  # noqa: SLF001
        repo._nodes.update(self._snapshot.nodes)
        repo._links.update(self._snapshot.links)
        repo._link_types.update(self._snapshot.link_types)
        for node_id in list(repo._nodes):
            if node_id in self._rollback_scope and node_id not in self._snapshot.nodes:
                repo._nodes.pop(node_id, None)
        for link_id in list(repo._links):
            if link_id in self._rollback_scope and link_id not in self._snapshot.links:
                repo._links.pop(link_id, None)
        repo._names = {node.name: node_id for node_id, node in repo._nodes.items()}  # noqa: SLF001
        repo._link_type_names = {  # noqa: SLF001
            link_type.name: link_type_id
            for link_type_id, link_type in repo._link_types.items()
        }
        return repo

    def find_node(self, node_id: str) -> Node | None:
        if node_id in self._snapshot.nodes:
            return self._snapshot.nodes[node_id]
        return self._live.find_node(node_id)

    def find_link(self, link_id: str) -> LinkInstance | None:
        if link_id in self._snapshot.links:
            return self._snapshot.links[link_id]
        return self._live.find_link(link_id)

    def find_link_type(self, link_type_id: str) -> LinkType | None:
        if link_type_id in self._snapshot.link_types:
            return self._snapshot.link_types[link_type_id]
        return self._live.find_link_type(link_type_id)

    def list_nodes(self) -> list[Node]:
        node_ids = set(self._live._nodes) | set(self._snapshot.nodes)  # noqa: SLF001
        nodes: list[Node] = []
        for node_id in node_ids:
            node = self.find_node(node_id)
            if node is not None:
                nodes.append(node)
        return nodes

    def list_instances(self) -> list[Node]:
        return [node for node in self.list_nodes() if node.category != "_type"]

    def list_types(self) -> list[Node]:
        return [node for node in self.list_nodes() if node.category == "_type"]

    def list_links(self) -> list[LinkInstance]:
        link_ids = set(self._live._links) | set(self._snapshot.links)  # noqa: SLF001
        links: list[LinkInstance] = []
        for link_id in link_ids:
            link = self.find_link(link_id)
            if link is not None:
                links.append(link)
        return links

    def list_link_types(self) -> list[LinkType]:
        lt_ids = set(self._live._link_types) | set(self._snapshot.link_types)  # noqa: SLF001
        link_types: list[LinkType] = []
        for lt_id in lt_ids:
            lt = self.find_link_type(lt_id)
            if lt is not None:
                link_types.append(lt)
        return link_types


def shallow_repository_copy(repository: Repository) -> Repository:
    """Shallow-copy repository maps for pre-mutate disk path comparison."""
    copy_repo = Repository(source_repo_id=repository.source_repo_id)
    copy_repo._repo_root = repository._repo_root  # noqa: SLF001
    copy_repo._nodes = dict(repository._nodes)  # noqa: SLF001
    copy_repo._links = dict(repository._links)  # noqa: SLF001
    copy_repo._link_types = dict(repository._link_types)  # noqa: SLF001
    copy_repo._names = dict(repository._names)  # noqa: SLF001
    copy_repo._link_type_names = dict(repository._link_type_names)  # noqa: SLF001
    return copy_repo


__all__ = [
    "PreMutateRepositoryView",
    "TouchedSubgraphSnapshot",
    "shallow_repository_copy",
]

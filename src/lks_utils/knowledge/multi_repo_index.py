"""Multi-repository index — replaces KnowledgeRepoWorkspace."""
from __future__ import annotations

from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.repository import Repository


class MultiRepoIndex:
    """Mounts multiple repositories under a single ULID-keyed lookup.

    Each node is tagged with its ``source_repo_id`` on load so the editor
    can display provenance labels (e.g., "Apple (repo_a)" vs "Apple (repo_b)").
    ULID identities guarantee no collision across repos.

    Usage::

        index = MultiRepoIndex()
        index.mount(repo_a, source_repo_id="project_a")
        index.mount(repo_b, source_repo_id="project_b")

        node = index.get("01ARZ3NDEKTSV4RRFFQ69G5FAV")
        for node in index.iter_all():
            print(node.source_repo_id, node.name)
    """

    def __init__(self) -> None:
        self._repos: dict[str, Repository] = {}  # source_repo_id -> repo
        self._index: dict[str, Node] = {}         # str(ULID) -> node (tagged)

    # ------------------------------------------------------------------
    # Mount / unmount
    # ------------------------------------------------------------------

    def mount(
        self,
        repo: Repository,
        *,
        source_repo_id: str | None = None,
    ) -> None:
        """Add *repo* to the index.

        Args:
            repo: The repository to mount.
            source_repo_id: Override the repo's own ``source_repo_id``.
                Defaults to ``repo.source_repo_id``.

        Raises:
            ValueError: If a repository with the same ``source_repo_id`` is
                already mounted.
        """
        repo_id = source_repo_id or repo.source_repo_id
        if repo_id in self._repos:
            raise ValueError(
                f"A repository with source_repo_id {repo_id!r} is already mounted. "
                "Unmount it first or provide a different source_repo_id."
            )
        self._repos[repo_id] = repo
        for node in repo.list_nodes():
            tagged = _tag_node(node, repo_id)
            self._index[str(tagged.id)] = tagged

    def unmount(self, source_repo_id: str) -> None:
        """Remove a previously mounted repository and its nodes from the index.

        Raises:
            KeyError: If no repository with *source_repo_id* is mounted.
        """
        if source_repo_id not in self._repos:
            raise KeyError(source_repo_id)
        repo = self._repos.pop(source_repo_id)
        for node in repo.list_nodes():
            self._index.pop(str(node.id), None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, node_id: str | NodeId) -> Node:
        """Return the node with the given ULID across all mounted repos.

        Raises:
            KeyError: If no node with that ULID is found.
        """
        return self._index[str(node_id)]

    def iter_all(self) -> list[Node]:
        """Return all nodes from all mounted repos, sorted by ULID."""
        return sorted(self._index.values(), key=lambda n: str(n.id))

    def iter_repo(self, source_repo_id: str) -> list[Node]:
        """Return all nodes from one specific mounted repo."""
        return [n for n in self.iter_all() if n.source_repo_id == source_repo_id]

    def mounted_repo_ids(self) -> list[str]:
        """Return the sorted list of mounted source_repo_id values."""
        return sorted(self._repos.keys())


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _tag_node(node: Node, source_repo_id: str) -> Node:
    """Return a copy of *node* with ``source_repo_id`` set."""
    if node.source_repo_id == source_repo_id:
        return node
    return node.model_copy(update={"source_repo_id": source_repo_id})

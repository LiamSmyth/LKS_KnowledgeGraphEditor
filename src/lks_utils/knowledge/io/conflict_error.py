"""ConflictError — optimistic-locking exception for KnowledgeIO mutations."""
from __future__ import annotations


class ConflictError(Exception):
    """Raised when an optimistic-lock revision check fails during a mutation.

    Attributes
    ----------
    node_id:
        The ID of the node whose revision was stale.
    current_rev:
        The revision currently stored in the repository snapshot.
    expected_rev:
        The revision the caller expected (as supplied to ``expected_revision_id``).
    """

    def __init__(
        self,
        node_id: str,
        current_rev: int,
        expected_rev: str,
    ) -> None:
        super().__init__(
            f"Conflict on node {node_id!r}: expected revision {expected_rev!r}, "
            f"found {current_rev}"
        )
        self.node_id = node_id
        self.current_rev = current_rev
        self.expected_rev = expected_rev


__all__ = ["ConflictError"]

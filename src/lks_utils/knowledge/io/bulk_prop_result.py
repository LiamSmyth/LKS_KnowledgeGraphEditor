"""BulkPropResult — aggregated result for bulk property mutations."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodePropMutationResult:
    """Result for one node in a bulk property mutation."""

    node_id: str
    status: str  # "ok" | "error" | "conflict"
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"node_id": self.node_id, "status": self.status, "error": self.error}


@dataclass(frozen=True)
class BulkPropResult:
    """Aggregated result for a ``bulk_set_prop`` call.

    One :class:`NodePropMutationResult` entry is recorded per input node_id.
    Failed nodes do **not** abort the batch — they are captured in ``results``
    with ``status="error"`` or ``status="conflict"``.
    """

    results: tuple[NodePropMutationResult, ...]

    @property
    def ok_count(self) -> int:
        """Return the number of nodes that were updated successfully."""
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def error_count(self) -> int:
        """Return the number of nodes that failed."""
        return sum(1 for r in self.results if r.status != "ok")

    def to_dict(self) -> dict[str, object]:
        return {
            "ok_count": self.ok_count,
            "error_count": self.error_count,
            "results": [r.to_dict() for r in self.results],
        }


__all__ = ["BulkPropResult", "NodePropMutationResult"]

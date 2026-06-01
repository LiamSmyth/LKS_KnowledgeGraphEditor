"""Graph-view edge proxy model."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphViewEdgeProxy:
    """Visual edge proxy that maps a local edge to a global link instance."""

    global_link_id: str
    source_local_id: str
    target_local_id: str

    def __post_init__(self) -> None:
        if not self.global_link_id.strip():
            raise ValueError(
                "GraphViewEdgeProxy.global_link_id must be non-empty")
        if not self.source_local_id.strip():
            raise ValueError(
                "GraphViewEdgeProxy.source_local_id must be non-empty")
        if not self.target_local_id.strip():
            raise ValueError(
                "GraphViewEdgeProxy.target_local_id must be non-empty")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping."""
        return {
            "global_link_id": self.global_link_id,
            "source_local_id": self.source_local_id,
            "target_local_id": self.target_local_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GraphViewEdgeProxy:
        """Build an edge proxy from a strict dictionary payload."""
        expected = {"global_link_id", "source_local_id", "target_local_id"}
        actual = set(data.keys())
        unknown = sorted(actual - expected)
        if unknown:
            raise ValueError(
                f"GraphViewEdgeProxy.from_dict received unknown keys: {unknown}"
            )
        missing = sorted(expected - actual)
        if missing:
            raise ValueError(
                f"GraphViewEdgeProxy.from_dict missing keys: {missing}"
            )
        return cls(
            global_link_id=str(data["global_link_id"]),
            source_local_id=str(data["source_local_id"]),
            target_local_id=str(data["target_local_id"]),
        )

"""Generic frame sample consumed by profiling widgets."""
from __future__ import annotations

from dataclasses import dataclass, field

from lks_utils.profiling.call_node import CallNode


@dataclass(frozen=True, slots=True)
class FrameSample:
    """One captured frame with a generic call-tree payload."""

    frame_index: int
    wall_ms: float
    call_tree: CallNode
    counters: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("FrameSample.frame_index must be >= 0")
        if float(self.wall_ms) < 0.0:
            raise ValueError("FrameSample.wall_ms must be >= 0")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict (call tree is recursive)."""
        return {
            "frame_index": self.frame_index,
            "wall_ms": self.wall_ms,
            "call_tree": self.call_tree.to_dict(),
            "counters": dict(self.counters),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "FrameSample":
        """Deserialize from a JSON-compatible dict."""
        return cls(
            frame_index=int(data["frame_index"]),  # type: ignore[arg-type]
            wall_ms=float(data["wall_ms"]),  # type: ignore[arg-type]
            call_tree=CallNode.from_dict(data["call_tree"]),  # type: ignore[arg-type]
            counters={str(k): float(v) for k, v in data.get("counters", {}).items()},  # type: ignore[union-attr]
            metadata=dict(data.get("metadata", {})),  # type: ignore[arg-type]
        )


__all__ = ["FrameSample"]

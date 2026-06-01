"""Graph-view node proxy model."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GraphViewNodeProxy:
    """Visual proxy of a global knowledge node inside one GraphView."""

    global_id: str
    x: float
    y: float
    cached_name: str = field(default="")

    def __post_init__(self) -> None:
        if not self.global_id.strip():
            raise ValueError("GraphViewNodeProxy.global_id must be non-empty")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping."""
        return {
            "global_id": self.global_id,
            "x": self.x,
            "y": self.y,
            "cached_name": self.cached_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GraphViewNodeProxy:
        """Build a node proxy from a strict dictionary payload."""
        required = {"global_id", "x", "y"}
        optional = {"cached_name"}
        actual = set(data.keys())
        unknown = sorted(actual - required - optional)
        if unknown:
            raise ValueError(
                f"GraphViewNodeProxy.from_dict received unknown keys: {unknown}"
            )
        missing = sorted(required - actual)
        if missing:
            raise ValueError(
                f"GraphViewNodeProxy.from_dict missing keys: {missing}"
            )
        return cls(
            global_id=str(data["global_id"]),
            x=float(data["x"]),
            y=float(data["y"]),
            cached_name=str(data.get("cached_name", "")),
        )

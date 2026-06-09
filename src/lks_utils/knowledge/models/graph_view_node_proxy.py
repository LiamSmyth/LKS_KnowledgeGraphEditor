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
    capabilities: dict[str, dict] | None = None

    def __post_init__(self) -> None:
        if not self.global_id.strip():
            raise ValueError("GraphViewNodeProxy.global_id must be non-empty")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping."""
        payload: dict[str, object] = {
            "global_id": self.global_id,
            "x": self.x,
            "y": self.y,
            "cached_name": self.cached_name,
        }
        if self.capabilities is not None:
            payload["capabilities"] = self.capabilities
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GraphViewNodeProxy:
        """Build a node proxy from a strict dictionary payload."""
        required = {"global_id", "x", "y"}
        optional = {"cached_name", "capabilities"}
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
        raw_capabilities = data.get("capabilities")
        capabilities: dict[str, dict] | None = None
        if raw_capabilities is not None:
            if not isinstance(raw_capabilities, dict):
                raise ValueError(
                    "GraphViewNodeProxy.from_dict expects 'capabilities' to be a dict"
                )
            capabilities = {}
            for cap_id, block in raw_capabilities.items():
                if not isinstance(block, dict):
                    raise ValueError(
                        "GraphViewNodeProxy.from_dict expects capability "
                        f"blocks to be dict values (key={cap_id!r})"
                    )
                capabilities[str(cap_id)] = dict(block)
        return cls(
            global_id=str(data["global_id"]),
            x=float(data["x"]),
            y=float(data["y"]),
            cached_name=str(data.get("cached_name", "")),
            capabilities=capabilities,
        )

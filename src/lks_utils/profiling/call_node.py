"""Generic call-tree node for profiling UIs and adapters."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from lks_utils.profiling.device import Device


Matcher = str | Callable[["CallNode"], bool]


@dataclass(frozen=True, slots=True)
class CallNode:
    """One node in a profiling call tree.

    ``total_ms`` may be omitted. In that case it is derived from ``self_ms``
    plus the totals of all children. When provided, it must be large enough to
    cover the full subtree.
    """

    name: str
    self_ms: float
    total_ms: float | None = None
    category: str = "core"
    device: Device = Device.UNKNOWN
    call_count: int = 1
    children: tuple[CallNode, ...] = ()
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        child_total_ms = sum(child.total_ms_value for child in self.children)
        implied_total_ms = max(0.0, float(self.self_ms)) + child_total_ms
        if float(self.self_ms) < 0.0:
            raise ValueError("CallNode.self_ms must be >= 0")
        if self.call_count < 1:
            raise ValueError("CallNode.call_count must be >= 1")
        if self.total_ms is None:
            object.__setattr__(self, "total_ms", implied_total_ms)
            return
        resolved_total_ms = float(self.total_ms)
        if resolved_total_ms < implied_total_ms - 1e-9:
            raise ValueError(
                "CallNode.total_ms must be >= self_ms + child totals"
            )
        object.__setattr__(self, "total_ms", resolved_total_ms)

    @property
    def total_ms_value(self) -> float:
        """Resolved inclusive duration for the full subtree."""
        assert self.total_ms is not None
        return float(self.total_ms)

    def iter_depth_first(self) -> tuple[CallNode, ...]:
        """Return nodes in pre-order depth-first traversal order."""
        ordered: list[CallNode] = [self]
        for child in self.children:
            ordered.extend(child.iter_depth_first())
        return tuple(ordered)

    def find(self, matcher: Matcher) -> CallNode | None:
        """Return the first breadth-first match, or ``None`` if absent."""
        predicate: Callable[[CallNode], bool]
        if isinstance(matcher, str):
            def predicate(node): return node.name == matcher
        else:
            predicate = matcher

        queue: deque[CallNode] = deque([self])
        while queue:
            node = queue.popleft()
            if predicate(node):
                return node
            queue.extend(node.children)
        return None

    def to_dict(self) -> dict[str, object]:
        """Recursively serialize this node to a JSON-compatible dict."""
        return {
            "name": self.name,
            "self_ms": self.self_ms,
            "total_ms": self.total_ms,
            "category": self.category,
            "device": self.device.value,
            "call_count": self.call_count,
            "children": [child.to_dict() for child in self.children],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CallNode":
        """Recursively deserialize from a JSON-compatible dict."""
        return cls(
            name=str(data["name"]),
            self_ms=float(data["self_ms"]),  # type: ignore[arg-type]
            total_ms=float(data["total_ms"]) if data.get("total_ms") is not None else None,  # type: ignore[arg-type]
            category=str(data.get("category", "core")),
            device=Device(str(data.get("device", Device.UNKNOWN.value))),
            call_count=int(data.get("call_count", 1)),  # type: ignore[arg-type]
            children=tuple(
                cls.from_dict(child)  # type: ignore[arg-type]
                for child in data.get("children", [])  # type: ignore[union-attr]
            ),
            metadata=dict(data.get("metadata", {})),  # type: ignore[arg-type]
        )


__all__ = ["CallNode"]

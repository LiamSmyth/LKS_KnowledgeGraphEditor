"""Counter history track for frame-oriented profiling views."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class CounterTrack:
    """Rolling history of one numeric profiling counter."""

    name: str
    max_samples: int = 240
    _values: deque[float] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.max_samples = max(1, int(self.max_samples))
        self._values = deque(maxlen=self.max_samples)

    def push(self, value: float) -> None:
        self._values.append(float(value))

    def reset(self) -> None:
        self._values.clear()

    def samples(self) -> tuple[float, ...]:
        return tuple(self._values)

    @property
    def latest(self) -> float | None:
        if not self._values:
            return None
        return float(self._values[-1])


__all__ = ["CounterTrack"]

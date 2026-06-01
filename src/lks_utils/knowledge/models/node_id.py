"""ULID-based identity value object for knowledge nodes."""
from __future__ import annotations

from ulid import ULID


class NodeId:
    """Immutable ULID identity for a knowledge node.

    Use ``NodeId.new()`` to mint fresh identities and
    ``NodeId.from_str(s)`` to parse persisted strings.
    """

    __slots__ = ("_ulid",)

    def __init__(self, value: ULID) -> None:
        self._ulid: ULID = value

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def new(cls) -> NodeId:
        """Mint a new, unique ULID-based identity."""
        return cls(ULID())

    @classmethod
    def from_str(cls, s: str) -> NodeId:
        """Parse a ULID string; raises ValueError on invalid input."""
        if not s or len(s) != 26:
            raise ValueError(f"Invalid ULID string (expected 26 chars): {s!r}")
        try:
            return cls(ULID.from_str(s))
        except Exception as exc:
            raise ValueError(f"Invalid ULID string {s!r}: {exc}") from exc

    # ------------------------------------------------------------------
    # Value-object protocol
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return str(self._ulid)

    def __repr__(self) -> str:
        return f"NodeId({str(self._ulid)!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, NodeId):
            return self._ulid == other._ulid
        return NotImplemented

    def __hash__(self) -> int:
        return hash(str(self._ulid))

    def __lt__(self, other: object) -> bool:
        """Time-sortable comparison (ULID encodes timestamp)."""
        if isinstance(other, NodeId):
            return str(self._ulid) < str(other._ulid)
        return NotImplemented

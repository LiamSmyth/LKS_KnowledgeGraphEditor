"""SlotValueEnvelope — structured response for KB property-reading tools."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class SlotValueEnvelope:
    """Structured response for a single slot/property value read.

    Attributes
    ----------
    slot_name:
        The name of the slot that was queried.
    field_type_id:
        The declared field type (e.g. ``"string"``, ``"ref"``, ``"int"``) or
        ``None`` when no schema contract exists.
    value:
        The resolved value, or ``None`` when ``scope`` is ``"absent"``.
    exists:
        ``True`` when a value was found for the slot (either own or inherited).
    scope:
        - ``"own"``:      value is set directly on this node's ``props``.
        - ``"inherited"``: value is present on the type node's ``props``.
        - ``"absent"``:   slot is defined in the type schema but no value is set.
    include_hydrated:
        When ``True``, ``value`` may include additional hydration data (e.g.
        resolved node names for reference values).  ``False`` by default.
    """

    slot_name: str
    field_type_id: str | None
    value: Any
    exists: bool
    scope: Literal["own", "inherited", "absent"]
    include_hydrated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation suitable for MCP tool responses."""
        return {
            "slot_name": self.slot_name,
            "field_type_id": self.field_type_id,
            "value": self.value,
            "exists": self.exists,
            "scope": self.scope,
        }


__all__ = ["SlotValueEnvelope"]

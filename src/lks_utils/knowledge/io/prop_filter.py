"""PropFilter — predicate dataclass for multi-property node queries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class PropFilter:
    """A single predicate for matching node properties.

    Attributes
    ----------
    prop_key:
        The property key to inspect on each node's ``props`` dict.
    op:
        The comparison operator.  One of:
        - ``"eq"``: exact equality.
        - ``"neq"``: inequality.
        - ``"contains"``: sub-string check (string props only).
        - ``"starts_with"``: prefix check (string props only).
    value:
        The value to compare against.
    """

    prop_key: str
    op: Literal["eq", "neq", "contains", "starts_with"]
    value: Any

    def matches(self, props: dict[str, Any]) -> bool:
        """Return ``True`` if *props* satisfies this predicate."""
        if self.prop_key not in props:
            # Absent key is only "not equal" to any value
            return self.op == "neq"
        v = props[self.prop_key]
        if self.op == "eq":
            return v == self.value
        if self.op == "neq":
            return v != self.value
        if self.op == "contains":
            return isinstance(v, str) and str(self.value) in v
        if self.op == "starts_with":
            return isinstance(v, str) and v.startswith(str(self.value))
        return False  # unknown op — treat as no-match (safe default)


__all__ = ["PropFilter"]

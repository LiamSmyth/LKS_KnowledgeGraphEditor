"""Filter predicate for profiling call nodes."""
from __future__ import annotations

from dataclasses import dataclass, field

from lks_utils.profiling.call_node import CallNode
from lks_utils.profiling.device import Device


@dataclass
class ProfileFilter:
    """Immutable predicate applied to a CallNode to decide visibility.

    All active criteria are ANDed.  An empty/default filter matches everything.
    """

    text: str = ""
    """Case-insensitive substring match against node name."""

    min_total_ms: float = 0.0
    """Exclude nodes whose total_ms is strictly below this threshold."""

    devices: frozenset[Device] = field(
        default_factory=lambda: frozenset(Device)
    )
    """Allowed device set.  Defaults to all devices."""

    categories: frozenset[str] = field(default_factory=frozenset)
    """If non-empty, only nodes whose category is in this set pass."""

    def is_empty(self) -> bool:
        """Return True when this filter would pass every node."""
        return (
            not self.text
            and self.min_total_ms <= 0.0
            and self.devices == frozenset(Device)
            and not self.categories
        )

    def matches(self, node: CallNode) -> bool:
        """Return True when *node* satisfies all active criteria."""
        if self.text and self.text.lower() not in node.name.lower():
            return False
        if self.min_total_ms > 0.0 and node.total_ms_value < self.min_total_ms:
            return False
        if node.device not in self.devices:
            return False
        if self.categories and node.category not in self.categories:
            return False
        return True

    def matches_subtree(self, node: CallNode) -> bool:
        """Return True when *node* or any descendant satisfies all criteria.

        Used to prune entire branches when building a filtered tree view.
        """
        if self.matches(node):
            return True
        return any(self.matches_subtree(child) for child in node.children)


__all__ = ["ProfileFilter"]

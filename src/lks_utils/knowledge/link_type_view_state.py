"""Link-type view state management for graph canvas filtering and rendering."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class LinkTypeFlags:
    """Per-link-type control flags for graph canvas visibility and interaction.

    Attributes:
        visible: If False, links of this type are hidden in canvas and not hit-tested.
        ghosted: If True, links rendered with reduced opacity (visual emphasis reduction).
        selectable: If False, links cannot be clicked/selected in canvas.
        filtered_out: If True, links AND endpoint-only-via-this-type nodes are hidden from frontier traversal.

    Precedence:
        filtered_out > visible=false > ghosted > selectable=false
    """

    visible: bool = True
    ghosted: bool = False
    selectable: bool = True
    filtered_out: bool = False

    def with_visible(self, value: bool) -> LinkTypeFlags:
        """Return a new LinkTypeFlags with visible flag set."""
        return replace(self, visible=value)

    def with_ghosted(self, value: bool) -> LinkTypeFlags:
        """Return a new LinkTypeFlags with ghosted flag set."""
        return replace(self, ghosted=value)

    def with_selectable(self, value: bool) -> LinkTypeFlags:
        """Return a new LinkTypeFlags with selectable flag set."""
        return replace(self, selectable=value)

    def with_filtered_out(self, value: bool) -> LinkTypeFlags:
        """Return a new LinkTypeFlags with filtered_out flag set."""
        return replace(self, filtered_out=value)


@dataclass(frozen=True)
class LinkTypeViewState:
    """Immutable container for per-link-type view state.

    This is the single source of truth for link-type graph control state.
    All state changes go through set_flag() which returns a new instance.
    """

    flags_by_type: dict[str, LinkTypeFlags] = field(default_factory=dict)

    def get_flags(self, type_id: str) -> LinkTypeFlags:
        """Get flags for a specific link type, defaulting to all True."""
        return self.flags_by_type.get(type_id, LinkTypeFlags())

    def set_flag(self, type_id: str, flag_name: str, value: bool) -> LinkTypeViewState:
        """Set a specific flag for a link type.

        Args:
            type_id: The link type identifier.
            flag_name: One of: 'visible', 'ghosted', 'selectable', 'filtered_out'.
            value: The new flag value.

        Returns:
            A new LinkTypeViewState with the flag updated.

        Raises:
            ValueError: If flag_name is not recognized.
        """
        current_flags = self.get_flags(type_id)

        if flag_name == "visible":
            new_flags = current_flags.with_visible(value)
        elif flag_name == "ghosted":
            new_flags = current_flags.with_ghosted(value)
        elif flag_name == "selectable":
            new_flags = current_flags.with_selectable(value)
        elif flag_name == "filtered_out":
            new_flags = current_flags.with_filtered_out(value)
        else:
            raise ValueError(f"Unknown flag name: {flag_name}")

        new_dict = dict(self.flags_by_type)
        new_dict[type_id] = new_flags
        return LinkTypeViewState(flags_by_type=new_dict)

    def set_flags(self, type_id: str, flags: LinkTypeFlags) -> LinkTypeViewState:
        """Set all flags for a link type at once.

        Args:
            type_id: The link type identifier.
            flags: The new LinkTypeFlags instance.

        Returns:
            A new LinkTypeViewState with flags replaced.
        """
        new_dict = dict(self.flags_by_type)
        new_dict[type_id] = flags
        return LinkTypeViewState(flags_by_type=new_dict)

    def set_all_flag(
        self, flag_name: str, value: bool, type_ids: list[str] | None = None
    ) -> LinkTypeViewState:
        """Set a flag for multiple link types (all/none/invert bulk operation).

        Args:
            flag_name: One of: 'visible', 'ghosted', 'selectable', 'filtered_out'.
            value: The new flag value.
            type_ids: Types to update. If None, updates all known types.

        Returns:
            A new LinkTypeViewState with flags updated.
        """
        target_types = type_ids or list(self.flags_by_type.keys())
        result = self
        for type_id in target_types:
            result = result.set_flag(type_id, flag_name, value)
        return result

    def invert_flag(
        self, flag_name: str, type_ids: list[str] | None = None
    ) -> LinkTypeViewState:
        """Invert a flag for multiple link types.

        Args:
            flag_name: One of: 'visible', 'ghosted', 'selectable', 'filtered_out'.
            type_ids: Types to update. If None, updates all known types.

        Returns:
            A new LinkTypeViewState with flags inverted.
        """
        target_types = type_ids or list(self.flags_by_type.keys())
        result = self
        for type_id in target_types:
            current = self.get_flags(type_id)
            current_value = getattr(current, flag_name)
            result = result.set_flag(type_id, flag_name, not current_value)
        return result

    def serialize(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            type_id: {
                "visible": flags.visible,
                "ghosted": flags.ghosted,
                "selectable": flags.selectable,
                "filtered_out": flags.filtered_out,
            }
            for type_id, flags in self.flags_by_type.items()
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> LinkTypeViewState:
        """Deserialize from JSON-compatible dict."""
        flags_by_type = {}
        for type_id, flag_dict in data.items():
            flags_by_type[type_id] = LinkTypeFlags(
                visible=flag_dict.get("visible", True),
                ghosted=flag_dict.get("ghosted", False),
                selectable=flag_dict.get("selectable", True),
                filtered_out=flag_dict.get("filtered_out", False),
            )
        return cls(flags_by_type=flags_by_type)

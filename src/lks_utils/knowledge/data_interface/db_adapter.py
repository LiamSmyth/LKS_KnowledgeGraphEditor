"""Collect open field values into a Repository.upsert-compatible payload."""
from __future__ import annotations

from lks_utils.knowledge.models.node import Node


class _FieldValueProvider:
    def value(self) -> object:
        raise NotImplementedError


class DBAdapter:
    """Collect field values and produce a JSON payload for node upserts."""

    def __init__(self) -> None:
        self._fields: dict[str, _FieldValueProvider] = {}

    def register_field(self, prop_name: str, field: _FieldValueProvider) -> None:
        """Register or replace a field provider for one property name."""
        self._fields[prop_name] = field

    def unregister_field(self, prop_name: str) -> None:
        """Remove a previously-registered field provider if present."""
        self._fields.pop(prop_name, None)

    def clear(self) -> None:
        """Remove all currently registered field providers."""
        self._fields.clear()

    def collect_props(self, *, base_props: dict[str, object] | None = None) -> dict[str, object]:
        """Merge registered field values onto a copy of *base_props*."""
        merged: dict[str, object] = dict(base_props or {})
        for prop_name, field in self._fields.items():
            merged[prop_name] = field.value()
        return merged

    def build_upsert_payload(self, node: Node) -> dict[str, object]:
        """Return a JSON-serializable payload suitable for Repository.upsert."""
        payload = node.model_dump()
        payload["props"] = self.collect_props(base_props=node.props)
        return payload


__all__ = ["DBAdapter"]

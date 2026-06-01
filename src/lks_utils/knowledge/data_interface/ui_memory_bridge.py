"""Bridge field value changes into in-memory knowledge node props."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lks_utils.knowledge.models.node import Node


class _SignalLike:
    """Small protocol-style wrapper for Qt-like signal objects."""

    def connect(self, callback: Callable[[object], None]) -> None:
        raise NotImplementedError

    def disconnect(self, callback: Callable[[object], None]) -> None:
        raise NotImplementedError


class _FieldLike:
    """Minimal field contract needed by the bridge."""

    value_changed: _SignalLike

    def value(self) -> object:
        raise NotImplementedError


@dataclass(frozen=True)
class _BindingKey:
    node_id: str
    prop_name: str


class UIMemoryBridge:
    """Route field change notifications into ``Node.props`` updates.

    The bridge updates one node property per bound field and triggers a dirty
    callback only when the incoming value actually changes.
    """

    def __init__(self, *, on_dirty: Callable[[], None] | None = None) -> None:
        self._on_dirty = on_dirty
        self._callbacks: dict[_BindingKey, Callable[[object], None]] = {}
        self._fields: dict[_BindingKey, _FieldLike] = {}

    def bind_field(self, *, node: Node, prop_name: str, field: _FieldLike) -> None:
        """Bind one field signal to one ``node.props`` slot."""
        key = _BindingKey(node_id=str(node.id), prop_name=prop_name)
        self.unbind_field(node=node, prop_name=prop_name)

        def _on_value_changed(_value: object) -> None:
            self._update_node_prop(
                node=node, prop_name=prop_name, value=field.value())

        field.value_changed.connect(_on_value_changed)
        self._callbacks[key] = _on_value_changed
        self._fields[key] = field

    def unbind_field(self, *, node: Node, prop_name: str) -> None:
        """Detach one previously-bound field if present."""
        key = _BindingKey(node_id=str(node.id), prop_name=prop_name)
        callback = self._callbacks.pop(key, None)
        field = self._fields.pop(key, None)
        if callback is None or field is None:
            return
        field.value_changed.disconnect(callback)

    def clear(self) -> None:
        """Detach all bound fields from this bridge."""
        keys = list(self._callbacks.keys())
        for key in keys:
            callback = self._callbacks.pop(key)
            field = self._fields.pop(key)
            field.value_changed.disconnect(callback)

    def _update_node_prop(self, *, node: Node, prop_name: str, value: object) -> None:
        current = node.props.get(prop_name)
        if current == value:
            return
        node.props[prop_name] = value
        if self._on_dirty is not None:
            self._on_dirty()


__all__ = ["UIMemoryBridge"]

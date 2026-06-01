"""Row-model builder used by decomposition-oriented knowledge editors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lks_utils.knowledge.models.node_slot import NodeSlot

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class FieldControl:
    """Declarative control descriptor for one rendered field row."""

    action_id: str
    label: str


@dataclass(frozen=True)
class FieldRowInheritance:
    """Inheritance metadata for one row.

    ``scope`` values:
    - ``local_instance``: value comes from node-local props.
    - ``instance_chain_default``: value inherited from prototype chain.
    - ``type_default``: value inherited from type defaults.
    - ``unknown``: scope could not be determined.
    """

    is_inherited: bool = False
    is_overridden: bool = False
    scope: str = "unknown"
    provenance: str | None = None


@dataclass(frozen=True)
class FieldRow:
    """Normalized row model used by knowledge decomposition widgets."""

    kind: str
    label: str
    slot_name: str
    value: object
    controls: list[FieldControl] = field(default_factory=list)
    nested_rows: list[FieldRow] = field(default_factory=list)
    inheritance: FieldRowInheritance = field(
        default_factory=FieldRowInheritance)


class FieldRowFactory:
    """Build UI-agnostic row models from slots and instance values."""

    def build_rows(
        self,
        slots: list[NodeSlot],
        values: dict[str, object],
        inheritance_by_slot: dict[str, FieldRowInheritance] | None = None,
    ) -> list[FieldRow]:
        """Build one row per slot using current value state."""
        inheritance = inheritance_by_slot or {}
        return [
            self.build_row(slot, values.get(slot.name),
                           inheritance.get(slot.name))
            for slot in slots
        ]

    def build_row(
        self,
        slot: NodeSlot,
        value: object,
        inheritance: FieldRowInheritance | None = None,
    ) -> FieldRow:
        """Build one normalized row for a slot and its current value."""
        # Import here to avoid circular dependencies
        from lks_utils.knowledge.property_types import (
            PROPERTY_TYPE_REGISTRY,
            SlotContext,
        )
        from lks_utils.knowledge.property_types import builtins as _  # noqa: F401

        row_inheritance = inheritance or FieldRowInheritance()

        # Try to resolve via PropertyTypeRegistry first (core types)
        value_type = (slot.value_type or "any").strip().lower()
        if PROPERTY_TYPE_REGISTRY.has(value_type):
            pt = PROPERTY_TYPE_REGISTRY.get(value_type)
            kind = self._kind_from_capabilities(pt.capabilities)

            # Create minimal SlotContext for property type dispatch
            class _NoOpRepo:
                def get_node(self, node_id: str):  # type: ignore
                    return None

                def get_link(self, link_id: str):  # type: ignore
                    return None

                def list_nodes_of_type(self, type_id: str):  # type: ignore
                    return []

            ctx = SlotContext(
                slot_name=slot.name,
                owner_type_id=None,
                sibling_slot=lambda _: None,
                repo_read=_NoOpRepo(),  # type: ignore
            )

            # Build row with kind derived from capabilities
            return FieldRow(
                kind=kind,
                label=slot.name,
                slot_name=slot.name,
                value=value,
                controls=self._build_controls_for_property_type(pt, value),
                nested_rows=[],
                inheritance=row_inheritance,
            )

        # Fall back to legacy logic for extended types not in registry
        if self._is_ref_slot(slot):
            return self._build_ref_row(slot, value, row_inheritance)
        if isinstance(value, dict):
            nested_rows = [
                FieldRow(
                    kind="nested",
                    label=key,
                    slot_name=key,
                    value=nested_value,
                    controls=[],
                    nested_rows=[],
                )
                for key, nested_value in value.items()
            ]
            return FieldRow(
                kind="composite",
                label=slot.name,
                slot_name=slot.name,
                value=value,
                controls=[FieldControl(
                    action_id="field.edit", label="Edit")],
                nested_rows=nested_rows,
                inheritance=row_inheritance,
            )
        return FieldRow(
            kind="literal",
            label=slot.name,
            slot_name=slot.name,
            value=value,
            controls=[FieldControl(
                action_id="field.edit", label="Edit")],
            nested_rows=[],
            inheritance=row_inheritance,
        )

    def _kind_from_capabilities(self, capabilities: object) -> str:
        """Derive FieldRow.kind from PropertyCapabilities."""
        # Import here to avoid circular dependencies
        from lks_utils.knowledge.property_types import PropertyCapabilities

        if not isinstance(capabilities, PropertyCapabilities):
            return "scalar"

        if capabilities.is_reference and capabilities.is_list:
            return "reference_list"
        if capabilities.is_reference:
            return "reference"
        return "scalar"

    def _build_controls_for_property_type(
        self, property_type: object, value: object
    ) -> list[FieldControl]:
        """Build controls appropriate for this PropertyType and value."""
        from lks_utils.knowledge.property_types import PropertyType

        if not isinstance(property_type, PropertyType):
            return [FieldControl(action_id="field.edit", label="Edit")]

        caps = property_type.capabilities
        controls: list[FieldControl] = []

        # Reference types have picker and clear controls
        if caps.is_reference:
            controls.append(FieldControl(
                action_id="knowledge.field.pick_ref", label="[...]"))
            if self._is_ref_value(value):
                controls.append(FieldControl(
                    action_id="knowledge.field.clear_ref", label="[x]"))
        else:
            # Non-reference types get standard edit control
            controls.append(FieldControl(
                action_id="field.edit", label="Edit"))

        return controls

    def _is_ref_slot(self, slot: NodeSlot) -> bool:
        return slot.source.is_reference or slot.effective_entry_mode() in {"ref_only", "ref_or_inline"}

    def _build_ref_row(
        self,
        slot: NodeSlot,
        value: object,
        inheritance: FieldRowInheritance,
    ) -> FieldRow:
        if self._is_ref_value(value):
            return FieldRow(
                kind="ref_set",
                label=slot.name,
                slot_name=slot.name,
                value=value,
                controls=[
                    FieldControl(
                        action_id="knowledge.field.pick_ref", label="[...]"),
                    FieldControl(
                        action_id="knowledge.field.clear_ref", label="[x]"),
                ],
                nested_rows=[],
                inheritance=inheritance,
            )
        return FieldRow(
            kind="ref_empty",
            label=slot.name,
            slot_name=slot.name,
            value=value,
            controls=[FieldControl(
                action_id="knowledge.field.pick_ref", label="[...]")],
            nested_rows=[],
            inheritance=inheritance,
        )

    @staticmethod
    def _is_ref_value(value: object) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return all(isinstance(item, str) and item.strip() for item in value)
        return False


__all__ = [
    "FieldControl",
    "FieldRowInheritance",
    "FieldRow",
    "FieldRowFactory",
]

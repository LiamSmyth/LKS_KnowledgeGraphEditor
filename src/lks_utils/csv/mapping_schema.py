"""Generic mapping schema for CSV workflows.

Defines reusable schema for mapping arbitrary CSV formats to structured output data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


class FieldType(str, Enum):
    """Field data type."""

    TEXT = "text"
    NUMBER = "number"
    DECIMAL = "decimal"
    DATE = "date"
    ENUM = "enum"
    BOOLEAN = "boolean"


@dataclass
class FieldDefinition:
    """Definition for a single field in a transaction schema.

    Attributes:
        name: Field identifier (e.g., "Date", "Type", "Amount")
        label: Human-readable label for UI display
        field_type: Data type (text, number, enum, etc.)
        enum_values: Valid values if field_type is ENUM
        required: Whether field must have a value
        default_value: Default value if not provided
        description: Help text for field purpose
        use_value_map: Hint that this field should present a value map editor
            (for mapping many input values to valid output values).
            If False and enum_values is set, a constant/dropdown editor is used instead.
    """

    name: str
    label: str
    field_type: FieldType = FieldType.TEXT
    enum_values: List[str] = field(default_factory=list)
    required: bool = False
    default_value: str = ""
    description: str = ""
    use_value_map: bool = False

    def validate(self, value: str) -> tuple[bool, str]:
        """Validate a value against this field definition.

        Args:
            value: Value to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Required check
        if self.required and not value:
            return False, f"{self.label} is required"

        # Enum check
        if self.field_type == FieldType.ENUM and value:
            if value not in self.enum_values:
                return False, f"{self.label} must be one of: {', '.join(self.enum_values)}"

        # Number checks
        if self.field_type in (FieldType.NUMBER, FieldType.DECIMAL) and value:
            try:
                float(value)
            except ValueError:
                return False, f"{self.label} must be a number"

        return True, ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "label": self.label,
            "field_type": self.field_type.value,
            "enum_values": self.enum_values,
            "required": self.required,
            "default_value": self.default_value,
            "description": self.description,
            "use_value_map": self.use_value_map,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FieldDefinition:
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            label=data.get("label", data["name"]),
            field_type=FieldType(data.get("field_type", "text")),
            enum_values=data.get("enum_values", []),
            required=data.get("required", False),
            default_value=data.get("default_value", ""),
            description=data.get("description", ""),
            use_value_map=data.get("use_value_map", False),
        )


@dataclass
class MappingSchema:
    """Schema defining structure of output records.

    A mapping schema defines:
    - Field names, types, and validation rules
    - Enum values for dropdown fields
    - Required vs optional fields
    - Default values
    - Field descriptions

    Used for any CSV-to-structured-data workflow.
    """

    schema_id: str
    schema_name: str
    schema_version: str = "1.0"
    description: str = ""
    fields: List[FieldDefinition] = field(default_factory=list)

    def get_field(self, name: str) -> Optional[FieldDefinition]:
        """Get field definition by name.

        Args:
            name: Field name

        Returns:
            Field definition or None if not found
        """
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def get_enum_values(self, field_name: str) -> List[str]:
        """Get enum values for a field.

        Args:
            field_name: Field name

        Returns:
            List of enum values, or empty list if not an enum field
        """
        field_def = self.get_field(field_name)
        if field_def and field_def.field_type == FieldType.ENUM:
            return field_def.enum_values
        return []

    def validate_record(self, record: Dict[str, str]) -> tuple[bool, List[str]]:
        """Validate a record against this schema.

        Args:
            record: Dictionary of field_name -> value

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors = []

        for field_def in self.fields:
            value = record.get(field_def.name, "")
            is_valid, error_msg = field_def.validate(value)
            if not is_valid:
                errors.append(error_msg)

        return len(errors) == 0, errors

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "schema_id": self.schema_id,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "description": self.description,
            "fields": [f.to_dict() for f in self.fields],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MappingSchema:
        """Deserialize from dictionary."""
        return cls(
            schema_id=data["schema_id"],
            schema_name=data["schema_name"],
            schema_version=data.get("schema_version", "1.0"),
            description=data.get("description", ""),
            fields=[FieldDefinition.from_dict(f)
                    for f in data.get("fields", [])],
        )

    @classmethod
    def from_json_file(cls, path: Path) -> MappingSchema:
        """Load schema from JSON file.

        Args:
            path: Path to JSON schema file

        Returns:
            Loaded mapping schema
        """
        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return cls.from_dict(data)

    def to_json_file(self, path: Path) -> None:
        """Save schema to JSON file.

        Args:
            path: Path to save JSON schema
        """
        import json

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

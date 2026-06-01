"""Property definitions for type-nodes."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SlotSource(str, Enum):
    """How a NodeSlot's value is provided.

    ``LITERAL``   — value is authored inline (text, number, bool, etc.).
    ``REF``       — value is a reference to one other Node.
    ``REF_LIST``  — value is a list of references to other Nodes.
    ``FILE_REF``  — reference constrained to a file-system resource.
    ``IMAGE_REF`` — reference constrained to an image resource.
    ``VIDEO_REF`` — reference constrained to a video resource.
    """

    LITERAL = "literal"
    REF = "ref"
    REF_LIST = "ref_list"
    FILE_REF = "file_ref"
    IMAGE_REF = "image_ref"
    VIDEO_REF = "video_ref"

    @property
    def is_reference(self) -> bool:
        """Return True when this source requires pointing to another node."""
        return self in (
            SlotSource.REF,
            SlotSource.REF_LIST,
            SlotSource.FILE_REF,
            SlotSource.IMAGE_REF,
            SlotSource.VIDEO_REF,
        )


class PropertyValueMode(str, Enum):
    """How an instance may provide a property value."""

    LITERAL_ONLY = "literal_only"
    REF_ONLY = "ref_only"
    REF_OR_LITERAL = "ref_or_literal"
    INLINE_ONLY = "inline_only"
    REF_OR_INLINE = "ref_or_inline"
    REF_LIST = "ref_list"

    @property
    def allows_reference(self) -> bool:
        """Return True when this mode allows reference-valued slots."""
        return self in (
            PropertyValueMode.REF_ONLY,
            PropertyValueMode.REF_OR_LITERAL,
            PropertyValueMode.REF_OR_INLINE,
            PropertyValueMode.REF_LIST,
        )

    @property
    def allows_list(self) -> bool:
        """Return True when this mode stores a list of values."""
        return self == PropertyValueMode.REF_LIST


class PropertyCardinality(str, Enum):
    """Common cardinality policies for property values."""

    SINGLE = "single"
    OPTIONAL = "optional"
    LIST = "list"
    EXACT = "exact"
    RANGE = "range"


class NodeSlot(BaseModel):
    """One Property definition in a type-node's ``props["slots"]`` list.

    ``NodeSlot`` is kept as the compatibility class name for existing callers.
    New code should treat it as a Property definition: a local contract owned by
    a Type, with a unique name, value policy, defaults, constraints, and editor
    hints.

    Attributes:
        name:        Identifier for the slot within the type.
        source:      Compatibility storage source (``SlotSource`` enum).
        required:    Whether a value must be present for the instance to be valid.
        ref_type:    For reference sources: type token used to resolve allowed
                 target type ids (with inheritance). ``None`` means any node
                 is accepted.
        default:     Default value used when creating a new instance.
                     For literal sources: a value string (``""``, ``"0"``…).
                     For reference sources: ``None`` (user must pick).
        entry_mode:  Compatibility override for how the UI presents the slot.
        description: Optional human-readable note on this slot's purpose.
        value_type:  Literal primitive, target Type/category, or ``"any"``.
        value_mode:  Explicit policy for literal/reference/inline values.
        target_type: Conventional alias for ``ref_type`` (same type-token semantics).
        cardinality: Single/list/exact/range policy.
        min_count:   Minimum item count for list/range policies.
        max_count:   Maximum item count for list/range policies.
        version:     Monotonic property-contract version for schema drift detection.
        constraints: JSON-friendly validation constraints.
        editor_hint: UI hint such as multiline, color, vector, or ref picker.
    """

    name: str = Field(min_length=1)
    source: SlotSource
    required: bool = True
    ref_type: str | None = None
    default: object = None
    entry_mode: str | None = None
    description: str | None = None
    value_type: str = "any"
    ref_required: bool = False
    value_mode: PropertyValueMode | None = None
    target_type: str | None = None
    cardinality: PropertyCardinality = PropertyCardinality.SINGLE
    min_count: int | None = None
    max_count: int | None = None
    version: int = 1
    constraints: dict[str, object] = Field(default_factory=dict)
    editor_hint: str | None = None

    model_config = {
        "extra": "forbid",
    }

    def model_post_init(self, __context: object) -> None:
        """Normalize conventional aliases without rewriting slot semantics."""
        if self.version < 1:
            self.version = 1
        if self.target_type is None and self.ref_type is not None:
            self.target_type = self.ref_type
        if self.ref_type is None and self.target_type is not None:
            self.ref_type = self.target_type
        if self.target_type is None and self.value_type not in ("", "any"):
            self.target_type = self.value_type
        if self.ref_type is None and self.target_type is not None:
            self.ref_type = self.target_type
        if self.value_type == "any" and self.target_type is not None:
            self.value_type = self.target_type

    def effective_value_mode(self) -> PropertyValueMode:
        """Return the current value policy for this slot."""
        if self.value_mode is not None:
            return self.value_mode
        if self.source == SlotSource.REF_LIST:
            return PropertyValueMode.REF_LIST
        if self.source.is_reference:
            return PropertyValueMode.REF_ONLY
        return PropertyValueMode.LITERAL_ONLY

    def effective_entry_mode(self) -> str:
        """Return the effective entry mode with source-aware defaults."""
        return self.effective_value_mode().value

    def default_value(self) -> object:
        """Return the default value for new instances.

        When no explicit default is stored, returns the type-appropriate zero
        value via :func:`type_default_value`.
        """
        if self.default is not None:
            return self.default
        if self.effective_value_mode().allows_reference:
            # Reference slots have no meaningful literal default — callers must
            # let the user pick the target node.
            return None
        return type_default_value(self.value_type)


PropertyDefinition = NodeSlot


__all__ = [
    "NodeSlot",
    "PropertyCardinality",
    "PropertyDefinition",
    "PropertyValueMode",
    "SlotSource",
]


_T = "type_default_value"
__all__ = [*__all__, _T]
del _T


def type_default_value(value_type: str) -> object:
    """Return the canonical default for a given type string.

    Uses PropertyTypeRegistry for core types (string, int, float, bool, ref, ref_list).
    Falls back to legacy hard-coded defaults for extended types (color, vector*, etc.).

    - ``string`` / ``str`` / ``json`` / ``bytes`` → ``""``
    - ``int`` / ``integer``                       → ``0``
    - ``float`` / ``number``                      → ``0.0``
    - ``bool`` / ``boolean``                      → ``False``
    - ``ref``                                     → ``None``
    - ``ref_list``                                → ``[]``
    - ``color``                                   → ``"#ffffff"``
    - ``vector2``                                 → ``[0, 0]``
    - ``vector3``                                 → ``[0, 0, 0]``
    - ``vector4``                                 → ``[0, 0, 0, 0]``
    - ``list`` / ``tuple`` / ``set``              → ``[]``
    - ``dict``                                    → ``{}``
    - any / object / complex / NoneType / unknown → ``None``
    """
    # Lazy import to avoid circular dependency at module load time
    # Importing builtins triggers auto-registration of all 6 core PropertyTypes
    from lks_utils.knowledge.property_types import PROPERTY_TYPE_REGISTRY, SlotContext
    from lks_utils.knowledge.property_types import builtins as _  # noqa: F401

    key = (value_type or "any").strip().lower()

    # Try to resolve via PropertyTypeRegistry first (covers core types)
    if PROPERTY_TYPE_REGISTRY.has(key):
        # Create a minimal SlotContext to pass to PropertyType.default_value()
        # Using a no-op RepositoryReadProtocol stub since default_value doesn't use it
        # for the core types
        class _NoOpRepo:
            def get_node(self, node_id: str):  # type: ignore
                return None

            def get_link(self, link_id: str):  # type: ignore
                return None

            def list_nodes_of_type(self, type_id: str):  # type: ignore
                return []

        ctx = SlotContext(
            slot_name="",
            owner_type_id=None,
            sibling_slot=lambda _: None,
            repo_read=_NoOpRepo(),  # type: ignore
        )
        return PROPERTY_TYPE_REGISTRY.get(key).default_value(ctx)

    # Extended types (not in PropertyTypeRegistry) - compatibility fallback.
    scalar_fallbacks: dict[str, object] = {
        "string": "",
        "str": "",
        "json": "",
        "bytes": "",
        "int": 0,
        "integer": 0,
        "float": 0.0,
        "number": 0.0,
        "bool": False,
        "boolean": False,
        "color": "#ffffff",
        "vector2": [0, 0],
        "vector3": [0, 0, 0],
        "vector4": [0, 0, 0, 0],
        "dict": {},
    }
    if key in scalar_fallbacks:
        value = scalar_fallbacks[key]
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            return dict(value)
        return value

    list_fallback_types: set[str] = {"list", "tuple", "set"}
    if key in list_fallback_types:
        return []
    return None

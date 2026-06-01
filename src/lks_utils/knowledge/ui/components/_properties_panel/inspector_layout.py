"""Inspector panel: editing and ref navigation for a selected node."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.widgets import QCollapsibleSection, QElidedLabel, QLabeledRowBase
from lks_utils.knowledge.default_theme import (
    FIELD_BUTTON_BG,
    FIELD_BUTTON_BORDER,
    FIELD_CHECKBOX_TEXT,
    IMMUTABLE_FIELD_TEXT,
    FIELD_MONO_FONT_FAMILY,
    FIELD_INPUT_TEXT,
    FIELD_LABEL_COLOR,
    FIELD_ROW_BORDER,
    REF_MALFORMED_COLOR,
    REF_MISMATCH_COLOR,
    REF_MISSING_COLOR,
    REF_SUBPANEL_BG,
    REF_SUBPANEL_BORDER,
    REF_VALID_COLOR,
    SCENE_BACKGROUND_COLOR,
    SECTION_LABEL_COLOR,
    VALIDATION_ERROR_TEXT,
    VALIDATION_WARNING_LABEL,
)
from lks_utils.input import get_default_bindings
from lks_utils.knowledge.actions import FIELD_CLEAR_REF, FIELD_PICK_REF
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.instance_validator import (
    PROPERTY_VERSIONS_PROP,
    RESERVED_VALIDATION_PROP_NAMES,
    TYPE_VERSION_PROP,
    VALIDATION_ERRORS_PROP,
    VALIDATION_STATUS_CANNOT_COMPILE,
    VALIDATION_STATUS_PROP,
    InstanceValidator,
)
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.mutator import Mutator
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.models.node_slot import (
    NodeSlot,
    PropertyCardinality,
    PropertyValueMode,
    SlotSource,
)
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.operations.promote_inline_literal import promote_inline_literal
from lks_utils.knowledge.system.system_reserved import (
    can_write_meta_field,
    validate_instance_category_value,
    validate_node_category_transition,
)
from lks_utils.knowledge.ui.widgets.field_widgets import (
    ClearFieldButton,
    FIELD_ROW_HEIGHT,
    TypeComboBox,
    field_value,
    make_field_label,
    make_primitive_field,
    make_simple_button,
    make_square_svg_icon,
    make_square_svg_button,
    simple_mono_font,
    style_simple_field,
)
from lks_utils.knowledge.ui.widgets.field_widgets import (
    SwappableDefaultField,
    type_default_value,
)
from lks_utils.gui_qt.components.fields import QColorField, QFieldBase, QFieldOverrideWrapper
from lks_utils.knowledge.display_color import (
    effective_node_display_color,
    normalize_display_color,
)
from lks_utils.knowledge.ui.components.ref_picker_dialog import QKnowledgeRefPickerDialog
from lks_utils.knowledge.ui.components.type_picker_dialog import QKnowledgeTypePickerDialog
from lks_utils.profiling import profile_action
from lks_utils.theme.color import Color

_KEY_WIDTH = 92
_FIELD_LABEL_WIDTH = 116
_CONTRACT_LABEL_WIDTH = 60
_BTN_H = 24
_SECTION_FRAME_LEFT_INDENT = 8
_META_TOOLTIPS: dict[str, str] = {
    "id": "Stable persisted identity for this node. References use this ID, not the display name.",
    "name": "Human-readable display label and preferred filename slug. This is not the canonical identity.",
    "category": "Instance category for this node. For Type nodes this is a reserved system marker and is read-only.",
    "description": "Human-readable documentation for this node.",
    "type_id": "Stable ID of the Type that defines this Instance's property contract.",
    "instance_category": "Category assigned to Instances created from this Type.",
}

_PROPERTY_CONTRACT_TOOLTIPS: dict[str, str] = {
    "title": "This section edits one Property contract owned by the current Type. Instances created from this Type use these rules for the matching value.",
    "name": "Unique property name inside this Type. Instances store their value under this key, so renaming it changes the contract key.",
    "type": "Expected value type for this property, such as string, number, vector4, any, or a Type/category name.",
    "ref_required": "When enabled, this property must resolve to a linked reference target (target_node_id).",
    "required": "When enabled, an Instance is invalid until this property has a non-empty value that satisfies the contract.",
    "default": "Value copied into new Instances created from this Type. Empty means no default.",
    "description": "Human-readable documentation for this property. This should explain what the property means and help tools/LLMs understand it.",
    "version": "Property contract version. Instances can use this to detect drift after the Type contract changes.",
    "save": "Save this Property contract back to the Type.",
}
_PROPERTY_CONTRACT_TOOLTIP_ALIASES: dict[str, str] = {
    "value": "type",
    "type": "type",
    "ref": "ref_required",
    "docs": "description",
}


def _mk_btn(label: str, tooltip: str = "", parent: QWidget | None = None) -> QPushButton:
    return make_simple_button(label, tooltip, parent)


def _mk_icon_btn(svg_name: str, tooltip: str, parent: QWidget | None = None) -> QPushButton:
    btn = make_square_svg_button(
        svg_name, tooltip=tooltip, parent=parent, size=27)
    return btn


def _mk_sep(text: str, parent: QWidget | None = None) -> QLabel:
    sep = QLabel(f"â”€â”€ {text} â”€â”€", parent)
    sep.setStyleSheet(
        f"color: {SECTION_LABEL_COLOR}; font-size: 10px; padding: 2px 0;")
    return sep


def _mk_section(title: str, parent: QWidget | None = None, *, expanded: bool = True) -> tuple[QCollapsibleSection, QVBoxLayout]:
    """Create a collapsible section with a subtle bordered content frame."""
    section = QCollapsibleSection(
        title=title, parent=parent, initially_expanded=expanded)
    section.setObjectName(
        f"inspector_section_{_normalize_section_state_key(title)}")
    section.content_layout.setContentsMargins(0, 2, 0, 2)
    section.content_layout.setSpacing(0)

    # Keep a hidden text marker so existing label-based UI tests can still
    # discover section titles now rendered by the custom collapsible header.
    title_marker = QLabel(title, section.content)
    title_marker.setVisible(False)
    section.content_layout.addWidget(title_marker)

    frame = QFrame(section.content)
    frame.setObjectName("inspector_section_frame")
    frame_layout = QVBoxLayout(frame)
    frame_layout.setContentsMargins(_SECTION_FRAME_LEFT_INDENT, 3, 2, 3)
    frame_layout.setSpacing(0)
    frame.setStyleSheet(
        f"QFrame#inspector_section_frame {{ border: 1px solid {FIELD_ROW_BORDER};"
        f" background: {FIELD_BUTTON_BG}; border-radius: 0; }}"
    )
    section.content_layout.addWidget(frame)
    return section, frame_layout


def _normalize_section_state_key(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def _collapsible_section_state_key(section: QCollapsibleSection) -> str | None:
    object_name = section.objectName().strip()
    if object_name:
        return object_name
    return None


def _mk_field_label(text: str, parent: QWidget | None = None) -> QLabel:
    label = make_field_label(text, parent, width=_FIELD_LABEL_WIDTH)
    tooltip = _META_TOOLTIPS.get(text)
    if tooltip is not None:
        label.setToolTip(tooltip)
    return label


# ---------------------------------------------------------------------------
# Read-only row
# ---------------------------------------------------------------------------

class _ReadonlyRow(QLabeledRowBase):
    def __init__(self, key: str, value: str, parent: QWidget | None = None, tooltip: str = "") -> None:
        val_lbl = QElidedLabel(value, None)
        val_lbl.setStyleSheet(
            f"font-size: 11px; color: {IMMUTABLE_FIELD_TEXT};")
        val_lbl.setFixedHeight(FIELD_ROW_HEIGHT)
        val_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        val_lbl.setSizePolicy(QSizePolicy.Policy.Expanding,
                              QSizePolicy.Policy.Preferred)
        if tooltip:
            val_lbl.setToolTip(tooltip)
        super().__init__(key, val_lbl, fixed_height=FIELD_ROW_HEIGHT, parent=parent)
        # Apply _mk_field_label styling to auto-created label_widget()
        lbl = self.label_widget()
        lbl.setText(key + ":")
        lbl.setFixedWidth(_FIELD_LABEL_WIDTH)
        lbl.setFixedHeight(FIELD_ROW_HEIGHT)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter)
        lbl.setStyleSheet(
            f"QLabel {{ color: {FIELD_LABEL_COLOR}; font-size: 10px; }}")
        lbl.setFont(simple_mono_font())
        meta_tooltip = _META_TOOLTIPS.get(key)
        if meta_tooltip:
            lbl.setToolTip(meta_tooltip)
        if tooltip:
            lbl.setToolTip(tooltip)


class _ValidationRecoveryRow(QWidget):
    """Validation row with an explicit discard action for invalid/stale values."""

    discard_requested = Signal(str)
    pick_ref_requested = Signal(str)
    convert_inline_requested = Signal(str)

    def __init__(
        self,
        key: str,
        message: str,
        *,
        supports_reference: bool = False,
        supports_inline: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"validation_row_{key}")
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 1, 2, 1)
        root.setSpacing(3)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)

        key_lbl = QLabel(key + ":", self)
        key_lbl.setFixedWidth(_KEY_WIDTH)
        key_lbl.setStyleSheet(
            f"color: {VALIDATION_WARNING_LABEL}; font-size: 11px;")

        val_lbl = QLabel(message, self)
        val_lbl.setStyleSheet(
            f"font-size: 11px; color: {VALIDATION_ERROR_TEXT};")
        val_lbl.setWordWrap(True)
        val_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        val_lbl.setSizePolicy(QSizePolicy.Policy.Expanding,
                              QSizePolicy.Policy.Preferred)

        actions = QHBoxLayout()
        actions.setContentsMargins(_KEY_WIDTH + 4, 0, 0, 0)
        actions.setSpacing(4)

        discard_btn = _mk_btn(
            "Discard", "Drop invalid value for this property", self)
        discard_btn.setObjectName(f"validation_discard_{key}")
        discard_btn.setMaximumWidth(80)
        discard_btn.clicked.connect(lambda: self.discard_requested.emit(key))

        pick_btn = _mk_btn("Pick Ref", "Pick a replacement reference", self)
        pick_btn.setObjectName(f"validation_pick_{key}")
        pick_btn.setMaximumWidth(80)
        pick_btn.setVisible(supports_reference)
        pick_btn.clicked.connect(lambda: self.pick_ref_requested.emit(key))

        inline_btn = _mk_icon_btn(
            "kwb_btn_construct_inline.svg",
            "Convert value to inline object",
            self,
        )
        inline_btn.setObjectName(f"validation_inline_{key}")
        inline_btn.setVisible(supports_inline)
        inline_btn.clicked.connect(
            lambda: self.convert_inline_requested.emit(key))

        body.addWidget(key_lbl)
        body.addWidget(val_lbl, stretch=1)
        actions.addWidget(pick_btn)
        actions.addWidget(inline_btn)
        actions.addWidget(discard_btn)
        actions.addStretch(1)
        root.addLayout(body)
        root.addLayout(actions)


class _TypePropertyContractRow(QWidget):
    """Editable row for a single Type-owned property contract."""

    save_requested = Signal(str, object)

    def __init__(self, slot: NodeSlot, type_names: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._original_name = slot.name
        self.setObjectName(f"type_slot_row_{slot.name}")

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 3, 2, 3)
        root.setSpacing(0)

        self._section = QCollapsibleSection(
            title=f"Property: {slot.name}",
            parent=self,
            initially_expanded=True,
        )
        self._section.setObjectName(f"type_slot_section_{slot.name}")
        self._section.setToolTip(_PROPERTY_CONTRACT_TOOLTIPS["title"])
        self._section.content_layout.setContentsMargins(6, 5, 6, 5)
        self._section.content_layout.setSpacing(0)

        self._body = QWidget(self._section.content)
        self._body.setStyleSheet("QWidget { border: 0; }")
        table = QGridLayout(self._body)
        table.setContentsMargins(6, 5, 6, 5)
        table.setHorizontalSpacing(2)
        table.setVerticalSpacing(4)
        table.setColumnStretch(1, 1)

        self._name = QLineEdit(slot.name, self)
        self._name.setObjectName(f"type_slot_name_{slot.name}")
        self._name.setPlaceholderText("name")
        self._name.setToolTip(_PROPERTY_CONTRACT_TOOLTIPS["name"])
        self._value_type = TypeComboBox(
            type_names, slot.value_type, self)
        self._type_names = {name.strip()
                            for name in type_names if name.strip()}
        self._type_name_tokens = {
            name.casefold() for name in self._type_names if name
        }
        self._value_type.setObjectName(f"type_slot_value_type_{slot.name}")
        self._value_type.setToolTip(_PROPERTY_CONTRACT_TOOLTIPS["type"])

        self._ref_required = QCheckBox("ref required", self)
        self._ref_required.setObjectName(f"type_slot_ref_required_{slot.name}")
        self._ref_required.setChecked(
            slot.ref_required
            or slot.required
            or slot.effective_value_mode()
            in (PropertyValueMode.REF_ONLY, PropertyValueMode.REF_LIST)
        )
        self._ref_required.setToolTip(
            _PROPERTY_CONTRACT_TOOLTIPS["ref_required"])
        self._ref_required.setStyleSheet(
            f"QCheckBox {{ border: 0; color: {FIELD_CHECKBOX_TEXT}; padding-left: 4px; }}"
        )

        init_default = slot.default if slot.default is not None else type_default_value(
            slot.value_type)
        self._default = SwappableDefaultField(
            slot.value_type, init_default, self)
        self._default.setObjectName(f"type_slot_default_{slot.name}")
        self._default.setToolTip(_PROPERTY_CONTRACT_TOOLTIPS["default"])
        # Keep the label widget so we can hide/show it together with _default.
        self._default_label = self._mk_grid_label("default")

        self._description = QLineEdit(slot.description or "", self)
        self._description.setObjectName(f"type_slot_description_{slot.name}")
        self._description.setPlaceholderText("description")
        self._description.setToolTip(
            _PROPERTY_CONTRACT_TOOLTIPS["description"])
        version = QLabel(f"v{slot.version}", self)
        version.setObjectName(f"type_slot_version_{slot.name}")
        version.setStyleSheet(f"color: {FIELD_LABEL_COLOR};")
        version.setToolTip(_PROPERTY_CONTRACT_TOOLTIPS["version"])

        self._style_contract_inputs()
        self._add_grid_row(table, 0, "name", self._name, colspan=3)
        self._add_grid_row(table, 1, "type", self._value_type, colspan=3)
        table.addWidget(self._ref_required, 2, 1, 1, 3)
        # Insert default label + field manually so we hold refs to both for show/hide.
        table.addWidget(self._default_label, 3, 0)
        table.addWidget(self._default, 3, 1, 1, 3)
        self._add_grid_row(table, 4, "docs", self._description, colspan=3)
        table.addWidget(version, 5, 1, 1, 3, Qt.AlignmentFlag.AlignRight)

        self._value_type.currentIndexChanged.connect(self._on_type_changed)
        self._ref_required.stateChanged.connect(self._on_ref_required_changed)
        self._default.committed.connect(lambda _value: self._on_save())
        self._name.editingFinished.connect(self._on_save)
        self._description.editingFinished.connect(self._on_save)

        self._sync_ref_required_enabled_state()
        # Apply initial visibility based on whether this slot starts ref-required.
        self._apply_default_row_visibility()

        self._section.content_layout.addWidget(self._body)
        root.addWidget(self._section)

    def _style_contract_inputs(self) -> None:
        for widget in (
            self._name,
            self._description,
        ):
            style_simple_field(widget)
        style_simple_field(self._value_type)

    def _mk_grid_label(self, label: str) -> QLabel:
        label_widget = QLabel(label + ":", self)
        label_widget.setFixedWidth(_CONTRACT_LABEL_WIDTH)
        label_widget.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label_widget.setStyleSheet(
            f"color: {FIELD_LABEL_COLOR}; font-size: 10px; border: 0;")
        tooltip_key = _PROPERTY_CONTRACT_TOOLTIP_ALIASES.get(label, label)
        tooltip = _PROPERTY_CONTRACT_TOOLTIPS.get(tooltip_key)
        if tooltip is not None:
            label_widget.setToolTip(tooltip)
        return label_widget

    def _add_grid_row(
        self,
        table: QGridLayout,
        row: int,
        label: str,
        widget: QWidget,
        *,
        colspan: int = 1,
        second_label: str | None = None,
        second_widget: QWidget | None = None,
    ) -> None:
        table.addWidget(self._mk_grid_label(label), row, 0)
        table.addWidget(widget, row, 1, 1, colspan)
        if second_label is not None and second_widget is not None:
            table.addWidget(self._mk_grid_label(second_label), row, 3)
            table.addWidget(second_widget, row, 4)

    def _labeled_line(self, label: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        label_widget = QLabel(label + ":", self)
        label_widget.setFixedWidth(58)
        label_widget.setStyleSheet(
            f"color: {FIELD_LABEL_COLOR}; font-size: 10px;")
        tooltip = _PROPERTY_CONTRACT_TOOLTIPS.get(label)
        if tooltip is not None:
            label_widget.setToolTip(tooltip)
        row.addWidget(label_widget)
        row.addWidget(widget, stretch=1)
        return row

    def _on_save(self) -> None:
        selected_value_type = self._value_type.value()
        is_typed_reference = self._is_reference_value_type(selected_value_type)
        is_ref = self._ref_required.isChecked() if is_typed_reference else False
        if is_typed_reference:
            value_mode = PropertyValueMode.REF_ONLY if is_ref else PropertyValueMode.REF_OR_INLINE
            source = SlotSource.REF if is_ref else SlotSource.LITERAL
            default_value = None
        else:
            value_mode = PropertyValueMode.REF_ONLY if is_ref else PropertyValueMode.LITERAL_ONLY
            source = SlotSource.REF if is_ref else SlotSource.LITERAL
            default_value = None if is_ref else self._default.value()
        slot = NodeSlot(
            name=self._name.text().strip() or self._original_name,
            source=source,
            required=True,
            ref_required=is_ref,
            description=self._description.text().strip() or None,
            value_type=selected_value_type or "any",
            value_mode=value_mode,
            version=1,
            # Reference-capable slots do not persist literal defaults.
            default=default_value,
        )
        self.save_requested.emit(self._original_name, slot)

    def _apply_default_row_visibility(self) -> None:
        """Show default field only when ref is NOT required."""
        visible = not self._ref_required.isChecked()
        self._default_label.setVisible(visible)
        self._default.setVisible(visible)

    def _on_ref_required_changed(self) -> None:
        self._apply_default_row_visibility()
        self._on_save()

    def _on_type_changed(self) -> None:
        """Swap the default field widget to match the newly selected type."""
        new_type = self._value_type.value() or "any"
        self._default.set_type(new_type)
        self._sync_ref_required_enabled_state()
        # Persist immediately so type edits survive deselection/reselection.
        self._on_save()

    def _sync_ref_required_enabled_state(self) -> None:
        """Enable ref-required only for value types that resolve to knowledge node types."""
        selected_value_type = self._value_type.value()
        can_require_ref = self._is_reference_value_type(selected_value_type)
        self._ref_required.setEnabled(can_require_ref)
        if not can_require_ref:
            with QSignalBlocker(self._ref_required):
                self._ref_required.setChecked(False)
            self._ref_required.setToolTip(
                "Disabled for primitive/data value types. "
                "Select a knowledge node type to allow references."
            )
        else:
            self._ref_required.setToolTip(
                _PROPERTY_CONTRACT_TOOLTIPS["ref_required"]
            )
        self._apply_default_row_visibility()

    def _is_reference_value_type(self, value_type: str | None) -> bool:
        if value_type is None:
            return False
        token = value_type.strip()
        if not token:
            return False
        return token.casefold() in self._type_name_tokens


def _compact_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def _parse_json_or_raw(raw: str) -> object:
    text = raw.strip()
    if not text:
        return None
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return raw
    return raw


def _parse_optional_int(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _source_for_mode(mode: PropertyValueMode) -> SlotSource:
    if mode == PropertyValueMode.REF_LIST:
        return SlotSource.REF_LIST
    if mode.allows_reference:
        return SlotSource.REF
    return SlotSource.LITERAL


def _is_inline_structured(value: object) -> bool:
    """Check if value is a nested dict/list (has depth > 1 or contains collections)."""
    if not isinstance(value, (dict, list)):
        return False
    if isinstance(value, dict):
        return any(isinstance(v, (dict, list)) for v in value.values())
    if isinstance(value, list):
        return any(isinstance(v, (dict, list)) for v in value)
    return False


def _flatten_inline_leaf_paths(value: object, prefix: str = "") -> list[tuple[str, object]]:
    leaves: list[tuple[str, object]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            leaves.extend(_flatten_inline_leaf_paths(child, child_prefix))
        return leaves
    if isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}.{index}" if prefix else str(index)
            leaves.extend(_flatten_inline_leaf_paths(child, child_prefix))
        return leaves
    if prefix:
        leaves.append((prefix, value))
    return leaves


# ---------------------------------------------------------------------------
# Editable literal row
# ---------------------------------------------------------------------------

class _EditableRow(QWidget):
    """Inline QLineEdit that commits on Return or blur."""

    committed = Signal(object)

    def __init__(
        self,
        key: str,
        value: object,
        parent: QWidget | None = None,
        *,
        value_type: str = "string",
        tooltip: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"prop_row_{key}")
        self._value_type = value_type
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        key_lbl = _mk_field_label(key, self)
        if tooltip:
            key_lbl.setToolTip(tooltip)
        # Allow label to shrink when space is constrained.
        # Undo the setFixedWidth from make_field_label by setting min/max width separately.
        key_lbl.setMinimumWidth(0)
        key_lbl.setMaximumWidth(16777215)  # Qt's QWIDGETSIZE_MAX
        key_lbl.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Fixed)

        self._edit = make_primitive_field(
            value_type,
            value,
            self,
            auto_multiline_overflow=True,
        )
        self._edit.setObjectName(f"prop_edit_{key}")
        style_simple_field(self._edit)
        existing_style = self._edit.styleSheet() or ""
        if "border-radius" not in existing_style:
            self._edit.setStyleSheet(existing_style + " border-radius: 0;")
        if tooltip:
            self._edit.setToolTip(tooltip)
        self._edit.setMinimumWidth(0)
        overflow_enabled = isinstance(self._edit, QFieldBase) and hasattr(
            self._edit, "auto_multiline_overflow_enabled"
        ) and self._edit.auto_multiline_overflow_enabled()
        self._edit.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred if overflow_enabled else QSizePolicy.Policy.Fixed,
        )
        if overflow_enabled:
            layout.setAlignment(key_lbl, Qt.AlignmentFlag.AlignTop)

        layout.addWidget(key_lbl)
        layout.addWidget(self._edit, stretch=1)
        self._wire_live_geometry_sync()

        if isinstance(self._edit, QFieldBase):
            # Use generic field controls (inner clear/revert) for consistency.
            self._edit.set_editable(True)

        committed_signal = getattr(self._edit, "committed", None)
        if committed_signal is not None:
            committed_signal.connect(
                lambda value, _reason: self.committed.emit(value))
        elif isinstance(self._edit, QLineEdit):
            self._edit.editingFinished.connect(self._emit)

    def _wire_live_geometry_sync(self) -> None:
        editor = self._edit.findChild(QPlainTextEdit)
        if editor is None:
            return
        editor.textChanged.connect(self._sync_live_geometry)

    def _sync_live_geometry(self) -> None:
        self._edit.updateGeometry()
        self.updateGeometry()
        parent: QWidget | None = self
        while parent is not None:
            layout = parent.layout()
            if layout is not None:
                layout.activate()
            parent.updateGeometry()
            parent = parent.parentWidget()

    def set_editable(self, editable: bool) -> None:
        """Enable or disable editing controls while keeping value visible."""
        if isinstance(self._edit, QFieldBase):
            self._edit.set_editable(editable)
        else:
            self._edit.setEnabled(editable)

    def _emit(self) -> None:
        self.committed.emit(field_value(self._edit))

    def _clear(self) -> None:
        """Reset the field to its type default and emit committed."""
        _FIELD_TYPE_DEFAULTS: dict[str, object] = {
            "string": "",
            "int": 0,
            "float": 0.0,
            "bool": False,
        }
        default = _FIELD_TYPE_DEFAULTS.get(self._value_type, "")
        if isinstance(self._edit, QFieldBase):
            self._edit.set_value(default)
        elif isinstance(self._edit, QLineEdit):
            self._edit.setText("" if self._value_type ==
                               "string" else str(default))
        self.committed.emit(default)


class _RefOrValueRow(QWidget):
    """Editable row that allows either direct value editing or reference picking."""

    committed = Signal(str)
    pick_requested = Signal(str)
    clear_requested = Signal(str)

    def __init__(
        self,
        slot_name: str,
        value_text: str,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"ref_or_value_row_{slot_name}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)
        key_lbl = _mk_field_label(slot_name, self)
        # Allow label to shrink when space is constrained.
        key_lbl.setMinimumWidth(0)
        key_lbl.setMaximumWidth(16777215)  # Qt's QWIDGETSIZE_MAX
        key_lbl.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Fixed)
        self._edit = QLineEdit(value_text, self)
        self._edit.setObjectName(f"prop_edit_{slot_name}")
        style_simple_field(self._edit)
        self._edit.setMinimumWidth(0)
        self._edit.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._edit.setFixedHeight(FIELD_ROW_HEIGHT)

        pick_btn = _mk_icon_btn("kwb_btn_pick_ref.svg", "Pick reference", self)
        pick_btn.setObjectName(f"prop_pick_{slot_name}")
        pick_btn.clicked.connect(lambda: self.pick_requested.emit(slot_name))

        clear_btn = ClearFieldButton("Clear value or reference", self)
        clear_btn.setObjectName(f"prop_clear_{slot_name}")
        clear_btn.clicked.connect(
            lambda: (self._edit.clear(), self.clear_requested.emit(slot_name)))

        layout.addWidget(key_lbl)
        layout.addWidget(self._edit, stretch=1)
        layout.addWidget(pick_btn)
        layout.addWidget(clear_btn)
        self._edit.editingFinished.connect(self._emit)

    def _emit(self) -> None:
        self.committed.emit(self._edit.text())


class _RefListRow(QWidget):
    """Editable row for multiple typed references with cardinality and type feedback."""

    add_requested = Signal(str)
    remove_requested = Signal(str, int)
    move_requested = Signal(str, int, int)

    def __init__(
        self,
        slot_name: str,
        entries: list[str],
        *,
        target_type: str | None = None,
        cardinality: PropertyCardinality | None = None,
        min_count: int | None = None,
        max_count: int | None = None,
        session: EditorSession | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"ref_list_row_{slot_name}")
        self._target_type = target_type
        self._cardinality = cardinality or PropertyCardinality.SINGLE
        self._min_count = min_count
        self._max_count = max_count
        self._session = session
        self._slot_name = slot_name
        self._entries = entries

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 1, 2, 1)
        header_layout.setSpacing(4)
        key_lbl = _mk_field_label(slot_name, self)

        # Build cardinality feedback text
        count_text = self._build_count_feedback()
        count_lbl = QLabel(count_text, self)
        count_lbl.setStyleSheet(
            f"font-size: 11px; color: {FIELD_LABEL_COLOR};")

        add_btn = _mk_icon_btn("kwb_btn_add.svg", "Add reference", self)
        add_btn.setObjectName(f"prop_list_add_{slot_name}")
        # Disable add button if max cardinality reached
        add_btn.setEnabled(self._can_add_more())
        if not self._can_add_more():
            add_btn.setToolTip(f"Maximum {self._max_count} item(s) reached")
        add_btn.clicked.connect(lambda: self.add_requested.emit(slot_name))

        header_layout.addWidget(key_lbl)
        header_layout.addWidget(count_lbl, stretch=1)
        header_layout.addWidget(add_btn)
        outer.addWidget(header)

        for index, entry in enumerate(entries):
            row = QWidget(self)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(18, 1, 2, 1)
            row_layout.setSpacing(4)

            # Extract ref status and display text
            ref_text, status = self._parse_entry_status(entry)

            # Color-code based on status (valid: cyan, missing: red, type-mismatch: yellow, malformed: orange)
            if status == "missing":
                color = REF_MISSING_COLOR
                tooltip = "Reference target not found"
            elif status == "type-mismatch":
                color = REF_MISMATCH_COLOR
                tooltip = f"Reference type mismatch (expected: {self._target_type})"
            elif status == "malformed":
                color = REF_MALFORMED_COLOR
                tooltip = "Reference structure is malformed"
            else:  # valid
                color = REF_VALID_COLOR
                tooltip = "Valid reference"

            value_lbl = QLabel(ref_text, self)
            value_lbl.setStyleSheet(f"font-size: 11px; color: {color};")
            value_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            value_lbl.setToolTip(tooltip)

            up_btn = _mk_icon_btn("kwb_btn_move_up.svg", "Move up", self)
            up_btn.setObjectName(f"prop_list_up_{slot_name}_{index}")
            up_btn.setEnabled(index > 0)
            up_btn.clicked.connect(
                lambda _checked=False, sn=slot_name, i=index: self.move_requested.emit(sn, i, -1))

            down_btn = _mk_icon_btn("kwb_btn_move_down.svg", "Move down", self)
            down_btn.setObjectName(f"prop_list_down_{slot_name}_{index}")
            down_btn.setEnabled(index < len(entries) - 1)
            down_btn.clicked.connect(
                lambda _checked=False, sn=slot_name, i=index: self.move_requested.emit(sn, i, 1))

            remove_btn = ClearFieldButton("Remove reference", self)
            remove_btn.setObjectName(f"prop_list_remove_{slot_name}_{index}")
            remove_btn.clicked.connect(
                lambda _checked=False, sn=slot_name, i=index: self.remove_requested.emit(sn, i))

            row_layout.addWidget(value_lbl, stretch=1)
            row_layout.addWidget(up_btn)
            row_layout.addWidget(down_btn)
            row_layout.addWidget(remove_btn)
            outer.addWidget(row)

    def _build_count_feedback(self) -> str:
        """Build cardinality feedback text."""
        count = len(self._entries)
        if self._max_count is not None:
            return f"{count}/{self._max_count} item(s)"
        elif self._min_count is not None:
            return f"{count} item(s) (min: {self._min_count})"
        return f"{count} item(s)"

    def _can_add_more(self) -> bool:
        """Check if we can add more items based on cardinality."""
        if self._max_count is None:
            return True
        return len(self._entries) < self._max_count

    def _matches_target_type(self, ref_node: Node) -> bool:
        """Return True when *ref_node* is compatible with this row's target type token."""
        if self._session is None or self._target_type is None:
            return True

        token = self._target_type.strip()
        if token == "":
            return True

        matching_ids = {
            str(candidate.id)
            for candidate in self._session.reference_options(token)
        }
        if str(ref_node.id) in matching_ids:
            return True

        # Legacy compatibility for untyped assets: accept category-token match.
        return ref_node.type_id is None and ref_node.category.strip().casefold() == token.casefold()

    def _parse_entry_status(self, entry: str) -> tuple[str, str]:
        """Parse entry to extract text and status.

        Returns: (display_text, status) where status is 'valid', 'missing', 'type-mismatch', or 'malformed'.
        """
        if "(missing)" in entry:
            return entry, "missing"
        if "malformed:" in entry:
            return entry, "malformed"

        # Try to extract ref_id and check for type mismatch
        if self._session is not None and self._target_type is not None:
            # Parse ref_id from entry format: "1. → RefName  (ref_id)"
            try:
                if "(" in entry and ")" in entry:
                    ref_id = entry[entry.rfind("(")+1:entry.rfind(")")]
                    try:
                        ref_node = self._session.get_node(ref_id)
                        if not self._matches_target_type(ref_node):
                            actual = str(
                                ref_node.type_id) if ref_node.type_id is not None else ref_node.category
                            return f"{entry}  [type: {actual}]", "type-mismatch"
                    except KeyError:
                        pass  # Already handled as "missing"
            except Exception:
                pass

        return entry, "valid"


# ---------------------------------------------------------------------------
# Reference row
# ---------------------------------------------------------------------------

class _InlineTreeRow(QWidget):
    """Expandable inline-value tree that exposes editable leaf values."""

    leaf_committed = Signal(str, str, str)
    clear_requested = Signal(str)
    promote_requested = Signal(str)

    def __init__(
        self,
        slot_name: str,
        value: object,
        parent: QWidget | None = None,
        *,
        can_promote: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"inline_tree_row_{slot_name}")
        self._expanded = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 1, 2, 1)
        header_layout.setSpacing(4)
        self._toggle_btn = _mk_icon_btn(
            "kwb_btn_collapse.svg", "Collapse nested value", self)
        self._toggle_btn.clicked.connect(self._toggle_expanded)
        key_lbl = _mk_field_label(slot_name, self)
        summary = QLabel(_compact_json(value), self)
        summary.setStyleSheet(f"font-size: 11px; color: {REF_VALID_COLOR};")
        summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        if can_promote:
            promote_btn = _mk_icon_btn(
                "kwb_btn_promote.svg",
                "Promote to instance",
                self,
            )
            promote_btn.setObjectName(f"prop_promote_{slot_name}")
            promote_btn.clicked.connect(
                lambda: self.promote_requested.emit(slot_name))
            header_layout.addWidget(promote_btn)
        clear_btn = ClearFieldButton("Clear inline value", self)
        clear_btn.clicked.connect(lambda: self.clear_requested.emit(slot_name))
        header_layout.addWidget(self._toggle_btn)
        header_layout.addWidget(key_lbl)
        header_layout.addWidget(summary, stretch=1)
        outer.addWidget(header)
        header_layout.addWidget(clear_btn)

        self._children = QWidget(self)
        children_layout = QVBoxLayout(self._children)
        children_layout.setContentsMargins(_FIELD_LABEL_WIDTH + 34, 0, 0, 0)
        children_layout.setSpacing(2)
        for path, leaf in _flatten_inline_leaf_paths(value):
            row = _EditableRow(path, "" if leaf is None else str(leaf), self)
            row.committed.connect(lambda text, sn=slot_name,
                                  p=path: self.leaf_committed.emit(sn, p, text))
            children_layout.addWidget(row)
        outer.addWidget(self._children)

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._children.setVisible(self._expanded)
        icon_name = "kwb_btn_collapse.svg" if self._expanded else "kwb_btn_expand_right.svg"
        self._toggle_btn.setIcon(make_square_svg_icon(icon_name))


class _RefRow(QWidget):
    """Row for a reference-typed slot with pick / clear / expand / save buttons."""

    pick_requested = Signal(str)   # slot_name
    clear_requested = Signal(str)  # slot_name
    create_requested = Signal(str)  # slot_name

    def __init__(
        self,
        slot_name: str,
        ref_id: str | None,
        ref_display: str,
        ref_node: Node | None,
        session: EditorSession,
        *,
        can_create_inline: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._slot_name = slot_name
        self._ref_node = ref_node
        self._session = session
        self._expanded = False
        self.setObjectName(f"ref_row_{slot_name}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        main_row = QWidget(self)
        row_layout = QHBoxLayout(main_row)
        row_layout.setContentsMargins(2, 1, 2, 1)
        row_layout.setSpacing(4)

        key_lbl = _mk_field_label(slot_name, self)

        self._val_lbl = QLabel(ref_display, self)
        self._val_lbl.setStyleSheet(
            f"font-size: 11px; color: {REF_VALID_COLOR};")
        self._val_lbl.setMinimumWidth(0)
        self._val_lbl.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._val_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)

        pick_btn = _mk_icon_btn("kwb_btn_pick_ref.svg", "Pick reference", self)
        pick_btn.setObjectName(f"prop_pick_{slot_name}")
        pick_btn.clicked.connect(lambda: self.pick_requested.emit(slot_name))

        add_btn = _mk_icon_btn(
            "kwb_btn_construct_inline.svg", "Construct inline value", self)
        add_btn.setObjectName(f"prop_add_{slot_name}")
        add_btn.setVisible(can_create_inline)
        add_btn.clicked.connect(lambda: self.create_requested.emit(slot_name))

        clear_btn = ClearFieldButton("Clear reference", self)
        clear_btn.setObjectName(f"prop_clear_{slot_name}")
        clear_btn.clicked.connect(lambda: self.clear_requested.emit(slot_name))

        self._expand_btn = _mk_icon_btn(
            "kwb_btn_expand_right.svg", "Expand referenced node", self)
        self._expand_btn.setVisible(ref_node is not None)
        self._expand_btn.clicked.connect(self._toggle_expand)

        save_btn = _mk_icon_btn(
            "kwb_btn_load.svg", "Export referenced node as JSON", self)
        save_btn.setVisible(ref_node is not None)
        save_btn.clicked.connect(self._do_save)

        row_layout.addWidget(key_lbl)
        row_layout.addWidget(self._val_lbl, stretch=1)
        row_layout.addWidget(pick_btn)
        row_layout.addWidget(add_btn)
        row_layout.addWidget(clear_btn)
        row_layout.addWidget(self._expand_btn)
        row_layout.addWidget(save_btn)
        outer.addWidget(main_row)

        self._sub_panel = QFrame(self)
        self._sub_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self._sub_panel.setStyleSheet(
            f"QFrame {{ border: 1px solid {REF_SUBPANEL_BORDER}; background: {REF_SUBPANEL_BG}; margin-left: 16px; }}"
        )
        sub_layout = QVBoxLayout(self._sub_panel)
        sub_layout.setContentsMargins(6, 4, 6, 4)
        sub_layout.setSpacing(2)
        if ref_node is not None:
            self._populate_sub_panel(sub_layout, ref_node)
        self._sub_panel.setVisible(False)
        outer.addWidget(self._sub_panel)

    def _populate_sub_panel(self, layout: QVBoxLayout, node: Node) -> None:
        layout.addWidget(_ReadonlyRow("id", str(node.id), self._sub_panel))
        layout.addWidget(_ReadonlyRow("name", node.name, self._sub_panel))
        layout.addWidget(_ReadonlyRow(
            "category", node.category, self._sub_panel))
        if node.description:
            layout.addWidget(_ReadonlyRow(
                "description", node.description, self._sub_panel))
        for key, value in node.props.items():
            if key == "slots":
                continue
            if isinstance(value, str):
                try:
                    rn = self._session.get_node(value)
                    display = f"→ {rn.name}"
                except KeyError:
                    display = f"→ {value}"
            elif isinstance(value, dict):
                try:
                    display = json.dumps(value, ensure_ascii=False)
                except Exception:
                    display = str(value)
            elif isinstance(value, list):
                try:
                    display = json.dumps(value, ensure_ascii=False)
                except Exception:
                    display = str(value)
            else:
                display = str(value) if value is not None else "(none)"
            layout.addWidget(_ReadonlyRow(key, display, self._sub_panel))

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        self._sub_panel.setVisible(self._expanded)
        icon_name = "kwb_btn_expand_down.svg" if self._expanded else "kwb_btn_expand_right.svg"
        self._expand_btn.setIcon(make_square_svg_icon(icon_name))

    def _do_save(self) -> None:
        if self._ref_node is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export node as JSON",
            f"{self._ref_node.name}.json",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(
                self._ref_node.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))


# ---------------------------------------------------------------------------
# Inherited-slot collection helper
# ---------------------------------------------------------------------------


def _collect_inherited_slots(session: EditorSession, node: Node) -> dict[str, NodeSlot]:
    """Return the merged slot dict for *node*, traversing the extends chain.

    Ancestors are visited outermost-first so that each child type can
    override a parent slot by the same name.  The direct type's slots win.
    Instance's own ``type_id`` is tried first, then the ``instance_of`` link.
    """
    from lks_utils.knowledge.resolver import Resolver

    resolver = Resolver(session._repository)  # noqa: SLF001

    type_node: Node | None = None
    if node.type_id is not None:
        try:
            tn = session.get_node(str(node.type_id))
            if is_type(tn):
                type_node = tn
        except KeyError:
            pass
    if type_node is None:
        type_node = resolver.fetch_type_for_instance(node)

    if type_node is None:
        return {}

    # Ancestors outermost first, then direct type
    chain = resolver.fetch_parent_chain(type_node) + [type_node]
    merged: dict[str, NodeSlot] = {}
    for n in chain:
        if is_type(n):
            for slot in as_type(n).slots:
                merged[slot.name] = slot  # child overrides parent
    return merged


def _collect_inherited_slot_provenance(session: EditorSession, node: Node) -> dict[str, str]:
    """Return slot->type-name provenance for the merged inherited slot set."""
    from lks_utils.knowledge.resolver import Resolver

    resolver = Resolver(session._repository)  # noqa: SLF001

    type_node: Node | None = None
    if node.type_id is not None:
        try:
            tn = session.get_node(str(node.type_id))
            if is_type(tn):
                type_node = tn
        except KeyError:
            pass
    if type_node is None:
        type_node = resolver.fetch_type_for_instance(node)
    if type_node is None:
        return {}

    chain = resolver.fetch_parent_chain(type_node) + [type_node]
    provenance: dict[str, str] = {}
    for type_candidate in chain:
        if not is_type(type_candidate):
            continue
        owner_name = type_candidate.name or str(type_candidate.id)
        for slot in as_type(type_candidate).slots:
            provenance[slot.name] = owner_name
    return provenance


def _slot_sort_metadata(slot: NodeSlot | None, *keys: str) -> object | None:
    """Return optional slot sort metadata from direct fields or constraints."""
    if slot is None:
        return None
    for key in keys:
        value = getattr(slot, key, None)
        if value is not None:
            return value
    constraints = slot.constraints if isinstance(
        slot.constraints, dict) else {}
    for key in keys:
        value = constraints.get(key)
        if value is not None:
            return value
    return None


def _slot_manual_sort_priority(slot: NodeSlot | None) -> int:
    """Return manual slot sort priority when present, else a stable fallback."""
    raw_priority = _slot_sort_metadata(
        slot,
        "manual_sort_priority",
        "sort_priority",
        "sort_order",
        "priority",
        "order",
    )
    if isinstance(raw_priority, bool):
        return int(raw_priority)
    if isinstance(raw_priority, int):
        return raw_priority
    if isinstance(raw_priority, str):
        try:
            return int(raw_priority.strip())
        except ValueError:
            pass
    return 2**31 - 1


def _slot_stable_uid(property_name: str, slot: NodeSlot | None) -> str:
    """Return the most stable property uid available for deterministic ordering."""
    raw_uid = _slot_sort_metadata(
        slot,
        "uid",
        "slot_uid",
        "property_uid",
        "id",
    )
    if raw_uid is None:
        return property_name.casefold()
    return str(raw_uid).casefold()


def _ordered_property_names(
    visible_props: dict[str, object],
    slots: dict[str, NodeSlot],
) -> list[str]:
    """Return deterministic property order across local and inherited rows."""
    property_names = {
        property_name
        for property_name in (set(visible_props) | set(slots))
        if isinstance(property_name, str) and property_name.strip()
    }
    return sorted(
        property_names,
        key=lambda property_name: (
            _slot_manual_sort_priority(slots.get(property_name)),
            property_name.casefold(),
            _slot_stable_uid(property_name, slots.get(property_name)),
        ),
    )


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class QKnowledgeInspectorPanel(QWidget):
    """Editable Inspector panel for the currently selected knowledge node.

    Literal props use inline ``QLineEdit`` fields.  Ref props show pick / clear
    / expand / save buttons.  Name and description are always editable.
    """

    node_mutated = Signal(str)  # node_id
    node_selection_requested = Signal(str)
    mutation_applied = Signal(object)

    def __init__(
        self,
        session: EditorSession,
        *,
        draft_edits: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._draft_edits = draft_edits
        self._current_node: Node | None = None
        self._selected_slot_name: str | None = None
        self._section_state_by_scope: dict[str, dict[str, bool]] = {}
        self._skip_next_rebuild_state_capture = False

        self._header = QLabel("Inspector", self)
        self._header.setObjectName("inspector_header")
        self._header.setStyleSheet("font-weight: 600; font-size: 12px;")

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch(1)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._content)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Keep a constant gutter so content width does not jump when overflow appears.
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)
        root.addWidget(self._header)
        root.addWidget(self._scroll, stretch=1)

        self._apply_styles()

    def _node_for_edit(self, node_id: str) -> Node:
        return self._session.get_node(node_id)

    @staticmethod
    def _slot_ref_link_ids_for_node(repo: Repository, node_id: str) -> set[str]:
        """Return slot_ref link ids sourced from *node_id* in *repo*."""
        return {
            str(link.id)
            for link in repo.list_links()
            if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
        }

    @staticmethod
    def _slot_ref_target_ids_for_slot(
        repo: Repository,
        node_id: str,
        slot_name: str,
    ) -> list[str]:
        """Return target node ids for one slot_ref-backed slot in stable file order."""
        return [
            str(link.target_node_id)
            for link in repo.list_links()
            if (
                link.link_type_id == SLOT_REF_LINK_TYPE_ID
                and link.source_node_id == node_id
                and link.source_slot_name == slot_name
            )
        ]

    @classmethod
    def _normalize_slot_ref_value(
        cls,
        repo: Repository,
        node_id: str,
        slot_name: str,
        is_list: bool,
    ) -> object | None:
        """Return synthesized current reference ids for UI rows.

        Slot-ref links are the source of truth, so the inspector synthesizes
        raw node ids from link targets.
        """
        target_ids = cls._slot_ref_target_ids_for_slot(
            repo, node_id, slot_name)
        if target_ids:
            if is_list:
                return target_ids
            return target_ids[0]
        return None

    @staticmethod
    def _extract_ref_target_id(value: object) -> str | None:
        """Return target node id from a reference value."""
        if isinstance(value, str) and value:
            return value
        return None

    def _apply_replacement_update(self, node: Node, updated: Node, *, dirty_reason: str) -> Node:
        node_id = str(node.id)

        def _mutate(repo: Repository) -> set[str]:
            repo.upsert(updated)
            return {node_id}

        with profile_action(
            "knowledge.inspector.commit",
            phase="replace_node",
            metadata={"dirty_reason": dirty_reason},
        ) as action_scope:
            result = self._session.apply_mutation(
                "inspector_replace_node",
                _mutate,
                validation_mode="touched_only",
            )
            action_scope.add_metadata("touched_count", len(result.touched_ids))
            if not result.ok:
                action_scope.set_outcome("fail")
        if not result.ok:
            raise ValueError(result.save_error or "Failed to update node")
        self._emit_mutation_payload(
            result.touched_ids, dirty_reason=dirty_reason)
        return self._session.get_node(str(node.id))

    def _apply_mutator_update(
        self,
        node: Node,
        *,
        dirty_reason: str,
        mutate: Callable[[Mutator, str], None],
    ) -> Node:
        node_id = str(node.id)

        def _mutate(repo: Repository) -> set[str]:
            before_link_ids = self._slot_ref_link_ids_for_node(repo, node_id)
            mutate(Mutator(repo), node_id)
            after_link_ids = self._slot_ref_link_ids_for_node(repo, node_id)
            return {node_id, *before_link_ids, *after_link_ids}

        with profile_action(
            "knowledge.inspector.commit",
            phase="mutator_update",
            metadata={"dirty_reason": dirty_reason},
        ) as action_scope:
            result = self._session.apply_mutation(
                "inspector_mutator_update",
                _mutate,
                validation_mode="touched_only",
            )
            action_scope.add_metadata("touched_count", len(result.touched_ids))
            if not result.ok:
                action_scope.set_outcome("fail")
        if not result.ok:
            if result.save_error and "Node not found" in result.save_error:
                raise KeyError(node_id)
            raise ValueError(result.save_error or "Failed to update node")
        self._emit_mutation_payload(
            result.touched_ids, dirty_reason=dirty_reason)
        return self._session.get_node(node_id)

    def _emit_mutation_payload(self, touched_ids: set[str], *, dirty_reason: str | None = None) -> None:
        payload = {
            "touched_ids": set(str(object_id) for object_id in touched_ids),
        }
        if dirty_reason is not None:
            payload["dirty_reason"] = dirty_reason
        self.mutation_applied.emit(payload)

    def set_node(self, node: Node | None) -> None:
        """Populate rows from *node*; pass ``None`` to clear."""
        self._remember_section_state()
        self._current_node = node
        self._selected_slot_name = None
        self._skip_next_rebuild_state_capture = True
        self._rebuild()

    def prepare_node_for_display(self, node: Node) -> Node:
        """Return a display-ready node, applying one-shot instance drift repair when needed."""
        if node.type_id is None:
            return node
        validator = InstanceValidator(self._session._io.repository)  # noqa: SLF001
        repaired = validator.repair_node(node)
        if repaired is None:
            return node

        node_id = str(repaired.id)

        def _mutate(repo: Repository) -> set[str]:
            repo.upsert(repaired)
            return {node_id}

        result = self._session.apply_mutation(
            "inspector_prepare_repair",
            _mutate,
            validation_mode="touched_only",
        )
        if result.ok:
            self._emit_mutation_payload(result.touched_ids)
        return self._session.get_node(str(repaired.id))

    def select_slot(self, slot_name: str | None) -> None:
        """Show only the selected slot/property, or the root node when None."""
        if isinstance(slot_name, str) and slot_name.startswith("__group_"):
            slot_name = None
        self._remember_section_state()
        self._selected_slot_name = slot_name
        self._skip_next_rebuild_state_capture = True
        self._rebuild()
        if slot_name is not None:
            QApplication.processEvents()
            self.focus_slot(slot_name)

    def clear(self) -> None:
        self.set_node(None)

    def focus_slot(self, slot_name: str) -> None:
        candidates = [
            f"type_slot_frame_{slot_name}",
            f"prop_edit_{slot_name}",
            f"prop_pick_{slot_name}",
            f"prop_clear_{slot_name}",
            f"validation_inline_{slot_name}",
            f"validation_pick_{slot_name}",
            f"validation_discard_{slot_name}",
            f"ref_row_{slot_name}",
            f"validation_row_{slot_name}",
        ]
        for object_name in candidates:
            widget = self.findChild(QWidget, object_name)
            if widget is None:
                continue
            self._scroll.ensureWidgetVisible(widget)
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            QApplication.processEvents()
            if object_name.startswith("type_slot_frame_"):
                break
            widget.setFocus(Qt.FocusReason.OtherFocusReason)
            widget.activateWindow()
            break

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _rebuild(self, *, full_layout_sync: bool = True) -> None:
        if not self._skip_next_rebuild_state_capture:
            self._remember_section_state()
        self._skip_next_rebuild_state_capture = False
        # Remove all rows before the trailing stretch
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.setParent(None)
                widget.deleteLater()

        node = self._current_node
        if node is None:
            self._header.setText("Inspector")
            return
        self._header.setText(f"Inspector — {node.name}")
        if self._selected_slot_name is None:
            self._add_meta_rows(node)
        if is_type(node):
            self._add_type_rows(node)
        else:
            self._add_instance_rows(node)

        self._restore_section_state()

        if full_layout_sync:
            # Force layout recalculation for collapsible sections so they display
            # with proper heights on initial load instead of requiring manual toggle.
            # The key is to recursively process all nested layouts before asking
            # the collapsible sections to sync their geometry.
            from lks_utils.gui_qt.widgets import QCollapsibleSection

            # Step 1: Force immediate layout processing on content widget and all children
            self._content.ensurePolished()
            self._content_layout.activate()

            # Step 2: Recursively update all nested layouts in collapsible sections
            sections = self.findChildren(QCollapsibleSection)
            for section in sections:
                # Ensure the section's content widget and its layout are fully processed
                section.content.ensurePolished()
                section.content_layout.activate()

                # Recursively process all child layouts
                all_children = section.content.findChildren(QWidget)
                for child in all_children:
                    child.ensurePolished()
                    if child.layout():
                        child.layout().activate()

                # Now queue the geometry sync after everything is polished
                section.schedule_geometry_sync()

            # Step 3: Flush only a bounded slice of pending events so layout timers
            # can run without risking long re-entrant event-loop stalls.
            QCoreApplication.sendPostedEvents(None, 0)
            QApplication.processEvents(
                QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
                2,
            )

            # Step 4: Final geometry update on scroll area
            self._scroll.updateGeometry()
            QCoreApplication.sendPostedEvents(None, 0)

    def _section_state_scope(self) -> str | None:
        node = self._current_node
        if node is None:
            return None
        slot = self._selected_slot_name or "__root__"
        return f"{node.id}:{slot}"

    def _remember_section_state(self) -> None:
        scope = self._section_state_scope()
        if scope is None:
            return
        state: dict[str, bool] = {}
        for section in self.findChildren(QCollapsibleSection):
            key = _collapsible_section_state_key(section)
            if key is None:
                continue
            state[key] = section.is_expanded
        if state:
            self._section_state_by_scope[scope] = state

    def _restore_section_state(self) -> None:
        scope = self._section_state_scope()
        if scope is None:
            return
        state = self._section_state_by_scope.get(scope)
        if not state:
            return
        for section in self.findChildren(QCollapsibleSection):
            key = _collapsible_section_state_key(section)
            if key is None or key not in state:
                continue
            section.set_expanded(state[key])

    def _insert(self, widget: QWidget) -> None:
        """Insert widget before the trailing stretch."""
        self._content_layout.insertWidget(
            self._content_layout.count() - 1, widget)

    def _insert_section_row(self, section_layout: QVBoxLayout, widget: QWidget) -> None:
        section_layout.addWidget(widget)

    def _type_name_options(self) -> list[str]:
        names: list[str] = []
        for type_node in self._session.iter_types():
            if type_node.name:
                names.append(type_node.name)
        return names

    def _promotable_type_node(self, slot: NodeSlot | None) -> Node | None:
        if slot is None or slot.value_mode not in {
            PropertyValueMode.INLINE_ONLY,
            PropertyValueMode.REF_OR_INLINE,
        }:
            return None
        slot_type = str(slot.value_type or "").strip()
        if not slot_type:
            return None
        for type_node in self._session.iter_types():
            if type_node.name == slot_type or str(type_node.id) == slot_type:
                return type_node
        return None

    def _default_inline_value_for_slot(self, slot: NodeSlot | None) -> dict[str, object]:
        type_node = self._promotable_type_node(slot)
        if type_node is None:
            return {}
        from lks_utils.knowledge.resolver import Resolver
        resolver = Resolver(self._session._repository)  # noqa: SLF001
        chain = resolver.fetch_parent_chain(type_node) + [type_node]
        merged_slots: dict[str, NodeSlot] = {}
        for candidate in chain:
            if not is_type(candidate):
                continue
            for candidate_slot in as_type(candidate).slots:
                merged_slots[candidate_slot.name] = candidate_slot
        return {
            name: candidate_slot.default_value()
            for name, candidate_slot in merged_slots.items()
        }

    def _add_meta_rows(self, node: Node) -> None:
        section, section_layout = _mk_section("Meta", self)
        self._insert(section)
        self._insert_section_row(section_layout, _ReadonlyRow("id", str(node.id),
                                 tooltip=_META_TOOLTIPS["id"]))

        name_row = _EditableRow(
            "name", node.name, tooltip=_META_TOOLTIPS["name"])
        name_row.committed.connect(
            lambda v, n=node: self._save_field(n, "name", v))
        self._insert_section_row(section_layout, name_row)

        if can_write_meta_field(field="category", node_category=node.category):
            cat_row = _EditableRow("category", node.category,
                                   tooltip=_META_TOOLTIPS["category"])
            cat_row.committed.connect(
                lambda v, n=node: self._save_field(n, "category", v))
            self._insert_section_row(section_layout, cat_row)
        else:
            self._insert_section_row(
                section_layout,
                _ReadonlyRow(
                    "category",
                    node.category,
                    tooltip=_META_TOOLTIPS["category"],
                ),
            )

        if node.type_id is not None:
            type_label = str(node.type_id)
            try:
                tn = self._session.get_node(str(node.type_id))
                type_label = f"{tn.name}  ({type_label})"
            except KeyError:
                pass
            self._insert_section_row(section_layout, _ReadonlyRow("type_id", type_label,
                                     tooltip=_META_TOOLTIPS["type_id"]))

        desc_row = _EditableRow(
            "description", node.description or "", tooltip=_META_TOOLTIPS["description"])
        desc_row.committed.connect(
            lambda v, n=node: self._save_field(n, "description", v))
        self._insert_section_row(section_layout, desc_row)

    def _add_type_rows(self, node: Node) -> None:
        tv = as_type(node)

        if self._selected_slot_name is not None:
            # A slot is selected — render its contract widget directly in the
            # inspector content (no outer wrapping section) so the nested
            # QCollapsibleSection inside _TypePropertyContractRow is at the
            # top level of the scroll content and sizes itself correctly.
            for slot in tv.slots:
                if slot.name != self._selected_slot_name:
                    continue
                row = _TypePropertyContractRow(
                    slot, self._type_name_options(), self)
                row.save_requested.connect(
                    lambda original_name, updated_slot, n=node: self._save_type_slot(
                        n,
                        original_name,
                        updated_slot,
                    )
                )
                self._insert(row)
            return

        # No slot selected — show type-level properties.
        section, section_layout = _mk_section("Type Properties", self)
        self._insert(section)
        ic_row = _EditableRow("instance_category", tv.category or "",
                              tooltip=_META_TOOLTIPS["instance_category"])
        ic_row.committed.connect(
            lambda v, n=node: self._save_instance_category(n, v))
        self._insert_section_row(section_layout, ic_row)
        self._insert_section_row(
            section_layout, self._make_type_display_color_row(node))
        self._insert_section_row(section_layout, _ReadonlyRow(
            "slot_count", str(len(tv.slots))))
        self._insert_section_row(section_layout, self._make_extends_row(node))

    def _make_type_display_color_row(self, node: Node) -> QWidget:
        row_widget = QWidget(self)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        label = make_field_label("display_color", self)
        label.setFixedWidth(_KEY_WIDTH)
        label.setToolTip(
            "Enable override to persist a custom display color for this Type. "
            "Disable to use deterministic seeded color from Type id."
        )
        row_layout.addWidget(label)

        color_field = QColorField(
            default_value=Color.from_hex("#4a708f"),
            show_alpha=False,
            use_compact_picker_dialog=True,
            parent=row_widget,
        )
        override = QFieldOverrideWrapper(
            color_field,
            overridden=normalize_display_color(node.display_color) is not None,
            parent=row_widget,
        )
        override.setObjectName("type_display_color_override")
        override.set_override_tooltip(
            "Enable override to persist a custom display color for this Type. "
            "Disable to use deterministic seeded color from Type id."
        )
        color_field.set_value(Color.from_hex(
            effective_node_display_color(node)))

        override.override_changed.connect(
            lambda enabled, n=node, wrapped=override: self._save_type_display_color(
                n,
                wrapped,
                enabled,
            )
        )
        override.committed.connect(
            lambda _value, n=node, wrapped=override: self._save_type_display_color(
                n,
                wrapped,
                wrapped.is_overridden(),
            )
        )

        row_layout.addWidget(override, 1)
        return row_widget

    # ------------------------------------------------------------------
    # Extends-edge helpers (type editor)
    # ------------------------------------------------------------------

    def _make_extends_row(self, node: Node) -> QWidget:
        """Build the 'extends (parent type)' picker row for a type node."""
        from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID

        repo = self._session._io.repository  # noqa: SLF001
        links = repo.list_links()
        parent_id: str | None = next(
            (lk.target_node_id for lk in links
             if lk.link_type_id == EXTENDS_LINK_TYPE_ID and lk.source_node_id == str(node.id)),
            None,
        )
        parent_name = "(none)"
        if parent_id is not None:
            try:
                parent_node = self._session.get_node(parent_id)
                parent_name = parent_node.name or parent_id
            except KeyError:
                parent_name = f"(missing: {parent_id[:8]})"

        row_widget = QWidget(self)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        label = make_field_label("extends", self)
        label.setFixedWidth(_KEY_WIDTH)
        row_layout.addWidget(label)

        parent_label = QLabel(parent_name, self)
        parent_label.setStyleSheet(f"color: {FIELD_INPUT_TEXT};")
        row_layout.addWidget(parent_label, stretch=1)

        pick_btn = _mk_btn("Pick", "Select a parent type to extend")
        pick_btn.clicked.connect(lambda: self._pick_extends_parent(node))
        row_layout.addWidget(pick_btn)

        clear_btn = _mk_btn("Clear", "Remove the parent type link")
        clear_btn.setEnabled(parent_id is not None)
        clear_btn.clicked.connect(lambda: self._clear_extends_parent(node))
        row_layout.addWidget(clear_btn)

        return row_widget

    def _pick_extends_parent(self, node: Node) -> None:
        """Open a type picker and set the extends edge to the chosen parent."""
        from lks_utils.knowledge.links.link_instance import LinkInstance
        from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID

        repo = self._session._io.repository  # noqa: SLF001
        links = repo.list_links()
        current_parent_id: str | None = next(
            (lk.target_node_id for lk in links
             if lk.link_type_id == EXTENDS_LINK_TYPE_ID and lk.source_node_id == str(node.id)),
            None,
        )
        dialog = QKnowledgeTypePickerDialog(
            list(self._session.iter_types()),
            selected_type_id=current_parent_id,
            exclude_type_ids={str(node.id)},
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        parent_id = dialog.selected_node_id()
        if parent_id is None or parent_id == str(node.id):
            return
        if parent_id == current_parent_id:
            return

        source_id = str(node.id)

        def _set_extends_parent(repo_mut) -> set[str]:  # noqa: ANN001
            touched: set[str] = {source_id, parent_id}
            for link in list(repo_mut.list_links()):
                if (
                    str(link.link_type_id) == EXTENDS_LINK_TYPE_ID
                    and str(link.source_node_id) == source_id
                ):
                    repo_mut.delete_link(str(link.id))
                    touched.add(str(link.id))
            new_edge = LinkInstance(
                link_type_id=EXTENDS_LINK_TYPE_ID,
                source_node_id=source_id,
                target_node_id=parent_id,
            )
            repo_mut.upsert_link(new_edge)
            touched.add(str(new_edge.id))
            return touched

        result = self._session.apply_mutation(
            "set_extends_parent",
            _set_extends_parent,
        )
        if not result.ok:
            QMessageBox.warning(
                self,
                "Extends Update Failed",
                result.save_error or "Unable to set extends link.",
            )
            return
        self.set_node(node)

    def _clear_extends_parent(self, node: Node) -> None:
        """Remove the extends edge from this type node."""
        from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID

        source_id = str(node.id)

        def _clear_extends_parent(repo_mut) -> set[str]:  # noqa: ANN001
            touched: set[str] = {source_id}
            for link in list(repo_mut.list_links()):
                if (
                    str(link.link_type_id) == EXTENDS_LINK_TYPE_ID
                    and str(link.source_node_id) == source_id
                ):
                    repo_mut.delete_link(str(link.id))
                    touched.add(str(link.id))
            return touched

        result = self._session.apply_mutation(
            "clear_extends_parent",
            _clear_extends_parent,
        )
        if not result.ok:
            QMessageBox.warning(
                self,
                "Extends Update Failed",
                result.save_error or "Unable to clear extends link.",
            )
            return
        self.set_node(node)

    def _add_instance_rows(self, node: Node) -> None:
        slots: dict[str, NodeSlot] = _collect_inherited_slots(
            self._session, node)
        provenance = _collect_inherited_slot_provenance(self._session, node)

        props = {
            key: value
            for key, value in node.props.items()
            if key != "slots" and key not in RESERVED_VALIDATION_PROP_NAMES
        }
        validator = InstanceValidator(self._session._io.repository)  # noqa: SLF001
        version_issues = validator.version_issues(node)
        validation_errors: dict[str, str] = {}
        validation_status: str | None = None
        persisted_status = node.props.get(VALIDATION_STATUS_PROP)
        raw_persisted_errors = node.props.get(VALIDATION_ERRORS_PROP)
        try:
            validator.validate_node(node)
            if isinstance(persisted_status, str) and persisted_status:
                if isinstance(raw_persisted_errors, dict):
                    persisted_ref_errors: dict[str, str] = {}
                    for key, value in raw_persisted_errors.items():
                        if not (isinstance(key, str) and isinstance(value, str)):
                            continue
                        prop_value = node.props.get(key)
                        has_ref_shape = self._extract_ref_target_id(
                            prop_value) is not None
                        if not has_ref_shape and isinstance(prop_value, list):
                            has_ref_shape = any(
                                self._extract_ref_target_id(item) is not None
                                for item in prop_value
                            )
                        if has_ref_shape:
                            persisted_ref_errors[key] = value
                    if persisted_ref_errors:
                        validation_status = persisted_status
                        validation_errors = persisted_ref_errors
                elif VALIDATION_ERRORS_PROP not in node.props:
                    validation_status = persisted_status
        except ValueError as exc:
            validation_status = VALIDATION_STATUS_CANNOT_COMPILE
            if isinstance(raw_persisted_errors, dict):
                validation_errors = {
                    key: value
                    for key, value in raw_persisted_errors.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            if not validation_errors:
                validation_errors = {"node": str(exc)}
        visible_props: dict[str, object] = dict(props)
        repository = self._session._io.repository  # noqa: SLF001
        node_id = str(node.id)

        # Rehydrate reference slots from slot_ref link assets.
        for slot_name, slot in slots.items():
            if not slot.effective_value_mode().allows_reference:
                continue
            is_list = slot.effective_value_mode().allows_list
            synthesized = self._normalize_slot_ref_value(
                repository,
                node_id,
                slot_name,
                is_list,
            )
            if synthesized is not None:
                visible_props[slot_name] = synthesized

        if props or slots:
            title = "Selected Value" if self._selected_slot_name else "Root Properties"
            main_section, main_layout = _mk_section(title, self)
            self._insert(main_section)
        else:
            main_layout = None

        ordered_property_names = _ordered_property_names(visible_props, slots)

        for key in ordered_property_names:
            if self._selected_slot_name is not None and key != self._selected_slot_name:
                continue
            slot = slots.get(key)
            if key not in visible_props:
                if slot is None:
                    continue
                if slot.effective_value_mode().allows_reference:
                    ref_row = _RefRow(
                        key,
                        None,
                        "(empty ref)",
                        None,
                        self._session,
                        can_create_inline=False,
                    )
                    ref_row.pick_requested.connect(
                        lambda sn, n=node: self._pick_ref(n, sn))
                    ref_row.clear_requested.connect(
                        lambda sn, n=node: self._clear_ref(n, sn))
                    if main_layout is not None:
                        self._insert_section_row(main_layout, ref_row)
                    continue

                inherited_value = slot.default_value()
                owner = provenance.get(key)
                tooltip = (
                    f"Inherited from {owner}. Enable override to set a local value."
                    if owner
                    else "Inherited value. Enable override to set a local value."
                )
                lit_row = _EditableRow(
                    key,
                    inherited_value,
                    value_type=slot.value_type,
                    tooltip=tooltip,
                )
                lit_row.committed.connect(
                    lambda v, k=key, s=slot, n=node: self._save_prop(n, k, v, s))
                wrapped_row = QFieldOverrideWrapper(
                    lit_row, overridden=False, parent=self)
                wrapped_row.setObjectName(f"prop_override_{key}")
                wrapped_row.set_override_tooltip(tooltip)
                wrapped_row.override_changed.connect(
                    lambda enabled, n=node, k=key, s=slot, dv=inherited_value: self._toggle_inherited_override(
                        n,
                        k,
                        s,
                        dv,
                        enabled,
                    )
                )
                if main_layout is not None:
                    self._insert_section_row(main_layout, wrapped_row)
                continue

            value = visible_props[key]
            is_ref = False
            if slot is not None and slot.effective_value_mode().allows_reference:
                if value is None:
                    is_ref = True
                elif isinstance(value, str):
                    is_ref = True
                elif isinstance(value, list):
                    is_ref = True
            if is_ref:
                ref_id = self._extract_ref_target_id(value)
                if ref_id is not None:
                    try:
                        ref_node: Node | None = self._session.get_node(
                            ref_id)
                        ref_display = f"→ {ref_node.name}  ({ref_id})"
                    except KeyError:
                        ref_node = None
                        ref_display = f"→ (missing)  ({ref_id})"
                else:
                    ref_id = None
                    ref_node = None
                    ref_display = "(empty ref)"
                ref_row = _RefRow(
                    key,
                    ref_id,
                    ref_display,
                    ref_node,
                    self._session,
                    can_create_inline=False,
                )
                ref_row.pick_requested.connect(
                    lambda sn, n=node: self._pick_ref(n, sn))
                ref_row.clear_requested.connect(
                    lambda sn, n=node: self._clear_ref(n, sn))
                if main_layout is not None:
                    self._insert_section_row(main_layout, ref_row)
            else:
                display = value if value is not None else ""
                value_type = slot.value_type if slot is not None else "string"
                promotable_type = self._promotable_type_node(slot)
                if isinstance(value, dict) and (_is_inline_structured(value) or promotable_type is not None):
                    lit_row = _InlineTreeRow(
                        key,
                        value,
                        self,
                        can_promote=promotable_type is not None,
                    )
                    lit_row.leaf_committed.connect(
                        lambda slot_name, path, text, n=node: self._update_nested_prop(
                            n,
                            slot_name,
                            path,
                            text,
                        )
                    )
                    lit_row.clear_requested.connect(
                        lambda slot_name, n=node: self._clear_nested_prop(
                            n, slot_name)
                    )
                    lit_row.promote_requested.connect(
                        lambda slot_name, n=node: self._promote_inline_literal(
                            n, slot_name)
                    )
                else:
                    lit_row = _EditableRow(key, display, value_type=value_type)
                    lit_row.committed.connect(
                        lambda v, k=key, s=slot, n=node: self._save_prop(n, k, v, s))
                if main_layout is not None:
                    if slot is None:
                        self._insert_section_row(main_layout, lit_row)
                    else:
                        owner = provenance.get(key)
                        tooltip = (
                            f"Inherited from {owner}. Disable override to resume inheritance."
                            if owner
                            else "Inherited slot value. Disable override to resume inheritance."
                        )
                        wrapped_row = QFieldOverrideWrapper(
                            lit_row, overridden=True, parent=self)
                        wrapped_row.setObjectName(f"prop_override_{key}")
                        wrapped_row.set_override_tooltip(tooltip)
                        wrapped_row.override_changed.connect(
                            lambda enabled, n=node, k=key, s=slot, dv=slot.default_value(): self._toggle_inherited_override(
                                n,
                                k,
                                s,
                                dv,
                                enabled,
                            )
                        )
                        self._insert_section_row(main_layout, wrapped_row)

        if validation_status or validation_errors:
            visible_errors = {
                key: value
                for key, value in validation_errors.items()
                if self._selected_slot_name is None or key == self._selected_slot_name
            }
            if validation_status or visible_errors:
                validation_section, validation_layout = _mk_section(
                    "Validation", self)
                self._insert(validation_section)
            else:
                validation_layout = None
            if isinstance(validation_status, str) and validation_status:
                if validation_layout is not None:
                    self._insert_section_row(
                        validation_layout, _ReadonlyRow("status", validation_status))
            for key, value in visible_errors.items():
                if not (isinstance(key, str) and isinstance(value, str)):
                    continue
                if key in props:
                    slot = slots.get(key)
                    row = _ValidationRecoveryRow(
                        key,
                        value,
                        supports_reference=bool(slot is not None and (
                            slot.effective_value_mode().allows_reference)),
                        supports_inline=False,
                    )
                    row.discard_requested.connect(
                        lambda slot_name, n=node: self._discard_invalid_prop(
                            n, slot_name)
                    )
                    row.pick_ref_requested.connect(
                        lambda slot_name, n=node: self._pick_ref(n, slot_name)
                    )
                    row.convert_inline_requested.connect(
                        lambda slot_name, n=node: self._convert_invalid_to_inline(
                            n, slot_name)
                    )
                    if validation_layout is not None:
                        self._insert_section_row(validation_layout, row)
                else:
                    if validation_layout is not None:
                        self._insert_section_row(
                            validation_layout, _ReadonlyRow(key, value))

        type_version = node.props.get(TYPE_VERSION_PROP)
        property_versions = node.props.get(PROPERTY_VERSIONS_PROP)
        if isinstance(type_version, int) or isinstance(property_versions, dict) or version_issues:
            version_section, version_layout = _mk_section(
                "Version", self, expanded=False)
            self._insert(version_section)
            if isinstance(type_version, int):
                self._insert_section_row(version_layout, _ReadonlyRow(
                    "type_snapshot", str(type_version)))
            if isinstance(property_versions, dict) and property_versions:
                self._insert_section_row(version_layout, _ReadonlyRow(
                    "property_snapshots",
                    self._format_compact_value(property_versions),
                ))
            for key, value in version_issues.items():
                self._insert_section_row(
                    version_layout, _ReadonlyRow(key, value))

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def _save_field(self, node: Node, field: str, value: str) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        if field == "category":
            validation = validate_node_category_transition(
                current_category=node.category,
                proposed_category=str(value),
            )
            if not validation.allowed:
                QMessageBox.warning(
                    self,
                    "Reserved Category",
                    validation.message,
                )
                self._rebuild()
                return
        selected_slot_snapshot = self._selected_slot_name
        updated = node.model_copy(
            update={field: str(value), "rev": node.rev + 1})
        updated = self._apply_replacement_update(
            node,
            updated,
            dirty_reason=f"inspector field updated: {field}",
        )
        self._selected_slot_name = selected_slot_snapshot
        self._current_node = updated
        self._header.setText(f"Inspector — {updated.name}")
        self._rebuild(full_layout_sync=False)
        self.node_mutated.emit(str(node.id))

    def _save_instance_category(self, node: Node, value: str) -> None:
        if not is_type(node):
            return
        clean_value = str(value).strip()
        validation = validate_instance_category_value(clean_value)
        if not validation.allowed:
            QMessageBox.warning(
                self,
                "Reserved Category Name",
                validation.message + "\nChoose a different name.",
            )
            self._rebuild()
            return
        props = dict(node.props)
        props["instance_category"] = clean_value
        updated = node.model_copy(update={"props": props, "rev": node.rev + 1})
        updated = self._apply_replacement_update(
            node,
            updated,
            dirty_reason="inspector instance category updated",
        )
        self._current_node = updated
        self.node_mutated.emit(str(node.id))

    def _save_type_display_color(self, node: Node, wrapped: QFieldOverrideWrapper, enabled: bool) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        if not is_type(node):
            return

        selected_slot_snapshot = self._selected_slot_name
        update_payload: dict[str, object] = {"rev": node.rev + 1}
        if enabled:
            normalized = normalize_display_color(wrapped.value())
            update_payload["display_color"] = normalized
        else:
            update_payload["display_color"] = None

        updated = node.model_copy(update=update_payload)
        updated = self._apply_replacement_update(
            node,
            updated,
            dirty_reason="inspector type display color updated",
        )
        self._selected_slot_name = selected_slot_snapshot
        self._current_node = updated
        self._header.setText(f"Inspector — {updated.name}")
        self._rebuild(full_layout_sync=False)
        self.node_mutated.emit(str(node.id))

    def _save_type_slot(self, node: Node, original_name: str, updated_slot: NodeSlot) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        # Keep focus on the edited contract, including rename operations.
        selected_slot_snapshot = updated_slot.name
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector type slot updated: {updated_slot.name}",
                mutate=lambda mutator, node_id: mutator.update_slot(
                    node_id, original_name, updated_slot
                ),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Contract", str(exc))
            return
        self._selected_slot_name = selected_slot_snapshot
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _save_prop(self, node: Node, key: str, value: object, slot: NodeSlot | None = None) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        selected_slot_snapshot = self._selected_slot_name
        parsed_value = value
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector property updated: {key}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, key, parsed_value),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self._selected_slot_name = selected_slot_snapshot
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _toggle_inherited_override(
        self,
        node: Node,
        slot_name: str,
        slot: NodeSlot,
        default_value: object,
        enabled: bool,
    ) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        selected_slot_snapshot = self._selected_slot_name
        try:
            if enabled:
                updated = self._apply_mutator_update(
                    node,
                    dirty_reason=f"inspector inherited override enabled: {slot_name}",
                    mutate=lambda mutator, node_id: mutator.set_local_instance_override(
                        node_id,
                        slot_name,
                        default_value,
                    ),
                )
            else:
                updated = self._apply_mutator_update(
                    node,
                    dirty_reason=f"inspector inherited override cleared: {slot_name}",
                    mutate=lambda mutator, node_id: mutator.clear_local_instance_override(
                        node_id, slot_name
                    ),
                )
        except (KeyError, ValueError):
            self._rebuild()
            return
        self._selected_slot_name = selected_slot_snapshot
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _slot_for_node(self, node: Node, slot_name: str):
        return _collect_inherited_slots(self._session, node).get(slot_name)

    def _ref_type_for_slot(self, slot: NodeSlot | None) -> str | None:
        if slot is None:
            return None
        return slot.target_type or slot.ref_type or slot.value_type

    def _add_ref_list_item(self, node: Node, slot_name: str) -> None:
        slot = self._slot_for_node(node, slot_name)
        dialog = QKnowledgeRefPickerDialog(
            self._session,
            ref_type=self._ref_type_for_slot(slot),
            slot_name=slot_name,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        selected_id = dialog.selected_node_id()
        if not selected_id:
            return
        current_value = self._normalize_slot_ref_value(
            self._session._io.repository,  # noqa: SLF001
            str(node.id),
            slot_name,
            is_list=True,
        )
        current_list = list(current_value) if isinstance(
            current_value, list) else []
        current_list.append(selected_id)
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector ref list appended: {slot_name}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, slot_name, current_list),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _remove_ref_list_item(self, node: Node, slot_name: str, index: int) -> None:
        current_value = self._normalize_slot_ref_value(
            self._session._io.repository,  # noqa: SLF001
            str(node.id),
            slot_name,
            is_list=True,
        )
        if not isinstance(current_value, list) or index < 0 or index >= len(current_value):
            return
        updated = list(current_value)
        updated.pop(index)
        try:
            new_node = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector ref list removed: {slot_name}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, slot_name, updated),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = new_node
        self._rebuild(full_layout_sync=False)

    def _move_ref_list_item(self, node: Node, slot_name: str, index: int, delta: int) -> None:
        current_value = self._normalize_slot_ref_value(
            self._session._io.repository,  # noqa: SLF001
            str(node.id),
            slot_name,
            is_list=True,
        )
        if not isinstance(current_value, list):
            return
        target = index + delta
        if index < 0 or index >= len(current_value) or target < 0 or target >= len(current_value):
            return
        updated = list(current_value)
        updated[index], updated[target] = updated[target], updated[index]
        try:
            new_node = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector ref list reordered: {slot_name}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, slot_name, updated),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = new_node
        self._rebuild(full_layout_sync=False)

    def _save_flexible_prop(
        self,
        node: Node,
        key: str,
        value: str,
        slot: object | None,
    ) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        parsed = self._parse_flexible_value(value, slot)
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector flexible property updated: {key}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, key, parsed),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _pick_ref(self, node: Node, slot_name: str) -> None:
        slot = self._slot_for_node(node, slot_name)
        dialog = QKnowledgeRefPickerDialog(
            self._session,
            ref_type=self._ref_type_for_slot(slot),
            slot_name=slot_name,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        selected_id = dialog.selected_node_id()
        if not selected_id:
            return
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector reference picked: {slot_name}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id,
                    slot_name,
                    selected_id,
                ),
            )
        except KeyError:
            # Node was deleted or is no longer in repository
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _clear_ref(self, node: Node, slot_name: str) -> None:
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector reference cleared: {slot_name}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, slot_name, None),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _create_inline_value(self, node: Node, slot_name: str) -> None:
        slot = self._slot_for_node(node, slot_name)
        inline_value = self._default_inline_value_for_slot(slot)
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector inline value created: {slot_name}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, slot_name, inline_value),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _update_nested_prop(self, node: Node, slot_name: str, path: str, value: str) -> None:
        """Update a nested value at dot-path within a structured property."""
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        try:
            current_node = self._node_for_edit(str(node.id))
        except KeyError:
            return
        root_value = current_node.props.get(slot_name)
        if not isinstance(root_value, (dict, list)):
            return
        # Deep copy the root value to avoid mutation
        import copy
        updated_root = copy.deepcopy(root_value)
        # Parse path and navigate to update the leaf
        # Path format: "key1.key2.3.key4" for nested dicts/lists
        parts = path.split(".")
        current = updated_root
        for part in parts[:-1]:
            if isinstance(current, dict):
                if part not in current:
                    current[part] = {}
                current = current[part]
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    if idx >= len(current):
                        current.append({})
                    current = current[idx]
                except (ValueError, IndexError):
                    return
            else:
                return
        # Set the leaf value
        last_part = parts[-1]
        if isinstance(current, dict):
            current[last_part] = value
        elif isinstance(current, list):
            try:
                idx = int(last_part)
                if idx < len(current):
                    current[idx] = value
            except ValueError:
                pass
        # Save the updated root value
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector nested property updated: {slot_name}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, slot_name, updated_root),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild()

    def _clear_nested_prop(self, node: Node, slot_name: str) -> None:
        """Clear a nested structured property."""
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        node_id = str(node.id)
        try:
            def _clear_slot_mutation(repo: Repository) -> set[str]:
                before_link_ids = self._slot_ref_link_ids_for_node(
                    repo, node_id)
                Mutator(repo).discard_slot_value(node_id, slot_name)
                after_link_ids = self._slot_ref_link_ids_for_node(
                    repo, node_id)
                return {node_id, *before_link_ids, *after_link_ids}

            result = self._session.apply_mutation(
                "inspector_clear_nested_prop",
                _clear_slot_mutation,
                validation_mode="touched_only",
            )
            if not result.ok:
                if result.save_error and "Node not found" in result.save_error:
                    raise KeyError(node_id)
                raise ValueError(
                    result.save_error or "Failed to clear slot value")
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self._emit_mutation_payload(result.touched_ids)
        updated = self._session.get_node(node_id)
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _promote_inline_literal(self, node: Node, slot_name: str) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return

        new_node_id: str | None = None

        def _mutate(repository: Repository) -> set[str]:
            nonlocal new_node_id
            before_link_ids = self._slot_ref_link_ids_for_node(
                repository, str(node.id))
            new_node_id = promote_inline_literal(
                repository, str(node.id), (slot_name,))
            after_link_ids = self._slot_ref_link_ids_for_node(
                repository, str(node.id))
            return {str(node.id), str(new_node_id), *before_link_ids, *after_link_ids}

        try:
            result = self._session.apply_mutation(
                "inspector_promote_inline_literal",
                _mutate,
                validation_mode="touched_only",
            )
            if not result.ok:
                raise ValueError(
                    result.save_error or "Promote operation failed")
            self._emit_mutation_payload(result.touched_ids)
        except (KeyError, ValueError) as exc:
            QMessageBox.warning(self, "Promote Failed", str(exc))
            return

        self.node_mutated.emit(str(node.id))
        self._current_node = self._session.get_node(str(node.id))
        self._rebuild(full_layout_sync=False)
        if new_node_id is not None:
            self.node_selection_requested.emit(new_node_id)

    def _discard_invalid_prop(self, node: Node, slot_name: str) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        updated = self._apply_mutator_update(
            node,
            dirty_reason=f"inspector invalid property discarded: {slot_name}",
            mutate=lambda mutator, node_id: mutator.discard_slot_value(
                node_id, slot_name),
        )
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def _convert_invalid_to_inline(self, node: Node, slot_name: str) -> None:
        if self._current_node is None or str(node.id) != str(self._current_node.id):
            return
        try:
            current_node = self._node_for_edit(str(node.id))
        except KeyError:
            return
        current_value = current_node.props.get(slot_name)
        inline_value: object
        if isinstance(current_value, str):
            inline_value = {"from_ref": current_value}
        elif isinstance(current_value, (dict, list)):
            inline_value = current_value
        elif isinstance(current_value, str):
            parsed = self._parse_flexible_value(current_value, None)
            inline_value = parsed if isinstance(parsed, (dict, list)) else {
                "value": current_value}
        elif current_value is None:
            inline_value = {}
        else:
            inline_value = {"value": current_value}
        try:
            updated = self._apply_mutator_update(
                node,
                dirty_reason=f"inspector invalid property converted inline: {slot_name}",
                mutate=lambda mutator, node_id: mutator.set_slot_value(
                    node_id, slot_name, inline_value),
            )
        except KeyError:
            QMessageBox.warning(
                self,
                "Node Not Found",
                f"The node {node.id} is no longer in the repository.\n"
                "It may have been deleted by another operation.",
            )
            self._rebuild()
            return
        self.node_mutated.emit(str(node.id))
        self._current_node = updated
        self._rebuild(full_layout_sync=False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        from PySide6.QtWidgets import QApplication, QLineEdit
        bindings = get_default_bindings()
        seq = QKeySequence(int(event.modifiers().value)
                           | int(event.key())).toString()
        if bindings.matches_key(FIELD_PICK_REF.id, seq):
            slot_name = self._active_ref_slot_name()
            if slot_name is not None and self._current_node is not None:
                self._pick_ref(self._current_node, slot_name)
                event.accept()
                return
        if bindings.matches_key(FIELD_CLEAR_REF.id, seq):
            # Only clear if not inside a text edit so Delete still works normally
            focused = QApplication.instance().focusWidget()
            if not isinstance(focused, QLineEdit):
                slot_name = self._active_ref_slot_name()
                if slot_name is not None and self._current_node is not None:
                    self._clear_ref(self._current_node, slot_name)
                    event.accept()
                    return
        super().keyPressEvent(event)

    def _active_ref_slot_name(self) -> str | None:
        """Return the slot name of the currently focused ref row, or None."""
        from PySide6.QtWidgets import QApplication
        focused = QApplication.instance().focusWidget()
        if focused is None:
            return None
        w: QWidget | None = focused
        while w is not None and w is not self:
            name = w.objectName()
            for prefix in ("ref_row_", "ref_or_value_row_", "ref_list_row_"):
                if name.startswith(prefix):
                    return name[len(prefix):]
            w = w.parentWidget()
        return None

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {FIELD_INPUT_TEXT};"
            f" font-family: '{FIELD_MONO_FONT_FAMILY}'; }}"
            f"QLabel {{ min-height: {FIELD_ROW_HEIGHT}px; max-height: {FIELD_ROW_HEIGHT}px; }}"
            f"QPushButton {{ min-height: {FIELD_ROW_HEIGHT}px; max-height: {FIELD_ROW_HEIGHT}px; }}"
            "QScrollArea { border: none; }"
        )

    def _parse_flexible_value(self, raw: str, slot: object | None) -> object:
        text = raw.strip()
        if not text:
            return None
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return raw
        return raw

    def _format_ref_list_entries(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        entries: list[str] = []
        for index, item in enumerate(value, start=1):
            ref_id = self._extract_ref_target_id(item)
            if ref_id is not None:
                try:
                    ref_node = self._session.get_node(ref_id)
                    entries.append(f"{index}. → {ref_node.name}  ({ref_id})")
                except KeyError:
                    entries.append(f"{index}. → (missing)  ({ref_id})")
            else:
                entries.append(
                    f"{index}. malformed: {self._format_compact_value(item)}")
        return entries

    def _format_compact_value(self, value: object) -> str:
        if value is None:
            return "(none)"
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False, sort_keys=True)
            except Exception:
                return str(value)
        return str(value)


QKnowledgePropertiesPanel = QKnowledgeInspectorPanel


__all__ = ["QKnowledgeInspectorPanel", "QKnowledgePropertiesPanel"]

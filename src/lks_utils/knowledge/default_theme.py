"""Default visual tokens for knowledge UI prototypes."""
from __future__ import annotations

import hashlib

from lks_utils.gui_qt.theme.palette import PALETTE

DEFAULT_COLORS: dict[str, str] = {
    "scene.background": PALETTE["canvas_bg"],
    "scene.edge": PALETTE["minimap_painted_outline"],
    "node.fill": PALETTE["layer_row_bg_alt"],
    "node.stroke": PALETTE["minimap_painted_outline"],
    "node.selected_stroke": "#f5c518",  # yellow — distinct selection indicator
    # pale white — top layer overlay for active selection
    "node.active_selected_stroke": "#f0f0f0",
    "node.text": PALETTE["selection_marquee"],
    "node.immutable_text": "#9aa7b7",
    "root.header_bg": PALETTE["layer_row_bg"],
    "root.header_stroke": PALETTE["minimap_painted_outline"],
    "root.label": "#88b8f0",
    "field.row_bg": "#1f1f1f",
    "field.row_border": "#3a3a3a",
    "field.input_bg": "#1a1a1a",
    "field.input_text": PALETTE["selection_marquee"],
    "field.input_border": PALETTE["minimap_painted_outline"],
    "field.input_focus_border": "#6fa8dc",
    "field.label": "#7a9cbf",
    "field.button_bg": "#101010",
    "field.button_text": "#ffffff",
    "field.button_border": "#6a6a6a",
    "field.button_hover_border": "#8faed0",
    "field.button_pressed_bg": "#0a0a0a",
    "field.button_pressed_border": "#3f3f3f",
    "field.button_disabled_text": "#777777",
    "field.button_disabled_border": "#444444",
    "save.hint_color": PALETTE["pin_marker"],
    "save.hint_border": PALETTE["pin_marker"],
    "field.checkbox_text": "#f1f6ff",
    "field.mono_font_family": "Consolas",
    "section.label": "#5a7a9a",
    "section.contract_frame_bg": "#141414",
    "section.contract_frame_border": "#5a7a9a",
    "section.contract_header_bg": "#171717",
    "section.contract_title": "#9bc8f0",
    "section.contract_toggle": "#d9e8ff",
    "validation.error_stripe": PALETTE["canvas2d_grid_axis_x"],
    "validation.warning_label": "#d9ad6b",
    "validation.error_text": "#f0cccc",
    "ref.pill_bg": PALETTE["selection_marquee"],
    "ref.pill_text": PALETTE["selection_marquee_alt"],
    "ref.valid": "#9bc8f0",
    "ref.missing": "#e74c3c",
    "ref.mismatch": "#f39c12",
    "ref.malformed": "#e67e22",
    "ref.subpanel_bg": "#141e28",
    "ref.subpanel_border": "#2a4060",
    "collapse.arrow": "#ffffff",  # white — matches text; dark theme default
    "adhoc.stub.outgoing": "#7fb7ff",
    "adhoc.stub.incoming": "#f0b46a",
    "adhoc.stub.text": "#9fb2c8",
    "adhoc.panel.section_label": "#9fb2c8",
    "adhoc.panel.out_of_graph_label": "#8ea4bb",
    "adhoc.panel.chip_border": "#4f6278",
    # Graph node card canvas primitives.
    "node.header_bg": PALETTE["layer_row_bg"],
    "node.header_sep": PALETTE["minimap_painted_outline"],
    "node.subtitle_text": "#b8bec7",
    "node.clear_btn_stroke": "#d75d6a",
    "node.rows_panel_border": PALETTE["minimap_painted_outline"],
    "node.rows_panel_bg": PALETTE["canvas_bg"],
    "node.type_text": "#a8afb8",
    "node.row_sep": PALETTE["dot_grid_strong"],
    "node.scrollbar_track": PALETTE["layer_row_bg_alt"],
    "node.scrollbar_thumb": PALETTE["canvas_border"],
    "node.ref_value_text": "#9bc8f0",
    "node.literal_value_text": "#e0c36f",
    "link.slot_ref": "#9bc8f0",
    "link.extends": "#b39ddb",
    "link.instance_of": "#86c7a8",
    "git.untracked": "#5cb85c",  # green
    "git.modified": "#f0ad4e",  # yellow
    "git.deleted": "#d9534f",  # red
}


def color(name: str) -> str:
    """Return a named Knowledge UI color token."""
    return DEFAULT_COLORS[name]


def colors() -> dict[str, str]:
    """Return a copy of the Knowledge UI default color map."""
    return dict(DEFAULT_COLORS)


NODE_FILL_COLOR: str = color("node.fill")
NODE_STROKE_COLOR: str = color("node.stroke")
NODE_SELECTED_STROKE_COLOR: str = color("node.selected_stroke")
NODE_ACTIVE_SELECTED_STROKE_COLOR: str = color("node.active_selected_stroke")
NODE_TEXT_COLOR: str = color("node.text")
EDGE_COLOR: str = color("scene.edge")
SCENE_BACKGROUND_COLOR: str = color("scene.background")

FIELD_ROW_BG: str = color("field.row_bg")
FIELD_ROW_BORDER: str = color("field.row_border")
FIELD_INPUT_BG: str = color("field.input_bg")
FIELD_INPUT_TEXT: str = color("field.input_text")
FIELD_INPUT_BORDER: str = color("field.input_border")
FIELD_INPUT_FOCUS_BORDER: str = color("field.input_focus_border")
FIELD_LABEL_COLOR: str = color("field.label")
FIELD_BUTTON_BG: str = color("field.button_bg")
FIELD_BUTTON_TEXT: str = color("field.button_text")
FIELD_BUTTON_BORDER: str = color("field.button_border")
FIELD_BUTTON_HOVER_BORDER: str = color("field.button_hover_border")
FIELD_BUTTON_PRESSED_BG: str = color("field.button_pressed_bg")
FIELD_BUTTON_PRESSED_BORDER: str = color(
    "field.button_pressed_border")
FIELD_BUTTON_DISABLED_TEXT: str = color("field.button_disabled_text")
FIELD_BUTTON_DISABLED_BORDER: str = color(
    "field.button_disabled_border")
SAVE_HINT_COLOR: str = color("save.hint_color")
SAVE_HINT_BORDER: str = color("save.hint_border")
FIELD_CHECKBOX_TEXT: str = color("field.checkbox_text")
FIELD_MONO_FONT_FAMILY: str = color("field.mono_font_family")

SECTION_LABEL_COLOR: str = color("section.label")
CONTRACT_FRAME_BG: str = color("section.contract_frame_bg")
CONTRACT_FRAME_BORDER: str = color("section.contract_frame_border")
CONTRACT_HEADER_BG: str = color("section.contract_header_bg")
CONTRACT_TITLE_COLOR: str = color("section.contract_title")
CONTRACT_TOGGLE_COLOR: str = color("section.contract_toggle")

REF_PILL_BG: str = color("ref.pill_bg")
REF_PILL_TEXT: str = color("ref.pill_text")
REF_VALID_COLOR: str = color("ref.valid")
REF_MISSING_COLOR: str = color("ref.missing")
REF_MISMATCH_COLOR: str = color("ref.mismatch")
REF_MALFORMED_COLOR: str = color("ref.malformed")
REF_SUBPANEL_BG: str = color("ref.subpanel_bg")
REF_SUBPANEL_BORDER: str = color("ref.subpanel_border")
COLLAPSE_ARROW_COLOR: str = color("collapse.arrow")
LIBRARY_TREE_INDENT_PX: int = 10
ADHOC_STUB_OUTGOING_COLOR: str = color("adhoc.stub.outgoing")
ADHOC_STUB_INCOMING_COLOR: str = color("adhoc.stub.incoming")
ADHOC_STUB_TEXT_COLOR: str = color("adhoc.stub.text")
ADHOC_PANEL_SECTION_LABEL_COLOR: str = color("adhoc.panel.section_label")
ADHOC_PANEL_OUT_OF_GRAPH_LABEL_COLOR: str = color(
    "adhoc.panel.out_of_graph_label")
ADHOC_PANEL_CHIP_BORDER_COLOR: str = color("adhoc.panel.chip_border")
VALIDATION_ERROR_STRIPE: str = color("validation.error_stripe")
VALIDATION_WARNING_LABEL: str = color("validation.warning_label")
VALIDATION_ERROR_TEXT: str = color("validation.error_text")

GIT_UNTRACKED_COLOR: str = color("git.untracked")
GIT_MODIFIED_COLOR: str = color("git.modified")
GIT_DELETED_COLOR: str = color("git.deleted")

NODE_WIDTH_PX: int = 176
NODE_HEIGHT_PX: int = 84
SCENE_SCALE_PX: int = 320
SCENE_PADDING_PX: int = 120

# Root-card visual tokens (the card representing the node being edited).
ROOT_HEADER_BG: str = color("root.header_bg")
ROOT_HEADER_STROKE: str = color("root.header_stroke")
ROOT_LABEL_COLOR: str = color("root.label")
IMMUTABLE_FIELD_TEXT: str = color("node.immutable_text")

# Graph node card canvas primitives.
NODE_HEADER_BG: str = color("node.header_bg")
NODE_HEADER_SEP: str = color("node.header_sep")
NODE_SUBTITLE_TEXT: str = color("node.subtitle_text")
NODE_CLEAR_BTN_STROKE: str = color("node.clear_btn_stroke")
NODE_ROWS_PANEL_BORDER: str = color("node.rows_panel_border")
NODE_ROWS_PANEL_BG: str = color("node.rows_panel_bg")
NODE_TYPE_TEXT: str = color("node.type_text")
NODE_ROW_SEP: str = color("node.row_sep")
NODE_SCROLLBAR_TRACK: str = color("node.scrollbar_track")
NODE_SCROLLBAR_THUMB: str = color("node.scrollbar_thumb")
NODE_REF_VALUE_TEXT: str = color("node.ref_value_text")
NODE_LITERAL_VALUE_TEXT: str = color("node.literal_value_text")
LINK_SLOT_REF_COLOR: str = color("link.slot_ref")
LINK_EXTENDS_COLOR: str = color("link.extends")
LINK_INSTANCE_OF_COLOR: str = color("link.instance_of")

# Link type view control tokens
# Alpha value (0.0-1.0) for ghosted links in the graph view
LINK_GHOST_ALPHA: float = 0.35

# Graph/workbench cards stay neutral; meaningful color is reserved for
# selection, link types, warnings, and destructive actions.
_HEADER_CLASSIFICATION_COLORS: tuple[str, ...] = (
    PALETTE["layer_row_bg"],
)


def header_color_for_classification(
    *,
    type_id: str | None,
    classification: str | None,
) -> str:
    """Return a stable header ribbon color keyed by type or classification."""
    key = type_id or classification or "_untyped"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(_HEADER_CLASSIFICATION_COLORS)
    return _HEADER_CLASSIFICATION_COLORS[index]


_ADHOC_CHIP_BG_COLORS: tuple[str, ...] = (
    "#21384e",
    "#2a3f30",
    "#3e3729",
    "#332d42",
    "#2a3a43",
)


def ad_hoc_chip_bg_for_predicate(predicate: str) -> str:
    """Return a stable low-saturation chip color for a predicate label."""
    digest = hashlib.md5(predicate.encode("utf-8")).hexdigest()
    return _ADHOC_CHIP_BG_COLORS[int(digest[:8], 16) % len(_ADHOC_CHIP_BG_COLORS)]


__all__ = [
    "EDGE_COLOR",
    "CONTRACT_FRAME_BG",
    "CONTRACT_FRAME_BORDER",
    "CONTRACT_HEADER_BG",
    "CONTRACT_TITLE_COLOR",
    "CONTRACT_TOGGLE_COLOR",
    "FIELD_BUTTON_BG",
    "FIELD_BUTTON_BORDER",
    "FIELD_BUTTON_DISABLED_BORDER",
    "FIELD_BUTTON_DISABLED_TEXT",
    "FIELD_BUTTON_HOVER_BORDER",
    "FIELD_BUTTON_PRESSED_BG",
    "FIELD_BUTTON_PRESSED_BORDER",
    "FIELD_BUTTON_TEXT",
    "FIELD_CHECKBOX_TEXT",
    "FIELD_INPUT_BG",
    "FIELD_INPUT_BORDER",
    "FIELD_INPUT_FOCUS_BORDER",
    "FIELD_INPUT_TEXT",
    "FIELD_LABEL_COLOR",
    "FIELD_MONO_FONT_FAMILY",
    "FIELD_ROW_BG",
    "FIELD_ROW_BORDER",
    "IMMUTABLE_FIELD_TEXT",
    "DEFAULT_COLORS",
    "LINK_GHOST_ALPHA",
    "NODE_CLEAR_BTN_STROKE",
    "NODE_FILL_COLOR",
    "NODE_HEADER_BG",
    "NODE_HEADER_SEP",
    "NODE_HEIGHT_PX",
    "NODE_LITERAL_VALUE_TEXT",
    "NODE_ACTIVE_SELECTED_STROKE_COLOR",
    "NODE_REF_VALUE_TEXT",
    "NODE_ROW_SEP",
    "NODE_ROWS_PANEL_BG",
    "NODE_ROWS_PANEL_BORDER",
    "NODE_SCROLLBAR_THUMB",
    "NODE_SCROLLBAR_TRACK",
    "NODE_SELECTED_STROKE_COLOR",
    "NODE_STROKE_COLOR",
    "NODE_SUBTITLE_TEXT",
    "NODE_TEXT_COLOR",
    "NODE_TYPE_TEXT",
    "NODE_WIDTH_PX",
    "LINK_EXTENDS_COLOR",
    "LINK_INSTANCE_OF_COLOR",
    "LINK_SLOT_REF_COLOR",
    "REF_PILL_BG",
    "REF_PILL_TEXT",
    "REF_MALFORMED_COLOR",
    "REF_MISMATCH_COLOR",
    "REF_MISSING_COLOR",
    "REF_SUBPANEL_BG",
    "REF_SUBPANEL_BORDER",
    "REF_VALID_COLOR",
    "ROOT_HEADER_BG",
    "ROOT_HEADER_STROKE",
    "ROOT_LABEL_COLOR",
    "SAVE_HINT_BORDER",
    "SAVE_HINT_COLOR",
    "SCENE_BACKGROUND_COLOR",
    "SECTION_LABEL_COLOR",
    "COLLAPSE_ARROW_COLOR",
    "LIBRARY_TREE_INDENT_PX",
    "ADHOC_STUB_INCOMING_COLOR",
    "ADHOC_STUB_OUTGOING_COLOR",
    "ADHOC_STUB_TEXT_COLOR",
    "ADHOC_PANEL_SECTION_LABEL_COLOR",
    "ADHOC_PANEL_OUT_OF_GRAPH_LABEL_COLOR",
    "ADHOC_PANEL_CHIP_BORDER_COLOR",
    "SCENE_PADDING_PX",
    "SCENE_SCALE_PX",
    "VALIDATION_ERROR_STRIPE",
    "VALIDATION_ERROR_TEXT",
    "VALIDATION_WARNING_LABEL",
    "header_color_for_classification",
    "ad_hoc_chip_bg_for_predicate",
    "color",
    "colors",
]

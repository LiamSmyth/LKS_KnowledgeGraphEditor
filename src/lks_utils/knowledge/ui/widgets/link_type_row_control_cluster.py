"""Link-type row control cluster widget - 4 toggle buttons for per-type visibility/ghost/etc."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from lks_utils.knowledge.actions import (
    LINKTYPE_TOGGLE_FILTER,
    LINKTYPE_TOGGLE_GHOST,
    LINKTYPE_TOGGLE_SELECTABLE,
    LINKTYPE_TOGGLE_VISIBILITY,
)
from lks_utils.knowledge.default_theme import (
    FIELD_BUTTON_DISABLED_TEXT,
    FIELD_BUTTON_TEXT,
)
from lks_utils.knowledge.link_type_view_state import LinkTypeViewState
from lks_utils.knowledge.ui.icons import get_icon


@dataclass(frozen=True)
class LinkTypeRowControlClusterConfig:
    """Configuration for link-type row control cluster widget."""
    icon_size_px: int = 14
    button_size_px: int = 22
    button_spacing_px: int = 1


class QLinkTypeRowControlCluster(QWidget):
    """
    4-button toolbar cluster for per-link-type view state controls.

    Displays toggle buttons for:
    - Filter (filtered_out flag)
    - Visibility (visible flag)
    - Ghost (ghosted flag)
    - Selectable (selectable flag)

    Emits link_type_state_changed(type_id, updated_view_state) when a flag changes.
    """

    link_type_state_changed = Signal(str, LinkTypeViewState)

    def __init__(
        self,
        type_id: str,
        view_state: LinkTypeViewState,
        *,
        config: LinkTypeRowControlClusterConfig | None = None,
        parent: QWidget | None = None,
    ):
        """
        Initialize the link-type row control cluster.

        Args:
            type_id: The link type ID this cluster controls.
            view_state: The LinkTypeViewState to read flags from and update.
            config: Optional configuration (icon size, spacing).
            parent: Parent widget.
        """
        super().__init__(parent)
        self.type_id = type_id
        self._view_state = view_state
        self._config = config or LinkTypeRowControlClusterConfig()
        self._button_icon_names: dict[QToolButton, tuple[str, str]] = {}

        # Get the flags for this type
        flags = view_state.get_flags(type_id)

        # Create layout
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._config.button_spacing_px)

        # Create buttons
        self._btn_filter = self._create_button(
            "filter",
            "filter_off",
            LINKTYPE_TOGGLE_FILTER,
            flags.filtered_out,
            self._toggle_filter,
        )
        layout.addWidget(self._btn_filter)

        self._btn_visibility = self._create_button(
            "visibility_on",
            "visibility_off",
            LINKTYPE_TOGGLE_VISIBILITY,
            flags.visible,
            self._toggle_visibility,
        )
        layout.addWidget(self._btn_visibility)

        self._btn_ghost = self._create_button(
            "ghost_on",
            "ghost_off",
            LINKTYPE_TOGGLE_GHOST,
            flags.ghosted,
            self._toggle_ghost,
        )
        layout.addWidget(self._btn_ghost)

        self._btn_selectable = self._create_button(
            "select_on",
            "select_off",
            LINKTYPE_TOGGLE_SELECTABLE,
            flags.selectable,
            self._toggle_selectable,
        )
        layout.addWidget(self._btn_selectable)

        self.setLayout(layout)

    def _create_button(
        self,
        icon_on: str,
        icon_off: str,
        action,
        is_active: bool,
        clicked_callback,
    ) -> QToolButton:
        """Create a single toggle button with icon and tooltip."""
        btn = QToolButton()
        btn.setObjectName("link_type_row_control_button")
        btn.setFixedSize(self._config.button_size_px, self._config.button_size_px)
        btn.setIconSize(QSize(self._config.icon_size_px,
                        self._config.icon_size_px))

        # Set tooltip from action
        btn.setToolTip(action.description)

        # Set checkable and initial state
        btn.setCheckable(True)
        btn.setChecked(is_active)

        # Connect clicked signal
        btn.clicked.connect(clicked_callback)

        self._button_icon_names[btn] = (icon_on, icon_off)
        self._set_button_icon(btn, is_active)
        self._apply_button_style(btn)

        return btn

    def _apply_button_style(self, btn: QToolButton) -> None:
        btn.setStyleSheet(
            "QToolButton#link_type_row_control_button {"
            "background: transparent; border: none;"
            "padding: 0px; margin: 0px;"
            f"color: {FIELD_BUTTON_TEXT};"
            "}"
            "QToolButton#link_type_row_control_button:hover {"
            "background: transparent; border: none;"
            "}"
            "QToolButton#link_type_row_control_button:pressed {"
            "background: transparent; border: none;"
            "}"
            "QToolButton#link_type_row_control_button:checked {"
            "background: transparent; border: none;"
            "}"
            "QToolButton#link_type_row_control_button:disabled {"
            f"color: {FIELD_BUTTON_DISABLED_TEXT};"
            "background: transparent; border: none;"
            "}"
        )

    def _set_button_icon(self, btn: QToolButton, is_active: bool) -> None:
        icon_names = self._button_icon_names.get(btn)
        if icon_names is None:
            return
        active_name, inactive_name = icon_names
        icon_name = active_name if is_active else inactive_name
        tint = FIELD_BUTTON_TEXT if is_active else FIELD_BUTTON_DISABLED_TEXT
        icon = get_icon(icon_name, color=tint, size_px=self._config.icon_size_px)
        if icon is not None:
            btn.setIcon(icon)

    def _toggle_filter(self):
        """Toggle the filter (filtered_out) flag."""
        flags = self._view_state.get_flags(self.type_id)
        new_flags = flags.with_filtered_out(not flags.filtered_out)
        new_state = self._view_state.set_flags(self.type_id, new_flags)
        self._view_state = new_state
        self.link_type_state_changed.emit(self.type_id, new_state)
        self._update_button_state()

    def _toggle_visibility(self):
        """Toggle the visibility flag."""
        flags = self._view_state.get_flags(self.type_id)
        new_flags = flags.with_visible(not flags.visible)
        new_state = self._view_state.set_flags(self.type_id, new_flags)
        self._view_state = new_state
        self.link_type_state_changed.emit(self.type_id, new_state)
        self._update_button_state()

    def _toggle_ghost(self):
        """Toggle the ghost (ghosted) flag."""
        flags = self._view_state.get_flags(self.type_id)
        new_flags = flags.with_ghosted(not flags.ghosted)
        new_state = self._view_state.set_flags(self.type_id, new_flags)
        self._view_state = new_state
        self.link_type_state_changed.emit(self.type_id, new_state)
        self._update_button_state()

    def _toggle_selectable(self):
        """Toggle the selectable flag."""
        flags = self._view_state.get_flags(self.type_id)
        new_flags = flags.with_selectable(not flags.selectable)
        new_state = self._view_state.set_flags(self.type_id, new_flags)
        self._view_state = new_state
        self.link_type_state_changed.emit(self.type_id, new_state)
        self._update_button_state()

    def _update_button_state(self):
        """Update button icons and states based on current flags."""
        flags = self._view_state.get_flags(self.type_id)

        # Update filter button
        self._btn_filter.setChecked(flags.filtered_out)
        self._set_button_icon(self._btn_filter, flags.filtered_out)

        # Update visibility button and icon
        self._btn_visibility.setChecked(flags.visible)
        self._set_button_icon(self._btn_visibility, flags.visible)

        # Update ghost button and icon
        self._btn_ghost.setChecked(flags.ghosted)
        self._set_button_icon(self._btn_ghost, flags.ghosted)

        # Update selectable button and icon
        self._btn_selectable.setChecked(flags.selectable)
        self._set_button_icon(self._btn_selectable, flags.selectable)

    def update_view_state(self, view_state: LinkTypeViewState):
        """Update the internal view state and refresh button displays."""
        self._view_state = view_state
        self._update_button_state()

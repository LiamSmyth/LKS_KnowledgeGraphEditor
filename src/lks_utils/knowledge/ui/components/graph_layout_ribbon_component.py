"""Layout action ribbon for the knowledge graph tab."""
from __future__ import annotations
from lks_utils.knowledge.ui.icons import get_icon
from lks_utils.knowledge.default_theme import FIELD_BUTTON_TEXT

from collections.abc import Callable
from typing import Literal

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

_EXPANSION_MODE_CYCLE: tuple[str, ...] = ("adjacent", "frontier", "all")

_EXPANSION_MODE_LABELS: dict[str, str] = {
    "adjacent": "Adjacent",
    "frontier": "Frontier",
    "all": "All",
}

_EXPANSION_MODE_TOOLTIPS: dict[str, str] = {
    "adjacent": "Mode: Adjacent — expand/contract one step from current frontier. Click to cycle.",
    "frontier": "Mode: Frontier — expand/contract to full reachable graph. Click to cycle.",
    "all": "Mode: All — show all nodes / collapse to selection. Click to cycle.",
}


class QGraphLayoutRibbonComponent(QWidget):
    """Compact graph-layout command strip with selection-aware enablement."""

    def __init__(
        self,
        *,
        on_apply_layout: Callable[[str], None],
        on_apply_traversal: Callable[[str], None] | None = None,
        on_set_traversal_direction: Callable[[
            Literal["forward", "back", "both"]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_apply_layout = on_apply_layout
        self._on_apply_traversal = on_apply_traversal
        self._on_set_traversal_direction = on_set_traversal_direction
        self._buttons: dict[str, QPushButton] = {}
        self._traversal_buttons: dict[str, QPushButton] = {}
        self._direction_button: QPushButton | None = None
        self._traversal_direction: Literal["forward", "back", "both"] = "both"
        self._expansion_mode: Literal["adjacent",
                                      "frontier", "all"] = "adjacent"
        self._expansion_mode_button: QPushButton | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        layout_label = QLabel("Layout", self)
        layout_label.setObjectName("graph_layout_ribbon_label")
        layout.addWidget(layout_label)

        self._create_button(
            layout,
            algorithm_key="grid",
            text="Grid",
            tooltip="Arrange selected nodes in a compact grid.",
            icon_name="layout_grid",
        )
        self._create_button(
            layout,
            algorithm_key="line",
            text="Line",
            tooltip="Arrange selected nodes in a horizontal line.",
            icon_name="layout_line",
        )
        self._create_button(
            layout,
            algorithm_key="radial",
            text="Radial",
            tooltip="Arrange selected nodes in a radial ring.",
            icon_name="layout_radial",
        )
        self._create_button(
            layout,
            algorithm_key="sugiyama",
            text="Sugiyama",
            tooltip="Arrange selected nodes in layered (Sugiyama) order.",
            icon_name="layout_sugiyama",
        )
        self._create_button(
            layout,
            algorithm_key="networkx_spread",
            text="NetworkX",
            tooltip="Arrange selected nodes with spring layout plus anti-overlap spreading.",
            icon_name="layout_networkx_spread",
        )

        traversal_label = QLabel("Traversal", self)
        traversal_label.setObjectName("graph_layout_ribbon_label")
        layout.addWidget(traversal_label)

        self._create_direction_cycle_button(layout)
        self.set_traversal_direction("both")

        self._create_expansion_mode_button(layout)
        self._create_traversal_button(
            layout,
            action_key="expand",
            text="Expand",
            tooltip="Expand from current selection (behavior depends on mode).",
            icon_name="expand_step",
        )
        self._create_traversal_button(
            layout,
            action_key="contract",
            text="Contract",
            tooltip="Contract graph focus (behavior depends on mode).",
            icon_name="contract_step",
        )

        layout.addStretch(1)

    def set_selection_count(self, count: int) -> None:
        enabled = count >= 2
        for button in self._buttons.values():
            button.setEnabled(enabled)
            if enabled:
                continue
            button.setToolTip("Select at least two nodes to apply layout.")
        traversal_enabled = count >= 1
        for button in self._traversal_buttons.values():
            button.setEnabled(traversal_enabled)

    def set_traversal_direction(self, direction: Literal["forward", "back", "both"]) -> None:
        if direction not in {"forward", "back", "both"}:
            return
        self._traversal_direction = direction
        self._refresh_direction_button_ui()

    def _create_button(
        self,
        layout: QHBoxLayout,
        *,
        algorithm_key: str,
        text: str,
        tooltip: str,
        icon_name: str,
    ) -> None:
        button = QPushButton(text, self)
        icon = get_icon(icon_name, color=FIELD_BUTTON_TEXT, size_px=18)
        if icon is not None:
            button.setIcon(icon)
        else:
            button.setIcon(QIcon())
        button.setToolTip(tooltip)
        button.setSizePolicy(QSizePolicy.Policy.Fixed,
                             QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False,
                               key=algorithm_key: self._on_apply_layout(key))
        layout.addWidget(button)
        self._buttons[algorithm_key] = button

    def _create_expansion_mode_button(self, layout: QHBoxLayout) -> None:
        button = QPushButton("Adjacent", self)
        button.setToolTip(_EXPANSION_MODE_TOOLTIPS["adjacent"])
        button.setSizePolicy(QSizePolicy.Policy.Fixed,
                             QSizePolicy.Policy.Fixed)
        button.clicked.connect(self._on_expansion_mode_cycle_clicked)
        layout.addWidget(button)
        self._expansion_mode_button = button

    def _on_expansion_mode_cycle_clicked(self) -> None:
        idx = _EXPANSION_MODE_CYCLE.index(self._expansion_mode)
        self._expansion_mode = _EXPANSION_MODE_CYCLE[(
            idx + 1) % len(_EXPANSION_MODE_CYCLE)]  # type: ignore[assignment]
        self._refresh_expansion_mode_button_ui()

    def _refresh_expansion_mode_button_ui(self) -> None:
        if self._expansion_mode_button is None:
            return
        mode = self._expansion_mode
        self._expansion_mode_button.setText(_EXPANSION_MODE_LABELS[mode])
        self._expansion_mode_button.setToolTip(_EXPANSION_MODE_TOOLTIPS[mode])
        expand_btn = self._traversal_buttons.get("expand")
        contract_btn = self._traversal_buttons.get("contract")
        if expand_btn is not None:
            expand_btn.setToolTip(
                {"adjacent": "Expand one step from current frontier.",
                 "frontier": "Expand to full reachable frontier.",
                 "all": "Show all nodes in the repository."}[mode]
            )
        if contract_btn is not None:
            contract_btn.setToolTip(
                {"adjacent": "Contract one step (remove outermost frontier nodes).",
                 "frontier": "Contract frontier to current selection.",
                 "all": "Collapse view to current selection only."}[mode]
            )

    def _create_traversal_button(
        self,
        layout: QHBoxLayout,
        *,
        action_key: str,
        text: str,
        tooltip: str,
        icon_name: str,
    ) -> None:
        button = QPushButton(text, self)
        icon = get_icon(icon_name, color=FIELD_BUTTON_TEXT, size_px=18)
        if icon is not None:
            button.setIcon(icon)
        else:
            button.setIcon(QIcon())
        button.setToolTip(tooltip)
        button.setSizePolicy(QSizePolicy.Policy.Fixed,
                             QSizePolicy.Policy.Fixed)
        if self._on_apply_traversal is None:
            button.setEnabled(False)
        else:
            button.clicked.connect(
                lambda _checked=False, key=action_key: self._on_apply_traversal(
                    f"{key}.{self._expansion_mode}")
            )
        layout.addWidget(button)
        self._traversal_buttons[action_key] = button

    def _create_direction_cycle_button(
        self,
        layout: QHBoxLayout,
    ) -> None:
        button = QPushButton("Both", self)
        button.setToolTip(
            "Traversal direction: click to cycle Both -> Outgoing -> Incoming.")
        button.setSizePolicy(QSizePolicy.Policy.Fixed,
                             QSizePolicy.Policy.Fixed)
        if self._on_set_traversal_direction is None:
            button.setEnabled(False)
        else:
            button.clicked.connect(self._on_traversal_direction_cycle_clicked)
        layout.addWidget(button)
        self._direction_button = button

    def _on_traversal_direction_cycle_clicked(self) -> None:
        next_direction: Literal["forward", "back", "both"]
        if self._traversal_direction == "both":
            next_direction = "forward"
        elif self._traversal_direction == "forward":
            next_direction = "back"
        else:
            next_direction = "both"
        self._on_traversal_direction_clicked(next_direction)

    def _on_traversal_direction_clicked(
        self,
        direction: Literal["forward", "back", "both"],
    ) -> None:
        self.set_traversal_direction(direction)
        if self._on_set_traversal_direction is not None:
            self._on_set_traversal_direction(direction)

    def _refresh_direction_button_ui(self) -> None:
        if self._direction_button is None:
            return
        labels = {
            "forward": "Outgoing",
            "back": "Incoming",
            "both": "Both",
        }
        icons = {
            "forward": "traversal_forward",
            "back": "traversal_back",
            "both": "traversal_both",
        }
        tooltips = {
            "forward": "Traversal direction: Outgoing (source -> target). Click to cycle.",
            "back": "Traversal direction: Incoming (target -> source). Click to cycle.",
            "both": "Traversal direction: Both directions. Click to cycle.",
        }
        direction = self._traversal_direction
        self._direction_button.setText(labels[direction])
        self._direction_button.setToolTip(tooltips[direction])
        icon = get_icon(icons[direction], color=FIELD_BUTTON_TEXT, size_px=18)
        if icon is not None:
            self._direction_button.setIcon(icon)
        else:
            self._direction_button.setIcon(QIcon())


__all__ = ["QGraphLayoutRibbonComponent"]

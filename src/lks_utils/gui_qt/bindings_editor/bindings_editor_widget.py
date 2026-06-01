"""QBindingsEditorWidget — full reflection-driven shortcut editor."""
from __future__ import annotations

from lks_utils.input.action import Action
from lks_utils.input.binding import Binding
from lks_utils.input.bindings_registry import InputBindings
from lks_utils.gui_qt.input_bindings_qt.input_bindings_provider_qt import (
    QInputBindingsProvider,
)
from lks_utils.gui_qt.base import QGUIStateMixin
from lks_utils.gui_qt.bindings_editor.action_row_widget import QActionRowWidget

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QComboBox,
    QLineEdit,
    QPushButton,
    QLabel,
    QGroupBox,
    QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QTimer


class QBindingsEditorWidget(QWidget, QGUIStateMixin):
    """Full reflection-driven shortcut editor.

    Walks the Action registry and renders one :class:`QActionRowWidget`
    per action, grouped by category.  Edits flow through
    :class:`~lks_utils.gui_qt.input_bindings_qt.QInputBindingsProvider`.
    """

    bindings_changed = Signal(object)  # InputBindings

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        state_key: str = "bindings_editor_widget",
        state_org: str = "lks_utils",
        state_settings_path: str | None = None,
        state_format: str = "registry",
    ) -> None:
        QWidget.__init__(self, parent=parent)
        QGUIStateMixin.__init__(self)

        self._provider = QInputBindingsProvider.instance()
        self._rows: dict[str, QActionRowWidget] = {}  # action_id → row

        self._build_ui()
        self._populate_rows()
        self._scope_combo.currentTextChanged.connect(
            lambda _: self._save_state())
        self._search_edit.textChanged.connect(lambda _: self._save_state())
        self._scroll_area.verticalScrollBar().valueChanged.connect(
            lambda _: self._save_state()
        )
        self._init_state(
            state_key,
            org=state_org,
            settings_path=state_settings_path,
            format=state_format,
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addLayout(self._build_toolbar())

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(4)
        self._scroll_area.setWidget(self._inner)
        root.addWidget(self._scroll_area, stretch=1)

        root.addWidget(self._build_footer())

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(6)

        scope_lbl = QLabel("Scope:")
        self._scope_combo = QComboBox()
        self._scope_combo.addItem("All", userData=None)
        self._scope_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._scope_combo.setMaximumWidth(160)
        self._scope_combo.currentTextChanged.connect(self._apply_filters)

        search_lbl = QLabel("Search:")
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter by name or description…")
        self._search_edit.textChanged.connect(self._apply_filters)

        btn_reset = QPushButton("Reset to defaults")
        btn_reset.clicked.connect(self._reset_to_defaults)

        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._save)

        for w in (scope_lbl, self._scope_combo, search_lbl, self._search_edit, btn_reset, btn_save):
            bar.addWidget(w)

        return bar

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(0, 0, 0, 0)
        self._status_lbl = QLabel("0 modified, 0 conflicts")
        lay.addWidget(self._status_lbl)
        lay.addStretch()
        return footer

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _populate_rows(self) -> None:
        bindings = self._provider.bindings()
        actions = bindings.actions()

        # Collect unique scopes
        scopes = sorted({a.scope for a in actions})
        for scope in scopes:
            if self._scope_combo.findText(scope) < 0:
                self._scope_combo.addItem(scope, userData=scope)

        # Group by category
        by_category: dict[str, list[Action]] = {}
        for action in actions:
            by_category.setdefault(action.category, []).append(action)

        for cat_name, cat_actions in sorted(by_category.items()):
            group = QGroupBox(cat_name)
            g_layout = QVBoxLayout(group)
            g_layout.setContentsMargins(4, 2, 4, 4)
            g_layout.setSpacing(1)

            for action in cat_actions:
                current = list(bindings.get_bindings(action.id))
                row = QActionRowWidget(action, current)
                row.binding_changed.connect(self._on_binding_changed)
                self._rows[action.id] = row
                g_layout.addWidget(row)

            self._inner_layout.addWidget(group)

        self._inner_layout.addStretch()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_binding_changed(self, action: Action, bindings: list[Binding]) -> None:
        self._provider.set_user_override(action, bindings)
        self.bindings_changed.emit(self._provider.bindings())
        self._update_status()

    def _apply_filters(self, *_) -> None:
        scope_text = self._scope_combo.currentText()
        scope_filter: str | None = None if scope_text == "All" else scope_text
        search_text = self._search_edit.text().lower()

        for action_id, row in self._rows.items():
            action = row.action()
            scope_match = scope_filter is None or action.scope == scope_filter
            search_match = (
                not search_text
                or search_text in action.label.lower()
                or search_text in action.description.lower()
            )
            row.setVisible(scope_match and search_match)

        # Hide empty group boxes — use isHidden() (not isVisible()) so that
        # a row whose own hidden-flag is False is counted as visible even if
        # its parent group-box was hidden by a previous filter application.
        for i in range(self._inner_layout.count()):
            item = self._inner_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, QGroupBox):
                    has_visible = any(
                        not w.layout().itemAt(j).widget().isHidden()
                        for j in range(w.layout().count())
                        if w.layout().itemAt(j) and w.layout().itemAt(j).widget()
                    )
                    w.setVisible(has_visible)

    def _reset_to_defaults(self) -> None:
        self._provider.reset_to_defaults()
        # Repopulate
        for action_id, row in self._rows.items():
            bindings = self._provider.bindings()
            row.set_bindings(list(bindings.get_bindings(action_id)))
        self._update_status()

    def _save(self) -> None:
        self._provider.save_user_overrides()

    def _update_status(self) -> None:
        bindings = self._provider.bindings()
        modified = sum(
            1 for aid, row in self._rows.items()
            if list(bindings.get_bindings(aid)) != list(bindings.get_defaults(aid))
        )
        self._status_lbl.setText(f"{modified} modified, 0 conflicts")

    # ------------------------------------------------------------------
    # QGUIStateMixin
    # ------------------------------------------------------------------

    def _get_state_fields(self) -> dict:
        return {
            "scope_filter": self._scope_combo.currentText(),
            "search": self._search_edit.text(),
            "scroll_value": self._scroll_area.verticalScrollBar().value(),
        }

    def _set_state_fields(self, state: dict) -> None:
        if "scope_filter" in state:
            idx = self._scope_combo.findText(state["scope_filter"])
            if idx >= 0:
                self._scope_combo.setCurrentIndex(idx)
        if "search" in state:
            self._search_edit.setText(state["search"])
        if "scroll_value" in state:
            scroll_value = state["scroll_value"]
            if isinstance(scroll_value, str):
                try:
                    scroll_value = int(scroll_value)
                except ValueError:
                    scroll_value = 0
            scrollbar = self._scroll_area.verticalScrollBar()

            def _restore_scroll(*_) -> None:
                scrollbar.setValue(scroll_value)

            scrollbar.rangeChanged.connect(_restore_scroll)
            QTimer.singleShot(0, _restore_scroll)


__all__ = ["QBindingsEditorWidget"]

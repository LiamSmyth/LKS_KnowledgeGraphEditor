"""Link-type palette panel for graph linking workflows."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QMimeData, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QMouseEvent
from PySide6.QtWidgets import QApplication, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from lks_utils.gui_qt.widgets.q_header_strip_base import QHeaderStripBase
from lks_utils.gui_qt.widgets.q_validation_badge import QValidationBadge
from lks_utils.input import GestureKind, get_default_bindings
from lks_utils.input.qt_adapter import qt_button_to_logical, qt_modifiers_to_logical
from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    FIELD_BUTTON_TEXT,
    FIELD_INPUT_FOCUS_BORDER,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.link_type_view_state import LinkTypeViewState
from lks_utils.knowledge.ui.icons import get_icon
from lks_utils.knowledge.ui.widgets.link_type_row_control_cluster import (
    LinkTypeRowControlClusterConfig,
    QLinkTypeRowControlCluster,
)
from lks_utils.knowledge.ui.actions import GRAPH_LINK_CREATE_BEGIN
from lks_utils.knowledge.ui.widgets.validation_badge_row_controller import (
    ValidationBadgeRowController,
)

_ACTIVE_BORDER_COLOR = FIELD_INPUT_FOCUS_BORDER
_LINK_TYPE_MIME = "application/x-knowledge-link-type-id"


class _QGraphLinkTypePaletteList(QListWidget):
    """List widget that starts drag-based link creation from link-type rows."""

    def __init__(
        self,
        on_drag_start: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_drag_start = on_drag_start
        self._press_pos: QPoint | None = None
        self._press_link_type_id: str | None = None
        self._press_button = None

    # type: ignore[override]
    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        button = qt_button_to_logical(event.button())
        if button is None:
            self._clear_press_state()
            return
        item = self.itemAt(event.position().toPoint())
        if item is None:
            self._clear_press_state()
            return
        is_system = bool(item.data(Qt.ItemDataRole.UserRole + 1))
        link_type_id = item.data(Qt.ItemDataRole.UserRole)
        if is_system or not isinstance(link_type_id, str):
            self._clear_press_state()
            return
        self.setCurrentItem(item)
        item.setSelected(True)
        self._press_pos = event.position().toPoint()
        self._press_link_type_id = link_type_id
        self._press_button = button

    # type: ignore[override]
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_pos is None or self._press_link_type_id is None or self._press_button is None:
            super().mouseMoveEvent(event)
            return
        if (event.position().toPoint() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return
        bindings = get_default_bindings()
        mods = qt_modifiers_to_logical(event.modifiers())
        if not bindings.matches_mouse(
            GRAPH_LINK_CREATE_BEGIN.id,
            self._press_button,
            mods,
            GestureKind.DRAG,
        ):
            super().mouseMoveEvent(event)
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_LINK_TYPE_MIME, self._press_link_type_id.encode("utf-8"))
        drag.setMimeData(mime)
        self._on_drag_start(self._press_link_type_id)
        drag.exec(Qt.DropAction.CopyAction)
        self._clear_press_state()
        event.accept()

    # type: ignore[override]
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self._clear_press_state()

    def _clear_press_state(self) -> None:
        self._press_pos = None
        self._press_link_type_id = None
        self._press_button = None


class QGraphLinkTypePalettePanel(QWidget):
    """Single-select palette of link types with active-link signal emission."""

    active_link_type_changed = Signal(object)  # link_type_id | None
    link_type_drag_started = Signal(str)
    link_type_view_state_changed = Signal(object)  # LinkTypeViewState

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._active_link_type_id: str | None = None
        self._view_state = LinkTypeViewState()
        self._badge_controller = ValidationBadgeRowController(
            session.validation_index, self)
        self._attached_object_ids: set[str] = set()
        self._link_type_ids: list[str] = []
        self._list = _QGraphLinkTypePaletteList(
            self._on_link_type_drag_started, self)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._title = QHeaderStripBase("Link Types", parent=self)
        self._title.title_widget().setObjectName("graph_link_type_palette_title")
        self._bulk_controls = self._build_bulk_controls_widget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._list)
        layout.addWidget(self._bulk_controls)

        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._apply_styles()
        self.refresh()

    def active_link_type_id(self) -> str | None:
        """Return currently active link type id."""
        return self._active_link_type_id

    def refresh(self) -> None:
        """Reload link-type rows from the active session repository."""
        for object_id in self._attached_object_ids:
            self._badge_controller.detach_row(object_id)
        self._attached_object_ids.clear()
        self._list.clear()
        self._link_type_ids = []
        for link_type in sorted(
            self._session.list_link_types(),
            key=lambda item: item.name.lower(),
        ):
            label = f"{link_type.name} (system)" if link_type.is_system else link_type.name
            item = QListWidgetItem("")
            object_id = str(link_type.id)
            item.setData(Qt.ItemDataRole.UserRole, object_id)
            item.setData(Qt.ItemDataRole.UserRole +
                         1, bool(link_type.is_system))
            if link_type.is_system:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setForeground(QBrush(QColor(EDGE_COLOR)))
            self._list.addItem(item)

            self._link_type_ids.append(object_id)

            row = QWidget(self._list)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(1)
            badge = QValidationBadge(row)
            text_label = QLabel(label, row)
            controls = QLinkTypeRowControlCluster(
                type_id=object_id,
                view_state=self._view_state,
                parent=row,
            )
            controls.link_type_state_changed.connect(
                self._on_link_type_state_changed
            )
            if link_type.is_system:
                text_label.setStyleSheet(f"color: {EDGE_COLOR};")
            row_layout.addWidget(badge, stretch=0)
            row_layout.addWidget(text_label, stretch=1)
            row_layout.addWidget(controls, stretch=0)
            badge.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            text_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            item.setSizeHint(row.sizeHint())
            self._list.setItemWidget(item, row)
            self._badge_controller.attach_row(object_id, row, badge)
            self._attached_object_ids.add(object_id)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            "QLabel#graph_link_type_palette_title { font-weight: 600; padding: 2px 2px 0px 2px; }"
            f"QListWidget {{ border: 1px solid {EDGE_COLOR}; }}"
            f"QListWidget::item:selected {{ border: 2px solid {_ACTIVE_BORDER_COLOR}; }}"
            "QPushButton#graph_link_type_bulk_button {"
            "background: transparent; border: none; padding: 0px; margin: 0px;"
            "font-size: 9px;"
            f"color: {FIELD_BUTTON_TEXT};"
            "}"
            "QToolButton#graph_link_type_bulk_button {"
            "background: transparent; border: none; padding: 0px; margin: 0px;"
            "font-size: 9px;"
            f"color: {FIELD_BUTTON_TEXT};"
            "}"
            "QPushButton#graph_link_type_bulk_button:disabled {"
            "background: transparent; border: none;"
            f"color: {EDGE_COLOR};"
            "}"
            "QToolButton#graph_link_type_bulk_button:disabled {"
            "background: transparent; border: none;"
            f"color: {EDGE_COLOR};"
            "}"
        )

    def _build_bulk_controls_widget(self) -> QWidget:
        host = QWidget(self)
        host_layout = QHBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        host_layout.addStretch(1)

        button_cfg = LinkTypeRowControlClusterConfig()
        block = QWidget(host)
        block.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        grid = QGridLayout(block)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(button_cfg.button_spacing_px)
        grid.setVerticalSpacing(0)
        grid.setAlignment(Qt.AlignmentFlag.AlignRight |
                          Qt.AlignmentFlag.AlignTop)

        entries = [
            (0, "filtered_out", "A", "Set all filters on"),
            (1, "filtered_out", "N", "Clear all filters"),
            (2, "filtered_out", "I", "Invert all filters"),
            (0, "visible", "A", "Set all visible"),
            (1, "visible", "N", "Set all hidden"),
            (2, "visible", "I", "Invert all visibility"),
            (0, "ghosted", "A", "Set all ghosted"),
            (1, "ghosted", "N", "Set all non-ghosted"),
            (2, "ghosted", "I", "Invert all ghost flags"),
            (0, "selectable", "A", "Set all selectable"),
            (1, "selectable", "N", "Set all non-selectable"),
            (2, "selectable", "I", "Invert all selectable flags"),
        ]
        column_for_flag = {
            "filtered_out": 0,
            "visible": 1,
            "ghosted": 2,
            "selectable": 3,
        }
        for row, flag_name, label, tooltip in entries:
            col = column_for_flag[flag_name]
            button = self._create_bulk_icon_button(
                tooltip=tooltip,
                flag_name=flag_name,
                op_label=label,
                size_px=button_cfg.button_size_px,
                icon_size_px=button_cfg.icon_size_px,
            )
            grid.addWidget(button, row, col)

        cluster_width = (4 * button_cfg.button_size_px) + \
            (3 * button_cfg.button_spacing_px)
        block.setFixedWidth(cluster_width)

        host_layout.addWidget(block, 0, Qt.AlignmentFlag.AlignRight)
        return host

    def _icon_name_for_bulk_op(self, flag_name: str, op_label: str) -> str | None:
        flag_to_prefix = {
            "filtered_out": "filter",
            "visible": "visible",
            "ghosted": "ghost",
            "selectable": "selectable",
        }
        op_to_suffix = {
            "A": "all",
            "N": "none",
            "I": "invert",
        }
        prefix = flag_to_prefix.get(flag_name)
        suffix = op_to_suffix.get(op_label)
        if prefix is None or suffix is None:
            return None
        return f"link_{prefix}_{suffix}"

    def _create_bulk_icon_button(
        self,
        *,
        tooltip: str,
        flag_name: str,
        op_label: str,
        size_px: int,
        icon_size_px: int,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("graph_link_type_bulk_button")
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setFixedSize(size_px, size_px)
        icon_name = self._icon_name_for_bulk_op(flag_name, op_label)
        if icon_name is not None:
            icon = get_icon(icon_name, color=FIELD_BUTTON_TEXT,
                            size_px=icon_size_px)
            if icon is not None:
                button.setIcon(icon)
                button.setIconSize(QSize(icon_size_px, icon_size_px))
            else:
                button.setText(op_label)
        else:
            button.setText(op_label)
        button.clicked.connect(
            lambda _checked=False, flag=flag_name, op=op_label: self._on_bulk_flag_operation(
                flag, op)
        )
        return button

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        is_system = bool(item.data(Qt.ItemDataRole.UserRole + 1))
        if is_system:
            return
        link_type_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(link_type_id, str):
            return
        self._active_link_type_id = link_type_id
        self._list.setCurrentItem(item)
        self.active_link_type_changed.emit(link_type_id)

    def _on_link_type_drag_started(self, link_type_id: str) -> None:
        self._active_link_type_id = link_type_id
        self.link_type_drag_started.emit(link_type_id)

    def set_view_state(self, view_state: LinkTypeViewState) -> None:
        """Set current link-type view state and rebuild row controls."""
        self._view_state = view_state
        self.refresh()

    def _on_link_type_state_changed(
        self,
        _type_id: str,
        updated_view_state: LinkTypeViewState,
    ) -> None:
        self._view_state = updated_view_state
        self._propagate_view_state_to_row_controls()
        self.link_type_view_state_changed.emit(updated_view_state)

    def _on_bulk_flag_operation(self, flag_name: str, op_label: str) -> None:
        if not self._link_type_ids:
            return
        if op_label == "A":
            self._view_state = self._view_state.set_all_flag(
                flag_name,
                True,
                self._link_type_ids,
            )
        elif op_label == "N":
            self._view_state = self._view_state.set_all_flag(
                flag_name,
                False,
                self._link_type_ids,
            )
        elif op_label == "I":
            self._view_state = self._view_state.invert_flag(
                flag_name,
                self._link_type_ids,
            )
        else:
            return
        self._propagate_view_state_to_row_controls()
        self.link_type_view_state_changed.emit(self._view_state)

    def _propagate_view_state_to_row_controls(self) -> None:
        """Push the latest global view state into every row control cluster."""
        for index in range(self._list.count()):
            item = self._list.item(index)
            row_widget = self._list.itemWidget(item)
            if row_widget is None:
                continue
            controls = row_widget.findChild(QLinkTypeRowControlCluster)
            if controls is None:
                continue
            controls.update_view_state(self._view_state)


__all__ = ["QGraphLinkTypePalettePanel"]

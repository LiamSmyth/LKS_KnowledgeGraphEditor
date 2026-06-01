"""Per-primitive tab: Library + Palette (left) | Edit canvas (center) | Inspector (right)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.editor_session_types import SessionChangeEvent
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_slot import NodeSlot, SlotSource
from lks_utils.knowledge.models.type import as_type, is_type, make_type
from lks_utils.knowledge.ui.components.context_library_panel import QKnowledgeContextLibraryPanel
from lks_utils.knowledge.ui.components.decomposition_canvas import (
    QKnowledgeDecompositionCanvasWidget,
)
from lks_utils.knowledge.ui.components.palette_panel import (
    PALETTE_PROPERTY,
    PALETTE_SLOT_LITERAL,
    PALETTE_SLOT_REF,
    QKnowledgePalettePanel,
)
from lks_utils.knowledge.ui.components.connections_panel import QKnowledgeConnectionsPanel
from lks_utils.knowledge.ui.components.properties_panel import QKnowledgeInspectorPanel
from lks_utils.knowledge.ui.components.ref_picker_dialog import QKnowledgeRefPickerDialog
from lks_utils.knowledge.ui.editor_tab_base import QKnowledgeEditorTabBase


PALETTE_SLOT_VALUE_PREFIX = "slot_value:"


class QKnowledgePrimitiveTabWidget(QKnowledgeEditorTabBase):
    """Three-panel editing surface for one primitive context (types or instances).

    Layout (left-to-right in horizontal splitter)::

        [ Library + Palette ] | [ Canvas ribbon + Canvas ] | [ Inspector ]

    Args:
        session: Active editor session.
        context: ``"type"`` or ``"instance"``.
    """

    node_opened = Signal(str)  # node_id str

    def __init__(
        self,
        session: EditorSession,
        context: str,
        parent: QWidget | None = None,
    ) -> None:
        if context not in ("type", "instance"):
            raise ValueError(
                f"context must be 'type' or 'instance', got {context!r}")
        super().__init__(session, parent)
        self._context = context
        self._current_node_id: str | None = None
        self._refresh_pending: bool = False

        self._revert_btn.setToolTip(
            "Revert this node file to last git commit after confirmation")

        # -- Left panels --------------------------------------------------
        self._library = QKnowledgeContextLibraryPanel(session, context, self)
        self._palette = QKnowledgePalettePanel(session, self)

        # -- Center: ribbon + canvas --------------------------------------
        self._canvas = QKnowledgeDecompositionCanvasWidget(session, self)
        self._validation_log = self._canvas.take_validation_log_widget()
        self._validation_log.setObjectName("kb_validation_log")

        # -- Right: inspector ---------------------------------------------
        self._inspector = QKnowledgeInspectorPanel(session, parent=self)
        self._connections_panel = QKnowledgeConnectionsPanel(session, self)
        # Backward-compat alias for existing tests/callers.
        self._properties = self._inspector

        self._build_layout()
        self._wire_signals()
        self._apply_styles()
        self._adjust_validation_panel_size()

    def current_node_id(self) -> str | None:
        return self._current_node_id

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.remove_change_listener(self._on_session_change)
        super().closeEvent(event)  # base stops save hint timer

    def showEvent(self, event) -> None:  # type: ignore[override]
        if self._refresh_pending and self._current_node_id is not None:
            self._refresh_pending = False
            try:
                node = self._session.get_node(self._current_node_id)
            except KeyError:
                self._canvas_title.setText(
                    f"(missing) {self._current_node_id}")
            else:
                self._refresh_canvas_title(node)
        super().showEvent(event)

    def open_node(self, node_id: str) -> None:
        """Load *node_id* into the canvas and refresh dependent panels."""
        self._current_node_id = node_id
        self._library.set_current_open_node(node_id)
        self._canvas.open_node(node_id)
        try:
            node = self._session.get_node(node_id)
            self._refresh_canvas_title(node)
            node = self._inspector.prepare_node_for_display(node)
            self._inspector.set_node(node)
            self._connections_panel.set_node(node)
        except KeyError:
            self._canvas_title.setText(f"(missing) {node_id}")
            self._inspector.clear()
            self._connections_panel.set_node(None)
        self.node_opened.emit(node_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def splitter_state(self) -> dict[str, list[int]]:
        """Return current splitter sizes for UI state persistence."""
        return {
            "outer": self._splitter.sizes(),
            "left": self._left_splitter.sizes(),
            "right": self._right_splitter.sizes(),
        }

    def restore_splitter_state(self, state: dict[str, list[int]]) -> None:
        """Restore splitter sizes from a previously saved state dict."""
        outer = state.get("outer")
        left = state.get("left")
        right = state.get("right")
        if outer and len(outer) == 3:
            self._splitter.setSizes(outer)
        if left:
            current_left = self._left_splitter.sizes()
            normalized_left = list(left[: len(current_left)])
            if len(normalized_left) < len(current_left):
                normalized_left.extend(current_left[len(normalized_left):])
            if len(normalized_left) == len(current_left):
                self._left_splitter.setSizes(normalized_left)
        if right and len(right) == 2:
            self._right_splitter.setSizes(right)

    def _build_layout(self) -> None:
        # Left: library, palette (type only), then validation issues at the bottom.
        self._left_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._left_splitter.setObjectName("kb_left_splitter")
        self._left_splitter.addWidget(self._library)
        if self._context == "type":
            self._left_splitter.addWidget(self._palette)
            self._left_splitter.addWidget(self._validation_log)
            self._left_splitter.setStretchFactor(0, 3)
            self._left_splitter.setStretchFactor(1, 1)
            self._left_splitter.setStretchFactor(2, 1)
            self._left_splitter.setSizes([260, 150, 150])
        else:
            self._palette.setVisible(False)
            self._left_splitter.addWidget(self._validation_log)
            self._left_splitter.setStretchFactor(0, 3)
            self._left_splitter.setStretchFactor(1, 1)
            self._left_splitter.setSizes([330, 150])
        self._left_splitter.setHandleWidth(8)
        self._left_splitter.setMinimumWidth(180)

        # Center: ribbon above canvas
        ribbon = self._build_ribbon()
        center_panel = QWidget(self)
        center_panel.setObjectName("kb_center_panel")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(ribbon)
        center_layout.addWidget(self._canvas, stretch=1)

        # Right: inspector + outgoing connections
        self._inspector.setObjectName("kb_inspector_panel")
        self._inspector.setMinimumWidth(340)
        self._connections_panel.setObjectName("kb_connections_panel")
        self._connections_panel.setMinimumWidth(300)

        self._right_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._right_splitter.setObjectName("kb_right_splitter")
        self._right_splitter.addWidget(self._inspector)
        self._right_splitter.addWidget(self._connections_panel)
        self._right_splitter.setHandleWidth(8)
        self._right_splitter.setStretchFactor(0, 2)
        self._right_splitter.setStretchFactor(1, 1)
        self._right_splitter.setSizes([520, 260])

        # Outer horizontal splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setObjectName("kb_outer_splitter")
        self._splitter.addWidget(self._left_splitter)
        self._splitter.addWidget(center_panel)
        self._splitter.addWidget(self._right_splitter)
        self._splitter.setHandleWidth(8)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.setSizes([240, 760, 420])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._splitter, stretch=1)

    def _wire_signals(self) -> None:
        self._library.node_load_requested.connect(self.open_node)
        self._library.node_deleted.connect(self._on_node_deleted)
        self._palette.component_activated.connect(self._on_palette_component)
        self._canvas.row_selected.connect(self._on_canvas_row_selected)
        self._canvas._canvas.selection_changed.connect(self._on_canvas_selection_changed)  # noqa: SLF001
        self._validation_log.panel_height_changed.connect(
            self._adjust_validation_panel_size
        )
        self._session.add_repo_loaded_listener(self._on_repo_loaded)
        self._session.add_change_listener(self._on_session_change)

    def _adjust_validation_panel_size(self, preferred: int | None = None) -> None:
        if preferred is None:
            preferred = self._validation_log.preferred_panel_height()
        sizes = self._left_splitter.sizes()
        if not sizes:
            return
        target = max(32, min(preferred, 280))
        total = max(sum(sizes), target + 1)

        if self._context == "type":
            if len(sizes) < 3:
                return
            other = max(total - target, 120)
            lib = int(other * 0.68)
            palette = max(60, other - lib)
            self._left_splitter.setSizes([lib, palette, target])
            return

        if len(sizes) < 2:
            return
        top = max(total - target, 120)
        self._left_splitter.setSizes([top, target])

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QWidget#canvas_ribbon {{ background: #1e1e1e; border-bottom: 1px solid {EDGE_COLOR}; }}"
            f"QLabel#canvas_title {{ color: {NODE_TEXT_COLOR}; font-weight: 600; }}"
            "QSplitter#kb_outer_splitter::handle:horizontal {"
            " background: #2c2c2c;"
            " border-left: 1px solid #5b5b5b;"
            " border-right: 1px solid #171717;"
            "}"
            "QSplitter#kb_outer_splitter::handle:horizontal:hover {"
            " background: #3a3a3a;"
            " border-left: 1px solid #7b7b7b;"
            "}"
            "QSplitter#kb_left_splitter::handle:vertical {"
            " background: #2c2c2c;"
            " border-top: 1px solid #5b5b5b;"
            " border-bottom: 1px solid #171717;"
            "}"
            "QSplitter#kb_left_splitter::handle:vertical:hover {"
            " background: #3a3a3a;"
            " border-top: 1px solid #7b7b7b;"
            "}"
            "QSplitter#kb_right_splitter::handle:vertical {"
            " background: #2c2c2c;"
            " border-top: 1px solid #5b5b5b;"
            " border-bottom: 1px solid #171717;"
            "}"
            "QSplitter#kb_right_splitter::handle:vertical:hover {"
            " background: #3a3a3a;"
            " border-top: 1px solid #7b7b7b;"
            "}"
            "QSplitter#kb_left_splitter { border: 1px solid #4a4a4a; }"
            "QSplitter#kb_right_splitter { border: 1px solid #4a4a4a; }"
            "QWidget#kb_center_panel { border: 1px solid #4a4a4a; }"
            "QWidget#kb_inspector_panel { border: 1px solid #4a4a4a; }"
            "QWidget#kb_connections_panel { border: 1px solid #4a4a4a; }"
        )

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_repo_loaded(self, _path: object) -> None:
        """Handle repository reloads by refreshing current open node if any."""
        if self._current_node_id is None:
            return
        try:
            self._session.get_node(self._current_node_id)
        except KeyError:
            self._clear_current_node_state()
            return
        self.open_node(self._current_node_id)

    def _on_node_deleted(self, node_id: str) -> None:
        if self._current_node_id == node_id:
            self._clear_current_node_state()

    def _clear_current_node_state(self) -> None:
        self._current_node_id = None
        self._refresh_pending = False
        self._library.set_current_open_node(None)
        self._canvas_title.setText("No item loaded")
        self._inspector.clear()
        self._connections_panel.set_node(None)

    def _on_session_change(self, event: SessionChangeEvent) -> None:
        change_type = event.change_type
        if change_type not in {"node", "repo_loaded", "dirty_changed"}:
            return
        if self._current_node_id is None:
            return
        if (
            change_type == "node"
            and not event.touches_any({self._current_node_id})
        ):
            return
        if not self.isVisible():
            self._refresh_pending = True
            return
        try:
            node = self._session.get_node(self._current_node_id)
        except KeyError:
            self._canvas_title.setText(f"(missing) {self._current_node_id}")
            return
        self._refresh_canvas_title(node)

    def _on_dirty_changed(self, _is_dirty: bool) -> None:
        if self._current_node_id is None:
            return
        try:
            node = self._session.get_node(self._current_node_id)
        except KeyError:
            return
        self._refresh_canvas_title(node)

    def _refresh_canvas_title(self, node: Node) -> None:
        suffix = "*" if self._session.is_dirty else ""
        self._canvas_title.setText(f"{node.name}  ({node.category}){suffix}")

    def _on_palette_component(self, component_id: str) -> None:
        if self._context == "type":
            self._handle_type_palette(component_id)
        else:
            self._handle_instance_palette(component_id)

    def _on_canvas_row_selected(self, slot_name: str) -> None:
        if self._current_node_id is None:
            return
        try:
            current_node = self._session.get_node(self._current_node_id)
        except KeyError:
            return
        # Keep inspector synced with repository mutations done by canvas DnD
        # so freshly added slots can be edited immediately.
        self._inspector.set_node(current_node)
        if slot_name.startswith("__group_"):
            self._inspector.select_slot(None)
            return
        self._inspector.select_slot(slot_name)

    def _on_canvas_selection_changed(self) -> None:
        if self._current_node_id is None:
            return
        if self._canvas._canvas.selected_items():  # noqa: SLF001
            return
        self._inspector.select_slot(None)

    def _handle_type_palette(self, component_id: str) -> None:
        if self._current_node_id is None:
            QMessageBox.information(
                self, "No type loaded", "Load a type first.")
            return
        if component_id not in (PALETTE_PROPERTY, PALETTE_SLOT_LITERAL, PALETTE_SLOT_REF):
            return
        is_ref = component_id == PALETTE_SLOT_REF
        slot = self._ask_slot(is_ref=is_ref)
        if slot is None:
            return
        try:
            node_id = self._current_node_id
            result = self._session._io.add_slot_to_type(  # noqa: SLF001
                node_id, slot.model_dump())
            if not result.ok:
                raise ValueError(result.error_message or "Failed to add slot")
            self._session.notify_io_mutation("node")
            self.open_node(self._current_node_id)
        except KeyError as exc:
            QMessageBox.warning(self, "Add Slot Failed",
                                f"Node not found: {exc}")
        except ValueError as exc:
            QMessageBox.warning(self, "Add Slot Failed", str(exc))

    def _handle_instance_palette(self, component_id: str) -> None:
        if self._current_node_id is None:
            QMessageBox.information(
                self, "No instance loaded", "Load an instance first.")
            return
        if not component_id.startswith(PALETTE_SLOT_VALUE_PREFIX):
            return
        slot_name = component_id[len(PALETTE_SLOT_VALUE_PREFIX):]
        node = self._session.get_node(self._current_node_id)
        type_id = node.type_id
        if type_id is None:
            QMessageBox.warning(
                self, "No Type", "Instance has no associated type.")
            return
        try:
            type_node = self._session.get_node(str(type_id))
        except KeyError:
            QMessageBox.warning(self, "Missing Type",
                                f"Type {type_id} not found.")
            return
        tv = as_type(type_node)
        slot = next((s for s in tv.slots if s.name == slot_name), None)
        if slot is None:
            return
        if not slot.effective_value_mode().allows_reference:
            value, ok = QInputDialog.getText(
                self, f"Set '{slot_name}'", f"Value for {slot_name}:")
            if not ok:
                return
            node_id = self._current_node_id
            result = self._session._io.set_slot_value(  # noqa: SLF001
                node_id, slot_name, value)
            if not result.ok:
                QMessageBox.warning(
                    self,
                    "Set Slot Failed",
                    result.error_message or "Unable to set slot value.",
                )
                return
            self._session.notify_io_mutation("node")
        else:
            picker = QKnowledgeRefPickerDialog(
                self._session, ref_type=slot.ref_type, slot_name=slot_name, parent=self
            )
            if picker.exec() != QDialog.DialogCode.Accepted:
                return
            ref_id = picker.selected_node_id()
            if ref_id is None:
                return
            node_id = self._current_node_id
            result = self._session._io.set_slot_value(  # noqa: SLF001
                node_id, slot_name, ref_id)
            if not result.ok:
                QMessageBox.warning(
                    self,
                    "Set Reference Failed",
                    result.error_message or "Unable to set slot reference.",
                )
                return
            self._session.notify_io_mutation("node")
        self.open_node(self._current_node_id)

    def _ask_slot(self, *, is_ref: bool) -> NodeSlot | None:
        name, ok = QInputDialog.getText(self, "Slot Name", "Slot name:")
        if not ok or not name.strip():
            return None
        ref_type: str | None = None
        if is_ref:
            ref_type_text, ok2 = QInputDialog.getText(
                self, "Ref Type", "Reference type (e.g. 'term'):")
            if not ok2:
                return None
            ref_type = ref_type_text.strip() or None
        return NodeSlot(
            name=name.strip(),
            source=SlotSource.REF if is_ref else SlotSource.LITERAL,
            required=True,
            ref_type=ref_type,
        )

    def _on_save(self) -> None:
        # Primitive edits are persisted immediately via apply_mutation.
        return None

    def _on_save_all(self) -> None:
        self._on_save()

    def _on_revert(self) -> None:
        if self._current_node_id is None:
            return
        reopen_node_id = self._current_node_id
        try:
            root = self._session.repository_root
            if root is not None:
                node_paths = self._session.node_storage_paths(root)
                target = node_paths.get(reopen_node_id)
                if target is not None:
                    rel_path = target.relative_to(root).as_posix()
                    core_kind = "type" if self._context == "type" else "instance"
                    git_result = self._confirm_and_revert_file_to_last_commit(
                        core_label=core_kind,
                        rel_path=rel_path,
                    )
                    if git_result is False:
                        return
            if self._session.repository_root is not None:
                self._session.load()
            if reopen_node_id is not None:
                try:
                    self._session.get_node(reopen_node_id)
                except KeyError:
                    reopen_node_id = None

            if reopen_node_id is not None:
                self.open_node(reopen_node_id)
            else:
                self._current_node_id = None
                self._library.set_current_open_node(None)
                self._canvas_title.setText("No item loaded")
                self._inspector.clear()
                self._connections_panel.set_node(None)
                self._palette.set_active_node(None)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Revert Failed", str(exc))


__all__ = ["QKnowledgePrimitiveTabWidget"]

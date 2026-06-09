"""Decomposition canvas widget â€” multi-card graph layout for one knowledge node."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QMessageBox, QVBoxLayout, QWidget

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.knowledge.ui.widgets.validation_log import (
    QKnowledgeValidationLogWidget,
    ValidationErrorEntry,
)
from lks_utils.knowledge.display_color import (
    effective_link_type_display_color,
    effective_node_display_color,
)
from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
    header_color_for_classification,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.editor_session_types import SessionChangeEvent
from lks_utils.knowledge.instance_validator import VALIDATION_ERRORS_PROP
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.mutator import Mutator
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_slot import NodeSlot, SlotSource
from lks_utils.knowledge.models.type import as_type, is_type
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.ui.components.decomposition_layout_constants import (
    CHILD_GAP as _CHILD_GAP,
    CHILD_H as _CHILD_H,
    CHILD_W as _CHILD_W,
    INSTANCE_ROOT_W as _INSTANCE_ROOT_W,
    MIME_KNOWLEDGE_PALETTE_COMPONENT,
    ROOT_H_BASE as _ROOT_H_BASE,
    ROOT_W as _ROOT_W,
    ROOT_X0 as _ROOT_X0,
    ROOT_Y0 as _ROOT_Y0,
    ROW_H as _ROW_H,
    TYPE_CARD_GAP as _TYPE_CARD_GAP,
    TYPE_CARD_W as _TYPE_CARD_W,
    TYPE_PROPERTY_EDGE_LABEL as _TYPE_PROPERTY_EDGE_LABEL,
    VERT_GAP as _VERT_GAP,
)
from lks_utils.knowledge.ui.components.decomposition_layout_helpers import card_height as _card_height
from lks_utils.knowledge.ui.widgets.field_node_canvas_object import QKnowledgeFieldNodeCanvasObject
from lks_utils.knowledge.ui.widgets.knowledge_decomposition_canvas import _KnowledgeDecompositionCanvas
from lks_utils.knowledge.ui.widgets.knowledge_edge_canvas_object import _KnowledgeEdgeCanvasObject
from lks_utils.knowledge.ui.widgets.port_stub_item import QKnowledgePortStubCanvasObject
from lks_utils.knowledge.ui.components.field_row_factory import (
    FieldRow,
    FieldRowInheritance,
)
from lks_utils.knowledge.ui.components.palette_panel import PALETTE_PROPERTY, PALETTE_SLOT_LITERAL, PALETTE_SLOT_REF
from lks_utils.knowledge.ui.components.ref_picker_dialog import QKnowledgeRefPickerDialog


class QKnowledgeDecompositionCanvasWidget(QWidget):
    """Multi-card decomposition graph for the currently loaded knowledge node.

    Shows the root node as one card and decomposes its slots into child cards
    connected by bezier edges. Accepts both node-id drops (from the library
    panel) and palette-component drops (from the palette panel).
    """

    row_selected = Signal(str)

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._current_node_id: str | None = None
        self._current_slots_by_name: dict[str, NodeSlot] = {}
        self._collapse_state_by_node_id: dict[str,
                                              dict[str, dict[str, bool]]] = {}
        self._collapse_state_capture_node_id: str | None = None

        self._canvas_objects: list[CanvasObject] = []
        self._field_items: list[QKnowledgeFieldNodeCanvasObject] = []

        self._canvas = _KnowledgeDecompositionCanvas(
            self, MIME_KNOWLEDGE_PALETTE_COMPONENT, self)
        self._canvas.setMinimumSize(720, 420)
        self._canvas.selection_changed.connect(self._sync_selection_visuals)

        self._validation_log = QKnowledgeValidationLogWidget(parent=self)
        self._validation_log.focus_node_requested.connect(
            self._on_validation_entry_clicked)

        self._build_layout()
        self._apply_styles()
        self._session.add_change_listener(self._on_session_change)

    @property
    def _mutator(self) -> Mutator:
        """Compatibility access for tests and legacy call sites.

        Always bind to the current IO repository snapshot to avoid stale repository
        references after session reload/swap operations.
        """
        return Mutator(self._session.repository)  # noqa: SLF001

    @staticmethod
    def _slot_ref_link_ids_for_node(repo: Repository, node_id: str) -> set[str]:
        """Return slot_ref link ids sourced from *node_id* in *repo*."""
        return {
            str(link.id)
            for link in repo.list_links()
            if link.link_type_id == SLOT_REF_LINK_TYPE_ID and link.source_node_id == node_id
        }

    @staticmethod
    def _slot_ref_target_ids_for_slot(repo: Repository, node_id: str, slot_name: str) -> list[str]:
        """Return slot_ref target ids for one (node, slot) pair."""
        return [
            str(link.target_node_id)
            for link in repo.list_links()
            if (
                link.link_type_id == SLOT_REF_LINK_TYPE_ID
                and link.source_node_id == node_id
                and link.source_slot_name == slot_name
            )
        ]

    def _matches_ref_type_token(self, dropped: Node, ref_type: str | None) -> bool:
        """Return True when *dropped* is a valid target for *ref_type* token."""
        if ref_type is None:
            return False
        token = ref_type.strip()
        if token == "":
            return False

        matching_ids = {
            str(candidate.id)
            for candidate in self._session.reference_options(token)
        }
        if str(dropped.id) in matching_ids:
            return True
        return False

    @staticmethod
    def _extract_ref_target_id(value: object) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    def _slot_display_value(self, node: Node, slot: NodeSlot) -> object:
        """Return display payload for a slot, preferring slot_ref link assets."""
        if slot.source.is_reference:
            target_ids = self._slot_ref_target_ids_for_slot(
                self._session.repository,  # noqa: SLF001
                str(node.id),
                slot.name,
            )
            if target_ids:
                if slot.source == SlotSource.REF_LIST:
                    return target_ids
                return target_ids[0]
        return node.props.get(slot.name)

    def _apply_slot_mutation(
        self,
        *,
        node_id: str,
        label: str,
        mutate: Callable[[Mutator], None],
    ) -> None:
        """Apply one slot mutation and mark touched node/link assets for persistence."""

        def _mutate(repo: Repository) -> set[str]:
            before_link_ids = self._slot_ref_link_ids_for_node(repo, node_id)
            mutate(Mutator(repo))
            after_link_ids = self._slot_ref_link_ids_for_node(repo, node_id)
            return {node_id, *before_link_ids, *after_link_ids}

        result = self._session.io_apply_op(_mutate)
        if not result.ok:
            raise ValueError(
                result.error_message or f"Failed to apply mutation: {label}")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.remove_change_listener(self._on_session_change)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_node(self, node_id: str) -> None:
        """Load *node_id* into the decomposition canvas."""
        self._collapse_state_capture_node_id = self._current_node_id
        self._current_node_id = node_id
        self._refresh_current_node()

    def take_validation_log_widget(self) -> QKnowledgeValidationLogWidget:
        """Detach and return the live validation log widget for external layouting."""
        layout = self.layout()
        if isinstance(layout, QVBoxLayout):
            layout.removeWidget(self._validation_log)
        self._validation_log.setParent(None)
        return self._validation_log

    def can_accept_drop(self, node_id: str, position: QPointF) -> bool:
        """Return True if dropping the library node makes sense at *position*."""
        try:
            dropped = self._session.get_node(node_id)
        except KeyError:
            return False
        if self._current_node_id is None:
            return True
        row = self._row_at_canvas_position(position)
        if row is None:
            return True
        slot = self._current_slots_by_name.get(
            row.slot_name) if row is not None else None
        if slot is not None and slot.ref_type is not None:
            return self._matches_ref_type_token(dropped, slot.ref_type)
        return any(
            candidate.source.is_reference
            and self._matches_ref_type_token(dropped, candidate.ref_type)
            for candidate in self._current_slots_by_name.values()
        )

    def apply_drop(self, node_id: str, position: QPointF) -> bool:
        """Apply a library-node drop onto the canvas."""
        try:
            dropped = self._session.get_node(node_id)
        except KeyError:
            return False
        if self._current_node_id is None:
            self.open_node(node_id)
            return True
        row = self._row_at_canvas_position(position)
        if row is None:
            self.open_node(node_id)
            return True
        slot_name = row.slot_name if row is not None else ""
        slot = self._current_slots_by_name.get(slot_name)
        if slot is None or slot.ref_type is None or not self._matches_ref_type_token(dropped, slot.ref_type):
            for candidate_name, candidate in self._current_slots_by_name.items():
                if candidate.source.is_reference and self._matches_ref_type_token(dropped, candidate.ref_type):
                    slot_name = candidate_name
                    slot = candidate
                    break
        if slot is None or slot.ref_type is None or not self._matches_ref_type_token(dropped, slot.ref_type):
            return False
        self._apply_slot_mutation(
            node_id=self._current_node_id,
            label="decomposition_canvas_apply_drop_ref",
            mutate=lambda mutator: mutator.set_slot_value(
                self._current_node_id,
                slot_name,
                str(dropped.id),
            ),
        )
        self._refresh_current_node()
        return True

    def can_accept_palette_drop(self, component_id: str) -> bool:
        """Return True if *component_id* from the palette can be dropped here."""
        if self._current_node_id is None:
            return False
        try:
            node = self._session.get_node(self._current_node_id)
        except KeyError:
            return False
        return is_type(node) and component_id in (PALETTE_PROPERTY, PALETTE_SLOT_LITERAL, PALETTE_SLOT_REF)

    def apply_palette_drop(self, component_id: str) -> bool:
        """Apply a palette-component drop (type nodes only)."""
        if self._current_node_id is None:
            return False
        try:
            node = self._session.get_node(self._current_node_id)
        except KeyError:
            return False
        if not is_type(node):
            return False
        return self._apply_type_palette(component_id)

    def select_slot_by_name(self, slot_name: str) -> None:
        """Programmatically select a slot by name, emitting row_selected signal.

        This is used after palette drops to auto-select the newly-created slot,
        ensuring the property inspector immediately displays its details.
        """
        for item in self._field_items:
            if getattr(item, "_selection_slot_name", None) == slot_name:
                # Select the item visually on the canvas
                self._canvas.select_object(item)
                # Manually emit row_selected signal since programmatic selection
                # doesn't trigger the mouse event that would normally emit it
                self.row_selected.emit(slot_name)
                return

    def delete_selected_components(self) -> bool:
        """Delete selected non-root graph components semantically, not visually.

        For instance nodes the canvas schema is immutable — this method returns
        False without mutating anything, preventing Delete-key structural changes.
        """
        selected_objects = [
            item for item in self._canvas.selected_objects()
            if isinstance(item, QKnowledgeFieldNodeCanvasObject)
        ]
        if not selected_objects:
            return False
        if self._current_node_id is None:
            self._canvas.clear_selection()
            return True
        try:
            node = self._session.get_node(self._current_node_id)
        except KeyError:
            self._canvas.clear_selection()
            return True

        # Schema-related canvas nodes are immutable for instance nodes.
        if not is_type(node):
            return False

        handled = False
        for item in selected_objects:
            if getattr(item, "_is_root", False):
                continue
            slot_name = getattr(item, "_selection_slot_name", None)
            if not isinstance(slot_name, str) or not slot_name:
                continue
            try:
                result = self._session.io_remove_slot_from_type(
                    self._current_node_id, slot_name)
                if not result.ok:
                    continue
            except Exception:
                continue
            handled = True

        self._canvas.clear_selection()
        if handled:
            self._refresh_current_node()
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(4)
        root.addWidget(self._canvas, stretch=1)
        root.addWidget(self._validation_log, stretch=0)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
        )

    def _on_session_change(self, event: SessionChangeEvent) -> None:
        change_type = event.change_type
        if self._current_node_id is None:
            return
        if (
            change_type == "node"
            and not event.touches_any({self._current_node_id})
        ):
            return
        if change_type in {"node", "repo_loaded", "repo_saved", "dirty_changed"}:
            self._refresh_current_node()

    def _clear_canvas(self) -> None:
        self._remember_collapse_state(self._collapse_state_capture_node_id)
        self._collapse_state_capture_node_id = None
        for item in self._canvas_objects:
            self._canvas.remove_object(item)
        self._canvas_objects = []
        self._field_items = []
        self._current_slots_by_name = {}

    def _add_object(self, item: CanvasObject) -> None:
        self._canvas.add_object(item)
        self._canvas_objects.append(item)
        if isinstance(item, QKnowledgeFieldNodeCanvasObject):
            self._field_items.append(item)
            self._restore_item_collapse_state(item)

    def _remember_collapse_state(self, node_id: str | None = None) -> None:
        target_node_id = node_id or self._current_node_id
        if target_node_id is None:
            return
        state = {
            item.node_id: item.collapse_state()
            for item in self._field_items
            if item.collapse_state()
        }
        if state:
            self._collapse_state_by_node_id[target_node_id] = state

    def _restore_item_collapse_state(self, item: QKnowledgeFieldNodeCanvasObject) -> None:
        if self._current_node_id is None:
            return
        state = self._collapse_state_by_node_id.get(
            self._current_node_id, {}).get(item.node_id)
        if state:
            item.apply_collapse_state(state)

    def _refresh_current_node(self) -> None:
        self._clear_canvas()
        if self._current_node_id is None:
            self._validation_log.set_validation_errors([])
            return
        try:
            node = self._session.get_node(self._current_node_id)
        except KeyError:
            self._validation_log.set_validation_errors([])
            return
        if is_type(node):
            self._build_type_decomposition(node)
        else:
            self._build_instance_decomposition(node)
        self._canvas.fit_to_content(buffer_world_px=40.0)
        self._canvas.camera.set_zoom(
            min(self._canvas.camera.view().zoom, 1.35))
        self._sync_selection_visuals()
        self._update_validation_log()

    def _sync_selection_visuals(self) -> None:
        selected = {
            item for item in self._canvas.selected_objects()
            if isinstance(item, QKnowledgeFieldNodeCanvasObject)
        }
        active = self._canvas.active_selected_object()
        for item in self._field_items:
            item.selected = item in selected
            item.active_selected = item is active

    # ------ TYPE decomposition ----------------------------------------

    def _build_type_decomposition(self, node: Node) -> None:
        tv = as_type(node)
        slots = tv.slots
        root_rows = [
            FieldRow("nested", "kind", "kind", "type", []),
            FieldRow("nested", "category",
                     "category", tv.category or "(none)", []),
            FieldRow("nested", "slot_count",
                     "slot_count", str(len(slots)), []),
            FieldRow("nested", "description",
                     "description", node.description or "(none)", []),
        ]
        root_h = _card_height(root_rows)
        root_object = QKnowledgeFieldNodeCanvasObject(
            node_id=str(node.id),
            node_name=f"{node.name}  (_type)",
            x=_ROOT_X0,
            y=_ROOT_Y0,
            width=_ROOT_W,
            height=root_h,
            rows=root_rows,
            is_root=True,
            on_row_selected=self._on_row_selected,
            on_select=self._on_item_selected,
            header_bg_color=effective_node_display_color(node),
        )
        self._add_object(root_object)
        root_object.set_validation_errors(self._validation_errors_dict(node))
        self._add_ad_hoc_port_stubs(node, root_object)

        if not slots:
            return

        n = len(slots)
        total_child_w = n * _CHILD_W + max(0, n - 1) * _CHILD_GAP
        root_cx = _ROOT_X0 + _ROOT_W / 2.0
        start_x = root_cx - total_child_w / 2.0
        child_y1 = _ROOT_Y0 - _VERT_GAP          # child visual top (Y-UP)

        for i, slot in enumerate(slots):
            child_x = start_x + i * (_CHILD_W + _CHILD_GAP)
            mode = slot.effective_value_mode().value
            target = slot.target_type or slot.ref_type or "(none)"
            badges = "required" if slot.required else "optional"
            if slot.constraints:
                badges += " +constraints"
            child_rows = [
                FieldRow(
                    kind="property_contract",
                    label=slot.name,
                    slot_name=slot.name,
                    value=f"{mode} -> {target}",
                    controls=[],
                    nested_rows=[
                        FieldRow("nested", "kind", slot.name,
                                 "property_contract", []),
                        FieldRow("nested", "value_type", slot.name,
                                 slot.value_type, []),
                        FieldRow("nested", "badges", slot.name,
                                 badges, []),
                        FieldRow(
                            "nested",
                            "counts",
                            slot.name,
                            f"{slot.cardinality.value}:{slot.min_count if slot.min_count is not None else 0}..{slot.max_count if slot.max_count is not None else '*'}",
                            [],
                        ),
                        FieldRow("nested", "validation_status",
                                 slot.name, "ok", []),
                    ],
                )
            ]
            child_h = _card_height(child_rows)
            child_y0 = child_y1 - child_h
            child_item = QKnowledgeFieldNodeCanvasObject(
                node_id=f"{node.id}:slot:{slot.name}",
                node_name=slot.name,
                x=child_x,
                y=child_y0,
                width=_CHILD_W,
                height=child_h,
                rows=child_rows,
                on_row_selected=self._on_row_selected,
                on_select=self._on_item_selected,
                selection_slot_name=slot.name,
                header_bg_color=self._header_color_for_slot(slot),
                header_subtitle=mode,
            )
            self._add_object(child_item)
            child_cx = child_x + _CHILD_W / 2.0
            self._add_object(_KnowledgeEdgeCanvasObject(
                x0=root_cx, y0=_ROOT_Y0, x1=child_cx, y1=child_y1,
                label=_TYPE_PROPERTY_EDGE_LABEL,
                arrow_at_end=True,
            ))

    # ------ INSTANCE decomposition ------------------------------------

    def _build_instance_decomposition(self, node: Node) -> None:
        slots = self._slots_for_instance(node)
        self._current_slots_by_name = {s.name: s for s in slots}
        literal_slots = [s for s in slots if not s.source.is_reference]
        ref_slots = [s for s in slots if s.source.is_reference]

        # ── Root instance card ──────────────────────────────────────────────────────────────────────
        root_rows: list[FieldRow] = []
        direct_literal_rows: list[FieldRow] = []
        inherited_literal_rows: list[FieldRow] = []
        invalid_slots = self._invalid_slot_names(node)
        for slot in literal_slots:
            value = self._slot_display_value(node, slot)
            summary = self._format_value_summary(value)
            badges = "required" if slot.required else "optional"
            status = "invalid" if slot.name in invalid_slots else "ok"
            is_local_override = slot.name in node.props
            inheritance = FieldRowInheritance(
                is_inherited=not is_local_override,
                is_overridden=is_local_override,
                scope="local_instance" if is_local_override else "type_default",
            )
            row = FieldRow(
                kind="literal",
                label=slot.name,
                slot_name=slot.name,
                value=summary,
                controls=[],
                nested_rows=[
                    FieldRow("nested", "kind",
                             slot.name, "value", []),
                    FieldRow(
                        "nested", "value_mode", slot.name, slot.effective_value_mode().value, []),
                    FieldRow(
                        "nested", "target", slot.name, slot.target_type or slot.ref_type or "(none)", []),
                    FieldRow("nested", "badges",
                             slot.name, badges, []),
                    FieldRow(
                        "nested", "counts", slot.name, self._value_counts_text(value), []),
                    FieldRow(
                        "nested", "validation_status", slot.name, status, []),
                ],
                inheritance=inheritance,
            )
            if slot.name in node.props:
                direct_literal_rows.append(row)
            else:
                inherited_literal_rows.append(row)

        if direct_literal_rows:
            root_rows.append(
                FieldRow(
                    kind="group_header",
                    label="Direct Properties",
                    slot_name="__group_direct__",
                    value=str(len(direct_literal_rows)),
                    controls=[],
                )
            )
            root_rows.extend(direct_literal_rows)

        if inherited_literal_rows:
            root_rows.append(
                FieldRow(
                    kind="group_header",
                    label="Inherited Properties",
                    slot_name="__group_inherited__",
                    value=str(len(inherited_literal_rows)),
                    controls=[],
                )
            )
            root_rows.extend(inherited_literal_rows)

        if not slots:
            for k, v in node.props.items():
                root_rows.append(FieldRow("literal", k, k, v, []))

        root_h = _card_height(root_rows)
        root_w = _INSTANCE_ROOT_W
        root_y0 = _ROOT_Y0
        root_y1 = root_y0 + root_h
        root_cx = _ROOT_X0 + root_w / 2.0

        root_object = QKnowledgeFieldNodeCanvasObject(
            node_id=str(node.id),
            node_name=f"{node.name}  ({node.category})",
            x=_ROOT_X0,
            y=root_y0,
            width=root_w,
            height=root_h,
            rows=root_rows,
            is_root=True,
            invalid_slot_names=self._invalid_slot_names(node),
            on_pick_ref=self._on_pick_ref,
            on_clear_ref=self._on_clear_ref,
            on_row_selected=self._on_row_selected,
            on_select=self._on_item_selected,
            header_bg_color=self._header_color_for_node(node),
        )
        self._add_object(root_object)
        root_object.set_validation_errors(self._validation_errors_dict(node))
        self._add_ad_hoc_port_stubs(node, root_object)

        # ── Type inheritance chain (above root) ────────────────────────────────────────────
        type_chain = self._type_chain_for_instance(node)
        if type_chain:
            from lks_utils.knowledge.links.link_types.link_type_system import (
                EXTENDS_LINK_TYPE_ID,
                INSTANCE_OF_LINK_TYPE_ID,
            )

            type_center_x = root_cx
            type_x0 = type_center_x - (_TYPE_CARD_W * 0.5)
            type_y0 = root_y1 + _VERT_GAP
            # Render nearest type closest to root, then stack ancestors above it.
            direct_to_root = list(reversed(type_chain))

            try:
                extends_type = self._session.get_link_type(
                    EXTENDS_LINK_TYPE_ID)
                extends_color = effective_link_type_display_color(extends_type)
            except KeyError:
                extends_color = EDGE_COLOR
            try:
                instance_of_type = self._session.get_link_type(
                    INSTANCE_OF_LINK_TYPE_ID)
                instance_of_color = effective_link_type_display_color(
                    instance_of_type)
            except KeyError:
                instance_of_color = EDGE_COLOR

            prev_child_top_y: float | None = None
            for type_node in direct_to_root:
                tv = as_type(type_node)
                type_rows = [
                    FieldRow(
                        "nested", f"{s.name}  [{s.source.value}]", s.name, s.source.value, [])
                    for s in tv.slots
                ]
                if not type_rows:
                    type_rows = [
                        FieldRow("nested", "(no own slots)", "(no own slots)", "", [])]
                t_h = _card_height(type_rows)
                t_x = type_x0
                t_top_y = type_y0 + t_h

                self._add_object(QKnowledgeFieldNodeCanvasObject(
                    node_id=str(type_node.id),
                    node_name=f"{type_node.name}  (_type)",
                    x=t_x,
                    y=type_y0,
                    width=_TYPE_CARD_W,
                    height=t_h,
                    rows=type_rows,
                    on_row_selected=self._on_row_selected,
                    on_select=self._on_item_selected,
                    header_bg_color=effective_node_display_color(type_node),
                ))

                # extends edge: parent (above) -> child (below)
                if prev_child_top_y is not None:
                    self._add_object(_KnowledgeEdgeCanvasObject(
                        x0=type_center_x,
                        y0=type_y0,
                        x1=type_center_x,
                        y1=prev_child_top_y,
                        color=extends_color,
                        label="extends",
                        dashed=True,
                        arrow_at_end=True,
                    ))
                prev_child_top_y = t_top_y
                type_y0 = t_top_y + _TYPE_CARD_GAP

            # instance_of edge: root card top-center -> direct type (outgoing from root)
            direct_type_bottom_y = root_y1 + _VERT_GAP
            self._add_object(_KnowledgeEdgeCanvasObject(
                x0=root_cx,
                y0=root_y1,
                x1=type_center_x,
                y1=direct_type_bottom_y,
                color=instance_of_color,
                label="instance_of",
                dashed=True,
                arrow_at_end=True,
            ))

        # ── Ref-slot children (below root) ──────────────────────────────────────────────────
        n_ref = len(ref_slots)
        if not n_ref:
            return

        total_child_w = n_ref * _CHILD_W + max(0, n_ref - 1) * _CHILD_GAP
        start_x = root_cx - total_child_w / 2.0
        # top of child cards (below root in Y-UP)
        child_y1 = root_y0 - _VERT_GAP

        for i, slot in enumerate(ref_slots):
            child_x = start_x + i * (_CHILD_W + _CHILD_GAP)
            value = self._slot_display_value(node, slot)
            status = "invalid" if slot.name in invalid_slots else "ok"
            child_row = FieldRow(
                kind="ref_summary",
                label=slot.name,
                slot_name=slot.name,
                value=self._format_value_summary(value),
                controls=[],
                nested_rows=[
                    FieldRow("nested", "kind",
                             slot.name, "value", []),
                    FieldRow(
                        "nested", "value_mode", slot.name, slot.effective_value_mode().value, []),
                    FieldRow(
                        "nested", "target", slot.name, slot.target_type or slot.ref_type or "(none)", []),
                    FieldRow(
                        "nested", "badges", slot.name, "required" if slot.required else "optional", []),
                    FieldRow(
                        "nested", "counts", slot.name, self._value_counts_text(value), []),
                    FieldRow(
                        "nested", "validation_status", slot.name, status, []),
                ],
            )
            child_h = _card_height([child_row])
            child_y0_card = child_y1 - child_h
            child_item = QKnowledgeFieldNodeCanvasObject(
                node_id=f"{node.id}:ref:{slot.name}",
                node_name=slot.name,
                x=child_x,
                y=child_y0_card,
                width=_CHILD_W,
                height=child_h,
                rows=[child_row],
                on_pick_ref=self._on_pick_ref,
                on_clear_ref=self._on_clear_ref,
                on_row_selected=self._on_row_selected,
                on_select=self._on_item_selected,
                selection_slot_name=slot.name,
                header_bg_color=self._header_color_for_slot(slot),
                header_subtitle=slot.ref_type or slot.effective_value_mode().value,
            )
            self._add_object(child_item)
            child_cx = child_x + _CHILD_W / 2.0
            self._add_object(_KnowledgeEdgeCanvasObject(
                x0=root_cx, y0=root_y0, x1=child_cx, y1=child_y1,
            ))

    # ------ Palette drop helpers ------------------------------------

    def _apply_type_palette(self, component_id: str) -> bool:
        if component_id not in (PALETTE_PROPERTY, PALETTE_SLOT_LITERAL, PALETTE_SLOT_REF):
            return False
        is_ref = component_id == PALETTE_SLOT_REF
        slot_name = self._next_slot_name(is_ref=is_ref)
        slot = NodeSlot(
            name=slot_name,
            source=SlotSource.REF if is_ref else SlotSource.LITERAL,
            required=False,
        )
        try:
            result = self._session.io_add_slot_to_type(
                self._current_node_id, slot.model_dump())
            if not result.ok:
                self._show_op_error(
                    result.error_message or "Failed to add slot")
                return False
        except (KeyError, ValueError) as exc:
            self._show_op_error(str(exc))
            return False
        self._refresh_current_node()
        # Auto-select the newly-created slot so inspector immediately shows its settings
        self.select_slot_by_name(slot_name)
        return True

    def _show_op_error(self, message: str) -> None:
        """Show a user-readable error dialog for a failed palette operation."""
        QMessageBox.warning(self, "Operation failed", message)

    def _next_slot_name(self, *, is_ref: bool) -> str:
        prefix = "ref" if is_ref else "slot"
        if self._current_node_id is None:
            return f"{prefix}_1"
        try:
            node = self._session.get_node(self._current_node_id)
            merged_slots = self._session.get_type_slots(  # noqa: SLF001
                self._current_node_id,
            )
        except (KeyError, ValueError):
            return f"{prefix}_1"
        if not is_type(node):
            return f"{prefix}_1"
        existing = {slot.name for slot in merged_slots}
        n = 1
        while f"{prefix}_{n}" in existing:
            n += 1
        return f"{prefix}_{n}"

    # ------ Shared helpers ------------------------------------------

    def _add_ad_hoc_port_stubs(self, node: Node, root_object: QKnowledgeFieldNodeCanvasObject) -> None:
        node_id = str(node.id)
        node_names_by_id = {
            str(candidate.id): candidate.name for candidate in self._session.list_nodes()
        }
        link_types = {str(lt.id): lt for lt in self._session.list_link_types()}
        link_type_names = {
            link_type_id: link_type.name
            for link_type_id, link_type in link_types.items()
        }
        inverse_link_type_names = {
            link_type_id: link_type.inverse_name
            for link_type_id, link_type in link_types.items()
        }
        links = [
            link
            for link in self._session.list_links()
            if link.link_type_id != SLOT_REF_LINK_TYPE_ID
            and (
                link.link_type_id not in link_types
                or not link_types[link.link_type_id].is_system
            )
            and (link.source_node_id == node_id or link.target_node_id == node_id)
        ]
        if not links:
            return

        outgoing = [link for link in links if link.source_node_id == node_id]
        incoming = [link for link in links if link.target_node_id == node_id]
        node_bounds = root_object.bounds()

        for index, link in enumerate(outgoing):
            self._add_object(
                QKnowledgePortStubCanvasObject(
                    node_id=node_id,
                    node_bounds=node_bounds,
                    direction="outgoing",
                    index=index,
                    count=len(outgoing),
                    link_type_id=link.link_type_id,
                    link_type_name=link_type_names.get(link.link_type_id),
                    peer_node_id=link.target_node_id,
                    peer_node_name=node_names_by_id.get(link.target_node_id),
                    display_color=effective_link_type_display_color(
                        link_types[link.link_type_id]
                    ) if link.link_type_id in link_types else None,
                )
            )

        for index, link in enumerate(incoming):
            self._add_object(
                QKnowledgePortStubCanvasObject(
                    node_id=node_id,
                    node_bounds=node_bounds,
                    direction="incoming",
                    index=index,
                    count=len(incoming),
                    link_type_id=link.link_type_id,
                    link_type_name=link_type_names.get(link.link_type_id),
                    inverse_link_type_name=inverse_link_type_names.get(
                        link.link_type_id),
                    peer_node_id=link.source_node_id,
                    peer_node_name=node_names_by_id.get(link.source_node_id),
                    display_color=effective_link_type_display_color(
                        link_types[link.link_type_id]
                    ) if link.link_type_id in link_types else None,
                )
            )

    def _header_color_for_node(self, node: Node) -> str:
        if is_type(node):
            return effective_node_display_color(node)
        type_node: Node | None = None
        if node.type_id is not None:
            try:
                candidate = self._session.get_node(str(node.type_id))
                if is_type(candidate):
                    type_node = candidate
            except KeyError:
                pass
        return effective_node_display_color(node, type_node)

    def _format_value_summary(self, value: object) -> str:
        if value is None:
            return "(empty)"
        if isinstance(value, dict):
            ref = self._extract_ref_target_id(value)
            if ref is not None:
                return f"ref:{ref[-8:]}"
            return "inline object"
        if isinstance(value, list):
            return f"list[{len(value)}]"
        text = str(value)
        return text if len(text) <= 40 else text[:37] + "..."

    def _value_counts_text(self, value: object) -> str:
        if isinstance(value, list):
            return f"items:{len(value)}"
        if value is None:
            return "items:0"
        return "items:1"

    def _slots_for_instance(self, node: Node) -> list[NodeSlot]:
        """Return the fully merged slot list for *node*, traversing the type chain."""
        from lks_utils.knowledge.resolver import Resolver
        resolver = Resolver(self._session.repository)  # noqa: SLF001

        type_node: Node | None = None
        if node.type_id is not None:
            try:
                tn = self._session.get_node(str(node.type_id))
                if is_type(tn):
                    type_node = tn
            except KeyError:
                pass
        if type_node is None:
            type_node = resolver.fetch_type_for_instance(node)
        if type_node is None:
            return []

        chain = resolver.fetch_parent_chain(type_node) + [type_node]
        merged: dict[str, NodeSlot] = {}
        for n in chain:
            if is_type(n):
                for slot in as_type(n).slots:
                    merged[slot.name] = slot
        return list(merged.values())

    def _type_chain_for_instance(self, node: Node) -> list[Node]:
        """Return [outermost_ancestor, ..., direct_type] for an instance node."""
        from lks_utils.knowledge.resolver import Resolver
        resolver = Resolver(self._session.repository)  # noqa: SLF001

        type_node: Node | None = None
        if node.type_id is not None:
            try:
                tn = self._session.get_node(str(node.type_id))
                if is_type(tn):
                    type_node = tn
            except KeyError:
                pass
        if type_node is None:
            type_node = resolver.fetch_type_for_instance(node)
        if type_node is None:
            return []

        parents = resolver.fetch_parent_chain(type_node)  # outermost-first
        return parents + [type_node]

    def _header_color_for_slot(self, slot: NodeSlot) -> str:
        return header_color_for_classification(
            type_id=slot.ref_type,
            classification=slot.value_type or slot.effective_value_mode().value,
        )

    def _invalid_slot_names(self, node: Node) -> set[str]:
        if is_type(node):
            return set()
        invalid: set[str] = set()
        raw_errors = node.props.get(VALIDATION_ERRORS_PROP)
        if isinstance(raw_errors, dict):
            invalid.update(key for key, value in raw_errors.items(
            ) if isinstance(key, str) and isinstance(value, str))
        for slot in self._slots_for_instance(node):
            value = self._slot_display_value(node, slot)
            if slot.required and value is None:
                invalid.add(slot.name)
            if slot.source == SlotSource.REF and value is not None:
                if self._extract_ref_target_id(value) is None:
                    invalid.add(slot.name)
        return invalid

    def _validation_errors_dict(self, node: Node) -> dict[str, str]:
        """Extract validation errors dict for a node, including inferred errors."""
        if is_type(node):
            return {}
        errors: dict[str, str] = {}
        raw_errors = node.props.get(VALIDATION_ERRORS_PROP)
        if isinstance(raw_errors, dict):
            errors.update({key: str(value) for key, value in raw_errors.items()
                          if isinstance(key, str) and isinstance(value, str)})
        for slot in self._slots_for_instance(node):
            if slot.name not in errors:
                value = self._slot_display_value(node, slot)
                if slot.required and value is None:
                    errors[slot.name] = "Required property is missing"
                elif slot.source == SlotSource.REF and value is not None:
                    if self._extract_ref_target_id(value) is None:
                        errors[slot.name] = "Invalid reference format"
        return errors

    def _update_validation_log(self) -> None:
        """Gather all validation errors from visible nodes and update the log widget."""
        entries: list[ValidationErrorEntry] = []

        if self._current_node_id is None:
            self._validation_log.set_validation_errors(entries)
            return

        try:
            current_node = self._session.get_node(self._current_node_id)
        except KeyError:
            self._validation_log.set_validation_errors(entries)
            return

        # Add errors from current node
        current_errors = self._validation_errors_dict(current_node)
        for field_name, error_msg in current_errors.items():
            entries.append(ValidationErrorEntry(
                node_id=str(current_node.id),
                node_name=current_node.name,
                field_name=field_name,
                error_message=error_msg,
                error_level="error",  # Could be enhanced to differentiate levels
            ))

        # Add errors from child nodes if this is an instance (shown in decomposition)
        if not is_type(current_node):
            for child_id in getattr(self, '_child_node_ids', []):
                try:
                    child = self._session.get_node(child_id)
                    child_errors = self._validation_errors_dict(child)
                    for field_name, error_msg in child_errors.items():
                        entries.append(ValidationErrorEntry(
                            node_id=str(child.id),
                            node_name=child.name,
                            field_name=field_name,
                            error_message=error_msg,
                            error_level="error",
                        ))
                except KeyError:
                    pass

        self._validation_log.set_validation_errors(entries)

    def _on_validation_entry_clicked(self, node_id: str) -> None:
        """Handle validation log entry click - focus on the problem node."""
        try:
            node = self._session.get_node(node_id)
            # Could implement: scroll to node, highlight it, etc.
        except KeyError:
            pass

    def _on_pick_ref(self, slot_name: str, _row: FieldRow) -> None:
        if self._current_node_id is None:
            return
        slot = self._current_slots_by_name.get(slot_name)
        dialog = QKnowledgeRefPickerDialog(
            self._session,
            ref_type=slot.ref_type if slot is not None else None,
            slot_name=slot_name,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        selected_id = dialog.selected_node_id()
        if not selected_id:
            return
        self._apply_slot_mutation(
            node_id=self._current_node_id,
            label="decomposition_canvas_pick_ref",
            mutate=lambda mutator: mutator.set_slot_value(
                self._current_node_id,
                slot_name,
                selected_id,
            ),
        )
        self._refresh_current_node()

    def _on_clear_ref(self, slot_name: str, _row: FieldRow) -> None:
        if self._current_node_id is None:
            return
        slot = self._current_slots_by_name.get(slot_name)
        self._apply_slot_mutation(
            node_id=self._current_node_id,
            label="decomposition_canvas_clear_ref",
            mutate=(
                (lambda mutator: mutator.set_slot_value(
                    self._current_node_id, slot_name, None))
                if slot is not None and slot.source.is_reference
                else (lambda mutator: mutator.discard_slot_value(self._current_node_id, slot_name))
            ),
        )
        self._refresh_current_node()

    def _on_row_selected(self, slot_name: str, _row: FieldRow) -> None:
        if self._current_node_id is None:
            return
        self.row_selected.emit(slot_name)

    def _on_item_selected(self, item: QKnowledgeFieldNodeCanvasObject) -> None:
        self._canvas.select_object(item, additive=False)

    def _row_at_canvas_position(self, position: QPointF) -> FieldRow | None:
        """Return the FieldRow under *position* across all field items."""
        world = self._canvas.camera.view().screen_to_world(
            (float(position.x()), float(position.y())),
            (float(self._canvas.width()), float(self._canvas.height())),
        )
        for fi in self._field_items:
            visible = fi._find_visible_row(world)  # noqa: SLF001
            if visible is not None:
                return visible.row
        return None


__all__ = ["QKnowledgeDecompositionCanvasWidget",
           "MIME_KNOWLEDGE_PALETTE_COMPONENT"]

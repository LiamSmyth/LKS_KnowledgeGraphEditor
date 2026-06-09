"""Embeddable workbench shell for end-to-end knowledge authoring.

This is the replacement for the old all-in-one layout.  The private dialog
classes (:class:`_QNewTypeDialog`, :class:`_QAddSlotDialog`,
:class:`_QNewInstanceDialog`) and the helpers ``_populate_category_combo``,
``_combo_value`` are kept here so existing tests
can still import them from this module without changes.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QTabWidget,
    QWidget,
)

from lks_utils.events import EventBus, EventEnvelope
from lks_utils.gui_qt.events import EventBusQtBridge

from lks_utils.knowledge.default_theme import (
    REF_VALID_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.git_service import KnowledgeGitService
from lks_utils.knowledge.instance_validator import PROPERTY_VERSIONS_PROP, TYPE_VERSION_PROP
from lks_utils.knowledge.instance_validator import PROTOTYPE_ID_PROP
from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.links.link_types.link_type_system import EXTENDS_LINK_TYPE_ID
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_slot import NodeSlot, SlotSource
from lks_utils.knowledge.models.type import as_type, is_type, make_type
from lks_utils.knowledge.ui.components._workbench import (
    dock_wiring,
    instance_helpers,
    menu_actions,
    theme_reapply,
)
from lks_utils.knowledge.editor_session_types import SessionChangeEvent
from lks_utils.knowledge.ui.components.add_slot_dialog import _QAddSlotDialog
from lks_utils.knowledge.ui.components.instance_creation_dialog import _QNewInstanceDialog
from lks_utils.knowledge.ui.components.q_init_repo_dialog import QInitRepoDialog
from lks_utils.knowledge.ui.components.type_creation_dialog import _QNewTypeDialog
from lks_utils.knowledge.ui.components.repo_controls_widget import QKnowledgeRepoControlsWidget
from lks_utils.knowledge.ui.components.workbench_dialog_helpers import combo_value, populate_category_combo
from lks_utils.knowledge.ui.components.graph_tab import QKnowledgeGraphTabWidget
from lks_utils.knowledge.ui.components.link_instances_tab import QKnowledgeLinkInstancesTabWidget
from lks_utils.knowledge.ui.components.link_types_tab import QKnowledgeLinkTypesTabWidget
from lks_utils.knowledge.ui.tabs import QGitChangesTab
from lks_utils.knowledge.ui.components.primitive_tab import QKnowledgePrimitiveTabWidget


_ULID_RE: re.Pattern[str] = re.compile(r"^[0-9A-Z]{26}$")


def _has_valid_ref_targets(value: object) -> bool:
    return instance_helpers.has_valid_ref_targets(value, _ULID_RE)


_populate_category_combo = populate_category_combo
_populate_type_kind_combo = _populate_category_combo
_combo_value = combo_value


class QKnowledgeWorkbenchWidget(QWidget):
    """Tab-based workbench shell: Node Types | Node Instances | Link Instances | Link Types.

    Each tab contains a three-panel layout (Library + Palette | Canvas | Inspector)
    implemented by :class:`~lks_utils.knowledge.ui.components.primitive_tab.QKnowledgePrimitiveTabWidget`.
    """

    def __init__(
        self,
        session: EditorSession | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session or EditorSession()
        self._current_node_id: str | None = None

        self._repo_controls = QKnowledgeRepoControlsWidget(self._session, self)
        self._ui_event_bus = EventBus()
        self._ui_event_bridge = EventBusQtBridge(self._ui_event_bus, self)
        self._ui_event_bridge.start(stream="knowledge.ui.workbench")
        self._ui_event_bridge.event_received.connect(
            self._on_workbench_ui_event_received
        )
        self._tabs = QTabWidget(self)
        self._type_tab = QKnowledgePrimitiveTabWidget(
            self._session, "type", self)
        self._instance_tab = QKnowledgePrimitiveTabWidget(
            self._session, "instance", self)
        self._link_instances_tab = QKnowledgeLinkInstancesTabWidget(
            self._session, self)
        self._link_types_tab = QKnowledgeLinkTypesTabWidget(
            self._session, self)
        self._git_tab = QGitChangesTab(self)
        self._graph_tab = QKnowledgeGraphTabWidget(
            self._session,
            self,
            ui_event_bus=self._ui_event_bus,
        )
        self._preferences_dialog: QPreferencesDialog | None = None
        self._status_label = QLabel("Ready", self)
        self._status_label.setObjectName("knowledge_status_label")
        self._pending_workbench_status_text: str | None = None
        self._workbench_status_reaction_timer = QTimer(self)
        self._workbench_status_reaction_timer.setSingleShot(True)
        self._workbench_status_reaction_timer.setInterval(120)
        self._workbench_status_reaction_timer.timeout.connect(
            self._flush_workbench_status_reaction
        )

        self._tabs.addTab(self._type_tab, "Node Types")
        self._tabs.addTab(self._instance_tab, "Node Instances")
        self._tabs.addTab(self._link_instances_tab, "Link Instances")
        self._tabs.addTab(self._link_types_tab, "Link Types")
        self._tabs.addTab(self._git_tab, "Version Control")
        self._tabs.addTab(self._graph_tab, "Graph View")

        self._state_persistence_enabled = False
        self._persistence_hooks_installed = False
        self._is_restoring_ui_state = False

        self._build_layout()
        self._wire_signals()
        self._wire_library_new_buttons()
        self._apply_styles()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._persist_ui_state_if_enabled()
        self._session.remove_change_listener(self._on_session_change)
        self._workbench_status_reaction_timer.stop()
        self._ui_event_bridge.stop()
        self._ui_event_bus.close()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def session(self) -> EditorSession:
        return self._session

    def ui_event_bus(self) -> EventBus:
        return self._ui_event_bus

    def ui_event_bridge(self) -> EventBusQtBridge:
        return self._ui_event_bridge

    def _on_workbench_ui_event_received(self, event_obj: object) -> None:
        if not isinstance(event_obj, EventEnvelope):
            return
        if event_obj.stream != "knowledge.ui.workbench":
            return
        if event_obj.event_type == "graph_tab.external_repo_change_detected":
            changed_path = str(event_obj.payload.get("path", "")).strip()
            if changed_path:
                self._queue_workbench_status_reaction(
                    f"Graph change detected: {Path(changed_path).name}"
                )
            return
        if event_obj.event_type == "graph_tab.external_repo_reload_applied":
            changed_files_raw = event_obj.payload.get("changed_files")
            changed_files = (
                changed_files_raw
                if isinstance(changed_files_raw, list)
                else []
            )
            self._queue_workbench_status_reaction(
                f"Graph reload applied: {len(changed_files)} file(s)"
            )

    def _queue_workbench_status_reaction(self, text: str) -> None:
        self._pending_workbench_status_text = text
        self._workbench_status_reaction_timer.start()

    def _flush_workbench_status_reaction(self) -> None:
        if not self._pending_workbench_status_text:
            return
        self._status_label.setText(self._pending_workbench_status_text)
        self._pending_workbench_status_text = None

    def current_node_id(self) -> str | None:
        return self._current_node_id

    def open_node(self, node_id: str) -> None:
        """Open *node_id* in the appropriate tab."""
        try:
            node = self._session.get_node(node_id)
        except KeyError:
            return
        self._current_node_id = node_id
        if is_type(node):
            self._tabs.setCurrentWidget(self._type_tab)
            self._type_tab.open_node(node_id)
        else:
            self._tabs.setCurrentWidget(self._instance_tab)
            self._instance_tab.open_node(node_id)

    def new_repo(self, root: str | Path, *, source_repo_id: str = "default") -> None:
        self._session.new_repo(root, source_repo_id=source_repo_id)
        git_service = self._session.git_service
        if git_service is not None and not git_service.is_repo:
            git_service.init_repo()
        self._current_node_id = None
        self._graph_tab.set_graph_view(None)
        self._graph_tab.refresh_palettes()
        self._sync_git_tab_sources()
        self._set_status(f"New repo: {root}")
        self._persist_ui_state_if_enabled()

    def open_repo(self, root: str | Path) -> None:
        repository_root = Path(root)
        gate_service = KnowledgeGitService(repository_root=repository_root)
        if not gate_service.is_repo:
            dialog = QInitRepoDialog(
                repository_path=repository_root, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._set_status("Open cancelled")
                return
            if not gate_service.init_repo():
                QMessageBox.critical(
                    self,
                    "Git Required",
                    f"Failed to initialize git repository at: {repository_root}",
                )
                return

        self._session.load_from(repository_root)
        self._current_node_id = None
        self._graph_tab.set_graph_view(None)
        self._graph_tab.refresh_palettes()
        self._sync_git_tab_sources()
        first_node = next(iter(self._session.list_nodes()), None)
        if first_node is not None:
            self.open_node(str(first_node.id))
        self._set_status(f"Opened repo: {repository_root}")
        self._persist_ui_state_if_enabled()

    def save_repo(self) -> None:
        self._session.save()
        self._set_status("Repository saved")

    def save_repo_as(self, root: str | Path) -> None:
        self._session.save_as(root)
        self._set_status(f"Saved repo: {root}")
        self._persist_ui_state_if_enabled()

    def create_type(
        self,
        *,
        type_kind: str,
        name: str,
        description: str,
        base_type_id: str | None = None,
        slots: list[KnowledgeSlot] | None = None,
    ) -> str:
        node = make_type(type_kind, name, description, slots=slots or [])
        result = self._session.io_upsert_node(node)
        if not result.ok:
            raise ValueError(result.error_message or "Failed to create type")
        if base_type_id:
            base_type = self._session.get_node(base_type_id)
            if not is_type(base_type):
                raise ValueError(
                    "Base type selection must reference a type node")

            def _mutate(repo: Repository) -> set[str]:
                repo.upsert(
                    node.model_copy(update={"rev": node.rev + 1})
                )
                repo.upsert_link(
                    LinkInstance(
                        link_type_id=EXTENDS_LINK_TYPE_ID,
                        source_node_id=str(node.id),
                        target_node_id=base_type_id,
                    )
                )
                return {str(node.id), base_type_id}

            result = self._session.io_apply_op(_mutate)
            if not result.ok:
                raise ValueError(
                    result.error_message or "Failed to add base type link")
        node_id = str(node.id)
        self.open_node(node_id)
        self._set_status(f"Created type: {name}")
        return node_id

    def add_slot(self, *, slot: NodeSlot, type_id: str | None = None) -> None:
        resolved_type_id = type_id or self._current_type_id()
        if resolved_type_id is None:
            raise ValueError("No type is selected")
        result = self._session.io_add_slot_to_type(
            resolved_type_id, slot.model_dump())
        if not result.ok:
            raise ValueError(result.error_message or "Failed to add slot")
        self.open_node(resolved_type_id)
        self._set_status(f"Added slot: {slot.name}")

    def create_instance(
        self,
        *,
        type_id: str,
        name: str,
        description: str,
        props: dict[str, object] | None = None,
    ) -> str:
        source_node = self._session.get_node(type_id)
        prototype_id: str | None = None
        if is_type(source_node):
            type_node = source_node
            type_view = as_type(type_node)
            initial_props = {slot.name: slot.default_value()
                             for slot in type_view.slots}
        else:
            if source_node.type_id is None:
                raise ValueError(
                    f"Node {type_id} cannot be used as an instance source because it has no type"
                )
            type_node = self._session.get_node(str(source_node.type_id))
            if not is_type(type_node):
                raise ValueError(
                    f"Node {type_id} references non-type {source_node.type_id}"
                )
            type_view = as_type(type_node)
            initial_props = self._resolve_instance_defaults(
                source_instance=source_node,
                type_node=type_node,
            )
            prototype_id = str(source_node.id)

        type_view = as_type(type_node)
        explicit_instance_category = str(
            type_node.props.get("instance_category") or ""
        ).strip()
        initial_props[TYPE_VERSION_PROP] = type_node.rev
        initial_props[PROPERTY_VERSIONS_PROP] = {
            slot.name: slot.version for slot in type_view.slots
        }
        if prototype_id is not None:
            initial_props[PROTOTYPE_ID_PROP] = prototype_id

        # Split caller props: REF/REF_LIST slots must go through the mutator
        # (slot_ref edges) rather than being written directly to node.props.
        # Exception: broken/stale refs (non-ULID targets) are written directly
        # to props so that recovery-action UI can display and resolve them.
        slot_source_map = {slot.name: slot.source for slot in type_view.slots}
        ref_props: dict[str, object] = {}
        for k, v in (props or {}).items():
            if slot_source_map.get(k) in (SlotSource.REF, SlotSource.REF_LIST):
                if _has_valid_ref_targets(v):
                    ref_props[k] = v
                else:
                    initial_props[k] = v
            else:
                initial_props[k] = v

        node = Node(
            category=explicit_instance_category,
            type_id=type_node.id,
            name=name,
            description=description,
            props=initial_props,
        )
        node_id = str(node.id)
        result = self._session.io_upsert_node(node)
        if not result.ok:
            raise ValueError(
                result.error_message or "Failed to create instance")
        for slot_name, ref_value in ref_props.items():
            set_result = self._session.io_set_slot_value(
                node_id, slot_name, ref_value)
            if not set_result.ok:
                raise ValueError(
                    set_result.error_message
                    or f"Failed to set reference slot '{slot_name}'"
                )

        self.open_node(node_id)
        self._set_status(f"Created instance: {name}")
        return node_id

    def _resolve_instance_defaults(
        self,
        *,
        source_instance: Node,
        type_node: Node,
    ) -> dict[str, object]:
        return instance_helpers.resolve_instance_defaults(
            session=self._session,
            source_instance=source_instance,
            type_node=type_node,
        )

    def set_slot_literal(self, *, slot_name: str, value: str, node_id: str | None = None) -> None:
        target = node_id or self._current_node_id
        if target is None:
            raise ValueError("No node is selected")
        result = self._session.io_set_slot_value(
            target, slot_name, value)
        if not result.ok:
            raise ValueError(
                result.error_message or "Failed to set slot value")
        self.open_node(target)
        self._set_status(f"Updated slot: {slot_name}")

    def set_slot_ref(self, *, slot_name: str, ref_node_id: str, node_id: str | None = None) -> None:
        target = node_id or self._current_node_id
        if target is None:
            raise ValueError("No node is selected")
        result = self._session.io_set_slot_value(
            target, slot_name, ref_node_id)
        if not result.ok:
            raise ValueError(
                result.error_message or "Failed to set slot reference")
        self.open_node(target)
        self._set_status(f"Linked slot: {slot_name}")

    def clear_slot_value(self, *, slot_name: str, node_id: str | None = None) -> None:
        target = node_id or self._current_node_id
        if target is None:
            raise ValueError("No node is selected")
        result = self._session.io_clear_slot_value(
            target, slot_name)
        if not result.ok:
            raise ValueError(
                result.error_message or "Failed to clear slot value")
        self.open_node(target)
        self._set_status(f"Cleared slot: {slot_name}")

    def open_search_popup(self) -> None:
        pass  # Placeholder â€” search popup may be re-added in a later phase

    # ------------------------------------------------------------------
    # UI state persistence
    # ------------------------------------------------------------------

    _SETTINGS_ORG = "lks_utils"
    _SETTINGS_APP = "KnowledgeWorkbench"

    def save_ui_state(self) -> None:
        dock_wiring.save_ui_state(self)

    def restore_ui_state(self) -> None:
        dock_wiring.restore_ui_state(self)

    def _persist_ui_state_if_enabled(self) -> None:
        dock_wiring.persist_ui_state_if_enabled(self)

    def _ensure_persistence_hooks(self) -> None:
        dock_wiring.ensure_persistence_hooks(self)

    def _on_app_about_to_quit(self) -> None:
        dock_wiring.on_app_about_to_quit(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if menu_actions.key_press_event(self, event):
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        dock_wiring.build_layout(self)

    def _wire_signals(self) -> None:
        dock_wiring.wire_signals(self)

    def _wire_library_new_buttons(self) -> None:
        dock_wiring.wire_library_new_buttons(self)

    def _sync_git_tab_sources(self) -> None:
        dock_wiring.sync_git_tab_sources(self)

    def _apply_styles(self) -> None:
        theme_reapply.apply_styles(self)

    def _on_tab_opened(self, node_id: str) -> None:
        dock_wiring.on_tab_opened(self, node_id)

    def _current_type_id(self) -> str | None:
        return dock_wiring.current_type_id(self)

    def _set_status(self, text: str) -> None:
        dock_wiring.set_status(self, text)

    def _open_preferences_dialog(self) -> None:
        menu_actions.open_preferences_dialog(self)

    def _on_preferences_dialog_closed(self) -> None:
        menu_actions.on_preferences_dialog_closed(self)

    def _on_session_change(self, event: SessionChangeEvent) -> None:
        dock_wiring.on_session_change(self, event)

    # ------------------------------------------------------------------
    # Repo control handlers
    # ------------------------------------------------------------------

    def _on_repo_new(self) -> None:
        menu_actions.on_repo_new(self)

    def _on_repo_open(self) -> None:
        menu_actions.on_repo_open(self)

    def _on_repo_save(self) -> None:
        menu_actions.on_repo_save(self)

    def _on_repo_save_all(self) -> None:
        menu_actions.on_repo_save_all(self)

    def _on_repo_save_as(self) -> None:
        menu_actions.on_repo_save_as(self)

    # ------------------------------------------------------------------
    # Creation dialogs  (triggered from library panel "Newâ€¦" button)
    # ------------------------------------------------------------------

    def _on_new_type_requested(self) -> None:
        menu_actions.on_new_type_requested(self)

    def _on_add_slot_requested(self) -> None:
        menu_actions.on_add_slot_requested(self)

    def _on_new_instance_requested(self) -> None:
        menu_actions.on_new_instance_requested(self)


__all__ = [
    "QKnowledgeWorkbenchWidget",
    "_QNewTypeDialog",
    "_QNewInstanceDialog",
    "_QAddSlotDialog",
    "_populate_category_combo",
    "_populate_type_kind_combo",  # backward-compat alias
    "_combo_value",
]

"""Private menu and shortcut handlers for the workbench shell."""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from lks_utils.gui_qt.preferences_dialog import QPreferencesDialog
from lks_utils.input import get_default_bindings
from lks_utils.knowledge.actions import (
    ADD_INSTANCE,
    ADD_SLOT,
    ADD_TYPE,
    PALETTE_SPAWN_SEARCH,
    SWITCH_TO_INSTANCES_TAB,
    SWITCH_TO_TYPES_TAB,
)
from lks_utils.knowledge.ui.components.autosave_preferences_widget import (
    QKnowledgeAutosavePreferencesWidget,
)
from lks_utils.knowledge.ui.components.live_reload_preferences_widget import (
    QKnowledgeLiveReloadPreferencesWidget,
)

if TYPE_CHECKING:
    from lks_utils.knowledge.ui.components.workbench import QKnowledgeWorkbenchWidget


def _workbench_module(workbench: QKnowledgeWorkbenchWidget):
    return sys.modules[workbench.__class__.__module__]


def key_press_event(workbench: QKnowledgeWorkbenchWidget, event: QKeyEvent) -> bool:
    bindings = get_default_bindings()
    seq = QKeySequence(int(event.modifiers().value)
                       | int(event.key())).toString()
    if bindings.matches_key(PALETTE_SPAWN_SEARCH.id, seq):
        workbench.open_search_popup()
        event.accept()
        return True
    if bindings.matches_key(ADD_TYPE.id, seq):
        workbench._on_new_type_requested()
        event.accept()
        return True
    if bindings.matches_key(ADD_INSTANCE.id, seq):
        workbench._on_new_instance_requested()
        event.accept()
        return True
    if bindings.matches_key(ADD_SLOT.id, seq):
        workbench._on_add_slot_requested()
        event.accept()
        return True
    if bindings.matches_key(SWITCH_TO_TYPES_TAB.id, seq):
        workbench._tabs.setCurrentWidget(workbench._type_tab)
        event.accept()
        return True
    if bindings.matches_key(SWITCH_TO_INSTANCES_TAB.id, seq):
        workbench._tabs.setCurrentWidget(workbench._instance_tab)
        event.accept()
        return True
    return False


def open_preferences_dialog(workbench: QKnowledgeWorkbenchWidget) -> None:
    if workbench._preferences_dialog is None:
        live_reload_widget = QKnowledgeLiveReloadPreferencesWidget(
            settings_org=workbench._SETTINGS_ORG,
            settings_app=workbench._SETTINGS_APP,
        )
        autosave_widget = QKnowledgeAutosavePreferencesWidget(
            settings_org=workbench._SETTINGS_ORG,
            settings_app=workbench._SETTINGS_APP,
        )
        workbench._preferences_dialog = QPreferencesDialog(
            parent=workbench.window(),
            state_org=workbench._SETTINGS_ORG,
            extra_tabs=(
                ("Knowledge", live_reload_widget),
                ("Autosave", autosave_widget),
            ),
        )
        workbench._preferences_dialog.finished.connect(
            workbench._on_preferences_dialog_closed)
    workbench._preferences_dialog.show()
    workbench._preferences_dialog.raise_()
    workbench._preferences_dialog.activateWindow()


def on_preferences_dialog_closed(workbench: QKnowledgeWorkbenchWidget) -> None:
    workbench._graph_tab.reload_live_reload_settings()
    workbench._git_tab.reload_autosave_settings()


def on_repo_new(workbench: QKnowledgeWorkbenchWidget) -> None:
    root = QFileDialog.getExistingDirectory(workbench, "Create Knowledge Repo")
    if root:
        workbench.new_repo(root)


def on_repo_open(workbench: QKnowledgeWorkbenchWidget) -> None:
    root = QFileDialog.getExistingDirectory(workbench, "Open Knowledge Repo")
    if root:
        workbench.open_repo(root)


def on_repo_save(workbench: QKnowledgeWorkbenchWidget) -> None:
    try:
        workbench.save_repo()
    except Exception:
        workbench._on_repo_save_as()


def on_repo_save_all(workbench: QKnowledgeWorkbenchWidget) -> None:
    # No-op: all mutations are now atomic. Git tracks modified-since-HEAD.
    return


def on_repo_save_as(workbench: QKnowledgeWorkbenchWidget) -> None:
    root = QFileDialog.getExistingDirectory(
        workbench, "Save Knowledge Repo As")
    if root:
        workbench.save_repo_as(root)


def on_new_type_requested(workbench: QKnowledgeWorkbenchWidget) -> None:
    mod = _workbench_module(workbench)
    type_nodes = list(workbench._session.iter_types())
    existing_names = [node.name for node in workbench._session.list_nodes()]
    dlg = mod._QNewTypeDialog(
        type_nodes,
        existing_names=existing_names,
        parent=workbench,
    )
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    base_type_id, category, name, description = dlg.values()
    workbench.create_type(
        type_kind=category,
        name=name,
        description=description,
        base_type_id=base_type_id or None,
    )


def on_add_slot_requested(workbench: QKnowledgeWorkbenchWidget) -> None:
    mod = _workbench_module(workbench)
    type_id = workbench._current_type_id()
    if type_id is None:
        return
    type_nodes = list(workbench._session.iter_types())
    dlg = mod._QAddSlotDialog(type_nodes, parent=workbench)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    slot = dlg.values()
    workbench.add_slot(slot=slot, type_id=type_id)


def on_new_instance_requested(workbench: QKnowledgeWorkbenchWidget) -> None:
    mod = _workbench_module(workbench)
    type_nodes = list(workbench._session.iter_types())
    if not type_nodes:
        QMessageBox.information(workbench, "No Types", "Create a type first.")
        return
    selected_source_id = workbench._current_node_id
    existing_names = [node.name for node in workbench._session.list_nodes()]
    dlg = mod._QNewInstanceDialog(
        list(workbench._session.list_nodes()),
        selected_source_id=selected_source_id,
        existing_names=existing_names,
        parent=workbench,
    )
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    type_id, name, description = dlg.values()
    if type_id is None:
        return
    workbench.create_instance(
        type_id=type_id, name=name, description=description)

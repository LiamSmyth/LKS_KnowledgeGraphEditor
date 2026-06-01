"""Private dock wiring and persistence helpers for the workbench shell."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QVBoxLayout

from lks_utils.knowledge.models.type import is_type
from lks_utils.knowledge.editor_session_types import SessionChangeEvent

if TYPE_CHECKING:
    from lks_utils.knowledge.ui.components.workbench import QKnowledgeWorkbenchWidget
    from lks_utils.knowledge.ui.components.primitive_tab import QKnowledgePrimitiveTabWidget


def build_layout(workbench: QKnowledgeWorkbenchWidget) -> None:
    root = QVBoxLayout(workbench)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    root.addWidget(workbench._repo_controls)
    root.addWidget(workbench._tabs, stretch=1)
    root.addWidget(workbench._status_label)


def wire_signals(workbench: QKnowledgeWorkbenchWidget) -> None:
    workbench._repo_controls.repo_new_requested.connect(workbench._on_repo_new)
    workbench._repo_controls.repo_open_requested.connect(
        workbench._on_repo_open)
    workbench._repo_controls.repo_save_as_requested.connect(
        workbench._on_repo_save_as
    )
    workbench._repo_controls.preferences_requested.connect(
        workbench._open_preferences_dialog
    )
    workbench._type_tab.node_opened.connect(
        lambda nid: workbench._on_tab_opened(nid))
    workbench._instance_tab.node_opened.connect(
        lambda nid: workbench._on_tab_opened(nid)
    )
    workbench._session.add_change_listener(workbench._on_session_change)


def wire_library_new_buttons(workbench: QKnowledgeWorkbenchWidget) -> None:
    """Connect library 'New...' buttons to creation dialogs."""
    workbench._type_tab._library.new_item_requested.connect(workbench._on_new_type_requested)  # noqa: SLF001
    workbench._instance_tab._library.new_item_requested.connect(workbench._on_new_instance_requested)  # noqa: SLF001


def sync_git_tab_sources(workbench: QKnowledgeWorkbenchWidget) -> None:
    workbench._git_tab.bind_sources(
        session=workbench._session,
        git_service=workbench._session.git_service,
    )


def on_tab_opened(workbench: QKnowledgeWorkbenchWidget, node_id: str) -> None:
    workbench._current_node_id = node_id


def current_type_id(workbench: QKnowledgeWorkbenchWidget) -> str | None:
    if workbench._current_node_id is None:
        return None
    try:
        node = workbench._session.get_node(workbench._current_node_id)
        return workbench._current_node_id if is_type(node) else None
    except KeyError:
        return None


def set_status(workbench: QKnowledgeWorkbenchWidget, text: str) -> None:
    workbench._status_label.setText(text)


def on_session_change(workbench: QKnowledgeWorkbenchWidget, event: SessionChangeEvent) -> None:
    change_type = event.change_type
    # Graph tab already performs targeted node/update refreshes; forcing a full
    # palette refresh on every node/repo_saved causes avoidable UI stalls.
    if change_type == "repo_loaded":
        workbench._graph_tab.refresh_palettes()
    if change_type in {"repo_loaded", "repo_saved", "dirty_changed"}:
        root = getattr(workbench._session, "repository_root", None)
        label = str(root) if root else "(no repo)"
        set_status(workbench, label)


def save_ui_state(workbench: QKnowledgeWorkbenchWidget) -> None:
    """Persist workbench UI state to QSettings."""
    s = QSettings(workbench._SETTINGS_ORG, workbench._SETTINGS_APP)
    s.beginGroup("workbench")

    root = workbench._session.repository_root
    s.setValue("repo_root", str(root) if root is not None else "")
    s.setValue("active_tab", workbench._tabs.currentIndex())
    s.setValue("type_tab/open_node_id",
               workbench._type_tab.current_node_id() or "")
    s.setValue(
        "instance_tab/open_node_id", workbench._instance_tab.current_node_id() or ""
    )
    s.setValue(
        "link_instances_tab/open_link_instance_id",
        workbench._link_instances_tab.current_link_instance_id() or "",
    )

    def _save_splitter(prefix: str, tab: QKnowledgePrimitiveTabWidget) -> None:
        state = tab.splitter_state()
        s.setValue(f"{prefix}/outer_splitter", ",".join(str(v)
                   for v in state["outer"]))
        s.setValue(f"{prefix}/left_splitter", ",".join(str(v)
                   for v in state["left"]))

    _save_splitter("type_tab", workbench._type_tab)
    _save_splitter("instance_tab", workbench._instance_tab)
    s.setValue(
        "link_instances_tab/outer_splitter",
        ",".join(str(v)
                 for v in workbench._link_instances_tab.splitter_state()["outer"]),
    )

    win = workbench.window()
    if win is not None:
        s.setValue("window_geometry", win.saveGeometry())

    s.endGroup()


def restore_ui_state(workbench: QKnowledgeWorkbenchWidget) -> None:
    """Restore workbench UI state from QSettings and enable persistence."""
    workbench._state_persistence_enabled = True
    ensure_persistence_hooks(workbench)
    workbench._is_restoring_ui_state = True
    s = QSettings(workbench._SETTINGS_ORG, workbench._SETTINGS_APP)
    s.beginGroup("workbench")

    try:
        geom = s.value("window_geometry")
        if geom is not None:
            win = workbench.window()
            if win is not None:
                win.restoreGeometry(geom)

        def _restore_splitter(
            prefix: str,
            tab: QKnowledgePrimitiveTabWidget,
        ) -> dict[str, list[int]]:
            def _parse(key: str) -> list[int]:
                raw = s.value(key, "")
                if not raw:
                    return []
                try:
                    return [int(v) for v in str(raw).split(",") if v.strip()]
                except ValueError:
                    return []

            splitter_state = {
                "outer": _parse(f"{prefix}/outer_splitter"),
                "left": _parse(f"{prefix}/left_splitter"),
            }
            tab.restore_splitter_state(splitter_state)
            return splitter_state

        type_splitter_state = _restore_splitter(
            "type_tab", workbench._type_tab)
        instance_splitter_state = _restore_splitter(
            "instance_tab", workbench._instance_tab)

        link_instances_outer_raw = s.value(
            "link_instances_tab/outer_splitter", "")
        link_instances_splitter_state: dict[str, list[int]] = {"outer": []}
        if link_instances_outer_raw:
            try:
                link_instances_splitter_state["outer"] = [
                    int(v)
                    for v in str(link_instances_outer_raw).split(",")
                    if v.strip()
                ]
            except ValueError:
                link_instances_splitter_state["outer"] = []

        saved_tab_index: int | None = None
        tab_index_raw = s.value("active_tab")
        if tab_index_raw is not None:
            try:
                idx = int(tab_index_raw)
                if 0 <= idx < workbench._tabs.count():
                    saved_tab_index = idx
            except (ValueError, TypeError):
                pass

        repo_root_str = s.value("repo_root", "")
        if repo_root_str:
            repo_path = Path(str(repo_root_str))
            if repo_path.exists():
                try:
                    workbench.open_repo(repo_path)
                    for tab_key, tab_widget in [
                        ("type_tab", workbench._type_tab),
                        ("instance_tab", workbench._instance_tab),
                    ]:
                        node_id = s.value(f"{tab_key}/open_node_id", "")
                        if node_id:
                            try:
                                workbench._session.get_node(str(node_id))
                                tab_widget.open_node(str(node_id))
                            except KeyError:
                                pass

                    link_instance_id = s.value(
                        "link_instances_tab/open_link_instance_id", ""
                    )
                    if link_instance_id:
                        workbench._link_instances_tab.open_link_instance(
                            str(link_instance_id)
                        )
                except Exception:
                    pass

        if saved_tab_index is not None:
            workbench._tabs.setCurrentIndex(saved_tab_index)

        workbench._type_tab.restore_splitter_state(type_splitter_state)
        workbench._instance_tab.restore_splitter_state(instance_splitter_state)
        workbench._link_instances_tab.restore_splitter_state(
            link_instances_splitter_state)
    finally:
        s.endGroup()
        workbench._is_restoring_ui_state = False


def persist_ui_state_if_enabled(workbench: QKnowledgeWorkbenchWidget) -> None:
    if workbench._state_persistence_enabled and not workbench._is_restoring_ui_state:
        save_ui_state(workbench)


def ensure_persistence_hooks(workbench: QKnowledgeWorkbenchWidget) -> None:
    if workbench._persistence_hooks_installed:
        return
    app = QCoreApplication.instance()
    if app is None:
        return
    app.aboutToQuit.connect(workbench._on_app_about_to_quit)
    workbench._persistence_hooks_installed = True


def on_app_about_to_quit(workbench: QKnowledgeWorkbenchWidget) -> None:
    try:
        persist_ui_state_if_enabled(workbench)
    except RuntimeError:
        pass

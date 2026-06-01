"""Reference-aware delete dialog for knowledge nodes and link types."""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.q_dialog_scaffold_base import QDialogScaffoldBase

from lks_utils.knowledge.default_theme import (
    EDGE_COLOR,
    FIELD_BUTTON_BG,
    FIELD_BUTTON_BORDER,
    FIELD_BUTTON_PRESSED_BG,
    FIELD_BUTTON_TEXT,
    NODE_TEXT_COLOR,
    SCENE_BACKGROUND_COLOR,
    VALIDATION_ERROR_TEXT,
)
from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.io.delete_resolution import (
    DeleteResolution,
    DeleteResolutionEntry,
    DeleteResolutionMode,
)
from lks_utils.knowledge.links.link_type import SLOT_REF_LINK_TYPE_ID
from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.node_id import NodeId
from lks_utils.knowledge.operations.delete_safety_analyzer import (
    DeleteImpact,
    IncomingRef,
    analyze_delete_impact,
)
from lks_utils.knowledge.repository import Repository
from lks_utils.knowledge.resolver import Resolver
from lks_utils.knowledge.ui.components.ref_picker_dialog import QKnowledgeRefPickerDialog


DeleteEntityKind = Literal["node", "link_type"]
DeleteApplier = Callable[[Repository,
                          DeleteImpact, "DeleteResolution"], set[str]]


def find_all_users(session: EditorSession, target_id: str) -> list[Node]:
    """Find every node that references *target_id* via links or ``type_id``."""
    repo = session._repository  # noqa: SLF001
    resolver = Resolver(repo)
    resolver.refresh_reverse_index()
    prop_dep_ids = set(resolver.get_dependents(target_id))
    result: list[Node] = []
    for node in session.list_nodes():
        node_id_str = str(node.id)
        if node_id_str == target_id:
            continue
        if node_id_str in prop_dep_ids or str(node.type_id or "") == target_id:
            result.append(node)
    return result


# DeleteResolution, DeleteResolutionEntry, DeleteResolutionMode are imported
# from lks_utils.knowledge.io.delete_resolution (canonical location).


def _apply_delete_resolution(
    repository: Repository,
    *,
    impact: DeleteImpact,
    resolution: DeleteResolution,
) -> set[str]:
    """Apply one multi-target delete resolution directly to the repository snapshot."""
    touched: set[str] = set()

    target_ids = set(impact.targets)
    entries_by_source: dict[str, list[DeleteResolutionEntry]] = {}
    for entry in resolution.entries:
        entries_by_source.setdefault(
            entry.incoming_ref.source_node_id, []).append(entry)

    for node in list(repository.list_nodes()):
        node_id = str(node.id)
        if node_id in target_ids:
            continue

        update: dict[str, object] = {}
        for entry in entries_by_source.get(node_id, []):
            path = entry.incoming_ref.source_slot_path
            target_id = entry.incoming_ref.target_node_id
            if path == ("type_id",):
                new_type_id = _resolved_type_id(entry, target_id=target_id)
                if new_type_id != node.type_id:
                    update["type_id"] = new_type_id
                continue

            slot_name: str | None
            if path == ("slot_ref",):
                slot_name = None
            else:
                slot_name = path[0] if path else None

            matching_links = [
                link
                for link in repository.list_links()
                if link.link_type_id == SLOT_REF_LINK_TYPE_ID
                and str(link.source_node_id) == node_id
                and str(link.target_node_id) == target_id
                and (slot_name is None or str(link.source_slot_name or "") == slot_name)
            ]
            if not matching_links:
                continue

            if entry.mode == "leave_dangling":
                continue
            if entry.mode == "remove_ref":
                for link in matching_links:
                    repository.delete_link(link.id)
                    touched.add(link.id)
                continue
            if entry.replacement_id is None or entry.replacement_id == target_id:
                raise ValueError(
                    "replace resolution requires a distinct replacement id")
            for link in matching_links:
                repository.upsert_link(
                    link.model_copy(
                        update={"target_node_id": entry.replacement_id})
                )
                touched.add(link.id)

        if update:
            repository.upsert(node.model_copy(update=update))
            touched.add(node_id)

    for link in list(repository.list_links()):
        if (
            str(link.source_node_id) in target_ids
            or str(link.target_node_id) in target_ids
        ):
            repository.delete_link(link.id)
            touched.add(link.id)

    for target_id in impact.targets:
        if repository.find_node(target_id) is None:
            continue
        repository.delete(target_id)
        touched.add(target_id)
    return touched


def _resolved_type_id(
    entry: DeleteResolutionEntry,
    *,
    target_id: str,
) -> NodeId | None:
    if entry.mode == "leave_dangling":
        return NodeId.from_str(target_id)
    if entry.mode == "remove_ref":
        return None
    if entry.replacement_id is None or entry.replacement_id == target_id:
        raise ValueError(
            "replace resolution requires a distinct replacement id")
    return NodeId.from_str(entry.replacement_id)


class QKnowledgeRefAwareDeleteDialog(QDialogScaffoldBase):
    """Confirm deletion of a node and handle any dependent references.

    When the target has zero users the dialog is a simple confirmation.
    When it has users, three options are offered:

    - **Cancel** â€” abort the operation.
                - **Force Delete** - null every reference / ``type_id`` that pointed to the
      target, then delete it.
        - **Replace With...** - redirect every reference to a user-chosen node, then
      delete the original.
    """

    def __init__(
        self,
        target_or_impact: Node | DeleteImpact,
        session: EditorSession,
        parent: QWidget | None = None,
        *,
        entity_kind: DeleteEntityKind = "node",
        allow_replace: bool | None = None,
        apply_resolution: DeleteApplier | None = None,
    ) -> None:
        super().__init__("Confirm Delete", parent=parent)
        self._session = session
        self._impact = self._coerce_impact(target_or_impact)
        self._entity_kind = entity_kind
        self._allow_replace = entity_kind == "node" if allow_replace is None else allow_replace
        self._apply_resolution_delegate = apply_resolution
        self._accepted_resolution: DeleteResolution | None = None
        self._row_selectors: list[tuple[IncomingRef, QComboBox]] = []

        self._header = QLabel(self._header_text(), self)
        self._header.setTextFormat(Qt.TextFormat.RichText)

        self._resolution_table = QTableWidget(self)
        self._resolution_table.setColumnCount(5)
        first_column = "Source node" if self._entity_kind == "node" else "Dependent link"
        self._resolution_table.setHorizontalHeaderLabels(
            [first_column, "Slot path", "Target", "State", "Resolution"]
        )
        self._resolution_table.verticalHeader().setVisible(False)
        self._resolution_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._resolution_table.setSelectionMode(
            QTableWidget.SelectionMode.NoSelection)
        self._resolution_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._resolution_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._resolution_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._resolution_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self._resolution_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self._resolution_table.setVisible(bool(self._impact.incoming_refs))
        self._populate_table()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(self._header)
        content_layout.addWidget(self._resolution_table)
        self.set_content(content)

        self._primary_btn = self.add_footer_button(
            "Delete", QDialogButtonBox.ButtonRole.DestructiveRole)
        self._primary_btn.clicked.connect(self._on_accept_primary)
        self._replace_btn = self.add_footer_button(
            "Replace All With...", QDialogButtonBox.ButtonRole.ActionRole)
        self._replace_btn.clicked.connect(self._on_replace_with)
        self.add_footer_button(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)

        self._replace_btn.setVisible(self._allow_replace)
        self._replace_btn.setEnabled(
            self._allow_replace and bool(self._impact.incoming_refs))

        # Keep aliases in sync with the new button references
        self._safe_btn = self._primary_btn
        self._force_btn = self._primary_btn

        self.setMinimumWidth(760)
        self.setMinimumHeight(220)
        self._sync_primary_button_state()
        self._apply_styles()

    def _coerce_impact(self, target_or_impact: Node | DeleteImpact) -> DeleteImpact:
        if isinstance(target_or_impact, DeleteImpact):
            return target_or_impact
        return self._session._io.preview_delete_nodes([str(target_or_impact.id)])  # noqa: SLF001

    def _header_text(self) -> str:
        incoming_count = len(self._impact.incoming_refs)
        target_label = "node(s)"
        incoming_label = "incoming reference(s)"
        if self._entity_kind == "link_type":
            target_label = "link type(s)"
            incoming_label = "dependent link(s)"
        return (
            f"Delete <b>{len(self._impact.targets)}</b> {target_label} with "
            f"<b>{incoming_count}</b> {incoming_label}"
        )

    def _populate_table(self) -> None:
        self._resolution_table.setRowCount(len(self._impact.incoming_refs))
        self._row_selectors.clear()
        for row_index, incoming_ref in enumerate(self._impact.incoming_refs):
            src_display, src_tooltip = self._source_label(
                incoming_ref.source_node_id)
            src_item = QTableWidgetItem(src_display)
            src_item.setToolTip(src_tooltip)
            self._resolution_table.setItem(row_index, 0, src_item)

            slot_item = QTableWidgetItem(
                ".".join(incoming_ref.source_slot_path))
            self._resolution_table.setItem(row_index, 1, slot_item)

            tgt_display, tgt_tooltip = self._target_label(
                incoming_ref.target_node_id)
            tgt_item = QTableWidgetItem(tgt_display)
            tgt_item.setToolTip(tgt_tooltip)
            self._resolution_table.setItem(row_index, 2, tgt_item)
            state_item = QTableWidgetItem(
                "resolved" if incoming_ref.is_resolved else "unresolved"
            )
            state_item.setForeground(
                Qt.GlobalColor.white
                if incoming_ref.is_resolved
                else Qt.GlobalColor.white
            )
            state_item.setBackground(
                Qt.GlobalColor.darkGreen if incoming_ref.is_resolved else Qt.GlobalColor.darkRed
            )
            self._resolution_table.setItem(row_index, 3, state_item)
            selector = self._build_resolution_selector(incoming_ref)
            self._resolution_table.setCellWidget(row_index, 4, selector)
            self._row_selectors.append((incoming_ref, selector))
        row_height = self._resolution_table.fontMetrics().height() + 10
        for row_index in range(self._resolution_table.rowCount()):
            self._resolution_table.setRowHeight(row_index, row_height)

    def _source_label(self, source_node_id: str) -> tuple[str, str]:
        """Return (display_text, tooltip_text) for the source column."""
        if self._entity_kind == "link_type":
            for link in self._session.list_links():
                if str(link.id) != source_node_id:
                    continue
                try:
                    source_name = self._session.get_node(
                        str(link.source_node_id)).name
                except KeyError:
                    source_name = str(link.source_node_id)
                try:
                    target_name = self._session.get_node(
                        str(link.target_node_id)).name
                except KeyError:
                    target_name = str(link.target_node_id)
                display = f"{source_name} -> {target_name}"
                tooltip = f"{display}\n{source_node_id}"
                return display, tooltip
            return source_node_id, source_node_id
        try:
            source_node = self._session.get_node(source_node_id)
        except KeyError:
            return source_node_id, source_node_id
        return source_node.name, f"{source_node.name}\n{source_node_id}"

    def _target_label(self, target_node_id: str) -> tuple[str, str]:
        """Return (display_text, tooltip_text) for the target column."""
        if self._entity_kind == "link_type":
            try:
                target_link_type = self._session.get_link_type(target_node_id)
            except KeyError:
                return target_node_id, target_node_id
            return target_link_type.name, f"{target_link_type.name}\n{target_node_id}"
        try:
            target_node = self._session.get_node(target_node_id)
        except KeyError:
            return target_node_id, target_node_id
        return target_node.name, f"{target_node.name}\n{target_node_id}"

    def _build_resolution_selector(self, incoming_ref: IncomingRef) -> QComboBox:
        selector = QComboBox(self)
        if self._entity_kind == "link_type":
            selector.addItem("Cascade delete link", ("remove_ref", None))
            selector.setEnabled(False)
            return selector
        selector.addItem("Leave dangling", ("leave_dangling", None))
        selector.addItem("Remove ref", ("remove_ref", None))
        if self._allow_replace:
            for replacement in self._replacement_candidates(incoming_ref):
                selector.addItem(
                    f"Replace with {replacement.name}",
                    ("replace", str(replacement.id)),
                )
        selector.currentIndexChanged.connect(self._sync_primary_button_state)
        return selector

    def _replacement_candidates(self, incoming_ref: IncomingRef) -> list[Node]:
        target_ids = set(self._impact.targets)
        try:
            target_node = self._session.get_node(incoming_ref.target_node_id)
            target_category = target_node.category
        except KeyError:
            target_category = None
        candidates: list[Node] = []
        for node in self._session.list_nodes():
            node_id = str(node.id)
            if node_id in target_ids:
                continue
            if target_category is not None and node.category != target_category:
                continue
            candidates.append(node)
        return candidates

    def selected_resolution(self) -> DeleteResolution | None:
        return self._accepted_resolution

    def _current_resolution(self) -> DeleteResolution:
        entries: list[DeleteResolutionEntry] = []
        for incoming_ref, selector in self._row_selectors:
            mode, replacement_id = selector.currentData()
            entries.append(
                DeleteResolutionEntry(
                    incoming_ref=incoming_ref,
                    mode=mode,
                    replacement_id=replacement_id,
                )
            )
        return DeleteResolution(entries=tuple(entries))

    def _sync_primary_button_state(self) -> None:
        resolution = self._current_resolution()
        safe = resolution.can_delete_safely
        self._primary_btn.setText("Delete" if safe else "Force Delete")
        self._primary_btn.setProperty("destructive", not safe)
        self._primary_btn.style().unpolish(self._primary_btn)
        self._primary_btn.style().polish(self._primary_btn)

    def _apply_styles(self) -> None:
        destructive_style = (
            f"color: {VALIDATION_ERROR_TEXT};"
            f"border: 1px solid {VALIDATION_ERROR_TEXT};"
            f"background: {FIELD_BUTTON_BG};"
        )
        neutral_style = (
            f"color: {FIELD_BUTTON_TEXT};"
            f"border: 1px solid {FIELD_BUTTON_BORDER};"
            f"background: {FIELD_BUTTON_BG};"
        )
        self._safe_btn.setStyleSheet(neutral_style)
        self.setStyleSheet(
            f"QDialog {{ background: {SCENE_BACKGROUND_COLOR}; color: {NODE_TEXT_COLOR}; }}"
            f"QTableWidget {{ background: {SCENE_BACKGROUND_COLOR}; border: 1px solid {EDGE_COLOR}; gridline-color: {EDGE_COLOR}; }}"
            f"QHeaderView::section {{ background: {FIELD_BUTTON_BG}; color: {NODE_TEXT_COLOR}; border: 0; border-bottom: 1px solid {EDGE_COLOR}; padding: 4px; }}"
            f"QPushButton[destructive='true'] {{ {destructive_style} }}"
            f"QPushButton[destructive='false'] {{ {neutral_style} }}"
            f"QPushButton:hover {{ background: {FIELD_BUTTON_PRESSED_BG}; }}"
        )

    def _apply_resolution(self, resolution: DeleteResolution, *, label: str) -> None:
        _ = label
        if self._apply_resolution_delegate is None:
            try:
                result = self._session._io.delete_nodes(  # noqa: SLF001
                    list(self._impact.targets),
                    resolution=resolution,
                )
                if not result.ok:
                    raise ValueError(
                        result.error_message or "Delete operation failed")
                self._session.notify_io_mutation("node")
                self._accepted_resolution = resolution
                return
            except Exception:  # noqa: BLE001
                # Compatibility fallback: keep existing behavior for edge cases
                # where validation of transitional delete states still raises.
                def _fallback_mutate(repository: Repository) -> set[str]:
                    return _apply_delete_resolution(
                        repository,
                        impact=self._impact,
                        resolution=resolution,
                    )

                fallback_result = self._session._io.apply_op(  # noqa: SLF001
                    _fallback_mutate,
                )
                if not fallback_result.ok:
                    raise ValueError(
                        fallback_result.error_message or "Delete operation failed"
                    )
                self._session.notify_io_mutation("node")
                self._accepted_resolution = resolution
                return

        def _mutate(repository: Repository) -> set[str]:
            return self._apply_resolution_delegate(repository, self._impact, resolution)

        result = self._session._io.apply_op(_mutate)  # noqa: SLF001
        if not result.ok:
            raise ValueError(result.error_message or "Delete operation failed")
        change_type = "link_type" if self._entity_kind == "link_type" else "node"
        self._session.notify_io_mutation(change_type)
        self._accepted_resolution = resolution

    def _on_safe_delete(self) -> None:
        resolution = self._current_resolution()
        if self._impact.incoming_refs and not resolution.can_delete_safely:
            return
        self._apply_resolution(resolution, label="ref_aware_delete_safe")
        self.accept()

    def _on_accept_primary(self) -> None:
        resolution = self._current_resolution()
        label = (
            "ref_aware_delete_safe"
            if resolution.can_delete_safely
            else "ref_aware_delete_force"
        )
        self._apply_resolution(resolution, label=label)
        self.accept()

    def _on_force_delete(self) -> None:
        resolution = DeleteResolution(
            entries=tuple(
                DeleteResolutionEntry(
                    incoming_ref=incoming_ref,
                    mode="leave_dangling",
                )
                for incoming_ref in self._impact.incoming_refs
            )
        )
        self._apply_resolution(resolution, label="ref_aware_delete_force")
        self.accept()

    def _on_replace_with(self) -> None:
        if not self._allow_replace:
            return
        target_node = None
        if len(self._impact.targets) == 1:
            target_node = self._session.get_node(self._impact.targets[0])
        picker = QKnowledgeRefPickerDialog(
            self._session,
            ref_type=target_node.category if target_node is not None else None,
            slot_name="replacement",
            parent=self,
        )
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        new_id = picker.selected_node_id()
        if new_id is None or new_id in set(self._impact.targets):
            return
        for _incoming_ref, selector in self._row_selectors:
            for index in range(selector.count()):
                mode, replacement_id = selector.itemData(index)
                if mode == "replace" and replacement_id == new_id:
                    selector.setCurrentIndex(index)
                    break
        resolution = self._current_resolution()
        if not resolution.entries:
            resolution = DeleteResolution(
                entries=tuple(
                    DeleteResolutionEntry(
                        incoming_ref=incoming_ref,
                        mode="replace",
                        replacement_id=new_id,
                    )
                    for incoming_ref in self._impact.incoming_refs
                )
            )
        self._apply_resolution(
            resolution,
            label="ref_aware_delete_replace",
        )
        self.accept()


__all__ = [
    "DeleteResolution",
    "DeleteResolutionEntry",
    "QKnowledgeRefAwareDeleteDialog",
    "find_all_users",
]

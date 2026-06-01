"""Link-instances library panel built on the shared context library component."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.ui.components.context_library_panel import (
    QKnowledgeContextLibraryPanel,
)


class QKnowledgeLinkInstancesLibraryPanel(QKnowledgeContextLibraryPanel):
    """Link-instances library with multi-select delete support."""

    link_instance_load_requested = Signal(str)
    link_instance_deleted = Signal(str)

    def __init__(
        self,
        session: EditorSession,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(session=session, context="link_instance", parent=parent)

        # Back-compat aliases expected by tests/callers for library panels.
        self._add_btn = self._new_btn
        self._add_btn.setEnabled(False)
        self._add_btn.setToolTip(
            "Link instances are created via graph or mutation flows")

        self._tree.setToolTip(
            "Link instances. Multi-select items to delete in one action."
        )

        self.node_load_requested.connect(
            self.link_instance_load_requested.emit)
        self.node_deleted.connect(self.link_instance_deleted.emit)

    def set_current_open_link_instance(self, link_instance_id: str | None) -> None:
        """Mark the currently open link instance for bold emphasis."""
        self.set_current_open_node(link_instance_id)


__all__ = ["QKnowledgeLinkInstancesLibraryPanel"]

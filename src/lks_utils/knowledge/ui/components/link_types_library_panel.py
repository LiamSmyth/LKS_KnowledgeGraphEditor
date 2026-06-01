"""Link-types library panel built on the shared context library component."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.ui.components.context_library_panel import (
    QKnowledgeContextLibraryPanel,
)


class QKnowledgeLinkTypesLibraryPanel(QKnowledgeContextLibraryPanel):
    """Link-types library using the same shell and controls as type/instance libraries.

    Exposes backward-compatible signal names and button aliases expected by
    existing link-types tab code/tests.
    """

    link_type_load_requested = Signal(str)
    link_type_deleted = Signal(str)

    def __init__(
        self,
        session: EditorSession,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(session=session, context="link_type", parent=parent)

        # Back-compat aliases expected by existing tests/callers.
        self._add_btn = self._new_btn
        self._tree.setToolTip(
            "Available link types. User link types are editable; system link types are shown read-only."
        )

        self.node_load_requested.connect(self.link_type_load_requested.emit)
        self.node_deleted.connect(self.link_type_deleted.emit)

    def set_current_open_link_type(self, link_type_id: str) -> None:
        """Mark the currently open link type for bold emphasis."""
        self.set_current_open_node(link_type_id)


__all__ = ["QKnowledgeLinkTypesLibraryPanel"]

"""Live reload coordinator for graph tab — journal poll + same-origin fast path."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from lks_utils.knowledge.editor_session import EditorSession
from lks_utils.knowledge.io.knowledge_change_journal import read_change_events_since
from lks_utils.knowledge.io.knowledge_change_journal_dispatcher import (
    KnowledgeChangeJournalDispatcher,
)


class LiveReloadCoordinator:
    """Poll KB + canvas journal events and trigger reload callbacks."""

    def __init__(
        self,
        session: EditorSession,
        *,
        on_external_events: Callable[[list[dict[str, object]]], bool] | None = None,
        on_same_origin_skip: Callable[[], None] | None = None,
    ) -> None:
        self._session = session
        self._on_external_events = on_external_events
        self._on_same_origin_skip = on_same_origin_skip
        self._journal_offset = 0
        self._dispatcher: KnowledgeChangeJournalDispatcher | None = None

    @property
    def journal_offset(self) -> int:
        return self._journal_offset

    @journal_offset.setter
    def journal_offset(self, value: int) -> None:
        self._journal_offset = int(value)
        if self._dispatcher is not None:
            self._dispatcher.set_offset(self._journal_offset)

    def poll_external_events(self) -> list[dict[str, object]]:
        """Read and filter journal events from other processes."""
        repo_root = self._session.repository_root
        if repo_root is None:
            return []
        offset, events = read_change_events_since(repo_root, offset=self._journal_offset)
        self._journal_offset = offset
        current_pid = os.getpid()
        external = [
            event
            for event in events
            if int(event.get("process_id", current_pid)) != current_pid
        ]
        if external and self._on_external_events is not None:
            self._on_external_events(external)
        return external

    def poll_dispatcher_events(self, repo_root: Path) -> list[dict[str, object]]:
        """Poll via KnowledgeChangeJournalDispatcher (graph-tab integration path)."""
        if self._dispatcher is None:
            self._dispatcher = KnowledgeChangeJournalDispatcher(repo_root)
            self._dispatcher.set_offset(self._journal_offset)
        events = self._dispatcher.poll_and_dispatch()
        self._journal_offset = self._dispatcher.offset
        current_pid = os.getpid()
        return [
            event
            for event in events
            if int(event.get("process_id", current_pid)) != current_pid
        ]

    def handle_same_origin_effects(self, effects: Any | None) -> bool:
        """Fast-path: skip redundant journal reload for UI-issued mutates."""
        if effects is None:
            return False
        if self._on_same_origin_skip is not None:
            self._on_same_origin_skip()
        return True


__all__ = ["LiveReloadCoordinator"]

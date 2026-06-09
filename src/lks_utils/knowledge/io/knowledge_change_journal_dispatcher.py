"""Dedicated journal IO dispatcher for knowledge change events."""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from lks_utils.knowledge.io.knowledge_change_journal import read_change_events_since


class KnowledgeChangeJournalDispatcher:
    """Stateful reader/dispatcher for the knowledge change journal.

    This helper centralizes incremental journal reads so Python services and UI
    components can share one consistent event-consumption behavior.
    """

    def __init__(
        self,
        repo_root: Path,
        *,
        include_current_process: bool = False,
        get_current_process_id: Callable[[], int] | None = None,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._offset = 0
        self._include_current_process = include_current_process
        self._get_current_process_id = get_current_process_id or os.getpid
        self._listeners: dict[int, tuple[set[str] | None,
                                         Callable[[dict[str, object]], None]]] = {}
        self._next_listener_token = 1

    @property
    def repo_root(self) -> Path:
        """Return repository root this dispatcher is bound to."""
        return self._repo_root

    @property
    def offset(self) -> int:
        """Return current journal byte offset."""
        return self._offset

    def set_offset(self, offset: int) -> None:
        """Override current journal offset."""
        self._offset = max(0, int(offset))

    def seed_offset_to_end(self) -> None:
        """Advance cursor to current file end to ignore historical records."""
        journal = self._repo_root / ".knowledge_events.jsonl"
        if not journal.exists():
            self._offset = 0
            return
        self._offset = int(journal.stat().st_size)

    def subscribe(
        self,
        callback: Callable[[dict[str, object]], None],
        *,
        event_types: set[str] | None = None,
    ) -> int:
        """Register one callback; optionally scope it to specific event types."""
        token = self._next_listener_token
        self._next_listener_token += 1
        normalized = {str(value)
                      for value in event_types} if event_types else None
        self._listeners[token] = (normalized, callback)
        return token

    def unsubscribe(self, token: int) -> None:
        """Unregister one callback by subscription token."""
        self._listeners.pop(int(token), None)

    def poll(self) -> list[dict[str, object]]:
        """Read newly appended journal events since the current offset."""
        next_offset, events = read_change_events_since(
            self._repo_root, offset=self._offset)
        self._offset = next_offset
        if self._include_current_process:
            return events
        process_id = str(self._get_current_process_id())
        return [
            event
            for event in events
            if str(event.get("process_id", "")) != process_id
        ]

    def dispatch(self, events: list[dict[str, object]]) -> None:
        """Deliver events to registered callbacks using optional type filters."""
        if not events or not self._listeners:
            return
        for event in events:
            event_type = str(event.get("event_type", ""))
            for allowed_types, callback in list(self._listeners.values()):
                if allowed_types is not None and event_type not in allowed_types:
                    continue
                callback(event)

    def poll_and_dispatch(self) -> list[dict[str, object]]:
        """Poll new events and deliver them to subscriptions."""
        events = self.poll()
        self.dispatch(events)
        return events

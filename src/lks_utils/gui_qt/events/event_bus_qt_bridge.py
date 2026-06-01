"""Qt bridge for routing pure-Python bus events into Qt signals."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from lks_utils.events import EventBus, EventEnvelope, EventSubscription


class EventBusQtBridge(QObject):
    """Bridge EventBus callbacks onto Qt signals."""

    event_received = Signal(object)

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = bus
        self._subscription: EventSubscription | None = None

    def start(self, *, stream: str | None = None, event_type: str | None = None) -> None:
        """Subscribe bridge callback to the Python event bus."""
        if self._subscription is not None:
            return
        self._subscription = self._bus.subscribe(
            self._on_event,
            stream=stream,
            event_type=event_type,
        )

    def stop(self) -> None:
        """Unsubscribe bridge callback from the Python event bus."""
        if self._subscription is None:
            return
        self._bus.unsubscribe(self._subscription)
        self._subscription = None

    def _on_event(self, event: EventEnvelope) -> None:
        self.event_received.emit(event)

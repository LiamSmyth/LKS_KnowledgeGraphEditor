"""Threaded event bus with non-blocking queued dispatch."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread

from lks_utils.events.event_envelope import EventEnvelope


EventCallback = Callable[[EventEnvelope], None]


@dataclass(frozen=True)
class EventSubscription:
    """Handle returned by ``EventBus.subscribe``."""

    token: int


@dataclass
class _Subscriber:
    token: int
    callback: EventCallback
    stream: str | None
    event_type: str | None


class EventBus:
    """In-process pub/sub with threaded non-blocking dispatch.

    Backpressure policy: if the queue is full, the oldest queued event is dropped.
    """

    def __init__(self, *, queue_size: int = 2048) -> None:
        self._queue: Queue[EventEnvelope] = Queue(maxsize=max(1, queue_size))
        self._subscribers: list[_Subscriber] = []
        self._lock = Lock()
        self._token_counter = 0
        self._stop = Event()
        self._worker = Thread(
            target=self._run, name="EventBusWorker", daemon=True)
        self._worker.start()

    def subscribe(
        self,
        callback: EventCallback,
        *,
        stream: str | None = None,
        event_type: str | None = None,
    ) -> EventSubscription:
        """Subscribe a callback and return a removable subscription handle."""
        with self._lock:
            self._token_counter += 1
            token = self._token_counter
            self._subscribers.append(
                _Subscriber(
                    token=token,
                    callback=callback,
                    stream=stream,
                    event_type=event_type,
                )
            )
        return EventSubscription(token=token)

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """Remove one subscription if present."""
        token = subscription.token
        with self._lock:
            self._subscribers = [
                sub for sub in self._subscribers if sub.token != token
            ]

    def publish(self, event: EventEnvelope) -> None:
        """Queue one event for asynchronous dispatch."""
        try:
            self._queue.put_nowait(event)
            return
        except Exception:
            pass

        # Queue full: drop one oldest item and retry exactly once.
        try:
            _ = self._queue.get_nowait()
        except Empty:
            return
        try:
            self._queue.put_nowait(event)
        except Exception:
            return

    def close(self, *, timeout_seconds: float = 1.0) -> None:
        """Stop worker dispatch and release subscribers."""
        self._stop.set()
        self._worker.join(timeout=timeout_seconds)
        with self._lock:
            self._subscribers.clear()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.05)
            except Empty:
                continue
            self._dispatch(event)

    def _dispatch(self, event: EventEnvelope) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for sub in subscribers:
            if sub.stream is not None and sub.stream != event.stream:
                continue
            if sub.event_type is not None and sub.event_type != event.event_type:
                continue
            try:
                sub.callback(event)
            except Exception:
                # Listener failures must not break the bus.
                continue

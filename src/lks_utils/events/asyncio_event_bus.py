"""Asyncio-native event bus for async consumers."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from lks_utils.events.event_envelope import EventEnvelope


AsyncEventCallback = Callable[[EventEnvelope], Awaitable[None] | None]


@dataclass(frozen=True)
class AsyncEventSubscription:
    """Handle returned by ``AsyncioEventBus.subscribe``."""

    token: int


@dataclass
class _AsyncSubscriber:
    token: int
    callback: AsyncEventCallback
    stream: str | None
    event_type: str | None


class AsyncioEventBus:
    """Async pub/sub bus backed by ``asyncio.Queue``."""

    def __init__(self, *, queue_size: int = 2048) -> None:
        self._queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(
            maxsize=max(1, queue_size))
        self._subscribers: list[_AsyncSubscriber] = []
        self._token_counter = 0
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start dispatch task if not running."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._run(), name="AsyncioEventBusWorker")

    async def stop(self) -> None:
        """Stop dispatch task and clear subscribers."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._subscribers.clear()

    def subscribe(
        self,
        callback: AsyncEventCallback,
        *,
        stream: str | None = None,
        event_type: str | None = None,
    ) -> AsyncEventSubscription:
        """Subscribe one async callback and return its handle."""
        self._token_counter += 1
        token = self._token_counter
        self._subscribers.append(
            _AsyncSubscriber(
                token=token,
                callback=callback,
                stream=stream,
                event_type=event_type,
            )
        )
        return AsyncEventSubscription(token=token)

    def unsubscribe(self, subscription: AsyncEventSubscription) -> None:
        """Remove one subscription if present."""
        token = subscription.token
        self._subscribers = [
            sub for sub in self._subscribers if sub.token != token
        ]

    async def publish(self, event: EventEnvelope) -> None:
        """Publish one event with drop-oldest backpressure handling."""
        if self._queue.full():
            try:
                _ = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self._queue.put(event)

    async def _run(self) -> None:
        while self._running:
            event = await self._queue.get()
            await self._dispatch(event)

    async def _dispatch(self, event: EventEnvelope) -> None:
        subscribers = list(self._subscribers)
        for sub in subscribers:
            if sub.stream is not None and sub.stream != event.stream:
                continue
            if sub.event_type is not None and sub.event_type != event.event_type:
                continue
            try:
                result = sub.callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                continue

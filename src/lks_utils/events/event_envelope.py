"""Typed event envelope for cross-module event transport."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class EventEnvelope:
    """Generic event payload for in-process and cross-process transport."""

    stream: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source_id: str | None = None
    bundle_id: str | None = None
    process_id: int | None = None
    timestamp: float = field(default_factory=time)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    schema_version: int = 1

    def to_record(self) -> dict[str, object]:
        """Return a JSON-serializable record suitable for journaling."""
        return {
            "schema_version": int(self.schema_version),
            "event_id": self.event_id,
            "stream": self.stream,
            "event_type": self.event_type,
            "timestamp": float(self.timestamp),
            "process_id": self.process_id,
            "source_id": self.source_id,
            "bundle_id": self.bundle_id,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_record(cls, record: dict[str, object]) -> EventEnvelope:
        """Create an envelope from one journal record."""
        payload_obj = record.get("payload")
        payload: dict[str, Any] = (
            dict(payload_obj)
            if isinstance(payload_obj, dict)
            else {}
        )
        return cls(
            stream=str(record.get("stream", "default")),
            event_type=str(record.get("event_type", "")),
            payload=payload,
            source_id=_as_optional_str(record.get("source_id")),
            bundle_id=_as_optional_str(record.get("bundle_id")),
            process_id=_as_optional_int(record.get("process_id")),
            timestamp=float(record.get("timestamp", time())),
            event_id=str(record.get("event_id", uuid4().hex)),
            schema_version=int(record.get("schema_version", 1)),
        )


def _as_optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _as_optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None

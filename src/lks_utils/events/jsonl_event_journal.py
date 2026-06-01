"""Generic JSONL-backed event journal for cross-process synchronization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lks_utils.events.event_envelope import EventEnvelope


DEFAULT_JOURNAL_SCHEMA_VERSION = 1


def journal_filename_for_stream(stream: str) -> str:
    """Return deterministic journal filename for one stream."""
    token = _sanitize_stream(stream)
    return f".{token}.jsonl"


def journal_path_for_stream(repo_root: Path, stream: str) -> Path:
    """Return full journal path for one stream under *repo_root*."""
    return repo_root / journal_filename_for_stream(stream)


def append_journal_event(repo_root: Path, stream: str, event: EventEnvelope) -> None:
    """Append one event envelope record to the stream journal."""
    path = journal_path_for_stream(repo_root, stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = event.to_record()
    if "schema_version" not in record:
        record["schema_version"] = DEFAULT_JOURNAL_SCHEMA_VERSION
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def append_journal_record(repo_root: Path, stream: str, record: dict[str, Any]) -> None:
    """Append one pre-serialized record to the stream journal."""
    path = journal_path_for_stream(repo_root, stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    payload.setdefault("schema_version", DEFAULT_JOURNAL_SCHEMA_VERSION)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def read_journal_records_since(
    repo_root: Path,
    stream: str,
    *,
    offset: int,
) -> tuple[int, list[dict[str, object]]]:
    """Read records from one stream journal after *offset* bytes."""
    path = journal_path_for_stream(repo_root, stream)
    if not path.exists():
        return offset, []

    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        handle.seek(max(0, offset))
        while True:
            line = handle.readline()
            if not line:
                break
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        new_offset = handle.tell()
    return new_offset, records


def _sanitize_stream(stream: str) -> str:
    token = "".join(ch if (ch.isalnum() or ch in {
                    "-", "_"}) else "_" for ch in stream)
    token = token.strip("_")
    return token or "events"

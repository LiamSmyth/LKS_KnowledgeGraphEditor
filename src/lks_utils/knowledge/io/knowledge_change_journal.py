"""Repo-backed append-only journal for cross-process knowledge change events."""
from __future__ import annotations

import os
from pathlib import Path

from lks_utils.events import append_journal_record, journal_path_for_stream, read_journal_records_since
from lks_utils.knowledge.knowledge_change_event import KnowledgeChangeEvent

_KNOWLEDGE_EVENT_STREAM = "knowledge_events"
EVENT_JOURNAL_FILENAME = ".knowledge_events.jsonl"


def append_change_event(repo_root: Path, event: KnowledgeChangeEvent) -> None:
    """Append one knowledge change event record to the repo journal."""
    record = {
        "schema_version": 1,
        "event_type": event.event_type,
        "entity_id": event.entity_id,
        "entity_type": event.entity_type,
        "bundle_id": event.bundle_id,
        "timestamp": float(event.timestamp),
        "process_id": os.getpid(),
        "violations": [str(issue) for issue in event.violations],
    }
    append_journal_record(repo_root, _KNOWLEDGE_EVENT_STREAM, record)


def read_change_events_since(
    repo_root: Path,
    *,
    offset: int,
) -> tuple[int, list[dict[str, object]]]:
    """Read journal records after *offset* bytes and return new offset + events."""
    return read_journal_records_since(
        repo_root,
        _KNOWLEDGE_EVENT_STREAM,
        offset=offset,
    )


def journal_file_path(repo_root: Path) -> Path:
    """Return the canonical journal file path for *repo_root*."""
    return journal_path_for_stream(repo_root, _KNOWLEDGE_EVENT_STREAM)

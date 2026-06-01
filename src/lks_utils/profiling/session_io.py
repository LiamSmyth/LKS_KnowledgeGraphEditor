"""Profiling session file I/O — gzip JSONL .lksprof format.

File format: each line is a JSON object representing one :class:`FrameSample`.
The file is gzip-compressed with a ``Content-Type`` header on the first line::

    {"lksprof": "1", "frame_count": N}   ← header (line 0)
    {"frame_index": 0, "wall_ms": 12.5, "call_tree": {...}, ...}
    {"frame_index": 1, "wall_ms": 11.8, ...}
    ...

The header is optional on read for forward compatibility.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from lks_utils.profiling.frame_sample import FrameSample


_FORMAT_VERSION = "1"
_EXTENSION = ".lksprof"


def export_session(path: Path | str, samples: list[FrameSample]) -> None:
    """Write *samples* to a gzip JSONL ``.lksprof`` file at *path*.

    Creates any missing parent directories.  Uses an atomic write (temp file
    followed by rename) to avoid partial writes on crash.

    Args:
        path: Destination file path.  A ``.lksprof`` extension is appended
              if not already present.
        samples: Ordered list of frame samples to persist.

    Raises:
        OSError: If the file cannot be written.
    """
    dest = Path(path)
    if dest.suffix.lower() != _EXTENSION:
        dest = dest.with_suffix(_EXTENSION)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".lksprof.tmp")

    header = json.dumps(
        {"lksprof": _FORMAT_VERSION, "frame_count": len(samples)},
        separators=(",", ":"),
    )
    lines = [header] + [
        json.dumps(sample.to_dict(), separators=(",", ":")) for sample in samples
    ]
    payload = "\n".join(lines).encode()

    with gzip.open(tmp, "wb") as fh:
        fh.write(payload)

    tmp.replace(dest)


def load_session(path: Path | str) -> list[FrameSample]:
    """Read a ``.lksprof`` file and return the ordered frame samples.

    The first line (header) is skipped if it contains the ``"lksprof"`` key.

    Args:
        path: Path to a ``.lksprof`` file (gzip JSONL).

    Returns:
        List of :class:`FrameSample` in original capture order.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If the file format is invalid.
    """
    src = Path(path)
    with gzip.open(src, "rb") as fh:
        raw = fh.read().decode()

    samples: list[FrameSample] = []
    for line_no, line in enumerate(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON on line {line_no + 1} of {src}: {exc}"
            ) from exc

        # Skip the header line
        if "lksprof" in data:
            continue

        try:
            samples.append(FrameSample.from_dict(data))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Cannot deserialize FrameSample on line {line_no + 1}: {exc}"
            ) from exc

    return samples


__all__ = ["export_session", "load_session"]

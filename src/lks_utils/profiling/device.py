"""Profiling device classification for generic frame samples."""
from __future__ import annotations

from enum import Enum


class Device(str, Enum):
    """Execution device associated with a profiling stage."""

    CPU = "cpu"
    GPU = "gpu"
    HANDOFF = "handoff"  # GPU<->CPU synchronization (fence/readback/upload)
    UNKNOWN = "unknown"


__all__ = ["Device"]

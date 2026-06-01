"""Types for mutation-driven EditorSession workflows."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class LastSaveStatus(str, Enum):
    """Persistence result of the most recent mutation."""

    OK = "ok"
    FAILED = "failed"


@dataclass(slots=True)
class MutationResult:
    """Result payload returned by EditorSession.apply_mutation."""

    ok: bool
    last_save_status: LastSaveStatus
    touched_ids: set[str]
    save_error: str | None = None


@dataclass(frozen=True, slots=True)
class SessionChangeEvent:
    """Typed session-change payload emitted alongside legacy change strings."""

    change_type: str
    touched_ids: frozenset[str] | None = None
    origin: str | None = None

    @property
    def is_precise(self) -> bool:
        """Return whether touched ids are available for precise gating."""
        return self.touched_ids is not None

    def touches_any(self, object_ids: set[str] | list[str] | tuple[str, ...]) -> bool:
        """Return whether event touches any of the provided ids.

        Falls back to ``True`` when touched ids are unavailable to preserve
        broad refresh behavior in subscribers.
        """
        if self.touched_ids is None:
            return True
        for object_id in object_ids:
            if str(object_id) in self.touched_ids:
                return True
        return False


class FatalValidationError(RuntimeError):
    """Raised when fatal integrity issues block mutation commit."""

    def __init__(self, issues: list[Any]) -> None:
        self.issues = issues
        message = "Fatal validation failed"
        if issues:
            message = f"{message}: {len(issues)} issue(s)"
        super().__init__(message)


__all__ = [
    "FatalValidationError",
    "LastSaveStatus",
    "MutationResult",
    "SessionChangeEvent",
]

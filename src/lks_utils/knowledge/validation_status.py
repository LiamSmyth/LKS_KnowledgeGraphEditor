"""Base validation status contract for knowledge objects."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ValidationStatus(ABC):
    """Abstract validity status for one object id."""

    @property
    @abstractmethod
    def is_valid(self) -> bool:
        """Return True when the target object has no known validation issues."""

    @property
    @abstractmethod
    def reasons(self) -> tuple[str, ...]:
        """Return a normalized tuple of human-readable reasons."""


__all__ = ["ValidationStatus"]

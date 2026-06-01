"""Valid sentinel status for validation index lookups."""
from __future__ import annotations

from lks_utils.knowledge.validation_status import ValidationStatus


class ValidValidationStatus(ValidationStatus):
    """Represents a known-valid object."""

    @property
    def is_valid(self) -> bool:
        return True

    @property
    def reasons(self) -> tuple[str, ...]:
        return ()


__all__ = ["ValidValidationStatus"]

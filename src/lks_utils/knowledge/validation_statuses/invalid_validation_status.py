"""Invalid status carrying one or more validation reasons."""
from __future__ import annotations

from lks_utils.knowledge.validation_status import ValidationStatus


class InvalidValidationStatus(ValidationStatus):
    """Represents a validation failure for one object."""

    def __init__(self, reasons: list[str]) -> None:
        unique_reasons = sorted({reason.strip() for reason in reasons if reason.strip()})
        self._reasons: tuple[str, ...] = tuple(unique_reasons)

    @property
    def is_valid(self) -> bool:
        return False

    @property
    def reasons(self) -> tuple[str, ...]:
        return self._reasons


__all__ = ["InvalidValidationStatus"]

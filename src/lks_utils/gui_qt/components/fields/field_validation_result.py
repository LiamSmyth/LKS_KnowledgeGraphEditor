"""Validation result model for field values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldValidationResult:
    """Represents whether a value passed validation and optional normalization."""

    is_valid: bool
    message: str = ""
    normalized_value: Any = None

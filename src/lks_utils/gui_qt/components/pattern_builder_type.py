"""Base class for pattern builder types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from PySide6.QtWidgets import QWidget


class PatternBuilderType(ABC):
    """Base class for pattern builder types.

    Each pattern builder type represents a different mode for constructing
    regex patterns (Line matching, Span extraction, Section extraction, or Custom).

    Subclasses must implement:
    - create_ui(): Create Qt widgets for configuration
    - build_pattern(): Generate regex pattern from UI state
    - get_config(): Serialize current configuration to dict
    - set_config(): Restore configuration from dict
    - get_type_name(): Return display name for this pattern type
    - set_on_change(): Register callback for config changes
    """

    def __init__(self) -> None:
        """Initialize the pattern builder type."""
        self._on_change_callback: Callable[[], None] | None = None

    def set_on_change(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when configuration changes.

        Args:
            callback: Function to call when any configuration field changes.
        """
        self._on_change_callback = callback

    def _notify_change(self) -> None:
        """Notify parent that configuration has changed."""
        if self._on_change_callback:
            self._on_change_callback()

    @abstractmethod
    def create_ui(self, parent: QWidget | None = None) -> QWidget:
        """Create and return the configuration UI widget.

        Args:
            parent: Parent widget

        Returns:
            QWidget containing the configuration controls for this pattern type
        """
        pass

    @abstractmethod
    def build_pattern(self, include_full_match: bool = False) -> str:
        """Build regex pattern from current UI configuration.

        Args:
            include_full_match: If True, wrap entire pattern to capture full match.
                              If False, capture only the extracted portion.

        Returns:
            Regex pattern string
        """
        pass

    @abstractmethod
    def get_config(self) -> dict[str, Any]:
        """Get current configuration as dictionary.

        Returns:
            Dictionary with pattern type-specific configuration
        """
        pass

    @abstractmethod
    def set_config(self, config: dict[str, Any]) -> None:
        """Set configuration from dictionary.

        Args:
            config: Dictionary with pattern type-specific configuration
        """
        pass

    @abstractmethod
    def get_type_name(self) -> str:
        """Get display name for this pattern type.

        Returns:
            Human-readable name (e.g., "Line Matching", "Span Extraction")
        """
        pass

    @abstractmethod
    def get_type_id(self) -> str:
        """Get unique identifier for this pattern type.

        Returns:
            Lowercase identifier (e.g., "line", "span", "section", "custom",
            "prefix", "delimiter")
        """
        pass

    def test_matches(self, text: str) -> list[str] | None:
        """Test the pattern against sample text using type-specific logic.

        Override in subclasses that produce non-regex output (e.g. prefix,
        delimiter) so the test area can show meaningful results without
        attempting to compile the output as a regex.

        Returns:
            List of matched strings, or *None* to fall back to the default
            regex-based testing in :class:`QPatternBuilderComponent`.
        """
        return None

    def uses_regex_output(self) -> bool:
        """Return True if build_pattern() produces a regex string.

        Non-regex types (prefix, delimiter) should return False so the
        pattern builder hides irrelevant controls like "Include matched text".
        """
        return True

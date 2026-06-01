"""
Token-based naming template system for generating file names.

Provides flexible filename generation using a template syntax with
support for dates, times, indices, and custom tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from lks_utils.text.filename import sanitize_filename


# Token pattern regex: {token_name:format|delimiter_replacement}
# Note: token_name can include dots (e.g., .ext)
TOKEN_PATTERN = re.compile(r'\{(\.?\w+)(?::([^}|]+))?(?:\|([^}]+))?\}')


@dataclass
class TokenInfo:
    """Information about a template token.

    Attributes:
        name: Token name (e.g., "base_name", "date")
        description: Human-readable description
        default_format: Default format string (if applicable)
        examples: Example outputs
    """
    name: str
    description: str
    default_format: str = ""
    examples: list[str] = None  # type: ignore

    def __post_init__(self) -> None:
        """Initialize examples list."""
        if self.examples is None:
            self.examples = []


class NamingTemplate:
    """Template-based filename generator with token substitution.

    Supports tokens for dynamic content:
    - {base_name}: Source name (sanitized)
    - {date}: Current date (default: YYYYMMDD)
    - {datetime}: Current date and time (default: YYYYMMDD_HHMMSS)
    - {index}: Sequential number (default: %d)
    - {ext}: Extension without dot
    - {.ext}: Extension with dot

    Format specifiers:
    - {date:%Y-%m-%d}: Custom date format
    - {datetime:%Y%m%d_%H%M%S}: Custom datetime format
    - {index:%03d}: Zero-padded index

    Delimiter replacement:
    - {date:%Y-%m-%d|_}: Replace - with _ in output

    Examples:
        >>> template = NamingTemplate("{base_name}_{date}")
        >>> template.render(base_name="MyProject")
        'MyProject_20260126'

        >>> template = NamingTemplate("backup_{datetime:%Y%m%d}.{ext}")
        >>> template.render(base_name="data", ext="zip")
        'backup_20260126.zip'
    """

    def __init__(self, template: str) -> None:
        """Initialize template.

        Args:
            template: Template string with {token} placeholders
        """
        self.template = template
        self._tokens = self._parse_tokens()

    def _parse_tokens(self) -> list[tuple[str, str, str]]:
        """Parse tokens from template.

        Returns:
            List of (token_name, format_spec, delimiter_replacement) tuples
        """
        tokens = []
        for match in TOKEN_PATTERN.finditer(self.template):
            token_name = match.group(1)
            format_spec = match.group(2) or ""
            delimiter_replacement = match.group(3) or ""
            tokens.append((token_name, format_spec, delimiter_replacement))
        return tokens

    def render(self, **context: Any) -> str:
        """Render template with provided context.

        Args:
            **context: Values for tokens (base_name, ext, index, etc.)

        Returns:
            Rendered filename string

        Examples:
            >>> template.render(base_name="MyProject", ext="tar.gz")
            'MyProject_20260126.tar.gz'
        """
        result = self.template
        now = datetime.now()

        for token_name, format_spec, delimiter_replacement in self._tokens:
            # Build replacement value
            value = ""

            if token_name == "base_name":
                value = sanitize_filename(context.get("base_name", "file"))

            elif token_name == "date":
                date_format = format_spec or "%Y%m%d"
                value = now.strftime(date_format)

            elif token_name == "datetime":
                datetime_format = format_spec or "%Y%m%d_%H%M%S"
                value = now.strftime(datetime_format)

            elif token_name == "time":
                time_format = format_spec or "%H%M%S"
                value = now.strftime(time_format)

            elif token_name == "index":
                index = context.get("index", 1)
                index_format = format_spec or "%d"
                value = index_format % index

            elif token_name == "ext":
                ext = context.get("ext", "")
                # Remove leading dot if present
                value = ext.lstrip(".")

            elif token_name == ".ext":
                ext = context.get("ext", "")
                # Ensure leading dot
                value = f".{ext.lstrip('.')}" if ext else ""

            else:
                # Unknown token - leave as is or use context value
                value = str(context.get(token_name, f"{{{token_name}}}"))

            # Apply delimiter replacement if specified
            if delimiter_replacement and value:
                # Find delimiter to replace (e.g., '-' in '2026-01-26')
                delimiters_to_replace = ['-', ':', ' ', '/']
                for delim in delimiters_to_replace:
                    if delim in value:
                        value = value.replace(delim, delimiter_replacement)

            # Replace token in template
            # Reconstruct the original token pattern
            token_pattern = f"{{{token_name}"
            if format_spec:
                token_pattern += f":{format_spec}"
            if delimiter_replacement:
                token_pattern += f"|{delimiter_replacement}"
            token_pattern += "}"

            result = result.replace(token_pattern, value)

        return result

    def validate(self) -> tuple[bool, str]:
        """Validate template syntax.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Try to parse tokens
        try:
            self._parse_tokens()
        except Exception as e:
            return False, f"Invalid template syntax: {e}"

        # Check for unsupported tokens
        supported = {"base_name", "date", "datetime",
                     "time", "index", "ext", ".ext"}
        for token_name, _, _ in self._tokens:
            if token_name not in supported:
                return False, f"Unsupported token: {{{token_name}}}"

        return True, ""

    @staticmethod
    def get_available_tokens() -> list[TokenInfo]:
        """Get list of available tokens with descriptions.

        Returns:
            List of TokenInfo objects
        """
        return [
            TokenInfo(
                name="base_name",
                description="Source name (sanitized for filesystem)",
                examples=["MyProject", "data_file"],
            ),
            TokenInfo(
                name="date",
                description="Current date",
                default_format="%Y%m%d",
                examples=["20260126", "2026-01-26 (with :%Y-%m-%d)"],
            ),
            TokenInfo(
                name="datetime",
                description="Current date and time",
                default_format="%Y%m%d_%H%M%S",
                examples=["20260126_143052",
                          "2026-01-26_14:30:52 (with format)"],
            ),
            TokenInfo(
                name="time",
                description="Current time",
                default_format="%H%M%S",
                examples=[
                    "143052", "14:30:52 (with :%H:%M:%S)", "14-30-52 (with :%H:%M:%S|-)", "143052.123 (with :%H%M%S.%f)"],
            ),
            TokenInfo(
                name="index",
                description="Sequential number",
                default_format="%d",
                examples=["1", "001 (with :%03d)"],
            ),
            TokenInfo(
                name="ext",
                description="Extension without leading dot",
                examples=["zip", "tar.gz"],
            ),
            TokenInfo(
                name=".ext",
                description="Extension with leading dot",
                examples=[".zip", ".tar.gz"],
            ),
        ]

    @staticmethod
    def get_example_render(template: str | None = None) -> str:
        """Get an example render of a template.

        Args:
            template: Template string, or None for default example

        Returns:
            Example rendered output
        """
        if template is None:
            template = "{base_name}_{date}.{ext}"

        tmpl = NamingTemplate(template)
        return tmpl.render(
            base_name="MyProject",
            ext="zip",
            index=1,
        )

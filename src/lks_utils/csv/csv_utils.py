"""
CSV utilities for loading, sniffing, and parsing CSV files.

Provides helpers for:
- Loading CSV files with automatic dialect detection
- Parsing decimal values (handles currency symbols, parentheses, thousands separators)
- Parsing dates in various formats
- Formatting decimals for output

Usage:
    from lks_utils.csv import load_csv, parse_decimal, parse_date

    # Load a CSV file (auto-detects delimiter)
    rows = load_csv("/path/to/file.csv")

    # Parse decimal values
    amount = parse_decimal("$1,234.56")  # Decimal('1234.56')
    loss = parse_decimal("(500)")        # Decimal('-500')

    # Parse dates
    date = parse_date("2023-12-25")  # "2023-12-25"
"""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


# Encoding constants
DEFAULT_CSV_ENCODING: str = "utf-8-sig"  # Handles BOM automatically
DEFAULT_SAMPLE_SIZE: int = 4096

# Default delimiters for dialect sniffing
DEFAULT_DELIMITERS: str = ",\t;|"

# Decimal parsing
DECIMAL_ZERO: str = "0"


def sniff_dialect(sample: str) -> csv.Dialect:
    """Detect CSV dialect from a sample string.

    Args:
        sample: Sample text from CSV file (first few KB is sufficient).

    Returns:
        Detected csv.Dialect object. Falls back to 'excel' dialect if
        detection fails.

    Examples:
        >>> dialect = sniff_dialect("a,b,c\\n1,2,3")
        >>> dialect.delimiter
        ','
    """
    try:
        return csv.Sniffer().sniff(sample, delimiters=DEFAULT_DELIMITERS)
    except csv.Error:
        return csv.get_dialect("excel")


def load_csv_with_sniff(
    path: str | Path,
    encoding: str = DEFAULT_CSV_ENCODING,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> list[dict[str, str]]:
    """Load a CSV file with automatic dialect detection.

    Args:
        path: Path to CSV file.
        encoding: File encoding (default: utf-8-sig to handle BOM).
        sample_size: Number of bytes to read for dialect detection.

    Returns:
        List of dictionaries (one per row), with keys from header row.
        Keys and values are stripped of whitespace.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file is empty or has no valid rows.

    Examples:
        >>> rows = load_csv_with_sniff("data.csv")
        >>> rows[0]["column_name"]
        'value'
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding=encoding, newline="") as handle:
        sample = handle.read(sample_size)
        if not sample.strip():
            raise ValueError(f"CSV file is empty: {path}")
        handle.seek(0)
        dialect = sniff_dialect(sample)
        reader = csv.DictReader(handle, dialect=dialect)
        rows = []
        for row in reader:
            # Normalize keys and values
            normalized = {
                k.strip(): (v or "").strip()
                for k, v in row.items()
                if k is not None
            }
            rows.append(normalized)
    return rows


def load_csv(
    path: str | Path,
    encoding: str = "utf-8-sig",
    delimiter: str | None = None,
) -> list[dict[str, str]]:
    """Load a CSV file.

    Args:
        path: Path to CSV file.
        encoding: File encoding (default: utf-8-sig to handle BOM).
        delimiter: Optional delimiter. If None, auto-detects.

    Returns:
        List of dictionaries (one per row).

    Raises:
        FileNotFoundError: If file doesn't exist.

    Examples:
        >>> rows = load_csv("data.csv")
        >>> rows = load_csv("data.tsv", delimiter="\\t")
    """
    if delimiter is None:
        return load_csv_with_sniff(path, encoding=encoding)

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        rows = []
        for row in reader:
            normalized = {
                k.strip(): (v or "").strip()
                for k, v in row.items()
                if k is not None
            }
            rows.append(normalized)
    return rows


def parse_decimal(value: str | None) -> Decimal:
    """Parse a string into a Decimal, handling common formats.

    Handles:
    - Currency symbols ($, €, £, etc.)
    - Thousands separators (commas)
    - Negative values in parentheses: "(500)" -> -500
    - Whitespace

    Args:
        value: String to parse.

    Returns:
        Parsed Decimal value. Returns Decimal("0") if parsing fails
        or value is empty/None.

    Examples:
        >>> parse_decimal("$1,234.56")
        Decimal('1234.56')
        >>> parse_decimal("(500)")
        Decimal('-500')
        >>> parse_decimal("")
        Decimal('0')
    """
    if not value:
        return Decimal("0")
    try:
        # Remove common currency symbols and whitespace
        cleaned = value.strip()
        for symbol in ("$", "€", "£", "¥", "₹", "₽", "₩"):
            cleaned = cleaned.replace(symbol, "")
        # Remove thousands separators (comma when used with decimal point)
        cleaned = cleaned.replace(",", "")
        # Handle accounting notation: (500) means -500
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]
        cleaned = cleaned.strip()
        if not cleaned:
            return Decimal("0")
        return Decimal(cleaned)
    except (InvalidOperation, AttributeError, ValueError):
        return Decimal("0")


def format_decimal(
    value: Decimal,
    precision: str = "0.000001",
    strip_trailing_zeros: bool = True,
) -> str:
    """Format a Decimal to string with specified precision.

    Args:
        value: Decimal value to format.
        precision: Precision as decimal string (default: 6 decimal places).
        strip_trailing_zeros: Remove trailing zeros and decimal point if True.

    Returns:
        Formatted string. Returns "0" for zero values.

    Examples:
        >>> format_decimal(Decimal("1.50000"))
        '1.5'
        >>> format_decimal(Decimal("100"))
        '100'
        >>> format_decimal(Decimal("1.23456789"), precision="0.01")
        '1.23'
    """
    if value == 0:
        return "0"
    quantized = value.quantize(Decimal(precision))
    formatted = f"{quantized:f}"
    if strip_trailing_zeros and "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


def parse_date(
    value: str,
    formats: list[str] | None = None,
    output_format: str = "%Y-%m-%d",
) -> str | None:
    """Parse a date string using common formats.

    Attempts to parse using each format in order until one succeeds.

    Args:
        value: Date string to parse.
        formats: List of strptime format strings to try.
            Defaults to common date formats if None.
        output_format: Output format string (default: ISO 8601 date).

    Returns:
        Formatted date string, or None if parsing fails.

    Examples:
        >>> parse_date("2023-12-25")
        '2023-12-25'
        >>> parse_date("12/25/2023")
        '2023-12-25'
        >>> parse_date("25.12.2023")
        '2023-12-25'
    """
    value = value.strip() if value else ""
    if not value:
        return None

    if formats is None:
        formats = [
            # ISO formats
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %I:%M:%S %p",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            # Common US/EU formats
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%m-%d-%Y",
            "%d-%m-%Y",
            "%d.%m.%Y",
            # Compact formats
            "%Y%m%d",
            # With time
            "%m/%d/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
        ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime(output_format)
        except ValueError:
            continue

    # Fallback: try parsing digits-only for YYYYMMDD
    try:
        cleaned = "".join(c for c in value if c.isdigit())
        if len(cleaned) >= 8:
            parsed = datetime.strptime(cleaned[:8], "%Y%m%d")
            return parsed.strftime(output_format)
    except ValueError:
        pass

    return None

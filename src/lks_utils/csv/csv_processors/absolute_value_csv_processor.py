"""Absolute-value CSV processor.

Strips negative signs from all numeric cell values so that every
number in the output is positive (or zero).  This is required by
importers such as Ghostfolio / stock-dashboard transaction validation,
which expect quantities, prices, fees, and amounts to be expressed as
positive values regardless of transaction direction.

Runs as a **postprocessor** — after column mapping and value
transformations have already produced the final output rows.

Non-numeric cells (text, dates, empty strings) are left untouched.
"""
from __future__ import annotations

import re

from lks_utils.csv.csv_processor import CSVProcessor

# Matches a string that is a negative number (optional whitespace,
# minus sign, then digits with optional decimal/comma separators).
_NEGATIVE_NUMBER: re.Pattern[str] = re.compile(
    r"^\s*-\s*([\d,]+\.?\d*)\s*$"
)


class AbsoluteValueCSVProcessor(CSVProcessor):
    """Convert all negative numeric values to positive.

    Any cell whose stripped value matches a negative number pattern
    (e.g. ``"-10000"``, ``"- 549.46"``, ``"-25,000.00"``) will have
    its leading minus sign removed.  All other cells pass through
    unchanged.
    """

    id: str = "absolute_value"
    name: str = "Absolute Values"
    description: str = (
        "Remove negative signs from all numeric values "
        "(Ghostfolio expects positive quantities/amounts)."
    )

    def process(
        self,
        rows: list[dict[str, str]],
        headers: list[str],
    ) -> list[dict[str, str]]:
        """Strip minus signs from negative numeric cells.

        Args:
            rows: List of row dicts (column_name → value).
            headers: Ordered list of column names.

        Returns:
            The same list of rows with negative numbers made positive.
        """
        for row in rows:
            for key in row:
                val: str = row[key]
                match: re.Match[str] | None = _NEGATIVE_NUMBER.match(val)
                if match:
                    row[key] = match.group(1)
        return rows

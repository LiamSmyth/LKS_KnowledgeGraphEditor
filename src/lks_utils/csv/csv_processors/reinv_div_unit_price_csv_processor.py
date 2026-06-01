"""Reinvestment dividend unit-price CSV processor.

Handles a common bank-CSV edge case where reinvestment-dividend rows
have ``unit_price = 0`` but embed the gross amount in the description
column as ``GRS: <amount>``.

This processor:
1. Finds rows where the unit-price column is ``"0"`` (or empty).
2. Searches the description column for a ``GRS: <number>`` pattern.
3. Computes ``unit_price = gross / quantity`` (if quantity > 0).
4. Writes the computed unit price back into the row.

Column detection is fuzzy: it looks for headers containing common
keywords so it works across slight CSV naming variations.
"""
from __future__ import annotations

import re

from lks_utils.csv.csv_processor import CSVProcessor

_GRS_PATTERN: re.Pattern[str] = re.compile(
    r"GRS:\s*([\d,]+\.?\d*)", re.IGNORECASE
)

# Common header keywords (lowercased) for fuzzy column matching
_UNIT_PRICE_KEYWORDS: list[str] = ["unit price", "unitprice", "price"]
_QUANTITY_KEYWORDS: list[str] = ["quantity", "qty", "units", "shares"]
_DESCRIPTION_KEYWORDS: list[str] = [
    "description", "desc", "details", "memo", "narrative"]


def _find_column(headers: list[str], keywords: list[str]) -> str | None:
    """Find the first header that contains any of the keywords.

    Args:
        headers: List of column header names.
        keywords: Lowercased keywords to search for.

    Returns:
        Matching header name, or ``None`` if not found.
    """
    for header in headers:
        lower = header.lower().strip()
        for kw in keywords:
            if kw in lower:
                return header
    return None


class ReinvDivUnitPriceCSVProcessor(CSVProcessor):
    """Compute unit price from GRS value in description for Reinv Div rows.

    When the unit-price column is ``"0"`` or empty and the description
    contains ``GRS: <amount>``, this processor computes
    ``unit_price = gross / quantity`` and writes it into the unit-price
    column.

    Rows where the unit price is already populated (non-zero) are left
    untouched.
    """

    id: str = "reinv_div_unit_price"
    name: str = "Reinv Div → Unit Price"
    description: str = (
        "Compute unit price from GRS value in description "
        "when unit price is 0 or empty."
    )

    def process(
        self,
        rows: list[dict[str, str]],
        headers: list[str],
    ) -> list[dict[str, str]]:
        """Process rows: fill missing unit prices from GRS in description.

        Args:
            rows: List of row dicts.
            headers: Ordered column names.

        Returns:
            The same list of rows, with unit-price cells filled where
            applicable.
        """
        # Detect columns
        price_col: str | None = _find_column(headers, _UNIT_PRICE_KEYWORDS)
        qty_col: str | None = _find_column(headers, _QUANTITY_KEYWORDS)
        desc_col: str | None = _find_column(headers, _DESCRIPTION_KEYWORDS)

        if not price_col or not qty_col or not desc_col:
            # Required columns not found — skip silently
            return rows

        for row in rows:
            price_str: str = row.get(price_col, "").strip()

            # Only act when unit price is missing or zero
            if price_str and price_str != "0":
                continue

            description: str = row.get(desc_col, "")
            match: re.Match[str] | None = _GRS_PATTERN.search(description)
            if not match:
                continue

            try:
                gross: float = float(match.group(1).replace(",", ""))
            except ValueError:
                continue

            qty_str: str = row.get(qty_col, "").strip()
            try:
                quantity: float = float(qty_str.replace(",", ""))
            except ValueError:
                continue

            if quantity <= 0:
                continue

            unit_price: float = gross / quantity
            row[price_col] = f"{unit_price:.6f}"

        return rows

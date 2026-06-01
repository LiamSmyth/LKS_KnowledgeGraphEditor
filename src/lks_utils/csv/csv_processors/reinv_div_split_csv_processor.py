"""Reinvestment-dividend row splitter CSV processor.

Splits each ``Reinv Div`` row into two separate rows:

1. **Dividend** — records the dividend income.
2. **Buy** — records the reinvestment purchase.

This is a **preprocessor**: it runs on the raw bank CSV *before* any
column mapping, ticker remapping, or field extraction.  Both output
rows keep the original column structure intact so downstream mapping
still works normally.

GRS (gross amount) is extracted from the description column to compute
the per-unit price (``GRS / quantity``), which populates the unit-price
column for *both* rows.

Example source row::

    Trade Date | Activity   | Symbol  | Unit Price | Unit/Shares | Net Amount | Description
    2026-01-20 | Reinv Div  | CCM5013 | 0          | 45.025      | 0          | ... GRS: 1690.50 ...

Becomes::

    2026-01-20 | Dividend   | CCM5013 | 37.55...   | 45.025      | 1690.50    | ... GRS: 1690.50 ...
    2026-01-20 | Buy        | CCM5013 | 37.55...   | 45.025      | 0          | ... GRS: 1690.50 ...
"""
from __future__ import annotations

import re

from lks_utils.csv.csv_processor import CSVProcessor

_GRS_PATTERN: re.Pattern[str] = re.compile(
    r"GRS:\s*([\d,]+\.?\d*)", re.IGNORECASE,
)

# Fuzzy column-name keywords (lowercased) for auto-detection
_ACTIVITY_KEYWORDS: list[str] = ["activity", "action", "transaction type"]
_UNIT_PRICE_KEYWORDS: list[str] = ["unit price", "unitprice", "price"]
_QUANTITY_KEYWORDS: list[str] = ["quantity",
                                 "qty", "units", "shares", "unit/shares"]
_NET_AMOUNT_KEYWORDS: list[str] = ["net amount", "netamount", "amount", "net"]
_DESCRIPTION_KEYWORDS: list[str] = [
    "description", "desc", "details", "memo", "narrative",
]

# Activity values that signify a reinvested dividend (lowercased)
_REINV_DIV_VALUES: set[str] = {"reinv div",
                               "reinvest dividend", "reinvestment dividend"}


def _find_column(headers: list[str], keywords: list[str]) -> str | None:
    """Return the first header whose lowercased name contains a keyword."""
    for header in headers:
        lower: str = header.lower().strip()
        for kw in keywords:
            if kw in lower:
                return header
    return None


class ReinvDivSplitCSVProcessor(CSVProcessor):
    """Split ``Reinv Div`` rows into a Dividend row and a Buy row.

    Designed to run as a **preprocessor** in the CSV-mapper pipeline,
    before any column remapping or value mapping takes place.  Both
    output rows retain the original column structure.

    Requirements:
        * An *activity* column whose value matches ``Reinv Div``
          (case-insensitive, stripped).
        * A *description* column containing ``GRS: <amount>``.
        * A *quantity* (``unit/shares``) column with a numeric value > 0.
    """

    id: str = "reinv_div_split"
    name: str = "Reinv Div → Dividend + Buy"
    description: str = (
        "Split reinvestment-dividend rows into a Dividend "
        "income row and a separate Buy row."
    )

    def process(
        self,
        rows: list[dict[str, str]],
        headers: list[str],
    ) -> list[dict[str, str]]:
        """Split Reinv Div rows into Dividend + Buy pairs.

        Args:
            rows: List of row dicts (column_name → value).
            headers: Ordered list of column names.

        Returns:
            New list with each Reinv Div row replaced by two rows.
            Non-matching rows pass through unchanged.
        """
        activity_col: str | None = _find_column(headers, _ACTIVITY_KEYWORDS)
        desc_col: str | None = _find_column(headers, _DESCRIPTION_KEYWORDS)
        qty_col: str | None = _find_column(headers, _QUANTITY_KEYWORDS)
        price_col: str | None = _find_column(headers, _UNIT_PRICE_KEYWORDS)
        net_col: str | None = _find_column(headers, _NET_AMOUNT_KEYWORDS)

        if not activity_col or not desc_col or not qty_col:
            # Required columns not found — pass through unchanged
            return rows

        result: list[dict[str, str]] = []

        for row in rows:
            activity: str = row.get(activity_col, "").strip()

            if activity.lower() not in _REINV_DIV_VALUES:
                result.append(row)
                continue

            # Extract GRS amount from description
            description: str = row.get(desc_col, "")
            match: re.Match[str] | None = _GRS_PATTERN.search(description)
            if not match:
                # No GRS found — keep original row unchanged
                result.append(row)
                continue

            try:
                gross: float = float(match.group(1).replace(",", ""))
            except ValueError:
                result.append(row)
                continue

            # Parse quantity
            qty_str: str = row.get(qty_col, "").strip()
            try:
                quantity: float = float(qty_str.replace(",", ""))
            except ValueError:
                result.append(row)
                continue

            if quantity <= 0:
                result.append(row)
                continue

            unit_price: float = gross / quantity

            # --- Dividend row ---
            div_row: dict[str, str] = dict(row)
            div_row[activity_col] = "Dividend"
            if price_col:
                div_row[price_col] = f"{unit_price:.6f}"
            if net_col:
                div_row[net_col] = f"{gross:.2f}"
            result.append(div_row)

            # --- Buy row ---
            buy_row: dict[str, str] = dict(row)
            buy_row[activity_col] = "Buy"
            if price_col:
                buy_row[price_col] = f"{unit_price:.6f}"
            # Net Amount stays 0 (no cash outflow — funded by dividend)
            result.append(buy_row)

        return result

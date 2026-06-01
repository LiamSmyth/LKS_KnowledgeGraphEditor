"""Yahoo Finance price lookup CSV postprocessor.

Fills missing ``UnitPrice`` values by fetching historical close prices
from Yahoo Finance.  This processor is designed to run as a
**postprocessor** — after field mapping has already resolved valid
Yahoo ticker symbols into the ``Symbol`` column.

For each row where ``UnitPrice`` is ``"0"``, ``"0.00"``, or empty, the
processor:

1. Reads the ``Symbol`` and ``Date`` columns.
2. Queries ``yfinance`` for the close price on that date.
3. Writes the close price back into ``UnitPrice``.

Multiple rows for the same symbol are batched into a single API call
covering the full date range, minimising network requests.

Requires:
    ``yfinance`` (``pip install yfinance``) — will skip gracefully if
    the package is not installed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from lks_utils.csv.csv_processor import CSVProcessor

try:
    import yfinance as yf

    HAS_YFINANCE = True
except ImportError:  # pragma: no cover
    HAS_YFINANCE = False

log: logging.Logger = logging.getLogger(__name__)

# Ghostfolio date format
_DATE_FORMAT: str = "%Y-%m-%d"


def _find_column(headers: list[str], candidates: list[str]) -> str | None:
    """Return the first header that matches any candidate (case-insensitive).

    Unlike the fuzzy substring matching in the reinv-div processor, this
    uses exact case-insensitive comparison because the postprocessor
    operates on schema field names, which are well-known.
    """
    lower_map: dict[str, str] = {h.lower().strip(): h for h in headers}
    for c in candidates:
        found: str | None = lower_map.get(c.lower())
        if found is not None:
            return found
    return None


def _fetch_close_prices(
    symbol: str,
    dates: list[datetime],
) -> dict[str, float]:
    """Fetch historical close prices for *symbol* covering *dates*.

    A single ``yfinance`` request is made spanning from the earliest
    date minus one day to the latest date plus two days, so that
    weekends / holidays are covered by the nearest trading day.

    Args:
        symbol: Yahoo Finance ticker (e.g. ``"AAPL"``, ``"XYZ.TO"``).
        dates: List of datetime objects for which prices are needed.

    Returns:
        Mapping of ``"YYYY-MM-DD"`` → close price.  Only dates that
        had a trading-day close within ±3 calendar days are included.
    """
    if not dates:
        return {}

    min_date: datetime = min(dates) - timedelta(days=5)
    max_date: datetime = max(dates) + timedelta(days=5)

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(
            start=min_date.strftime(_DATE_FORMAT),
            end=max_date.strftime(_DATE_FORMAT),
            interval="1d",
        )
    except Exception:
        log.warning("yfinance lookup failed for %s", symbol, exc_info=True)
        return {}

    if hist is None or hist.empty:
        log.info("No price data returned for %s", symbol)
        return {}

    # Build a lookup from date string → close price
    close_by_date: dict[str, float] = {}
    for idx, row in hist.iterrows():
        date_str: str = idx.strftime(_DATE_FORMAT)  # type: ignore[union-attr]
        close_by_date[date_str] = float(row["Close"])

    # For each requested date, find the nearest trading day close
    result: dict[str, float] = {}
    for dt in dates:
        target: str = dt.strftime(_DATE_FORMAT)
        if target in close_by_date:
            result[target] = close_by_date[target]
            continue
        # Search ±3 days for nearest trading day
        for offset in range(1, 4):
            before: str = (dt - timedelta(days=offset)).strftime(_DATE_FORMAT)
            after: str = (dt + timedelta(days=offset)).strftime(_DATE_FORMAT)
            if before in close_by_date:
                result[target] = close_by_date[before]
                break
            if after in close_by_date:
                result[target] = close_by_date[after]
                break

    return result


class YahooPriceLookupCSVProcessor(CSVProcessor):
    """Fill missing UnitPrice by fetching Yahoo Finance close prices.

    Designed to run as a **postprocessor** where the ``Symbol`` column
    already contains valid Yahoo ticker symbols (mapped via value maps).

    Rows where ``UnitPrice`` is already populated (non-zero, non-empty)
    are left untouched.  If ``yfinance`` is not installed, the
    processor logs a warning and returns rows unchanged.
    """

    id: str = "yahoo_price_lookup"
    name: str = "Yahoo Price Lookup"
    description: str = (
        "Fetch missing UnitPrice from Yahoo Finance historical close "
        "prices using the Symbol and Date columns."
    )

    def process(
        self,
        rows: list[dict[str, str]],
        headers: list[str],
    ) -> list[dict[str, str]]:
        """Fill missing unit prices from Yahoo Finance.

        Args:
            rows: Mapped output row dicts.
            headers: Ordered output field names.

        Returns:
            Rows with ``UnitPrice`` filled where possible.
        """
        if not HAS_YFINANCE:
            log.warning(
                "yfinance not installed — skipping Yahoo price lookup. "
                "Install with: pip install yfinance"
            )
            return rows

        # Detect columns
        price_col: str | None = _find_column(
            headers, ["UnitPrice", "unitprice", "unit_price", "price"],
        )
        symbol_col: str | None = _find_column(
            headers, ["Symbol", "symbol", "ticker"],
        )
        date_col: str | None = _find_column(
            headers, ["Date", "date", "transaction_date"],
        )

        if not price_col or not symbol_col or not date_col:
            log.info(
                "Yahoo price lookup: required columns not found "
                "(need UnitPrice, Symbol, Date). Found: price=%s, "
                "symbol=%s, date=%s",
                price_col, symbol_col, date_col,
            )
            return rows

        # Collect rows that need price lookup, grouped by symbol
        needs_lookup: dict[str, list[tuple[int, datetime]]] = {}
        for idx, row in enumerate(rows):
            price_str: str = row.get(price_col, "").strip()
            if price_str and price_str not in ("0", "0.00", "0.0"):
                continue

            symbol: str = row.get(symbol_col, "").strip()
            date_str: str = row.get(date_col, "").strip()
            if not symbol or not date_str:
                continue

            try:
                dt: datetime = datetime.strptime(date_str, _DATE_FORMAT)
            except ValueError:
                log.debug(
                    "Cannot parse date %r for row %d — skipping",
                    date_str, idx,
                )
                continue

            needs_lookup.setdefault(symbol, []).append((idx, dt))

        if not needs_lookup:
            return rows

        log.info(
            "Yahoo price lookup: %d symbols, %d rows to fill",
            len(needs_lookup),
            sum(len(v) for v in needs_lookup.values()),
        )

        # Fetch prices per symbol (batched)
        for symbol, entries in needs_lookup.items():
            dates: list[datetime] = [dt for _, dt in entries]
            prices: dict[str, float] = _fetch_close_prices(symbol, dates)

            for row_idx, dt in entries:
                date_key: str = dt.strftime(_DATE_FORMAT)
                if date_key in prices:
                    rows[row_idx][price_col] = f"{prices[date_key]:.6f}"
                    log.debug(
                        "Filled %s %s → %s",
                        symbol, date_key, rows[row_idx][price_col],
                    )
                else:
                    log.warning(
                        "No price found for %s on %s", symbol, date_key,
                    )

        return rows

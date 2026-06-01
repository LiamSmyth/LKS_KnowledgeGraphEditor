"""CSV processor registry.

Discovers all :class:`CSVProcessor` subclasses defined in this package
and exposes them via :func:`get_all_processors` and
:func:`get_processor_by_id`.

Usage:
    from lks_utils.csv.csv_processors import get_all_processors, get_processor_by_id

    all_procs = get_all_processors()          # list[CSVProcessor]
    proc = get_processor_by_id("reinv_div_unit_price")  # CSVProcessor | None
"""
from __future__ import annotations

from lks_utils.csv.csv_processor import CSVProcessor

# ---- Import all processor modules so their classes register ----
from lks_utils.csv.csv_processors.absolute_value_csv_processor import (
    AbsoluteValueCSVProcessor,
)
from lks_utils.csv.csv_processors.reinv_div_split_csv_processor import (
    ReinvDivSplitCSVProcessor,
)
from lks_utils.csv.csv_processors.reinv_div_unit_price_csv_processor import (
    ReinvDivUnitPriceCSVProcessor,
)
from lks_utils.csv.csv_processors.yahoo_price_lookup_csv_processor import (
    YahooPriceLookupCSVProcessor,
)

# ---- Registry ----

_PROCESSORS: list[CSVProcessor] = [
    AbsoluteValueCSVProcessor(),
    ReinvDivSplitCSVProcessor(),
    ReinvDivUnitPriceCSVProcessor(),
    YahooPriceLookupCSVProcessor(),
]


def get_all_processors() -> list[CSVProcessor]:
    """Return a list of all registered CSV processor instances.

    Returns:
        List of all available processor instances.
    """
    return list(_PROCESSORS)


def get_processor_by_id(processor_id: str) -> CSVProcessor | None:
    """Look up a processor by its unique ``id``.

    Args:
        processor_id: The ``id`` attribute of the desired processor.

    Returns:
        The matching processor instance, or ``None`` if not found.
    """
    for proc in _PROCESSORS:
        if proc.id == processor_id:
            return proc
    return None


__all__ = [
    "AbsoluteValueCSVProcessor",
    "CSVProcessor",
    "ReinvDivSplitCSVProcessor",
    "ReinvDivUnitPriceCSVProcessor",
    "YahooPriceLookupCSVProcessor",
    "get_all_processors",
    "get_processor_by_id",
]

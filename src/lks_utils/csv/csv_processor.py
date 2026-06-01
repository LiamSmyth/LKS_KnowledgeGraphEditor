"""Base class for CSV row processors.

CSVProcessors are composable, reorderable scripts that transform CSV data
row-by-row or in bulk. They serve as a plugin/middleware layer between
raw CSV loading and field-level mapping, enabling edge-case data fixes
without breaking the generic mapper pipeline.

Usage:
    from lks_utils.csv import CSVProcessor

    class MyProcessor(CSVProcessor):
        id = "my_processor"
        name = "My Processor"
        description = "Does something useful to CSV rows."

        def process(self, rows, headers):
            for row in rows:
                row["col"] = row["col"].strip()
            return rows
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class CSVProcessor(ABC):
    """Base class for CSV row processors.

    Subclasses MUST define class-level ``id``, ``name``, and
    ``description`` attributes and implement :meth:`process`.

    Attributes:
        id: Unique identifier used for serialization and registry lookup.
        name: Human-readable display name.
        description: One-line description shown as tooltip in the UI.
    """

    id: str = ""
    name: str = ""
    description: str = ""

    @abstractmethod
    def process(
        self,
        rows: list[dict[str, str]],
        headers: list[str],
    ) -> list[dict[str, str]]:
        """Process CSV rows and return the (possibly modified) rows.

        Implementations may mutate rows in-place **and** return them,
        or return a new list.  The caller always uses the returned value.

        Args:
            rows: List of row dicts (column_name → value).
            headers: Ordered list of column names.

        Returns:
            Processed list of row dicts (same or new list).
        """

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, str]:
        """Serialize to a dict for persistence.

        Returns:
            Dict with processor ``id``.
        """
        return {"id": self.id}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r})"

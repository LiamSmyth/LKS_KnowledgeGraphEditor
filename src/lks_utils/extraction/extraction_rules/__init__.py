"""Extraction rules organized by type."""
from __future__ import annotations

from .composite_rule import CompositeExtractionRule
from .csv_rule import CSVExtractionRule
from .text_rule import TextExtractionRule

# Import individual rules to trigger registration
from . import csv_rules, text_rules

__all__ = [
    "TextExtractionRule",
    "CSVExtractionRule",
    "CompositeExtractionRule",
]

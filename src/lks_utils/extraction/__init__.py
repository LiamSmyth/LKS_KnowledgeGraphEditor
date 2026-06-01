"""Text extraction rules for transforming unstructured text into structured data.

This module provides a generic, composable system for extracting information
from text and CSV data using various strategies (regex, substring matching,
JSON extraction, etc.).
"""
from __future__ import annotations

from .extraction_rule import (
    ExtractionRule,
    ExtractionTestResult,
    register_rule_type,
    rule_from_dict,
)
from .extraction_spec import ExtractionSpec
from .extract_multiple import ExtractionResult, OrderedMatch, extract_multiple
from .extraction_rules.composite_rule import CompositeExtractionRule
from .extraction_rules.csv_rules import ColumnMapRule, ColumnSelectRule, RowFilterRule
from .extraction_rules.text_rules import (
    DelimiterExtractRule,
    JsonArrayExtractRule,
    JsonObjectExtractRule,
    LineSelectRule,
    PrefixExtractRule,
    RegexExtractRule,
    SplitExtractRule,
    SubstringMapRule,
)
from .preprocessing import (
    apply_preprocessing,
    get_preprocessor,
    lowercase,
    normalize_brackets,
    normalize_bracket_style,
    register_preprocessor,
    strip_code_fences,
    strip_whitespace,
)
from .wildcard import (
    WILDCARD_HELP_TEXT,
    glob_to_regex,
    has_wildcards,
    wildcard_find,
    wildcard_match_length,
    wildcard_match_line,
)

__all__ = [
    # Base classes and infrastructure
    "ExtractionRule",
    "ExtractionTestResult",
    "register_rule_type",
    "rule_from_dict",
    # Text extraction rules
    "RegexExtractRule",
    "SubstringMapRule",
    "SplitExtractRule",
    "LineSelectRule",
    "DelimiterExtractRule",
    "PrefixExtractRule",
    "JsonObjectExtractRule",
    "JsonArrayExtractRule",
    # CSV extraction rules
    "ColumnSelectRule",
    "ColumnMapRule",
    "RowFilterRule",
    # Composite rule
    "CompositeExtractionRule",
    # Preprocessing
    "apply_preprocessing",
    "get_preprocessor",
    "register_preprocessor",
    "normalize_brackets",
    "normalize_bracket_style",
    "strip_whitespace",
    "lowercase",
    "strip_code_fences",
    # Wildcard utilities
    "WILDCARD_HELP_TEXT",
    "glob_to_regex",
    "has_wildcards",
    "wildcard_find",
    "wildcard_match_length",
    "wildcard_match_line",
    # Extraction spec (generic, LLM-agnostic)
    "ExtractionSpec",
    "ExtractionResult",
    "OrderedMatch",
    "extract_multiple",
]

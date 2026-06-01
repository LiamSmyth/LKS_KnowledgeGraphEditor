"""
Text processing utilities: normalization, sanitization, filename handling.
"""
from __future__ import annotations

from lks_utils.text.naming_template import NamingTemplate, TokenInfo
from lks_utils.text.normalization import normalize_text_for_console
from lks_utils.text.sanitization import handle_spaces, clamp_length, remove_filesystem_unsafe_chars, remove_special_characters, normalize_whitespace_and_underscores, strip_leading_trailing_chars, ensure_non_empty, split_name_extension, remove_emojis_and_symbols, remove_non_ascii_chars, convert_fullwidth_to_ascii, convert_to_ascii_only, remove_multiple_periods, remove_ytdlp_format_codes, sanitize_reserved_names, validate_path_safety, sanitize_tag, sanitize_tags, MAX_TAG_LENGTH
from lks_utils.text.filename import sanitize_filename, sanitize_video_filename
from lks_utils.text.repetition import collapse_repetitions
from lks_utils.text.search import normalize_search_text, suggest_close_matches
from lks_utils.text.chunking import chunk_text

# Note: Iterative processing has moved to lks_utils.llm.iterator
# Import from there: from lks_utils.llm.iterator import LLMIteratorProcessor, LLMIteratorProcessorConfig

__all__ = [
    # Naming template
    "NamingTemplate",
    "TokenInfo",
    # Normalization
    "normalize_text_for_console",
    # Sanitization - basic
    "handle_spaces",
    "clamp_length",
    "remove_filesystem_unsafe_chars",
    "remove_special_characters",
    "normalize_whitespace_and_underscores",
    "strip_leading_trailing_chars",
    "ensure_non_empty",
    "split_name_extension",
    # Sanitization - advanced
    "remove_emojis_and_symbols",
    "remove_non_ascii_chars",
    "convert_fullwidth_to_ascii",
    "convert_to_ascii_only",
    "remove_multiple_periods",
    "remove_ytdlp_format_codes",
    "sanitize_reserved_names",
    "validate_path_safety",
    # Tag sanitization
    "sanitize_tag",
    "sanitize_tags",
    "MAX_TAG_LENGTH",
    # Filename
    "sanitize_filename",
    "sanitize_video_filename",
    # Repetition
    "collapse_repetitions",
    # Search
    "normalize_search_text",
    "suggest_close_matches",
    # Chunking
    "chunk_text",
]

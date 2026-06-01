"""
Text normalization utilities.

Fixes common UTF-8/Windows-1252 mojibake (e.g. 'âœ…' -> '✅', 'ðŸ"' -> '📝')
and normalizes unicode so emojis render correctly.

Uses ftfy primarily, plus a lightweight cp1252 repair heuristic.
"""
from __future__ import annotations

import unicodedata

# ftfy is a required dependency
from ftfy import fix_text as _ftfy_fix  # type: ignore[assignment]


def _looks_better(original: str, candidate: str) -> bool:
    """Heuristic: candidate is better if it reduces typical mojibake artifacts."""
    # Common mojibake tokens in cp1252/utf-8 mixups
    suspicious = ["Ã", "Â", "â", "ð", "ï", "¸", "œ", "€", ""]

    def score(s: str) -> int:
        if not s:
            return 0
        return sum(s.count(tok) for tok in suspicious if tok)

    return score(candidate) < score(original)


def _repair_cp1252_mojibake(text: str) -> str:
    """Attempt to reverse UTF-8 text decoded as cp1252 (common mojibake)."""
    try:
        # Re-encode as latin-1 bytes and decode as utf-8
        fixed = text.encode(
            "latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if _looks_better(text, fixed):
            return fixed
    except Exception:
        pass
    return text


def normalize_text_for_console(text: str | None) -> str:
    """Normalize text for console output, repairing mojibake/emojis when possible.

    Args:
        text: The text to normalize. None is converted to empty string.

    Returns:
        Normalized text safe for console output.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    original = text

    # First pass: ftfy
    try:
        text = _ftfy_fix(text)  # type: ignore[misc]
    except Exception:
        # If ftfy unexpectedly fails, keep original and try heuristic
        text = original

    # Second pass: repair common cp1252 mis-decoding if it improves text
    maybe = _repair_cp1252_mojibake(text)
    if _looks_better(text, maybe):
        text = maybe

    # Normalize to NFC for consistent emoji rendering
    try:
        text = unicodedata.normalize("NFC", text)
    except Exception:
        pass

    return text

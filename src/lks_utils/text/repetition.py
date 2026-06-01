"""Text repetition detection and removal utilities.

This module provides functions to detect and collapse pathological repeated
patterns in text, particularly useful for cleaning up LLM outputs that loop.
"""

from __future__ import annotations

import re


def collapse_repetitions(
    text: str,
    min_pattern_len: int = 8,
    max_pattern_len: int = 4096,
    max_repeats: int = 1,
    min_consecutive: int = 3,
    normalize_whitespace: bool = True,
    gap_ws_max: int = 1,
) -> tuple[str, int]:
    """Collapse runs of consecutive repeated substrings.

    Scans for patterns between min_pattern_len and max_pattern_len characters
    that repeat consecutively at least min_consecutive times, and replaces such
    runs with at most max_repeats copies.

    Args:
        text: Input text to process
        min_pattern_len: Minimum substring length to consider a pattern (default: 8)
        max_pattern_len: Maximum substring length to consider (default: 4096)
        max_repeats: Cap consecutive repeats to this many copies (default: 1)
        min_consecutive: Minimum consecutive occurrences to treat as repetition (default: 3)
        normalize_whitespace: Coalesce spaces and blank lines before detection (default: True)
        gap_ws_max: Allow up to this many whitespace chars between repeats (default: 1)

    Returns:
        Tuple of (cleaned_text, replacements_made)

    Examples:
        >>> text = "Hello world! " * 5
        >>> cleaned, count = collapse_repetitions(text, min_pattern_len=5, min_consecutive=3)
        >>> count >= 1
        True
        >>> len(cleaned) < len(text)
        True
    """
    if not text:
        return text, 0

    # Optional whitespace normalization helps align boundaries
    if normalize_whitespace:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

    replacements: int = 0
    max_passes: int = 4  # safety cap to avoid edge cases looping

    # Precompute bounds
    min_len = max(1, int(min_pattern_len))
    max_len = max(min_len, int(max_pattern_len))
    cap_repeats = max(1, int(max_repeats))
    gap_ws = max(0, int(gap_ws_max))

    for _ in range(max_passes):
        changed = False
        i = 0
        n = len(text)
        out_parts: list[str] = []

        while i < n:
            # (pattern, run_len, total_span)
            best_match: tuple[str, int, int] | None = None

            # Effective maximum pattern length at this position
            max_l_here = min(max_len, (n - i) // min_consecutive)
            if max_l_here < min_len:
                # Can't possibly have min_consecutive repeats at this position
                out_parts.append(text[i])
                i += 1
                continue

            # Try candidate pattern lengths
            for pattern_len in range(min_len, max_l_here + 1):
                pattern = text[i: i + pattern_len]
                if not pattern.strip():
                    # Skip all-whitespace patterns
                    continue

                # Count consecutive repeats of pattern starting at i
                run = 1
                j = i + pattern_len
                while True:
                    if j + pattern_len > n:
                        break
                    if text[j: j + pattern_len] != pattern:
                        # Optionally allow small whitespace gap between repeats
                        if gap_ws > 0:
                            gap = 0
                            while (
                                gap < gap_ws
                                and j + gap < n
                                and text[j + gap].isspace()
                            ):
                                gap += 1
                            if (
                                gap > 0
                                and j + gap + pattern_len <= n
                                and text[j + gap: j + gap + pattern_len] == pattern
                            ):
                                j += gap  # consume the gap
                            else:
                                break
                        else:
                            break
                    # We have a repeat
                    run += 1
                    j += pattern_len

                if run >= min_consecutive:
                    # Prefer the longest span we find
                    span = run * pattern_len
                    if best_match is None or span > best_match[2]:
                        best_match = (pattern, run, span)

            if best_match:
                pattern, run, span = best_match
                # Keep at most cap_repeats copies
                keep = min(cap_repeats, run)
                out_parts.append(pattern * keep)
                i += span
                replacements += 1
                changed = True
            else:
                out_parts.append(text[i])
                i += 1

        new_text = "".join(out_parts)
        if not changed:
            return new_text, replacements
        text = new_text

    return text, replacements
